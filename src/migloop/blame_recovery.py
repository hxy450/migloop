"""Bounded navigation from unavailable line attribution, never substitute blame.

This module reads ledger metadata only. A prior native full Write is a snapshot
source, not the owner of an unknown later line. No content is reconstructed here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .atoms import Ledger

SCHEMA = "migloop-blame-recovery/1"
LIMIT = 3
PATCH_CHARS = 600
WARNING = "仅为继续调查的入口；最近全文写者不是被替换行作者，不自动归责。"
_LOCATION = re.compile(r"^(\d+)(?:/(\d+))?·(.+)$")


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc) if stamp.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _event(ledger: Ledger, aid: str, action: Any) -> dict[str, Any]:
    """Only publish a copyable locator when all existing locator indexes agree."""
    from . import atoms
    out = {"status": "unavailable", "ref": None, "seq": getattr(action, "seq", None),
           "agent": aid, "use_line": None, "result_line": None, "event_id": None,
           "call_located": False, "result_located": False}
    if action is None or action.src is None:
        return out
    path, use, done = action.src
    if type(use) is not int or use < 0:
        return out
    loc = ledger.locs.get(action.seq)
    match = _LOCATION.fullmatch(loc) if isinstance(loc, str) else None
    if match is None:
        return out
    line, block, tag = int(match[1]), int(match[2] or 0), match[3]
    key = (tag, line, block)
    if (key in ledger.loc_ambiguous or ledger.by_loc.get(key) != action.seq or line != use + 1
            or block != action.blk or ledger.tag_paths.get(tag) != path):
        return out
    result_located = type(done) is int and done >= use and action.ok is not None
    out.update(status="recorded", ref=f"#{tag}:{action.seq}@L{line}" + (f"/{block}" if match[2] else ""),
               use_line=line, result_line=done + 1 if result_located else None,
               call_located=True, result_located=result_located,
               event_id=atoms.event_id(ledger, aid, action.seq))
    return out


def _bucket(items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"count": len(items), "items": items[:LIMIT], "remainder": max(0, len(items) - LIMIT), **extra}


def build(ledger: Ledger, path: str, anchor: int) -> dict[str, Any]:
    """Describe existing evidence before an anchor without changing any ledger fact."""
    from . import atoms
    from .coverage import _exact_mention, _excluded_action

    story = ledger.stories[path]
    target = story.versions[anchor - 1] if 1 <= anchor <= len(story.versions) else None
    cutoff = _time(target.ts) if target else None
    result: dict[str, Any] = {
        "schema": SCHEMA, "purpose": "investigation_navigation_not_blame", "semantic_checked": False,
        "warning": WARNING,
        "scope": {"status": "known" if cutoff else "unknown", "cutoff_ts": target.ts if cutoff else None,
                  "cutoff_basis": "requested_version_record_time", "lower_ts": None,
                  "selection": "same exact file; no later records; unknown/overlapping execution stays unconfirmed",
                  "unknown_time_events": 0, "ambiguous_mentions_excluded": 0},
        "nearest_snapshot": None, "first_gap": None,
        "target_patch": {"available": False, "kind": target.diff_kind if target else None, "text": "",
                         "truncated": False, "event": None, "line_authorship_checked": False},
        "intervening": {key: {**_bucket([]), "count_checked": bool(cutoff)} for key in
                        ("formal_versions", "explicit_effect_candidates", "unverified_target_mentions")},
        "next_queries": [],
    }
    if target is None:
        return result

    actions: dict[tuple[str, int], Any] = {}
    duplicated: set[tuple[str, int]] = set()
    for agent in ledger.agents.values():
        for action in agent.actions:
            key = (agent.id, action.seq)
            if key in actions:
                duplicated.add(key)
            actions[key] = action

    def action_for(version: Any) -> Any:
        key = (version.by, version.act_seq)
        return None if key in duplicated else actions.get(key)

    def version_row(version: Any) -> dict[str, Any]:
        action = action_for(version)
        return {"v": version.v, "ts": version.ts, "content_known": version.content is not None,
                "source": version.source, "diff_kind": version.diff_kind,
                "writer": {"id": version.by, "v": version.by_ver},
                "event": _event(ledger, version.by, action)}

    target_event = _event(ledger, target.by, action_for(target))
    result["target_patch"]["event"] = target_event
    if target.diff_kind == "native" and target.diff is not None and target_event["status"] == "recorded":
        lines = [line for line in target.diff.splitlines() if line.startswith(("+", "-"))
                 and not line.startswith(("+++", "---"))]
        cue = "\n".join(lines[:8])
        result["target_patch"].update(available=True, text=cue[:PATCH_CHARS],
                                      truncated=len(lines) > 8 or len(cue) > PATCH_CHARS)
        result["next_queries"].append({"tool": "diff", "args": {"path": path, "v": anchor},
                                       "purpose": "literal patch, not original-line ownership"})
        result["next_queries"].append({"tool": "action", "args": {"id": target.by, "seq": target.act_seq},
                                       "purpose": "original operation input and result"})
    if cutoff is None:
        return result

    # Only explicit same-target write risk affects snapshot certification. A print,
    # output locator, readonly mention or metadata probe must not become a barrier.
    risks: list[tuple[str, Any]] = []
    for (aid, _), action in actions.items():
        if (any(ref.op != "read" and ref.path == path for ref in action.files)
                or any(path in (action.detail.get(k) or []) for k in ("effect_candidates", "touched", "conditional"))):
            risks.append((aid, action))

    def overlaps_write(action: Any) -> bool:
        start, end = _time(action.ts), _time(action.done_ts)
        for _, other in risks:
            if other is action:
                continue
            other_start, other_end = _time(other.ts), _time(other.done_ts)
            if other_start is None:
                return True
            if other_start <= end and (other_end is None or other_end >= start):
                return True
        return False

    baseline = None
    for version in reversed(story.versions[:anchor - 1]):
        action = action_for(version)
        proof = version.proof
        if (version.content is None or version.source != "full" or version.sealed or version.conditional
                or proof is None or proof.operation_basis != "native_tool" or proof.execution != "confirmed"
                or proof.snapshot != "full" or action is None or action.ok is not True):
            continue
        start, done = _time(action.ts), _time(action.done_ts)
        if (start is None or done is None or not start <= done <= cutoff or _time(version.ts) != start
                or not _event(ledger, version.by, action)["result_located"]
                or version.by_ver != action.ver or not isinstance(action.ver, int)
                or not 1 <= action.ver <= ledger.agents[version.by].n_versions):
            continue
        refs = [ref for ref in action.files if ref.path == path and ref.ev.seq == version.seq
                and ref.ev.kind == "wfull" and ref.ev.content == version.content and ref.v == version.v
                and ref.proof == proof and not ref.observation_uncertain]
        if (len(refs) != 1 or overlaps_write(action)
                or any(path in (action.detail.get(k) or []) for k in ("effect_candidates", "touched", "conditional"))):
            continue
        baseline = version
        row = version_row(version)
        row.update(available_at=action.done_ts, availability_basis="successful_native_full_write_result",
                   authorship_scope="snapshot_write_not_line_origin")
        result["nearest_snapshot"] = row
        result["scope"]["lower_ts"] = action.done_ts
        result["next_queries"] = [
            {"tool": "file", "args": {"path": path, "v": version.v, "content": True}, "purpose": "earlier full snapshot"},
            {"tool": "agent", "args": {"id": version.by, "v": version.by_ver, "reads": True},
             "purpose": "cumulative inputs through actual writer version; do not narrow to its last feeding window"},
            {"tool": "action", "args": {"id": version.by, "seq": version.act_seq}, "purpose": "actual snapshot write"},
            *result["next_queries"],
        ]
        break

    lower = _time(result["scope"]["lower_ts"])
    lower_v = baseline.v if baseline else 0
    formal = [version_row(version) for version in story.versions if lower_v < version.v < anchor
              and _time(version.ts) is not None and _time(version.ts) <= cutoff]
    result["intervening"]["formal_versions"] = _bucket(formal,
        count_checked=True,
        distinct_calls=len({(row["writer"]["id"], row["event"]["seq"]) for row in formal}),
        query={"tool": "file", "args": {"path": path, "v": anchor, "diff": True,
                                           "v_from": lower_v + 1, "v_to": anchor}})
    gaps = [gap for gap in story.breaks if _time(gap.ts) is not None and _time(gap.ts) <= cutoff
            and (lower is None or _time(gap.ts) > lower)]
    if gaps:
        gap = min(gaps, key=lambda x: _time(x.ts))
        matching = [version for version in story.versions[:anchor] if version.ts == gap.ts]
        result["first_gap"] = {"ts": gap.ts, "reason": gap.kind, "detail": gap.detail[:240],
                               "event": version_row(matching[0])["event"] if len(matching) == 1 else None}

    represented = {(version.by, version.act_seq) for version in story.versions[:anchor]}
    explicit: dict[tuple[str, int], dict[str, Any]] = {}
    mentions: dict[tuple[str, int], dict[str, Any]] = {}
    unknown_time: set[tuple[str, int]] = set()

    def candidate(aid: str, action: Any) -> dict[str, Any] | None:
        start, done = _time(action.ts), _time(action.done_ts)
        if start is None:
            unknown_time.add((aid, action.seq))
            return None
        if start > cutoff or lower is not None and done is not None and done <= lower:
            return None
        return {"seq": action.seq, "agent": aid, "ts": action.ts, "done_ts": action.done_ts,
                "tool_status": action.ok, "writer_confirmed": False,
                "temporal_relation": "overlaps_cutoff" if done is None or done > cutoff else "within",
                "event": _event(ledger, aid, action)}

    for aid, action in risks:
        key = (aid, action.seq)
        unknown_part = any(path in (action.detail.get(k) or []) for k in ("effect_candidates", "touched", "conditional"))
        if (key not in represented or unknown_part) and (row := candidate(aid, action)) is not None:
            row["also_recorded_versions"] = [version.v for version in story.versions[:anchor]
                                              if (version.by, version.act_seq) == key]
            explicit[key] = row
    for mention in ledger.mentions.get(path, []):
        key = (mention.by, mention.seq)
        action = actions.get(key)
        if key in represented or key in explicit or action is None or mention.cls == "readonly" or _excluded_action(action, path):
            continue
        row = {"token": mention.token, "ctx": mention.ctx, "ambiguous": mention.ambiguous}
        if not _exact_mention(ledger, path, row, action):
            result["scope"]["ambiguous_mentions_excluded"] += 1
            continue
        if (item := candidate(mention.by, action)) is not None:
            # An output mention is only available when that result actually arrived.
            if mention.where == "out" and (_time(action.done_ts) is None or _time(action.done_ts) > cutoff):
                continue
            item.update(where=mention.where, classification=mention.cls, ctx=mention.ctx[:120])
            mentions[key] = item
    for name, values in (("explicit_effect_candidates", explicit), ("unverified_target_mentions", mentions)):
        ordered = sorted(values.values(), key=lambda row: (_time(row["ts"]), row["seq"]))
        result["intervening"][name] = _bucket(ordered,
            count_checked=True,
            query={"tool": "file", "args": {"path": path, "v": anchor, "m_n": 40},
                   "scope_note": "file is a broader index; keep this diagnostic time window when inspecting rows"})
    result["scope"]["unknown_time_events"] = len(unknown_time)
    return result


def render(recovery: dict[str, Any], root: str = "") -> str:
    """Text projection of the same JSON diagnostic, intentionally bounded."""
    import json

    def query_text(query: dict[str, Any]) -> str:
        args = dict(query["args"])
        if root and isinstance(args.get("path"), str) and args["path"].startswith(root.rstrip("/") + "/"):
            args["path"] = args["path"][len(root.rstrip("/")) + 1:]
        return f"{query['tool']}({json.dumps(args, ensure_ascii=False, separators=(',', ':'))})"

    lines = ["## 续查入口（非归因）", recovery["warning"]]
    if recovery["scope"]["status"] != "known":
        lines.append("时间边界未知，未选历史快照或推断期间活动。")
    else:
        lines.append(f"证据窗口：{recovery['scope']['lower_ts'] or '未找到可靠下界'} → {recovery['scope']['cutoff_ts']}；重叠调用仅列待核。")
    snapshot = recovery["nearest_snapshot"]
    if snapshot:
        writer = snapshot["writer"]
        lines.append(f"最近可靠全文 v{snapshot['v']} ← {writer['id']}@v{writer['v']} | {snapshot['event']['ref']}"
                     f"（{snapshot['available_at']} 已返回的原生全文写；不是被替换行作者）")
    else:
        lines.append("未找到在边界前可认证的原生全文写快照；不从后续封口或未知来源猜作者。")
    gap = recovery["first_gap"]
    if gap:
        lines.append(f"首个复原断点：{gap['reason']} | {gap['ts']} | {gap['detail']}"
                     + (f" | {gap['event']['ref']}" if gap.get("event") else ""))
    patch = recovery["target_patch"]
    if patch["available"]:
        lines.append(f"本版原生补丁（不是全文/旧行作者证明）| {patch['event']['ref']}\n```diff\n{patch['text']}\n```"
                     + ("\n…摘录已截断，diff/action 可取原文。" if patch["truncated"] else ""))
    labels = {"formal_versions": "期间正式版本（不含本版）", "explicit_effect_candidates": "显式效应待核调用",
              "unverified_target_mentions": "未核目标提及调用（不是写次数）"}
    for key, bucket in recovery["intervening"].items():
        if not bucket.get("count_checked", True):
            lines.append(f"{labels[key]}：时间范围未知，未计数。")
            continue
        entries = [(row["event"].get("ref") or "原文定位未认证")
                   + ("[跨界/未完成]" if row.get("temporal_relation") == "overlaps_cutoff" else "")
                   + ("[调用失败]" if row.get("tool_status") is False else "") for row in bucket["items"]]
        lines.append(f"{labels[key]} {bucket['count']}；显示 {len(entries)}，其余 {bucket['remainder']}"
                     + ("：" + "、".join(entries) if entries else ""))
        if bucket["remainder"] and bucket.get("query"):
            lines.append("  续查：" + query_text(bucket["query"]) + "；文件索引可能更宽，保留上方时间边界。")
    for query in recovery["next_queries"]:
        lines.append("→ " + query_text(query))
    if snapshot:
        lines.append("agent 入口保留累计输入；最近窗口没有某条输入，不等于更早没有收到。")
        lines.append("file/agent 仍需显式 via：先从已打开节点或真实搜索回执打开该 file，再以它导航到 writer；本诊断没有新增访问或历史读边。")
    return "\n".join(lines)
