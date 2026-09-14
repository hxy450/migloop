"""A native call reference selects evidence; it is not a hand-copied receipt pair."""

import json

import pytest

from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, ts, use
from migloop.inquiry.store import timestamp


def document(engine, evidence, at=ts(5)):
    return {"schema": "inquiry/1", "target": {"file": "A.ets", "at": at}, "findings": [{
        "id": "A", "title": "write", "reason": "write evidence", "changes": evidence,
        "nodes": [{"id": "author", "kind": "agent", "key": "a", "at": at, "role": "origin", "reason": "write", "evidence": evidence},
                  {"id": "target", "kind": "file", "key": "A.ets", "at": at, "role": "repaired", "reason": "target", "evidence": evidence}],
        "edges": [{"from": "author", "to": "target", "relation": "write", "evidence": evidence, "claim": "native write"}]}]}


@pytest.mark.parametrize("side", [1, 2])
def test_one_unique_native_ref_binds_byte_checked_pair_without_rewriting_draft(tmp_path, side):
    engine = build(tmp_path, [record(1, use("w", file_path="/proj/A.ets", content="bad")), record(2, result("w"))])
    try:
        evidence = [engine.store.locate("a.jsonl", side)]
        doc = document(engine, evidence)
        graph = check(engine, json.dumps(doc))
        assert graph["mechanical_status"] == "valid"
        edge, = graph["edges"]
        assert edge["strength"] == "confirmed"
        assert set(edge["evidence"]) == {engine.store.locate("a.jsonl", 1), engine.store.locate("a.jsonl", 2)}
        assert graph["document"] == doc and doc["findings"][0]["edges"][0]["evidence"] == evidence
        assert not edge["semantic_verified"]
    finally:
        engine.store.close()


def test_pair_completion_never_leaks_a_future_receipt(tmp_path):
    engine = build(tmp_path, [record(1, use("w", file_path="/proj/A.ets", content="bad")), record(9, result("w"))])
    try:
        request = engine.store.locate("a.jsonl", 1)
        graph = check(engine, json.dumps(document(engine, [request])))
        edge, = graph["edges"]
        assert edge["strength"] == "candidate" and edge["evidence"] == [request]
    finally:
        engine.store.close()


def test_mate_bytes_changed_cannot_certify_a_request_only_reference(tmp_path):
    engine = build(tmp_path, [record(1, use("w", file_path="/proj/A.ets", content="bad")), record(2, result("w"))])
    try:
        doc = document(engine, [engine.store.locate("a.jsonl", 1)])
        path = tmp_path / "a.jsonl"
        path.write_text(path.read_text(encoding="utf-8").replace('"ok"', '"NO"'), encoding="utf-8")
        graph = check(engine, json.dumps(doc))
        assert not graph["edges"] and graph["unverified_edges"]
    finally:
        engine.store.close()


def test_multi_call_row_still_needs_exact_link(tmp_path):
    engine = build(tmp_path, [record(1, use("w1", file_path="/proj/A.ets", content="a"), use("w2", file_path="/proj/A.ets", content="b")),
                              record(2, result("w1"), result("w2"))])
    try:
        doc = document(engine, [engine.store.locate("a.jsonl", 1)])
        graph = check(engine, json.dumps(doc))
        assert not graph["edges"] and graph["unverified_edges"]
        operation = engine.relations("file", "/proj/A.ets", timestamp(ts(5)))[0]
        link = engine.link_view(operation, ts(5))["link"]
        doc["findings"][0]["edges"] = [{"from": "author", "to": "target", "link": link, "claim": "specific call"}]
        graph = check(engine, json.dumps(doc))
        assert len(graph["edges"]) == 1 and graph["edges"][0]["operation"] == operation["id"]
    finally:
        engine.store.close()


def test_widening_a_node_cannot_move_evidence_past_report_observation(tmp_path):
    engine = build(tmp_path, [record(1, use("early", file_path="/proj/A.ets", content="early")), record(2, result("early")),
                              record(6, use("late", file_path="/proj/A.ets", content="late")), record(7, result("late"))])
    try:
        doc = document(engine, [engine.store.locate("a.jsonl", 3)], at=ts(9))
        doc["target"]["at"] = ts(3)
        doc["findings"][0]["changes"] = [engine.store.locate("a.jsonl", 1)]
        graph = check(engine, json.dumps(doc))
        assert graph["mechanical_status"] == "needs_revision" and not graph["edges"]
        assert any(i["where"] == "A.author" for i in graph["issues"])
        assert all(not n["valid_refs"] for n in graph["nodes"])
    finally:
        engine.store.close()
