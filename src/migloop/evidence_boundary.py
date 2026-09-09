"""Bounded locator/window warnings, not semantic checks or historical replay.

Called only for identity-bound, resolved RED nodes by verdict._consistency.
Only basis.actual_evidence action locators are inspected; ordinary evidence,
expected evidence and prose are deliberately out of scope. No raw I/O, node
construction, file reconstruction, graph traversal, or mutation is performed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .evidence import proof_payload, read_basis
from .time_scope import _time

if TYPE_CHECKING:
    from .atoms import Ledger

MAX_ADVISORIES = 12
MAX_READ_DETAILS = 3
_READ_LABELS = {
    "uncertain_version": "版本就近绑定不确定",
    "overlapping_read": "读写窗口重叠、观测时刻不确定",
    "dependency_read": "依赖读，正文未交付上下文",
    "unverified_read": "操作/执行/正文观测依据未全部确认",
    "different_version": "未精确绑定当前声明版本",
}


def entry_effect_alignment(ledger: Ledger, node: dict[str, Any]) -> dict[str, Any] | None:
    """Compare an explicit entry coordinate with actual-side effect locators.

    This is not proof that the first defect occurred at either location. Earlier
    effects may legitimately explain cumulative state. Never reinterpret a read,
    text record, or feeding slot as an effect version to obtain a comparison.
    """
    if not (node.get("ok") and node.get("entry") and node.get("kind") == "agent"
            and node.get("role") in ("进入·错", "进入·缺") and node.get("basis")):
        return None
    result: dict[str, Any] = {
        "schema": "migloop-entry-effect-alignment/1", "status": "indeterminate",
        "anchor_agent": node["key"], "anchor_v": node["v"], "events": [],
        "events_omitted": 0, "source": "ledger_coordinates", "semantic_checked": False,
        "note": "只比较声明进入点与实际侧引用的效应版本，不认证进入原因或首次发生时刻。",
    }
    refs = node["basis"].get("actual_evidence") or []
    comparable = bool(refs)
    events = []
    seen = set()
    for ref in refs:
        if ref.get("type") != "action" or ref.get("status") not in ("ok", "drifted"):
            comparable = False
            continue
        aid, seq = ref.get("aid"), ref.get("seq")
        owner = ledger.agents.get(aid)
        actions = [action for action in owner.actions if action.seq == seq] if owner and type(seq) is int else []
        if len(actions) != 1:
            comparable = False
            continue
        action = actions[0]
        if aid != node["key"] or type(action.ver) is not int:
            comparable = False
        if (aid, seq) not in seen:
            seen.add((aid, seq))
            events.append({"ref": ref.get("original_ref", ref.get("ref")), "agent": aid,
                           "seq": seq, "effect_v": action.ver})
    if comparable and events:
        versions = [event["effect_v"] for event in events]
        result["status"] = ("anchor_cited" if node["v"] in versions else
                            "earlier_effects_only" if all(v < node["v"] for v in versions) else
                            "later_or_mixed_effects")
    if result["status"] == "earlier_effects_only":
        # A current-effect citation in the ordinary evidence field is still
        # direct coordinate evidence; the basis subset must not erase it.
        owner = ledger.agents.get(node["key"])
        for ref in node.get("evidence") or []:
            if ref.get("type") == "action" and ref.get("status") in ("ok", "drifted") and ref.get("aid") == node["key"]:
                matching = [action for action in owner.actions if action.seq == ref.get("seq")] if owner else []
                if len(matching) == 1 and matching[0].ver == node["v"]:
                    result["status"] = "anchor_cited_elsewhere"
                    break
    result["events"] = events[:MAX_ADVISORIES]
    result["events_omitted"] = max(0, len(events) - MAX_ADVISORIES)
    return result


def _anchor_ts(ledger: Ledger, node: dict[str, Any]) -> str | None:
    if node["kind"] == "file":
        story = ledger.stories.get(node["key"])
        rows = [v for v in story.versions if v.v == node["v"]] if story else []
    else:
        owner = ledger.agents.get(node["key"])
        rows = [a for a in owner.actions if a.ver == node["v"]] if owner else []
    return rows[0].ts if len(rows) == 1 else None


def node_advisories(ledger: Ledger, node: dict[str, Any], defect_id: str) -> list[dict[str, Any]]:
    """Inspect already resolved action metadata, preserving all model claims.

    The caller enforces identity and RED role. A missing warning does not mean
    the evidence supports the assertion. Repeated locators are deduplicated by
    resolved action; any output budget overflow is explicitly counted.
    """
    if not node.get("ok") or node.get("kind") not in ("file", "agent") or not node.get("basis"):
        return []
    anchor_ts = _anchor_ts(ledger, node)
    anchor = _time(anchor_ts)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()

    def add(code: str, aid: str, seq: int, original: str, message: str,
            boundary: dict[str, Any]) -> None:
        key = (code, aid, seq)
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "code": code, "level": "warning", "defect": defect_id, "node": node["spec"],
            "ref": original, "message": original.strip() + "：" + message,
            "boundary": {"anchor_v": node["v"], "anchor_ts": anchor_ts, **boundary},
            "source": "ledger_boundary", "semantic_checked": False,
        })

    for evidence in node["basis"].get("actual_evidence") or []:
        if evidence.get("type") != "action" or evidence.get("status") not in ("ok", "drifted"):
            continue
        aid, seq = evidence.get("aid"), evidence.get("seq")
        owner = ledger.agents.get(aid)
        actions = [a for a in owner.actions if a.seq == seq] if owner and type(seq) is int else []
        if len(actions) != 1:
            continue
        action = actions[0]
        original = evidence.get("original_ref", evidence.get("ref", ""))
        if not isinstance(original, str):
            continue
        common = {"aid": aid, "seq": seq, "use_ts": action.ts, "done_ts": action.done_ts}
        matching_reads = [r for r in action.files if r.op == "read" and r.path == node["key"]] \
            if node["kind"] == "file" else []
        if matching_reads:
            bases: list[str] = []
            details = []
            exact_read = False
            for ref in matching_reads:
                basis = read_basis(ref)
                exact_read |= ref.v == node["v"] and basis == "read"
                if basis != "read" and basis not in bases:
                    bases.append(basis)
                if ref.v != node["v"] and "different_version" not in bases:
                    bases.append("different_version")
                details.append({
                    "bound_v": ref.v, "read_basis": basis, "certain": ref.certain,
                    "observation_uncertain": ref.observation_uncertain, "dep": ref.ev.dep,
                    "proof": proof_payload(ref.proof),
                })
            # A second uncertain/different-version read must not negate a
            # confirmed read of this exact target/version in the same call.
            if bases and not exact_read:
                add("basis_read_version_boundary", aid, seq, original,
                    "此动作对当前文件有" + "、".join(_READ_LABELS[b] for b in bases)
                    + "；这些读取记录本身不证明此版本内容。保留实际观测/其他证据，不据此改判。",
                    {**common, "path": node["key"], "read_bases": bases,
                     "reads": details[:MAX_READ_DETAILS], "read_count": len(details),
                     "read_details_omitted": max(0, len(details) - MAX_READ_DETAILS)})

        # The invocation time and result availability are different facts.
        # A native writer's own result naturally follows its use-time anchor;
        # that alone is not a post-anchor-input warning.
        use, done = _time(action.ts), _time(action.done_ts)
        temporal_basis = None
        if anchor is not None:
            if use is not None and use > anchor:
                temporal_basis = "action_use"
            elif matching_reads and done is not None and done > anchor and (use is None or done >= use):
                temporal_basis = "read_result"
        if temporal_basis:
            add("basis_action_post_anchor", aid, seq, original,
                ("引用动作发起时刻" if temporal_basis == "action_use" else "引用读取结果返回时刻")
                + "晚于节点记录锚点；后置读回/反证可能合法，但不证明生成前已可用，不判断因果错误。",
                {**common, "temporal_basis": temporal_basis})

        if node["kind"] == "agent" and aid == node["key"]:
            feeding_slot = action.ver if action.ver is not None else action.at
            if type(feeding_slot) is int and feeding_slot > node["v"]:
                tail = action.ver is None and feeding_slot > owner.n_versions
                add("basis_agent_window_boundary", aid, seq, original,
                    f"同一 agent 的证据事件在节点 v{node['v']} 窗口之后（喂养槽 {feeding_slot}）"
                    + ("，没有对应正式效应版本；不重绑到末版，也不制造新版本。" if tail
                       else "；不能当作本节点窗口内的事件。")
                    + "后置证据仍可核对，不自动改变原角色。",
                    {**common, "feeding_slot": feeding_slot, "event_v": action.ver,
                     "n_versions": owner.n_versions, "after_last_effect": tail})

    if len(rows) <= MAX_ADVISORIES:
        return rows
    omitted = len(rows) - MAX_ADVISORIES
    return rows[:MAX_ADVISORIES] + [{
        "code": "basis_boundary_omitted", "level": "warning", "defect": defect_id,
        "node": node["spec"], "ref": None,
        "message": f"证据边界诊断已显示 {MAX_ADVISORIES} 条，另有 {omitted} 条未展开；"
                   "原始 basis 引用与主张未删，未显示不代表没有边界问题。",
        "boundary": {"emitted": MAX_ADVISORIES, "omitted": omitted, "total": len(rows)},
        "source": "ledger_boundary", "semantic_checked": False,
    }]
