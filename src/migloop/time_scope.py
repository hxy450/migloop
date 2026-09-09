"""Observed ledger time bounds for navigation, never a validation or completeness claim.

Only supplied AgentRec.session values group records. A missing root is not invented,
and a root's version range comes only from that root's actual numbered actions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .atoms import Ledger


SCHEMA = "migloop-time-scope/1"
_UNKNOWN = ("use_missing", "use_invalid", "done_missing", "done_invalid")


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        # A timezone-free wall-clock time cannot be ordered against another host.
        return parsed.astimezone(timezone.utc) if parsed.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z") if value is not None else None


def _bounds() -> dict[str, Any]:
    return {"min": None, "max": None, "count": 0}


def _observe(bounds: dict[str, Any], value: datetime | None) -> None:
    if value is not None:
        bounds["min"] = value if bounds["min"] is None else min(bounds["min"], value)
        bounds["max"] = value if bounds["max"] is None else max(bounds["max"], value)
        bounds["count"] += 1


def overview(ledger: Ledger, anchor_ts: str | None = None,
             anchor_agent: str | None = None) -> dict[str, Any]:
    """Return bounded per-session metadata, with UTC ISO timestamps and no I/O.

    ``after_anchor`` is None without a valid timezone-aware anchor. Its started,
    results_returned and observed_actions counts are separate: a call started
    before the anchor may still return after it. Missing done_ts is never replaced
    by use_ts, and a recorded done timestamp does not imply a successful result.

    ``later_sessions`` contains declared session IDs with observed activity after
    the anchor. ``other_later_sessions`` is None unless anchor_agent identifies an
    exact supplied agent with a session. Unassigned agents remain separate rows.
    ``search_window`` contains only since_ts/until_ts; callers supply query and sid.
    """
    anchor = _time(anchor_ts)
    owner = ledger.agents.get(anchor_agent) if isinstance(anchor_agent, str) else None
    anchor_session = owner.session if owner and isinstance(owner.session, str) and owner.session else None
    pool = _bounds()
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    diagnostics = []
    if anchor_ts is not None and anchor is None:
        diagnostics.append("anchor_ts 无效或缺少明确时区;未计算锚点之后的计数或检索窗口")
    if anchor_agent is not None and anchor_session is None:
        diagnostics.append("anchor_agent 未对应已提供的明确会话;不推测其他根会话集合")
    for supplied_id, agent in sorted(ledger.agents.items()):
        session = agent.session if isinstance(agent.session, str) and agent.session else None
        group_key = ("session", session) if session else ("unassigned", supplied_id)
        row = groups.setdefault(group_key, {
            "session": session, "agent_count": 0, "action_count": 0, "root_agents": [],
            "observed_use": _bounds(), "observed_done": _bounds(),
            "unknown_timestamps": dict.fromkeys(_UNKNOWN, 0),
            "unknown_intervals": 0, "reversed_intervals": 0,
            "after_anchor": {"started": 0, "results_returned": 0, "observed_actions": 0,
                             "known_straddling": 0} if anchor is not None else None,
        })
        row["agent_count"] += 1
        if agent.id == "__main__" or agent.id.startswith("__main__:"):
            versions = {a.ver for a in agent.actions if type(a.ver) is int and a.ver > 0}
            paths = sorted({a.src[0] for a in agent.actions if a.src and isinstance(a.src[0], str)})
            row["root_agents"].append({"id": agent.id, "versions": {
                "first": min(versions) if versions else None, "last": max(versions) if versions else None,
                "count": len(versions)}, "source_paths": paths})
        for action in agent.actions:
            row["action_count"] += 1
            use, done = _time(action.ts), _time(action.done_ts)
            for key, raw, value in (("use", action.ts, use), ("done", action.done_ts, done)):
                _observe(row["observed_" + key], value)
                _observe(pool, value)
                if value is None:
                    missing = raw is None or isinstance(raw, str) and not raw.strip()
                    row["unknown_timestamps"][key + ("_missing" if missing else "_invalid")] += 1
            if use is None or done is None:
                row["unknown_intervals"] += 1
            elif done < use:
                row["reversed_intervals"] += 1
            if anchor is not None:
                after = row["after_anchor"]
                started, returned = use is not None and use > anchor, done is not None and done > anchor
                after["started"] += int(started)
                after["results_returned"] += int(returned)
                after["observed_actions"] += int(started or returned)
                after["known_straddling"] += int(use is not None and done is not None and use <= anchor < done)
    rows = list(groups.values())
    for row in rows:
        starts = [b["min"] for b in (row["observed_use"], row["observed_done"]) if b["min"] is not None]
        ends = [b["max"] for b in (row["observed_use"], row["observed_done"]) if b["max"] is not None]
        row["observed_start"] = _iso(min(starts)) if starts else None
        row["observed_end"] = _iso(max(ends)) if ends else None
        for name in ("observed_use", "observed_done"):
            bounds = row[name]
            row[name] = {"min": _iso(bounds["min"]), "max": _iso(bounds["max"]), "count": bounds["count"]}
        roots = row["root_agents"]
        row["root_present"] = bool(roots)
        row["root_ambiguous"] = len(roots) > 1
        row["root_agent"] = roots[0]["id"] if len(roots) == 1 else None
        row["root_versions"] = roots[0]["versions"] if len(roots) == 1 else None
    rows.sort(key=lambda r: (r["observed_start"] is None, r["observed_start"] or "", r["session"] or ""))
    later = [r["session"] for r in rows if r["session"] and r["after_anchor"] is not None
             and r["after_anchor"]["observed_actions"]]
    return {
        "schema": SCHEMA,
        "anchor": {"input": anchor_ts, "time": _iso(anchor),
                   "status": "unanchored" if anchor_ts is None else "valid" if anchor is not None else "invalid",
                   "agent": anchor_agent, "session": anchor_session},
        "observed_start": _iso(pool["min"]), "latest_known_pool_time": _iso(pool["max"]),
        "roots": rows, "agent_count": len(ledger.agents), "action_count": sum(r["action_count"] for r in rows),
        "unknown_timestamps": {key: sum(r["unknown_timestamps"][key] for r in rows) for key in _UNKNOWN},
        "unknown_intervals": sum(r["unknown_intervals"] for r in rows),
        "reversed_intervals": sum(r["reversed_intervals"] for r in rows),
        "later_sessions": later if anchor is not None else None,
        "other_later_sessions": [sid for sid in later if sid != anchor_session]
                                if anchor is not None and anchor_session is not None else None,
        "search_window": {"since_ts": _iso(anchor), "until_ts": _iso(pool["max"])}
                         if anchor is not None and pool["max"] is not None and anchor < pool["max"] else None,
        "diagnostics": diagnostics, "scope_complete": False, "negative_proof": False,
        "scope": "仅汇总已提供 agent 动作中可解析且含时区的 use/done 时刻;未记录时刻不补齐。"
                 "后续活动不证明构建针对目标文件、验证成功或行为正确;零计数不证明全局没有活动。",
    }


def for_atom(ledger: Ledger, kind: str, payload: dict[str, Any] | None,
             until: int | None = None) -> dict[str, Any]:
    """Resolve one atom's time anchor, without substituting a result time.

    File anchors come from the uniquely selected payload version's ts/by. Agent
    anchors come from the supplied ledger's unique action with ver == payload.v.
    A provided until must identify one action of that same agent whose use time
    is no later than the version effect's use time; any invalid cutoff makes the
    anchor unknown instead of silently falling back to a later version time.
    """
    atom = payload if isinstance(payload, dict) else {}
    version = atom.get("v")
    key = atom.get("path" if kind == "file" else "id")
    key = key if isinstance(key, str) else None
    anchor_ts = anchor_agent = basis = error = None
    if type(version) is not int or version < 1:
        error = "原子没有可定位的正整数版本,时间锚点未知"
    elif kind == "file":
        rows = atom.get("versions")
        matches = [r for r in rows if isinstance(r, dict) and type(r.get("v")) is int and r["v"] == version] \
                  if isinstance(rows, list) else []
        if until is not None:
            error = "until 只允许用于 agent 原子,未推测文件时间截止"
        elif len(matches) != 1:
            error = "文件载荷不能唯一定位所选版本,时间锚点未知"
        else:
            anchor_ts = matches[0].get("ts")
            by = matches[0].get("by")
            anchor_agent = by if isinstance(by, str) else None
            basis = "file_version"
    elif kind == "agent":
        owner = ledger.agents.get(key) if key is not None else None
        matches = [a for a in owner.actions if type(a.ver) is int and a.ver == version] if owner else []
        if len(matches) != 1:
            error = "已提供 agent 不能唯一定位所选效应版本,时间锚点未知"
        else:
            anchor_ts, anchor_agent, basis = matches[0].ts, owner.id, "agent_effect_use"
            if until is not None:
                cuts = [a for a in owner.actions if type(a.seq) is int and a.seq == until] if type(until) is int else []
                cutoff = _time(cuts[0].ts) if len(cuts) == 1 else None
                effect = _time(anchor_ts)
                if cutoff is None or effect is None or cutoff > effect:
                    error = "until 不能唯一定位该 agent 的有效较早调用时刻;未回退到版本锚点"
                else:
                    anchor_ts, basis = cuts[0].ts, "agent_until_use"
    else:
        error = "原子种类不是 file/agent,时间锚点未知"
    if error is None and _time(anchor_ts) is None:
        error = "所选原子时刻缺失、无效或缺时区,未使用完成时刻或其他版本代替"
    result = overview(ledger, anchor_ts if error is None else None, anchor_agent)
    result["anchor"].update(kind=kind, key=key, v=version, until=until, basis=basis if error is None else None)
    if error is not None:
        result["anchor"].update(status="unknown", input=anchor_ts, reason=error)
        result["diagnostics"].append(error)
    return result
