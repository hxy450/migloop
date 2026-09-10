"""Independent real MCP/HTTP and native-call checks for compact batch receipts.

The initial review reproduced a supported result-wrapper mismatch: the query
trace authenticated it while via.trace_identity did not unwrap it. After the
shared safe unwrap fix, both new and legacy wrappers are ordinary regressions.
"""
import asyncio
from copy import deepcopy
import json

import pytest

from migloop import batch_wire, investigation, mcp_server, probe, raw_events, transcript_store, via
from tests.test_investigation_http import real_http  # noqa: F401 -- shared real server fixture
from tests.test_temporal import source, ts


def mcp_batch(ledger, args):
    class Backend:
        async def get_ledger(self, sid):
            assert sid == "time"
            return ledger

        async def get_session_cwd(self, sid):
            return "/proj"
    blocks = asyncio.run(mcp_server.build_server(Backend()).call_tool("batch", {"sid": "time", **args}))
    assert len(blocks) == 1 and blocks[0].type == "text"
    return blocks[0].text


def native_calls(run, text, args, *, provider="migloop", wrapped=False, pending=False):
    delivered = json.dumps({"result": text}, ensure_ascii=False) if wrapped else text
    rows = [{"timestamp": ts(20), "type": "response_item", "payload": {
        "type": "function_call", "call_id": "receipt-call", "name": f"mcp__{provider}__batch",
        "arguments": json.dumps({"sid": "time", **args}, ensure_ascii=False)}}]
    if not pending:
        rows.append({"timestamp": ts(21), "type": "response_item", "payload": {
            "type": "function_call_output", "call_id": "receipt-call",
            "output": [{"type": "text", "text": delivered}]}})
    source(run, rows, name="transcript.jsonl")
    calls = probe._transcript_calls(str(run))
    assert len(calls) == 1
    return calls


@pytest.mark.parametrize("budget", [1000, 6000, 100000])
def test_actual_mcp_http_restore_same_partial_deferred_and_error_data(real_http, budget):
    pytest.importorskip("mcp")
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    path = real_http["paths"]["time"]
    refs = [transcript_store.read_record(path, line).ref for line in (1, 2, 4)]
    scope = investigation.scope(ledger, "agent", aid, ts(10), ts(4))
    args = {"requests": [
        {"tool": "record", "scope": scope, "args": {"ref": refs[1], "max_chars": 7}},
        {"tool": "expand", "scope": scope, "args": {"refs": refs, "max_chars": 7}},
        {"tool": "agent", "args": {"id": "not-in-pool", "at": ts(10)}},
        {"tool": "agent", "args": {"id": aid, "at": ts(10), "view": "records", "limit": 3}},
        {"tool": "events", "args": {"at": ts(10), "limit": 2}},
    ], "max_chars": budget}
    # Cache-access diagnostics are not evidence; warm both independent requests
    # identically before comparing their complete canonical transport trees.
    raw_events.inventory(ledger)
    text = mcp_batch(ledger, args)
    parsed = investigation.parse_receipt("batch", args, text)
    assert parsed is not None
    status, http_data, _ = real_http["post"]("batch", args)
    assert status == 200 and parsed["data"] == http_data
    assert http_data["items"][2]["status"] == "error"
    assert "edges" not in http_data and "query_trace" not in http_data
    for item in http_data["items"]:
        if item["status"] != "ok":
            assert item["delivery"]["records"] == [] and "data" not in item
        if item.get("data"):
            assert "LATE_SECRET" not in json.dumps(item["data"])
    if budget == 1000:
        assert http_data["delivery_summary"]["deferred"] > 0
    if budget == 100000:
        assert investigation.WIRE_MARKER in text
        record = http_data["items"][0]["data"]
        assert len(record["text"]) == 7 and record["next_offset"] == 7
        expansion = http_data["items"][1]["data"]["items"]
        assert [part["status"] for part in expansion] == ["error", "ok", "error"]
        assert http_data["items"][1]["delivery"]["records"][0]["chars"] == 7
        assert all(row["ref"] == refs[1] for row in http_data["items"][1]["delivery"]["records"])


def repeated_args(aid):
    return {"requests": [{"tool": "agent", "args": {"id": aid, "at": ts(10), "view": "records"}}] * 3,
            "max_chars": 100000}


