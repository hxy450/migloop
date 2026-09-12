"""Other actors' observations are searchable, without becoming writer evidence."""

import asyncio
import json

import pytest

from migloop.inquiry.interfaces import build_mcp
from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, ts, use
from tests.test_inquiry_query_contract_regressions import document


def test_pool_returns_keep_time_owner_and_record_type_without_new_effects(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="code")),
            record(2, result("w")),
        ],
        [
            record(1, result("prior", "probe completed")),
            record(3, use("probe", "Bash", command="execute_probe")),
            record(4, result("probe", "probe completed")),
            record(5, {"type": "text", "text": "probe completed is only a message"}),
            record(8, result("future", "probe completed")),
            record(None, result("undated", "probe completed")),
        ],
    )
    before = engine.store.rows("SELECT * FROM effects ORDER BY id")
    query = {
        "op": "search",
        "kind": "pool",
        "view": "returns",
        "since": ts(2),
        "at": ts(6),
        "terms": ["probe completed"],
        "limit": 1,
    }
    data = engine.query(query)
    assert data["total"] == 1 and data["undated_records"] == 1
    assert data["rows"][0]["agent"] == "b" and data["rows"][0]["line"] == 3
    assert data["rows"][0]["tools"] == ["Bash"]
    assert data["next"] is None
    assert (
        engine.query(
            {
                "op": "search",
                "scope": data["scope_id"],
                "view": "returns",
                "terms": ["probe completed"],
            }
        )["total"]
        == 1
    )
    assert engine.query({**query, "view": "records"})["total"] == 2
    assert engine.query({**query, "undated": True})["total"] == 2
    assert engine.store.rows("SELECT * FROM effects ORDER BY id") == before
    assert not [row for row in before if row["agent"] == "b"]
    with pytest.raises(ValueError, match="search view"):
        engine.query({**query, "view": "inputs"})
    engine.store.close()


def test_writer_review_offers_pool_scope_without_certifying_other_checker(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="code")),
            record(2, result("w")),
        ],
        [
            record(3, use("p", "Bash", command="execute_probe")),
            record(4, result("p", "probe completed")),
        ],
    )
    doc = document(engine.store.locate("a.jsonl", 1))
    graph = check(engine, json.dumps(doc))
    window = graph["evidence_review"]["post_write_returns"][0]
    assert window["agent"] == "a" and window["total"] == 0
    query = window["pool_returns_query"]
    assert query["kind"] == "pool" and "key" not in query
    assert query["since"] == window["since"] and query["at"] == window["at"]
    data = engine.query({**query, "terms": ["probe completed"]})
    assert data["total"] == 1 and data["rows"][0]["agent"] == "b"
    assert graph["document"] == doc and len(graph["edges"]) == 1
    assert graph["semantic_verified"] is False and engine.trace() == []
    engine.store.close()


def test_mcp_submit_delivers_the_cross_actor_query_not_just_server_metadata(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="code")),
            record(2, result("w")),
        ],
        [
            record(3, use("p", "Bash", command="execute_probe")),
            record(4, result("p", "probe completed")),
        ],
    )
    doc = document(engine.store.locate("a.jsonl", 1))
    path = engine.store.path
    engine.store.close()
    server = build_mcp(path)

    async def run():
        submitted = await server.call_tool("submit", {"document": json.dumps(doc)})
        summary = json.loads(submitted[0].text)
        query = summary["evidence_review"]["post_write_returns"][0][
            "pool_returns_query"
        ]
        assert query["kind"] == "pool" and query["view"] == "returns"
        found = await server.call_tool(
            "investigate", {"requests": [{**query, "terms": ["probe completed"]}]}
        )
        assert "probe completed" in found[0].text and "ERROR" not in found[0].text

    asyncio.run(run())
