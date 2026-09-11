"""Mechanical review supplies facts/hints without rewriting model claims."""

import asyncio
import json

import pytest

from migloop.inquiry.engine import Engine
from migloop.inquiry.interfaces import build_mcp
from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, ts, use


def report_for(engine):
    ref = engine.store.locate("b.jsonl", 1)
    return {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "since": ts(3), "at": ts(9)},
        "findings": [
            {
                "id": "B",
                "title": "later replacement",
                "reason": "actor a changed this",
                "changes": [ref],
                "nodes": [
                    {
                        "id": "wrong_actor",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(9),
                        "role": "repaired",
                        "reason": "model claim",
                        "evidence": [ref],
                    }
                ],
            }
        ],
    }


def test_review_catches_foreign_native_actor_and_prior_literal_delta(tmp_path):
    line = "Telemetry.recordProblem('details')"
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "first",
                    "Edit",
                    file_path="A.ets",
                    old_string="oldMarker()",
                    new_string=line,
                ),
            ),
            record(2, result("first")),
        ],
        [
            record(
                4,
                use(
                    "last",
                    "Edit",
                    file_path="A.ets",
                    old_string=line,
                    new_string="Platform.reportProblem('details')",
                ),
            ),
            record(5, result("last")),
        ],
    )
    doc = report_for(engine)
    graph = check(engine, json.dumps(doc))
    review = graph["evidence_review"]
    assert review["actor_notes"][0]["node"] == "B:wrong_actor"
    assert review["actor_notes"][0]["actual_actors"] == ["b"]
    hint = review["literal_predecessors"][0]
    assert hint["earlier_actor"] == "a" and hint["current_actor"] == "b"
    assert hint["fragments"] == [line] and hint["not_author_proof"]
    assert len(graph["edges"]) == 1  # review does not manufacture a causal edge
    assert graph["document"] == doc and graph["semantic_verified"] is False
    engine.store.close()


def test_failed_prior_write_is_not_promoted_by_literal_review(tmp_path):
    line = "Telemetry.recordProblem('details')"
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "first",
                    "Edit",
                    file_path="A.ets",
                    old_string="oldMarker()",
                    new_string=line,
                ),
            ),
            record(2, result("first", error=True)),
        ],
        [
            record(
                4,
                use(
                    "last",
                    "Edit",
                    file_path="A.ets",
                    old_string=line,
                    new_string="replacement()",
                ),
            ),
            record(5, result("last")),
        ],
    )
    assert (
        check(engine, json.dumps(report_for(engine)))["evidence_review"][
            "literal_predecessors"
        ]
        == []
    )
    engine.store.close()


def test_review_timeline_uses_evidence_time_not_node_cutoff(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, {"type": "text", "text": "earlier observation A.ets"}),
            record(5, {"type": "text", "text": "later observation A.ets"}),
        ],
    )
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(9)},
        "findings": [
            {
                "id": "A",
                "title": "ordering",
                "reason": "not checked by prose parsing",
                "nodes": [
                    {
                        "id": "late",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(9),
                        "role": "context",
                        "reason": "later",
                        "evidence": [engine.store.locate("a.jsonl", 2)],
                    },
                    {
                        "id": "early",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(9),
                        "role": "context",
                        "reason": "earlier",
                        "evidence": [engine.store.locate("a.jsonl", 1)],
                    },
                ],
            }
        ],
    }
    times = check(engine, json.dumps(doc))["evidence_review"]["timeline"]
    assert [n["node"] for n in times] == ["A:early", "A:late"]
    assert times[0]["first"].startswith("2026-01-01T00:00:01")
    assert times[0]["cutoff"] == ts(9)
    engine.store.close()


