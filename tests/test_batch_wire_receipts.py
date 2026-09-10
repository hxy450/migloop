"""Actual selected data and new wire bytes must agree, not just self-report."""
from copy import deepcopy
import json

import pytest

from migloop import atoms, batch_wire, investigation, via
from migloop.time_receipts import digest
from tests.test_temporal_atom import message, pool, ts


def scenario(tmp_path):
    ledger, agent, _ = pool(tmp_path, [message(1, "original evidence " * 100)])
    args = {"requests": [{"tool": "agent", "args": {"id": agent, "at": ts(3)}}] * 3,
            "max_chars": 100000}
    data = investigation.batch(ledger, **args)
    text = investigation.render_batch_data(data, **args)
    assert investigation.WIRE_MARKER in text
    return ledger, args, data, text


def old_wire(data, args):
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    receipt = {"schema": "migloop-investigation-receipt/1", "ledger": data["ledger"],
               "request_sha256": digest(args), "body_sha256": digest(body)}
    return body + investigation.MARKER + json.dumps(receipt, separators=(",", ":"))


def test_new_and_historical_receipts_restore_identical_canonical_data(tmp_path):
    ledger, args, data, text = scenario(tmp_path)
    old = old_wire(data, args)
    assert len(text) < len(old)
    for rendered in (text, old):
        parsed = investigation.parse_receipt("batch", {"sid": "test", **args}, rendered)
        assert parsed["data"] == data
        assert parsed["receipt"]["ledger"] == atoms.ledger_identity(ledger)
    assert batch_wire.unpack(text.split(investigation.WIRE_MARKER)[0], args["requests"]) == data


def test_new_wire_trace_keeps_failed_items_and_requires_native_pair(tmp_path):
    ledger, args, _data, text = scenario(tmp_path)
    call = {"tool": "batch", "input": {"sid": "test", **args}, "text": text,
            "has_result": True, "provenance": {"complete_pair": True}}
    trace = investigation.project_trace(ledger, [call])
    assert trace["edges"] == []
    row, = trace["steps"]
    assert row["status"] == "recorded_response" and len(row["items"]) == 3
    assert all(item["delivery"]["records"] for item in row["items"])
    assert via.trace_identity(ledger, [call], {})["bound"] is True
    for change in ({"has_result": False}, {"delivery_truncated": True},
                   {"provenance": {"origin_unverified": True}}, {"is_error": True}):
        item = investigation.project_trace(ledger, [{**call, **change}])["steps"][0]
        assert item["status"] == "unverified_response" and not item["items"]


@pytest.mark.parametrize("change", ["body", "request", "budget", "canonical", "ledger", "duplicate_receipt_key"])
def test_tampered_bytes_requests_and_reconstruction_rejected(tmp_path, change):
    _, args, _data, text = scenario(tmp_path)
    args = deepcopy(args)
    body, _, tail = text.rpartition(investigation.WIRE_MARKER)
    receipt = json.loads(tail)
    if change == "body":
        body = body.replace("original evidence", "tampered evidence", 1)
    elif change == "request":
        args["requests"][0]["args"]["at"] = ts(4)
    elif change == "budget":
        args["max_chars"] -= 1
    elif change == "canonical":
        receipt["canonical_sha256"] = "0" * 64
    elif change == "ledger":
        receipt["ledger"] = "another-ledger"
    elif change == "duplicate_receipt_key":
        tail = tail[:-1] + ',"ledger":' + json.dumps(receipt["ledger"]) + "}"
    rendered = body + investigation.WIRE_MARKER + (tail if change == "duplicate_receipt_key" else json.dumps(receipt))
    assert investigation.parse_receipt("batch", args, rendered) is None


def test_codec_limits_fallback_preserves_original_json_not_truncated_data(tmp_path, monkeypatch):
    _, args, data, _ = scenario(tmp_path)
    def decline(*_args, **_kwargs):
        raise ValueError("codec safety limit")
    monkeypatch.setattr(batch_wire, "pack", decline)
    text = investigation.render_batch_data(data, **args)
    assert investigation.WIRE_MARKER not in text
    assert investigation.parse_receipt("batch", args, text)["data"] == data


def test_wire_for_other_tool_is_not_accepted_as_scalar_receipt(tmp_path):
    _, args, _, text = scenario(tmp_path)
    assert investigation.parse_receipt("changes", args, text) is None
