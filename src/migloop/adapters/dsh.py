# -*- coding: utf-8 -*-
"""DeepSeek Harness (dsh) session log -> MigLoop normalized trace.

Input: a dsh Session generation file (``session.v4.jsonl`` or
``session.v4.jsonl.zstd``), its session directory, or a session id / id prefix
found under the dsh persistence root (``$DSH_HOME/sessions``, default
``~/.dsh/sessions``). Decoding, generation selection and sub-agent discovery
live in :mod:`dsh_source`; this module only maps durable ``SessionEvent``s onto
the common trace dict consumed by render/compare/chat.

Mapping (dsh Session format v4, dsh 0.2.2-rc.1):

* header ``{id, cwd, createdAt, parentSession, origin}`` -> ``meta``; a header
  with ``parentSession`` is a sub-agent Session and becomes an ``agents`` entry
  of its root, never a separate report.
* ``tool/call {callId, name, arguments}`` + ``tool/result {message.toolCallId,
  message.content, message.isError, meta}`` -> ``tools`` (paired by call id;
  ``read``/``write``/``edit`` keep their ``file_path``; ``read`` line spans come
  from ``meta.offset``/``meta.lines``/``meta.totalLines``; ``apply_patch`` is
  expanded per file like Codex patches; ``pwsh``/``bash`` feed the shell
  visible-source inference).
* ``assistant/message {usage}`` -> ``billing`` / ``context_timeline``:
  ``inputTokens`` (uncached), ``cacheReadTokens``, ``cacheWriteTokens``,
  ``outputTokens``; the model comes from the latest ``request/header``.
* ``user/message`` with ``source.kind == "user"`` and ``command/run`` (slash
  commands) -> human ``prompts``; injected context (runtime-context,
  skill-catalog, agent-message, subagent-settled ...) is not a human prompt.
  ``agent/inbox/spliced`` re-delivers queued messages, so prompts and usage are
  de-duplicated by message id; ``assistant/attempt`` (failed request, no usage)
  is not a request.
* ``subagent`` tool calls are dispatches; the child id is read from the tool's
  fixed result template ``started subagent <id>`` and must be confirmed by a
  ``subagent/catalog`` event of the parent or the child's ``parentSession``.
* ``compaction/*`` events and surface replacements -> ``markers`` (compact).
* Pipeline ``skill`` calls (``a2h-*``) open stages exactly as for DevEco.

Not mapped: assistant stream timing (``stream``), plugin records, jobs and
todos (kept only as ordinary tool calls), file effects of shell commands
(opaque, as for every adapter).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

from .. import stage_signals
from . import claude as common
from . import codex as codex_common
from . import deveco as dv
from . import dsh_source as src
from .base import SessionCandidate

FORMAT = "dsh"
SUPPORTS_LIVE = False

TOOL_MAP = {
    "read": "Read", "write": "Write", "edit": "Edit", "read_image": "ReadImage",
    "bash": "Bash", "pwsh": "PowerShell", "glob": "Glob", "grep": "Grep",
    "subagent": "Agent", "subagent_fork": "Agent", "skill": "Skill",
    "todo_write": "TodoWrite", "web_search": "WebSearch", "web_fetch": "WebFetch",
    "send_message": "SendMessage", "list_agents": "ListAgents", "interrupt_agent": "InterruptAgent",
    "job_output": "JobOutput", "job_list": "JobList", "job_kill": "JobKill",
    "workflow": "Workflow", "str_replace_editor": "StrReplaceEditor",
}
DISPATCH_TOOLS = ("subagent", "subagent_fork")
HUMAN_SOURCES = ("user",)


# --------------------------------------------------------------------------- #
# Adapter contract
# --------------------------------------------------------------------------- #

def default_root():
    return src.default_root()


def is_session(path):
    if not isinstance(path, str):
        return False
    gen = src.resolve(path)
    return bool(gen) and src.peek_header(gen) is not None


def dsh_log_of(target):
    """A dsh generation file for a file / session-directory target, else None (cheap header check)."""
    gen = src.resolve(target) if isinstance(target, str) else None
    return gen if gen and src.peek_header(gen) is not None else None


def iter_sessions(root):
    """Root Sessions only (sub-agents appear inside their root's report)."""
    gens = [src.select_generation(sdir) for sdir in src.iter_session_dirs(root)]
    for gen, header in src.peek_headers([g for g in gens if g]).items():
        if header.get("parentSession"):
            continue
        try:
            st = os.stat(gen)
        except OSError:
            continue
        cwd = header.get("cwd") or ""
        yield SessionCandidate(mtime=st.st_mtime, path=gen,
                               project=os.path.basename(cwd.rstrip("\\/")) or "dsh-session",
                               size=st.st_size, format=FORMAT, session_id=header["id"])


def extract(path, sessions_root=None):
    header, events, gen = src.read_session(path)
    root = sessions_root or src.root_of(gen)
    children = src.descendants(root, header["id"])
    return _parse(header, events, gen, children)


# --------------------------------------------------------------------------- #
# One Session
# --------------------------------------------------------------------------- #

def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _read_entry(entry, inp, meta, output):
    if isinstance(meta, dict) and isinstance(meta.get("lines"), list) and meta["lines"]:
        start = meta.get("offset") if isinstance(meta.get("offset"), int) else 1
        count = len(meta["lines"]) if "fixtureTruncated_lines" not in meta else meta["fixtureTruncated_lines"]
        entry["rstart"], entry["rlines"] = start, count
        if isinstance(meta.get("totalLines"), int):
            entry["rtotal"] = meta["totalLines"]
        return
    spans = dv._read_spans(output)
    if spans:
        entry["_rspans"] = spans
        entry["rlines"] = sum(c for _, c in spans)
        entry["rstart"] = spans[0][0]
        entry["rtotal"] = spans[-1][0] + spans[-1][1] - 1


def _lines(text):
    return text.count("\n") + 1 if isinstance(text, str) and text else 0


def _abs(path, cwd):
    """A tool's relative path resolved against the Session cwd (dsh resolves it there), in the cwd's own flavour."""
    if not isinstance(path, str) or not path or not cwd:
        return path
    import ntpath
    import posixpath
    windows = bool(ntpath.splitdrive(cwd)[0]) or "\\" in cwd
    flavour = ntpath if windows else posixpath
    if flavour.isabs(path) or (windows and ntpath.splitdrive(path)[0]):
        return path
    return flavour.normpath(flavour.join(cwd, path))


def _tool_rows(seq, idx, ts, name, inp, call_id, output, ok, dur_ms, meta, cwd):
    """One recorded call -> trace tool rows (``apply_patch`` -> one row per file)."""
    from ..audit_events import observation
    display = TOOL_MAP.get(name, name)

    def base(display_name, brief):
        return {"seq": seq, "idx": idx, "ts": ts, "name": display_name, "brief": brief,
                "ok": ok is not False, "dur_ms": dur_ms, "tuid": call_id,
                "result": (output or "").strip()[:220], "_inp": inp,
                "audit": observation(display_name, inp, output, ok, call=call_id, idx=idx, ts=ts)}

    if name == "apply_patch":
        patch = inp.get("input") if isinstance(inp, dict) else None
        rows = []
        for row in codex_common._patch_entries(patch if isinstance(patch, str) else "", cwd):
            entry = base(row.pop("name"), row.pop("brief"))
            entry.update(row)
            rows.append(entry)
        return rows or [base("ApplyPatch", "")]
    fp = inp.get("file_path") if isinstance(inp, dict) else None
    brief = _abs(fp, cwd) if display in ("Read", "Write", "Edit", "ReadImage") and isinstance(fp, str) else \
        common.brief_tool_target(display, inp)
    entry = base(display, brief)
    if display == "Read":
        _read_entry(entry, inp, meta, output)
    elif display == "Write" and isinstance(inp, dict):
        wl = _lines(inp.get("content"))
        entry["wlines"], entry["wevent"] = wl, ["set", wl]
    elif display == "Edit" and isinstance(inp, dict):
        nl, ol = _lines(inp.get("new_string")), _lines(inp.get("old_string"))
        entry["wlines"], entry["wevent"] = nl, ["delta", nl - ol]
    elif display in ("Bash", "PowerShell") and isinstance(inp, dict) and isinstance(inp.get("command"), str):
        workdir = inp.get("workdir") or cwd
        visible = common._infer_visible_source_lines(display, {"command": inp["command"]}, output, workdir)
        if visible:
            entry["_visible_source_lines"] = visible
        probed = common._script_probed_paths(display, {"command": inp["command"]}, workdir)
        if probed:
            entry["_probed_paths"] = probed
    elif display == "Skill" and isinstance(inp, dict):
        entry["skill"] = inp.get("name") or inp.get("skill")
    elif display == "Agent" and isinstance(inp, dict):
        entry["agent_type"] = "subagent_fork" if name == "subagent_fork" else "subagent"
        entry["agent_desc"] = str(inp.get("description") or "")[:240]
        entry["agent_prompt"] = str(inp.get("prompt") or "")[:800]
    return [entry]


def _session_walk(header, events):
    """Calls, prompts, usage and activity of one Session, in log order."""
    cwd = header.get("cwd") or ""
    results = {}
    for ev in events:
        if ev.get("type") == "tool/result":
            msg = (ev.get("data") or {}).get("message") or {}
            cid = msg.get("toolCallId")
            if cid:
                results[cid] = ev
    seen_msgs = set()      # user / assistant 消息 id:inbox 拼接会重放同一条消息
    commands = {}          # commandId → (seq, 开始毫秒)
    out = {"tools": [], "prompts": [], "usage": [], "texts": [], "markers": [],
           "act": [], "dispatches": [], "turn_end": None, "model": None, "reasoning_chars": 0,
           "text_chars": 0, "tool_chars": 0, "first": header.get("createdAt"), "last": header.get("createdAt"),
           "skills": [], "context": []}
    model = None
    for ev in events:
        t, d, ms = ev.get("type"), ev.get("data") or {}, ev.get("time")
        if isinstance(ms, (int, float)):
            out["first"] = ms if out["first"] is None else min(out["first"], ms)
            out["last"] = ms if out["last"] is None else max(out["last"], ms)
        ts = src.iso(ms)
        seq = ev.get("seq")
        if t == "request/header":
            model = ((d.get("header") or {}).get("config") or {}).get("model") or model
            out["model"] = out["model"] or model
        elif t == "subagent/descriptor":
            out["model"] = out["model"] or d.get("agentModel")
        elif t == "user/message":
            source = d.get("source") or {}
            if d.get("id") and ("u", d["id"]) in seen_msgs:
                continue
            seen_msgs.add(("u", d.get("id")))
            if source.get("kind") in HUMAN_SOURCES:
                text = src.text_of(d.get("content"))
                if text.strip():
                    out["prompts"].append({"idx": seq, "ts": ts, "wait_ms": 0, "kind": "human",
                                           "text": " ".join(text.split())[:400]})
        elif t == "command/run":
            # 斜杠命令:人敲的(source.kind=user)算人工输入;run → done 期间命令在跑,算活动
            if (d.get("source") or {}).get("kind", "user") in HUMAN_SOURCES:
                text = ("/%s%s" % (d.get("name") or "", d.get("args") or "")).strip()
                out["prompts"].append({"idx": seq, "ts": ts, "wait_ms": 0, "kind": "human", "text": text[:400]})
            if d.get("commandId") and isinstance(ms, (int, float)):
                commands[d["commandId"]] = (seq, float(ms))
        elif t == "command/done":
            started = commands.pop(d.get("commandId"), None)
            if started and isinstance(ms, (int, float)) and ms > started[1]:
                out["act"].append((started[0], started[1], float(ms)))
        elif t == "assistant/message":
            msg = d.get("message") or {}
            mid = msg.get("id") or d.get("id")
            if mid and ("a", mid) in seen_msgs:
                continue
            seen_msgs.add(("a", mid))
            for block in msg.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "reasoning":
                    out["reasoning_chars"] += len(block.get("text") or "")
                elif block.get("type") == "text":
                    out["text_chars"] += len(block.get("text") or "")
                    if (block.get("text") or "").strip():
                        out["texts"].append(block["text"].strip())
                elif block.get("type") == "tool-call":
                    out["tool_chars"] += len(block.get("arguments") or "")
            usage = d.get("usage")
            if isinstance(usage, dict):
                out["usage"].append((ts, model or out["model"], usage))
            stream = d.get("stream") or []
            times = [r.get("time") or r.get("time0") for r in stream if isinstance(r, dict)]
            times = [x for x in times if isinstance(x, (int, float))]
            if times and isinstance(ms, (int, float)) and ms > min(times):
                out["act"].append((seq, float(min(times)), float(ms)))
        elif t == "tool/call":
            name = d.get("name") or ""
            inp = src.tool_arguments(d.get("arguments"))
            res = results.get(d.get("callId"))
            rdata = (res or {}).get("data") or {}
            rmsg = rdata.get("message") or {}
            output = src.text_of(rmsg.get("content"))
            ok = None if res is None else not bool(rmsg.get("isError"))
            dur = None
            if res is not None and isinstance(res.get("time"), (int, float)) and isinstance(ms, (int, float)):
                dur = max(0, int(res["time"] - ms))
                if name not in DISPATCH_TOOLS and res["time"] > ms:
                    out["act"].append((seq, float(ms), float(res["time"])))
            rows = _tool_rows(len(out["tools"]), seq, ts, name, inp, d.get("callId"), output, ok, dur,
                              rdata.get("meta"), cwd)
            for row in rows:
                row["_done"] = res is not None
                if res is not None and isinstance(res.get("time"), (int, float)):
                    row["_end_ms"] = float(res["time"])
            out["tools"].extend(rows)
            if name in DISPATCH_TOOLS:
                out["dispatches"].append({"call_id": d.get("callId"), "child": src.started_child(output),
                                          "ts": ts, "desc": str(inp.get("description") or ""),
                                          "prompt": str(inp.get("prompt") or ""), "row": rows[-1]})
        elif t in ("compaction/start", "compaction/end") or (
                t in ("user/message", "assistant/message", "tool/result", "system/message")
                and isinstance(ev.get("surfaceOp"), dict) and ev["surfaceOp"].get("op") == "replace"):
            if t != "compaction/end":
                out["markers"].append({"idx": seq, "ts": ts, "kind": "compact"})
        elif t == "turn/end":
            out["turn_end"] = (d.get("reason") or {}).get("kind")
    for i, row in enumerate(out["tools"]):
        row["seq"] = i
    return out


def _bill(billing, timeline, usage_rows, default_model):
    for ts, model, u in usage_rows:
        key = model or default_model or "unknown"
        b = billing.setdefault(key, {"req": 0, "inp": 0, "cread": 0, "cw5": 0, "cw1h": 0, "out": 0})
        inp, cread, cw, out = _num(u.get("inputTokens")), _num(u.get("cacheReadTokens")), \
            _num(u.get("cacheWriteTokens")), _num(u.get("outputTokens"))
        b["req"] += 1
        b["inp"] += inp
        b["cread"] += cread
        b["cw5"] += cw           # dsh 只报一个缓存写入总数(没有 5m/1h 之分),与 DevEco 同归 cw5
        b["out"] += out
        if timeline is not None:
            timeline.append({"ts": ts, "ctx": inp + cread + cw, "out": out, "inp": inp,
                             "cread": cread, "cwrite": cw})


def _out_split(walk, output_tokens):
    """DeepSeek reports reasoning inside outputTokens; split by visible character shares."""
    th, tx, tu = walk["reasoning_chars"], walk["text_chars"], walk["tool_chars"]
    total = th + tx + tu
    if not total:
        return {"thinking": 0, "text": output_tokens, "tool": 0}
    thinking = int(round(output_tokens * th / total))
    text = int(round(output_tokens * tx / total))
    return {"thinking": thinking, "text": text, "tool": max(0, output_tokens - thinking - text)}


def _confirmed_children(walk, events, children):
    """Dispatch rows whose child id is confirmed by the catalog or by the child header."""
    catalog = src.catalog_children(events)
    child_ids = {h["id"] for h, _ in children}
    confirmed = {}
    for disp in walk["dispatches"]:
        cid = disp["child"]
        if cid and (cid in catalog or cid in child_ids):
            confirmed[cid] = disp
    return confirmed, catalog


# --------------------------------------------------------------------------- #
# Whole trace
# --------------------------------------------------------------------------- #

def _parse(header, events, gen, children):
    cwd = header.get("cwd") or ""
    main = _session_walk(header, events)
    tools, prompts = main["tools"], main["prompts"]
    model = main["model"]
    billing, timeline = {}, []
    _bill(billing, timeline, main["usage"], model)
    main_out = sum(_num(u.get("outputTokens")) for _, _, u in main["usage"])

    # ---- stages:与 DevEco 同一套信号(管线 skill、Workflow、mark-stage),统一走 stage_signals
    points = [(ev.get("seq"), ev.get("time") if isinstance(ev.get("time"), (int, float)) else None)
              for ev in events if isinstance(ev.get("seq"), int)]
    human = [p for p in prompts if p.get("kind") == "human"]
    segs = stage_signals.segment(
        [(i, ms / 1000.0 if ms is not None else None) for i, ms in points] or [(0, None)],
        marks=dv._stage_marks(tools, cwd, main["first"], gen),
        signals=dv._stage_signals(tools), human=[p["idx"] for p in human],
        resumes=[p["idx"] for p in human if stage_signals.is_resume_request(p.get("text"))],
        workflows=dv._stage_workflows(tools))
    stages = dv._build_stages(segs, points, None)
    for t in tools:
        s = dv._stage_of_idx(stages, t["idx"] if isinstance(t["idx"], int) else 0)
        t["stage"], t["seg"] = s["stage"], s["id"]
        s["tool_counts"][t["name"]] = s["tool_counts"].get(t["name"], 0) + 1
        for ch in s["children"]:
            if ch["start_idx"] <= t["idx"] <= ch["end_idx"]:
                t["subseg"] = ch["id"]
                ch["tool_counts"][t["name"]] = ch["tool_counts"].get(t["name"], 0) + 1
        if t["name"] in ("Write", "Edit") and t.get("brief") and t["brief"] not in s["artifacts"]:
            s["artifacts"].append(t["brief"])
        if t["name"] == "Skill" and t.get("skill") and stage_signals.normalize(t["skill"]) is None:
            s["helper_skills"].append({"idx": t["idx"], "ts": t["ts"], "skill": t["skill"]})
    for p in prompts:
        s = dv._stage_of_idx(stages, p["idx"] if isinstance(p["idx"], int) else 0)
        p["stage"], p["seg"] = s["stage"], s["id"]
        s["prompt_idxs"].append(p["idx"])
    for ev in events:
        if ev.get("type") == "assistant/message" and isinstance(ev.get("seq"), int):
            u = (ev.get("data") or {}).get("usage") or {}
            s = dv._stage_of_idx(stages, ev["seq"])
            s["output_tokens"] += _num(u.get("outputTokens"))
            s["cache_read_tokens"] += _num(u.get("cacheReadTokens"))

    # ---- sub-agents: every descendant Session is one agent entry
    by_id = {header["id"]: (header, events)}
    walks = {header["id"]: main}
    for ch, cgen in children:
        h, ev, _g = src.read_session(cgen)
        by_id[h["id"]] = (h, ev)
        walks[h["id"]] = _session_walk(h, ev)
    dispatch_of = {}
    for sid, (h, ev) in by_id.items():
        confirmed, _cat = _confirmed_children(walks[sid], ev, children)
        for cid, disp in confirmed.items():
            dispatch_of[cid] = (sid, disp)
    agents, sub_act = [], []
    for ch, _cgen in children:
        h, ev = by_id[ch["id"]]
        w = walks[ch["id"]]
        descriptor = next((e.get("data") for e in ev if e.get("type") == "subagent/descriptor"), {}) or {}
        parent_sid, disp = dispatch_of.get(h["id"], (h.get("parentSession"), None))
        created, updated = src.iso(h.get("createdAt")), src.iso(w["last"])
        stage = dv._stage_of_time(stages, created)
        for _seq, s0, s1 in w["act"]:
            sub_act.append((stage["id"], s0, s1))
        out_tokens = sum(_num(u.get("outputTokens")) for _, _, u in w["usage"])
        child_model = w["model"] or descriptor.get("agentModel") or model
        _bill(billing, None, w["usage"], child_model)
        skills, skill_calls = {}, []
        for t in w["tools"]:
            if t["name"] == "Skill" and t.get("skill"):
                skills[t["skill"]] = skills.get(t["skill"], 0) + 1
                skill_calls.append({"skill": t["skill"], "ts": t.get("ts"), "ok": t.get("ok"), "dur_ms": t.get("dur_ms")})
        label = descriptor.get("label") or (disp or {}).get("desc") or h["id"]
        status = {"completed": "completed", "aborted": "interrupted", "error": "error",
                  "interrupted": "interrupted"}.get(w["turn_end"] or "", w["turn_end"] or "unknown")
        entry = {
            "agent_id": "subagent:" + h["id"],
            "audit_tools": [{**t["audit"], "source": "dsh:" + h["id"]} for t in w["tools"]],
            "type": descriptor.get("provider") or ("subagent" if h.get("origin") == "subagent" else "session"),
            "desc": str(label)[:240],
            "parent": parent_sid,
            "wf_run": None, "wf_name": None, "wf_phase": None,
            "tuid": (disp or {}).get("call_id"),
            "stage": stage["stage"], "seg": stage["id"],
            "start_ts": created, "end_ts": updated,
            "dur_ms": common.ms_between(created, updated),
            "output_tokens": out_tokens,
            "tool_uses": len(w["tools"]),
            "tool_counts": dict(Counter(t["name"] for t in w["tools"])),
            "status": status,
            "aborted": "interrupted" if status == "interrupted" else None,
            "model": child_model,
            "result": (w["texts"][-1] if w["texts"] else "")[:300],
            "skills": skills, "skill_calls": skill_calls,
            "out_split": _out_split(w, out_tokens),
            "prompt_excerpt": ((disp or {}).get("prompt") or (w["prompts"][0]["text"] if w["prompts"] else ""))[:800],
            "_prompt": "", "_probed": [], "_reads": [], "_writes": [],
            "_read_lines": {}, "_read_iv": {}, "_read_total": {}, "_read_sources": {},
            "_write_lines": {}, "_write_events": [], "_blame_events": [],
        }
        dv._aggregate_reads(entry, w["tools"])
        for t in w["tools"]:
            p = t.get("brief")
            if t["name"] in ("Write", "Edit") and p and p.endswith(".ets") and t.get("ok") is not False:
                inp = t.get("_inp") or {}
                bev = t.get("bevent")
                if bev is None:
                    if t["name"] == "Write" and inp.get("content") is not None:
                        bev = ("write", inp["content"])
                    elif t["name"] == "Edit" and inp.get("old_string"):
                        bev = ("edits", [(inp.get("old_string") or "", inp.get("new_string") or "",
                                          bool(inp.get("replace_all")))])
                    else:
                        bev = ("opaque", None)
                entry["_blame_events"].append((t.get("ts") or "", p, bev[0], bev[1]))
        agents.append(entry)
        if disp is not None:
            disp["row"]["agent_id"] = entry["agent_id"]
    for a in agents:
        for s in stages:
            if s["id"] == a["seg"]:
                s["agent_count"] += 1
                break
    for agent in agents:
        agent["abort_explicit"] = bool(agent.get("aborted"))

    # ---- activity
    main_act = []
    for seq, s0, s1 in main["act"]:
        stg = dv._stage_of_idx(stages, seq if isinstance(seq, int) else 0)
        main_act.append((stg["id"], s0, s1))
    all_act = main_act + sub_act
    merged_global, global_active = dv._union_ms([(s0, s1) for _, s0, s1 in all_act])
    for s in stages:
        _m, act = dv._union_ms([(s0, s1) for sid, s0, s1 in all_act if sid == s["id"]])
        s["active_ms"] = act

    # ---- lineage (classification root = HarmonyOS project root when it can be found)
    write_paths = [p for a in agents for p in a.get("_writes") or []]
    write_paths += [t["brief"] for t in tools if t["name"] in ("Write", "Edit") and t.get("brief")]
    target_root = dv._find_harmony_root(write_paths)
    lineage = common.build_lineage(agents, tools, target_root or cwd)
    if lineage and target_root:
        lineage["cwd"] = cwd

    split = _out_split(main, main_out)
    for a in agents:
        for k in ("thinking", "text", "tool"):
            split[k] += (a.get("out_split") or {}).get(k, 0)
    started_at = src.iso(min([x for x in [main["first"]] + [walks[h["id"]]["first"] for h, _ in children] if x]))
    ended_at = src.iso(max([x for x in [main["last"]] + [walks[h["id"]]["last"] for h, _ in children] if x]))
    meta = {
        "source_file": os.path.abspath(gen),
        "schema_version": "dsh-session-v%s" % header.get("version"),
        "session_format": FORMAT,
        "session_id": header["id"],
        "cc_version": "format v%s" % header.get("version"),
        "cwd": cwd,
        "model": model,
        "started_at": started_at,
        "ended_at": ended_at,
        "record_count": len(events) + sum(len(by_id[h["id"]][1]) for h, _ in children),
    }
    totals = {
        "duration_ms": common.ms_between(started_at, ended_at),
        "active_ms": global_active,
        "tool_calls": len(tools),
        "agent_calls": len(main["dispatches"]),
        "subagent_transcripts": len(agents),
        "main_output_tokens": main_out,
        "subagent_output_tokens": sum(a["output_tokens"] for a in agents),
        "aborted_agents": sum(1 for a in agents if a.get("aborted")),
        "interrupted_output_tokens": sum(a["output_tokens"] for a in agents if a.get("abort_explicit")),
        "waste_output_tokens": None,
        "output_split": {k: int(v) for k, v in split.items()},
        "user_prompts": sum(1 for p in prompts if p.get("kind") == "human"),
        "program_prompts": sum(1 for p in prompts if p.get("kind") == "program"),
        "files_touched": len({t.get("brief") for t in tools if t["name"] in ("Write", "Edit") and t.get("brief")}),
        "compactions": len(main["markers"]),
    }
    for t in tools:
        for key in ("_inp", "_visible_source_lines", "_probed_paths", "_done", "_end_ms"):
            t.pop(key, None)
    for a in agents:
        for key in ("_prompt", "_reads", "_writes", "_read_lines", "_write_lines", "_read_iv", "_read_total",
                    "_read_sources", "_write_events", "_probed", "_blame_events"):
            a.pop(key, None)
    audit_tools = [{**t["audit"], "stage": t.get("stage"), "segment": t.get("seg"),
                    "source": os.path.abspath(gen), "message_index": t.get("idx")} for t in tools]
    return {"meta": meta, "totals": totals, "stages": stages, "audit_tools": audit_tools,
            "tools": tools, "agents": agents, "prompts": prompts, "markers": main["markers"],
            "context_timeline": timeline, "billing": billing, "lineage": lineage, "workflows": [],
            "activity_intervals": [[src.iso(s0), src.iso(s1)] for s0, s1 in merged_global]}


# --------------------------------------------------------------------------- #
# Standalone CLI
# --------------------------------------------------------------------------- #

def resolve_target(target, root=None):
    """File / session directory / session id prefix / project fragment -> generation path."""
    gen = src.resolve(target) if isinstance(target, str) else None
    if gen:
        return gen
    root = root or default_root()
    rows = sorted(iter_sessions(root), key=lambda r: r.mtime, reverse=True)
    bare = lambda sid: sid[len("session-"):] if sid.startswith("session-") else sid  # noqa: E731
    hits = [r.path for r in rows if r.session_id.startswith(target) or bare(r.session_id).startswith(target)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError("dsh session id prefix is ambiguous (%d sessions): %s" % (len(hits), target))
    proj = [r.path for r in rows if target.lower() in r.project.lower()]
    if proj:
        return proj[0]
    raise ValueError("no dsh session matches %r under %s" % (target, root))


def main():
    ap = argparse.ArgumentParser(prog="migloop.adapters.dsh", description="dsh session log -> MigLoop trace")
    ap.add_argument("target", nargs="?", help="generation file | session dir | session id prefix | project fragment")
    ap.add_argument("--root", default=None, help="dsh sessions root (default $DSH_HOME/sessions or ~/.dsh/sessions)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    root = args.root or default_root()
    if args.list or not args.target:
        for row in sorted(iter_sessions(root), key=lambda r: r.mtime, reverse=True):
            print("%-48s %-20s %s" % (row.session_id, row.project[:20], row.path))
        return
    trace = extract(resolve_target(args.target, root), sessions_root=args.root)
    json.dump({"meta": trace["meta"], "totals": trace["totals"]}, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
