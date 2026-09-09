import importlib.util
from pathlib import Path


def helper():
    path = Path(__file__).parents[1] / "docs/experiments/2026-09-09-attribution10/audit_run.py"
    spec = importlib.util.spec_from_file_location("annotation_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.annotation_summary


def test_annotation_audit_separates_events_basis_and_scope_without_counting_versions():
    source = {"schema": "migloop-verdict/2", "defects": [{"id": "A",
        "target_binding": {"status": "matched", "creates_node": False},
        "nodes": [{"evidence": [{"status": "ok"}], "basis": {"actual_evidence": [{"status": "missing"}]}}],
        "event_claims": [{"id": "E", "event": "#x:9@L1", "role": "进入·错", "entry": True,
                          "evidence": [{"status": "ok"}], "basis": {"expected_evidence": [{"status": "drifted"}]},
                          "binding": {"status": "ok", "ok": True, "effect_version": None, "creates_node": False}}]}]}
    out = helper()(source)
    assert out["reference_field_counts"]["node_basis_actual"] == {"missing": 1}
    assert out["reference_field_counts"]["event_basis_expected"] == {"drifted": 1}
    assert out["event_resolved"] == 1 and out["events"][0]["binding"]["effect_version"] is None
    assert "nodes" not in out and out["semantic_checked"] is False
    assert out["target_scopes"][0]["creates_node"] is False


def test_failed_event_binding_is_not_hidden_by_valid_supporting_reference():
    source = {"defects": [{"id": "A", "event_claims": [{"id": "E", "event": "#missing:8@L1",
        "evidence": [{"status": "ok"}], "binding": {"status": "missing", "ok": False}}]}]}
    out = helper()(source)
    assert out["event_binding_status"] == {"missing": 1} and out["event_resolved"] == 0
    assert out["reference_field_counts"]["event_evidence"] == {"ok": 1}


def test_legacy_absent_events_are_not_invented_and_duplicate_occurrences_are_explicit():
    source = {"schema": "migloop-verdict/1", "defects": [{"id": "A",
        "repair": {"evidence": [{"status": "ok"}]},
        "nodes": [{"evidence": [{"status": "ok"}, {"status": "ok"}]}]}]}
    out = helper()(source)
    assert out["events"] == out["target_scopes"] == []
    assert out["reference_field_counts"]["node_evidence"] == {"ok": 2}
    assert "not unique" in out["note"]
