# -*- coding: utf-8 -*-
"""Incremental live monitor for a growing Claude Code session.

The offline extractor remains the source of truth for a finalized report.  This
module deliberately solves a different problem: keep a cheap, continuously
updated progress view while the main/session and sub-agent JSONL files are
still being appended.

Every JSONL stream owns a byte cursor.  A poll reads only bytes written after
that cursor, reduces the new records into an aggregate state, and checkpoints
both state and cursors.  Restarting the monitor therefore resumes at the last
complete byte instead of replaying the whole session.
"""

from __future__ import annotations

import argparse
import base64
import collections
import copy
import datetime as _dt
import hashlib
import html
import json
import os
import re
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..adapters import claude as extract_session
from ..chat import provider as chat_provider


CACHE_SCHEMA = 3
_AGENT_FILE_RE = re.compile(r"agent-([^.\\/]+)\.jsonl$", re.IGNORECASE)
_PIPELINE_SKILLS = set(extract_session.PIPELINE_SKILLS)
_TERMINAL_WORKFLOW_STATES = {"done", "completed", "failed", "error", "cancelled", "canceled"}


def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _parse_ts(value):
    return extract_session.parse_ts(value)


def _atomic_write(path, content, binary=False):
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d-%d" % (path, os.getpid(), threading.get_ident())
    mode = "wb" if binary else "w"
    kwargs = {} if binary else {"encoding": "utf-8", "newline": ""}
    with open(tmp, mode, **kwargs) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _jsonable(value):
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, collections.Counter):
        return dict(value)
    if isinstance(value, collections.deque):
        return list(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _safe_rel(path, root):
    if not path:
        return ""
    p = os.path.abspath(path)
    if root:
        try:
            rel = os.path.relpath(p, root)
            if rel != os.pardir and not rel.startswith(os.pardir + os.sep):
                return rel.replace(os.sep, "/")
        except (OSError, ValueError):
            pass
    return p.replace(os.sep, "/")


def _tool_result_text(block, record):
    return extract_session.result_text(block, record.get("toolUseResult"))


def _message_text(message):
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    return ""


def _is_terminal_assistant_message(message):
    """Recognize both current and legacy Claude Code terminal messages.

    Older sub-agent transcripts often omit ``stop_reason`` on the final
    assistant record.  A non-empty text-only assistant message is nevertheless
    terminal; tool-calling turns contain a ``tool_use`` block and must remain
    running.  Explicit interruption/API-error text is handled before this
    helper is consulted.
    """
    if not isinstance(message, dict):
        return False
    stop = message.get("stop_reason")
    if stop in ("end_turn", "stop_sequence"):
        return True
    if stop is not None:
        return False
    content = message.get("content")
    has_tool_use = isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_use"
        for block in content
    )
    return bool(_message_text(message).strip()) and not has_tool_use


class IntervalIndex:
    """Per-file union of inclusive line intervals.

    ``add`` returns the number of newly visible lines, so totals are updated
    without rescanning every previous span.
    """

    def __init__(self, data=None):
        self.by_path = {}
        for path, spans in (data or {}).items():
            self.by_path[path] = [[int(a), int(b)] for a, b in spans]

    def add(self, path, spans):
        incoming = []
        for start, count in spans or []:
            try:
                start, count = int(start), int(count)
            except (TypeError, ValueError):
                continue
            if count > 0:
                incoming.append([start, start + count - 1])
        if not incoming:
            return 0
        old = self.by_path.get(path, [])
        old_total = sum(b - a + 1 for a, b in old)
        merged = sorted(old + incoming)
        out = []
        for start, end in merged:
            if not out or start > out[-1][1] + 1:
                out.append([start, end])
            else:
                out[-1][1] = max(out[-1][1], end)
        self.by_path[path] = out
        return sum(b - a + 1 for a, b in out) - old_total

    def line_count(self, path=None):
        if path is not None:
            return sum(b - a + 1 for a, b in self.by_path.get(path, []))
        return sum(self.line_count(p) for p in self.by_path)

    def to_json(self):
        return self.by_path


def _new_stream(path, kind, agent_id=None):
    return {
        "path": os.path.abspath(path),
        "kind": kind,
        "agent_id": agent_id,
        "offset": 0,
        "pending_b64": "",
        "records": 0,
        "tool_uses": 0,
        "tool_counts": {},
        "pending_tools": {},
        "active_usage": {},
        "output_tokens": 0,
        "input_tokens": 0,
        "cache_read_tokens": 0,
        "read_files": set(),
        "write_files": set(),
        "status": "running" if kind == "agent" else "idle",
        "last_ts": None,
        "model": None,
        "desc": "",
        "agent_type": None,
        "stage": "session",
        "head_sig": None,
    }


def _restore_stream(data):
    stream = dict(data)
    stream["read_files"] = set(stream.get("read_files") or [])
    stream["write_files"] = set(stream.get("write_files") or [])
    stream.setdefault("pending_tools", {})
    stream.setdefault("active_usage", {})
    stream.setdefault("tool_counts", {})
    stream.setdefault("pending_b64", "")
    return stream


