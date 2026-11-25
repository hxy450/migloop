"""编年史事件收集 —— CC 会话实录 → filestory.Ev 流。

与 collect_blame_events 同款的"独立轻扫"模式:不动 extract() 的主流程,
单独一遍读 transcript(主线 + subagents/),产出引擎认的五种事件。
全部证据规则与 0723 复盘探针一致(replay_verify.py,数字见 filestory.py 提交):

- Read 工具结果 = 全文快照(toolUseResult.file.content 是裸全文,
  startLine==1 且 numLines==totalLines 才算 full,能当锚)
- Write/Edit/MultiEdit = 全文写/原生差量
- shell 命令经 shellparse 白盒解析:heredoc 唯一体+唯一写目标 → 全文写;
  其余命令级写 → wopaque;内容读带命令自带的行区间;cp 源/< 输入 → 依赖读
- 「整条命令就是一次干净 cat」的输出 = 全文快照(宁可漏,不把 echo 噪音当快照)

agent 身份:主线 = ``__main__:<sid8>``,子代理 = 其 transcript 文件 stem。
codex 收集器另行提供(需复用 codex adapter 的 JS 内嵌调用解码,不在此重造)。
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any

from migloop.filestory import Ev
from migloop.shellparse import _split_segments, _strip_heredocs, parse_shell


def _norm(p: object, cwd: object) -> str:
    s = str(p).replace("\\", "/")
    if not (s.startswith("/") or (len(s) > 1 and s[1] == ":")):
        c = str(cwd or "").replace("\\", "/").rstrip("/")
        s = c + "/" + s if c else s
    return s


def _clean_single_cat(cmd: str) -> str | None:
    """整条命令 = (可有 cd) + 一次干净 cat <单一路径>,无管道无其它输出段。"""
    text, bodies = _strip_heredocs(cmd or "")
    if bodies:
        return None
    segs = [s for s in _split_segments(text) if not s.strip().startswith("cd ")]
    if len(segs) != 1:
        return None
    io = parse_shell(segs[0])
    if len(io.content_reads) == 1 and not io.writes and not io.dep_reads:
        s = segs[0].strip()
        if s.startswith("cat ") and "|" not in s:
            return io.content_reads[0]
    return None


_ERRISH = ("no such file", "cat:")


def _collect_one(path: str, who: str, seq: list[int]) -> list[Ev]:
    evs: list[Ev] = []
    pend: dict[Any, tuple[str, str, Any]] = {}   # tool_use_id -> (cmd, ts, cwd)

    def nxt() -> int:
        seq[0] += 1
        return seq[0]

    with open(path, encoding="utf-8", errors="ignore") as stream:
        lines = stream.readlines()
    for line in lines:
        try:
            r = json.loads(line)
        except Exception:
            continue
        ts = str(r.get("timestamp") or "")
        cwd = r.get("cwd")
        m = r.get("message")
        tur = r.get("toolUseResult")
        if isinstance(tur, dict) and isinstance(tur.get("file"), dict):
            f = tur["file"]
            if isinstance(f.get("content"), str) and f.get("numLines"):
                full = ((f.get("startLine") or 1) == 1
                        and f.get("numLines") == f.get("totalLines"))
                evs.append(Ev(ts, nxt(), "read", _norm(f.get("filePath"), cwd), who,
                              content=f["content"], full=bool(full),
                              start=f.get("startLine") or 1, n=f["numLines"]))
        if not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        for b in m["content"]:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                nm = b.get("name")
                if nm == "Write" and isinstance(inp.get("file_path"), str):
                    evs.append(Ev(ts, nxt(), "wfull", _norm(inp["file_path"], cwd),
                                  who, content=str(inp.get("content") or "")))
                elif nm in ("Edit", "MultiEdit") and isinstance(inp.get("file_path"), str):
                    edits = inp.get("edits") if nm == "MultiEdit" else [inp]
                    for e in edits or []:
                        if not isinstance(e, dict):
                            continue
                        evs.append(Ev(ts, nxt(), "edit", _norm(inp["file_path"], cwd),
                                      who, old=str(e.get("old_string") or ""),
                                      new=str(e.get("new_string") or ""),
                                      replace_all=bool(e.get("replace_all"))))
                elif nm in ("Bash", "PowerShell"):
                    cmd = str(inp.get("command") or "")
                    io = parse_shell(cmd)
                    if len(io.writes) == 1 and len(io.scripts) == 1 and ">" in cmd:
                        evs.append(Ev(ts, nxt(), "wfull", _norm(io.writes[0], cwd),
                                      who, content=next(iter(io.scripts.values()))))
                    else:
                        for w in io.writes:
                            evs.append(Ev(ts, nxt(), "wopaque", _norm(w, cwd), who))
                    for rp in io.content_reads:
                        sp = io.spans.get(rp)
                        evs.append(Ev(ts, nxt(), "read", _norm(rp, cwd), who,
                                      start=sp[0] if sp else None,
                                      n=sp[1] if sp else None))
                    for dp in io.dep_reads:
                        evs.append(Ev(ts, nxt(), "read", _norm(dp, cwd), who, dep=True))
                    pend[b.get("id")] = (cmd, ts, cwd)
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in pend:
                cmd, _uts, ucwd = pend.pop(b["tool_use_id"])
                out_raw = b.get("content")
                if isinstance(out_raw, list):
                    out = "\n".join(x.get("text", "") for x in out_raw
                                    if isinstance(x, dict))
                else:
                    out = str(out_raw or "")
                tgt = _clean_single_cat(cmd)
                if tgt and out.strip() and not out.lower().startswith(_ERRISH):
                    evs.append(Ev(ts, nxt(), "read", _norm(tgt, ucwd), who,
                                  content=out, full=True))
    return evs


def collect_events_cc(main_jsonl: str) -> list[Ev]:
    """CC 会话(主线 + subagents/)→ 事件流,全局时间序。"""
    seq = [0]
    sid8 = os.path.basename(main_jsonl)[:8]
    events = _collect_one(main_jsonl, "__main__:" + sid8, seq)
    sub = os.path.splitext(main_jsonl)[0] + "/subagents"
    if os.path.isdir(sub):
        for fn in sorted(glob.glob(os.path.join(sub, "*.jsonl"))):
            events += _collect_one(fn, os.path.splitext(os.path.basename(fn))[0], seq)
    events.sort(key=lambda e: (e.ts, e.seq))
    return events


# ═══════════════ codex 侧 ═══════════════
#
# codex 的工具调用内嵌在 exec 的 JS 源码里,解码复用 codex adapter 的三件套
# (_extract_shell_calls / _extract_apply_patches / _patch_chunks),不重造。
# apply_patch 是 V4A 差量:Add File → 全文写;Update File 的每个 hunk →
# edit(old=ctx+del, new=ctx+add) —— 与 Edit 工具同一档(原生差量);
# Delete File → 全文写空(终态空,如实)。shell 命令与 CC 同一套 shellparse。


def _patch_events(patch: str, cwd: object, ts: str, who: str,
                  nxt: Any) -> list[Ev]:
    import re

    from migloop.adapters import codex

    header = re.compile(r"^\*\*\* (Add|Update|Delete) File:\s*(.+?)\s*$", re.M)
    matches = list(header.finditer(patch or ""))
    evs: list[Ev] = []
    for pos, match in enumerate(matches):
        body_end = matches[pos + 1].start() if pos + 1 < len(matches) else len(patch)
        body = patch[match.end():body_end]
        action, raw_path = match.group(1), match.group(2).strip()
        path = _norm(codex._resolve_path(raw_path, str(cwd) if cwd else None)
                     or raw_path, cwd)
        if action == "Add":
            content = "\n".join(line[1:] for line in codex._patch_body_lines(body)
                                if line.startswith("+"))
            evs.append(Ev(ts, nxt(), "wfull", path, who, content=content + "\n"))
        elif action == "Delete":
            evs.append(Ev(ts, nxt(), "wfull", path, who, content=""))
        else:
            for hunk in codex._patch_chunks(body):
                old_lines: list[str] = []
                new_lines: list[str] = []
                for kind, lines in hunk:
                    if kind in ("ctx", "del"):
                        old_lines += lines
                    if kind in ("ctx", "add"):
                        new_lines += lines
                if not old_lines:
                    # 无上下文的纯追加:锚不住,如实降级为内容未知
                    evs.append(Ev(ts, nxt(), "wopaque", path, who))
                    continue
                evs.append(Ev(ts, nxt(), "edit", path, who,
                              old="\n".join(old_lines), new="\n".join(new_lines)))
    return evs


def _codex_output_body(text: str) -> str | None:
    """exec 输出剥壳:'Script completed…Output:\\n<正文>'。失败/无正文 → None。"""
    if text.lstrip().startswith("Script failed"):
        return None
    idx = text.find("Output:\n")
    return text[idx + len("Output:\n"):].lstrip("\n") if idx >= 0 else text


def _collect_codex_one(path: str, who: str, seq: list[int]) -> list[Ev]:
    from migloop.adapters import codex

    evs: list[Ev] = []
    pend: dict[Any, tuple[str, str, Any]] = {}    # call_id -> (clean-cat 目标, ts, cwd)

    def nxt() -> int:
        seq[0] += 1
        return seq[0]

    cwd: Any = None
    with open(path, encoding="utf-8", errors="ignore") as stream:
        lines = stream.readlines()
    for line in lines:
        try:
            r = json.loads(line)
        except Exception:
            continue
        pl = r.get("payload") or {}
        if cwd is None and isinstance(pl, dict) and pl.get("cwd"):
            cwd = pl.get("cwd")
        ts = str(r.get("timestamp") or "")
        t = pl.get("type")
        if t in ("function_call", "custom_tool_call"):
            if pl.get("name") != "exec":
                continue
            raw_arg = pl.get("arguments") if pl.get("arguments") is not None else pl.get("input")
            if isinstance(raw_arg, str) and raw_arg.lstrip().startswith("{"):
                js = str(codex._decode_arguments(raw_arg).get("input") or raw_arg)
            else:
                js = str(raw_arg or "")
            shell_calls = codex._extract_shell_calls(js, str(cwd) if cwd else None)
            for sc in shell_calls:
                cmd = str(sc.get("command") or "")
                wdir = sc.get("workdir") or cwd
                io = parse_shell(cmd)
                if len(io.writes) == 1 and len(io.scripts) == 1 and ">" in cmd:
                    evs.append(Ev(ts, nxt(), "wfull", _norm(io.writes[0], wdir),
                                  who, content=next(iter(io.scripts.values()))))
                else:
                    for w in io.writes:
                        evs.append(Ev(ts, nxt(), "wopaque", _norm(w, wdir), who))
                for rp in io.content_reads:
                    sp = io.spans.get(rp)
                    evs.append(Ev(ts, nxt(), "read", _norm(rp, wdir), who,
                                  start=sp[0] if sp else None,
                                  n=sp[1] if sp else None))
                for dp in io.dep_reads:
                    evs.append(Ev(ts, nxt(), "read", _norm(dp, wdir), who, dep=True))
            for patch in codex._extract_apply_patches(js):
                evs += _patch_events(patch, cwd, ts, who, nxt)
            if len(shell_calls) == 1:
                tgt = _clean_single_cat(str(shell_calls[0].get("command") or ""))
                if tgt:
                    pend[pl.get("call_id")] = (
                        tgt, ts, shell_calls[0].get("workdir") or cwd)
        elif t in ("function_call_output", "custom_tool_call_output"):
            hit = pend.pop(pl.get("call_id"), None)
            if hit is None:
                continue
            tgt, _uts, ucwd = hit
            body = _codex_output_body(codex._content_text(pl.get("output")))
            if body and body.strip() and not body.lower().startswith(_ERRISH):
                evs.append(Ev(ts, nxt(), "read", _norm(tgt, ucwd), who,
                              content=body, full=True))
    return evs


def collect_events_codex(root_jsonl: str, sessions_root: str | None = None) -> list[Ev]:
    """codex 会话(主 rollout + 子代理 rollout 树)→ 事件流,全局时间序。"""
    from migloop.adapters import codex

    seq = [0]
    tree = codex.discover_rollout_tree(root_jsonl, sessions_root)
    events: list[Ev] = []
    for i, item in enumerate(tree):
        rid = str((item.get("meta") or {}).get("id") or
                  os.path.basename(str(item.get("path"))))
        who = ("__main__:" + rid[:8]) if i == 0 else "agent-" + rid[:12]
        events += _collect_codex_one(str(item.get("path")), who, seq)
    events.sort(key=lambda e: (e.ts, e.seq))
    return events
