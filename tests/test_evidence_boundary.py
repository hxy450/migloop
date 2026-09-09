"""Basis boundaries are mechanical warnings, never semantic verdicts or new visits."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from migloop import atoms, draft_check, verdict
from migloop.evidence import FileProof
from tests.test_atoms import _call, _ledger
from tests.test_verdict import _pool, _ref

FILE = "/proj/entry/A.ets"
GOOD = FileProof("native_tool", "confirmed", "content", "partial")


def document(ledger, refs, node=None, role="进入·错"):
    return {
        "schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger),
        "defects": [{"id": "A", "title": "问题甲", "nodes": [{
            "node": node or f"file:{FILE}@v1", "role": role, "reason": "原始主张不改",
            "basis": {"expected": "预期", "actual": "实际", "counterevidence": "反证仍未知",
                      "expected_evidence": [f"file:{FILE}@v1"], "actual_evidence": refs},
        }]}],
    }


def build(ledger, data):
    assert verdict.validate(data) == []
    return verdict.build(ledger, data, [], {})


def advice(result, code):
    return [a for a in result["consistency"]["advisories"] if a["code"] == code]


def reader(ledger):
    return next(a for a in ledger.agents["agent-f"].actions if a.tool == "Read")


@pytest.mark.parametrize("change,expected", [
    ("nearby", "uncertain_version"), ("overlap", "overlapping_read"),
    ("dependency", "dependency_read"), ("no_proof", "unverified_read"),
    ("execution_unknown", "unverified_read"), ("different_version", "different_version"),
])
def test_same_file_read_boundaries_keep_claim_and_ref(tmp_path, change, expected):
    ledger = _pool(tmp_path)
    act = reader(ledger)
    ref = act.files[0]
    ref.ev = replace(ref.ev, proof=GOOD)
    if change == "nearby":
        ref.certain = False
    elif change == "overlap":
        ref.observation_uncertain = True
    elif change == "dependency":
        ref.ev = replace(ref.ev, dep=True)
    elif change == "no_proof":
        ref.ev = replace(ref.ev, proof=None)
    elif change == "execution_unknown":
        ref.ev = replace(ref.ev, proof=replace(GOOD, execution="unknown"))
    else:
        ref.v = 2
    original_ref = "  " + _ref(ledger, act.seq) + "  "
    data = document(ledger, [original_ref])
    snapshot = deepcopy(data)
    result = build(ledger, data)
    rows = advice(result, "basis_read_version_boundary")
    assert len(rows) == 1 and rows[0]["ref"] == original_ref
    assert expected in rows[0]["boundary"]["read_bases"]
    assert rows[0]["node"] == f"file:{FILE}@v1"
    assert "不证明此版本内容" in rows[0]["message"]
    assert rows[0]["semantic_checked"] is False
    node = result["defects"][0]["nodes"][0]
    assert node["ok"] and node["role"] == "进入·错" and node["checked"] == "not_checked"
    assert node["basis_evidence_bad"] == 0 and result["errors"] == [] and data == snapshot


def test_other_path_uncertainty_does_not_poison_matching_read(tmp_path):
    ledger = _pool(tmp_path)
    act = reader(ledger)
    act.files[0].ev = replace(act.files[0].ev, proof=GOOD)
    other = atoms.FileRef("read", "/proj/other.ets",
                          replace(act.files[0].ev, path="/proj/other.ets", proof=None),
                          v=1, certain=False, observation_uncertain=True)
    act.files.append(other)
    result = build(ledger, document(ledger, [_ref(ledger, act.seq)]))
    assert not advice(result, "basis_read_version_boundary")
    assert advice(result, "basis_action_post_anchor")


@pytest.mark.parametrize("bad_kind", ["uncertain", "different_version"])
@pytest.mark.parametrize("confirmed_first", [True, False])
def test_same_path_confirmed_target_read_is_not_negated_by_other_reads(tmp_path, bad_kind, confirmed_first):
    ledger = _pool(tmp_path)
    act = reader(ledger)
    confirmed = act.files[0]
    confirmed.ev = replace(confirmed.ev, proof=GOOD)
    assert confirmed.v == 1 and confirmed.certain
    other = atoms.FileRef("read", FILE, confirmed.ev,
                          v=2 if bad_kind == "different_version" else 1,
                          certain=bad_kind != "uncertain")
    act.files = [confirmed, other] if confirmed_first else [other, confirmed]
    result = build(ledger, document(ledger, [_ref(ledger, act.seq)]))
    assert not advice(result, "basis_read_version_boundary")
    assert advice(result, "basis_action_post_anchor")
    assert result["defects"][0]["nodes"][0]["ok"]


def test_confirmed_later_read_is_not_a_failed_version_claim(tmp_path):
    ledger = _pool(tmp_path)
    act = reader(ledger)
    act.files[0].ev = replace(act.files[0].ev, proof=GOOD)
    data = document(ledger, [_ref(ledger, act.seq)])
    result = build(ledger, data)
    assert not advice(result, "basis_read_version_boundary")
    row = advice(result, "basis_action_post_anchor")[0]
    assert row["boundary"]["temporal_basis"] == "action_use"
    assert "后置读回/反证可能合法" in row["message"]
    assert result["defects"][0]["nodes"][0]["ok"]


def test_read_result_after_anchor_and_same_write_completion_are_distinct(tmp_path):
    ledger = _pool(tmp_path)
    act = reader(ledger)
    act.ts = "2026-01-01T00:00:19Z"
    act.done_ts = "2026-01-01T00:00:21Z"
    act.files[0].ev = replace(act.files[0].ev, proof=GOOD, use_ts=act.ts, done_ts=act.done_ts)
    result = build(ledger, document(ledger, [_ref(ledger, act.seq)]))
    assert advice(result, "basis_action_post_anchor")[0]["boundary"]["temporal_basis"] == "read_result"
    writer = next(a for a in ledger.agents["agent-c"].actions if a.ver == 1)
    result = build(ledger, document(ledger, [_ref(ledger, writer.seq)]))
    assert not advice(result, "basis_action_post_anchor")


def test_equal_utc_times_and_unknown_times_do_not_invent_order(tmp_path):
    ledger = _pool(tmp_path)
    act = reader(ledger)
    act.ts = "2025-12-31T19:00:20-05:00"
    act.done_ts = "2026-01-01T00:00:20.000000Z"
    act.files[0].ev = replace(act.files[0].ev, proof=GOOD, done_ts=act.done_ts)
    result = build(ledger, document(ledger, [_ref(ledger, act.seq)]))
    assert not advice(result, "basis_action_post_anchor")
    act.ts, act.done_ts = "unknown", None
    act.files[0].ev = replace(act.files[0].ev, done_ts=None, proof=None)
    result = build(ledger, document(ledger, [_ref(ledger, act.seq)]))
    assert not advice(result, "basis_action_post_anchor")
    assert advice(result, "basis_read_version_boundary")


def tail_ledger(tmp_path):
    return _ledger(tmp_path, [], {"agent-c": [
        *_call("2026-01-01T00:00:10Z", "write", "Write",
               {"file_path": FILE, "content": "a\n"}, "File created successfully"),
        *_call("2026-01-01T00:00:20Z", "tail", "Bash", {"command": "printf done"}, "done"),
    ]})


def test_tail_action_cannot_be_rebound_to_last_agent_version(tmp_path):
    ledger = tail_ledger(tmp_path)
    owner = ledger.agents["agent-c"]
    tail = next(a for a in owner.actions if a.tool == "Bash")
    assert tail.ver is None and tail.at == 2 and owner.n_versions == 1
    result = build(ledger, document(ledger, [_ref(ledger, tail.seq)], "agent:agent-c@v1"))
    row = advice(result, "basis_agent_window_boundary")[0]
    assert row["boundary"]["feeding_slot"] == 2 and row["boundary"]["n_versions"] == 1
    assert row["boundary"]["after_last_effect"] is True
    assert row["boundary"]["event_v"] is None
    assert "不重绑到末版" in row["message"]
    assert result["defects"][0]["nodes"][0]["v"] == 1 and tail.ver is None


def test_earlier_same_agent_action_remains_usable_and_other_owner_is_not_tail(tmp_path):
    ledger = _pool(tmp_path)
    earlier = next(a for a in ledger.agents["agent-c"].actions if a.tool == "Read")
    result = build(ledger, document(ledger, [_ref(ledger, earlier.seq)], "agent:agent-c@v1"))
    assert not advice(result, "basis_agent_window_boundary")
    later_other = reader(ledger)
    result = build(ledger, document(ledger, [_ref(ledger, later_other.seq)], "agent:agent-c@v1"))
    assert not advice(result, "basis_agent_window_boundary")


def test_previous_effect_window_is_not_late_evidence(tmp_path):
    ledger = _ledger(tmp_path, [], {"agent-c": [
        *_call("2026-01-01T00:00:10Z", "one", "Write",
               {"file_path": FILE, "content": "a\n"}, "File created successfully"),
        *_call("2026-01-01T00:00:30Z", "two", "Write",
               {"file_path": FILE, "content": "b\n"}, "ok"),
    ]})
    earlier = next(a for a in ledger.agents["agent-c"].actions if a.ver == 1)
    result = build(ledger, document(ledger, [_ref(ledger, earlier.seq)], "agent:agent-c@v2"))
    assert result["consistency"]["advisories"] == []


def test_drifted_reference_checks_resolved_action_but_keeps_original_text(tmp_path):
    ledger = _pool(tmp_path)
    act = reader(ledger)
    act.files[0].certain = False
    ref = _ref(ledger, act.seq)
    stale_ref = ref.replace(":" + str(act.seq) + "@", ":999999@")
    result = build(ledger, document(ledger, [stale_ref]))
    resolved = result["defects"][0]["nodes"][0]["basis"]["actual_evidence"][0]
    assert resolved["status"] == "drifted" and resolved["seq"] == act.seq
    row = advice(result, "basis_read_version_boundary")[0]
    assert row["ref"] == stale_ref and row["boundary"]["seq"] == act.seq


def test_only_actual_basis_actions_on_bound_valid_red_nodes_are_checked(tmp_path, monkeypatch):
    ledger = _pool(tmp_path)
    act = reader(ledger)
    act.files[0].certain = False
    ref = _ref(ledger, act.seq)
    data = document(ledger, [f"file:{FILE}@v1"])
    data["defects"][0]["nodes"][0]["basis"]["expected_evidence"] = [ref]
    data["defects"][0]["nodes"][0]["evidence"] = [ref]
    assert build(ledger, data)["consistency"]["advisories"] == []
    data = document(ledger, [ref], role="正常")
    assert build(ledger, data)["consistency"]["advisories"] == []
    data = document(ledger, [ref], node=f"file:{FILE}@v999")
    assert build(ledger, data)["consistency"]["advisories"] == []
    data = document(ledger, [ref])
    data.pop("ledger")
    monkeypatch.setattr(atoms, "resolve_ref", lambda *args: pytest.fail("unbound must not resolve raw refs"))
    result = build(ledger, data)
    assert result["consistency"] == {"checked": False, "semantic_checked": False, "advisories": []}


def test_invalid_refs_do_not_gain_boundary_certification(tmp_path):
    ledger = _pool(tmp_path)
    result = build(ledger, document(ledger, ["#absent:999@L999"]))
    assert result["defects"][0]["nodes"][0]["basis_evidence_bad"] == 1
    assert result["consistency"]["advisories"] == []


def test_duplicate_refs_are_deduplicated_and_budget_discloses_omissions(tmp_path, monkeypatch):
    from migloop import evidence_boundary
    ledger = _pool(tmp_path)
    act = reader(ledger)
    act.files[0].certain = False
    ref = _ref(ledger, act.seq)
    data = document(ledger, [ref, " " + ref + " ", ref])
    result = build(ledger, data)
    assert len(advice(result, "basis_read_version_boundary")) == 1
    assert len(advice(result, "basis_action_post_anchor")) == 1
    monkeypatch.setattr(evidence_boundary, "MAX_ADVISORIES", 1)
    result = build(ledger, data)
    rows = result["consistency"]["advisories"]
    assert len(rows) == 2 and rows[-1]["code"] == "basis_boundary_omitted"
    assert rows[-1]["boundary"]["omitted"] == 1


def test_checker_exposes_warning_without_semantic_upgrade_or_raw_access(tmp_path, monkeypatch):
    ledger = _pool(tmp_path)
    act = reader(ledger)
    act.files[0].certain = False
    data = document(ledger, [_ref(ledger, act.seq)])
    monkeypatch.setattr(atoms, "action_raw", lambda *args, **kwargs: pytest.fail("diagnostic must not open raw"))
    result = draft_check.evaluate(ledger, json.dumps(data))
    assert result["status"] == "needs_review" and result["semantic_checked"] is False
    rows = [i for i in result["issues"] if i["code"] == "basis_read_version_boundary"]
    assert rows and rows[0]["severity"] == "warning"
    assert _ref(ledger, act.seq) in rows[0]["detail"] and rows[0]["node"] == f"file:{FILE}@v1"
    assert result["counts"]["errors"] == 0
