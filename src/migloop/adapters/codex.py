# -*- coding: utf-8 -*-
"""Codex rollout JSONL -> MigLoop's normalized trace schema.

The viewer deliberately consumes one provider-neutral trace.  This module is
therefore an input adapter, not a second visualization pipeline.  It keeps the
Claude Code extractor unchanged and translates Codex records (`session_meta`,
`response_item`, `event_msg`) into the same meta/stage/tool/agent/lineage
objects returned by :mod:`extract_session`.
"""
from __future__ import annotations

import copy
import difflib
import glob
import json
import os
import re
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from .. import shellparse

from . import claude as common
from .base import SessionCandidate


FORMAT = "codex"
SUPPORTS_LIVE = False


def default_root() -> str:
    return os.path.join(os.path.expanduser("~"), ".codex", "sessions")


_JSON_STRING = r'"(?:\\.|[^"\\])*"'
_PIPELINE_SKILLS = set(common.PIPELINE_SKILLS)
# Codex conversion skills read the run/build wrappers while bootstrapping.
# They are orchestration helpers, not migration work phases.  The concrete
# phase skills below are the stable stage boundaries users expect to see.
_CODEX_STAGE_SKILLS = {
    "mig-arch", "a2h-arch-scaffold", "a2h-spec", "a2h-plan",
    "a2h-execute", "a2h-verify", "a2h-retrospect",
    # dynamic workflow 的 verify 轮:visual verify 会话整场读它开工 ——
    # 不成阶段的话 fixer 拿不到 verify 语义,正式口径(verify 阶段=fix)落空
    "arkts-visual-verify",
}


def _first_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return None


def is_codex_session(path: str) -> bool:
    record = _first_json(path) or {}
    return record.get("type") == "session_meta" and isinstance(record.get("payload"), dict)


is_session = is_codex_session


def iter_sessions(root: str | None) -> Iterator[SessionCandidate]:
    if not root or not os.path.isdir(root):
        return
    for path in glob.iglob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        summary = session_summary(path)
        if not summary or summary.get("thread_source") == "subagent":
            continue
        try:
            stat = os.stat(path)
        except OSError:
            continue
        project = os.path.basename((summary.get("cwd") or "codex-session").rstrip("\\/"))
        yield SessionCandidate(
            mtime=stat.st_mtime,
            path=path,
            project=project,
            size=stat.st_size,
            format=FORMAT,
            session_id=summary.get("id") or summary.get("session_id") or "",
        )


def session_summary(path: str) -> dict[str, Any] | None:
    """Cheap first-record metadata used by the CLI session index."""
    record = _first_json(path) or {}
    payload = record.get("payload") or {}
    if record.get("type") != "session_meta":
        return None
    return {
        "id": payload.get("id") or payload.get("session_id"),
        "session_id": payload.get("session_id") or payload.get("id"),
        "cwd": payload.get("cwd"),
        "thread_source": payload.get("thread_source"),
        "source": payload.get("source"),
        "cli_version": payload.get("cli_version"),
    }


def _sessions_root(path: str) -> str:
    cur = os.path.abspath(os.path.dirname(path))
    while True:
        if os.path.basename(cur).lower() == "sessions" and os.path.basename(os.path.dirname(cur)).lower() == ".codex":
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.dirname(os.path.abspath(path))


def discover_rollout_tree(path: str, sessions_root: str | None = None) -> list[dict[str, Any]]:
    """Return the root rollout plus every descendant rollout.

    Codex stores each subagent in a separate date-partitioned file.  Children
    share the root ``session_id`` and carry an explicit
    ``source.subagent.thread_spawn.parent_thread_id`` edge.  We use both facts:
    session_id makes discovery fast and the parent edge prevents unrelated
    SDK rollouts from being attached accidentally.
    """
    path = os.path.abspath(path)
    root_meta = session_summary(path)
    if not root_meta:
        raise ValueError("not a Codex rollout JSONL: %s" % path)
    root_id = root_meta.get("id") or root_meta.get("session_id")
    root_session = root_meta.get("session_id") or root_id
    scan_root = sessions_root or _sessions_root(path)
    candidates: dict[Any, dict[str, Any]] = {}
    pattern = os.path.join(scan_root, "**", "*.jsonl")
    for candidate in glob.iglob(pattern, recursive=True):
        summary = session_summary(candidate)
        if not summary:
            continue
        source = summary.get("source") or {}
        spawn = ((source.get("subagent") or {}).get("thread_spawn") or {}) if isinstance(source, dict) else {}
        candidates[summary.get("id")] = {
            "path": os.path.abspath(candidate),
            "meta": summary,
            "parent": spawn.get("parent_thread_id"),
            "agent_path": spawn.get("agent_path"),
            "nickname": spawn.get("agent_nickname"),
            "agent_role": spawn.get("agent_role"),
            "depth": spawn.get("depth"),
        }
    if root_id not in candidates:
        candidates[root_id] = {"path": path, "meta": root_meta, "parent": None,
                               "agent_path": None, "nickname": None, "depth": 0}

    selected = {root_id}
    changed = True
    while changed:
        changed = False
        for thread_id, item in candidates.items():
            if thread_id in selected:
                continue
            same_session = item["meta"].get("session_id") == root_session
            if item.get("parent") in selected and same_session:
                selected.add(thread_id)
                changed = True
    rows = [candidates[x] for x in selected if x in candidates]
    rows.sort(key=lambda item: (0 if item["meta"].get("id") == root_id else 1,
                                item.get("depth") or 0, item["path"]))
    return rows


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                value = item.get("text")
                if isinstance(value, str):
                    chunks.append(value)
        return "\n".join(chunks)
    if isinstance(content, dict):
        for key in ("text", "output", "content", "message"):
            if key in content:
                text = _content_text(content[key])
                if text:
                    return text
    return ""


def _decode_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {"input": result}
    except (json.JSONDecodeError, TypeError):
        return {"input": value}


def _decode_js_string(token: str) -> Any:
    try:
        return json.loads(token)
    except (json.JSONDecodeError, TypeError):
        return ""


def _js_field(segment: str | None, key: str) -> Any:
    pattern = re.compile(r'(?:"?%s"?)\s*:\s*(%s)' % (re.escape(key), _JSON_STRING), re.DOTALL)
    match = pattern.search(segment or "")
    return _decode_js_string(match.group(1)) if match else None


def _nested_segments(source: str | None, tool_name: str) -> Iterator[str]:
    text = source or ""
    hits = list(re.finditer(r"\btools\.%s\s*\(" % re.escape(tool_name), text))
    for pos, hit in enumerate(hits):
        end = hits[pos + 1].start() if pos + 1 < len(hits) else len(text)
        yield text[hit.start():end]


