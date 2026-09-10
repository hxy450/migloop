"""Pure transport reduction: explicit recovery, no inferred evidence or visits."""
from copy import deepcopy
from datetime import datetime
import json

import pytest

from migloop import batch_wire, investigation
from tests.test_temporal import corpus, ts


def fixture(data=None):
    scope = {"kind": "file", "key": "/p/A.ets", "at": ts(10), "since_ts": None}
    requests = [{"tool": "search", "args": {"q": "needle", "at": ts(10)}, "scope": scope}]
    if data is None:
        data = {"schema": "migloop-time-view/1", "scope": scope, "rows": [
            {"ref": "raw:abc:L1:def", "preview": "needle 中文😀\ncontent: false", "ts": ts(5)}],
            "total": 10, "offset": 0, "limit": 1, "next_offset": 1,
            "unknown": None, "complete": False, "gaps": [{"error": "unknown source"}]}
    delivery = investigation._delivery(data)
    batch = {"schema": investigation.SCHEMA, "ledger": "ledger:test", "items": [{
        "item_index": 0, "tool": "search", "args": deepcopy(requests[0]["args"]), "status": "ok",
        "scope": deepcopy(scope), "data": data, "delivery": delivery,
        "budget_adjusted": True, "original_data_chars": 10000,
        "continuations": [{"kind": "page", "scope": deepcopy(scope), "offset": 1,
                           "args_patch": {"offset": 1, "limit": 40}}]}],
        "delivery_summary": {"ok": 1, "error": 0, "deferred": 0}, "attention": [],
        "max_chars": 1000, "data_chars": 700, "budget_scope": "serialized_data_only"}
    return batch, requests


def same_json(left, right):
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(right, ensure_ascii=False, sort_keys=True)


def test_explicit_lossless_roundtrip_preserves_raw_data_and_cursors():
    original, requests = fixture()
    saved, saved_requests = deepcopy(original), deepcopy(requests)
    wire = batch_wire.pack(original, requests)
    item = wire["batch"]["items"][0]
    assert wire["schema"] == batch_wire.SCHEMA
    assert wire["ledger"] == original["ledger"] == wire["batch"]["ledger"]
    assert wire["omitted"] == {"items": [{"item_index": 0, "fields": ["args", "scope", "delivery"]}], "top": ["attention"]}
    assert not {"args", "scope", "delivery"} & item.keys()
    assert item["data"] == original["items"][0]["data"]
    assert item["continuations"] == original["items"][0]["continuations"]
    encoded = json.dumps(wire, ensure_ascii=False)
    restored = batch_wire.unpack(encoded, requests)
    assert same_json(restored, original) and original == saved and requests == saved_requests
    restored["items"][0]["data"]["rows"][0]["preview"] = "changed copy"
    assert original == saved and wire["batch"]["items"][0]["data"] == saved["items"][0]["data"]


def test_real_canonical_batch_roundtrips_without_requery(tmp_path, monkeypatch):
    ledger, aid, _ = corpus(tmp_path)
    requests = [
        {"tool": "agent", "args": {"id": aid, "at": ts(10), "view": "records", "limit": 1}},
        {"tool": "agent", "args": {"id": "absent", "at": ts(10)}},
        {"tool": "file", "args": {"path": "/p/A.ets", "at": ts(10)}},
    ]
    original = investigation.batch(ledger, requests, max_chars=16000)
    monkeypatch.setattr(investigation, "query", lambda *a, **k: pytest.fail("codec must not query"))
    monkeypatch.setattr(investigation, "_delivery", lambda *a, **k: pytest.fail("wire v1 extraction must be pinned"))
    wire = batch_wire.pack(original, requests)
    assert same_json(batch_wire.unpack(wire, requests), original)
    assert "LATE_SECRET" not in json.dumps(wire)
    assert "edges" not in wire


