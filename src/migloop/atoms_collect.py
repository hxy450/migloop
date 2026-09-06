"""CC 会话实录 → 两原子账本的动作流(atoms.AgentRec)。

与 filestory_collect 的差别就是 0723 普查钉出来的几条:
- 相对路径按「记录 cwd + 命令内 cd 链」解析;cd 到变量之后的相对路径解析不了就丢,不猜
- 工具调用先等结果:is_error 的不落账、不占版本号
- 脚本落盘/脚本读:heredoc 体、会话内落盘的脚本体、python -c 里的文件字面量(via=script)
- rm / git rm / Remove-Item → 删除版本;git checkout/restore <path> → 内容未知的写
- Grep 工具 content 模式的命中行 → 带行段的读
- Agent 派发 / SendMessage 是效应;收件箱从自己实录里的 teammate-message 读

agent 身份:主线 = ``__main__:<sid8>``,子代理 = 其 transcript 文件 stem(自带会话 hash)。
"""

from __future__ import annotations

import glob
import json
import os
import posixpath
import re
from dataclasses import dataclass
from typing import Any

from migloop.atoms import Action, AgentRec, FileRef
from migloop.filestory import Ev
from migloop.filestory_collect import _clean_single_cat
from migloop.shellparse import (
    _PREFIX_SKIP,
    _VAR_ASSIGN,
    _path_of,
    _split_segments,
    _strip_heredocs,
    _tokenize,
    parse_shell,
)

_EXT = r"(?:md|ets|ts|js|mjs|json5?|py|sh|txt|ya?ml|xml|csv|html|properties|gradle|kts|java|kt)"
_LIT = re.compile(r"""['"]([^'"\n{}$*?<>|]{2,240}\.""" + _EXT + r""")['"]""")
_WRITEISH = re.compile(r"write_text|write_bytes|open\([^)]*['\"][wa]|\.write\(|json\.dump\(|"
                       r"shutil\.(?:copy|move)|writelines|writeFile|Set-Content|Out-File|"
                       r"os\.rename|\.rename\(|os\.remove|unlink\(", re.I)
_READISH = re.compile(r"read_text|\.read\(\)|json\.load\(|readlines|open\(|readFile|"
                      r"Get-Content|glob\(", re.I)
_TEAM = re.compile(r'^\s*<teammate-message\s+teammate_id="([^"]*)"(?:\s+summary="([^"]*)")?[^>]*>\n?',
                   re.S)
_SCRIPT_RUN = re.compile(r"\.(?:py|js|mjs|sh)$")
_PATHLINE = re.compile(r"^(.+?):(\d+)[:-]")
_LINEONLY = re.compile(r"^(\d+)[:-]")
_ERRISH = ("no such file", "cat:")
_PY = {"python", "python3", "py"}
_RUNNERS = _PY | {"node", "bash", "sh", "zsh"}


@dataclass
class FileOp:
    op: str                        # read | write | delete | edit
    path: str
    via: str = "shell"
    content: str | None = None     # write 全文 / read 快照
    full: bool = False
    start: int | None = None
    n: int | None = None
    dep: bool = False
    old: str | None = None
    new: str | None = None
    replace_all: bool = False
    seen: tuple[tuple[int, str], ...] | None = None


# ═══════════════ 路径 ═══════════════

def _norm_abs(p: str) -> str:
    q = p.replace("\\", "/")
    if len(q) > 1 and q[1] == ":":
        return q[:2] + posixpath.normpath(q[2:] or "/")
    return posixpath.normpath(q)


_BAD_PATH_CHARS = frozenset(" \t\n;|\"'<>=")


def _resolve(p: object, base: str | None) -> str | None:
    # 带空白/引号/分隔符的 token 是分词失衡的残渣,不是路径 —— 宁可漏
    if not isinstance(p, str) or not p or any(c in _BAD_PATH_CHARS for c in p):
        return None
    q = p.replace("\\", "/")
    if q.startswith("/") or (len(q) > 1 and q[1] == ":"):
        return _norm_abs(q)
    if base is None:
        return None
    return _norm_abs(base.rstrip("/") + "/" + q)


# ═══════════════ 脚本字面量 ═══════════════

