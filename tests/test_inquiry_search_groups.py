"""Pool navigation exposes other matching actors, not inferred provenance."""

import pytest

from tests.test_inquiry_core import build, record, result, ts, use


def test_actor_groups_cover_whole_match_set_and_narrow_same_time_terms(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="x")),
            record(2, result("w", "needle old A.ets")),
            record(3, result("unpaired", "needle docs A.ets")),
        ],
        [
            record(4, result("probe", "needle observed A.ets", error=True)),
            record(5, result("probe2", "needle later A.ets")),
            record(8, result("future", "needle future A.ets")),
            record(None, result("unknown", "needle undated A.ets")),
        ],
    )
    before = engine.store.rows("SELECT * FROM effects ORDER BY id")
    q = {
        "op": "search",
        "kind": "pool",
        "view": "returns",
        "since": ts(2),
        "at": ts(6),
        "terms": ["needle"],
        "limit": 1,
    }
    data = engine.query(q)
    nav = data["matching_agents"]
    assert nav["total"] == 2 and nav["matched_records"] == 4
    assert sum(r["matches"] for r in nav["rows"]) == 4
    assert data["total"] == 4 and len(data["rows"]) == 1
    actor = next(r for r in nav["rows"] if r["agent"] == "b")
    narrowed = engine.query(actor["query"])
    assert narrowed["scope"]["at"] == data["scope"]["at"]
    assert narrowed["scope"]["since"] == data["scope"]["since"]
    assert narrowed["scope"]["key"] == "b" and narrowed["total"] == 2
    assert actor["query"]["terms"] == ["needle"] and actor["query"]["view"] == "returns"
    # Narrowing changes the actor, not the query's default chronological order.
    assert [r["line"] for r in narrowed["rows"]] == [1, 2]
    assert narrowed["rows"][0]["return_blocks"][0]["success"] == 0
    grouped = engine.query({**nav["query"], "limit": 1})
    assert grouped["kind"] == "matching_agents" and grouped["next"] == 1
    second = engine.query({**nav["query"], "limit": 1, "offset": 1})
    assert second["rows"][0]["agent"] != grouped["rows"][0]["agent"]
    assert second["next"] is None
    assert engine.store.rows("SELECT * FROM effects ORDER BY id") == before
    assert engine.trace() == []
    engine.store.close()


@pytest.mark.parametrize("kind", ["pool", "agent", "file"])
def test_record_order_changes_only_pagination_not_scope_or_matching_set(tmp_path, kind):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="needle")),
            record(2, result("w", "needle A.ets")),
            record(3, result("u", "needle A.ets")),
            record(3, result("u2", "needle A.ets")),
            record(None, result("u3", "needle A.ets")),
        ],
    )
    q = {
        "op": "search",
        "kind": kind,
        "at": ts(5),
        "since": ts(2),
        "view": "returns",
        "terms": ["needle"],
        "undated": True,
    }
    if kind != "pool":
        q["key"] = "a" if kind == "agent" else "A.ets"
    old = engine.query({**q, "order": "oldest"})
    new = engine.query({**q, "order": "newest"})
    assert old["scope_id"] == new["scope_id"]
    assert [r["line"] for r in old["rows"]] == [2, 3, 4, 5]
    assert [r["line"] for r in new["rows"]] == [4, 3, 2, 5]
    assert new["order"] == "newest first"
    assert [
        r["ref"]
        for offset in range(4)
        for r in engine.query({**q, "order": "newest", "offset": offset, "limit": 1})[
            "rows"
        ]
    ] == [r["ref"] for r in new["rows"]]
    for value in [None, 1, [], "DESC; DROP TABLE records"]:
        with pytest.raises(ValueError, match="order"):
            engine.query({**q, "order": value})
    with pytest.raises(ValueError, match="group_by"):
        engine.query({**q, "group_by": "file"})
    engine.store.close()
