"""Self-consistency is diagnostic metadata, never a replacement model verdict."""
from copy import deepcopy

from migloop import verdict
from tests.test_verdict import _build, _pool


def _data(role="正常", before="file:A.ets@v1", after="file:A.ets@v2"):
    return {"schema": verdict.SCHEMA, "defects": [{"id": "A", "title": "test",
            "entry": ["agent:agent-c@v1"], "repair": {"before": before, "after": after},
            "nodes": [{"node": "agent:agent-c@v1", "role": role, "reason": "original reason"}]}]}


def test_conflicting_entry_remains_a_model_claim(tmp_path):
    ledger = _pool(tmp_path)
    data = _data()
    original = deepcopy(data)
    out = _build(ledger, data)
    assert out["errors"] == [] and out["consistency"]["semantic_checked"] is False
    assert [a["code"] for a in out["consistency"]["advisories"]] == ["entry_role_conflict"]
    assert out["defects"][0]["nodes"][0]["role"] == "正常"
    assert out["defects"][0]["nodes"][0]["ok"] is True
    assert out["defects"][0]["nodes"][0]["checked"] == "not_checked"
    assert data == original


def test_nonincreasing_repair_is_not_a_schema_failure(tmp_path):
    ledger = _pool(tmp_path)
    for before, after in (("file:A.ets@v1", "file:A.ets@v1"), ("file:A.ets@v2", "file:A.ets@v1")):
        out = _build(ledger, _data("进入·错", before, after))
        assert [a["code"] for a in out["consistency"]["advisories"]] == ["repair_non_increasing"]
        assert out["defects"][0]["repair"]["after"]["ok"] is True
        assert out["errors"] == []


def test_distinct_defect_roles_do_not_conflict(tmp_path):
    data = _data("进入·错")
    normal = deepcopy(data["defects"][0])
    normal.update(id="B", entry=[])
    normal["nodes"][0]["role"] = "正常"
    data["defects"].append(normal)
    out = _build(_pool(tmp_path), data)
    assert out["consistency"]["advisories"] == []


def test_missing_node_reason_duplicate_roles_and_unbound(tmp_path):
    ledger = _pool(tmp_path)
    data = _data("进入·缺")
    data["defects"][0]["nodes"] = []
    assert _build(ledger, data)["consistency"]["advisories"][0]["code"] == "entry_without_node_reason"
    data = _data("进入·缺")
    data["defects"][0]["entry"] = []
    data["defects"][0]["nodes"].append({"node": "agent:agent-c@v1", "role": "正常", "reason": "second"})
    assert _build(ledger, data)["consistency"]["advisories"][0]["code"] == "node_role_conflict"
    for identity in (None, "mismatched"):
        data["ledger"] = identity
        out = verdict.build(ledger, data, [], {})
        assert out["consistency"] == {"checked": False, "semantic_checked": False, "advisories": []}


def test_out_of_scope_is_distinct_from_nonrepair():
    data = {"schema": verdict.SCHEMA, "defects": [], "coverage": [
        {"node": "file:A.ets@v1", "status": "out_of_scope", "defects": [],
         "reason": "outside the question; did not investigate", "evidence": []}]}
    assert verdict.validate(data) == []
