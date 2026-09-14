"""Search uses the existing message index, not a second task inference path."""

import pytest

from tests.test_inquiry_core import build, record, result, ts, use
from tests.test_inquiry_inputs import message


@pytest.fixture
def messages(tmp_path):
    reply = record(4, result("scan", "scan /proj/A.ets returned a claim"))
    reply["type"] = "user"
    reply["message"]["role"] = "user"
    undated = {**message(1, "undated A.ets task"), "timestamp": None}
    engine = build(tmp_path, [message(1, "Please diagnose only, do not edit"),
        message(2, "[image cache placeholder]"),
        record(3, use("scan", "Bash", command="scan /proj/A.ets")), reply,
        message(7, "A.ets may now be edited"), undated,
        record(None, result("unpaired", "undated result"))],
        second=[message(2, "A.ets is another actor's task"), message(8, "Later instruction")])
    try:
        yield engine
    finally:
        engine.store.close()


def test_search_agent_messages_matches_direct_agent_view(messages):
    q = {"key": "a", "at": ts(5), "view": "messages", "order": "newest", "limit": 3}
    expected = messages.query({"op": "agent", **q})
    actual = messages.query({"op": "search", "kind": "agent", **q})
    assert actual["scope"] == expected["scope"]
    assert actual["rows"] == expected["rows"]
    assert actual["total"] == expected["total"] == 2
    assert "placeholder" in actual["rows"][0]["excerpt"]
    opened = messages.query({"op": "open", "ref": actual["rows"][1]["cite"], "at": ts(5)})
    assert opened["text"] == "Please diagnose only, do not edit"
    assert not messages.store.rows("SELECT * FROM effects")


def test_messages_search_reuses_time_order_and_pagination(messages):
    q = {"op": "search", "kind": "agent", "key": "a", "view": "messages", "at": ts(5), "limit": 1}
    first = messages.query(q)
    second = messages.query({**q, "offset": first["next"]})
    assert first["next"] == 1 and second["next"] is None
    assert second["rows"][0]["line"] == 1
    window = messages.query({**q, "since": ts(2)})
    assert window["total"] == 1
    # Keywords can exclude a real instruction. An empty match isn't no task.
    narrow = messages.query({**q, "terms": ["A.ets"]})
    assert narrow["total"] == 0


def test_pool_messages_group_and_narrow_are_consistent(messages):
    q = {"op": "search", "kind": "pool", "at": ts(5), "view": "messages", "limit": 100}
    all_rows = messages.query(q)
    assert all_rows["total"] == 3
    groups = messages.query({**q, "group_by": "agent"})
    assert {row["agent"] for row in groups["rows"]} == {"a", "b"}
    assert sum(row["matches"] for row in groups["rows"]) == all_rows["total"]
    for row in groups["rows"]:
        assert messages.query(row["query"])["total"] == row["matches"]


def test_file_message_search_is_only_lexical_not_a_read(messages):
    data = messages.query({"op": "search", "kind": "file", "key": "/proj/A.ets", "at": ts(5), "view": "messages"})
    assert data["total"] == 1 and data["rows"][0]["agent"] == "b"
    assert not messages.store.rows("SELECT * FROM effects")


def test_undated_messages_do_not_count_tool_returns(messages):
    q = {"op": "search", "kind": "agent", "key": "a", "view": "messages", "at": ts(5)}
    data = messages.query(q)
    assert data["undated_records"] == 1
    visible = messages.query({**q, "undated": True})
    assert visible["total"] == 3
    assert sum(row["at"] is None for row in visible["rows"]) == 1


@pytest.mark.parametrize("view", ["messages", "returns", "records"])
@pytest.mark.parametrize("order", [None, "newest", "oldest"])
def test_narrow_navigation_preserves_effective_order_and_first_page(tmp_path, view, order):
    rows = [message(n, "Please edit the page") for n in range(1, 22)]
    rows.append(message(22, "Only diagnose now, do not edit"))
    if view == "returns":
        rows = [record(n, result(str(n), f"returned at {n}")) for n in range(1, 23)]
    engine = build(tmp_path, rows)
    try:
        q = {"op": "search", "kind": "pool", "view": view, "at": ts(30), "limit": 20}
        if order is not None:
            q["order"] = order
        pool = engine.query(q)
        narrow = pool["matching_agents"]["rows"][0]["query"]
        actual = engine.query(narrow)
        assert [r["line"] for r in actual["rows"]] == [r["line"] for r in pool["rows"]]
        assert actual["next"] == pool["next"] == 20
        if view == "messages" and order != "oldest":
            assert actual["rows"][0]["line"] == 22
    finally:
        engine.store.close()
