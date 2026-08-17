# -*- coding: utf-8 -*-
"""Codex rollout JSONL -> MigLoop's normalized trace schema.

The viewer deliberately consumes one provider-neutral trace.  This module is
therefore an input adapter, not a second visualization pipeline.  It keeps the
Claude Code extractor unchanged and translates Codex records (`session_meta`,
`response_item`, `event_msg`) into the same meta/stage/tool/agent/lineage
objects returned by :mod:`extract_session`.
"""
import difflib
import glob
import json
import os
import re
from collections import Counter

import extract_session as common


_JSON_STRING = r'"(?:\\.|[^"\\])*"'
_PIPELINE_SKILLS = set(common.PIPELINE_SKILLS)
# Codex conversion skills read the run/build wrappers while bootstrapping.
# They are orchestration helpers, not migration work phases.  The concrete
# phase skills below are the stable stage boundaries users expect to see.
_CODEX_STAGE_SKILLS = {
    "mig-arch", "a2h-arch-scaffold", "a2h-spec", "a2h-plan",
    "a2h-execute", "a2h-verify", "a2h-retrospect",
}


def _first_json(path):
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


def is_codex_session(path):
    record = _first_json(path) or {}
    return record.get("type") == "session_meta" and isinstance(record.get("payload"), dict)


def session_summary(path):
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


def _sessions_root(path):
    cur = os.path.abspath(os.path.dirname(path))
    while True:
        if os.path.basename(cur).lower() == "sessions" and os.path.basename(os.path.dirname(cur)).lower() == ".codex":
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.dirname(os.path.abspath(path))


def discover_rollout_tree(path, sessions_root=None):
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
    candidates = {}
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


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
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


def _decode_arguments(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {"input": result}
    except (json.JSONDecodeError, TypeError):
        return {"input": value}


def _decode_js_string(token):
    try:
        return json.loads(token)
    except (json.JSONDecodeError, TypeError):
        return ""


def _js_field(segment, key):
    pattern = re.compile(r'(?:"?%s"?)\s*:\s*(%s)' % (re.escape(key), _JSON_STRING), re.DOTALL)
    match = pattern.search(segment or "")
    return _decode_js_string(match.group(1)) if match else None


def _nested_segments(source, tool_name):
    hits = list(re.finditer(r"\btools\.%s\s*\(" % re.escape(tool_name), source or ""))
    for pos, hit in enumerate(hits):
        end = hits[pos + 1].start() if pos + 1 < len(hits) else len(source)
        yield source[hit.start():end]


def _extract_shell_calls(source, default_cwd):
    calls = []
    for segment in _nested_segments(source, "shell_command"):
        command = _js_field(segment, "command")
        if not command:
            continue
        calls.append({"command": command,
                      "workdir": _js_field(segment, "workdir") or default_cwd})
    return calls


def _extract_apply_patches(source):
    variables = {}
    var_re = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(%s)\s*;" % _JSON_STRING,
                        re.DOTALL)
    for match in var_re.finditer(source or ""):
        variables[match.group(1)] = _decode_js_string(match.group(2))
    patches = []
    call_re = re.compile(r"\btools\.apply_patch\s*\(\s*(%s|[A-Za-z_$][\w$]*)\s*\)" % _JSON_STRING,
                         re.DOTALL)
    for match in call_re.finditer(source or ""):
        arg = match.group(1)
        patch = _decode_js_string(arg) if arg.startswith('"') else variables.get(arg)
        if patch and "*** Begin Patch" in patch:
            patches.append(patch)
    return patches


def _skill_names(text):
    pattern = re.compile(r"(?i)(?:\\+|/)+skills(?:\\+|/)+([a-z0-9_-]+)(?:\\+|/)+SKILL\.md")
    return list(dict.fromkeys(match.group(1) for match in pattern.finditer(text or "")))


def _tool_failed(output):
    low = (output or "").lower()
    if "script failed" in low or '"iserror":true' in low.replace(" ", ""):
        return True
    match = re.search(r"exit code:\s*(-?\d+)", low)
    return bool(match and int(match.group(1)) != 0)


def _duration_ms(start_ts, end_ts, output):
    values = [float(x) for x in re.findall(r"Wall time\s+([0-9.]+)\s+seconds", output or "", re.I)]
    if values:
        return int(max(values) * 1000)
    return common.ms_between(start_ts, end_ts)


