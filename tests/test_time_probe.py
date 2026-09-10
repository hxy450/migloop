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
