"""Explicit opens select complete originals; budgets and time remain honest."""
from copy import deepcopy
import json

import pytest

from migloop import atom_queries, delivery_budget, investigation, temporal, transcript_store
from tests.test_temporal_atom import message, pool, ts


@pytest.mark.parametrize("length", [13001, 24001, 130001])
def test_default_expansion_and_messages_do_not_pretruncate_selected_text(tmp_path, length):
    original = ("原文\\\n\" detail; " * 12000)[:length]
    ledger, aid, _ = pool(tmp_path, [message(1, original)])
    data = investigation.query(ledger, "agent", {"id": aid, "at": ts(3), "view": "messages"})
    row, = data["sections"]["messages"]["rows"]
    assert row["preview"] == original and row["preview_span"]["chars"] == len(original)
    expanded = investigation.query(ledger, "expand", {"refs": [{"ref": row["ref"], "pointer": row["pointer"]}],
                                                       "scope": data["scope"]})
    record, = expanded["items"][0]["records"]
    assert record["text"] == original and record["complete"] and record["next_offset"] is None
    raw = temporal.record_data(ledger, row["ref"], at=ts(3))
    assert raw["text"] == transcript_store.resolve(ledger, row["ref"]).raw
    assert raw["complete"] and raw["returned_chars"] == len(raw["text"])
    via_locator = investigation.query(ledger, "expand", {**row["expand_query"]["args"], "scope": data["scope"]})
    assert via_locator["items"][0]["records"][0]["text"] == original
    # Scalar JSON and batch share the same selection. The overview stays small.
    assert atom_queries.json_data(ledger, "agent", {"id": aid, "at": ts(3), "view": "messages"})["sections"] == data["sections"]
    overview = investigation.query(ledger, "agent", {"id": aid, "at": ts(3)})
    assert len(overview["sections"]["messages"]["rows"][0]["preview"]) == 4096


def test_default_batch_does_not_recut_explicit_full_open(tmp_path):
    original = "all selected source; " * 8000
    ledger, aid, _ = pool(tmp_path, [message(1, original)])
    row = temporal.query(ledger, kind="agent", key=aid, at=ts(3))["rows"][0]
    args = {"refs": [{"ref": row["ref"], "pointer": "/message/content"}],
            "scope": investigation.scope(ledger, "agent", aid, ts(3))}
    batch = investigation.batch(ledger, [{"tool": "expand", "args": args}])
    body = batch["items"][0]["data"]["items"][0]["records"][0]
    assert body["text"] == original and body["complete"]
    assert batch["max_chars"] is None and batch["data_chars"] > 100000


def test_explicit_budget_and_character_page_never_claim_whole_original(tmp_path):
    original = "selected original; " * 1600
    ledger, aid, _ = pool(tmp_path, [message(1, original), message(5, "FUTURE_SECRET")])
    scope = investigation.scope(ledger, "agent", aid, ts(3))
    rows = temporal.query(ledger, kind="agent", key=aid, at=ts(6))["rows"]
    args = {"refs": [{"ref": rows[0]["ref"], "pointer": "/message/content"}], "scope": scope}
    selected = investigation.query(ledger, "expand", args)
    before = deepcopy(selected)
    fitted = delivery_budget.fit(selected, 4000)
    part = fitted["data"]["items"][0]["records"][0]
    assert not part["complete"] and 0 < part["returned_chars"] == len(part["text"]) < len(original)
    assert part["next_offset"] == len(part["text"])
    remainder = investigation.query(ledger, "expand", {**args, "offset": part["next_offset"]})
    tail = remainder["items"][0]["records"][0]
    assert part["text"] + tail["text"] == original and not tail["complete"]
    assert selected == before
    page = investigation.query(ledger, "expand", {**args, "offset": 7, "max_chars": 9})
    assert page["items"][0]["records"][0]["text"] == original[7:16]
    denied = investigation.query(ledger, "expand", {**args, "refs": [rows[1]["ref"]]})
    assert denied["items"][0]["status"] == "error" and "FUTURE_SECRET" not in str(denied)


