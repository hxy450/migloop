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


def v2_document(tmp_path):
    built = document(_pool(tmp_path))
    built["schema"] = "migloop-verdict/2"
    defect = built["defects"][0]
    defect["target_binding"] = {"declared_path": "scope/ReportedOnly.ets", "canonical_path": "/proj/scope/ReportedOnly.ets",
                                "status": "matched", "source": "model", "creates_node": False, "semantic_checked": False}
    defect["event_claims"] = [{"id": "late-event", "event": "  #agent-c:7@L4  ", "role": "进入·错",
                               "reason": "  event reason\n<script>not HTML</script>", "entry": True,
                               "evidence": [{"ref": "bad ref", "status": "missing"}],
                               "basis": {"expected": "expect", "actual": "actual", "counterevidence": "later"},
                               "binding": {"status": "not_checked", "diagnostics": ["future binding fields stay intact"]},
                               "source": "model", "semantic_checked": False}]
    return built


def test_v2_scope_association_is_not_a_repair_file_or_node(tmp_path):
    built = v2_document(tmp_path)
    original = deepcopy(built)
    got = findings.project(built)
    assert built == original
    assert got["files"][0]["path"] == "/proj/entry/A.ets"
    scope = got["scope_files"][0]
    assert scope["path"] == "/proj/scope/ReportedOnly.ets"
    assert scope["item_ids"] == got["files"][0]["item_ids"]
    assert "versions" not in scope and "node_source" not in scope
    assert all(a["kind"] == "task_scope" and a["source"] == "model" and a["creates_node"] is False
               and a["semantic_checked"] is False for a in scope["associations"])
    item = got["items"][scope["item_ids"][0]]
    assert item["target_binding"] == original["defects"][0]["target_binding"]
    assert item["event_claims"] == original["defects"][0]["event_claims"]
    assert item["causes"][0]["reason"] == original["defects"][0]["nodes"][0]["reason"]
    assert got["root"] == original["root"]
    item["event_claims"][0]["binding"]["diagnostics"].append("changed copy")
    item["target_binding"]["canonical_path"] = "changed copy"
    assert built == original


def test_scope_without_repair_stays_in_historical_unbound_items_bucket(tmp_path):
    built = v2_document(tmp_path)
    built["defects"][0]["repair"] = None
    got = findings.project(built)
    assert got["files"] == [] and len(got["scope_files"]) == 1
    assert got["scope_files"][0]["item_ids"] == got["unbound_items"]
    item = got["items"][got["unbound_items"][0]]
    assert item["repair"] is None and item["event_claims"][0]["entry"] is True
    assert item["entry"] == built["defects"][0]["entry"]  # event entry never becomes a node entry


def test_unbound_or_unresolved_scope_keeps_diagnostics_without_path_fallback(tmp_path):
    built = v2_document(tmp_path)
    for status in ("ambiguous", "unlocated", "not_checked"):
        built["defects"][0]["target_binding"]["status"] = status
        got = findings.project(built)
        assert got["scope_files"] == [] and len(got["unbound_scope_items"]) == 1
        assert next(iter(got["items"].values()))["target_binding"]["status"] == status
    built["defects"][0]["target_binding"]["status"] = "matched"
    built["identity"]["bound"] = False
    got = findings.project(built)
    assert got["scope_files"] == [] and got["files"] == []
    assert len(got["unbound_scope_items"]) == len(got["unbound_items"]) == 1
    assert next(iter(got["items"].values()))["event_claims"] == built["defects"][0]["event_claims"]


def test_v1_does_not_acquire_v2_scope_or_event_projection(tmp_path):
    built = v2_document(tmp_path)
    built["schema"] = "migloop-verdict/1"
    got = findings.project(built)
    assert "scope_files" not in got and "unbound_scope_items" not in got
    assert all("target_binding" not in i and "event_claims" not in i for i in got["items"].values())


def test_event_only_item_keeps_context_separate_from_node_entry_and_repair(tmp_path):
    built = v2_document(tmp_path)
    built["root"] = None
    defect = built["defects"][0]
    defect.update(nodes=[], entry=[], repair=None)
    defect["event_claims"][0]["binding"] = {"status": "ok", "owner_agent": "agent-c", "seq": 7,
                                            "context_anchor": {"kind": "agent", "aid": "agent-c", "v": 1},
                                            "textual_only": True, "creates_node": False}
    original = deepcopy(built)
    got = findings.project(built)
    item = next(iter(got["items"].values()))
    assert got["root"] is None and got["files"] == []
    assert item["causes"] == item["entry"] == [] and item["repair"] is None
    assert item["event_claims"] == defect["event_claims"]
    assert got["scope_files"] and built == original


def test_v2_recommendation_is_a_lossless_model_claim_not_inferred_from_notes(tmp_path):
    built = v2_document(tmp_path)
    assert next(iter(findings.project(built)["items"].values()))["recommendation_status"] == "not_provided"
    built["defects"][0]["recommendation"] = "  suggestion\n<img src=x>"
    got = next(iter(findings.project(built)["items"].values()))
    assert got["recommendation"] == built["defects"][0]["recommendation"]
    assert got["recommendation_status"] == "model_claim" and got["audit"]["semantic_checked"] is False
    built["schema"] = "migloop-verdict/1"
    old = next(iter(findings.project(built)["items"].values()))
    assert old["recommendation"] is None and old["recommendation_status"] == "not_provided_by_source_schema"
