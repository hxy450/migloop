"""The source timestamp error must name the actual contract, not another node."""

import json

from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, ts, use
from tests.test_inquiry_query_contract_regressions import document


def test_generation_context_is_valid_but_not_a_repair_window_change(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="early")),
            record(2, result("w")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 1)
    doc = document(ref)
    doc["target"]["since"] = ts(5)
    doc["findings"][0]["changes"] = [ref]
    graph = check(engine, json.dumps(doc))
    issue = next(i for i in graph["issues"] if i["where"] == "A.changes")
    assert issue["scope_kind"] == "target_change_window"
    assert issue["record_at"].startswith(ts(1)[:-1])
    assert issue["required_scope"]["since"].startswith(ts(5)[:-1])
    assert graph["document"] == doc and graph["mechanical_status"] == "needs_revision"
    del doc["findings"][0]["changes"]
    assert check(engine, json.dumps(doc))["mechanical_status"] == "valid"
    doc["findings"][0]["nodes"][0]["since"] = ts(5)
    graph = check(engine, json.dumps(doc))
    assert any(i.get("scope_kind") == "node" for i in graph["issues"])
    engine.store.close()


def test_edge_extra_evidence_must_respect_both_node_lower_bounds(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, {"type": "text", "text": "old context"}),
            record(5, use("w", file_path="A.ets", content="new")),
            record(6, result("w")),
        ],
    )
    old, write, receipt = [engine.store.locate("a.jsonl", line) for line in (1, 2, 3)]
    doc = document(write)
    finding = doc["findings"][0]
    finding["changes"] = [write, receipt]
    finding["nodes"][0]["since"] = ts(3)
    finding["nodes"].append(
        {**finding["nodes"][0], "id": "a", "kind": "agent", "key": "a", "since": ts(4)}
    )
    finding["edges"] = [
        {
            "from": "a",
            "to": "f",
            "relation": "write",
            "claim": "native write",
            "evidence": [write, receipt, old],
        }
    ]
    graph = check(engine, json.dumps(doc))
    assert graph["mechanical_status"] == "needs_revision"
    issue = next(i for i in graph["issues"] if i.get("scope_kind") == "edge")
    assert issue["required_scope"]["since"].startswith(ts(4)[:-1])
    assert not graph["edges"] and len(graph["unverified_edges"]) == 1
    finding["edges"][0]["evidence"].remove(old)
    valid = check(engine, json.dumps(doc))
    assert valid["mechanical_status"] == "valid" and len(valid["edges"]) == 1, (
        valid["issues"],
        valid["unverified_edges"],
        valid["missing_evidence_links"],
    )
    engine.store.close()