class IncrementalSessionMonitor:
    """Incrementally reduce an active session directory into live progress."""

    def __init__(self, jsonl_path, cache_dir=None, poll_interval=10.0,
                 checkpoint_interval=10.0, reset_cache=False):
        self.jsonl_path = os.path.abspath(jsonl_path)
        self.session_dir = os.path.splitext(self.jsonl_path)[0]
        self.poll_interval = max(0.2, float(poll_interval))
        self.checkpoint_interval = max(1.0, float(checkpoint_interval))
        sid = os.path.splitext(os.path.basename(self.jsonl_path))[0]
        cache_dir = cache_dir or os.path.join(os.path.expanduser("~"), ".migloop", "cache")
        self.cache_path = os.path.join(os.path.abspath(cache_dir), sid + ".live.json")
        if reset_cache:
            try:
                os.remove(self.cache_path)
            except FileNotFoundError:
                pass

        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.last_checkpoint = 0.0
        self.metadata_mtimes = {}
        self.workflows = {}
        self.agent_workflow = {}
        self.intervals = IntervalIndex()
        self.streams = {}
        self.events = collections.deque(maxlen=80)
        self.source_paths = set()
        self.write_files = set()
        self.inventory = None
        self.android_root = None
        self.state = self._fresh_state()
        self.loaded_checkpoint = False
        self._load_checkpoint()

    def _fresh_state(self):
        return {
            "schema": CACHE_SCHEMA,
            "session_id": os.path.splitext(os.path.basename(self.jsonl_path))[0],
            "source_file": self.jsonl_path,
            "cwd": None,
            "model": None,
            "started_at": None,
            "ended_at": None,
            "version": 0,
            "last_update": None,
            "last_error": None,
            "status": "starting",
            "records": 0,
            "user_prompts": 0,
            "tool_calls": 0,
            "output_tokens": 0,
            "input_tokens": 0,
            "cache_read_tokens": 0,
            "bytes_read_total": 0,
            "bytes_read_last": 0,
            "json_errors": 0,
            "current_stage": "session",
            "tool_counts": {},
            "coverage": {
                "root": None, "files": 0, "lines": 0,
                "code_files": 0, "code_lines": 0,
                "total_files": None, "total_lines": None,
                "total_code_files": None, "total_code_lines": None,
            },
        }

    # ---------- persistence ----------
    def _checkpoint_payload(self):
        return {
            "schema": CACHE_SCHEMA,
            "source_file": self.jsonl_path,
            "state": self.state,
            "streams": self.streams,
            "intervals": self.intervals.to_json(),
            "events": list(self.events),
            "source_paths": self.source_paths,
            "write_files": self.write_files,
            "android_root": self.android_root,
            "inventory": self.inventory,
            "workflows": self.workflows,
            "agent_workflow": self.agent_workflow,
            "metadata_mtimes": self.metadata_mtimes,
            "saved_at": _now_iso(),
        }

    def _load_checkpoint(self):
        try:
            with open(self.cache_path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, json.JSONDecodeError):
            return
        if data.get("schema") != CACHE_SCHEMA:
            return
        if os.path.abspath(data.get("source_file") or "") != self.jsonl_path:
            return
        streams = {}
        for path, raw in (data.get("streams") or {}).items():
            path = os.path.abspath(path)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            if size < int(raw.get("offset") or 0):
                return  # any truncation invalidates aggregate contributions
            streams[path] = _restore_stream(raw)
        self.state.update(data.get("state") or {})
        self.streams = streams
        self.intervals = IntervalIndex(data.get("intervals") or {})
        self.events = collections.deque(data.get("events") or [], maxlen=80)
        self.source_paths = set(data.get("source_paths") or [])
        self.write_files = set(data.get("write_files") or [])
        self.android_root = data.get("android_root")
        self.inventory = data.get("inventory")
        self.workflows = data.get("workflows") or {}
        self.agent_workflow = data.get("agent_workflow") or {}
        self.metadata_mtimes = {
            str(k): int(v) for k, v in (data.get("metadata_mtimes") or {}).items()
        }
        self.loaded_checkpoint = True

    def save_checkpoint(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_checkpoint < self.checkpoint_interval:
            return
        with self.lock:
            payload = json.dumps(_jsonable(self._checkpoint_payload()), ensure_ascii=False,
                                 separators=(",", ":"))
        _atomic_write(self.cache_path, payload)
        self.last_checkpoint = now

    # ---------- discovery ----------
    def _discover_stream_paths(self):
        paths = [(self.jsonl_path, "main", None)]
        sub = os.path.join(self.session_dir, "subagents")
        if os.path.isdir(sub):
            for root, _, files in os.walk(sub):
                for name in files:
                    match = _AGENT_FILE_RE.match(name)
                    if match:
                        paths.append((os.path.join(root, name), "agent", match.group(1)))
        return paths

    def _register_streams(self):
        changed = False
        for path, kind, agent_id in self._discover_stream_paths():
            path = os.path.abspath(path)
            if path not in self.streams:
                self.streams[path] = _new_stream(path, kind, agent_id)
                changed = True
                if agent_id:
                    self._event("agent", "发现子 agent %s" % agent_id[:8], agent_id=agent_id)
            if kind == "agent":
                changed = self._load_agent_meta(self.streams[path]) or changed
        return changed

    def _load_agent_meta(self, stream):
        path = stream["path"]
        meta_path = path[:-len(".jsonl")] + ".meta.json"
        try:
            st = os.stat(meta_path)
        except OSError:
            return False
        key = "meta:" + meta_path
        if self.metadata_mtimes.get(key) == st.st_mtime_ns:
            return False
        try:
            with open(meta_path, encoding="utf-8") as source:
                meta = json.load(source)
        except (OSError, json.JSONDecodeError):
            return False
        self.metadata_mtimes[key] = st.st_mtime_ns
        stream["desc"] = (meta.get("description") or stream.get("desc") or "")[:240]
        stream["agent_type"] = meta.get("agentType") or stream.get("agent_type")
        return True

    def _refresh_workflows(self):
        wdir = os.path.join(self.session_dir, "workflows")
        if not os.path.isdir(wdir):
            return False
        changed = False
        for name in sorted(os.listdir(wdir)):
            if not (name.startswith("wf_") and name.endswith(".json")):
                continue
            path = os.path.join(wdir, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            key = "wf:" + path
            if self.metadata_mtimes.get(key) == st.st_mtime_ns:
                continue
            try:
                with open(path, encoding="utf-8") as source:
                    data = json.load(source)
            except (OSError, json.JSONDecodeError):
                continue  # writer may currently be replacing this file
            self.metadata_mtimes[key] = st.st_mtime_ns
            rid = data.get("runId") or os.path.splitext(name)[0]
            wf = {
                "run_id": rid,
                "name": data.get("workflowName") or rid,
                "status": data.get("status") or "running",
                "duration_ms": data.get("durationMs"),
                "agent_count": data.get("agentCount"),
                "tokens": data.get("totalTokens"),
                "tool_calls": data.get("totalToolCalls"),
            }
            self.workflows[rid] = wf
            for item in data.get("workflowProgress") or []:
                if not isinstance(item, dict) or item.get("type") != "workflow_agent":
                    continue
                aid = item.get("agentId")
                if not aid:
                    continue
                self.agent_workflow[aid] = {
                    "run_id": rid,
                    "workflow": wf["name"],
                    "label": item.get("label") or "",
                    "phase": item.get("phaseTitle") or "",
                    "state": item.get("state") or "running",
                    "model": item.get("model"),
                }
            changed = True
        if changed:
            self._apply_workflow_statuses()
        return changed

    def _apply_workflow_statuses(self):
        by_agent = {s.get("agent_id"): s for s in self.streams.values() if s.get("agent_id")}
        for aid, info in self.agent_workflow.items():
            stream = by_agent.get(aid)
            if stream is None:
                # Workflow metadata may appear before its transcript file.
                continue
            stream["desc"] = (info.get("label") or stream.get("desc") or "")[:240]
            stream["stage"] = "wf:" + (info.get("workflow") or "workflow")
            stream["model"] = info.get("model") or stream.get("model")
            state = (info.get("state") or "running").lower()
            if state in ("done", "completed"):
                stream["status"] = "completed"
            elif state in ("failed", "error"):
                stream["status"] = "failed"
            elif state in ("cancelled", "canceled"):
                stream["status"] = "interrupted"
            else:
                stream["status"] = "running"

    # ---------- incremental I/O ----------
    def _head_signature(self, path):
        try:
            if os.path.getsize(path) < 128:
                return None
            with open(path, "rb") as source:
                return hashlib.sha1(source.read(128)).hexdigest()
        except OSError:
            return None

    def _read_new_records(self, stream):
        path = stream["path"]
        try:
            size = os.path.getsize(path)
        except OSError:
            return [], 0, False
        if size < int(stream.get("offset") or 0):
            return [], 0, True
        sig = self._head_signature(path)
        if stream.get("head_sig") and sig and stream["head_sig"] != sig:
            return [], 0, True
        if sig and not stream.get("head_sig"):
            stream["head_sig"] = sig
        offset = int(stream.get("offset") or 0)
        if size == offset:
            return [], 0, False
        with open(path, "rb") as source:
            source.seek(offset)
            fresh = source.read()
        stream["offset"] = offset + len(fresh)
        pending = base64.b64decode(stream.get("pending_b64") or "")
        data = pending + fresh
        parts = data.split(b"\n")
        tail = parts.pop()
        records = []
        errors = 0
        for raw in parts:
            raw = raw.rstrip(b"\r")
            if not raw.strip():
                continue
            try:
                records.append(json.loads(raw.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                errors += 1
        # A finalized JSONL occasionally lacks a trailing newline.  If the tail
        # already parses, consume it now; otherwise retain exact bytes.
        if tail.strip():
            try:
                records.append(json.loads(tail.decode("utf-8")))
                tail = b""
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        stream["pending_b64"] = base64.b64encode(tail).decode("ascii") if tail else ""
        self.state["json_errors"] += errors
        return records, len(fresh), False

    def _reset_for_replay(self):
        self.intervals = IntervalIndex()
        self.streams = {}
        self.events = collections.deque(maxlen=80)
        self.source_paths = set()
        self.write_files = set()
        self.inventory = None
        self.android_root = None
        self.workflows = {}
        self.agent_workflow = {}
        self.metadata_mtimes = {}
        self.state = self._fresh_state()
        self.loaded_checkpoint = False

    # ---------- reducer ----------
    def _event(self, kind, text, ts=None, **extra):
        event = {"kind": kind, "text": text, "ts": ts or _now_iso()}
        event.update(extra)
        self.events.append(event)

    def _update_usage(self, stream, message):
        usage = message.get("usage") if isinstance(message, dict) else None
        model = message.get("model") if isinstance(message, dict) else None
        if not isinstance(usage, dict) or (model or "").startswith("<"):
            return
        mid = message.get("id") or "anon:%d" % stream["records"]
        latest = {
            "out": int(usage.get("output_tokens") or 0),
            "inp": int(usage.get("input_tokens") or 0),
            "cache": int(usage.get("cache_read_input_tokens") or 0),
        }
        previous = stream["active_usage"].get(mid) or {"out": 0, "inp": 0, "cache": 0}
        for key, state_key in (("out", "output_tokens"), ("inp", "input_tokens"),
                               ("cache", "cache_read_tokens")):
            delta = latest[key] - int(previous.get(key) or 0)
            stream[state_key] += delta
            self.state[state_key] += delta
        stream["active_usage"][mid] = latest
        while len(stream["active_usage"]) > 1024:
            stream["active_usage"].pop(next(iter(stream["active_usage"])))
        # Keep the latest value for every message id.  Claude Code can write
        # several records for one streamed message, including a repeated final
        # record; dropping the slot at stop_reason would count that final usage
        # twice if another copy arrives.

    def _normalize_source(self, raw):
        if not isinstance(raw, str) or not raw.strip():
            return None
        bases = [self.state.get("cwd")] if self.state.get("cwd") else []
        resolved = extract_session._resolve_source_path(raw, bases)
        if resolved:
            return resolved
        value = raw.replace("\\", os.sep).replace("/", os.sep)
        if not os.path.isabs(value) and self.state.get("cwd"):
            value = os.path.join(self.state["cwd"], value)
        value = os.path.abspath(value)
        if os.path.isfile(value) and value.lower().endswith(extract_session._ANDROID_EXT):
            return value.replace(os.sep, "/")
        return None

    def _add_visible(self, stream, path, spans):
        path = path.replace("\\", "/")
        coverage = self.state.get("coverage") or {}
        inventory = (self.inventory or {}).get("inventory") or {}
        if inventory and self.android_root:
            rel = _safe_rel(path, self.android_root)
            max_lines = inventory.get(rel)
            if max_lines is None:
                # Keep out-of-denominator evidence for diagnostics without
                # allowing it to push coverage above 100%.
                self.intervals.add(path, spans)
                self.source_paths.add(path)
                stream["read_files"].add(path)
                return
            clipped = []
            for start, count in spans or []:
                start = max(1, int(start))
                end = min(int(max_lines), start + int(count) - 1)
                if end >= start:
                    clipped.append((start, end - start + 1))
            spans = clipped
        was_visible = path in self.intervals.by_path and bool(self.intervals.by_path[path])
        added = self.intervals.add(path, spans)
        if added <= 0:
            return
        self.source_paths.add(path)
        stream["read_files"].add(path)
        if inventory:
            coverage["lines"] = int(coverage.get("lines") or 0) + added
            if not was_visible:
                coverage["files"] = int(coverage.get("files") or 0) + 1
            if path.lower().endswith(extract_session._CODE_EXT):
                coverage["code_lines"] = int(coverage.get("code_lines") or 0) + added
                if not was_visible:
                    coverage["code_files"] = int(coverage.get("code_files") or 0) + 1
            self.state["coverage"] = coverage

    def _read_tool_result(self, stream, tool, block, record):
        name = tool.get("name")
        inp = tool.get("input") or {}
        body = _tool_result_text(block, record)
        if block.get("is_error"):
            return
        if name == "Read":
            path = self._normalize_source(inp.get("file_path") or inp.get("path"))
            if not path:
                return
            spans = []
            tur = record.get("toolUseResult")
            if isinstance(tur, dict):
                file_meta = tur.get("file")
                if isinstance(file_meta, dict) and file_meta.get("numLines"):
                    spans = [(file_meta.get("startLine") or 1, file_meta["numLines"])]
            if not spans:
                spans = extract_session._spans_from_numbered_text(body)
            if not spans and body:
                spans = [(1, body.count("\n") + 1)]
            self._add_visible(stream, path, spans)
        elif name in ("Grep", "Bash", "PowerShell"):
            for event in extract_session._infer_visible_source_lines(
                    name, inp, body, self.state.get("cwd")):
                self._add_visible(stream, event["path"], event["intervals"])

    def _handle_tool_use(self, stream, block, ts):
        tid = block.get("id")
        name = block.get("name") or "unknown"
        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
        if tid and tid in stream["pending_tools"]:
            return
        stream["tool_uses"] += 1
        stream["tool_counts"][name] = stream["tool_counts"].get(name, 0) + 1
        self.state["tool_calls"] += 1
        global_tools = self.state.setdefault("tool_counts", {})
        global_tools[name] = global_tools.get(name, 0) + 1
        if tid:
            stream["pending_tools"][tid] = {"name": name, "input": inp, "ts": ts}
        if name == "Skill":
            skill = (inp.get("skill") or "").split(":")[-1]
            if skill:
                stream["stage"] = skill
                if stream["kind"] == "main" and skill in _PIPELINE_SKILLS:
                    self.state["current_stage"] = skill
                    self._event("stage", "进入 %s" % skill, ts)
        elif name == "Workflow":
            script = inp.get("script") or ""
            match = re.search(r"name\s*:\s*['\"]([^'\"]+)", script)
            if match:
                stage = "wf:" + match.group(1)
                stream["stage"] = stage
                if stream["kind"] == "main":
                    self.state["current_stage"] = stage
                    self._event("stage", "启动 %s" % match.group(1), ts)
        if name in ("Write", "Edit", "MultiEdit"):
            target = inp.get("file_path") or inp.get("path")
            if isinstance(target, str):
                target = os.path.abspath(target if os.path.isabs(target) else
                                         os.path.join(self.state.get("cwd") or os.getcwd(), target))
                stream["write_files"].add(target)
                self.write_files.add(target)
                self._event("write", "%s %s" % (name, os.path.basename(target)), ts)
        elif name in ("Agent", "Task"):
            self._event("agent", "派发 %s" % (inp.get("description") or
                                               inp.get("subagent_type") or "subagent"), ts)

    def _handle_tool_result(self, stream, block, record):
        tid = block.get("tool_use_id")
        tool = stream["pending_tools"].pop(tid, None)
        if not tool:
            return
        self._read_tool_result(stream, tool, block, record)

    def _process_record(self, stream, record):
        stream["records"] += 1
        self.state["records"] += 1
        ts = record.get("timestamp")
        if ts:
            stream["last_ts"] = ts
            if self.state["started_at"] is None or ts < self.state["started_at"]:
                self.state["started_at"] = ts
            if self.state["ended_at"] is None or ts > self.state["ended_at"]:
                self.state["ended_at"] = ts
        if not self.state.get("cwd") and record.get("cwd"):
            self.state["cwd"] = record["cwd"]
        if record.get("sessionId"):
            self.state["session_id"] = record["sessionId"]

        rtype = record.get("type")
        message = record.get("message")
        if isinstance(message, dict):
            model = message.get("model")
            if model and not model.startswith("<"):
                stream["model"] = stream.get("model") or model
                self.state["model"] = self.state.get("model") or model
            self._update_usage(stream, message)
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        self._handle_tool_use(stream, block, ts)
                    elif block.get("type") == "tool_result":
                        self._handle_tool_result(stream, block, record)

        if stream["kind"] == "main":
            skill = (record.get("attributionSkill") or "").split(":")[-1]
            if skill in _PIPELINE_SKILLS and skill != self.state.get("current_stage"):
                self.state["current_stage"] = skill
                stream["stage"] = skill
                self._event("stage", "进入 %s" % skill, ts)
            if rtype == "user" and record.get("promptSource") == "typed":
                text = _message_text(message)
                if text.strip():
                    self.state["user_prompts"] += 1
                    stream["status"] = "running"
                    self._event("prompt", "用户输入: %s" % " ".join(text.split())[:100], ts)
            if rtype == "system" and record.get("subtype") in ("stop_hook_summary", "turn_duration"):
                stream["status"] = "waiting"
            elif rtype == "assistant" and isinstance(message, dict):
                stream["status"] = "waiting" if message.get("stop_reason") == "end_turn" else "running"
        else:
            text = _message_text(message).lower()
            if "request interrupted" in text or "stopped by the user" in text:
                stream["status"] = "interrupted"
            elif "api error" in text and "connection" in text:
                stream["status"] = "failed"
            elif rtype == "assistant" and isinstance(message, dict):
                stop = message.get("stop_reason")
                if _is_terminal_assistant_message(message):
                    stream["status"] = "completed"
                    # Only explicit modern end_turn records create a timeline
                    # event.  A legacy text-only block might be followed by a
                    # later tool turn in a growing file; status will be updated
                    # by that record, but we must not leave a false event behind.
                    if stop in ("end_turn", "stop_sequence"):
                        self._event("agent", "子 agent 完成 %s" %
                                    (stream.get("desc") or stream.get("agent_id", ""))[:80], ts,
                                    agent_id=stream.get("agent_id"))
                else:
                    stream["status"] = "running"
            elif rtype in ("assistant", "user"):
                stream["status"] = "running"

    # ---------- coverage / public state ----------
    def _ensure_inventory(self):
        if self.inventory is not None or not self.source_paths:
            return
        root = extract_session._find_gradle_root(sorted(self.source_paths))
        scan = extract_session._scan_android_total(root) if root else None
        if scan:
            self.android_root = scan.get("root")
            self.inventory = scan
            self._rebuild_coverage_cache()

    def _rebuild_coverage_cache(self):
        total = self.inventory or {}
        inventory = total.get("inventory") or {}
        root = self.android_root
        result = {
            "root": root, "files": 0, "lines": 0,
            "code_files": 0, "code_lines": 0,
            "total_files": total.get("files"),
            "total_lines": total.get("lines"),
            "total_code_files": total.get("code_files"),
            "total_code_lines": total.get("code_lines"),
        }
        for path, spans in self.intervals.by_path.items():
            rel = _safe_rel(path, root)
            max_lines = inventory.get(rel)
            if inventory and max_lines is None:
                continue
            count = 0
            for start, end in spans:
                if max_lines:
                    start, end = max(1, start), min(max_lines, end)
                if end >= start:
                    count += end - start + 1
            if count:
                result["files"] += 1
                result["lines"] += count
                if path.lower().endswith(extract_session._CODE_EXT):
                    result["code_files"] += 1
                    result["code_lines"] += count
        self.state["coverage"] = result

    def _coverage(self):
        return copy.deepcopy(self.state.get("coverage") or {})

    def _overall_status(self):
        agent_statuses = [s.get("status") for s in self.streams.values() if s["kind"] == "agent"]
        if any(x == "running" for x in agent_statuses):
            return "running"
        main = next((s for s in self.streams.values() if s["kind"] == "main"), None)
        if main and main.get("status") == "running":
            return "running"
        if main and main.get("status") == "waiting":
            return "waiting"
        return "idle"

    def snapshot(self):
        with self.lock:
            agents = []
            for stream in self.streams.values():
                if stream["kind"] != "agent":
                    continue
                agents.append({
                    "agent_id": stream.get("agent_id"),
                    "desc": stream.get("desc") or stream.get("agent_id"),
                    "type": stream.get("agent_type"),
                    "status": stream.get("status"),
                    "stage": stream.get("stage"),
                    "model": stream.get("model"),
                    "tool_uses": stream.get("tool_uses", 0),
                    "output_tokens": stream.get("output_tokens", 0),
                    "read_files": len(stream.get("read_files") or []),
                    "write_files": len(stream.get("write_files") or []),
                    "last_ts": stream.get("last_ts"),
                })
            agents.sort(key=lambda x: (x.get("status") != "running", x.get("desc") or ""))
            counts = collections.Counter(x["status"] for x in agents)
            state = copy.deepcopy(self.state)
            state["status"] = self._overall_status()
            state["agents"] = agents
            state["agent_counts"] = dict(counts)
            state["coverage"] = self._coverage()
            state["tool_counts"] = dict(self.state.get("tool_counts") or {})
            state["write_files"] = len(self.write_files)
            state["source_bytes"] = sum(
                os.path.getsize(path) if os.path.isfile(path) else 0 for path in self.streams
            )
            state["events"] = list(self.events)
            state["cache_path"] = self.cache_path
            state["checkpoint_loaded"] = self.loaded_checkpoint
            return state

    # ---------- poll lifecycle ----------
    def poll_once(self):
        with self.lock:
            self.state["bytes_read_last"] = 0
            changed = self._register_streams()
            changed = self._refresh_workflows() or changed
            # Truncation/replacement requires a deterministic replay because
            # previous aggregate contributions can no longer be subtracted.
            for stream in self.streams.values():
                try:
                    size = os.path.getsize(stream["path"])
                except OSError:
                    continue
                if size < int(stream.get("offset") or 0):
                    self._reset_for_replay()
                    self._event("reset", "检测到 transcript 截断，重新建立增量状态")
                    self._register_streams()
                    self._refresh_workflows()
                    break

            for stream in list(self.streams.values()):
                records, nbytes, reset = self._read_new_records(stream)
                if reset:
                    self._reset_for_replay()
                    return self.poll_once()
                if nbytes:
                    changed = True
                    self.state["bytes_read_last"] += nbytes
                    self.state["bytes_read_total"] += nbytes
                for record in records:
                    self._process_record(stream, record)
            self._apply_workflow_statuses()
            if changed:
                self._ensure_inventory()
                self.state["version"] += 1
                self.state["last_update"] = _now_iso()
                self.state["last_error"] = None
        if changed:
            self.save_checkpoint()
        return changed

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # retain last good state, surface the error
                with self.lock:
                    self.state["last_error"] = "%s: %s" % (type(exc).__name__, exc)
                    self.state["version"] += 1
                    self.state["last_update"] = _now_iso()
                self._event("error", self.state["last_error"])
            self.stop_event.wait(self.poll_interval)

    def start(self):
        self.poll_once()
        self.thread = threading.Thread(target=self._loop, name="migloop-live", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=max(2.0, self.poll_interval * 3))
        self.save_checkpoint(force=True)


LIVE_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MigLoop Live</title><style>
:root{color-scheme:light dark;--bg:#f4f6f8;--card:#fff;--ink:#18212f;--muted:#667085;--line:#e1e6ec;--green:#23946b;--blue:#3976d4;--amber:#c27a13;--red:#c5473d}
@media(prefers-color-scheme:dark){:root{--bg:#11151b;--card:#181e27;--ink:#eef2f7;--muted:#9ba7b6;--line:#303846}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}.wrap{max-width:1240px;margin:auto;padding:24px}.top{display:flex;gap:14px;align-items:center;flex-wrap:wrap}.dot{width:10px;height:10px;border-radius:50%;background:var(--green);box-shadow:0 0 0 5px color-mix(in srgb,var(--green) 16%,transparent)}h1{font-size:24px;margin:0}.sub{color:var(--muted)}.actions{margin-left:auto;display:flex;gap:8px}.btn{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:8px 12px;border-radius:8px;text-decoration:none;cursor:pointer}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:20px 0}.card,.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px}.k{color:var(--muted);font-size:12px}.v{font-size:24px;font-weight:650;margin-top:3px}.bar{height:7px;background:var(--line);border-radius:9px;overflow:hidden;margin-top:8px}.fill{height:100%;background:var(--blue)}.cols{display:grid;grid-template-columns:1.4fr .8fr;gap:12px}@media(max-width:850px){.cols{grid-template-columns:1fr}}h2{font-size:16px;margin:0 0 12px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px 6px;border-top:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-size:11px}.status{display:inline-flex;border-radius:99px;padding:2px 7px;font-size:11px;background:var(--line)}.running{color:var(--green)}.failed,.interrupted{color:var(--red)}.waiting{color:var(--amber)}.events{display:flex;flex-direction:column;gap:8px}.event{border-left:2px solid var(--line);padding-left:9px}.event small{color:var(--muted)}.warn{background:color-mix(in srgb,var(--red) 10%,var(--card));border-color:color-mix(in srgb,var(--red) 40%,var(--line))}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.empty{color:var(--muted);padding:16px 0}
</style></head><body><main class="wrap">
<div class="top"><span class="dot" id="dot"></span><div><h1>MigLoop Live</h1><div class="sub" id="headline">正在连接增量状态…</div></div><div class="actions"><a class="btn" href="/snapshot.html" target="_blank">生成详细快照</a></div></div>
<div id="error"></div><section class="grid" id="cards"></section><div class="cols"><section class="panel"><h2>Agent 进度</h2><div id="agents"></div></section><section class="panel"><h2>最近事件</h2><div class="events" id="events"></div></section></div>
</main><script>
let etag="";const $=id=>document.getElementById(id);const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));const fmt=n=>{n=Number(n||0);return n>=1e6?(n/1e6).toFixed(2)+"M":n>=1e3?(n/1e3).toFixed(1)+"K":String(n)};const pct=(a,b)=>b?Math.min(100,a*100/b):0;const tm=s=>s?new Date(s).toLocaleTimeString():"—";
function card(k,v,sub,bar){return `<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="sub">${sub||""}</div>${bar==null?"":`<div class="bar"><div class="fill" style="width:${bar}%"></div></div>`}</div>`}
function render(d){document.title=`MigLoop Live · ${String(d.session_id||"").slice(0,8)}`;$("headline").textContent=`${d.status.toUpperCase()} · ${d.current_stage||"session"} · 更新 ${tm(d.last_update)} · v${d.version}`;$("dot").style.background=d.status==="running"?"var(--green)":d.status==="waiting"?"var(--amber)":"var(--muted)";
 const c=d.coverage||{},ac=d.agent_counts||{};$("cards").innerHTML=card("Agent",`${ac.running||0} running`,`${ac.completed||0} completed · ${ac.failed||0} failed`)+card("工具调用",fmt(d.tool_calls),`${fmt(d.output_tokens)} output tokens`)+card("Java/Kotlin 视野",`${fmt(c.code_lines)} / ${fmt(c.total_code_lines)}`,`${c.code_files||0} / ${c.total_code_files||"—"} files`,pct(c.code_lines,c.total_code_lines))+card("本次增量读取",fmt(d.bytes_read_last)+" B",`累计处理 ${fmt(d.bytes_read_total)} B · session ${fmt(d.source_bytes)} B`)+card("产物",fmt(d.write_files)+" files",`${fmt(d.records)} JSONL records`);
 $("error").innerHTML=d.last_error?`<div class="panel warn" style="margin-top:14px">保留上一版状态；刷新错误：${esc(d.last_error)}</div>`:"";
 const agents=d.agents||[];$("agents").innerHTML=agents.length?`<table><thead><tr><th>状态</th><th>Agent</th><th>阶段</th><th>工具</th><th>源码</th><th>Token</th></tr></thead><tbody>${agents.map(a=>`<tr><td><span class="status ${esc(a.status)}">${esc(a.status)}</span></td><td>${esc(a.desc||a.agent_id)}<div class="sub mono">${esc(String(a.agent_id||"").slice(0,8))}</div></td><td>${esc(a.stage||"—")}</td><td>${a.tool_uses||0}</td><td>${a.read_files||0} files</td><td>${fmt(a.output_tokens)}</td></tr>`).join("")}</tbody></table>`:`<div class="empty">尚未发现子 agent</div>`;
 const ev=(d.events||[]).slice(-18).reverse();$("events").innerHTML=ev.length?ev.map(e=>`<div class="event"><div>${esc(e.text)}</div><small>${tm(e.ts)} · ${esc(e.kind)}</small></div>`).join(""):`<div class="empty">等待新事件</div>`;}
async function tick(){try{const r=await fetch("/api/state",{cache:"no-store",headers:etag?{"If-None-Match":etag}:{}});if(r.status===304)return;if(!r.ok)throw Error(r.status);etag=r.headers.get("ETag")||"";render(await r.json())}catch(e){$("headline").textContent="连接中断，正在重试…"}}
tick();setInterval(tick,__MIGLOOP_POLL_MS__);
</script></body></html>'''


def _chat_ui(chat_info):
    if not chat_info or not chat_info.get("enabled"):
        return "", "", ""
    button = r'''<button id="migloop-chat-open" type="button" style="flex:none;padding:5px 9px;border:0;border-radius:8px;background:#7357c7;color:#fff;cursor:pointer">Agent 分析</button>'''
    panel = r'''
<div id="migloop-chat-backdrop" hidden style="position:fixed;inset:0;z-index:99991;background:rgba(15,23,42,.18)"></div>
<aside id="migloop-chat-panel" aria-label="MigLoop Agent 分析" style="position:fixed;z-index:99992;right:18px;top:18px;bottom:18px;width:min(440px,calc(100vw - 36px));display:none;grid-template-rows:auto auto 1fr auto;border:1px solid rgba(90,105,125,.28);border-radius:16px;background:var(--paper,#fff);color:var(--ink,#18212f);box-shadow:0 20px 70px rgba(20,28,40,.25);overflow:hidden;font:14px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif">
  <div style="display:flex;align-items:flex-start;gap:10px;padding:16px 16px 12px;border-bottom:1px solid rgba(90,105,125,.18)">
    <div style="width:32px;height:32px;border-radius:10px;background:#7357c7;color:#fff;display:grid;place-items:center;font-weight:700">AI</div>
    <div style="min-width:0"><div style="font-weight:700;font-size:16px">Agent 分析</div><div id="migloop-chat-model" style="font-size:12px;opacity:.65"></div></div>
    <button id="migloop-chat-clear" type="button" style="margin-left:auto;border:0;background:transparent;color:inherit;opacity:.65;cursor:pointer">清空</button>
    <button id="migloop-chat-close" type="button" aria-label="关闭" style="border:0;background:transparent;color:inherit;font-size:20px;line-height:1;cursor:pointer">×</button>
  </div>
  <div id="migloop-chat-quick" style="display:flex;gap:6px;overflow:auto;padding:10px 14px;border-bottom:1px solid rgba(90,105,125,.12)">
    <button type="button" data-q="总结当前迁移进度，并指出最值得关注的一个风险。">总结进度</button>
    <button type="button" data-q="哪些阶段的源码阅读或产物写入最不均衡？请给出数据依据。">检查视野</button>
    <button type="button" data-q="从当前血缘看，哪些 Agent 或文件可能是返工热点？">返工热点</button>
  </div>
  <div id="migloop-chat-messages" style="overflow:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:color-mix(in srgb,var(--paper,#fff) 96%,#7357c7 4%)"></div>
  <form id="migloop-chat-form" style="padding:12px;border-top:1px solid rgba(90,105,125,.18);background:var(--paper,#fff)">
    <textarea id="migloop-chat-input" rows="3" maxlength="12000" placeholder="问当前会话、阶段、Agent、源码视野或产物关系…" style="width:100%;resize:none;padding:10px 11px;border:1px solid rgba(90,105,125,.28);border-radius:10px;background:transparent;color:inherit;font:inherit;outline:none"></textarea>
    <div style="display:flex;align-items:center;gap:8px;margin-top:8px"><span id="migloop-chat-status" style="font-size:12px;opacity:.6">只读分析完整 session</span><button id="migloop-chat-send" type="submit" style="margin-left:auto;border:0;border-radius:9px;background:#7357c7;color:#fff;padding:8px 14px;cursor:pointer">发送</button></div>
  </form>
</aside>'''
    info_json = json.dumps(chat_info, ensure_ascii=False).replace("</", "<\\/")
    script = r'''
<script>
(function(){
  "use strict";
  var INFO=__CHAT_INFO__, history=[], busy=false;
  var openBtn=document.getElementById("migloop-chat-open"), panel=document.getElementById("migloop-chat-panel"), backdrop=document.getElementById("migloop-chat-backdrop"), messages=document.getElementById("migloop-chat-messages"), input=document.getElementById("migloop-chat-input"), form=document.getElementById("migloop-chat-form"), send=document.getElementById("migloop-chat-send"), status=document.getElementById("migloop-chat-status");
  if(!openBtn||!panel)return;
  document.getElementById("migloop-chat-model").textContent=(INFO.provider||"model")+" · "+(INFO.model||"default");
  document.querySelectorAll("#migloop-chat-quick button").forEach(function(b){b.style.cssText="flex:none;border:1px solid rgba(90,105,125,.22);border-radius:999px;background:transparent;color:inherit;padding:5px 9px;font:12px inherit;cursor:pointer";});
  function bubble(role,content,error){
    var row=document.createElement("div"), box=document.createElement("div");
    row.style.cssText="display:flex;"+(role==="user"?"justify-content:flex-end":"justify-content:flex-start");
    box.style.cssText="max-width:88%;padding:9px 11px;border-radius:12px;white-space:pre-wrap;word-break:break-word;"+(role==="user"?"background:#7357c7;color:#fff":"background:var(--paper,#fff);border:1px solid rgba(90,105,125,.16)")+(error?";border-color:#c5473d;color:#c5473d":"");
    box.textContent=content; row.appendChild(box); messages.appendChild(row); messages.scrollTop=messages.scrollHeight; return row;
  }
  function welcome(){messages.innerHTML="";bubble("assistant","我会以完整 session 记录为事实源，结合血缘索引分析主线程、Workflow、子 Agent、工具调用和实际读写。必要时会追查原始 transcript；回答不会修改工程。",false);}
  function show(){panel.style.display="grid";backdrop.hidden=false;setTimeout(function(){input.focus()},0)}
  function hide(){panel.style.display="none";backdrop.hidden=true}
  function setBusy(value){busy=value;send.disabled=value;input.disabled=value;send.textContent=value?"分析中…":"发送";status.textContent=value?"正在追查 session 记录…":"只读分析完整 session"}
  async function ask(content){
    content=String(content||"").trim(); if(!content||busy)return;
    history.push({role:"user",content:content}); bubble("user",content,false); input.value=""; setBusy(true);
    var pending=bubble("assistant","正在分析…",false);
    try{
      var r=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({messages:history})});
      var data=await r.json().catch(function(){return {error:"服务返回了不可解析的响应"}});
      pending.remove();
      if(!r.ok)throw Error(data.error||("HTTP "+r.status));
      var reply=String(data.reply||"").trim(); history.push({role:"assistant",content:reply}); bubble("assistant",reply,false);
      if(history.length>20)history=history.slice(-20);
    }catch(e){pending.remove();bubble("assistant","分析失败："+e.message,true)}finally{setBusy(false);input.focus()}
  }
  openBtn.addEventListener("click",show);document.getElementById("migloop-chat-close").addEventListener("click",hide);backdrop.addEventListener("click",hide);
  document.getElementById("migloop-chat-clear").addEventListener("click",function(){history=[];welcome()});
  document.getElementById("migloop-chat-quick").addEventListener("click",function(e){var q=e.target&&e.target.getAttribute("data-q");if(q)ask(q)});
  form.addEventListener("submit",function(e){e.preventDefault();ask(input.value)});
  input.addEventListener("keydown",function(e){if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();ask(input.value)}});
  welcome();
})();
</script>'''.replace("__CHAT_INFO__", info_json)
    return button, panel, script


def _attach_live_controls(body, baseline_version, baseline_records, poll_ms, chat_info=None):
    """Add a tiny live controller to the real, fully rendered analysis page.

    The heavy viewer remains a point-in-time deterministic snapshot.  Only this
    controller polls the incremental reducer.  When new records arrive it marks
    the snapshot stale; rebuilding the full graphs is an explicit user action,
    so a long-running session never falls back to replaying all history every
    polling interval.
    """
    was_bytes = isinstance(body, (bytes, bytearray))
    text = bytes(body).decode("utf-8") if was_bytes else str(body)
    baseline_version = int(baseline_version or 0)
    baseline_records = int(baseline_records or 0)
    poll_ms = max(200, int(poll_ms))
    snapshot_at = _now_iso()
    controls = r'''
<div id="migloop-live-controls" style="position:fixed;right:18px;bottom:18px;z-index:99990;display:flex;align-items:center;gap:10px;max-width:min(680px,calc(100vw - 36px));padding:10px 12px;border:1px solid rgba(90,105,125,.28);border-radius:12px;background:color-mix(in srgb,var(--paper,#fff) 94%,transparent);color:var(--ink,#18212f);box-shadow:0 8px 30px rgba(20,28,40,.18);font:13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;backdrop-filter:blur(12px)">
  <span id="migloop-live-dot" style="width:8px;height:8px;border-radius:50%;background:#23946b;flex:none"></span>
  <span id="migloop-live-text" style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">完整分析快照已生成，正在连接增量状态…</span>
  <a id="migloop-live-refresh" href="/refresh" style="display:none;flex:none;padding:5px 9px;border-radius:8px;background:#3976d4;color:#fff;text-decoration:none">刷新完整分析</a>
  __CHAT_BUTTON__
  <a href="/export.html" style="flex:none;color:inherit;text-decoration:none">导出 HTML</a>
  <a href="/status.html" style="flex:none;color:inherit;opacity:.72;text-decoration:none">状态</a>
</div>
__CHAT_PANEL__
<script>
(function(){
  "use strict";
  var BASELINE_VERSION=__BASELINE_VERSION__, BASELINE_RECORDS=__BASELINE_RECORDS__, SNAPSHOT_AT="__SNAPSHOT_AT__", etag="";
  var text=document.getElementById("migloop-live-text"), dot=document.getElementById("migloop-live-dot"), refresh=document.getElementById("migloop-live-refresh");
  function clock(ts){if(!ts)return "—";return new Date(ts).toLocaleTimeString()}
  async function tick(){
    try{
      var r=await fetch("/api/state",{cache:"no-store",headers:etag?{"If-None-Match":etag}:{}});
      if(r.status===304)return;
      if(!r.ok)throw Error(String(r.status));
      etag=r.headers.get("ETag")||"";
      var d=await r.json(), newer=Number(d.version||0)>BASELINE_VERSION;
      var added=Math.max(0,Number(d.records||0)-BASELINE_RECORDS);
      dot.style.background=d.status==="running"?"#23946b":d.status==="waiting"?"#c27a13":"#7b8796";
      if(newer){
        text.textContent="检测到 "+added+" 条新记录 · 当前图表仍是 v"+BASELINE_VERSION+" · "+clock(d.last_update);
        refresh.style.display="inline-block";
      }else{
        text.textContent=(d.status||"live").toUpperCase()+" · 快照 v"+BASELINE_VERSION+" · "+BASELINE_RECORDS+" 条 · 生成 "+clock(SNAPSHOT_AT)+" · 每 __POLL_SECONDS__ 秒检查";
        refresh.style.display="none";
      }
    }catch(e){
      dot.style.background="#c5473d";
      text.textContent="增量连接中断，下一轮自动重试";
    }
  }
  refresh.addEventListener("click",function(){refresh.textContent="正在重建…";text.textContent="正在生成新的完整分析快照";});
  tick();setInterval(tick,__POLL_MS__);
})();
</script>
__CHAT_SCRIPT__
'''
    chat_button, chat_panel, chat_script = _chat_ui(chat_info)
    controls = (controls
                .replace("__BASELINE_VERSION__", str(baseline_version))
                .replace("__BASELINE_RECORDS__", str(baseline_records))
                .replace("__SNAPSHOT_AT__", snapshot_at)
                .replace("__POLL_SECONDS__", ("%g" % (poll_ms / 1000.0)))
                .replace("__POLL_MS__", str(poll_ms))
                .replace("__CHAT_BUTTON__", chat_button)
                .replace("__CHAT_PANEL__", chat_panel)
                .replace("__CHAT_SCRIPT__", chat_script))
    if "</body>" in text:
        text = text.replace("</body>", controls + "\n</body>", 1)
    else:
        text += controls
    return text.encode("utf-8") if was_bytes else text


class _LiveHandler(BaseHTTPRequestHandler):
    server_version = "MigLoopLive/1.0"

    def log_message(self, fmt, *args):
        return

    def _send(self, body, content_type, status=HTTPStatus.OK, headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urllib.parse.urlsplit(self.path).path
        if route in ("/", "/index.html"):
            self._send(self.server.analysis_html, "text/html; charset=utf-8")
            return
        if route == "/status.html":
            self._send(self.server.status_html, "text/html; charset=utf-8")
            return
        if route == "/api/state":
            state = self.server.monitor.snapshot()
            etag = '"%s"' % state.get("version", 0)
            if self.headers.get("If-None-Match") == etag:
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
            self._send(payload, "application/json; charset=utf-8", headers={"ETag": etag})
            return
        if route == "/api/chat/config":
            info = self.server.chat_service.info() if self.server.chat_service else {
                "enabled": False, "provider": "off", "model": None
            }
            self._send(json.dumps(info, ensure_ascii=False),
                       "application/json; charset=utf-8")
            return
        if route == "/snapshot.html":
            try:
                body = self.server.snapshot_builder()
                self._send(body, "text/html; charset=utf-8")
            except Exception as exc:
                self._send("生成快照失败: %s" % html.escape(str(exc)),
                           "text/plain; charset=utf-8", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if route == "/export.html":
            try:
                body = self.server.snapshot_builder()
                sid = (self.server.monitor.snapshot().get("session_id") or "session")[:8]
                self._send(body, "text/html; charset=utf-8", headers={
                    "Content-Disposition": 'attachment; filename="migloop-%s.html"' % sid
                })
            except Exception as exc:
                self._send("导出 HTML 失败: %s" % html.escape(str(exc)),
                           "text/plain; charset=utf-8", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if route == "/refresh":
            try:
                self.server.refresh_analysis()
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/")
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except Exception as exc:
                self._send("刷新完整分析失败: %s" % html.escape(str(exc)),
                           "text/plain; charset=utf-8", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send("not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)

    def do_POST(self):
        route = urllib.parse.urlsplit(self.path).path
        if route != "/api/chat":
            self._send("not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)
            return
        if not self.server.chat_service:
            self._send(json.dumps({"error": "分析助手未启用"}, ensure_ascii=False),
                       "application/json; charset=utf-8", HTTPStatus.SERVICE_UNAVAILABLE)
            return
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            size = 0
        if size <= 0 or size > 256 * 1024:
            self._send(json.dumps({"error": "请求体大小无效"}, ensure_ascii=False),
                       "application/json; charset=utf-8", HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            reply = self.server.chat_service.chat(payload.get("messages"))
            result = {"reply": reply, **self.server.chat_service.info()}
            self._send(json.dumps(result, ensure_ascii=False),
                       "application/json; charset=utf-8")
        except chat_provider.ChatConfigurationError as exc:
            self._send(json.dumps({"error": str(exc)}, ensure_ascii=False),
                       "application/json; charset=utf-8", HTTPStatus.BAD_REQUEST)
        except chat_provider.ChatProviderError as exc:
            self._send(json.dumps({"error": str(exc)}, ensure_ascii=False),
                       "application/json; charset=utf-8", HTTPStatus.BAD_GATEWAY)
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            self._send(json.dumps({"error": "请求格式错误：%s" % exc}, ensure_ascii=False),
                       "application/json; charset=utf-8", HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send(json.dumps({"error": "分析失败：%s" % exc}, ensure_ascii=False),
                       "application/json; charset=utf-8", HTTPStatus.INTERNAL_SERVER_ERROR)


class LiveHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, monitor, snapshot_builder, dashboard_poll_ms,
                 chat_service=None):
        super().__init__(address, _LiveHandler)
        self.monitor = monitor
        self.snapshot_builder = snapshot_builder
        self.dashboard_poll_ms = max(200, int(dashboard_poll_ms))
        self.chat_service = chat_service
        self.status_html = LIVE_HTML.replace(
            "__MIGLOOP_POLL_MS__", str(self.dashboard_poll_ms)
        )
        self.analysis_lock = threading.Lock()
        self.analysis_html = b""
        self.analysis_version = 0
        self.refresh_analysis()

    def refresh_analysis(self):
        """Rebuild the heavyweight viewer only on initial load or explicit refresh."""
        with self.analysis_lock:
            baseline = self.monitor.snapshot()
            body = self.snapshot_builder()
            self.analysis_html = _attach_live_controls(
                body,
                baseline.get("version"),
                baseline.get("records"),
                self.dashboard_poll_ms,
                self.chat_service.info() if self.chat_service else None,
            )
            self.analysis_version = int(baseline.get("version") or 0)
            return self.analysis_html


def run_live(jsonl, build_snapshot, out_path, host="127.0.0.1", port=0,
             interval=10.0, cache_dir=None, reset_cache=False, open_browser=False,
             write_final=True, chat_service=None):
    monitor = IncrementalSessionMonitor(
        jsonl, cache_dir=cache_dir, poll_interval=interval, reset_cache=reset_cache
    )
    print("建立/恢复增量状态 …")
    monitor.start()

    snapshot_lock = threading.Lock()

    def snapshot_bytes():
        with snapshot_lock:
            return build_snapshot()

    print("生成首次完整分析页 …")
    server = LiveHTTPServer(
        (host, int(port)), monitor, snapshot_bytes,
        dashboard_poll_ms=round(monitor.poll_interval * 1000),
        chat_service=chat_service,
    )
    url = "http://%s:%d/" % (host, server.server_address[1])
    print("MigLoop Live -> %s" % url)
    print("cache         -> %s" % monitor.cache_path)
    print("Ctrl+C 停止；停止时%s最终静态页面。" % ("生成" if write_final else "不生成"))
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\n正在停止 live monitor …")
    finally:
        server.shutdown()
        server.server_close()
        monitor.stop()
    if write_final:
        print("生成最终一致性快照 …")
        body = snapshot_bytes()
        _atomic_write(out_path, body, binary=True)
        print("最终页面 -> %s (%.0f KB)" % (os.path.abspath(out_path), os.path.getsize(out_path) / 1024))
    return monitor.snapshot()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl")
    parser.add_argument("--cache-dir")
    parser.add_argument("--interval", type=float, default=10.0)
    args = parser.parse_args()
    mon = IncrementalSessionMonitor(args.jsonl, args.cache_dir, args.interval)
    mon.start()
    try:
        while True:
            print(json.dumps(mon.snapshot(), ensure_ascii=False, indent=2))
            time.sleep(5)
    except KeyboardInterrupt:
        mon.stop()
