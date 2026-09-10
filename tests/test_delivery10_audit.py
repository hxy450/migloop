"""Delivery statistics must not turn projection diagnostics into accuracy."""
import importlib.util
import json
from pathlib import Path

MODULE = Path(__file__).parents[1] / "docs/experiments/file-first-10/audit_tools10_delivery.py"
spec = importlib.util.spec_from_file_location("delivery10_audit", MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_count_subitems_once_keep_pending_and_no_semantic_bonus(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"cases": [{"id": "A"}], "repetitions": 2}), encoding="utf-8")
    run = tmp_path / "runs/A/rep1"
    run.mkdir(parents=True)
    trace = {"schema": "migloop-investigation-trace/1", "edges": [], "steps": [
        {"step": 1, "tool": "exec", "items": []},
        {"step": 2, "tool": "batch", "items": [
            {"item_index": 0, "tool": "search", "status": "ok"},
            {"item_index": 1, "tool": "file", "status": "deferred", "error": "budget"},
            {"item_index": 2, "tool": "diff", "status": "error", "error": "argument"},
        ]},
    ]}
    (run / "query-trace.json").write_text(json.dumps(trace), encoding="utf-8")
    data = audit.audit(tmp_path)
    assert data["expected_runs"] == 2 and data["observed_runs"] == 1
    assert data["batch_items_total"] == 3
    assert data["batch_items"] == {"ok": 1, "error": 1, "deferred": 1}
    assert data["runs"][1]["status"] == "pending"
    assert not data["semantic_checked"] and data["model_calls"] == 0
    assert data["failure_groups"][0]["locations"][0]["step"] == 2
    assert len(data["manifest_sha256"]) == len(data["runs"][0]["trace_sha256"]) == 64
