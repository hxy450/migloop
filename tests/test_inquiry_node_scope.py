"""Report scope handles retain the same interval as investigation views."""

import json

from migloop.inquiry.report import check
from migloop.inquiry.store import timestamp
from tests.test_inquiry_core import build, record, result, ts, use


def scoped_report(engine, evidence, *, edges=None):
    nodes = []
    for kind, key in (("agent", "a"), ("file", "/proj/A.ets")):
        scope = engine.query({"op": kind, "key": key, "since": ts(5), "at": ts(10)})[
            "scope_id"
        ]
        nodes.append(
            {
                "id": kind,
                "scope": scope,
                "role": "context",
                "reason": "bounded claim",
                "evidence": evidence,
            }
        )
    finding = {
        "id": "A",
        "title": "bounded evidence",
        "reason": "not a state assertion",
        "nodes": nodes,
    }
    if edges is not None:
        finding["edges"] = edges
    return {
        "schema": "inquiry/1",
        "target": {"file": "/proj/A.ets", "at": ts(10)},
        "findings": [finding],
    }


def test_node_cannot_silently_discard_scope_lower_bound(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="early")),
            record(2, result("w")),
            record(7, {"type": "text", "text": "later activity"}),
        ],
    )
    early = engine.store.locate("a.jsonl", 2)
    graph = check(engine, json.dumps(scoped_report(engine, [early])))
    assert graph["mechanical_status"] == "needs_revision"
    claims = [n for n in graph["nodes"] if not n["generated_context"]]
    assert all(timestamp(n["since"]) == timestamp(ts(5)) for n in claims)
    assert all(not n["valid_refs"] for n in claims)
    assert not next(n for n in claims if n["kind"] == "file")["exists"]
    # The early operation may be shown on neutral earlier endpoints, never on
    # the later model scopes. The submitted document is not rewritten.
    assert all(e["from"] != "A:agent" and e["to"] != "A:file" for e in graph["edges"])
    assert graph["document"] == scoped_report(engine, [early])
    engine.store.close()


def test_explicit_edge_must_fall_within_both_endpoint_intervals(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="early")),
            record(2, result("w")),
            record(7, {"type": "text", "text": "later mention /proj/A.ets"}),
        ],
    )
    request, response, late = [engine.store.locate("a.jsonl", n) for n in (1, 2, 3)]
    graph = check(
        engine,
        json.dumps(
            scoped_report(
                engine,
                [late],
                edges=[
                    {
                        "from": "agent",
                        "to": "file",
                        "relation": "write",
                        "claim": "old operation misbound to later window",
                        "evidence": [request, response],
                    }
                ],
            )
        ),
    )
    assert graph["edges"] == [] and len(graph["unverified_edges"]) == 1
    engine.store.close()


def test_operation_returning_inside_window_keeps_earlier_request_as_edge_evidence(
    tmp_path,
):
    engine = build(
        tmp_path,
        [
            record(4, use("r", "Read", file_path="/proj/A.ets")),
            record(6, result("r", "observed contents")),
        ],
    )
    request, response = [engine.store.locate("a.jsonl", n) for n in (1, 2)]
    graph = check(
        engine,
        json.dumps(
            scoped_report(
                engine,
                [response],
                edges=[
                    {
                        "from": "file",
                        "to": "agent",
                        "relation": "read",
                        "claim": "returned during interval",
                        "evidence": [request, response],
                    }
                ],
            )
        ),
    )
    assert len(graph["edges"]) == 1 and graph["unverified_edges"] == []
    assert graph["issues"] == []
    assert engine.store.has_records(
        "file", "/proj/A.ets", timestamp(ts(10)), since=timestamp(ts(5))
    )
    assert not engine.store.has_records(
        "file", "/proj/A.ets", timestamp(ts(10)), since=timestamp(ts(7))
    )
    engine.store.close()


def test_auto_edges_prefer_the_node_that_cites_that_operation(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("r", "Read", file_path="/proj/spec.md")),
            record(2, result("r", "input")),
            record(3, use("w", file_path="/proj/A.ets", content="output")),
            record(4, result("w")),
        ],
    )
    read, write = [engine.store.locate("a.jsonl", n) for n in (2, 3)]
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "/proj/A.ets", "at": ts(20)},
        "findings": [
            {
                "id": "A",
                "title": "one actor, two claims",
                "reason": "input and output claims are distinct",
                "changes": [write],
                "nodes": [
                    {
                        "id": "input",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(10),
                        "role": "context",
                        "reason": "read this input",
                        "evidence": [read],
                    },
                    {
                        "id": "output",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(20),
                        "role": "origin",
                        "reason": "wrote this output",
                        "evidence": [write],
                    },
                ],
            }
        ],
    }
    graph = check(engine, json.dumps(doc))
    assert (
        next(e for e in graph["edges"] if e["relation"] == "write")["from"]
        == "A:output"
    )
    assert next(e for e in graph["edges"] if e["relation"] == "read")["to"] == "A:input"
    assert graph["document"] == doc
    engine.store.close()