def _resolve_path(value, cwd):
    if not value or "$" in value or "%" in value or "*" in value or "?" in value:
        return None
    value = value.strip().strip("\"'").replace("\\", os.sep).replace("/", os.sep)
    path = value if os.path.isabs(value) else os.path.join(cwd or os.getcwd(), value)
    return os.path.abspath(path)


def _powershell_variables(command):
    values = {}
    pattern = re.compile(r"\$([A-Za-z_][\w]*)\s*=\s*(?:@?\()?\s*(['\"])(.*?)\2", re.DOTALL)
    for match in pattern.finditer(command or ""):
        values[match.group(1).lower()] = match.group(3)
    return values


def _explicit_get_content_paths(command, cwd):
    variables = _powershell_variables(command)
    values = []
    pattern = re.compile(
        r"(?i)\bGet-Content\b(?:(?![;|\r\n]).)*?(?:-(?:LiteralPath|Path)\s+)?"
        r"(?P<value>\$[A-Za-z_][\w]*|'[^']+'|\"[^\"]+\")"
    )
    for match in pattern.finditer(command or ""):
        raw = match.group("value")
        if raw.startswith("$"):
            raw = variables.get(raw[1:].lower())
        else:
            raw = raw[1:-1]
        path = _resolve_path(raw, cwd)
        if path and os.path.isfile(path) and path not in values:
            values.append(path)
    return values


def _visible_intervals(path, output):
    try:
        with open(path, encoding="utf-8", errors="ignore") as stream:
            source = stream.read().replace("\r\n", "\n").replace("\r", "\n")
    except OSError:
        return [], 0
    lines = source.splitlines()
    shown = (output or "").replace("\r\n", "\n").replace("\r", "\n")
    if source and source.rstrip("\n") in shown:
        return [(1, len(lines))], len(lines)
    output_lines = shown.splitlines()
    hits = []
    matcher = difflib.SequenceMatcher(None, [x.rstrip() for x in lines],
                                      [x.rstrip() for x in output_lines], autojunk=False)
    for block in matcher.get_matching_blocks():
        if block.size < 2:
            continue
        if sum(len(x.strip()) for x in lines[block.a:block.a + block.size]) < 16:
            continue
        hits.append((block.a + 1, block.size))
    # A search may expose isolated but globally unique substantive lines.
    index = {}
    for lineno, line in enumerate(lines, 1):
        key = line.strip()
        if len(key) >= 8:
            index.setdefault(key, []).append(lineno)
    for line in output_lines:
        locations = index.get(line.strip()) or []
        if len(locations) == 1:
            hits.append((locations[0], 1))
    return common._merge_line_intervals(hits), len(lines)


def _generic_visible_events(command, output, cwd):
    events = []
    for path in _explicit_get_content_paths(command, cwd):
        intervals, _ = _visible_intervals(path, output)
        if intervals:
            events.append({"path": path.replace("\\", "/"),
                           "intervals": intervals, "via": "PowerShell"})
    return events


def _patch_entries(patch, cwd):
    header = re.compile(r"^\*\*\* (Add|Update|Delete) File:\s*(.+?)\s*$", re.M)
    matches = list(header.finditer(patch or ""))
    rows = []
    for pos, match in enumerate(matches):
        body_end = matches[pos + 1].start() if pos + 1 < len(matches) else len(patch)
        body = patch[match.end():body_end]
        action, raw_path = match.group(1), match.group(2).strip()
        path = _resolve_path(raw_path, cwd) or raw_path
        added = sum(1 for line in body.splitlines()
                    if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in body.splitlines()
                      if line.startswith("-") and not line.startswith("---"))
        if action == "Add":
            name, event = "Write", ["set", added]
        elif action == "Delete":
            name, event = "Edit", ["delta", -removed]
        else:
            name, event = "Edit", ["delta", added - removed]
        rows.append({"name": name, "brief": path, "wlines": added,
                     "wevent": event, "patch_action": action})
    return rows


def _tool_entry(idx, ts, name, inp, call_id, output, output_ts, brief=None):
    return {
        "idx": idx, "ts": ts, "name": name,
        "brief": brief if brief is not None else common.brief_tool_target(name, inp),
        "ok": not _tool_failed(output),
        "dur_ms": _duration_ms(ts, output_ts, output),
        "tuid": call_id, "result": (output or "").strip()[:220], "_inp": inp,
    }


