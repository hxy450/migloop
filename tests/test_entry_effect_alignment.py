"""Earlier decisions can explain later state without locating a later entry event."""
from copy import deepcopy
import json

import pytest

from migloop import atoms, draft_check, verdict
from tests.test_atoms import _call, _ledger, _read_call
from tests.test_verdict import _ref


def fixture(tmp_path):
    ledger = _ledger(tmp_path, [], {"agent-c": [
        *_call("2026-01-01T00:00:10Z", "w1", "Write", {"file_path": "/proj/A.ets", "content": "first"}),
        *_read_call("2026-01-01T00:00:15Z", "read", "/proj/A.ets", "first"),
        *_call("2026-01-01T00:00:20Z", "w2", "Write", {"file_path": "/proj/A.ets", "content": "second"}),
        *_call("2026-01-01T00:00:30Z", "w3", "Write", {"file_path": "/proj/A.ets", "content": "third"}),
    ]})
    refs = {action.tuid: _ref(ledger, action.seq) for action in ledger.agents["agent-c"].actions if action.tuid}
    doc = {"schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger), "defects": [{
        "id": "A", "title": "entry versus state", "entry": ["agent:agent-c@v3"],
        "nodes": [{"node": "agent:agent-c@v3", "role": "进入·错", "reason": "original claim",
                   "evidence": [], "basis": {"expected": "expected", "actual": "actual", "counterevidence": "unknown",
                       "expected_evidence": [refs["w1"]], "actual_evidence": [refs["w1"], refs["w2"]]}}]}]}
    return ledger, refs, doc


def evaluate(ledger, doc):
    assert verdict.validate(doc) == []
    result = verdict.build(ledger, doc, [], {})
    node = result["defects"][0]["nodes"][0]
    rows = [row for row in result["consistency"]["advisories"] if row["code"] == "entry_effect_earlier_only"]
    return result, node, rows


def test_only_earlier_effects_warn_without_changing_model_or_ledger(tmp_path):
    ledger, refs, doc = fixture(tmp_path)
    saved, identity = deepcopy(doc), atoms.ledger_identity(ledger)
    result, node, rows = evaluate(ledger, doc)
    assert node["entry_effect_alignment"]["status"] == "earlier_effects_only"
    assert len(rows) == 1 and rows[0]["semantic_checked"] is False
    assert "不是声明进入点 v3 的效应" in rows[0]["message"] and "可能合法解释累计状态" in rows[0]["message"]
    assert node["role"] == "进入·错" and node["v"] == 3 and node["ok"] is True
    assert result["errors"] == [] and doc == saved and atoms.ledger_identity(ledger) == identity
    check = draft_check.evaluate(ledger, json.dumps(doc))
    assert any(row["code"] == "entry_effect_earlier_only" and row["severity"] == "warning" for row in check["issues"])


@pytest.mark.parametrize("field,status", [("actual_evidence", "anchor_cited"), ("evidence", "anchor_cited_elsewhere")])
def test_direct_anchor_citation_suppresses_earlier_only_warning(tmp_path, field, status):
    ledger, refs, doc = fixture(tmp_path)
    node = doc["defects"][0]["nodes"][0]
    target = node["basis"] if field == "actual_evidence" else node
    target[field].append(refs["w3"])
    _, resolved, rows = evaluate(ledger, doc)
    assert resolved["entry_effect_alignment"]["status"] == status and rows == []


@pytest.mark.parametrize("change", ["read", "file_ref", "missing_ref", "future", "not_entry", "propagation", "normal", "unbound"])
def test_ambiguous_context_later_evidence_and_nonentry_are_not_earlier_only(tmp_path, change):
    ledger, refs, doc = fixture(tmp_path)
    defect = doc["defects"][0]
    node = defect["nodes"][0]
    if change == "read":
        node["basis"]["actual_evidence"].append(refs["read"])
    elif change == "file_ref":
        node["basis"]["actual_evidence"].append("file:/proj/A.ets@v3")
    elif change == "missing_ref":
        node["basis"]["actual_evidence"].append("#absent:999@L999")
    elif change == "future":
        node["node"] = "agent:agent-c@v1"
        defect["entry"] = [node["node"]]
        node["basis"]["actual_evidence"] = [refs["w3"]]
    elif change == "not_entry":
        defect["entry"] = []
    elif change == "propagation":
        node["role"] = "带病传递"
    elif change == "normal":
        node["role"] = "正常"
    else:
        doc["ledger"] = "different-ledger"
    _, resolved, rows = evaluate(ledger, doc)
    assert rows == []
    if change in ("read", "file_ref", "missing_ref"):
        assert resolved["entry_effect_alignment"]["status"] == "indeterminate"
    if change == "not_entry":
        assert resolved["entry_effect_alignment"]["entry_declared"] is False
        assert resolved["entry_effect_alignment"]["status"] == "earlier_effects_only"
    if change in ("propagation", "normal", "unbound"):
        assert "entry_effect_alignment" not in resolved


def test_mixed_sources_still_show_exact_metadata_without_a_semantic_warning(tmp_path):
    ledger, refs, doc = fixture(tmp_path)
    defect = doc["defects"][0]
    defect["entry"] = []
    defect["nodes"][0]["basis"]["actual_evidence"].append(refs["read"])
    checked = draft_check.evaluate(ledger, json.dumps(doc))
    assert not any(row["code"] == "entry_effect_earlier_only" for row in checked["issues"])
    alignment = checked["entry_effect_alignments"][0]
    assert alignment["status"] == "indeterminate" and alignment["entry_declared"] is False
    assert [row["effect_v"] for row in alignment["events"]] == [1, 2, None]
    assert alignment["semantic_checked"] is False