@pytest.mark.parametrize(
    "earlier", ["snapshot", "future_return", "ambiguous", "already_cited"]
)
def test_review_does_not_certify_snapshots_concurrency_or_repeated_introductions(
    tmp_path, earlier
):
    line = "Telemetry.recordProblem('details')"
    operation = use(
        "first", "Edit", file_path="A.ets", old_string="old()", new_string=line
    )
    if earlier == "snapshot":
        operation = use("first", "Write", file_path="A.ets", content=line)
    rows = [
        record(1, operation),
        record(6 if earlier == "future_return" else 2, result("first")),
    ]
    if earlier == "ambiguous":
        rows.extend(
            [
                record(
                    2,
                    use(
                        "again",
                        "Edit",
                        file_path="A.ets",
                        old_string="other()",
                        new_string=line,
                    ),
                ),
                record(3, result("again")),
            ]
        )
    engine = build(
        tmp_path,
        rows,
        [
            record(
                4,
                use(
                    "last",
                    "Edit",
                    file_path="A.ets",
                    old_string=line,
                    new_string="replacement()",
                ),
            ),
            record(5, result("last")),
        ],
    )
    doc = report_for(engine)
    if earlier == "already_cited":
        doc["findings"][0]["reason"] += " seen " + engine.store.handle(
            "e", {"ref": engine.store.locate("a.jsonl", 1)}
        )
    assert (
        check(engine, json.dumps(doc))["evidence_review"]["literal_predecessors"] == []
    )
    engine.store.close()


def test_review_is_owned_by_investigator_and_original_stays_immutable(tmp_path):
    engine = build(
        tmp_path,
        [record(1, {"type": "text", "text": "A.ets earlier input"})],
        [record(4, {"type": "text", "text": "A.ets later input"})],
    )
    source = json.dumps(report_for(engine))
    saved = check(engine, source, save=True)
    own = Engine(engine.store, origin="mcp", session=engine.session)
    query = {"op": "review", "report_id": saved["report_id"]}
    result = own.query(query)
    assert result["kind"] == "evidence_review" and result["total"]
    assert "timeline" in own.investigate([query])
    assert len(own.trace(engine.session)) == 1  # only the actual explicit review query
    foreign = Engine(engine.store, origin="mcp", session="other")
    with pytest.raises(ValueError, match="different investigator"):
        foreign.query(query)
    assert (
        engine.store.rows("SELECT request FROM runs WHERE id=?", (saved["report_id"],))[
            0
        ]["request"]
        == source
    )
    engine.store.close()


def test_changed_prior_receipt_cannot_be_used_for_predecessor_hint(tmp_path):
    line = "Telemetry.recordProblem('details')"
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "first",
                    "Edit",
                    file_path="A.ets",
                    old_string="old()",
                    new_string=line,
                ),
            ),
            record(2, result("first")),
        ],
        [
            record(
                4,
                use(
                    "last",
                    "Edit",
                    file_path="A.ets",
                    old_string=line,
                    new_string="replacement()",
                ),
            ),
            record(5, result("last")),
        ],
    )
    path = tmp_path / "a.jsonl"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"ok"', '"NO"'), encoding="utf-8"
    )
    review = check(engine, json.dumps(report_for(engine)))["evidence_review"]
    assert review["limitations"] and not review["literal_predecessors"]
    engine.store.close()


def test_mcp_submit_exposes_real_review_query_without_synthesizing_trace(tmp_path):
    engine = build(
        tmp_path,
        [record(1, {"type": "text", "text": "A.ets"})],
        [record(4, {"type": "text", "text": "A.ets"})],
    )
    doc = json.dumps(report_for(engine))
    server = build_mcp(engine.store.path)

    async def run():
        blocks = await server.call_tool("submit", {"document": doc})
        summary = json.loads(blocks[0].text)
        assert summary["evidence_review"]["counts"]["timeline"] == 1
        assert engine.trace() == []
        result = await server.call_tool(
            "investigate", {"requests": [summary["review_query"]]}
        )
        assert "timeline" in result[0].text
        assert len(engine.trace()) == 1

    asyncio.run(run())
    engine.store.close()
