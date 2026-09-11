"""Bounded operation/observation inventory, not a list of proven repairs.

Native effects, parsed operations and unequal full observations remain distinct.
An observation interval never creates a writer or an exact mutation timestamp.
"""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from typing import Any

from . import atoms, raw_events, temporal
from . import transcript_store as store
from .evidence import CONFIRMED_BASES, proof_payload
from .time_scope import _iso, _time

SCHEMA = "migloop-time-changes/1"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


def _source(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _path(path: str) -> str:
    return path.replace("\\", "/")


def _check_sources(ledger: atoms.Ledger) -> None:
    for path, expected in ledger.source_stats.items():
        try:
            stat = os.stat(path)
            if (stat.st_mtime_ns, stat.st_size) == expected:
                continue
        except OSError:
            pass
        raise ValueError("源文件已变化；修改对账需重建账本，原始时间检索仍可用")


def _candidate_paths(action: atoms.Action) -> set[str]:
    return set(action.detail.get("touched") or []) | set(action.detail.get("conditional") or []) | set(
        action.detail.get("effect_candidates") or [])


def _native_target(record: store.Record | None, action: atoms.Action, path: str) -> bool:
    """A pending direct native target is not inferred from a later result or prose."""
    if record is None or not isinstance(record.value, dict):
        return False
    message = record.value.get("message")
    blocks = message.get("content") if isinstance(message, dict) else None
    if not isinstance(blocks, list) or type(action.blk) is not int or not 0 <= action.blk < len(blocks):
        return False
    block = blocks[action.blk]
    return (isinstance(block, dict) and block.get("type") == "tool_use"
            and block.get("name") in ("Write", "Edit", "MultiEdit")
            and isinstance(block.get("input"), dict)
            and _path(str(block["input"].get("file_path") or "")) == path)


def _apply_single(before: str, ref: atoms.FileRef) -> str | None:
    event = ref.ev
    if event.kind == "wfull" and isinstance(event.content, str):
        return event.content
    if event.kind == "edit" and isinstance(event.old, str) and isinstance(event.new, str) and event.old:
        count = before.count(event.old)
        if count and (event.replace_all or count == 1):
            return before.replace(event.old, event.new, -1 if event.replace_all else 1)
    return None


def _action_address(action: atoms.Action) -> tuple[Any, ...] | None:
    if not action.src or action.src[1] is None:
        return None
    return (_source(action.src[0]), action.src[1] + 1, action.blk, action.tuid)


def _matches_action(event, part, action: atoms.Action) -> bool:
    address = _action_address(action)
    if address is None or address[:2] != (_source(event.source), part.record.line):
        return False
    block, call_id = address[2:]
    if event.protocol == "codex" and part.block is None:
        return bool(call_id) and call_id == event.call_id
    return ((type(block) is int and block == part.block and
             (not call_id or call_id == event.call_id)) or
            (block is None and bool(call_id) and call_id == event.call_id))


def _part_preview(part, current: dict[str, Any], window: temporal.Window) -> dict[str, Any]:
    """Actual decoded native text, never an operation/effect paraphrase."""
    fields = deepcopy(part.fields)
    selected = fields.get("input" if part.direction == "use" else "output")
    pointer = selected["pointer"] if selected else part.pointer
    value = part.payload
    if selected:
        name = pointer.rsplit("/", 1)[-1]
        value = part.payload[name]
    text = store.readable(value)
    basename = current.get("key", "").replace("\\", "/").rsplit("/", 1)[-1]
    position = text.casefold().find(basename.casefold()) if basename else -1
    start = max(0, position - 60) if position >= 0 else 0
    in_range = window.contains(part.record.ts)
    query_scope = deepcopy(current)
    if not in_range:
        # This is explicit independent antecedent context, not an inherited
        # request window. A scope ID authenticates its bounds and cannot follow
        # a changed since_ts into the new scope.
        query_scope.pop("id", None)
        query_scope["since_ts"] = None
    return {"ref": part.record.ref, "line": part.record.line, "ts": part.record.ts,
            "block": part.block, "pointer": pointer, "direction": part.direction,
            "fields": fields, "preview": text[start:start + 240],
            "preview_kind": "decoded_native_payload_excerpt", "preview_start": start,
            "preview_chars": len(text), "preview_truncated": start > 0 or len(text) > 240,
            "in_requested_range": in_range,
            "scope_relation": "inherited" if in_range else "independent_antecedent",
            "scope_note": "继承原查询范围" if in_range else "独立查看起点前的请求/回执；不是原since窗口内的证据",
            "expand_query": {"tool": "expand", "scope": query_scope,
                             "args": {"refs": [{"ref": part.record.ref, "pointer": pointer}]}}}


def _call_presentation(event, window: temporal.Window, current: dict[str, Any],
                       action: atoms.Action | None = None) -> dict[str, Any]:
    # Both pairing and previews use only facts available at the requested cutoff.
    parts = [part for part in event.parts if part.record.ts and window.ended(part.record.ts)]
    projection = raw_events._project(event, parts, scoped=True)
    uses = [part for part in parts if part.direction == "use"]
    results = [part for part in parts if part.direction != "use"]
    independent = event.protocol == "codex_patch"
    anomalies = projection["anomalies"]
    unambiguous = event.addressable and not any(a in anomalies for a in (
        "duplicate_use", "duplicate_result", "out_of_order", *(() if independent else ("missing_call_id",))))
    outer = bool(action and action.detail.get("code_host_intents")) or (
        len(uses) == 1 and uses[0].payload.get("name") in ("exec", "functions.exec", "functions"))
    basis, success = "no_return_at_cutoff", None
    if not unambiguous:
        status, basis = "ambiguous", "native_pairing_ambiguity"
    elif independent:
        status, basis = "independent_event", "independent_patch_observation_not_call_pair"
        if len(results) == 1:
            payload = results[0].payload
            success = False if raw_events._failed(payload) else True if payload.get("success") is True else None
    elif len(uses) != 1:
        status, basis = "returned_unknown", "no_unique_request_at_cutoff"
    elif not results:
        status = "pending"
    else:
        payload = results[0].payload
        # Parsed Action.ok belongs to this exact native call, not to nested code.
        action_returned = bool(action and _time(action.ts) and action.done_ts and window.ended(action.done_ts)
                               and _time(action.done_ts) >= _time(action.ts))
        if raw_events._failed(payload):
            success, basis = False, "native_structured_failure"
        elif action_returned and action.ok is not None:
            success, basis = action.ok is True, "same_native_call_action_ok"
        elif event.protocol == "cc":
            success, basis = True, "cc_tool_result_default_non_error"
        elif any(p.get("success") is True or type(p.get("exit_code")) is int and p["exit_code"] == 0
                 for p in [payload] + ([payload["output"]] if isinstance(payload.get("output"), dict) else [])):
            success, basis = True, "native_structured_success"
        else:
            basis = "returned_without_success_status"
        status = "returned_success" if success is True else "returned_failed" if success is False else "returned_unknown"
    return {
        "call_return": {"status": status, "unambiguous": unambiguous, "success": success,
                        "basis": basis, "subject": "recorded_outer_call" if outer else
                        "independent_patch_observation" if independent else "recorded_native_call",
                        "nested_execution": "unverified" if outer else "not_inferred",
                        "effect_certified": False,
                        "note": "调用回执状态不等于目标文件效应、净变化、内部调用成功或行为验证。"},
        "native_io": {"source": projection["source"], "protocol": event.protocol,
                      "call_id": event.call_id, "native_status": projection["status"],
                      "anomalies": anomalies, "request_total": len(uses), "result_total": len(results),
                      "requests": [_part_preview(part, current, window) for part in uses[:2]],
                      "results": [_part_preview(part, current, window) for part in results[:2]],
                      "parts_omitted": max(0, len(uses) - 2) + max(0, len(results) - 2)}}


def _related_page(rows: list[dict[str, Any]], offset: int, limit: int) -> dict[str, Any]:
    if type(limit) is not int or not 0 <= limit <= 200:
        raise ValueError("related_limit 必须在 0–200 之间")
    page = temporal._page(rows, offset, max(1, limit))
    if limit == 0:
        page.update(limit=0, rows=[], remaining=max(0, len(rows) - offset), next_offset=None)
    return page


def _related_inventory(ledger: atoms.Ledger, current: dict[str, Any],
                       associated: set[tuple[Any, ...]], covered: set[tuple[Any, ...]],
                       native_covered: set[tuple[str, str]], offset: int, limit: int) -> dict[str, Any]:
    """Mechanical remainder of registered calls, not another effect detector.

    Use the same cached native index and per-part time projection as events.
    No per-result read_record calls or repeated 40-row rescans are needed. An
    earlier request can associate an in-range result, but a later result never
    associates an earlier request. Whole-line refs cannot authenticate a block.
    """
    window = temporal.Window.parse(current["at"], current.get("since_ts"))
    normalized = current["key"].replace("\\", "/").casefold()
    basename = normalized.rsplit("/", 1)[-1]
    data = raw_events._scan(ledger)
    links: dict[tuple[str, int], list[tuple[Any, ...]]] = {}
    for address in associated | covered:
        links.setdefault(address[:2], []).append(address)

    def matches(value: Any) -> bool:
        text = store.readable(value).replace("\\", "/").casefold()
        return normalized in text or bool(basename and basename in text)

    def bindings(event, parts) -> set[tuple[Any, ...]]:
        found = set()
        for part in parts:
            if part.direction != "use":
                continue
            for address in links.get((_source(event.source), part.record.line), []):
                _, _, block, call_id = address
                # A precise use block or explicit native ID is required. Never
                # remove another call just because it shares a physical line.
                if (type(block) is int and block == part.block and
                        (not call_id or call_id == event.call_id)) or (
                        block is None and call_id and call_id == event.call_id):
                    found.add(address)
        return found

    def locator(part) -> dict[str, Any]:
        result = {"ref": part.record.ref, "line": part.record.line, "ts": part.record.ts,
                "block": part.block, "pointer": part.pointer, "direction": part.direction,
                "failed": raw_events._failed(part.payload) if part.direction != "use" else None,
                "fields": deepcopy(part.fields),
                "query": {"tool": "record", "args": {"ref": part.record.ref}, "scope": deepcopy(current)}}
        if part.record.ts and window.contains(part.record.ts):
            text = store.readable(part.payload)
            position = text.casefold().find(basename) if basename else -1
            start = max(0, position - 60) if position >= 0 else 0
            result.update(preview=text[start:start + 240], preview_kind="decoded_native_payload_excerpt")
        return result

    rows, undated = [], []
    excluded = 0
    categories = {"shell": 0, "unknown_tool": 0, "other_native": 0, "readonly": 0}
    statuses: dict[str, int] = {}
    readonly_tools: dict[str, int] = {}
    actions_by_use: dict[tuple[str, int], list[atoms.Action]] = {}
    for owner in ledger.agents.values():
        for action in owner.actions:
            address = _action_address(action)
            if address:
                actions_by_use.setdefault(address[:2], []).append(action)
    presentations = {}
    for event in data["events"]:
        known = [p for p in event.parts if p.record.ts and window.ended(p.record.ts)]
        visible = [p for p in known if window.contains(p.record.ts)]
        for part in event.parts:
            if part.record.ts is None and matches(part.payload):
                entry = locator(part)
                entry.pop("query")  # Unknown-time locators cannot inherit a cutoff as evidence.
                undated.append({**entry, "source": os.path.basename(event.source), "time_status": "unknown"})
        if not visible:
            continue
        matched = [p for p in visible if matches(p.payload)]
        earlier = [p for p in known if p.direction == "use" and not window.contains(p.record.ts)
                   and matches(p.payload)]
        addresses = bindings(event, known)
        if not matched and not earlier and not addresses & associated:
            continue
        projected = raw_events._project(event, visible, scoped=True)
        known_projection = raw_events._project(event, known, scoped=True)
        unambiguous = event.addressable and not any(
            anomaly in known_projection["anomalies"] for anomaly in ("duplicate_use", "duplicate_result", "out_of_order"))
        if unambiguous and (addresses & covered or
                            (_source(event.source), projected["id"]) in native_covered):
            excluded += 1
            continue
        tool = projected["tool"]
        if tool in ("Read", "Grep", "Glob") and unambiguous:
            category = "readonly"
            readonly_tools[tool] = readonly_tools.get(tool, 0) + 1
        elif tool in ("Bash", "bash", "exec_command", "functions.exec_command", "shell_command", "run_shell_command"):
            category = "shell"
        elif tool in ("Write", "Edit", "MultiEdit", "Task", "Agent", "apply_patch", "patch_apply_end"):
            category = "other_native"
        else:
            category = "unknown_tool"
        categories[category] += 1
        statuses[projected["status"]] = statuses.get(projected["status"], 0) + 1
        matched_actions = [action for part in known if part.direction == "use"
                           for action in actions_by_use.get((_source(event.source), part.record.line), [])
                           if _matches_action(event, part, action)]
        action = matched_actions[0] if len(matched_actions) == 1 else None
        # Existing collector signal only, scoped to the call, never this target's
        # effect. A future result's Action metadata must not change early order.
        write_capable = bool(unambiguous and action and action.done_ts and window.ended(action.done_ts)
                             and action.detail.get("write_capable") is True)
        presentations[projected["id"], projected["source_path"]] = (event, action)
        rows.append({"id": projected["id"], "source": projected["source"],
                     "protocol": projected["protocol"], "call_id": projected["call_id"], "tool": tool,
                     "status": projected["status"], "category": category,
                     "classification": "unclassified_related", "effect_status": "unknown",
                     "agent": None, "author_status": "unknown", "source_agents": projected["agents"],
                     "reference_status": projected["reference_status"], "anomalies": projected["anomalies"],
                     "association": "lexical_mention_not_effect" if matched else
                                    "earlier_request_mention_not_effect" if earlier else "parsed_association_not_effect",
                     "pointers": [locator(p) for p in visible],
                     "matched_parts": [{"ref": p.record.ref, "pointer": p.pointer} for p in matched],
                     "write_capable": write_capable, "signal_scope": "call_not_target_effect",
                     "ordering_basis": "existing_action_detail_write_capable" if write_capable else "no_write_capable_signal",
                     "_source_path": projected["source_path"],
                     "semantic_checked": False})
    rows.sort(key=lambda row: (not row["write_capable"], row["category"] == "readonly",
                              min((p["ts"], row["source"], p["line"], p["block"] or 0) for p in row["pointers"]),
                              row["id"]))
    undated.sort(key=lambda row: (row["source"], row["line"], row["block"] or 0))
    non_native = sum(1 for item in data["unknown"] if item["_record"].ts
                     and window.contains(item["_record"].ts) and matches(raw_events._unknown_payload(item)))
    page = _related_page(rows, offset, limit)
    for row in page["rows"]:
        event, action = presentations[row["id"], row["_source_path"]]
        row.update(_call_presentation(event, window, current, action))
        row.pop("_source_path")

    def query(start):
        return {"tool": "changes", "scope": deepcopy(current),
                "args": {"related_offset": start, "related_limit": limit}}

    undated_page = _related_page(undated, offset, limit)
    return {**page, "category_counts": categories, "status_counts": statuses,
            "review_required_total": page["total"] - categories["readonly"],
            "ordering": "write_capable_first_then_non_readonly_then_recorded_time",
            "count_only": limit == 0,
            "resume_query": {"tool": "changes", "scope": deepcopy(current),
                             "args": {"related_offset": offset, "related_limit": 8}} if limit == 0 else None,
            "readonly": {"total": categories["readonly"], "tool_counts": readonly_tools,
                         "display": "collapsed", "included_in_total_and_pagination": True},
            "excluded_covered_total": excluded,
            "query": query(offset), "next_query": query(page["next_offset"]) if page["next_offset"] is not None else None,
            "raw_query": {"tool": "events", "scope": deepcopy(current)},
            "undated": {**undated_page, "cutoff_evidence": False,
                        "query": query(offset), "next_query": query(undated_page["next_offset"])
                        if undated_page["next_offset"] is not None else None},
            "non_native_mentions": {"total": non_native, "native_calls": False,
                                    "query": {"tool": "events", "scope": deepcopy(current)}},
            "source_count": data["source_count"], "gaps": data["gaps"],
            "registered_scan_ok": bool(data["source_count"]) and not data["gaps"],
            "counts_scope": "registered_sources_only",
            "complete": False, "causal_complete": False,
            "note": "全范围注册原生调用余项，按调用身份扣除已列修改/候选/观察的依据；已有write_capable信号只用于排序，非目标效应证明；只读调用后排并可折叠。"
                    "词法或关联命中不是写者、候选写入或修改认证；返回状态也不是脚本效应证明。"
                    "未注册来源不在本清单，0余项不等于0修改、0缺陷或调查完备；未知时间定位不算截止证据。"}


def native_effects(ledger: atoms.Ledger, current_scope: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Independent patch effects for one file or all files in a pool time scope.

    ``raw_only`` means no parsed Action covers the same source/line/target, not
    that the source's registered agent is the writer. State consumers may place
    an unknown-state barrier at observation_ts, never before it: use time and
    the actual mutation time are unknown even for success=true.
    """
    if not isinstance(current_scope, dict) or current_scope.get("kind") not in ("file", "pool"):
        raise ValueError("原生效应需要 file 或 pool scope")
    window = temporal.Window.parse(current_scope.get("at"), current_scope.get("since_ts"))
    _check_sources(ledger)
    target = None
    if current_scope["kind"] == "file":
        if not current_scope.get("key"):
            raise ValueError("file scope 缺 key")
        target = temporal.resolve_file(ledger, current_scope["key"])
    covered = {(_source(action.src[0]), line + 1, _path(ref.path))
               for agent in ledger.agents.values() for action in agent.actions if action.src
               for ref in action.files if ref.op != "read"
               for line in {action.src[1], action.src[2]} if line is not None}
    native = raw_events.inventory(ledger)
    rows, gaps = [], deepcopy(native.get("gaps") or [])
    for event in native["events"]:
        if event.get("protocol") != "codex_patch":
            continue
        for part in event.get("results") or []:
            try:
                original = store.read_record(event["source_path"], part["line"],
                                             source=store.source_spec(ledger, event["source_path"]))
            except (OSError, UnicodeError, ValueError) as exc:
                gaps.append({"source": event["source"], "line": part["line"], "reason": str(exc)})
                continue
            payload = original.value.get("payload") if isinstance(original.value, dict) else None
            changes = payload.get("changes") if isinstance(payload, dict) else None
            if not isinstance(changes, dict):
                continue
            for path, change in changes.items():
                if not isinstance(path, str) or not isinstance(change, dict):
                    continue
                canonical = _path(path)
                if target is not None and canonical != target:
                    continue
                stamp = original.ts
                if stamp is None:
                    gaps.append({"source": event["source"], "line": part["line"], "path": canonical,
                                 "reason": "undated_native_effect", "evidence": [original.ref]})
                    continue
                if not window.contains(stamp):
                    continue
                confirmed = (payload.get("success") is True and not raw_events._failed(payload)
                             and payload.get("conditional") is not True and change.get("conditional") is not True
                             and change.get("type") in ("add", "update", "delete")
                             and event.get("reference_status") == "addressable")
                identity = "native-change:" + _digest([event["id"], original.ref, canonical])
                rows.append({"id": identity, "event_id": event["id"], "path": canonical,
                    "status": "confirmed_change" if confirmed else "candidate_effect",
                    "agent": None, "author_status": "unknown", "source_agents_are_not_authors": True,
                    "source_path": event["source_path"], "source_line": part["line"],
                    "raw_only": (_source(event["source_path"]), part["line"], canonical) not in covered,
                    "use_ts": None, "done_ts": stamp, "observation_ts": stamp,
                    "time_basis": "native_effect_observation", "changed_time_unknown": True,
                    "tool": "patch_apply_end", "evidence": [original.ref],
                    "evidence_scope": {"kind": "file", "key": canonical, "at": window.at, "since_ts": None},
                    "operations": ["delete" if change.get("type") == "delete" else "write"],
                    "native": {"source": event["source"], "line": part["line"], "call_id": event.get("call_id"),
                               "status": event.get("status"), "success": payload.get("success")},
                    "summary": "独立原生补丁事件确认目标写入/删除；不绑定外层call或推定作者/实际修改时刻" if confirmed else
                               "原生目标效应未确认（失败、条件、缺成功状态或来源歧义），仅在观察时刻立未知屏障",
                    "semantic_checked": False})
    rows.sort(key=lambda row: (row["observation_ts"], row["id"]))
    return rows, gaps


def native_diff(ledger: atoms.Ledger, row: dict[str, Any], max_chars: int | None = None) -> dict[str, Any] | None:
    """An independently located native delta, never an inferred full snapshot.

    Keep large patch bodies out of the modification inventory. Consumers ask
    for this projection explicitly; the raw reference opens the whole event.
    """
    from . import text_window
    text_window.validate(max_chars=max_chars)
    ref = next(iter(row.get("evidence") or []), None)
    if not isinstance(ref, str):
        return None
    original = store.resolve(ledger, ref)
    payload = original.value.get("payload") if isinstance(original.value, dict) else None
    native = row.get("native") or {}
    if (not isinstance(payload, dict) or original.value.get("type") != "event_msg"
            or payload.get("type") != "patch_apply_end" or payload.get("call_id") != native.get("call_id")
            or payload.get("success") != native.get("success")):
        raise ValueError("原生补丁身份或回执状态不匹配，未提供推断diff")
    changes = payload.get("changes")
    matches = [value for path, value in changes.items() if isinstance(path, str) and _path(path) == row.get("path")] if isinstance(changes, dict) else []
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise ValueError("原生补丁目标未唯一定位")
    delta = matches[0].get("unified_diff")
    if not isinstance(delta, str):
        return None  # Add/delete may record only a content body; raw still opens.
    return {"ts": row["observation_ts"], "effect_ts": None, "ref": ref, "agent": None,
            "event_id": row["id"], "author_status": "unknown", "changed_time_unknown": True,
            "basis": "native_effect_observation", "effect_status": row["status"],
            "diff": delta[:max_chars], "diff_chars": len(delta), "truncated": max_chars is not None and len(delta) > max_chars,
            "native": deepcopy(native), "semantic_checked": False,
            "note": "原生事件的目标补丁；时间为观察可用时刻，不认证外层作者、完整前后状态或缺陷原因。"
                    + ("回执未确认执行：此处仅为所报补丁，不能当实际已生效差异。" if row["status"] != "confirmed_change" else "")}


@raw_events.reuse_scans
def build(ledger: atoms.Ledger, current_scope: dict[str, Any], offset: int = 0,
          limit: int = 40, related_offset: int = 0, related_limit: int = 8) -> dict[str, Any]:
    """Return the selected page only after discovering the whole bounded inventory."""
    if not isinstance(current_scope, dict) or current_scope.get("kind") != "file" or not current_scope.get("key"):
        raise ValueError("修改清单需要明确 file scope/key")
    window = temporal.Window.parse(current_scope.get("at"), current_scope.get("since_ts"))
    temporal._page([], offset, limit)
    _related_page([], related_offset, related_limit)
    _check_sources(ledger)
    canonical = temporal.resolve_file(ledger, current_scope["key"])
    current = {**deepcopy(current_scope), "key": canonical, "at": window.at, "since_ts": window.since}
    evidence_scope = {"kind": "file", "key": canonical, "at": window.at, "since_ts": None}
    rows: list[dict[str, Any]] = []
    all_effects: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    pointers: dict[tuple[str, int], store.Record | None] = {}
    covered: dict[tuple[str, int, str], dict[str, Any]] = {}
    associated: set[tuple[Any, ...]] = set()
    row_addresses: dict[str, set[tuple[Any, ...]]] = {}
    row_native_ids: dict[str, set[tuple[str, str]]] = {}
    row_actions: dict[str, atoms.Action] = {}

    def record(path: str, line: int) -> store.Record | None:
        key = (_source(path), line)
        if key not in pointers:
            try:
                pointers[key] = store.read_record(path, line, source=store.source_spec(ledger, path))
            except (OSError, UnicodeError, ValueError) as exc:
                pointers[key] = None
                gaps.append({"source": path, "line": line, "reason": str(exc)})
        return pointers[key]

    def evidence(action: atoms.Action, returned: bool) -> list[str]:
        values = []
        if action.src:
            for line in (action.src[1], action.src[2] if returned else None):
                original = record(action.src[0], line + 1) if line is not None else None
                if original and original.ts and window.ended(original.ts):
                    values.append(original.ref)
        return list(dict.fromkeys(values))

    for agent in ledger.agents.values():
        for action in agent.actions:
            refs = [r for r in action.files if _path(r.path) == canonical and r.op != "read"]
            reads = [r for r in action.files if _path(r.path) == canonical and r.op == "read"]
            candidates = {_path(p) for p in _candidate_paths(action)}
            if not refs and not reads and canonical not in candidates:
                continue
            use, done = _iso(_time(action.ts)), _iso(_time(action.done_ts))
            if not use:
                gaps.append({"agent": agent.id, "seq": action.seq, "path": canonical,
                             "reason": "unknown_use_time"})
                continue
            if not window.ended(use):
                continue
            returned = bool(done and use <= done and window.ended(done))
            address = _action_address(action)
            if returned and address:
                associated.add(address)
            raw_refs = evidence(action, returned)
            if returned and action.src and action.src[2] is None:
                gaps.append({"source": action.src[0], "agent": agent.id, "seq": action.seq,
                             "path": canonical, "reason": "missing_result_location"})
            for ref in reads if returned and action.ok is True else []:
                proof = proof_payload(ref.proof)
                reliable = (ref.ev.full and isinstance(ref.ev.content, str) and not ref.ev.dep
                            and not ref.ev.conditional and not ref.observation_uncertain
                            and proof["execution"] == "confirmed" and proof["operation_basis"] in CONFIRMED_BASES
                            and proof["delivery"] == "content" and proof["snapshot"] == "full")
                result = record(action.src[0], action.src[2] + 1) if action.src and action.src[2] is not None else None
                if reliable and result and result.ts and window.ended(result.ts):
                    snapshots.append({"use_ts": use, "done_ts": done, "content": ref.ev.content,
                                      "evidence": raw_refs, "result_ref": result.ref, "block": action.blk,
                                      "address": address})
            if not refs and canonical not in candidates:
                continue
            if not returned:
                original = record(action.src[0], action.src[1] + 1) if action.src and action.src[1] is not None else None
                if canonical not in candidates and not _native_target(original, action, canonical):
                    continue
            confirmed_refs = [r for r in refs if returned and action.ok is True and not r.ev.conditional
                              and proof_payload(r.proof)["execution"] == "confirmed"
                              and proof_payload(r.proof)["operation_basis"] in CONFIRMED_BASES]
            confirmed = bool(confirmed_refs and raw_refs and action.src and action.src[2] is not None)
            identity = atoms.event_id_for_action(agent, action)
            row = {"id": identity, "event_id": identity,
                   "status": "confirmed_change" if confirmed else "candidate_effect", "agent": agent.id if confirmed else None,
                   "author_status": "operation_actor" if confirmed else "unknown", "source_agents": [agent.id],
                   "operation_basis": "code_host_intent" if action.detail.get("code_host_intents") else "parsed_operation",
                   "use_ts": use, "done_ts": done if returned else None, "tool": action.tool,
                   "evidence": raw_refs, "evidence_scope": deepcopy(evidence_scope),
                   "legacy_ref": atoms.format_ref(action.seq, ledger.locs.get(action.seq)),
                   "operations": sorted({r.op for r in refs}) if returned else [],
                   "summary": f"{action.tool}: " + ("已确认写入/删除操作；是否语义修复待判" if confirmed else "效应未决，不认证实际改动或问题作者"),
                   "semantic_checked": False}
            all_effects.append({"row": row, "refs": confirmed_refs})
            row_actions[identity] = action
            row_addresses[identity] = {address} if address else set()
            if window.contains(use) or returned and window.contains(done):
                rows.append(row)
            if action.src:
                for line in (action.src[1], action.src[2] if returned else None):
                    if line is not None:
                        covered[(_source(action.src[0]), line + 1, canonical)] = row

    native_rows, native_gaps = native_effects(ledger, {**current, "since_ts": None})
    gaps.extend(native_gaps)
    for row in native_rows:
        previous = covered.get((_source(row["source_path"]), row["source_line"], canonical))
        if previous is not None:
            row_native_ids.setdefault(previous["id"], set()).add((_source(row["source_path"]), row["event_id"]))
            previous.setdefault("native_corroboration", []).append(deepcopy(row["native"]))
            previous["evidence"] = list(dict.fromkeys(previous["evidence"] + row["evidence"]))
            if row["status"] == "confirmed_change" and previous["status"] != "confirmed_change":
                previous.update(status="confirmed_change", agent=None, author_status="unknown", summary=row["summary"])
            elif row["status"] != "confirmed_change" and previous["status"] == "confirmed_change":
                previous.update(status="candidate_effect", summary="原生事件失败或确认依据不足，与解析操作冲突；不认证写入")
                gaps.append({"source": row["native"]["source"], "line": row["source_line"], "reason": "native_action_status_conflict"})
            continue
        all_effects.append({"row": row, "refs": []})
        row_native_ids[row["id"]] = {(_source(row["source_path"]), row["event_id"])}
        if window.contains(row["observation_ts"]):
            rows.append(row)

    # Full observations bound an interval; they are not individual write events.
    snapshots.sort(key=lambda r: (r["use_ts"], r["done_ts"], r["result_ref"], r["block"]))
    for before, after in zip(snapshots, snapshots[1:]):
        if before["content"] == after["content"] or not window.contains(after["done_ts"]):
            continue
        if before["done_ts"] >= after["use_ts"]:
            gaps.append({"path": canonical, "reason": "snapshot_order_unconfirmed",
                         "evidence": list(dict.fromkeys(before["evidence"] + after["evidence"]))})
            continue
        between = [effect for effect in all_effects
                   if (effect["row"].get("done_ts") or window.at) >= before["use_ts"]
                   and (effect["row"].get("use_ts") or effect["row"].get("done_ts") or "") <= after["done_ts"]]
        accounted = False
        if len(between) == 1:
            effect = between[0]
            row, refs = effect["row"], effect["refs"]
            separated = (row.get("use_ts") and row.get("done_ts")
                         and before["done_ts"] < row["use_ts"] <= row["done_ts"] < after["use_ts"])
            if row["status"] == "confirmed_change" and separated and len(refs) == 1:
                accounted = _apply_single(before["content"], refs[0]) == after["content"]
        if accounted:
            continue
        crossing = window.since is not None and before["use_ts"] < window.since
        identity = "observed-change:" + _digest([canonical, before["result_ref"], before["block"],
                                                after["result_ref"], after["block"]])
        row_addresses[identity] = {item["address"] for item in (before, after) if item["address"]}
        def side(item):
            return {key: deepcopy(item[key]) for key in ("use_ts", "done_ts", "evidence")}
        rows.append({"id": identity, "event_id": identity, "status": "observed_change", "agent": None,
                     "author_status": "unknown", "use_ts": None, "done_ts": None,
                     "observed_at": after["done_ts"], "change_time": None, "tool": "full_read_observations",
                     "operations": [], "evidence": list(dict.fromkeys(before["evidence"] + after["evidence"])),
                     "evidence_scope": deepcopy(evidence_scope),
                     "observation_interval": {"since": before["use_ts"], "at": after["done_ts"],
                                              "before": side(before), "after": side(after)},
                     "boundary_relation": "crosses_since_boundary" if crossing else "within_scope",
                     "occurred_in_scope": "not_proven" if crossing else "bounded_interval",
                     "unassigned_effect_ids": [effect["row"]["id"] for effect in between],
                     "summary": "两次可靠完整Read内容不同；变化仅限观察区间，不能归给单次已证写入、唯一作者或精确时刻"
                                + ("；区间跨越查询起点，不能声称确定在修复期发生" if crossing else ""),
                     "semantic_checked": False})
    rows.sort(key=lambda r: (r.get("observed_at") or r.get("done_ts") or r.get("use_ts") or "", r["id"]))
    related = _related_inventory(ledger, current, associated,
                                 set().union(*(row_addresses.get(row["id"], set()) for row in rows)),
                                 set().union(*(row_native_ids.get(row["id"], set()) for row in rows)),
                                 related_offset, related_limit)
    page = temporal._page(rows, offset, limit)
    # Enrich only delivered rows; the native index is shared/cached and no
    # payload is copied into the full inventory or used to infer a new effect.
    native = raw_events._scan(ledger)
    by_line: dict[tuple[str, int], list[Any]] = {}
    for event in native["events"]:
        for part in event.parts:
            if part.record.ts and window.ended(part.record.ts):
                by_line.setdefault((_source(event.source), part.record.line), []).append(event)
    for row in page["rows"]:
        action = row_actions.get(row["id"])
        address = _action_address(action) if action else None
        candidates = by_line.get(address[:2], []) if address else by_line.get(
            (_source(row["source_path"]), row["source_line"]), []) if row.get("source_path") else []
        matches = [event for event in candidates if action and any(
            _matches_action(event, part, action) for part in event.parts if part.direction == "use")]
        if not action:
            matches = [event for event in candidates if event.protocol == "codex_patch"
                       and event.call_id == (row.get("native") or {}).get("call_id")]
        elif not matches and row.get("native_corroboration"):
            # An Action backed by an independent patch record is still only
            # an observation: do not fabricate a request for that record.
            matches = [event for event in candidates if event.protocol == "codex_patch"
                       and event.call_id == action.tuid]
            if matches:
                action = None
        matches = list({id(event): event for event in matches}.values())
        if len(matches) == 1:
            row.update(_call_presentation(matches[0], window, current, action))
        elif action:
            row.update(call_return={"status": "ambiguous", "unambiguous": False, "success": None,
                                    "basis": "native_call_not_uniquely_located", "effect_certified": False},
                       native_io={"requests": [], "results": [], "request_total": None, "result_total": None})
    return {"schema": SCHEMA, "scope": current, **page,
            "gaps": gaps, "complete": False, "causal_complete": False,
            "unclassified_related": related,
            "note": "已解析操作、独立原生效应与完整快照差异分列；确认写入不保证净内容变化或语义修复。"
                    "observed_change没有唯一作者/精确修改时间，跨起点区间不证明修复期发生；不宣称穷尽所有修改。"}
