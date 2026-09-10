"""The post-run index must not claim shell isolation or duplicate raw bodies."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "docs/experiments/file-first-10/audit_raw10.py"
spec = importlib.util.spec_from_file_location("raw10_post_run_audit", SOURCE)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


def fixture_run(tmp_path, monkeypatch):
    run = tmp_path / "runs/F10-01/rep1"
    run.mkdir(parents=True)
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    transcript = run / "transcript.jsonl"
    transcript.write_text("recorded transcript", encoding="utf-8")
    metrics = {
        "status": "completed", "actual_models": ["gpt-5.6-luna"],
        "actual_effort": "medium", "recording_complete": True,
        "host_skill_catalog_absent": True,
        "transcript_sha256": audit_module.sha(transcript),
    }
    (run / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    manifest = {"cases": [{"id": "F10-01"}], "repetitions": 1}
    trace = {"calls": [{
        "step": 1, "input": "read only", "text": "raw historical sensitive body",
        "visible_chars": 29, "truncation_marker": True,
        "pairing": "unique", "tool": "exec",
    }], "orphan_output_ids": []}
    runner = SimpleNamespace(verify_manifest=lambda base: manifest)
    native = SimpleNamespace(native_calls=lambda path: trace)
    monkeypatch.setattr(audit_module, "module", lambda path, name: runner if path.name == "run_raw10.py" else native)
    return transcript


def test_index_preserves_delivery_limits_without_copying_return_body(tmp_path, monkeypatch):
    fixture_run(tmp_path, monkeypatch)
    result = audit_module.audit(tmp_path)
    row = result["runs"][0]
    assert row["native_outer_calls"] == 1
    assert row["returns_with_truncation_marker"] == 1
    assert "text" not in result["call_index"][0]["calls"][0]
    assert "not an OS isolation proof" in result["scope_status"]
    assert "quoted historical markers" in result["truncation_semantics"]


def test_changed_transcript_cannot_be_silently_reaudited(tmp_path, monkeypatch):
    transcript = fixture_run(tmp_path, monkeypatch)
    transcript.write_text("different recording", encoding="utf-8")
    with pytest.raises(ValueError, match="Transcript drift"):
        audit_module.audit(tmp_path)
