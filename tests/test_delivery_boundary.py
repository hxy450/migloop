from migloop.delivery_boundary import derive, inherited


def test_unlinked_runtime_receipt_is_server_only():
    row = derive({"has_result": True, "provenance": {
        "format": "codex_rollout_event", "complete_pair": True}})
    assert row["server_returned"] is True
    assert row["model_visible"] is None  # Not certified absent, merely unknown.
    assert row["status"] == "runtime_only"


def test_direct_pair_is_model_output_record_without_fullness_claim():
    row = derive({"has_result": True, "provenance": {
        "format": "codex_rollout", "complete_pair": True}, "delivery_truncated": True})
    assert row["model_output_recorded"] is True
    assert row["model_visible"] is True
    assert row["status"] == "model_output_recorded"
    assert not row["full_body_delivery_verified"] and row["recorded_truncation"]


def test_old_record_without_boundary_is_unknown():
    row = derive({"has_result": True})
    assert row["status"] == "unknown"
    assert row["model_visible"] is None
    unpaired = derive({"has_result": True, "provenance": {"format": "codex_rollout", "complete_pair": False}})
    assert unpaired["model_visible"] is None and unpaired["status"] == "unverified"


def test_batch_child_inherits_runtime_boundary():
    parent = {"has_result": True, "provenance": {
        "format": "codex_rollout_event", "complete_pair": True}}
    child = inherited(parent, {"item_index": 0, "status": "ok"})
    assert child["status"] == "runtime_only"
    assert child["inherited_from_parent"] is True


def test_actual_exec_event_fallback_is_runtime_only():
    assert derive({"has_result": True, "provenance": {"format": "codex_exec_events"}})["status"] == "runtime_only"


def test_real_parsed_nested_runtime_keeps_query_but_not_model_delivery(tmp_path):
    import json
    from migloop import investigation, probe
    from tests.test_trajectory import _pool
    from tests.test_verdict_v3 import document
    ledger = _pool(tmp_path)
    doc = document(ledger)
    args = {"requests": [{"tool": "file", "args": {"path": doc["target"]["file"], "at": doc["target"]["at"]}}]}
    text = investigation.render_batch(ledger, **args)
    events = [
        {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "outer", "name": "exec", "input": "text(result)"}},
        {"type": "event_msg", "payload": {"type": "item_completed", "started_at_ms": 1, "completed_at_ms": 2,
            "item": {"type": "McpToolCall", "id": "inner", "server": "migloop", "tool": "batch", "arguments": args,
                     "result": {"content": [{"type": "text", "text": text}]}}}},
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "outer", "output": [
            {"type": "input_text", "text": "Script completed\nOutput:\n"},
            {"type": "input_text", "text": "Warning: truncated output (original token count: 20000)\nhead…tail"}]}}
    ]
    run = tmp_path / "nested-run"
    run.mkdir()
    (run / "transcript.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    calls = probe._transcript_calls(str(run))
    trace = investigation.project_trace(ledger, calls)
    step, = [s for s in trace["steps"] if s["tool"] == "batch"]
    assert step["status"] == "recorded_response"  # Runtime receipt still exists.
    assert step["delivery_boundary"]["status"] == "runtime_only"
    assert step["delivery_boundary"]["model_visible"] is None
    assert step["delivery_boundary"]["item_id"] == "inner"
    assert len(step["items"]) == 1 and step["items"][0]["status"] == "ok"
    assert step["items"][0]["delivery_boundary"]["status"] == "runtime_only"
    assert not step["items"][0]["delivery_boundary"]["full_body_delivery_verified"]
    assert trace["edges"] == []  # No invented outer/inner or historical edge.


def test_native_scalar_and_batch_project_same_direct_boundary(tmp_path):
    from migloop import atom_queries, investigation, probe, time_receipts
    from tests.test_trajectory import _pool, _run_dir
    from tests.test_verdict_v3 import document
    ledger = _pool(tmp_path)
    doc = document(ledger)
    args = {"path": doc["target"]["file"], "at": doc["target"]["at"]}
    text = atom_queries.render_text(ledger, "", "file", args)
    run = _run_dir(tmp_path, [("file", args, text)], "report")
    calls = probe._transcript_calls(run)
    scalar = time_receipts.project(ledger, calls)["steps"][0]
    unified = investigation.project_trace(ledger, calls)["steps"][0]
    assert scalar["delivery_boundary"] == unified["delivery_boundary"]
    assert unified["delivery_boundary"]["model_output_recorded"] is True
    assert not unified["delivery_boundary"]["full_body_delivery_verified"]


def test_actual_template_labels_runtime_child_direct_and_legacy():
    import os
    from pathlib import Path
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if node is None:
        pytest.skip("node required for actual template helper execution")
    template = (Path(__file__).parents[1] / "src/migloop/render/templates/fixchain.html").read_text(encoding="utf-8")
    helper = template[template.index("    function renderQueryTrace("):template.index("    function renderArgumentProbe(")]
    setup = r'''
const assert=require('node:assert/strict');
function el(tag,cls,text) { return {tag,className:cls,textContent:text,dataset:{},children:[],appendChild(x){this.children.push(x);return x;}}; }
function argumentDetails(){}
function recordedTimeRequest(){return null;}
const PROBE={query_trace:{steps:[
 {step:1,tool:'batch',status:'recorded_response',args:{requests:[{tool:'file',args:{}}]},
  delivery_boundary:{status:'runtime_only',model_visible:null},
  items:[{item_index:0,tool:'file',status:'ok'}]},
 {step:2,tool:'file',status:'recorded_response',delivery_boundary:{status:'model_output_recorded'}},
 {step:3,tool:'file',status:'recorded_response'}
]}};
'''
    checks = r'''
const host=el('div'); renderQueryTrace(host);
function all(n){return [n,...n.children.flatMap(all)];}
const nodes=all(host), rows=nodes.filter(n=>n.className==='query-item');
assert.deepEqual(rows.map(n=>n.dataset.deliveryBoundary),['runtime_only','runtime_only','model_output_recorded','unknown']);
const labels=nodes.filter(n=>n.className==='argument-note delivery-boundary').map(n=>n.textContent);
assert.equal(labels.filter(s=>s.includes('仅服务端返回')).length,2);
assert(labels.some(s=>s.includes('不代表全文/理解')));
assert(labels.some(s=>s.includes('旧记录未记录')));
'''
    result = subprocess.run([node, "-e", setup + helper + checks], capture_output=True, text=True, encoding="utf-8",
        timeout=15, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert result.returncode == 0, result.stderr