def _extract_shell_calls(source: str | None, default_cwd: str | None) -> list[dict[str, Any]]:
    # CLI 0.147+ 把 shell_command 换成 exec_command、参数 command 换成 cmd;
    # 两代形态都要认 —— 漏认的后果是读侧血缘整体为零(AIPPT 实测)。
    calls: list[dict[str, Any]] = []
    for tool_name, field in (("shell_command", "command"), ("exec_command", "cmd")):
        for segment in _nested_segments(source, tool_name):
            command = _js_field(segment, field) or _js_field(segment, "command")
            if not command:
                continue
            calls.append({"command": command,
                          "workdir": _js_field(segment, "workdir") or default_cwd})
    return calls


def _extract_apply_patches(source: str | None) -> list[str]:
    variables: dict[str, Any] = {}
    var_re = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(%s)\s*;" % _JSON_STRING,
                        re.DOTALL)
    for match in var_re.finditer(source or ""):
        variables[match.group(1)] = _decode_js_string(match.group(2))
    patches: list[str] = []
    call_re = re.compile(r"\btools\.apply_patch\s*\(\s*(%s|[A-Za-z_$][\w$]*)\s*\)" % _JSON_STRING,
                         re.DOTALL)
    for match in call_re.finditer(source or ""):
        arg = match.group(1)
        patch = _decode_js_string(arg) if arg.startswith('"') else variables.get(arg)
        if patch and "*** Begin Patch" in patch:
            patches.append(patch)
    return patches


def _skill_names(text: str | None) -> list[str]:
    pattern = re.compile(r"(?i)(?:\\+|/)+skills(?:\\+|/)+([a-z0-9_-]+)(?:\\+|/)+SKILL\.md")
    return list(dict.fromkeys(match.group(1) for match in pattern.finditer(text or "")))


def _tool_failed(output: str | None) -> bool:
    low = (output or "").lower()
    if "script failed" in low or '"iserror":true' in low.replace(" ", ""):
        return True
    match = re.search(r"exit code:\s*(-?\d+)", low)
    return bool(match and int(match.group(1)) != 0)


def _duration_ms(start_ts: str | None, end_ts: str | None, output: str | None) -> int | None:
    values = [float(x) for x in re.findall(r"Wall time\s+([0-9.]+)\s+seconds", output or "", re.I)]
    if values:
        return int(max(values) * 1000)
    return common.ms_between(start_ts, end_ts)


def _resolve_path(value: str | None, cwd: str | None) -> str | None:
    if not value or "$" in value or "%" in value or "*" in value or "?" in value:
        return None
    value = value.strip().strip("\"'").replace("\\", os.sep).replace("/", os.sep)
    path = value if os.path.isabs(value) else os.path.join(cwd or os.getcwd(), value)
    return os.path.abspath(path)


def _powershell_variables(command: str | None) -> dict[str, str]:
    values: dict[str, str] = {}
    pattern = re.compile(r"\$([A-Za-z_][\w]*)\s*=\s*(?:@?\()?\s*(['\"])(.*?)\2", re.DOTALL)
    for match in pattern.finditer(command or ""):
        values[match.group(1).lower()] = match.group(3)
    return values


def _explicit_get_content_paths(command: str | None, cwd: str | None) -> list[str]:
    variables = _powershell_variables(command)
    values: list[str] = []
    pattern = re.compile(
        r"(?i)\bGet-Content\b(?:(?![;|\r\n]).)*?(?:-(?:LiteralPath|Path)\s+)?"
        r"(?P<value>\$[A-Za-z_][\w]*|'[^']+'|\"[^\"]+\")"
    )
    for match in pattern.finditer(command or ""):
        raw: str | None = match.group("value")
        if raw and raw.startswith("$"):
            raw = variables.get(raw[1:].lower())
        elif raw:
            raw = raw[1:-1]
        path = _resolve_path(raw, cwd)
        if path and os.path.isfile(path) and path not in values:
            values.append(path)
    return values


#: 源文件读缓存 —— 视野推断对同一批源文件反复 open+read(326MB 会话实测
#: 3843 次 open 共 24s),按 (mtime,size) 缓存;文件在写自然失效。
_SRC_CACHE: dict[str, tuple[tuple[int, int], tuple[str, list[str]]]] = {}
_SRC_CACHE_MAX = 64


def _read_source_cached(path: str) -> tuple[str, list[str]] | None:
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return None
    hit = _SRC_CACHE.get(path)
    if hit is not None and hit[0] == key:
        return hit[1]
    try:
        with open(path, encoding="utf-8", errors="ignore") as stream:
            source = stream.read().replace("\r\n", "\n").replace("\r", "\n")
    except OSError:
        return None
    value = (source, source.splitlines())
    if len(_SRC_CACHE) >= _SRC_CACHE_MAX:
        _SRC_CACHE.pop(next(iter(_SRC_CACHE)))
    _SRC_CACHE[path] = (key, value)
    return value


def _visible_intervals(path: str, output: str | None) -> tuple[list[tuple[int, int]], int]:
    cached = _read_source_cached(path)
    if cached is None:
        return [], 0
    source, lines = cached
    shown = (output or "").replace("\r\n", "\n").replace("\r", "\n")
    if source and source.rstrip("\n") in shown:
        return [(1, len(lines))], len(lines)
    output_lines = shown.splitlines()
    hits: list[tuple[int, int]] = []
    matcher = difflib.SequenceMatcher(None, [x.rstrip() for x in lines],
                                      [x.rstrip() for x in output_lines], autojunk=False)
    for block in matcher.get_matching_blocks():
        if block.size < 2:
            continue
        if sum(len(x.strip()) for x in lines[block.a:block.a + block.size]) < 16:
            continue
        hits.append((block.a + 1, block.size))
    # A search may expose isolated but globally unique substantive lines.
    index: dict[str, list[int]] = {}
    for lineno, line in enumerate(lines, 1):
        key = line.strip()
        if len(key) >= 8:
            index.setdefault(key, []).append(lineno)
    for line in output_lines:
        locations = index.get(line.strip()) or []
        if len(locations) == 1:
            hits.append((locations[0], 1))
    return common._merge_line_intervals(hits), len(lines)


_SED_RANGE_RE = re.compile(r"\bsed\s+-n\s+'?(\d+),(\d+)p'?\s+\"?([^-\s;|&\"][^\s;|&\"]*)")
_CAT_READ_RE = re.compile(r"\b(?:cat|head|tail)\s+(?:-n\s*\d*\s+)?\"?([^-\s;|&\"][^\s;|&\"]*)")


