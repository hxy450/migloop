"""Conservative as-of replay for diffs/provenance. Never slices final versions.

Only completed, confirmed effects may restore state. Pending, conditional and
opaque writes are barriers. Native patch requests stay accessible in raw records
regardless of whether a state can be reconstructed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

from . import atoms, change_inventory, transcript_store
from .evidence import CONFIRMED_BASES, proof_payload
from .filestory import EXTERNAL, OUTBAND, Ev, build_stories, line_origins
from .temporal import Window, resolve_file
from .time_scope import _iso, _time

_SHELL_TOOLS = {"bash", "powershell", "exec", "exec_command", "shell_command", "run_shell_command"}
_OPAQUE_SIGNALS = ("unresolved", "unknown_scripts", "unsupported_execution")


def _execution_window(ledger: atoms.Ledger, action: atoms.Action, agent: str, window: Window) -> dict[str, Any] | None:
    """Collector-declared opacity, never path mentions or an inferred writer."""
    if action.tool.casefold().split(".")[-1] not in _SHELL_TOOLS:
        return None
    signals = [key for key in _OPAQUE_SIGNALS if action.detail.get(key)]
    if not signals:
        return None
    start, end = _iso(_time(action.ts)), _iso(_time(action.done_ts))
    if start and not window.ended(start):
        return None
    completed = bool(start and end and start <= end and window.ended(end))
    identity = hashlib.sha256(json.dumps([agent, action.seq, action.tuid, start],
                                        ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    return {"id": "unclassified-execution:" + identity, "scope": "pool", "tool": action.tool,
            "use_ts": start, "done_ts": end if completed else None,
            "time_status": "recorded" if start else "unknown",
            "status": ("returned" if action.ok is True else "failed_or_unknown") if completed else "pending_or_unknown",
            "signals": signals if completed or not start else ["incomplete_or_opaque_execution"],
            "agent": None, "author_status": "unknown", "effect_status": "unclassified",
            "call_id": action.tuid, "ref": atoms.format_ref(action.seq, ledger.locs.get(action.seq)) if action.src else None,
            "note": "不透明执行可能影响池内内容；这是不确定窗口，不证明写入、修改时刻或作者"}


def _dependency_paths(events: list[Ev], path: str | None) -> set[str]:
    dependencies: dict[str, set[str]] = {}
    for event in events:
        dependencies.setdefault(event.path, set()).update(
            ([event.src] if event.src else []) + list(event.sources))
    selected = {path} if path is not None else set(dependencies)
    pending = list(selected)
    while pending:
        for source in dependencies.get(pending.pop(), ()):
            if source not in selected:
                selected.add(source)
                pending.append(source)
    return selected


def replay(ledger: atoms.Ledger, at: str, path: str | None = None) -> tuple[dict, dict, list]:
    window = Window.parse(at)
    events, owners, gaps, execution_windows = [], {}, [], []
    for agent in ledger.agents.values():
        for action in agent.actions:
            opaque = _execution_window(ledger, action, agent.id, window)
            if opaque:
                execution_windows.append(opaque)
            start, done = _iso(_time(action.ts)), _iso(_time(action.done_ts))
            possible = (set(action.detail.get("touched") or []) | set(action.detail.get("conditional") or [])
                        | set(action.detail.get("effect_candidates") or []))
            if not start:
                if action.files or possible:
                    gaps.append({"agent": agent.id, "seq": action.seq, "reason": "unknown invocation time",
                                 "paths": sorted({r.path for r in action.files} | possible)})
                continue
            if not window.ended(start):
                continue
            completed = bool(done and done >= start and window.ended(done))
            for ref in action.files:
                proof = proof_payload(ref.proof)
                confirmed = (completed and action.ok is True and proof["execution"] == "confirmed"
                             and proof["operation_basis"] in CONFIRMED_BASES and not ref.ev.conditional)
                if ref.op == "read":
                    confirmed = (confirmed and proof["delivery"] == "content" and not ref.ev.dep
                                 and not ref.observation_uncertain
                                 and (not ref.ev.full or proof["snapshot"] == "full"))
                if confirmed:
                    # Availability is the result timestamp, not the inferred
                    # mutation's invocation timestamp or a later sealed version.
                    event = replace(ref.ev, ts=done, use_ts=start, done_ts=done)
                    events.append(event)
                    owners[event.seq] = {"agent": agent.id, "seq": action.seq,
                                         "event_id": atoms.event_id_for_action(agent, action),
                                         "ref": atoms.format_ref(action.seq, ledger.locs.get(action.seq)),
                                         "event": event}
                elif ref.op != "read":
                    possible.add(ref.path)
            for candidate_path in possible:
                events.append(Ev(start, action.seq, "candidate", candidate_path, agent.id,
                                 use_ts=start, done_ts=done if completed else None))
                if completed:
                    events.append(Ev(done, action.seq, "candidate", candidate_path, agent.id, use_ts=start, done_ts=done))
    # One pool scan per replay, backed by the bounded raw source index. Do not
    # loop over file names or turn source registration into a writer identity.
    if transcript_store.sources(ledger):
        native, native_gaps = change_inventory.native_effects(ledger, {"kind": "pool", "at": window.at})
        for gap in native_gaps:
            paths = gap.get("paths") or ([gap["path"]] if isinstance(gap.get("path"), str) else [])
            gaps.append({**gap, "paths": list(paths), "scope": "paths" if paths else "pool",
                         "reason": gap.get("reason") or gap.get("error") or "原生源不可完整核验"})
        for row in native:
            if not row.get("raw_only"):
                continue
            observed = _iso(_time(row.get("observation_ts")))
            if observed is None or not window.ended(observed):
                continue
            seq = 10**18 + int(hashlib.sha256(row["id"].encode("utf-8")).hexdigest()[:15], 16)
            barrier = Ev(observed, seq, "candidate", row["path"], EXTERNAL,
                         use_ts=None, done_ts=observed)
            events.append(barrier)
            owners[seq] = {"agent": None, "seq": seq, "ref": next(iter(row.get("evidence") or []), None),
                           "event": barrier, "native_effect": row}
    # Project the pool uncertainty onto the requested file AND every source
    # needed to derive it. A cp must not restore A from an unbarriered old B.
    selected = _dependency_paths(events, path)
    events = [event for event in events if event.path in selected]
    owners = {seq: owner for seq, owner in owners.items() if owner["event"].path in selected}
    for opaque in execution_windows:
        if opaque["use_ts"] is None:
            gaps.append({"scope": "pool", "paths": [], "reason": "undated_unclassified_execution",
                         "unclassified_execution": opaque})
            continue
        for target in sorted(selected):
            seq = 10**20 + int(hashlib.sha256((opaque["id"] + target).encode("utf-8")).hexdigest()[:15], 16)
            for stamp in dict.fromkeys([opaque["use_ts"], opaque["done_ts"] or opaque["use_ts"]]):
                barrier = Ev(stamp, seq, "candidate", target, EXTERNAL,
                             use_ts=opaque["use_ts"], done_ts=opaque["done_ts"])
                events.append(barrier)
            owners[seq] = {"agent": None, "seq": seq, "ref": opaque["ref"], "event": barrier,
                           "unclassified_execution": opaque}
    # Equal completion timestamps and overlapping write windows cannot establish
    # a unique last writer. Put a barrier after each overlapping write finish.
    writes: dict[str, list[Ev]] = {}
    for event in events:
        if event.kind != "read":
            writes.setdefault(event.path, []).append(event)
    ambiguous = set()
    for write_path, rows in writes.items():
        ordered = sorted(rows, key=lambda e: (e.use_ts or e.ts, e.seq))
        active: list[Ev] = []
        for event in ordered:
            active = [p for p in active if (p.done_ts or "~") >= (event.use_ts or event.ts)]
            for prior in active:
                if (prior.agent, prior.seq) != (event.agent, event.seq):
                    ambiguous.add((write_path, prior.seq))
                    ambiguous.add((write_path, event.seq))
            active.append(event)
    for write_path, rows in writes.items():
        for event in rows:
            if event.kind != "candidate" and (write_path, event.seq) in ambiguous:
                events.append(Ev(event.ts, 10**15 + event.seq, "candidate", write_path, event.agent,
                                 use_ts=event.use_ts, done_ts=event.done_ts))
    # No collector scripts, directory attribution or source-body backfill here.
    return build_stories(events), owners, gaps


def query(ledger: atoms.Ledger, tool: str, path: str, at: str, *, since_ts: str | None = None,
          start: int | None = None, n: int | None = None, offset: int = 0, limit: int = 40,
          max_chars: int = 6000, window_offset: int = 0, window_limit: int = 4) -> dict[str, Any]:
    import os

    from .temporal import _page
    window = Window.parse(at, since_ts)
    _page([], window_offset, window_limit)
    if type(max_chars) is not int or not 1 <= max_chars <= 120000:
        raise ValueError("max_chars 必须在 1–120000 之间")
    if any(type(value) is not int or value < 1 for value in (start, n) if value is not None):
        raise ValueError("start/n 必须是正整数")
    canonical = resolve_file(ledger, path)
    for source, expected in ledger.source_stats.items():
        try:
            stat = os.stat(source)
            if (stat.st_mtime_ns, stat.st_size) == expected:
                continue
        except OSError:
            pass
        raise ValueError("源文件变化，须重建账本后才能重放状态；raw 时间查询仍可用")
    stories, owners, gaps = replay(ledger, window.at, path=canonical)
    story = stories.get(canonical)
    execution_windows = {item["id"]: item for owner in owners.values()
                         if (item := owner.get("unclassified_execution"))}
    execution_windows.update({item["id"]: item for gap in gaps
                              if (item := gap.get("unclassified_execution"))})
    execution_windows = sorted(execution_windows.values(), key=lambda item: (item["use_ts"] or "", item["id"]))
    window_page = _page(list(reversed(execution_windows)), window_offset, window_limit)
    displayed_windows = list(reversed(window_page.pop("rows")))
    window_page.update(omitted=window_page["total"] - len(displayed_windows),
                       ordering="newest_pages_chronological_within_page",
                       note="完整窗口参与状态重构；此分页仅控制展示，与主要rows分页独立")
    page_args = {"path": path, "at": at, "offset": offset, "limit": limit,
                 "window_offset": window_offset, "window_limit": window_limit}
    if tool == "diff":
        page_args["max_chars"] = max_chars
    if tool == "diff" and since_ts is not None:
        page_args["since_ts"] = since_ts
    for key, value in (("start", start), ("n", n)):
        if value is not None:
            page_args[key] = value
    window_page["query"] = {"tool": tool, "args": page_args}
    window_page["next_query"] = ({"tool": tool, "args": {**page_args, "window_offset": window_page["next_offset"]}}
                                  if window_page["next_offset"] is not None else None)
    # Snapshot time is the last reliable full body, not the last guessed write.
    observed_reads = {read.seq for read in story.reads if read.full and not read.dep and not read.observation_uncertain} if story else set()
    snapshots = [owner for owner in owners.values() if owner["event"].path == canonical
                 and isinstance(owner["event"].content, str)
                 and (owner["event"].kind == "wfull" or owner["event"].kind == "read" and owner["event"].seq in observed_reads)
                 and not any(item["use_ts"] and item["use_ts"] <= owner["event"].ts
                             and (item["done_ts"] is None or item["done_ts"] >= (owner["event"].use_ts or owner["event"].ts))
                             for item in execution_windows)]
    snapshot = max(snapshots, key=lambda owner: owner["event"].ts, default=None)
    result = {"schema": "migloop-time-state/1", "tool": tool, "path": canonical,
              "at": window.at, "since_ts": window.since, "known": False, "gaps": gaps,
              "known_basis": "registered_identified_history_reconstruction",
              "reconstruction_paths": sorted(stories),
              "current_state_certified": False,
              "snapshot_at": snapshot["event"].ts if snapshot else None,
              "snapshot_ref": snapshot["ref"] if snapshot else None,
              "unclassified_execution_windows": displayed_windows,
              "unclassified_execution_window_page": window_page,
              "native_effect_barriers": [owner["native_effect"] for owner in owners.values()
                                          if owner.get("native_effect") and owner["event"].path == canonical],
              "note": "known仅指注册、已识别历史的有界内容重构，不认证真实当前状态或完备效应清单；时间不是版本别名。"
                      "未知/条件/并发效应会断开状态；后续快照不倒灌至更早查询。"
                      "未解析原生补丁仅在记录观察时刻立未知屏障，不回推发起时刻或作者；后续可靠全文只恢复观察内容。"
                      "明确不透明shell执行是可恢复的内容不确定窗口，不是作者边或修改事件；后续完整快照须在窗口结束后才可重锚。"
                      "无明确不透明信号的未识别长尾仍属覆盖限制，不以0命中证明完整。归属是文本来源，不认证缺陷原因。"}
    if not story:
        return {**result, **_page([], offset, limit)}
    result["known"] = story.current_content is not None and not any(
        gap.get("scope") == "pool" or set(stories).intersection(gap.get("paths", [])) for gap in gaps)
    if tool == "diff":
        rows = []
        for version in story.versions:
            source = owners.get(version.seq)
            available = version.content_ts or version.ts
            if not window.contains(available):
                continue
            observed = version.sealed or version.source in (OUTBAND, "outband", "external")
            evidence_source = owners.get(version.content_seq) if observed else source
            rows.append({"ts": available, "effect_ts": version.ts,
                         "ref": evidence_source["ref"] if evidence_source else None,
                         "event_id": source.get("event_id") if source and not observed else None,
                         "agent": source["agent"] if source and not observed else None,
                         "basis": "observed_interval_not_single_writer" if observed else version.diff_kind,
                         "diff": (version.diff or "")[:max_chars],
                         "diff_chars": len(version.diff or ""),
                         "truncated": len(version.diff or "") > max_chars,
                         "note": "全文/原生补丁用 action(ref=...)；此处不把观测封口当单笔写入"})
        # Independent patch observations have no outer Action author and may
        # leave the full state unknown, but their exact raw delta is inspectable.
        for owner in owners.values():
            native = owner.get("native_effect")
            if native and native["path"] == canonical and window.contains(native["observation_ts"]):
                delta = change_inventory.native_diff(ledger, native, max_chars=max_chars)
                if delta is not None:
                    rows.append(delta)
        rows.sort(key=lambda row: (row["ts"], row.get("event_id") or row.get("ref") or ""))
        return {**result, **_page(rows, offset, limit)}
    if tool != "blame":
        raise ValueError("时间状态只支持 diff/blame")
    if since_ts is not None:
        raise ValueError("blame 是截止时刻的累计来源，不接受 since_ts")
    if not result["known"] or not story.versions:
        return {**result, **_page([], offset, limit)}
    versions = story.versions
    signatures = line_origins(story)[-1]
    rows = []
    for number, text in enumerate(story.current_content.splitlines(), 1):
        if start is not None and number < start or n is not None and number >= (start or 1) + n:
            continue
        origin = signatures[number - 1] if number <= len(signatures) else None
        version = versions[origin[1] - 1] if origin else None
        source = owners.get(version.seq) if version else None
        trusted = bool(origin and len(origin) == 2 and version and not version.sealed
                       and not version.state_gap and origin[0] not in (OUTBAND, EXTERNAL)
                       and source and source["event"].kind != "read")
        # A same-content Read after a candidate can reuse an old engine version.
        # It restores observed bytes, never pre-window writer attribution.
        if version and any(item["use_ts"] and version.ts <= (item["done_ts"] or window.at)
                           for item in execution_windows):
            trusted = False
        # First observed full overwrite is not proof this text originated there.
        if version and version.v == 1 and source and not source["event"].created:
            trusted = False
        rows.append({"line": number, "text": text, "agent": source["agent"] if trusted else None,
                     "event_id": source.get("event_id") if trusted else None,
                     "introduced_at": version.ts if trusted else None,
                     "ref": source["ref"] if trusted else None,
                     "status": "supported_text_origin" if trusted else "unknown_origin"})
    return {**result, **_page(rows, offset, limit)}


def render(data: dict[str, Any]) -> str:
    import json
    return "# 时间 " + data["tool"] + "\n" + json.dumps(data, ensure_ascii=False, indent=2)
