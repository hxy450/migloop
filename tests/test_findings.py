from copy import deepcopy

from migloop import findings, verdict
from tests.test_verdict import _pool, _build


def document(ledger):
    return _build(ledger, {
        "schema": verdict.SCHEMA, "root": "file:A.ets@v1",
        "notes": "An unassigned recommendation stays a document note.",
        "defects": [{"id": "A", "title": "Changed value", "entry": ["agent:agent-c@v1"],
            "repair": {"before": "file:A.ets@v1", "after": "file:A.ets@v2", "evidence": []},
            "nodes": [{"node": "agent:agent-c@v1", "role": "进入·错", "reason": "  original reason\n",
                       "evidence": ["invalid citation"], "boundary": "Not tested"}],
            "edges": []}],
    })


def test_groups_by_bound_repair_files_and_preserves_claims_and_warnings(tmp_path):
    ledger = _pool(tmp_path)
    built = document(ledger)
    original = deepcopy(built)
    got = findings.project(built)
    assert built == original
    assert got["schema"] == "migloop-findings/1" and len(got["files"]) == 1
    bucket = got["files"][0]
    assert bucket["path"] == "/proj/entry/A.ets" and bucket["versions"] == [1, 2]
    assert len(bucket["item_ids"]) == 1 and len(bucket["associations"]) == 2
    assert all(x["source"] == "model" and not x["repair_semantic_checked"] for x in bucket["associations"])
    item = got["items"][bucket["item_ids"][0]]
    assert item["causes"][0]["reason"] == "  original reason\n"
    assert item["causes"][0]["evidence_bad"] == 1
    assert item["causes"][0]["basis_status"] == "absent_warning"
    assert item["recommendation"] is None and got["notes"] == built["notes"]
    assert not item["audit"]["semantic_checked"] and item["audit"]["advisories"]
    item["causes"][0]["reason"] = "changed projection"
    assert built == original


def test_invalid_repair_does_not_fall_back_to_valid_root(tmp_path):
    built = document(_pool(tmp_path))
    for side in ("before", "after"):
        built["defects"][0]["repair"][side]["ok"] = False
    got = findings.project(built)
    assert got["root"]["ok"] is True
    assert got["files"] == [] and len(got["items"]) == 1 and len(got["unbound_items"]) == 1


def test_identity_mismatch_retains_model_items_without_fake_file_binding(tmp_path):
    built = document(_pool(tmp_path))
    built["identity"]["bound"] = False
    got = findings.project(built)
    assert not got["files"] and len(got["unbound_items"]) == 1
    assert next(iter(got["items"].values()))["causes"][0]["reason"] == "  original reason\n"


def test_multifile_defect_is_one_item_with_two_file_references(tmp_path):
    built = document(_pool(tmp_path))
    # Simulate a separately resolved second repair endpoint, not an inferred move.
    built["defects"][0]["repair"]["after"].update(key="/proj/B.ets", spec="file:/proj/B.ets@v2")
    got = findings.project(built)
    assert len(got["files"]) == 2 and len(got["items"]) == 1
    assert got["files"][0]["item_ids"] == got["files"][1]["item_ids"]
    assert findings.project(built) == got


def test_failed_or_legacy_document_cannot_become_structured_findings(tmp_path):
    assert not findings.project(None)["items"]
    built = document(_pool(tmp_path))
    built["errors"] = ["invalid schema"]
    assert not findings.project(built)["items"]


def test_basis_presence_does_not_certify_evidence_or_causality():
    assert findings.basis_status({"role": "正常"}) == "not_required"
    assert findings.basis_status({"role": "进入·缺", "basis": {"expected": "x"}}) == "invalid_legacy"
    assert findings.basis_status({"role": "进入·错", "basis": {
        "expected": "e", "actual": "a", "counterevidence": "unknown",
        "expected_evidence": [{"status": "missing"}], "actual_evidence": [{"status": "missing"}],
    }}) == "complete"