def test_batch_continues_each_selected_record_at_its_own_offset(tmp_path):
    originals = ["first-original-" * 800, "second-original-" * 500]
    ledger, aid, _ = pool(tmp_path, [message(i + 1, value) for i, value in enumerate(originals)])
    scope = investigation.scope(ledger, "agent", aid, ts(3))
    rows = temporal.query(ledger, kind="agent", key=aid, at=ts(3))["rows"]
    requests = [{"tool": "expand", "scope": scope, "args": {
        "refs": [{"ref": row["ref"], "pointer": "/message/content"}], "max_chars": size}}
        for row, size in zip(rows, (100, 250))]
    first = investigation.batch(ledger, requests)
    continuations, prefixes = [], []
    for item, original in zip(first["items"], requests):
        record = item["data"]["items"][0]["records"][0]
        prefixes.append(record["text"])
        continuations.append({"tool": "expand", "scope": scope, "args": {
            "refs": original["args"]["refs"], "offset": record["next_offset"]}})
    assert [r["args"]["offset"] for r in continuations] == [100, 250]
    tail = investigation.batch(ledger, continuations)
    for original, prefix, item in zip(originals, prefixes, tail["items"]):
        record = item["data"]["items"][0]["records"][0]
        assert prefix + record["text"] == original and record["next_offset"] is None
        assert not record["complete"]  # This response alone is the suffix.


@pytest.mark.parametrize("wire", [False, True])
def test_old_omitted_batch_budget_receipt_is_not_reinterpreted_as_unbounded(tmp_path, wire):
    from migloop import batch_wire
    from migloop.time_receipts import digest
    ledger, aid, _ = pool(tmp_path, [message(1, "input" * 300)])
    requests = [{"tool": "agent", "args": {"id": aid, "at": ts(3)}}]
    data = investigation.batch(ledger, requests, max_chars=100000)
    if wire:
        body = json.dumps(batch_wire.pack(data, requests), ensure_ascii=False, separators=(",", ":"))
        receipt = {"schema": investigation.WIRE_RECEIPT, "codec": batch_wire.SCHEMA,
            "ledger": data["ledger"], "request_sha256": digest({"requests": requests, "max_chars": 100000}),
            "body_sha256": digest(body), "canonical_sha256": digest(data)}
        marker = investigation.WIRE_MARKER
    else:
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        receipt = {"schema": "migloop-investigation-receipt/1", "ledger": data["ledger"],
            "request_sha256": digest({"requests": requests, "max_chars": 100000}), "body_sha256": digest(body)}
        marker = investigation.MARKER
    original = body + marker + json.dumps(receipt)
    assert investigation.parse_receipt("batch", {"requests": requests}, original)["data"] == data
    assert investigation.parse_receipt("batch", {"requests": requests, "max_chars": None}, original) is None
    current = investigation.render_batch(ledger, requests)
    assert investigation.parse_receipt("batch", {"requests": requests}, current)["data"]["max_chars"] is None
    assert investigation.parse_receipt("batch", {"requests": requests, "max_chars": 100000}, current) is None


def test_old_expand_default_and_raw_record_receipts_keep_original_limits(tmp_path):
    from migloop import atoms, time_receipts
    from migloop.time_receipts import digest
    ledger, aid, _ = pool(tmp_path, [message(1, "historical" * 4000)])
    ref = temporal.query(ledger, kind="agent", key=aid, at=ts(3))["rows"][0]["ref"]
    args = {"refs": [ref], "scope": investigation.scope(ledger, "agent", aid, ts(3))}
    data = {**investigation.query(ledger, "expand", {**args, "max_chars": 12000}), "ledger": atoms.ledger_identity(ledger)}
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    receipt = {"schema": "migloop-investigation-receipt/1", "argument_normalization": "time-query/2",
        "tool": "expand", "ledger": data["ledger"], "body_sha256": digest(body),
        "request_sha256": digest({"offset": 0, "max_chars": 12000, "include_undated": False, **args})}
    original = body + investigation.MARKER + json.dumps(receipt)
    assert investigation.parse_receipt("expand", args, original)["data"] == data
    assert investigation.parse_receipt("expand", {**args, "max_chars": None}, original) is None
    request = {"ref": ref, "at": ts(3)}
    selected = temporal.record_data(ledger, ref, at=ts(3), max_chars=20000)
    rendered = temporal.render(selected)
    canonical = {**time_receipts.canonical("record", request), "max_chars": 20000}
    old = {"schema": "migloop-time-receipt/1", "tool": "record", "ledger": data["ledger"],
        "request_sha256": digest(canonical), "body_sha256": digest(rendered), "node": None,
        "raw_refs_sha256": digest([ref]), "raw_count": 1, "relation": None}
    assert time_receipts.parse(ledger, "record", request, rendered + time_receipts.MARKER + json.dumps(old))
    current = atom_queries.render_text(ledger, "", "record", request)
    assert time_receipts.parse(ledger, "record", request, current)
    assert time_receipts.parse(ledger, "record", {**request, "max_chars": 20000}, current) is None