def _normalize_tools(rollout):
    rows = []
    for call in rollout["calls"]:
        result = rollout["outputs"].get(call.get("call_id")) or {}
        output = result.get("text") or ""
        output_ts = result.get("ts")
        raw = call.get("raw") or ""
        if call.get("name") == "exec":
            extracted = False
            for shell in _extract_shell_calls(raw, rollout.get("cwd")):
                extracted = True
                command = shell["command"]
                workdir = shell.get("workdir") or rollout.get("cwd")
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
                for patch_row in _patch_entries(patch, rollout.get("cwd")):
                    entry = _tool_entry(call["idx"], call["ts"], patch_row.pop("name"),
                                        {}, call.get("call_id"), output, output_ts,
                                        brief=patch_row.pop("brief"))
                    entry.update(patch_row)
                    rows.append(entry)
            if not extracted:
                rows.append(_tool_entry(call["idx"], call["ts"], "exec",
                                        {"input": raw}, call.get("call_id"), output, output_ts,
                                        brief=" ".join(raw.split())[:300]))
            continue

        args = _decode_arguments(call.get("raw"))
        name = call.get("name") or "tool"
        display_name = "Agent" if name == "spawn_agent" else name
        entry = _tool_entry(call["idx"], call["ts"], display_name, args,
                            call.get("call_id"), output, output_ts)
        if name == "spawn_agent":
            entry["agent_type"] = args.get("task_name") or "codex-subagent"
            message = args.get("message") or ""
            entry["agent_desc"] = message[:240] if not message.startswith("gAAAA") else args.get("task_name", "")
        rows.append(entry)
    for seq, row in enumerate(sorted(rows, key=lambda x: (x["idx"], x.get("ts") or "", x["name"]))):
        row["seq"] = seq
    return rows