def test_deferred_keeps_scope_error_continuations_and_empty_delivery():
    original, requests = fixture()
    item = original["items"][0]
    item.pop("data")
    item.update(status="deferred", delivery={"records": []}, error="metadata does not fit")
    original["attention"] = [{"item_index": 0, "tool": "search", "status": "deferred", "reason": item["error"]}]
    wire = batch_wire.pack(original, requests)
    assert wire["omitted"]["items"][0]["fields"] == ["args"]
    assert wire["batch"]["items"][0]["scope"] == item["scope"]
    assert wire["batch"]["items"][0]["delivery"] == {"records": []}
    assert same_json(batch_wire.unpack(wire, requests), original)


def test_partial_field_and_withheld_other_side_remain_partial():
    scope = {"kind": "agent", "key": "a", "at": ts(10), "since_ts": ts(4)}
    raw = {"schema": "migloop-raw-field/1", "ref": "raw:abc:L2:def", "pointer": "/body",
           "text": "中文😀\r\n", "representation": "decoded_string", "offset": 2, "chars": 100,
           "next_offset": 7, "field_sha256": "original-field-hash"}
    data = {"schema": "migloop-evidence-expansion/1", "scope": scope, "items": [
        {"item_index": 0, "status": "ok", "records": [raw], "withheld": [
            {"ref": "raw:abc:L3:future", "reason": "outside cutoff"}]},
        {"item_index": 1, "status": "error", "records": [], "error": "source stale"}]}
    original, requests = fixture(data)
    original["items"][0]["scope"] = scope
    wire = batch_wire.pack(original, requests)
    restored = batch_wire.unpack(wire, requests)
    assert same_json(restored, original)
    record, = restored["items"][0]["delivery"]["records"]
    assert record["extent"] == "raw_field_segment" and record["chars"] == len(raw["text"])
    assert record["offset"] == 2 and record["next_offset"] == 7
    assert "future" not in json.dumps(record)


@pytest.mark.parametrize("schema", ["future-query/9", None, False, 0, {"future": True}])
def test_unknown_data_schema_keeps_explicit_delivery(schema):
    original, requests = fixture()
    original["items"][0]["data"]["schema"] = schema
    original["items"][0]["delivery"]["data_schema"] = schema
    wire = batch_wire.pack(original, requests)
    assert "delivery" not in wire["omitted"]["items"][0]["fields"]
    assert same_json(batch_wire.unpack(wire, requests), original)


@pytest.mark.parametrize("field", ["args", "scope", "delivery", "attention"])
def test_nonidentical_fields_are_kept_including_null_false_and_unknown(field):
    original, requests = fixture()
    if field == "args":
        requests[0]["args"]["extra"] = 0
        original["items"][0][field]["extra"] = False
    elif field == "scope":
        original["items"][0][field]["since_ts"] = False
        original["items"][0]["data"][field]["since_ts"] = 0
    elif field == "delivery":
        original["items"][0][field]["semantic_checked"] = 0
        original["items"][0][field]["unknown"] = None
    else:
        original[field] = None
    wire = batch_wire.pack(original, requests)
    assert field in (wire["batch"] if field == "attention" else wire["batch"]["items"][0])
    assert same_json(batch_wire.unpack(wire, requests), original)


def test_cross_scope_values_are_not_reconstructed_from_another_item():
    original, requests = fixture()
    original["items"][0]["scope"]["key"] = "/another/A.ets"
    wire = batch_wire.pack(original, requests)
    assert "scope" not in wire["omitted"]["items"][0]["fields"]
    assert same_json(batch_wire.unpack(wire, requests), original)


def test_locator_only_navigation_never_becomes_raw_delivery():
    data = {"schema": "migloop-time-atom/1", "sections": {"messages": {"rows": []}},
            "body_sources": {"entries": [{"ref": "raw:only:L9:locator", "chars": 50000}]},
            "raw_index": {"query": {"tool": "record", "args": {"ref": "raw:only:L9:locator"}}}}
    original, requests = fixture(data)
    restored = batch_wire.unpack(batch_wire.pack(original, requests), requests)
    assert restored["items"][0]["delivery"]["records"] == []
    assert same_json(restored["items"][0]["data"], data)


