"""Expose the saved reconciliation difference without judging script effects."""

import json

import pytest

from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, use
from tests.test_inquiry_query_contract_regressions import document


def test_review_lists_opaque_gap_without_promoting_it_or_changing_original(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="code")),
            record(2, result("w")),
            record(3, use("x", "Bash", command="python mysterious.py A.ets")),
            record(4, result("x", "done")),
        ],
    )
    doc = document(engine.store.locate("a.jsonl", 1))
    doc["findings"][0]["changes"] = [engine.store.locate("a.jsonl", 1)]
    graph = check(engine, json.dumps(doc), save=True)
    query = {
        "op": "review",
        "report_id": graph["report_id"],
        "view": "coverage",
        "limit": 1,
    }
    data = engine.query(query)
    assert data["view"] == "coverage" and data["total"] == 1
    assert data["rows"][0]["category"] == "unassessed"
    assert data["rows"][0]["recorded_effects"] == []
    assert data["rows"][0]["ref"] == engine.store.handle(
        "e", {"ref": engine.store.locate("a.jsonl", 3)}
    )
    assert graph["document"] == doc and len(graph["edges"]) == 1
    assert not graph["coverage"]["complete"] and not graph["semantic_verified"]
    other = Engine(engine.store, session="different", origin="mcp")
    with pytest.raises(ValueError, match="different investigator"):
        other.query(query)
    with pytest.raises(ValueError, match="evidence or coverage"):
        engine.query({**query, "view": "whatever"})
    engine.store.close()