def _parse_rollout(path, tree_item=None):
    records = []
    with open(path, encoding="utf-8", errors="replace") as stream:
        for idx, line in enumerate(stream):
            try:
                records.append((idx, json.loads(line)))
            except json.JSONDecodeError:
                continue

    meta_payload = next(
        ((record.get("payload") or {}) for _, record in records
         if record.get("type") == "session_meta"),
        {},
    )

    # A forked Codex rollout starts with its own session_meta, then replays the
    # parent's conversation snapshot before injecting the child-agent
    # developer message.  Tool calls are normally local-only, but token_count
    # records in that snapshot contain the parent's cumulative counters.  Do
    # not charge that inherited context to the child.  The marker is emitted
    # by Codex itself at the subagent activation boundary.
    local_start = 0
    if tree_item and tree_item.get("parent"):
        for idx, record in records:
            payload = record.get("payload") or {}
            if (record.get("type") == "response_item" and
                    payload.get("type") == "message" and
                    payload.get("role") == "developer" and
                    "You are an agent in a team of agents" in _content_text(payload.get("content"))):
                local_start = idx

    inherited_usage = {}
    if local_start:
        for idx, record in records:
            if idx >= local_start:
                break
            payload = record.get("payload") or {}
            if (record.get("type") == "event_msg" and
                    payload.get("type") == "token_count" and
                    isinstance(payload.get("info"), dict)):
                inherited_usage = dict(payload["info"].get("total_token_usage") or {})

    first = last = None
    record_points = []
    calls, outputs, prompts, token_points, markers = [], {}, [], [], []
    model = None
    last_message = ""
    completed = False
    text_chars = tool_chars = 0
    record_count = 0
    for idx, record in records:
            if idx < local_start:
                continue
            record_count += 1
            ts = record.get("timestamp")
            if ts:
                first = min(first, ts) if first else ts
                last = max(last, ts) if last else ts
                record_points.append((idx, ts))
            outer = record.get("type")
            payload = record.get("payload") or {}
            if outer == "session_meta":
                first = first or payload.get("timestamp")
            elif outer == "turn_context":
                model = payload.get("model") or model
            elif outer == "response_item":
                ptype = payload.get("type")
                if ptype in ("function_call", "custom_tool_call"):
                    raw = payload.get("arguments") if ptype == "function_call" else payload.get("input")
                    raw = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                    calls.append({"idx": idx, "ts": ts, "ptype": ptype,
                                  "name": payload.get("name"), "call_id": payload.get("call_id"),
                                  "raw": raw})
                    tool_chars += len(raw or "")
                elif ptype in ("function_call_output", "custom_tool_call_output"):
                    outputs[payload.get("call_id")] = {"ts": ts, "text": _content_text(payload.get("output"))}
                elif ptype == "message" and payload.get("role") == "assistant":
                    text = _content_text(payload.get("content"))
                    if text.strip():
                        last_message = text.strip()[:300]
                        text_chars += len(text)
                elif ptype == "reasoning":
                    summary = _content_text(payload.get("summary"))
                    if summary:
                        text_chars += len(summary)
            elif outer == "event_msg":
                ptype = payload.get("type")
                if ptype == "user_message":
                    text = payload.get("message") or ""
                    if text.strip():
                        prompts.append({"idx": idx, "ts": ts, "wait_ms": 0,
                                        "text": " ".join(text.split())[:400]})
                elif ptype == "agent_message" and payload.get("message"):
                    last_message = str(payload.get("message"))[:300]
                elif ptype == "task_complete":
                    completed = True
                elif ptype == "token_count" and isinstance(payload.get("info"), dict):
                    info = payload["info"]
                    total = dict(info.get("total_token_usage") or {})
                    if inherited_usage:
                        for key, value in list(total.items()):
                            if isinstance(value, (int, float)):
                                total[key] = max(0, value - (inherited_usage.get(key) or 0))
                    token_points.append({"idx": idx, "ts": ts,
                                         "total": total,
                                         "last": info.get("last_token_usage") or {},
                                         "model": model or "codex"})
                elif ptype in ("context_compacted", "compaction"):
                    markers.append({"idx": idx, "ts": ts, "kind": "compact"})
    resolved_model = model or "codex"
    for point in token_points:
        if point.get("model") == "codex":
            point["model"] = resolved_model
    result = {
        "path": os.path.abspath(path), "meta": meta_payload,
        "id": meta_payload.get("id") or meta_payload.get("session_id"),
        "session_id": meta_payload.get("session_id") or meta_payload.get("id"),
        "cwd": meta_payload.get("cwd"), "model": resolved_model,
        "start_ts": first or meta_payload.get("timestamp"), "end_ts": last,
        "record_count": record_count, "record_points": record_points,
        "calls": calls, "outputs": outputs, "prompts": prompts,
        "token_points": token_points, "markers": markers,
        "completed": completed, "result": last_message,
        "text_chars": text_chars, "tool_chars": tool_chars,
    }
    if tree_item:
        result.update({"parent": tree_item.get("parent"),
                       "agent_path": tree_item.get("agent_path"),
                       "nickname": tree_item.get("nickname"),
                       "depth": tree_item.get("depth")})
    result["tools"] = _normalize_tools(result)
    return result


def _usage_deltas(points):
    previous = {"input_tokens": 0, "cached_input_tokens": 0,
                "output_tokens": 0, "reasoning_output_tokens": 0}
    rows = []
    for point in points:
        current = point.get("total") or {}
        delta = {}
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


def _billing_add(billing, model, delta):
    cached = delta.get("cached_input_tokens") or 0
    inp = max(0, (delta.get("input_tokens") or 0) - cached)
    bucket = billing.setdefault(model or "codex", {"req": 0, "inp": 0, "cread": 0,
                                                    "cw5": 0, "cw1h": 0, "out": 0})
    bucket["req"] += 1
    bucket["inp"] += inp
    bucket["cread"] += cached
    bucket["out"] += delta.get("output_tokens") or 0


def _stage_boundaries(root):
    markers = []
    for call in root["calls"]:
        for skill in _skill_names(call.get("raw") or ""):
            skill = skill.split(":")[-1]
            if skill in _CODEX_STAGE_SKILLS:
                markers.append((call["idx"], skill))
    # Preserve textual/call order for multiple skill paths in one command.
    # Tuple sorting would alphabetize equal-index skills (Build before Run),
    # inventing a stage transition that never happened.
    markers.sort(key=lambda item: item[0])
    transitions = []
    current = None
    used_idx = set()
    for idx, skill in markers:
        if idx in used_idx or skill == current:
            continue
        transitions.append((idx, skill))
        used_idx.add(idx)
        current = skill
    if not transitions:
        return [(0, "session")]
    rows = [(0, "setup")] if transitions[0][0] > 0 else []
    rows.extend(transitions)
    return rows


