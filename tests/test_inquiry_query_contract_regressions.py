"""i14 observations: query IDs, list pagination and inline evidence consistency.

Written against the frozen i14 failures before the next candidate is changed.
"""

import asyncio
import json
import re

import pytest

from migloop.inquiry.engine import Engine
from migloop.inquiry.interfaces import build_mcp
from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, ts, use


def document(ref):
    return {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(9)},
        "findings": [
            {
                "id": "A",
                "title": "claim",
                "reason": "a model claim",
                "nodes": [
                    {
                        "id": "f",
                        "kind": "file",
                        "key": "A.ets",
                        "at": ts(9),
                        "role": "context",
                        "reason": "original model reason",
                        "evidence": [ref],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def engine(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="literal source")),
            record(2, result("w")),
        ],
    )
    yield engine
    engine.store.close()


def test_review_lists_use_the_same_record_pagination(engine):
    doc = document(engine.store.locate("a.jsonl", 1))
    doc["findings"][0]["nodes"].append(
        {
            **doc["findings"][0]["nodes"][0],
            "id": "second",
            "evidence": [engine.store.locate("a.jsonl", 2)],
        }
    )
    saved = check(engine, json.dumps(doc), save=True)
    q = {"op": "review", "report_id": saved["report_id"], "offset": 0, "limit": 1}
    full = engine.query({"op": "review", "report_id": saved["report_id"]})
    first = engine.query(q)
    assert (
        first["total"] == len(full["rows"])
        and len(first["rows"]) == 1
        and first["next"] == 1
    )
    rows = first["rows"]
    while first["next"] is not None:
        first = engine.query({**q, "offset": first["next"]})
        rows.extend(first["rows"])
    assert rows == full["rows"]


def test_parameter_error_names_the_actual_contract(engine):
    with pytest.raises(ValueError, match="report_id"):
        engine.query({"op": "review", "key": "not-a-report"})


def test_query_result_used_as_source_gets_exact_owned_hint_not_rewrite(engine):
    actual = engine.store.locate("a.jsonl", 1)
    frame = engine.investigate([{"op": "open", "ref": actual, "at": ts(9)}])
    query_id = re.search(r"RESULT (\w+)", frame)[1]
    bad = "e-" + query_id
    doc = document(bad)
    graph = check(engine, json.dumps(doc))
    issue = next(i for i in graph["issues"] if i.get("ref") == bad)
    hint = issue["resolution_hint"]
    assert hint["kind"] == "query_result_used_as_source"
    assert hint["source_cite"] == engine.store.handle("e", {"ref": actual})
    assert hint["source"] == "a.jsonl" and hint["line"] == 1
    assert graph["document"] == doc and not graph["nodes"][0]["valid_refs"]
    assert (
        graph["edges"] == []
    )  # diagnostic must not silently add the corrected evidence


@pytest.mark.parametrize("reason", ["other_session", "aggregate", "changed_source"])
def test_query_reference_hint_does_not_guess_or_cross_investigators(
    engine, tmp_path, reason
):
    producer = (
        Engine(engine.store, session="foreign") if reason == "other_session" else engine
    )
    q = (
        {"op": "file", "key": "A.ets", "at": ts(9)}
        if reason == "aggregate"
        else {"op": "open", "ref": engine.store.locate("a.jsonl", 1), "at": ts(9)}
    )
    frame = producer.investigate([q])
    bad = "e-" + re.search(r"RESULT (\w+)", frame)[1]
    if reason == "changed_source":
        path = tmp_path / "a.jsonl"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "literal source", "changed source"
            ),
            encoding="utf-8",
        )
    graph = check(engine, json.dumps(document(bad)))
    issue = next(i for i in graph["issues"] if i.get("ref") == bad)
    assert not issue.get("resolution_hint")
    assert graph["edges"] == []


def test_inline_reason_citation_and_edge_reconciliation_share_sources(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("r", "Read", file_path="A.ets")),
            record(2, result("r", "actual earlier contents")),
        ],
    )
    ref = engine.store.handle("e", {"ref": engine.store.locate("a.jsonl", 2)})
    doc = document(ref)
    doc["findings"][0]["nodes"][0]["evidence"] = []
    doc["findings"][0]["reason"] = "Observed in " + ref
    graph = check(engine, json.dumps(doc))
    assert graph["document"] == doc and graph["semantic_verified"] is False
    assert len(graph["edges"]) == 1 and graph["edges"][0]["relation"] == "read"
    assert graph["edges"][0]["source"] == "native_evidence"
    assert graph["missing_evidence_links"] == []
    engine.store.close()


def test_inline_unknown_script_still_cannot_manufacture_a_write(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("shell", "Bash", command="python modify.py A.ets")),
            record(2, result("shell", "possibly changed")),
        ],
    )
    ref = engine.store.handle("e", {"ref": engine.store.locate("a.jsonl", 2)})
    doc = document(ref)
    doc["findings"][0]["reason"] = "Claimed change " + ref
    graph = check(engine, json.dumps(doc))
    assert graph["edges"] == [] and not graph["semantic_verified"]
    engine.store.close()


def test_mcp_deduplicates_hints_but_preserves_all_issue_locations(engine):
    server = build_mcp(engine.store.path)

    async def run():
        frame = await server.call_tool(
            "investigate",
            {"requests": [{"op": "open", "source": "a.jsonl", "line": 1, "at": ts(9)}]},
        )
        bad = "e-" + re.search(r"RESULT (\w+)", frame[0].text)[1]
        doc = document(bad)
        doc["findings"][0]["reason"] = "Also cited here " + bad
        response = await server.call_tool("submit", {"document": json.dumps(doc)})
        data = json.loads(response[0].text)
        assert len(data["issues"]) == 2 and len(data["resolution_hints"]) == 1
        assert data["resolution_hints"][bad]["source_cite"].startswith("e-")
        assert all("resolution_hint" not in i for i in data["issues"])
        assert data["mechanical_status"] == "needs_revision"

    asyncio.run(run())
