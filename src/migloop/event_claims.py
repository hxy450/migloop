"""Model event claims bound to immutable transcript actions, never graph nodes.

An event claim is a statement *about* a raw recorded event.  Resolution proves
only its location and recorded envelope.  It does not certify the model's reason,
the truth of text spoken by an actor, or the semantics of a successful command.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from . import action_query, atoms


FIELDS = frozenset(("id", "event", "role", "reason", "evidence", "basis"))
REQUIRED = frozenset(("id", "event", "role", "reason", "evidence"))
TEXT_KINDS = frozenset(("say", "think", "message", "instruction", "inject", "system", "notify", "inbox", "compact"))


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(rows: Any, entry_ids: Any) -> list[str]:
    """Strictly validate model-owned fields without consulting a ledger."""
    from . import verdict

    errors: list[str] = []
    if not isinstance(rows, list):
        return ["event_claims 必须是列表"]
    ids: set[str] = set()
    for index, row in enumerate(rows):
        where = f"event_claims[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{where}: 必须是映射")
            continue
        verdict._check_keys(row, set(FIELDS), where, errors)
        missing = sorted(REQUIRED - set(row))
        if missing:
            errors.append(f"{where}: 缺少键 {', '.join(missing)}")
        ident = row.get("id")
        if not _text(ident):
            errors.append(f"{where}.id: 必须是非空字符串")
        elif ident in ids:
            errors.append(f"{where}.id: 重复 {ident}")
        else:
            ids.add(ident)
        event = row.get("event")
        match = atoms.REF_RE.fullmatch(event.strip()) if _text(event) else None
        if match is None or not (match.group(1) or match.group(5)):
            errors.append(f"{where}.event: 必须是单个完整 #转录标识:n@L行[/块] 引用")
        else:
            try:
                if int(match.group(2)) < 1 or int(match.group(3)) < 1:
                    raise ValueError
            except ValueError:
                errors.append(f"{where}.event: 动作号和行号必须大于0")
        if row.get("role") not in verdict.ROLES:
            errors.append(f"{where}.role: 必须是 {' / '.join(verdict.ROLES)} 之一")
        if not _text(row.get("reason")):
            errors.append(f"{where}.reason: 必须是非空字符串")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(_text(ref) for ref in evidence):
            errors.append(f"{where}.evidence: 必须是非空引用字符串列表")
        if "basis" in row:
            verdict._check_basis(row.get("basis"), f"{where}.basis", errors)
        elif row.get("role") in verdict.RED:
            errors.append(f"{where}.basis: 红色事件必须给出期望、实际、双方证据与反证")

    if not isinstance(entry_ids, list) or not all(_text(value) for value in entry_ids):
        errors.append("entry_events 必须是 event_claim id 字符串列表")
    else:
        repeated = sorted({value for value in entry_ids if entry_ids.count(value) > 1})
        if repeated:
            errors.append("entry_events 重复: " + ", ".join(repeated))
        missing_entries = sorted(set(entry_ids) - ids)
        if missing_entries:
            errors.append("entry_events 指向不存在的 event_claim: " + ", ".join(missing_entries))
    return errors


def _unbound(reason: str, *, status: str = "unresolved") -> dict[str, Any]:
    return {"status": status, "ok": False, "ref": None, "original_ref": None, "owner_agent": None,
            "seq": None, "source_path": None, "use_line": None, "result_line": None,
            "use_ts": None, "done_ts": None, "tool_use_id": None, "tool": None,
            "action_ok": None, "kind": None, "event_class": None,
            "textual_only": None, "effect_version": None, "context_anchor": None,
            "anchor_basis": None, "context_available_before_event": None,
            "context_timing_note": None, "temporal_relation": None, "paired_result": None, "diag": reason,
            "creates_node": False, "creates_edge": False, "semantic_checked": False}


def _canonical_ref(ledger: atoms.Ledger, seq: int) -> str | None:
    loc = ledger.locs.get(seq)
    if not loc:
        return None
    from .atoms_text import _core
    return _core(seq, loc)


def _context_timing(previous: atoms.Action | None, event: atoms.Action) -> tuple[bool | None, str]:
    """Compare envelope timestamps only; never infer that prior content was consumed."""
    if previous is None:
        return None, "没有此前真实效应"
    if not previous.done_ts or not event.ts:
        return None, "此前效应完成时刻或事件发起时刻未知；不证明上下文当时可用"
    try:
        done = datetime.fromisoformat(previous.done_ts.replace("Z", "+00:00"))
        begun = datetime.fromisoformat(event.ts.replace("Z", "+00:00"))
        if done.tzinfo is None and begun.tzinfo is not None or done.tzinfo is not None and begun.tzinfo is None:
            return None, "时区信息不一致；不证明此前效应在事件前完成"
    except (ValueError, TypeError):
        return None, "时刻无法解析；不证明此前效应在事件前完成"
    if done <= begun:
        return True, "此前效应的记录完成时刻不晚于事件发起时刻；只证明外壳时序，不证明内容被消费"
    return False, "此前效应在事件发起后才记录完成（窗口重叠）；不能作为事件前已可用输入"


def _binding(ledger: atoms.Ledger, original_ref: str, identity_bound: bool) -> dict[str, Any]:
    if not identity_bound:
        value = _unbound("账本身份未绑定", status="unbound")
        value["original_ref"] = original_ref
        return value
    try:
        address = action_query.resolve(ledger, ref=original_ref)
    except ValueError as exc:
        message = str(exc)
        status = "ambiguous" if "ambiguous" in message or "歧义" in message else (
                 "missing" if "missing" in message or "缺失" in message else "invalid")
        value = _unbound(message, status=status)
        value["original_ref"] = original_ref
        return value
    owner = ledger.agents.get(address.agent)
    matches = [action for action in owner.actions if action.seq == address.seq] if owner else []
    if owner is None or len(matches) != 1:
        value = _unbound("动作归属缺失或歧义")
        value["original_ref"] = original_ref
        return value
    action = matches[0]
    if action.src is None:
        value = _unbound("动作没有原始记录指针")
        value["original_ref"] = original_ref
        return value
    position = owner.actions.index(action)
    previous = next((candidate for candidate in reversed(owner.actions[:position])
                     if candidate.ver is not None), None)
    anchor = ({"kind": "agent", "aid": owner.id, "v": previous.ver}
              if previous is not None and previous.ver is not None else None)
    if action.ver is not None:
        temporal = "effect_after_anchor" if anchor else "first_effect"
    elif anchor is None:
        temporal = "before_first_effect"
    elif action.at > owner.n_versions:
        temporal = "tail_after_anchor"
    else:
        temporal = "input_after_anchor_before_next_effect"
    textual = action.kind in TEXT_KINDS
    use_index, result_index = action.src[1], action.src[2]
    paired = bool(action.tuid is not None and action.ok is not None and result_index != use_index)
    canonical = _canonical_ref(ledger, action.seq)
    context_available, timing_note = _context_timing(previous, action)
    return {"status": address.status, "ok": True, "ref": canonical, "original_ref": original_ref,
            "owner_agent": owner.id, "seq": action.seq, "source_path": action.src[0],
            "use_line": use_index + 1, "result_line": result_index + 1 if paired else None,
            "use_ts": action.ts, "done_ts": action.done_ts, "tool_use_id": action.tuid,
            "tool": action.tool, "action_ok": action.ok, "kind": action.kind,
            "event_class": "text_record" if textual else "recorded_action",
            "textual_only": textual, "effect_version": action.ver, "context_anchor": anchor,
            "anchor_basis": "prior_ledger_effect_order" if anchor else None,
            "context_available_before_event": context_available, "context_timing_note": timing_note,
            "temporal_relation": temporal, "paired_result": paired,
            "diag": ("文本记录只证明 actor 说过/想过这些内容，不证明所述操作执行"
                     if textual else "位置与调用外壳可核；成功状态不认证模型的语义归因")
                    + "；context_anchor 仅按账本效应顺序，不自动是事件前输入",
            "creates_node": False, "creates_edge": False, "semantic_checked": False}


def _evidence(ledger: atoms.Ledger, ref: str, identity_bound: bool) -> dict[str, Any]:
    from . import verdict
    if identity_bound:
        return {**verdict.resolve_evidence(ledger, ref), "original_ref": ref}
    return {"ref": str(ref), "original_ref": ref, "type": "text", "status": "not_checked",
            "diag": "账本身份未绑定"}


def _basis(ledger: atoms.Ledger, value: dict[str, Any] | None, identity_bound: bool) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"expected": value["expected"], "actual": value["actual"],
            "counterevidence": value["counterevidence"], "source": "model", "semantic_checked": False,
            "expected_evidence": [_evidence(ledger, ref, identity_bound) for ref in value["expected_evidence"]],
            "actual_evidence": [_evidence(ledger, ref, identity_bound) for ref in value["actual_evidence"]]}


def build(ledger: atoms.Ledger, rows: list[dict[str, Any]], entry_ids: list[str], *,
          identity_bound: bool) -> list[dict[str, Any]]:
    """Resolve validated claims without manufacturing file/agent nodes or edges."""
    entries = set(entry_ids)
    result = []
    for row in rows:
        evidence = [_evidence(ledger, ref, identity_bound) for ref in row["evidence"]]
        result.append({"id": row["id"], "event": row["event"], "role": row["role"],
                       "reason": row["reason"], "evidence": evidence,
                       "evidence_bad": sum(ref["status"] not in ("ok", "drifted") for ref in evidence),
                       "basis": _basis(ledger, row.get("basis"), identity_bound),
                       "entry": row["id"] in entries,
                       "binding": _binding(ledger, row["event"], identity_bound),
                       "source": "model", "creates_node": False, "creates_edge": False,
                       "semantic_checked": False})
    return result