@pytest.mark.parametrize("mutation", ["request", "index", "bool_index", "duplicate_omission", "unknown_field",
                                      "explicit_and_omitted", "missing_marker", "scope_missing", "unknown_schema", "extra_wrapper"])
def test_structural_and_request_tampering_is_rejected(mutation):
    original, requests = fixture()
    wire = batch_wire.pack(original, requests)
    if mutation == "request": requests[0]["args"]["at"] = ts(15)
    elif mutation == "index": wire["batch"]["items"][0]["item_index"] = 1
    elif mutation == "bool_index": wire["omitted"]["items"][0]["item_index"] = False
    elif mutation == "duplicate_omission": wire["omitted"]["items"].append(deepcopy(wire["omitted"]["items"][0]))
    elif mutation == "unknown_field": wire["omitted"]["items"][0]["fields"].append("status")
    elif mutation == "explicit_and_omitted": wire["batch"]["items"][0]["args"] = requests[0]["args"]
    elif mutation == "missing_marker": wire["omitted"]["items"] = []
    elif mutation == "scope_missing": wire["batch"]["items"][0]["data"].pop("scope")
    elif mutation == "unknown_schema": wire["batch"]["items"][0]["data"]["schema"] = "future/1"
    else: wire["alias_table"] = {}
    with pytest.raises(ValueError):
        batch_wire.unpack(wire, requests)


def test_missing_optional_fields_are_not_inferred_without_markers():
    original, requests = fixture()
    original.pop("attention")
    original["items"][0].pop("scope")
    wire = batch_wire.pack(original, requests)
    restored = batch_wire.unpack(wire, requests)
    assert "attention" not in restored and "scope" not in restored["items"][0]
    assert same_json(restored, original)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), datetime(2026, 1, 1), {1: "non-string key"}, (1, 2)])
def test_non_json_input_is_rejected_without_coercion(bad):
    original, requests = fixture()
    original["items"][0]["data"]["bad"] = bad
    with pytest.raises(ValueError):
        batch_wire.pack(original, requests)


def test_duplicate_json_keys_are_rejected_at_every_level():
    original, requests = fixture()
    text = json.dumps(batch_wire.pack(original, requests))
    for changed in (text.replace('"schema":', '"schema":"duplicate", "schema":', 1),
                    text.replace('"total": 10', '"total": 10, "total": 11')):
        with pytest.raises(ValueError, match="strict bounded JSON"):
            batch_wire.unpack(changed, requests)


def test_depth_size_nodes_and_cycles_are_bounded():
    original, requests = fixture()
    for limits in ({"max_chars": 100}, {"max_depth": 2}, {"max_nodes": 5}):
        with pytest.raises(ValueError):
            batch_wire.pack(original, requests, **limits)
    wire = batch_wire.pack(original, requests)
    with pytest.raises(ValueError):
        batch_wire.unpack(json.dumps(wire), requests, max_chars=100)
    with pytest.raises(ValueError):
        batch_wire.unpack("[" * 2000 + "]" * 2000, requests)
    original["cycle"] = original
    with pytest.raises(ValueError, match="cyclic"):
        batch_wire.pack(original, requests)


@pytest.mark.parametrize("arg", [{"max_chars": True}, {"max_depth": 0}, {"max_nodes": -1}, {"max_depth": 129}])
def test_limit_options_are_not_coerced(arg):
    original, requests = fixture()
    with pytest.raises(ValueError):
        batch_wire.pack(original, requests, **arg)


