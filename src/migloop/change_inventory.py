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
                original = store.read_record(event["source_path"], part["line"])
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


def build(ledger: atoms.Ledger, current_scope: dict[str, Any], offset: int = 0,
          limit: int = 40) -> dict[str, Any]:
    """Return the selected page only after discovering the whole bounded inventory."""
    if not isinstance(current_scope, dict) or current_scope.get("kind") != "file" or not current_scope.get("key"):
        raise ValueError("修改清单需要明确 file scope/key")
    window = temporal.Window.parse(current_scope.get("at"), current_scope.get("since_ts"))
    temporal._page([], offset, limit)
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

    def record(path: str, line: int) -> store.Record | None:
        key = (_source(path), line)
        if key not in pointers:
            try:
                pointers[key] = store.read_record(path, line)
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
                                      "evidence": raw_refs, "result_ref": result.ref, "block": action.blk})
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
            identity = atoms.event_id(ledger, agent.id, action.seq) or "operation:" + _digest(
                [canonical, raw_refs, action.tuid, action.blk])
            row = {"id": identity, "event_id": identity,
                   "status": "confirmed_change" if confirmed else "candidate_effect", "agent": agent.id,
                   "use_ts": use, "done_ts": done if returned else None, "tool": action.tool,
                   "evidence": raw_refs, "evidence_scope": deepcopy(evidence_scope),
                   "legacy_ref": atoms.format_ref(action.seq, ledger.locs.get(action.seq)),
                   "operations": sorted({r.op for r in refs}) if returned else [],
                   "summary": f"{action.tool}: " + ("已确认写入/删除操作；是否语义修复待判" if confirmed else "效应未决，不认证实际改动或问题作者"),
                   "semantic_checked": False}
            all_effects.append({"row": row, "refs": confirmed_refs})
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
            previous.setdefault("native_corroboration", []).append(deepcopy(row["native"]))
            previous["evidence"] = list(dict.fromkeys(previous["evidence"] + row["evidence"]))
            if row["status"] == "confirmed_change" and previous["status"] != "confirmed_change":
                previous.update(status="confirmed_change", agent=None, author_status="unknown", summary=row["summary"])
            elif row["status"] != "confirmed_change" and previous["status"] == "confirmed_change":
                previous.update(status="candidate_effect", summary="原生事件失败或确认依据不足，与解析操作冲突；不认证写入")
                gaps.append({"source": row["native"]["source"], "line": row["source_line"], "reason": "native_action_status_conflict"})
            continue
        all_effects.append({"row": row, "refs": []})
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
    return {"schema": SCHEMA, "scope": current, **temporal._page(rows, offset, limit),
            "gaps": gaps, "complete": False, "causal_complete": False,
            "unclassified_related": {"query": {"tool": "events", "scope": current},
                                     "note": "纯提及/未分类原文另查，不升级为候选写者"},
            "note": "已解析操作、独立原生效应与完整快照差异分列；确认写入不保证净内容变化或语义修复。"
                    "observed_change没有唯一作者/精确修改时间，跨起点区间不证明修复期发生；不宣称穷尽所有修改。"}