def _offline_norm(path: str, cwd: str | None) -> str:
    # 相对路径(verify 轮 fixer 实测形态)以 workdir 归一;绝对路径原样
    p = path.replace("\\", "/")
    if not p.startswith("/") and ":" not in p.split("/")[0]:
        p = (cwd or "").replace("\\", "/").rstrip("/") + "/" + p
    return p


def _looks_like_path(token: str) -> bool:
    # 数字参数/引号残片不是路径:tail -n 1000 的 1000、裸引号等(实测污染图)
    t = token.strip("'")
    if not t or t.isdigit():
        return False
    return "/" in t or "." in t


def _strip_exec_wrapper(output: str | None) -> str:
    text = output or ""
    idx = text.find("Output:\n")
    if idx >= 0 and text[:idx].count("\n") <= 4:
        return text[idx + len("Output:\n"):].lstrip("\n")
    return text


def _offline_visible_events(
    command: str | None, output: str | None, cwd: str | None
) -> list[dict[str, Any]]:
    """离线导入的会话兜底:文件不在本机盘,磁盘比对必然为空 —— 用命令语义
    (sed 的范围是实录参数)+ 输出规模判定"内容进了上下文"。wc/重定向这类
    只有计数或无正文输出的不算。仅在磁盘比对拿不到结果时使用。"""
    body = _strip_exec_wrapper(output)
    if not body.strip():
        return []
    n_out = body.count("\n") + 1
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _SED_RANGE_RE.finditer(command or ""):
        start, end = int(match.group(1)), int(match.group(2))
        path = match.group(3)
        if path in seen or "$" in path or not _looks_like_path(path):
            continue
        seen.add(path)
        count = max(1, min(end - start + 1, n_out))
        events.append({"path": _offline_norm(path, cwd),
                       "intervals": [(start, count)], "via": "PowerShell"})
    for match in _CAT_READ_RE.finditer(command or ""):
        path = match.group(1)
        if path in seen or "$" in path or not _looks_like_path(path):
            continue
        seen.add(path)
        events.append({"path": _offline_norm(path, cwd),
                       "intervals": [(1, n_out)], "via": "PowerShell"})
    return events