def _build_stages(root):
    boundaries = _stage_boundaries(root)
    max_idx = max([idx for idx, _ in root["record_points"]] or [0])
    points = root["record_points"]
    stages = []
    seen = Counter()
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


def _stage_of_idx(stages, idx):
    for stage in reversed(stages):
        if idx >= stage["start_idx"]:
            return stage
    return stages[0]


def _stage_of_time(stages, ts):
    if ts:
        for stage in stages:
            if stage.get("start_ts") and stage.get("end_ts") and stage["start_ts"] <= ts <= stage["end_ts"]:
                return stage
        for stage in reversed(stages):
            if stage.get("start_ts") and ts >= stage["start_ts"]:
                return stage
    return stages[0]


def _aggregate_agent_reads(agent, tools):
    for tool in tools:
        path = tool.get("brief")
        if tool.get("name") == "Read" and path:
            agent["_reads"].append(path)
        if tool.get("name") in ("Write", "Edit") and path and tool.get("ok") is not False:
            agent["_writes"].append(path)
            if tool.get("wlines"):
                agent["_write_lines"][path] = agent["_write_lines"].get(path, 0) + tool["wlines"]
            if tool.get("wevent"):
                agent["_write_events"].append((tool.get("ts") or "", path,
                                                tool["wevent"][0], tool["wevent"][1]))
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


def _agent_entry(rollout, stage, spawn_tool=None):
    skills = Counter()
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
        "type": (rollout.get("agent_path") or "codex-subagent").rstrip("/").split("/")[-1],
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
        "_prompt": rollout["prompts"][0]["text"] if rollout["prompts"] else "",
        "_probed": [], "_reads": [], "_writes": [], "_read_lines": {},
        "_read_iv": {}, "_read_total": {}, "_read_sources": {},
        "_write_lines": {}, "_write_events": [],
    }
    _aggregate_agent_reads(entry, rollout["tools"])
    return entry


def extract(path, sessions_root=None):
    tree = discover_rollout_tree(path, sessions_root=sessions_root)
    parsed = [_parse_rollout(item["path"], item) for item in tree]
    root_id = session_summary(path).get("id")
    root = next((item for item in parsed if item["id"] == root_id), parsed[0])
    children = [item for item in parsed if item is not root]
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

    billing = {}
    context_timeline = []
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
    tools_by_rollout = {item["id"]: item["tools"] for item in parsed}
    stage_by_agent = {}
    agents = []
    pending = sorted(children, key=lambda item: (item.get("depth") or 0, item["start_ts"] or ""))
    for child in pending:
        parent_stage = stage_by_agent.get(child.get("parent"))
        stage = parent_stage or _stage_of_time(stages, child.get("start_ts"))
        parent_tools = tools_by_rollout.get(child.get("parent"), [])
        task_name = (child.get("agent_path") or "").rstrip("/").split("/")[-1]
        spawn = next((tool for tool in parent_tools
                      if tool["name"] == "Agent" and task_name and task_name in (tool.get("brief") or "")), None)
        agent = _agent_entry(child, stage, spawn)
        agents.append(agent)
        stage_by_agent[child["id"]] = stage
        stage["agent_count"] += 1
        for row in _usage_deltas(child["token_points"]):
            _billing_add(billing, row.get("model"), row["delta"])

    meta_payload = root["meta"]
    meta = {
        "source_file": os.path.abspath(path), "schema_version": "codex-1.0",
        "session_format": "codex", "session_id": root["session_id"],
        "cc_version": meta_payload.get("cli_version"), "cwd": root["cwd"],
        "model": root["model"], "started_at": root["start_ts"],
        "ended_at": root["end_ts"],
        "record_count": sum(item["record_count"] for item in parsed),
    }
    lineage = common.build_lineage(agents, root["tools"], root["cwd"])

    for agent in agents:
        for key in ("_prompt", "_reads", "_writes", "_read_lines", "_write_lines",
                    "_read_iv", "_read_total", "_read_sources", "_write_events"):
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