@pytest.mark.parametrize("transport", ["wire", "legacy"])
def test_receipt_uses_real_native_pair_for_both_identity_and_trace(real_http, tmp_path_factory, monkeypatch, transport):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    args = repeated_args(aid)
    if transport == "legacy":
        def decline(*_args, **_kwargs):
            raise ValueError("exercise the real lossless legacy fallback")
        monkeypatch.setattr(batch_wire, "pack", decline)
    text = mcp_batch(ledger, args)
    assert (investigation.WIRE_MARKER in text) is (transport == "wire")
    calls = native_calls(tmp_path_factory.mktemp("wire-native-direct"), text, args)
    assert calls[0]["provenance"]["complete_pair"] is True
    identity = via.trace_identity(ledger, calls, {})
    assert identity["bound"] is True and identity["source"] == "investigation"
    before = deepcopy(calls)
    trace = investigation.project_trace(ledger, calls)
    assert calls == before and trace["edges"] == []
    row, = trace["steps"]
    assert row["status"] == "recorded_response" and len(row["items"]) == 3
    assert all(item["delivery"]["records"] for item in row["items"])
    assert all("data" not in item for item in row["items"])


@pytest.mark.parametrize("provider,pending", [("other", False), ("migloop", True)])
def test_consistent_receipt_without_trusted_provider_or_result_does_not_bind(real_http, tmp_path_factory, provider, pending):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    args = repeated_args(aid)
    text = mcp_batch(ledger, args)
    assert investigation.parse_receipt("batch", args, text)
    calls = native_calls(tmp_path_factory.mktemp("wire-native-untrusted"), text, args, provider=provider, pending=pending)
    assert via.trace_identity(ledger, calls, {})["bound"] is not True
    row, = investigation.project_trace(ledger, calls)["steps"]
    assert row["status"] == "unverified_response" and row["items"] == []


@pytest.mark.parametrize("transport", ["wire", "legacy"])
def test_supported_result_text_wrapper_has_consistent_identity_and_trace(real_http, tmp_path_factory, monkeypatch, transport):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    args = repeated_args(aid)
    if transport == "legacy":
        def decline(*_args, **_kwargs):
            raise ValueError("exercise legacy wrapper compatibility")
        monkeypatch.setattr(batch_wire, "pack", decline)
    text = mcp_batch(ledger, args)
    calls = native_calls(tmp_path_factory.mktemp("wire-native-result-wrapper"), text, args, wrapped=True)
    assert calls[0]["provenance"]["complete_pair"] is True
    row, = investigation.project_trace(ledger, calls)["steps"]
    assert row["status"] == "recorded_response"
    assert via.trace_identity(ledger, calls, {})["bound"] is True


def test_wire_canonical_hash_rejects_self_consistent_body_tamper(real_http):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    args = repeated_args(aid)
    text = mcp_batch(ledger, args)
    body, _, tail = text.rpartition(investigation.WIRE_MARKER)
    assert body and tail
    wire, receipt = json.loads(body), json.loads(tail)
    wire["batch"]["items"][0]["data"]["rows"][0]["preview"] = "altered preview"
    new_body = json.dumps(wire, ensure_ascii=False, separators=(",", ":"))
    receipt["body_sha256"] = investigation.digest(new_body)
    forged = new_body + investigation.WIRE_MARKER + json.dumps(receipt)
    assert investigation.parse_receipt("batch", args, forged) is None


@pytest.mark.parametrize("shape", ["extra_field", "nested_result"])
def test_safe_wrapper_compatibility_does_not_drop_or_recursively_unwrap_fields(real_http, tmp_path_factory, shape):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    args = repeated_args(aid)
    text = mcp_batch(ledger, args)
    value = {"result": text, "extra": "must not disappear"} if shape == "extra_field" else {"result": {"result": text}}
    calls = native_calls(tmp_path_factory.mktemp("wire-native-not-a-wrapper"), json.dumps(value), args)
    assert calls[0]["provenance"]["complete_pair"] is True
    assert via.trace_identity(ledger, calls, {})["bound"] is not True
    row, = investigation.project_trace(ledger, calls)["steps"]
    assert row["status"] == "unverified_response" and row["items"] == []
