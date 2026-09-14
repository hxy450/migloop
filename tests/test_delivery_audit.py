import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location("delivery_audit", Path(__file__).parents[1] / "docs/experiments/inquiry-20260911/audit_delivery.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_deleting_or_renaming_a_claim_is_not_reported_as_a_correction():
    before = {"findings": [{"id": "A", "nodes": [{"id": "old", "role": "origin", "reason": "wrong author"}]}]}
    after = {"findings": [{"id": "B", "nodes": [{"id": "new", "role": "unknown", "reason": "not checked"}]}]}
    delta = audit.transition(before, after)
    assert delta["removed"] == ["A:old"] and delta["added"] == ["B:new"]
    assert delta["changed"] == [] and delta["semantic_corrections"] is None


def test_changed_role_preserves_both_claims_for_semantic_review():
    before = {"findings": [{"id": "A", "nodes": [{"id": "actor", "role": "origin", "reason": "first"}]}]}
    after = {"findings": [{"id": "A", "nodes": [{"id": "actor", "role": "propagated", "reason": "preserved"}]}]}
    delta = audit.transition(before, after)
    change, = delta["changed"]
    assert change["before"]["role"] == "origin" and change["after"]["role"] == "propagated"
    assert delta["semantic_corrections"] is None
