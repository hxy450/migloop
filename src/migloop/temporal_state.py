"""Conservative as-of replay for diffs/provenance. Never slices final versions.

Only completed, confirmed effects may restore state. Pending, conditional and
opaque writes are barriers. Native patch requests stay accessible in raw records
regardless of whether a state can be reconstructed.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from . import atoms
from .evidence import proof_payload, CONFIRMED_BASES
from .filestory import Ev, build_stories, line_origins, OUTBAND, EXTERNAL
from .temporal import Window, resolve_file
from .time_scope import _time, _iso


def replay(ledger: atoms.Ledger, at: str) -> tuple[dict, dict, list]:
    window = Window.parse(at)
    events, owners, gaps = [], {}, []
    for agent in ledger.agents.values():
        for action in agent.actions:
            start, done = _iso(_time(action.ts)), _iso(_time(action.done_ts))
            if not start:
                if action.files or action.detail.get("touched"):
                    gaps.append({"agent": agent.id, "seq": action.seq, "reason": "unknown invocation time",
                                 "paths": sorted({r.path for r in action.files} | set(action.detail.get("touched") or []))})
                continue
            if not window.ended(start):
                continue
            completed = bool(done and done >= start and window.ended(done))
            possible = (set(action.detail.get("touched") or []) | set(action.detail.get("conditional") or [])
                        | set(action.detail.get("effect_candidates") or []))
            for ref in action.files:
                proof = proof_payload(ref.proof)
                confirmed = (completed and action.ok is True and proof["execution"] == "confirmed"
                             and proof["operation_basis"] in CONFIRMED_BASES and not ref.ev.conditional)
                if confirmed:
                    # Availability is the result timestamp, not the inferred
                    # mutation's invocation timestamp or a later sealed version.
                    event = replace(ref.ev, ts=done, use_ts=start, done_ts=done)
                    events.append(event)
                    owners[event.seq] = {"agent": agent.id, "seq": action.seq,
                                         "ref": atoms.format_ref(action.seq, ledger.locs.get(action.seq)),
                                         "event": event}
                elif ref.op != "read":
                    possible.add(ref.path)
            for path in possible:
                events.append(Ev(start, action.seq, "candidate", path, agent.id,
                                 use_ts=start, done_ts=done if completed else None))
                if completed:
                    events.append(Ev(done, action.seq, "candidate", path, agent.id, use_ts=start, done_ts=done))
    # Equal completion timestamps and overlapping write windows cannot establish
    # a unique last writer. Put a barrier after each overlapping write finish.
    writes: dict[str, list[Ev]] = {}
    for event in events:
        if event.kind != "read":
            writes.setdefault(event.path, []).append(event)
    ambiguous = set()
    for path, rows in writes.items():
        ordered = sorted(rows, key=lambda e: (e.use_ts or e.ts, e.seq))
        active: list[Ev] = []
        for event in ordered:
            active = [p for p in active if (p.done_ts or "~") >= (event.use_ts or event.ts)]
            for prior in active:
                if (prior.agent, prior.seq) != (event.agent, event.seq):
                    ambiguous.add((path, prior.seq))
                    ambiguous.add((path, event.seq))
            active.append(event)
    for path, rows in writes.items():
        for event in rows:
            if event.kind != "candidate" and (path, event.seq) in ambiguous:
                events.append(Ev(event.ts, 10**15 + event.seq, "candidate", path, event.agent,
                                 use_ts=event.use_ts, done_ts=event.done_ts))
    # No collector scripts, directory attribution or source-body backfill here.
    return build_stories(events), owners, gaps


def query(ledger: atoms.Ledger, tool: str, path: str, at: str, *, since_ts: str | None = None,
          start: int | None = None, n: int | None = None, offset: int = 0, limit: int = 40,
          max_chars: int = 6000) -> dict[str, Any]:
    from .temporal import _page
    import os
    window = Window.parse(at, since_ts)
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
    stories, owners, gaps = replay(ledger, window.at)
    story = stories.get(canonical)
    result = {"schema": "migloop-time-state/1", "tool": tool, "path": canonical,
              "at": window.at, "since_ts": window.since, "known": False, "gaps": gaps,
              "note": "只重放截止前已返回且确认执行的效应；时间不是版本别名。"
                      "未知/条件/并发效应会断开状态；后续快照不倒灌至更早查询。"
                      "归属是文本来源，不认证缺陷原因；未识别的效应仍须查原始转录。"}
    if not story:
        return {**result, **_page([], offset, limit)}
    result["known"] = story.current_content is not None and not any(canonical in gap["paths"] for gap in gaps)
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
                         "agent": source["agent"] if source and not observed else None,
                         "basis": "observed_interval_not_single_writer" if observed else version.diff_kind,
                         "diff": (version.diff or "")[:max_chars],
                         "diff_chars": len(version.diff or ""),
                         "truncated": len(version.diff or "") > max_chars,
                         "note": "全文/原生补丁用 action(ref=...)；此处不把观测封口当单笔写入"})
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
        # First observed full overwrite is not proof this text originated there.
        if version and version.v == 1 and source and not source["event"].created:
            trusted = False
        rows.append({"line": number, "text": text, "agent": source["agent"] if trusted else None,
                     "introduced_at": version.ts if trusted else None,
                     "ref": source["ref"] if trusted else None,
                     "status": "supported_text_origin" if trusted else "unknown_origin"})
    return {**result, **_page(rows, offset, limit)}


def render(data: dict[str, Any]) -> str:
    import json
    return "# 时间 " + data["tool"] + "\n" + json.dumps(data, ensure_ascii=False, indent=2)