def _generic_visible_events(
    command: str | None, output: str | None, cwd: str | None
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in _explicit_get_content_paths(command, cwd):
        intervals, _ = _visible_intervals(path, output)
        if intervals:
            events.append({"path": path.replace("\\", "/"),
                           "intervals": intervals, "via": "PowerShell"})
    return events


def _patch_body_lines(body: str) -> list[str]:
    lines = body.split("\n")
    if lines and lines[0] == "":
        lines = lines[1:]
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return [line for line in lines if not line.startswith("***")]


def _patch_chunks(body: str) -> list[list[tuple[str, list[str]]]]:
    """V4A Update 体 → 结构化 hunk 列表,每块 = [("ctx"|"del"|"add", [行])…]。
    ctx/del/add 分开是行级归属的关键:上下文行没被改,必须保留原作者,
    只有 add 行归编辑者(blame 的 "hunks" op 语义)。块按序作用。"""
    chunks: list[list[tuple[str, list[str]]]] = []
    runs: list[tuple[str, list[str]]] = []

    def push(kind: str, text: str) -> None:
        if runs and runs[-1][0] == kind:
            runs[-1][1].append(text)
        else:
            runs.append((kind, [text]))

    for line in _patch_body_lines(body):
        if line.startswith("@@"):
            if runs:
                chunks.append(runs)
            runs = []
            continue
        if line.startswith("-"):
            push("del", line[1:])
        elif line.startswith("+"):
            push("add", line[1:])
        else:
            push("ctx", line[1:] if line.startswith(" ") else line)
    if runs:
        chunks.append(runs)
    return chunks


def _patch_entries(patch: str, cwd: str | None) -> list[dict[str, Any]]:
    header = re.compile(r"^\*\*\* (Add|Update|Delete) File:\s*(.+?)\s*$", re.M)
    matches = list(header.finditer(patch or ""))
    rows: list[dict[str, Any]] = []
    for pos, match in enumerate(matches):
        body_end = matches[pos + 1].start() if pos + 1 < len(matches) else len(patch)
        body = patch[match.end():body_end]
        action, raw_path = match.group(1), match.group(2).strip()
        path = _resolve_path(raw_path, cwd) or raw_path
        added = sum(1 for line in body.splitlines()
                    if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in body.splitlines()
                      if line.startswith("-") and not line.startswith("---"))
        event: list[Any]
        if action == "Add":
            name, event = "Write", ["set", added]
        elif action == "Delete":
            name, event = "Edit", ["delta", -removed]
        else:
            name, event = "Edit", ["delta", added - removed]
        row: dict[str, Any] = {"name": name, "brief": path, "wlines": added,
               "wevent": event, "patch_action": action}
        if path.endswith(".ets"):
            if action == "Add":
                row["bevent"] = ("write", "\n".join(
                    line[1:] for line in _patch_body_lines(body)
                    if line.startswith("+")))
            elif action == "Delete":
                row["bevent"] = ("delete", None)
            else:
                row["bevent"] = ("hunks", _patch_chunks(body))
        rows.append(row)
    return rows


def _tool_entry(
    idx: int, ts: str | None, name: str, inp: Any, call_id: Any,
    output: str | None, output_ts: str | None, brief: str | None = None,
) -> dict[str, Any]:
    return {
        "idx": idx, "ts": ts, "name": name,
        "brief": brief if brief is not None else common.brief_tool_target(name, inp),
        "ok": not _tool_failed(output),
        "dur_ms": _duration_ms(ts, output_ts, output),
        "tuid": call_id, "result": (output or "").strip()[:220], "_inp": inp,
    }


def _normalize_one(
    call: dict[str, Any], outputs: dict[Any, dict[str, Any]], cwd: str | None
) -> list[dict[str, Any]]:
    """单条 call 的规整(原 _normalize_tools 循环体)。纯函数:结果只依赖
    (call, 它的 output, cwd) —— 增量解析按此粒度缓存昂贵的源码视野推断。"""
    rows: list[dict[str, Any]] = []
    result = outputs.get(call.get("call_id")) or {}
    output = result.get("text") or ""
    output_ts = result.get("ts")
    raw = call.get("raw") or ""
    if call.get("name") == "exec":
        extracted = False
        for shell in _extract_shell_calls(raw, cwd):
            extracted = True
            command = shell["command"]
            workdir = shell.get("workdir") or cwd
            entry = _tool_entry(call["idx"], call["ts"], "PowerShell",
                                {"command": command, "workdir": workdir},
                                call.get("call_id"), output, output_ts,
                                brief=" ".join(command.split())[:300])
            visible = common._infer_visible_source_lines(
                "PowerShell", {"command": command}, output, workdir
            )
            existing = {(event["path"], tuple(event["intervals"])) for event in visible}
            for event in _generic_visible_events(command, output, workdir):
                key = (event["path"], tuple(event["intervals"]))
                if key not in existing:
                    visible.append(event)
                    existing.add(key)
            if not visible:
                covered = {event["path"] for event in visible}
                for event in _offline_visible_events(command, output, workdir):
                    if event["path"] in covered or os.path.isfile(event["path"]):
                        continue  # 本机盘上存在的文件以磁盘比对为权威
                    visible.append(event)
            if visible:
                entry["_visible_source_lines"] = visible
            probed = common._script_probed_paths(
                "PowerShell", {"command": command}, workdir
            )
            if probed:
                entry["_probed_paths"] = probed
            skills = _skill_names(command)
            if skills:
                entry["skills"] = skills
            rows.append(entry)
        for patch in _extract_apply_patches(raw):
            extracted = True
            for patch_row in _patch_entries(patch, cwd):
                entry = _tool_entry(call["idx"], call["ts"], patch_row.pop("name"),
                                    {}, call.get("call_id"), output, output_ts,
                                    brief=patch_row.pop("brief"))
                entry.update(patch_row)
                rows.append(entry)
        if not extracted:
            rows.append(_tool_entry(call["idx"], call["ts"], "exec",
                                    {"input": raw}, call.get("call_id"), output, output_ts,
                                    brief=" ".join(raw.split())[:300]))
        return rows

    args = _decode_arguments(call.get("raw"))
    name = call.get("name") or "tool"
    display_name = "Agent" if name == "spawn_agent" else name
    entry = _tool_entry(call["idx"], call["ts"], display_name, args,
                        call.get("call_id"), output, output_ts)
    if name == "spawn_agent":
        entry["agent_type"] = args.get("task_name") or "codex-subagent"
        message = args.get("message") or ""
        entry["agent_desc"] = message[:240] if not message.startswith("gAAAA") else args.get("task_name", "")
        # 派发原话全文段:子代理条目的 prompt_excerpt 用(codex 子代理 rollout
        # 里没有 user_message,派发内容只存在于主线这条 spawn 调用上)
        if not message.startswith("gAAAA"):
            entry["agent_prompt"] = message[:800]
    rows.append(entry)
    return rows


def _normalize_tools(rollout: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for call in rollout["calls"]:
        rows.extend(_normalize_one(call, rollout["outputs"], rollout.get("cwd")))
    for seq, row in enumerate(sorted(rows, key=lambda x: (x["idx"], x.get("ts") or "", x["name"]))):
        row["seq"] = seq
    return rows


# ---- 子代理归约产物缓存(与 claude.py 的 _SUB_CACHE 同款) ----
# 收尾的子代理 rollout 不再变化,它对 trace 的全部贡献可以按 (mtime,size)
# 签名复用:一个 agent 条目 + 它那份计费 + 供孙代理找派发点的 Agent 工具行。
# 主 rollout 每次全解 —— 和 CC 的主 transcript 一样,它的工具明细要进 trace,
# 缓存不了小的;但它只有 1 份,不乘 N。
_CHILD_CACHE: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
_CHILD_CACHE_MAX = 2048
_FORK_MARKER = "You are an agent in a team of agents"


def _new_scan_state() -> dict[str, Any]:
    return {"line_idx": 0, "local_start": 0, "inherited": {}, "meta": {},
            "first": None, "last": None, "record_points": [], "calls": [],
            "outputs": {}, "prompts": [], "token_points": [], "markers": [],
            "model": None, "last_message": "", "first_message": "", "completed": False,
            "text_chars": 0, "tool_chars": 0, "record_count": 0,
            "norm": {}, "offset": 0, "sig": None, "head": None}


def _scan_record(s: dict[str, Any], idx: int, record: dict[str, Any]) -> None:
    """主循环体的状态机版:一条记录进,各累加器更新。与原实现逐分支等价。"""
    if idx < s["local_start"]:
        return
    s["record_count"] += 1
    ts = record.get("timestamp")
    if ts:
        s["first"] = min(s["first"], ts) if s["first"] else ts
        s["last"] = max(s["last"], ts) if s["last"] else ts
        s["record_points"].append((idx, ts))
    outer = record.get("type")
    payload = record.get("payload") or {}
    if outer == "session_meta":
        if not s["meta"]:
            s["meta"] = payload
        s["first"] = s["first"] or payload.get("timestamp")
    elif outer == "turn_context":
        s["model"] = payload.get("model") or s["model"]
    elif outer == "response_item":
        ptype = payload.get("type")
        if ptype in ("function_call", "custom_tool_call"):
            raw = payload.get("arguments") if ptype == "function_call" else payload.get("input")
            raw = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            s["calls"].append({"idx": idx, "ts": ts, "ptype": ptype,
                               "name": payload.get("name"), "call_id": payload.get("call_id"),
                               "raw": raw})
            s["tool_chars"] += len(raw or "")
        elif ptype in ("function_call_output", "custom_tool_call_output"):
            s["outputs"][payload.get("call_id")] = {"ts": ts, "text": _content_text(payload.get("output"))}
        elif ptype == "message" and payload.get("role") == "assistant":
            text = _content_text(payload.get("content"))
            if text.strip():
                if not s["first_message"]:
                    s["first_message"] = text.strip()[:800]
                s["last_message"] = text.strip()[:300]
                s["text_chars"] += len(text)
        elif ptype == "reasoning":
            summary = _content_text(payload.get("summary"))
            if summary:
                s["text_chars"] += len(summary)
    elif outer == "event_msg":
        ptype = payload.get("type")
        if ptype == "user_message":
            text = payload.get("message") or ""
            if text.strip():
                s["prompts"].append({"idx": idx, "ts": ts, "wait_ms": 0,
                                     "text": " ".join(text.split())[:400]})
        elif ptype == "agent_message" and payload.get("message"):
            s["last_message"] = str(payload.get("message"))[:300]
        elif ptype == "task_complete":
            s["completed"] = True
        elif ptype == "token_count" and isinstance(payload.get("info"), dict):
            info = payload["info"]
            total = dict(info.get("total_token_usage") or {})
            if s["inherited"]:
                for key, value in list(total.items()):
                    if isinstance(value, (int, float)):
                        total[key] = max(0, value - (s["inherited"].get(key) or 0))
            s["token_points"].append({"idx": idx, "ts": ts, "total": total,
                                      "last": info.get("last_token_usage") or {},
                                      "model": s["model"] or "codex"})
        elif ptype in ("context_compacted", "compaction"):
            s["markers"].append({"idx": idx, "ts": ts, "kind": "compact"})


def _split_complete_lines(data: bytes) -> tuple[list[bytes], int]:
    boundary = data.rfind(b"\n") + 1
    if boundary <= 0:
        return [], 0
    return data[:boundary].split(b"\n")[:-1], boundary


def _full_scan(path: str, tree_item: dict[str, Any] | None = None) -> dict[str, Any]:
    s = _new_scan_state()
    with open(path, "rb") as f:
        data = f.read()
    lines, boundary = _split_complete_lines(data)
    s["offset"] = boundary
    s["line_idx"] = len(lines)
    records: list[tuple[int, dict[str, Any]]] = []
    for idx, raw in enumerate(lines):
        try:
            records.append((idx, json.loads(raw)))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    # fork 子代理:先定 local_start(激活边界)与父的累计用量,再喂状态机
    if tree_item and tree_item.get("parent"):
        for idx, record in records:
            payload = record.get("payload") or {}
            if (record.get("type") == "response_item" and
                    payload.get("type") == "message" and
                    payload.get("role") == "developer" and
                    _FORK_MARKER in _content_text(payload.get("content"))):
                s["local_start"] = idx
        if s["local_start"]:
            for idx, record in records:
                if idx >= s["local_start"]:
                    break
                payload = record.get("payload") or {}
                if (record.get("type") == "event_msg" and
                        payload.get("type") == "token_count" and
                        isinstance(payload.get("info"), dict)):
                    s["inherited"] = dict(payload["info"].get("total_token_usage") or {})
    # meta 兜底:local_start 之前的 session_meta 也是身份来源(fork 首条)
    for idx, record in records:
        if record.get("type") == "session_meta":
            s["meta"] = s["meta"] or (record.get("payload") or {})
            break
    for idx, record in records:
        _scan_record(s, idx, record)
    return s


def _emit(s: dict[str, Any], path: str, tree_item: dict[str, Any] | None = None) -> dict[str, Any]:
    """从状态组装 rollout dict。normalize 按 call 增量:已推断且当时有 output
    的直接复用;output 新到或新 call 才跑昂贵路径。行 dict 浅拷贝出货 ——
    下游会回填 stage/seg,共享对象会污染缓存。"""
    outputs = s["outputs"]
    cwd = (s["meta"] or {}).get("cwd")
    all_rows: list[dict[str, Any]] = []
    for call in s["calls"]:
        key = call.get("call_id") or "i%d" % call["idx"]
        out = outputs.get(call.get("call_id"))
        slot = s["norm"].get(key)
        if slot is not None and (slot["had"] or not out):
            rows = slot["rows"]
        else:
            rows = _normalize_one(call, outputs, cwd)
            s["norm"][key] = {"rows": rows, "had": bool(out)}
        all_rows.extend(rows)
    tools = [dict(r) for r in sorted(all_rows, key=lambda x: (x["idx"], x.get("ts") or "", x["name"]))]
    for seq, row in enumerate(tools):
        row["seq"] = seq
    resolved_model = s["model"] or "codex"
    token_points = [dict(p) for p in s["token_points"]]
    for point in token_points:
        if point.get("model") == "codex":
            point["model"] = resolved_model
    meta_payload = s["meta"] or {}
    result = {
        "path": os.path.abspath(path), "meta": meta_payload,
        "id": meta_payload.get("id") or meta_payload.get("session_id"),
        "session_id": meta_payload.get("session_id") or meta_payload.get("id"),
        "cwd": meta_payload.get("cwd"), "model": resolved_model,
        "start_ts": s["first"] or meta_payload.get("timestamp"), "end_ts": s["last"],
        "record_count": s["record_count"], "record_points": s["record_points"],
        "calls": s["calls"], "outputs": outputs,
        "prompts": [dict(pp) for pp in s["prompts"]],
        "token_points": token_points,
        "markers": [dict(m) for m in s["markers"]],
        "completed": s["completed"], "result": s["last_message"],
        "first_message": s["first_message"],
        "text_chars": s["text_chars"], "tool_chars": s["tool_chars"],
    }
    if tree_item:
        result.update({"parent": tree_item.get("parent"),
                       "agent_path": tree_item.get("agent_path"),
                       "nickname": tree_item.get("nickname"),
                       "agent_role": tree_item.get("agent_role"),
                       "depth": tree_item.get("depth")})
    result["tools"] = tools
    return result


def _parse_rollout(path: str, tree_item: dict[str, Any] | None = None) -> dict[str, Any]:
    """解析一份 rollout。不缓存 —— 缓存发生在归约之后(见 _child_product)。"""
    return _emit(_full_scan(path, tree_item), path, tree_item)


#: 归约时还不知道自己属于哪个阶段(阶段由主线决定),命中后再回填。
_NO_STAGE: dict[str, Any] = {"stage": None, "id": None}


def _child_product(tree_item: dict[str, Any]) -> dict[str, Any]:
    """一份子代理 rollout 对 trace 的**全部**贡献,归约完再缓存。

    与 claude.py 的 _SUB_CACHE 同款:签名 = (mtime, size),文件冻结即永久命中。
    缓存的不是解析中间态而是成品 —— 原始 calls/outputs 没有任何下游消费者。
    阶段/派发点来自主线,可能每轮不同,和 CC 一样在命中后回填。
    """
    path = tree_item["path"]
    try:
        st = os.stat(path)
        sig: tuple[int, int] | None = (st.st_mtime_ns, st.st_size)
    except OSError:
        sig = None
    if sig is not None:
        hit = _CHILD_CACHE.get(path)
        if hit is not None and hit[0] == sig:
            return copy.deepcopy(hit[1])

    rollout = _parse_rollout(path, tree_item)
    entry = _agent_entry(rollout, _NO_STAGE, None)
    product = {
        "id": rollout["id"],
        "parent": rollout.get("parent"),
        "depth": rollout.get("depth"),
        "agent_path": rollout.get("agent_path"),
        "start_ts": rollout["start_ts"],
        "record_count": rollout["record_count"],
        "entry": entry,
        "billing": [(row.get("model"), row["delta"])
                    for row in _usage_deltas(rollout["token_points"])],
        # 孙代理要靠父的 Agent 工具行找自己的派发点,只留这一小撮
        "agent_tools": [{"name": tool["name"], "brief": tool.get("brief"),
                         "tuid": tool.get("tuid"), "agent_prompt": tool.get("agent_prompt")}
                        for tool in rollout["tools"] if tool["name"] == "Agent"],
        "prompt_fallback": entry.get("_prompt") or "",
    }
    if sig is not None:
        if path not in _CHILD_CACHE and len(_CHILD_CACHE) >= _CHILD_CACHE_MAX:
            _CHILD_CACHE.pop(next(iter(_CHILD_CACHE)))
        _CHILD_CACHE[path] = (sig, copy.deepcopy(product))
    return product


def _usage_deltas(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous = {"input_tokens": 0, "cached_input_tokens": 0,
                "output_tokens": 0, "reasoning_output_tokens": 0}
    rows: list[dict[str, Any]] = []
    for point in points:
        current = point.get("total") or {}
        delta: dict[str, int] = {}
        changed = False
        for key in previous:
            value = int(current.get(key) or 0)
            old = previous[key]
            amount = value - old if value >= old else value
            delta[key] = max(0, amount)
            changed = changed or amount > 0
            previous[key] = value
        if changed:
            row = dict(point)
            row["delta"] = delta
            rows.append(row)
    return rows


def _billing_add(
    billing: dict[str, dict[str, int]], model: str | None, delta: dict[str, Any]
) -> None:
    cached = delta.get("cached_input_tokens") or 0
    inp = max(0, (delta.get("input_tokens") or 0) - cached)
    bucket = billing.setdefault(model or "codex", {"req": 0, "inp": 0, "cread": 0,
                                                    "cw5": 0, "cw1h": 0, "out": 0})
    bucket["req"] += 1
    bucket["inp"] += inp
    bucket["cread"] += cached
    bucket["out"] += delta.get("output_tokens") or 0


#: 阶段最短驻留(秒):短于它的"阶段"是技能路径的浏览批次,不是真实切换
_STAGE_MIN_SPAN_S = 90


def _ts_seconds(ts: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _stage_boundaries(root: dict[str, Any]) -> list[tuple[int, str]]:
    markers: list[tuple[int, str]] = []
    for call in root["calls"]:
        for skill in _skill_names(call.get("raw") or ""):
            skill = skill.split(":")[-1]
            if skill in _CODEX_STAGE_SKILLS:
                markers.append((call["idx"], skill))
    # Preserve textual/call order for multiple skill paths in one command.
    # Tuple sorting would alphabetize equal-index skills (Build before Run),
    # inventing a stage transition that never happened.
    markers.sort(key=lambda item: item[0])
    transitions: list[tuple[int, str]] = []
    current: str | None = None
    used_idx: set[int] = set()
    for idx, skill in markers:
        if idx in used_idx or skill == current:
            continue
        transitions.append((idx, skill))
        used_idx.add(idx)
        current = skill
    # 浏览批次去噪:开场技能清单/一条命令引用多个技能,会造出几秒到几十秒的
    # 假阶段(实测 AIPPT 生成会话开场 1 分钟连环 execute/plan/spec/verify)。
    # 持续不足 _STAGE_MIN_SPAN_S 的段不是真实阶段:删掉后其区间归前段
    # (开场批次归 setup),同名相邻合并,迭代至稳定;真实的多轮循环保留。
    ts_by_idx: dict[int, float] = {}
    for call in root["calls"]:
        sec = _ts_seconds(call.get("ts"))
        if sec is not None:
            ts_by_idx[call["idx"]] = sec
    changed = True
    while changed and len(transitions) > 1:
        changed = False
        for i in range(len(transitions)):
            t0 = ts_by_idx.get(transitions[i][0])
            t1 = (ts_by_idx.get(transitions[i + 1][0])
                  if i + 1 < len(transitions) else None)
            if t0 is not None and t1 is not None and t1 - t0 < _STAGE_MIN_SPAN_S:
                del transitions[i]
                j = 1
                while j < len(transitions):
                    if transitions[j][1] == transitions[j - 1][1]:
                        del transitions[j]
                    else:
                        j += 1
                changed = True
                break
    if not transitions:
        return [(0, "session")]
    rows = [(0, "setup")] if transitions[0][0] > 0 else []
    rows.extend(transitions)
    return rows


def _build_stages(root: dict[str, Any]) -> list[dict[str, Any]]:
    boundaries = _stage_boundaries(root)
    max_idx = max([idx for idx, _ in root["record_points"]] or [0])
    points = root["record_points"]
    stages: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    for pos, (start_idx, key) in enumerate(boundaries):
        end_idx = boundaries[pos + 1][0] - 1 if pos + 1 < len(boundaries) else max_idx
        times = [ts for idx, ts in points if start_idx <= idx <= end_idx and ts]
        label = common.STAGE_LABELS.get(key, key)
        seen[key] += 1
        if seen[key] > 1:
            label += " ·%d" % seen[key]
        stages.append({
            "id": "s%d" % pos, "stage": key, "label": label,
            "start_idx": start_idx, "end_idx": end_idx,
            "start_ts": min(times) if times else None,
            "end_ts": max(times) if times else None,
            "duration_ms": common.ms_between(min(times), max(times)) if times else None,
            "tool_counts": {}, "output_tokens": 0, "cache_read_tokens": 0,
            "helper_skills": [], "artifacts": [], "agent_count": 0,
            "prompt_idxs": [], "wait_ms": 0, "active_ms": None,
        })
    return stages


def _stage_of_idx(stages: list[dict[str, Any]], idx: int) -> dict[str, Any]:
    for stage in reversed(stages):
        if idx >= stage["start_idx"]:
            return stage
    return stages[0]


def _stage_of_time(stages: list[dict[str, Any]], ts: str | None) -> dict[str, Any]:
    if ts:
        for stage in stages:
            if stage.get("start_ts") and stage.get("end_ts") and stage["start_ts"] <= ts <= stage["end_ts"]:
                return stage
        for stage in reversed(stages):
            if stage.get("start_ts") and ts >= stage["start_ts"]:
                return stage
    return stages[0]


def _aggregate_agent_reads(agent: dict[str, Any], tools: list[dict[str, Any]]) -> None:
    for tool in tools:
        path = tool.get("brief")
        if tool.get("name") == "Read" and path:
            agent["_reads"].append(path)
        if tool.get("name") in ("Bash", "PowerShell"):
            # shell 白盒解析(common 同款):确定性读写,零推断零磁盘
            _sio = shellparse.parse_shell(str((tool.get("_inp") or {}).get("command") or ""))
            for rp0 in _sio.content_reads:
                agent["_reads"].append(rp0)
                agent["_read_sources"].setdefault(rp0, set()).add(str(tool.get("name")) + "·cmd")
                sp0 = _sio.spans.get(rp0)
                if sp0:
                    agent["_read_iv"].setdefault(rp0, []).append(sp0)
                    agent["_read_lines"][rp0] = agent["_read_lines"].get(rp0, 0) + sp0[1]
            for wp0 in _sio.writes:
                agent["_writes"].append(wp0)
        if tool.get("name") in ("Write", "Edit") and path and tool.get("ok") is not False:
            agent["_writes"].append(path)
            if tool.get("wlines"):
                agent["_write_lines"][path] = agent["_write_lines"].get(path, 0) + tool["wlines"]
            if tool.get("wevent"):
                agent["_write_events"].append((tool.get("ts") or "", path,
                                                tool["wevent"][0], tool["wevent"][1]))
            if path.endswith(".ets"):
                # patch 行自带 bevent;shell 写盘没有明文 → opaque 让重放诚实断链
                bev = tool.get("bevent") or ("opaque", None)
                agent["_blame_events"].append((tool.get("ts") or "", path, bev[0], bev[1]))
        for probed in tool.get("_probed_paths") or []:
            agent["_probed"].append(probed)
        for event in tool.get("_visible_source_lines") or []:
            path = event["path"]
            agent["_reads"].append(path)
            agent["_read_sources"].setdefault(path, set()).add(event.get("via") or tool.get("name"))
            for start, count in event.get("intervals") or []:
                agent["_read_iv"].setdefault(path, []).append((start, count))
                agent["_read_lines"][path] = agent["_read_lines"].get(path, 0) + count
            try:
                with open(path, encoding="utf-8", errors="ignore") as stream:
                    total = sum(1 for _ in stream)
            except OSError:
                total = 0
            if total:
                agent["_read_total"][path] = max(agent["_read_total"].get(path, 0), total)


def _agent_entry(
    rollout: dict[str, Any], stage: dict[str, Any], spawn_tool: dict[str, Any] | None = None
) -> dict[str, Any]:
    skills: Counter[str] = Counter()
    for call in rollout["calls"]:
        skills.update(_skill_names(call.get("raw") or ""))
    deltas = _usage_deltas(rollout["token_points"])
    output = sum(row["delta"].get("output_tokens", 0) for row in deltas)
    reasoning = min(output, sum(row["delta"].get("reasoning_output_tokens", 0) for row in deltas))
    remaining = max(0, output - reasoning)
    chars = rollout["text_chars"] + rollout["tool_chars"]
    text_out = int(round(remaining * rollout["text_chars"] / chars)) if chars else remaining
    entry = {
        "agent_id": rollout["id"],
        # 角色(thread_spawn.agent_role)优先于任务代号:fixer/visual 等审计判定
        # 靠 type,任务代号可以叫任何名字(实据见 test_codex_session)
        "type": (rollout.get("agent_role")
                 or (rollout.get("agent_path") or "codex-subagent").rstrip("/").split("/")[-1]),
        "desc": ((rollout.get("agent_path") or "Codex subagent") +
                 ((" · " + rollout["nickname"]) if rollout.get("nickname") else ""))[:240],
        "wf_run": None, "wf_name": None, "wf_phase": None,
        "tuid": spawn_tool.get("tuid") if spawn_tool else None,
        "stage": stage["stage"], "seg": stage["id"],
        "start_ts": rollout["start_ts"], "end_ts": rollout["end_ts"],
        "dur_ms": common.ms_between(rollout["start_ts"], rollout["end_ts"]),
        "output_tokens": output, "tool_uses": len(rollout["tools"]),
        "tool_counts": dict(Counter(tool["name"] for tool in rollout["tools"])),
        "status": "completed" if rollout["completed"] else "unknown",
        "aborted": None if rollout["completed"] else "interrupted",
        "model": rollout["model"], "result": rollout["result"],
        "skills": dict(skills), "skill_calls": [],
        "out_split": {"thinking": reasoning, "text": text_out,
                      "tool": max(0, remaining - text_out)},
        "_prompt": ((spawn_tool or {}).get("agent_prompt")
                    or (rollout["prompts"][0]["text"] if rollout["prompts"] else "")
                    or (("[任务复述·派发原文加密未落盘] " + rollout["first_message"])
                        if rollout.get("first_message") else "")),
        "_probed": [], "_reads": [], "_writes": [], "_read_lines": {},
        "_read_iv": {}, "_read_total": {}, "_read_sources": {},
        "_write_lines": {}, "_write_events": [], "_blame_events": [],
    }
    # 活跃段(与 claude 同口径,>10min 空洞切段):resume 复用型子代理甘特按段画
    act_segs = common._activity_segments(
        [ts for _idx, ts in rollout.get("record_points") or [] if ts])
    if len(act_segs) > 1:
        entry["active"] = act_segs
        entry["active_ms"] = sum(
            (common.ms_between(s0, s1) or 0) for s0, s1 in act_segs)
    _aggregate_agent_reads(entry, rollout["tools"])
    return entry


def collect_blame_events(path: str, sessions_root: str | None = None) -> list[tuple[Any, ...]]:
    """整个会话树(root+全部子代理)的 .ets 行级写事件,跨会话接力用。

    返回 [(ts, abs_path, agent_id, op, payload)];agent_id = rollout thread id
    (与 trace lineage 的子代理 agent_id 同一命名空间,root 主线即 root id)。
    payload 只在内存流转,与单会话 blame 同一来源(tools 行的 bevent)。
    """
    events: list[tuple[Any, ...]] = []
    for item in discover_rollout_tree(path, sessions_root=sessions_root):
        rollout = _parse_rollout(item["path"], tree_item=item)
        aid = str(rollout.get("id") or "")
        for tool in rollout["tools"]:
            bev = tool.get("bevent")
            if bev and tool.get("ok") is not False and tool.get("brief"):
                events.append((tool.get("ts") or "", str(tool["brief"]), aid,
                               bev[0], bev[1]))
    return events


def stage_intervals(path: str, sessions_root: str | None = None) -> list[dict[str, Any]]:
    """主线 rollout 的阶段区间(与 extract 同一套边界与去噪):[{stage, start_ts, end_ts}]。
    两原子账本给 codex 版本回填阶段用 —— codex 记录没有归属戳,阶段只能从主线读 SKILL.md 推。"""
    tree = discover_rollout_tree(path, sessions_root=sessions_root)
    root_id = (session_summary(path) or {}).get("id")
    root_item = next((item for item in tree if item["meta"].get("id") == root_id), tree[0])
    root = _parse_rollout(root_item["path"], root_item)
    return [{"stage": st["stage"], "start_ts": st.get("start_ts"), "end_ts": st.get("end_ts")}
            for st in _build_stages(root)]


def stage_at(stages: list[dict[str, Any]], ts: str | None) -> str | None:
    """时刻 → 阶段名(区间内取区间,区间外取最近开始的;没有区间给 None)。"""
    if not stages:
        return None
    return str(_stage_of_time(stages, ts)["stage"])


def extract(path: str, sessions_root: str | None = None) -> dict[str, Any]:
    tree = discover_rollout_tree(path, sessions_root=sessions_root)
    root_id = (session_summary(path) or {}).get("id")
    root_item = next((item for item in tree if item["meta"].get("id") == root_id), tree[0])
    # 主线每次全解(它的工具明细要进 trace);子代理走归约产物缓存
    root = _parse_rollout(root_item["path"], root_item)
    children = [_child_product(item) for item in tree if item is not root_item]
    stages = _build_stages(root)

    # Root tools and prompts receive deterministic stage ownership by record index.
    for tool in root["tools"]:
        stage = _stage_of_idx(stages, tool["idx"])
        tool["stage"], tool["seg"] = stage["stage"], stage["id"]
        stage["tool_counts"][tool["name"]] = stage["tool_counts"].get(tool["name"], 0) + 1
        if tool["name"] in ("Write", "Edit") and tool.get("brief") not in stage["artifacts"]:
            stage["artifacts"].append(tool.get("brief"))
        for skill in tool.get("skills") or []:
            if skill not in _PIPELINE_SKILLS:
                stage["helper_skills"].append({"idx": tool["idx"], "ts": tool["ts"], "skill": skill})
    for prompt in root["prompts"]:
        stage = _stage_of_idx(stages, prompt["idx"])
        prompt["stage"], prompt["seg"] = stage["stage"], stage["id"]
        stage["prompt_idxs"].append(prompt["idx"])

    billing: dict[str, dict[str, int]] = {}
    context_timeline: list[dict[str, Any]] = []
    for row in _usage_deltas(root["token_points"]):
        delta, last = row["delta"], row.get("last") or {}
        _billing_add(billing, row.get("model"), delta)
        stage = _stage_of_idx(stages, row["idx"])
        stage["output_tokens"] += delta.get("output_tokens") or 0
        stage["cache_read_tokens"] += delta.get("cached_input_tokens") or 0
        cached = last.get("cached_input_tokens") or 0
        context_timeline.append({"ts": row.get("ts"),
                                 "ctx": last.get("input_tokens") or 0,
                                 "out": last.get("output_tokens") or 0,
                                 "inp": max(0, (last.get("input_tokens") or 0) - cached),
                                 "cread": cached, "cwrite": 0})

    # Link spawn calls to child agent_path where possible; otherwise use the
    # child's explicit parent edge and start time.
    tools_by_rollout: dict[Any, list[dict[str, Any]]] = {root["id"]: root["tools"]}
    for product in children:
        tools_by_rollout[product["id"]] = product["agent_tools"]
    stage_by_agent: dict[Any, dict[str, Any]] = {}
    agents: list[dict[str, Any]] = []
    pending = sorted(children, key=lambda item: (item.get("depth") or 0, item["start_ts"] or ""))
    for child in pending:
        parent_stage = stage_by_agent.get(child.get("parent"))
        stage = parent_stage or _stage_of_time(stages, child.get("start_ts"))
        parent_tools = tools_by_rollout.get(child.get("parent"), [])
        task_name = (child.get("agent_path") or "").rstrip("/").split("/")[-1]
        spawn = next((tool for tool in parent_tools
                      if tool["name"] == "Agent" and task_name and task_name in (tool.get("brief") or "")), None)
        # 归约产物不带阶段/派发点(那是主线决定的),命中后在这里回填 —— 同 CC
        agent = child["entry"]
        agent["stage"], agent["seg"] = stage["stage"], stage["id"]
        agent["tuid"] = spawn.get("tuid") if spawn else None
        agent["_prompt"] = ((spawn or {}).get("agent_prompt") or child["prompt_fallback"])
        agents.append(agent)
        stage_by_agent[child["id"]] = stage
        stage["agent_count"] += 1
        for model, delta in child["billing"]:
            _billing_add(billing, model, delta)

    meta_payload = root["meta"]
    meta = {
        "source_file": os.path.abspath(path), "schema_version": "codex-1.0",
        "session_format": "codex", "session_id": root["session_id"],
        "cc_version": meta_payload.get("cli_version"), "cwd": root["cwd"],
        "model": root["model"], "started_at": root["start_ts"],
        "ended_at": root["end_ts"],
        "record_count": root["record_count"] + sum(c["record_count"] for c in children),
    }
    lineage = common.build_lineage(agents, root["tools"], root["cwd"])

    for agent in agents:
        # 与 claude.py 同款:派发指令摘录保留(抽屉「派发指令」栏用),其余临时字段剥离
        agent["prompt_excerpt"] = (agent.pop("_prompt", None) or "")[:800]
        for key in ("_reads", "_writes", "_read_lines", "_write_lines",
                    "_read_iv", "_read_total", "_read_sources", "_write_events",
                    "_blame_events"):
            agent.pop(key, None)
    for tool in root["tools"]:
        tool.pop("_inp", None)
        tool.pop("_visible_source_lines", None)
        tool.pop("_probed_paths", None)

    main_out = sum(stage["output_tokens"] for stage in stages)
    sub_out = sum(agent["output_tokens"] for agent in agents)
    split = {"thinking": 0, "text": 0, "tool": 0}
    for agent in agents:
        for key, value in agent.get("out_split", {}).items():
            split[key] += value
    root_reasoning = sum(row["delta"].get("reasoning_output_tokens", 0)
                         for row in _usage_deltas(root["token_points"]))
    split["thinking"] += min(main_out, root_reasoning)
    split["text"] += max(0, main_out - root_reasoning)
    duration = common.ms_between(meta["started_at"], meta["ended_at"])
    totals = {
        "duration_ms": duration, "user_wait_ms": 0,
        "active_ms": duration, "tool_calls": len(root["tools"]),
        "agent_calls": len(agents), "subagent_transcripts": len(agents),
        "main_output_tokens": main_out, "subagent_output_tokens": sub_out,
        "aborted_agents": sum(1 for agent in agents if agent.get("aborted")),
        "waste_output_tokens": sum(agent["output_tokens"] for agent in agents if agent.get("aborted")),
        "output_split": split, "user_prompts": len(root["prompts"]),
        "files_touched": len({tool.get("brief") for tool in root["tools"]
                              if tool["name"] in ("Write", "Edit") and tool.get("brief")}),
        "compactions": len(root["markers"]),
    }
    return {"meta": meta, "totals": totals, "stages": stages,
            "tools": root["tools"], "agents": agents, "prompts": root["prompts"],
            "markers": root["markers"], "context_timeline": context_timeline,
            "billing": billing, "lineage": lineage, "workflows": []}
