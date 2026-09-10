import json
from pathlib import Path

import pytest

from migloop import atoms, investigation, probe, time_probe
from tests.test_trajectory import _pool, _run_dir
from tests.test_verdict_v3 import document


def test_v3_probe_uses_real_query_receipts_not_model_nodes_as_visits(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    requests = [{"tool": "file", "args": {"path": "/proj/entry/A.ets", "at": doc["target"]["at"]}},
                {"tool": "agent", "args": {"id": "agent-c", "at": doc["target"]["at"]}}]
    text = investigation.render_batch(ledger, requests)
    run = _run_dir(tmp_path, [("sessions", {}, "账本身份: " + atoms.ledger_identity(ledger)),
                              ("batch", {"requests": requests}, text)],
                   "```json\n" + json.dumps(doc) + "\n```")
    result = probe.probe_payload(ledger, run)
    assert result["schema"] == "migloop-time-probe/1"
    assert result["argument_graph"]["schema"] == "migloop-argument-graph/1"
    assert len(result["argument_graph"]["edges"]) == 2
    assert "trajectory" not in result and "evidence_graph" not in result
    assert result["query_trace"]["steps"]
    assert "edges" not in result["query_trace"] or result["query_trace"]["edges"] == []


def test_v3_without_query_pair_keeps_claims_and_does_not_invent_visits(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    run = _run_dir(tmp_path, [], "```json\n" + json.dumps(doc) + "\n```")
    result = probe.probe_payload(ledger, run)
    assert len(result["argument_graph"]["nodes"]) == 3
    assert result["query_trace"]["steps"] == []
    assert result["argument_graph"]["semantic_checked"] is False


def test_old_report_detection_is_not_changed(tmp_path):
    assert not time_probe.is_v3_run(str(tmp_path), "a normal report")
    assert not time_probe.is_v3_run(str(tmp_path), '```json\n{"schema":"migloop-verdict/1","defects":[]}\n```')


def test_invalid_v3_shows_diagnostics_without_falling_into_old_tree(tmp_path):
    ledger = _pool(tmp_path)
    run = _run_dir(tmp_path, [], "```yaml\nschema: migloop-verdict/3\nfindings: [\n```")
    result = probe.probe_payload(ledger, run)
    assert result["argument_graph"]["nodes"] == []
    assert result["diagnostics"] and "trajectory" not in result


def test_native_authenticated_invalid_schema_previews_without_accepting_submission(tmp_path):
    import hashlib
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["unknown"] = ["a local schema error, not a new fact"]
    report = "```json\n" + json.dumps(doc) + "\n```"
    requests = [{"tool": "file", "args": {"path": doc["target"]["file"], "at": doc["target"]["at"]}}]
    run = _run_dir(tmp_path, [("batch", {"requests": requests}, investigation.render_batch(ledger, requests))], report)
    path = Path(run) / "transcript.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "assistant", "message": {"stop_reason": "end_turn", "role": "assistant",
            "content": [{"type": "text", "text": report}]}}) + "\n")
    metrics = {"recording_complete": True, "transcript_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (Path(run) / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    result = probe.probe_payload(ledger, run)
    assert result["partial_document"] and result["native_report"]["verified"]
    assert len(result["argument_graph"]["nodes"]) == 3
    assert result["argument_graph"]["original_schema_valid"] is False
    assert result["structured"]["errors"] and result["structured"]["document_sha256"] is None
    assert result["preview"]["original_document"] == doc
    assert result["query_trace"]["steps"][0]["status"] == "recorded_response"
    # A forged cached verdict cannot supply the missing final authentication.
    (Path(run) / "result.json").write_text(json.dumps({"result": report.replace("author claim", "FORGED CLAIM")}), encoding="utf-8")
    rejected = probe.probe_payload(ledger, run)
    assert rejected["preview"] is None and not rejected["native_report"]["verified"]
    assert rejected["argument_graph"]["nodes"] == []


def test_manual_partial_draft_keeps_strict_failure_and_has_no_investigation_trace(tmp_path):
    from migloop import draft_check
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["coverage"] = [{"event": "e", "status": "explained", "finding": "F"}]
    draft = "```json\n" + json.dumps(doc) + "\n```"
    strict = draft_check.evaluate(ledger, draft)
    inspected = draft_check.evaluate(ledger, draft, with_graph=True)
    assert strict["document_sha256"] is None and inspected["document_sha256"] is None
    assert strict["status"] == inspected["status"] == "needs_review"
    assert strict["issues"] == inspected["issues"]
    assert len(inspected["argument_graph"]["nodes"]) == 3
    assert not inspected["argument_graph"]["document_source"]["verified"]
    assert "query_trace" not in inspected


@pytest.mark.parametrize("tool", ["batch", "changes", "expand", "events"])
@pytest.mark.parametrize("provider", ["bare", "other", "functions"])
def test_untrusted_new_tool_cannot_authenticate_investigation_trace(tmp_path, tool, provider):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    args = {"path": doc["target"]["file"], "at": doc["target"]["at"]}
    if tool == "batch":
        args = {"requests": [{"tool": "file", "args": args}]}
        text = investigation.render_batch(ledger, **args)
    elif tool == "expand":
        args = {"refs": doc["findings"][0]["nodes"][0]["evidence"], "at": doc["target"]["at"]}
        text = investigation.render_query(ledger, tool, args)
    else:
        text = investigation.render_query(ledger, tool, args)
    run = _run_dir(tmp_path, [(tool, args, text)], "```json\n" + json.dumps(doc) + "\n```")
    path = Path(run) / "transcript.jsonl"
    name = tool if provider == "bare" else "functions." + tool if provider == "functions" else "mcp__other__" + tool
    path.write_text(path.read_text(encoding="utf-8").replace("mcp__migloop__" + tool, name), encoding="utf-8")
    calls = probe._transcript_calls(run)
    assert calls[0]["provenance"]["origin_unverified"] is True
    assert calls[0]["provenance"]["complete_pair"] is False
    trace = investigation.project_trace(ledger, calls)
    assert trace["steps"][0]["status"] == "unverified_response"
    assert trace["steps"][0]["items"] == []
