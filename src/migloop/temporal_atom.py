"""Compact, time-safe I/O navigation over indexed Actions and original messages.

This is not a state replay, a writer attribution graph, or a replacement raw
corpus. A section row is one Action/relation, not two use/result transcript rows.
The raw index and independent native-event/body indexes remain explicit exits.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import os
from typing import Any

from . import atoms, body_sources, raw_events, temporal, transcript_store as store

SCHEMA = "migloop-time-atom/1"
_SECTIONS = ("writes", "reads", "candidates", "messages", "dispatches")
_OVERVIEW_LIMITS = {"writes": 3, "reads": 3, "candidates": 2, "messages": 2, "dispatches": 3}
# Task constraints are original input, not a generated summary. Let short
# fields fit whole; batch delivery still applies its independent total budget.
_MESSAGE_PREVIEW_CHARS = 4096
# Explicit messages selects the complete original field. Overview alone is a
# preview; an explicitly requested transport budget may shorten either view.


def _request(kind, key, window, view, offset, limit, include_undated, details):
    return {"tool": kind, "args": {"path" if kind == "file" else "id": key,
            "at": window.at, "since_ts": window.since, "view": view, "offset": offset,
            "limit": limit, "include_undated": include_undated, "details": details}}


def _pointer(part, window):
    return {"ref": part.record.ref, "pointer": part.pointer,
            "source": part.record.address()["source"], "line": part.record.line,
            "ts": part.record.ts, "in_window": window.contains(part.record.ts)}


def _expand(parts, scope, *, include_undated=False):
    refs = [{"ref": p["ref"], "pointer": p["pointer"]} for p in parts
            if p is not None and (p["in_window"] or (include_undated and p["ts"] is None))]
    return {"tool": "expand", "args": {"refs": refs,
            "include_undated": include_undated}, "scope": deepcopy(scope)} if refs else None


def _request_target(part):
    """A literal native request target is not a successful read/write fact.

    Do not parse shell scripts, code-host literals, or resolve relative paths
    using a later Action detail. Those remain reachable in the raw indexes.
    """
    tool, payload = part.payload.get("name"), part.payload.get("input")
    if tool not in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit") or not isinstance(payload, dict):
        return None
    target = payload.get("notebook_path" if tool == "NotebookEdit" else "file_path")
    if not isinstance(target, str) or not body_sources._target(target, target):
        return None
    return {"kind": "read" if tool == "Read" else "write",
            "path": target.replace("\\", "/"), "status": "candidate",
            "operation_basis": "native_request_target", "execution": "unknown",
            "delivery": "not_certified"}


def _actions(ledger, kind, key, window, scope, include_undated, stale):
    groups = {name: [] for name in _SECTIONS}
    counts = {"unknown_time_actions": 0, "unlocated_actions": 0}
    if stale:
        return groups, counts, []
    owners = {key} if kind == "agent" else None
    annotations = temporal._annotations(ledger, window, owners)
    native = raw_events._scan(ledger, key if kind == "agent" else None)
    # Cached native pairing is source-local and does not execute historical code.
    uses = {}
    for event in native["events"]:
        for part in event.parts:
            if part.direction == "use":
                uses[(event.source, part.record.line, part.block, event.call_id)] = (event, part)
    agents = [ledger.agents[key]] if kind == "agent" else ledger.agents.values()
    for agent in agents:
        for action in agent.actions:
            if temporal.Window.parse("latest").contains(action.ts) and not window.ended(action.ts):
                continue
            if not action.src or not action.tuid:
                if action.files:
                    counts["unlocated_actions"] += 1
                continue
            source, first, last = action.src
            if type(first) is not int or first < 0:
                counts["unlocated_actions"] += 1
                continue
            source = os.path.normcase(os.path.abspath(source))
            pair = uses.get((source, first + 1, action.blk, action.tuid)) or uses.get(
                (source, first + 1, None, action.tuid))
            if pair is None:
                counts["unlocated_actions"] += 1
                continue
            event, use = pair
            if use.record.ts is not None and not window.ended(use.record.ts):
                continue
            visible = [p for p in event.parts if p.record.ts and window.ended(p.record.ts)]
            projected = raw_events._project(event, visible, scoped=True)
            results = [p for p in visible if p.direction == "result"]
            result = results[0] if len(results) == 1 else None
            annotation = next((a for a in annotations.get((source, first + 1), [])
                               if a["seq"] == action.seq and a["agent"] == agent.id), None)
            completed = bool(annotation and annotation["state"] in ("returned", "failed")
                             and projected["status"] in ("returned", "failed")
                             and use.record.ts and result and result.record.ts >= use.record.ts
                             and type(last) is int and last >= 0 and result.record.line == last + 1
                             and not any(p.record.ts is None for p in event.parts))
            # A future/undated result cannot supply either a target or a status.
            relations = [dict(r) for r in annotation["relations"] if r["kind"] != "mention"] if completed else []
            direct = _request_target(use)
            if direct and not any(r["path"] == direct["path"] for r in relations):
                relations.append(direct)
            if kind == "file":
                relations = [r for r in relations if r.get("path") == key]
            elif not relations:
                # A real indexed native call without a certified target remains
                # an inspection candidate, not a candidate writer of any file.
                relations = [{"kind": "unclassified_call", "path": None, "status": "candidate",
                              "operation_basis": "indexed_native_call", "execution": "unknown"}]
            if not relations:
                continue
            if use.record.ts is None:
                counts["unknown_time_actions"] += 1
                if not include_undated:
                    continue
            stamp = result.record.ts if completed else use.record.ts
            if stamp is not None and not window.contains(stamp):
                continue
            call_state = projected["status"] if use.record.ts else "unknown_time"
            if completed and (action.ok is False or annotation["state"] == "failed"):
                call_state = "failed"
            use_pointer = _pointer(use, window)
            # In-window native result metadata is independently visible even
            # when it does not establish a completed indexed file operation.
            result_pointer = _pointer(result, window) if result is not None else None
            for relation in { (r["kind"], r.get("path")): r for r in relations }.values():
                confirmed = bool(completed and action.ok is True and call_state == "returned"
                                 and event.addressable and relation["status"] == "confirmed")
                operation = {k: v for k, v in relation.items() if k not in ("version_binding", "legacy_v")}
                if not confirmed:
                    operation["status"] = "candidate"
                # Even completed execution is not certified in an ambiguous call.
                if not completed or call_state != "returned" or not event.addressable or action.ok is not True:
                    operation["execution"] = "unknown"
                section = ("reads" if relation["kind"] == "read" else "writes") if confirmed and relation["kind"] in (
                    "read", "write", "delete") else "candidates"
                row = {"id": atoms.event_id_for_action(agent, action),
                    "id_scope": "source_event_shared_with_changes; target_and_operation_separate",
                    "agent": agent.id, "seq": action.seq, "call_id": event.call_id, "tool": action.tool,
                    "ts": stamp, "use_ts": use.record.ts, "done_ts": result.record.ts if completed else None,
                    "time_status": "recorded" if stamp else "undated_not_cutoff_evidence",
                    "call_state": call_state, "operation": operation, "use": use_pointer,
                    "result": result_pointer, "reference_status": "addressable" if event.addressable else "ambiguous_source",
                    "expand_query": _expand([use_pointer, result_pointer], scope, include_undated=include_undated)
                                    if event.addressable else None,
                    "navigation_is_relation": False, "current_state_certified": False}
                if kind == "file" and use.record.ts:
                    row["agent_query"] = {"tool": "agent", "args": {"id": agent.id, "at": use.record.ts,
                        "since_ts": None, "view": "overview"}}
                    row["navigation_label"] = "independent_inputs_before_request"
                elif kind == "agent" and relation.get("path") and stamp:
                    row["file_query"] = {"tool": "file", "args": {"path": relation["path"], "at": stamp,
                        "since_ts": None, "view": "overview"}}
                    row["navigation_label"] = "independent_file_evidence_at_return" if completed else "independent_file_evidence_at_request"
                groups[section].append(row)
    for rows in groups.values():
        rows.sort(key=lambda r: (r["ts"] or "~", r["use"]["source"], r["use"]["line"], r["seq"], r["id"]))
    return groups, counts, native["gaps"]


def _text_fields(record):
    """Original message fields only; tool-result user envelopes are not tasks."""
    value = record.value
    if not isinstance(value, dict):
        return
    content, base, label = None, None, None
    message = value.get("message")
    if isinstance(message, dict) and message.get("role") in ("user", "system", "developer"):
        content, base = message.get("content"), "/message/content"
        label = "recorded_input" if message["role"] == "user" else "recorded_system_input"
    payload = value.get("payload")
    if value.get("type") == "response_item" and isinstance(payload, dict):
        if payload.get("type") == "agent_message":
            content, base, label = payload.get("content"), "/payload/content", "recorded_agent_message"
        elif payload.get("type") == "message" and payload.get("role") in ("user", "system", "developer"):
            content, base = payload.get("content"), "/payload/content"
            label = "recorded_input" if payload["role"] == "user" else "recorded_system_input"
    if isinstance(content, str) and content.strip():
        yield base, content, label
    elif isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") in ("tool_result", "tool_use") for b in content):
            return
        for index, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") in ("text", "input_text") and isinstance(block.get("text"), str):
                if block["text"].strip():
                    yield f"{base}/{index}/text", block["text"], label


def _messages(ledger, key, window, scope, *, explicit=False):
    rows, gaps = [], []
    counts = Counter(store.source_key(p, store.source_spec(ledger, p)) for p in store.sources(ledger))
    for path in store.sources(ledger, key):
        try:
            for record in store.records(path, source=store.source_spec(ledger, path)):
                if not window.contains(record.ts):
                    continue  # Undated text is raw material, never cutoff input.
                for pointer, text, label in _text_fields(record):
                    addressable = counts[store.source_key(path, store.source_spec(ledger, path))] == 1
                    excerpt = text if explicit else text[:_MESSAGE_PREVIEW_CHARS]
                    rows.append({**record.address(), "pointer": pointer, "message_kind": label,
                                 "preview": excerpt, "preview_start": 0, "chars": len(text),
                                 "preview_kind": "original_decoded_field_excerpt",
                                 "preview_span": {"offset": 0, "chars": len(excerpt)},
                                 "source_agent": key, "sender_certified": False,
                                 "reference_status": "addressable" if addressable else "ambiguous_source",
                                 "expand_query": {"tool": "expand", "args": {"refs": [{"ref": record.ref,
                                     "pointer": pointer}]}, "scope": deepcopy(scope)} if addressable else None})
        except (OSError, UnicodeError, ValueError) as exc:
            gaps.append({"source": path, "error": str(exc)})
    rows.sort(key=lambda r: (r["ts"], r["source"], r["line"], r["pointer"]))
    return rows, gaps


def query(ledger: atoms.Ledger, *, kind: str, key: str, at: str, since_ts: str | None = None,
          view: str = "overview", offset: int = 0, limit: int = 40,
          include_undated: bool = False, details: bool = False) -> dict[str, Any]:
    if kind not in ("file", "agent") or view not in ("overview", *_SECTIONS):
        raise ValueError("time atom kind must be file/agent; view must be overview/writes/reads/candidates/messages/dispatches")
    if kind == "file" and view in ("messages", "dispatches"):
        raise ValueError("messages/dispatches view requires an agent scope")
    if type(details) is not bool or type(include_undated) is not bool:
        raise ValueError("details/include_undated must be booleans")
    temporal._page([], offset, limit)
    window = temporal.Window.parse(at, since_ts)
    # One complete raw search supplies identity, exact counts and source gaps.
    # Do not use its first row as the atom's default content or as an input edge.
    raw = temporal.query(ledger, kind=kind, key=key, at=window.at, since_ts=window.since,
                         limit=1, include_undated=include_undated)
    key = raw["node"]["key"]
    scope = {"kind": kind, "key": key, "at": window.at, "since_ts": window.since}
    groups, action_counts, native_gaps = _actions(ledger, kind, key, window, scope,
                                                include_undated, raw["stale_annotation_sources"])
    message_gaps = []
    if kind == "agent":
        groups["messages"], message_gaps = _messages(ledger, key, window, scope, explicit=view == "messages")
        if not raw["stale_annotation_sources"]:
            from . import dispatch_scope
            groups["dispatches"] = dispatch_scope.rows(ledger, key, window)
    else:
        del groups["messages"]
        del groups["dispatches"]
    # A source might change between the raw-count pass and native-index access.
    # Never combine new bytes with stale Action annotations in that case.
    for path, expected in ledger.source_stats.items():
        try:
            stat = os.stat(path)
            changed = (stat.st_mtime_ns, stat.st_size) != expected
        except OSError:
            changed = True
        if changed and path not in raw["stale_annotation_sources"]:
            raw["stale_annotation_sources"].append(path)
    if raw["stale_annotation_sources"]:
        for name in ("writes", "reads", "candidates", "dispatches"):
            if name in groups:
                groups[name] = []
    sections = {}
    for name, rows in groups.items():
        page_limit = min(limit, _OVERVIEW_LIMITS[name]) if view == "overview" else limit
        selected = view in ("overview", name)
        page = temporal._page(rows, offset, page_limit) if selected else {
            "total": len(rows), "offset": 0, "limit": 0, "rows": [], "remaining": len(rows),
            "next_offset": 0 if rows else None}
        page["mode"] = "page" if selected else "count_only"
        page["query"] = _request(kind, key, window, name, page["offset"], page_limit,
                                 include_undated, details)
        page["next_query"] = _request(kind, key, window, name, page["next_offset"], page_limit,
                                      include_undated, details) if page["next_offset"] is not None else None
        sections[name] = page
    warnings = []
    if raw["stale_annotation_sources"]:
        warnings.append("Registered sources changed: indexed Action relations suppressed; original raw/body indexes remain available.")
    return {"schema": SCHEMA, "node": raw["node"], "scope": scope, "view": view,
            "query": _request(kind, key, window, view, offset, limit, include_undated, details),
            "body_sources": body_sources.navigation(ledger, key, window.at, window.since,
                show=view == "overview" and offset == 0) if kind == "file" else None,
            "sections": sections,
            "raw_index": {"total": raw["total"], "counts": raw["counts"], "source_count": raw["source_count"],
                "raw_scan_complete": raw["raw_scan_complete"], "gaps": raw["gaps"],
                "unknown_time_count": raw["counts"]["undated"],
                "query": _request(kind, key, window, "records", 0, limit, include_undated, details)},
            "events_query": {"tool": "events", "args": {"file" if kind == "file" else "agent": key,
                "at": window.at, "since_ts": window.since, "view": "events", "offset": 0, "limit": limit}},
            "stale_annotation_sources": raw["stale_annotation_sources"], "warnings": warnings,
            "coverage": {**action_counts, "native_source_gaps": native_gaps, "message_source_gaps": message_gaps,
                "native_source_gaps_scope": "current_registry_not_historical_cutoff",
                "unlocated_actions_scope": "selected_agent_or_pool_index_not_target_effects",
                "indexed_only": True, "sections_may_overlap": True, "all_effects_complete": False},
            "details": details, "causal_complete": False, "current_state_certified": False,
            "note": "Indexed operation/message navigation, not a state replay or a complete effects inventory. "
                    "A returned call is not by itself a confirmed file effect. Agent labels are indexed call ownership, "
                    "not authors inferred from native source membership. Completion time is evidence availability, "
                    "not the exact modification time. Section order and independent file/agent queries create no edges. "
                    "Other mentions/unclassified or undated records remain in the full raw index; zero rows do not prove absence. "
                    "Raw pointers/body navigation do not mean their full text was delivered. details does not add hidden relations."}