def _literal_ops(code: str, base: str | None) -> list[FileOp]:
    """脚本正文里的文件字面量 → 读/写。按紧邻的调用形态判方向;判不出的按
    全文倾向(只写/只读)兜底,都有则放弃 —— 宁可漏。"""
    body_w, body_r = bool(_WRITEISH.search(code)), bool(_READISH.search(code))
    ops: list[FileOp] = []
    for m in _LIT.finditer(code):
        after = code[m.end():m.end() + 40]
        before = code[max(0, m.start() - 40):m.start()]
        if re.match(r"\s*,\s*['\"][wa]", after) or re.match(r"\s*\)\s*\.write", after):
            op = "write"
        elif re.match(r"\s*\)\s*\.(?:read|open|exists|is_file|iterdir|glob)", after) \
                or re.search(r"(?:json\.load|read_text|readFile|Get-Content)\s*\(?\s*(?:open\()?$",
                             before) \
                or (re.search(r"open\(\s*$", before) and re.match(r"\s*\)", after)):
            op = "read"
        elif body_w and not body_r:
            op = "write"
        elif body_r and not body_w:
            op = "read"
        else:
            continue
        p = _resolve(m.group(1), base)
        if p:
            ops.append(FileOp(op, p, "script"))
    return ops


def _head_word(words: list[str]) -> tuple[str, list[str]]:
    ws = list(words)
    while ws and (_VAR_ASSIGN.match(ws[0]) or ws[0].lower() in _PREFIX_SKIP):
        ws.pop(0)
    if not ws:
        return "", []
    head = ws[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    return (head[:-4] if head.endswith(".exe") else head), ws[1:]


def _shell_analyze(cmd: str, cwd: object, scripts: dict[str, str]) -> tuple[list[FileOp], bool]:
    """一条 shell 命令 → 文件读写 + 「有写能力但目标不全可知」标记。"""
    ops: list[FileOp] = []
    capable = False
    text, bodies = _strip_heredocs((cmd or "").replace("\\\n", " "))
    whole = parse_shell(cmd or "")
    base = _resolve(cwd, None) if isinstance(cwd, str) and cwd else None
    hd_target = (_resolve(whole.writes[0], base)
                 if len(whole.writes) == 1 and len(whole.scripts) == 1 and ">" in (cmd or "")
                 else None)

    def add(op: str, raw: str, via: str = "shell", **kw: Any) -> None:
        p = _resolve(raw, base)
        if p:
            ops.append(FileOp(op, p, via, **kw))

    for seg in _split_segments(text):
        words = [t[0] for t in _tokenize(seg) if t[2] == ""]
        head, args = _head_word(words)
        if not head:
            continue
        if head in ("cd", "pushd", "set-location", "push-location"):
            tgt = next((w for w in args if not w.startswith("-")), None)
            base = None if (tgt is None or "$" in tgt or tgt == "-") else _resolve(tgt, base)
            continue
        io = parse_shell(seg)
        for p in io.writes:
            add("write", p)
        for p in io.content_reads:
            sp = io.spans.get(p)
            add("read", p, start=sp[0] if sp else None, n=sp[1] if sp else None)
        for p in io.dep_reads:
            add("read", p, dep=True)
        pathish = [q for w in args if (q := _path_of(w))]
        if head in ("rm", "remove-item") or (head == "git" and args[:1] == ["rm"]):
            for p in pathish:
                add("delete", p)
        elif head == "git" and args[:1] in (["checkout"], ["restore"]):
            for p in pathish:
                add("write", p)
        elif head in ("mv", "move-item", "move"):
            for p in io.dep_reads:
                add("delete", p)
        if head in _PY and "-c" in args and args.index("-c") + 1 < len(args):
            code = args[args.index("-c") + 1]
            ops += _literal_ops(code, base)
            capable = capable or bool(_WRITEISH.search(code))
        if head in _RUNNERS:
            run = next((w for w in args if _SCRIPT_RUN.search(w) and not w.startswith("-")), None)
            if run:
                body = scripts.get(os.path.basename(run)) or scripts.get(_resolve(run, base) or "")
                if body is None:
                    capable = True                # 会话外脚本:目标不可知
                else:
                    ops += _literal_ops(body, base)
                    capable = capable or bool(_WRITEISH.search(body))
    for body in bodies:
        if hd_target is not None:
            for op in ops:
                if op.op == "write" and op.path == hd_target:
                    op.content, op.via = body, "shell"
            continue
        ops += _literal_ops(body, base)
        capable = capable or bool(_WRITEISH.search(body))
    return ops, capable


def shell_file_ops(cmd: str, cwd: object, scripts: dict[str, str]) -> list[FileOp]:
    return _shell_analyze(cmd, cwd, scripts)[0]


# ═══════════════ 工具 → 动作 ═══════════════

def _text_of(raw: object) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "\n".join(str(x.get("text", "")) for x in raw if isinstance(x, dict))
    return ""


_HITLINE = re.compile(r"^(?:(?P<p>[^:\n]+?):)?(?P<ln>\d+)[:-](?P<t>.*)$")


def _grep_ops(inp: dict[str, Any], out: str, cwd: object) -> list[FileOp]:
    root = _resolve(inp.get("path"), _resolve(cwd, None)) if inp.get("path") else _resolve(cwd, None)
    single = root if root and re.search(r"\.\w{1,6}$", root) else None
    base = root if single is None else posixpath.dirname(single)
    hits: dict[str, list[tuple[int, str]]] = {}
    for line in out.splitlines():
        if single is not None and (m1 := _LINEONLY.match(line)):
            hits.setdefault(single, []).append((int(m1.group(1)), line[m1.end():]))
            continue
        m = _HITLINE.match(line)
        if not m or not m.group("p"):
            continue
        p = _resolve(m.group("p"), base)
        if p:
            hits.setdefault(p, []).append((int(m.group("ln")), m.group("t")))
    ops: list[FileOp] = []
    for p, raw_pairs in hits.items():
        pairs = sorted({num: t for num, t in raw_pairs}.items())
        run: list[tuple[int, str]] = []
        for num, t in pairs:
            if run and num != run[-1][0] + 1:
                ops.append(FileOp("read", p, "tool", start=run[0][0], n=len(run), seen=tuple(run)))
                run = []
            run.append((num, t))
        if run:
            ops.append(FileOp("read", p, "tool", start=run[0][0], n=len(run), seen=tuple(run)))
    return ops


def _attach_stdout(cmd: str, text: str, out: str, ops: list[FileOp]) -> None:
    """把 shell 读的 stdout 对账到读记录上:grep -n 的命中行 / head 前缀。
    只在能唯一归属时才认(单一内容读目标),对不上就不动 —— 宁可漏。"""
    reads = [o for o in ops if o.op == "read" and not o.dep and o.content is None]
    if len(reads) != 1 or not out.strip() or out.lower().startswith(_ERRISH):
        return
    target = reads[0]
    segs = [_head_word([t[0] for t in _tokenize(s) if t[2] == ""]) for s in _split_segments(text)]
    grep_n = any(h in ("grep", "rg", "egrep", "fgrep") and any(a.startswith("-") and "n" in a for a in args)
                 for h, args in segs)
    if grep_n:
        pairs = []
        for ln in out.splitlines():
            m = _HITLINE.match(ln)
            if m and (not m.group("p") or target.path.endswith(m.group("p").replace("\\", "/").lstrip("./"))):
                pairs.append((int(m.group("ln")), m.group("t")))
        if pairs:
            target.seen = tuple(pairs)
        return
    head_n = next((int(a[1:]) if a[1:].isdigit() else None
                   for h, args in segs if h == "head" for a in args if a.startswith("-")), None)
    if head_n is None and target.start == 1 and target.n:
        head_n = target.n                        # head -N <path> / Get-Content -TotalCount N
    if head_n:
        lines = out.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if 0 < len(lines) <= head_n:
            target.start, target.n = 1, len(lines)
            target.seen = tuple((i + 1, t) for i, t in enumerate(lines))


def _basic_detail(name: str, inp: dict[str, Any]) -> dict[str, Any]:
    """成败都要留的调用摘要 —— 调查 agent 定"grep 到过没 / 构建跑了什么"靠它。"""
    if name in ("Bash", "PowerShell"):
        return {"cmd": " ".join(str(inp.get("command") or "").split())[:200]}
    if name in ("Grep", "Glob"):
        return {"pattern": inp.get("pattern"), "path": inp.get("path")}
    if name == "WebFetch":
        return {"url": inp.get("url")}
    if name == "Read":
        return {"path": inp.get("file_path")}
    return {}


def _file_ops(name: str, inp: dict[str, Any], out: str, tur: Any, cwd: object,
              scripts: dict[str, str]) -> tuple[list[FileOp], dict[str, Any]]:
    """成功的调用 → 文件读写 + 附加细节。"""
    detail: dict[str, Any] = _basic_detail(name, inp)
    ops: list[FileOp] = []
    if name == "Read":
        f = tur.get("file") if isinstance(tur, dict) else None
        if isinstance(f, dict) and isinstance(f.get("content"), str) and f.get("numLines"):
            p = _resolve(f.get("filePath"), _resolve(cwd, None))
            if p:
                full = (f.get("startLine") or 1) == 1 and f.get("numLines") == f.get("totalLines")
                ops.append(FileOp("read", p, "tool", content=f["content"], full=bool(full),
                                  start=f.get("startLine") or 1, n=f["numLines"]))
        elif isinstance(tur, dict):
            detail["result_type"] = tur.get("type")
    elif name == "Write":
        p = _resolve(inp.get("file_path"), _resolve(cwd, None))
        if p:
            content = str(inp.get("content") or "")
            ops.append(FileOp("write", p, "tool", content=content))
            if _SCRIPT_RUN.search(p):
                scripts[os.path.basename(p)] = content
                scripts[p] = content
    elif name in ("Edit", "MultiEdit"):
        p = _resolve(inp.get("file_path"), _resolve(cwd, None))
        edits = inp.get("edits") if name == "MultiEdit" else [inp]
        for e in edits or []:
            if p and isinstance(e, dict):
                ops.append(FileOp("edit", p, "tool", old=str(e.get("old_string") or ""),
                                  new=str(e.get("new_string") or ""),
                                  replace_all=bool(e.get("replace_all"))))
    elif name == "NotebookEdit":
        p = _resolve(inp.get("notebook_path"), _resolve(cwd, None))
        if p:
            ops.append(FileOp("write", p, "tool"))
    elif name in ("Bash", "PowerShell"):
        cmd = str(inp.get("command") or "")
        ops, capable = _shell_analyze(cmd, cwd, scripts)
        if capable:
            detail["write_capable"] = True
        tgt = _clean_single_cat(cmd)
        if tgt and out.strip() and not out.lower().startswith(_ERRISH):
            p = _resolve(tgt, _resolve(cwd, None))
            if p:
                ops.append(FileOp("read", p, "shell", content=out, full=True))
        else:
            _attach_stdout(cmd, _strip_heredocs(cmd.replace("\\\n", " "))[0], out, ops)
    elif name == "Grep":
        mode = str(inp.get("output_mode") or "files_with_matches")
        detail["mode"] = mode
        if mode == "content":
            ops = _grep_ops(inp, out, cwd)
    elif name in ("Agent", "Task"):
        detail.update({"name": inp.get("name"), "subagent_type": inp.get("subagent_type"),
                       "description": inp.get("description"), "model": inp.get("model"),
                       "prompt": inp.get("prompt")})
    elif name == "SendMessage":
        detail.update({"to": inp.get("to") or inp.get("recipient"),
                       "summary": inp.get("summary"),
                       "text": inp.get("message") or inp.get("content")})
    elif name == "Skill":
        detail["skill"] = inp.get("skill")
    return ops, detail


def _kind_of(name: str, ops: list[FileOp]) -> str:
    if name in ("Agent", "Task"):
        return "dispatch"
    if name == "SendMessage":
        return "message"
    if name == "Skill":
        return "skill"
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return "write"                        # 失败的写也是写的企图,只是不占版本号
    if any(o.op in ("write", "edit", "delete") for o in ops):
        return "write" if any(o.op != "delete" for o in ops) else "delete"
    if any(o.op == "read" for o in ops):
        return "read"
    return "other"


def _to_ev(op: FileOp, agent: str, ts: str, seq: int) -> Ev:
    kind = {"read": "read", "delete": "delete", "edit": "edit",
            "write": "wfull" if op.content is not None else "wopaque"}[op.op]
    return Ev(ts, seq, kind, op.path, agent, content=op.content, old=op.old, new=op.new,
              replace_all=op.replace_all, start=op.start, n=op.n, full=op.full, dep=op.dep,
              via=op.via, seen=op.seen)


def _walk(path: str, agent_id: str, session: str, seq: list[int],
          scripts: dict[str, str]) -> AgentRec:
    rec = AgentRec(id=agent_id, session=session)
    pend: dict[str, tuple[str, str, Any, Any, int]] = {}   # id -> (ts, name, inp, cwd, 行号)

    def nxt() -> int:
        seq[0] += 1
        return seq[0]

    last_text: str | None = None
    with open(path, encoding="utf-8", errors="ignore") as stream:
        for line_no, line in enumerate(stream):
            try:
                r = json.loads(line)
            except Exception:
                continue
            ts = str(r.get("timestamp") or "")
            cwd = r.get("cwd")
            if r.get("isCompactSummary"):
                rec.actions.append(Action(ts, nxt(), "compact", "compact"))
            m = r.get("message")
            if not isinstance(m, dict):
                continue
            content = m.get("content")
            blocks = content if isinstance(content, list) else \
                [{"type": "text", "text": content}] if isinstance(content, str) else []
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and m.get("role") == "user":
                    raw = str(b.get("text") or "")
                    tm = _TEAM.match(raw)
                    is_sub = not agent_id.startswith("__main__")
                    if tm or (is_sub and rec.prompt is None and raw.strip()
                              and not raw.lstrip().startswith("<")):
                        # teammate-message 是收件;子代理没包装的首条文本就是派发词本身
                        text = raw[tm.end():] if tm else raw
                        text = re.sub(r"\s*</teammate-message>\s*$", "", text)
                        rec.actions.append(Action(ts, nxt(), "inbox", "inbox", detail={
                            "from": tm.group(1) if tm else "dispatcher",
                            "summary": tm.group(2) if tm else None, "text": text}))
                        if rec.prompt is None and is_sub:
                            rec.prompt = text
                elif b.get("type") == "text" and m.get("role") == "assistant":
                    if str(b.get("text") or "").strip():
                        last_text = str(b["text"]).strip()
                elif b.get("type") == "tool_use":
                    pend[str(b.get("id"))] = (ts, str(b.get("name")), b.get("input") or {}, cwd, line_no)
                elif b.get("type") == "tool_result" and str(b.get("tool_use_id")) in pend:
                    tuid = str(b.get("tool_use_id"))
                    uts, name, inp, ucwd, use_line = pend.pop(tuid)
                    ok = not b.get("is_error", False)
                    ops: list[FileOp] = []
                    detail: dict[str, Any] = _basic_detail(name, inp)
                    if ok:
                        ops, detail = _file_ops(name, inp, _text_of(b.get("content")),
                                                r.get("toolUseResult"), ucwd, scripts)
                    act = Action(uts, nxt(), name, _kind_of(name, ops), ok=ok, detail=detail,
                                 src=(path, use_line, line_no), tuid=tuid)
                    for op in ops:
                        # 写在调用时刻发生,读的内容在结果时刻进上下文
                        ev = _to_ev(op, agent_id, ts if op.op == "read" else uts, nxt())
                        act.files.append(FileRef("read" if op.op == "read" else
                                                 "delete" if op.op == "delete" else "write",
                                                 op.path, ev))
                    rec.actions.append(act)
    for uts, name, _inp, _cwd, _line in pend.values():
        rec.actions.append(Action(uts, nxt(), name, "other", ok=None))
    rec.result = last_text
    return rec


def collect_cc(main_jsonl: str, seq: list[int]) -> dict[str, AgentRec]:
    """CC 会话(主线 + subagents/)→ {agent_id: AgentRec}。seq 跨会话共用,保证全局可排序。"""
    sid8 = os.path.basename(main_jsonl)[:8]
    scripts: dict[str, str] = {}
    main_id = f"__main__:{sid8}"
    agents = {main_id: _walk(main_jsonl, main_id, sid8, seq, scripts)}
    sub = os.path.splitext(main_jsonl)[0] + "/subagents"
    if os.path.isdir(sub):
        for fn in sorted(glob.glob(os.path.join(sub, "*.jsonl"))):
            stem = os.path.splitext(os.path.basename(fn))[0]
            agents[stem] = _walk(fn, stem, sid8, seq, scripts)
    return agents


def agents_from_events(events: list[Ev], session: str) -> dict[str, AgentRec]:
    """只有事件流(codex 收集器)时的兜底:每条事件一个动作,没有派发/收件箱。"""
    agents: dict[str, AgentRec] = {}
    for e in events:
        a = agents.setdefault(e.agent, AgentRec(id=e.agent, session=session))
        op = "read" if e.kind == "read" else "delete" if e.kind == "delete" else "write"
        a.actions.append(Action(e.ts, e.seq, "event", op, files=[FileRef(op, e.path, e)]))
    return agents