def test_request_hash_is_not_native_response_authentication():
    original, requests = fixture()
    wire = batch_wire.pack(original, requests)
    wire["batch"]["items"][0]["data"]["rows"][0]["preview"] = "changed body"
    # The integration must reject changed returned bytes using its receipt and
    # native transcript. A pure codec cannot authenticate its own input origin.
    restored = batch_wire.unpack(wire, requests)
    assert restored["items"][0]["data"]["rows"][0]["preview"] == "changed body"
    assert "verified" not in wire and "semantic_checked" not in wire


@pytest.mark.parametrize("schema", sorted(batch_wire._DATA_SCHEMAS_V1))
def test_fixed_v1_delivery_matches_current_known_projection_without_body_inference(schema):
    data = {"schema": schema, "scope": {"kind": "pool", "key": None, "at": ts(10), "since_ts": None},
            "rows": [{"ref": "#5@L1", "line": 1, "text": "derived line"},
                     {"ref": "raw:abc:L2:def", "diff": "+line", "diff_chars": 200, "truncated": True}],
            "items": [{"records": [{"ref": "raw:abc:L3:def", "text": "field😀", "pointer": "/output",
                                     "offset": 4, "next_offset": 10}]}],
            "undated": {"rows": [{"ref": "raw:abc:L4:def", "preview": "undated excerpt"}]},
            "body_sources": {"entries": [{"ref": "raw:abc:L9:def", "chars": 50000}]},
            "sections": {"messages": {"rows": [{"ref": "raw:abc:L5:def", "preview": "message"}]}}}
    expected = investigation._delivery(data)
    assert same_json(batch_wire._delivery_v1(data), expected)
    assert "L9" not in json.dumps(expected)
    original, requests = fixture(data)
    assert same_json(batch_wire.unpack(batch_wire.pack(original, requests), requests), original)


def test_unknown_or_malformed_delivery_shape_is_preserved_not_reclassified():
    original, requests = fixture()
    original["items"][0]["data"]["rows"][0]["preview"] = False
    original["items"][0]["delivery"] = {"records": [], "unknown": True, "reason": "unrecognized projection"}
    wire = batch_wire.pack(original, requests)
    assert "delivery" in wire["batch"]["items"][0]
    assert same_json(batch_wire.unpack(wire, requests), original)


def test_real_batch_error_items_keep_malformed_original_requests(tmp_path):
    ledger, _, _ = corpus(tmp_path)
    requests = [None, {"tool": "search", "args": False}, {"tool": "unknown", "args": {"x": None}}]
    original = investigation.batch(ledger, requests)
    assert all(item["status"] == "error" for item in original["items"])
    assert same_json(batch_wire.unpack(batch_wire.pack(original, requests), requests), original)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_tool"])
def test_canonical_request_order_cannot_be_remapped(mutation):
    original, requests = fixture()
    if mutation == "missing": original["items"] = []
    elif mutation == "duplicate": original["items"].append(deepcopy(original["items"][0]))
    else: original["items"][0]["tool"] = "record"
    with pytest.raises(ValueError):
        batch_wire.pack(original, requests)


@pytest.mark.parametrize("text", ['{"x": NaN}', '{"x": Infinity}', '{"x": "\\ud800"}'])
def test_untrusted_text_nonfinite_or_non_utf8_does_not_escape_as_a_500(text):
    _, requests = fixture()
    with pytest.raises(ValueError):
        batch_wire.unpack(text, requests)


@pytest.mark.parametrize("ledger", ["ledger:other", "", None, False, 0])
def test_top_ledger_must_match_canonical_exactly(ledger):
    original, requests = fixture()
    wire = batch_wire.pack(original, requests)
    wire["ledger"] = ledger
    with pytest.raises(ValueError, match="ledger"):
        batch_wire.unpack(wire, requests)


def test_top_ledger_is_required_not_inferred_from_batch():
    original, requests = fixture()
    wire = batch_wire.pack(original, requests)
    wire.pop("ledger")
    with pytest.raises(ValueError):
        batch_wire.unpack(wire, requests)
