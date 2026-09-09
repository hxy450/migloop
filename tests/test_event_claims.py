from __future__ import annotations

from migloop import atoms_text, event_claims
from tests.test_action_owner_version import _history
from tests.test_atoms import MAIN_ID


def ref(ledger, action):
    return atoms_text._core(action.seq, ledger.locs[action.seq])


def basis(reference):
    return {"expected": "requirement", "actual": "recorded result",
            "expected_evidence": [reference], "actual_evidence": [reference],
            "counterevidence": "semantic truth remains unchecked"}


def row(reference, **changes):
    value = {"id": "E1", "event": reference, "role": "进入·错", "reason": "model explanation",
             "evidence": [reference], "basis": basis(reference)}
    value.update(changes)
    return value


def test_effect_and_input_bind_to_real_event_with_prior_effect_anchor(tmp_path):
    ledger = _history(tmp_path)
    owner = ledger.agents[MAIN_ID]
    first = next(action for action in owner.actions if action.tuid == "write-first")
    middle = next(action for action in owner.actions if action.tuid == "read-middle")
    claims = [row(ref(ledger, first)), row(ref(ledger, middle), id="E2", role="正常")]
    claims[1].pop("basis")
    assert event_claims.validate(claims, ["E1"]) == []
    built = event_claims.build(ledger, claims, ["E1"], identity_bound=True)
    effect, inp = (item["binding"] for item in built)
    assert effect["ok"] is True and effect["owner_agent"] == MAIN_ID and effect["effect_version"] == 1
    assert effect["action_ok"] is True
    assert effect["context_anchor"] is None and effect["temporal_relation"] == "first_effect"
    assert effect["paired_result"] is True and effect["use_line"] < effect["result_line"]
    assert inp["effect_version"] is None
    assert inp["context_anchor"] == {"kind": "agent", "aid": MAIN_ID, "v": 1}
    assert inp["anchor_basis"] == "prior_ledger_effect_order"
    assert inp["context_available_before_event"] is True
    assert inp["use_ts"] == middle.ts and inp["done_ts"] == middle.done_ts and inp["tool"] == middle.tool
    assert inp["temporal_relation"] == "input_after_anchor_before_next_effect"
    assert all(item["creates_node"] is False and item["creates_edge"] is False for item in built)
    assert built[0]["entry"] is True and built[1]["entry"] is False


def test_tail_and_text_are_locatable_without_fake_version_or_execution(tmp_path):
    ledger = _history(tmp_path)
    owner = ledger.agents[MAIN_ID]
    tail_read = next(action for action in owner.actions if action.tuid == "read-tail")
    tail_text = next(action for action in owner.actions if action.kind == "say")
    claims = [row(ref(ledger, tail_read)), row(ref(ledger, tail_text), id="E2")]
    built = event_claims.build(ledger, claims, [], identity_bound=True)
    read_binding, text_binding = (item["binding"] for item in built)
    assert read_binding["effect_version"] is None and read_binding["temporal_relation"] == "tail_after_anchor"
    assert read_binding["context_anchor"] == {"kind": "agent", "aid": MAIN_ID, "v": 2}
    assert text_binding["effect_version"] is None and text_binding["context_anchor"]["v"] == 2
    assert text_binding["event_class"] == "text_record" and text_binding["textual_only"] is True
    assert text_binding["paired_result"] is False and "不证明" in text_binding["diag"]
    assert text_binding["result_line"] is None and text_binding["use_line"] is not None


def test_zero_effect_text_has_no_context_anchor(tmp_path):
    ledger = _history(tmp_path, effects=False)
    action = next(action for action in ledger.agents[MAIN_ID].actions if action.kind == "say")
    built = event_claims.build(ledger, [row(ref(ledger, action))], [], identity_bound=True)[0]
    assert built["binding"]["context_anchor"] is None
    assert built["binding"]["effect_version"] is None
    assert built["binding"]["temporal_relation"] == "before_first_effect"


def test_pending_call_has_no_fabricated_result_line_and_overlap_is_not_available(tmp_path):
    ledger = _history(tmp_path)
    owner = ledger.agents[MAIN_ID]
    pending = next(action for action in owner.actions if action.tuid == "read-tail")
    assert pending.src is not None
    pending.ok = None
    pending.done_ts = None
    pending.src = (pending.src[0], pending.src[1], pending.src[1])
    previous = next(action for action in owner.actions if action.tuid == "write-last")
    previous.done_ts = "2026-01-01T00:01:00Z"
    built = event_claims.build(ledger, [row(ref(ledger, pending))], [], identity_bound=True)[0]["binding"]
    assert built["ok"] is True and built["action_ok"] is None and built["paired_result"] is False
    assert built["use_line"] is not None and built["result_line"] is None and built["done_ts"] is None
    assert built["context_anchor"]["v"] == 2 and built["context_available_before_event"] is False
    assert "窗口重叠" in built["context_timing_note"]


def test_drift_uses_location_and_bad_or_unbound_identity_fails_closed(tmp_path):
    ledger = _history(tmp_path)
    action = next(action for action in ledger.agents[MAIN_ID].actions if action.tuid == "write-last")
    original = ref(ledger, action)
    drifted = original.replace(f":{action.seq}@", ":999999@")
    resolved = event_claims.build(ledger, [row(drifted)], [], identity_bound=True)[0]["binding"]
    assert resolved["status"] == "drifted" and resolved["seq"] == action.seq
    assert resolved["ref"] == original and resolved["original_ref"] == drifted

    tag = original[1:].split(":", 1)[0]
    ledger.loc_ambiguous.add((tag, action.src[1] + 1, action.blk))
    ambiguous = event_claims.build(ledger, [row(original)], [], identity_bound=True)[0]["binding"]
    assert ambiguous["status"] == "ambiguous" and ambiguous["owner_agent"] is None
    assert ambiguous["context_anchor"] is None and ambiguous["creates_node"] is False

    unbound = event_claims.build(ledger, [row(original)], [], identity_bound=False)[0]
    assert unbound["binding"]["status"] == "unbound" and unbound["binding"]["ok"] is False
    assert unbound["binding"]["seq"] is None
    assert unbound["evidence"][0]["status"] == "not_checked"
    assert unbound["basis"]["expected_evidence"][0]["status"] == "not_checked"


def test_validation_is_strict_and_model_cannot_supply_anchors_or_versions(tmp_path):
    ledger = _history(tmp_path)
    action = next(action for action in ledger.agents[MAIN_ID].actions if action.tuid == "write-first")
    reference = ref(ledger, action)
    good = row(reference)
    assert event_claims.validate([good], ["E1"]) == []
    bad = {**good, "anchor": "agent:made-up@v9", "version": 9}
    errors = event_claims.validate([bad], ["missing", "missing"])
    assert any("未知键 anchor, version" in error for error in errors)
    assert any("entry_events 重复" in error for error in errors)
    assert any("不存在" in error for error in errors)
    invalid = {key: value for key, value in good.items() if key != "basis"}
    errors = event_claims.validate([invalid], [])
    assert any("红色事件" in error for error in errors)
    normal = {**invalid, "role": "无法确认"}
    assert event_claims.validate([normal], []) == []
    invalid["basis"] = basis(reference)
    invalid["event"] = f"#{action.seq}@L{action.src[1] + 1}"
    assert any("完整" in error for error in event_claims.validate([invalid], []))
