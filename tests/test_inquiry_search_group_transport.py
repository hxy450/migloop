"""Native text must expose real navigation, never an unknown-owner fake query."""

import asyncio

from migloop.inquiry.engine import Engine
from migloop.inquiry.interfaces import build_mcp
from migloop.inquiry.store import Source, Store
from tests.test_inquiry_core import build, record, result, ts


def test_unknown_actor_group_has_no_narrow_query_and_keeps_undated_sample(tmp_path):
    seed = build(tmp_path, [record(None, result("unknown", "needle"))])
    row = seed.store.rows("SELECT * FROM sources")[0]
    seed.store.close()
    store = Store.build(tmp_path / "unknown.sqlite", [Source(row["path"], row["name"])])
    engine = Engine(store)
    q = {
        "op": "search",
        "kind": "pool",
        "at": ts(4),
        "view": "returns",
        "terms": ["needle"],
        "undated": True,
    }
    data = engine.query(q)
    actor = data["matching_agents"]["rows"][0]
    assert actor["agent"] is None and actor["query"] is None and actor["undated"] == 1
    assert actor["first_at"] is None and actor["last_at"] is None
    for request in (q, data["matching_agents"]["query"]):
        text = engine.investigate([request])
        assert "NARROW SAME QUERY null" not in text
        assert actor["latest_match"] in text and "ERROR" not in text
    store.close()


def test_mcp_group_navigation_is_in_emitted_text_and_executes(tmp_path):
    engine = build(
        tmp_path,
        [record(1, result("old", "needle old"))],
        [record(3, result("late", "needle observed"))],
    )
    path = engine.store.path
    engine.store.close()
    server = build_mcp(path)
    q = {
        "op": "search",
        "kind": "pool",
        "at": ts(4),
        "view": "returns",
        "terms": ["needle"],
        "group_by": "agent",
    }

    async def run():
        reply = await server.call_tool("investigate", {"requests": [q]})
        assert (
            "MATCHING" in reply[0].text.upper() and "NARROW SAME QUERY" in reply[0].text
        )
        assert "ERROR" not in reply[0].text

    asyncio.run(run())
