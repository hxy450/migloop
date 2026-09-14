"""Time-tree paths are projections of the same events as manual neighborhoods."""

import json

import pytest

from migloop.inquiry import report
from tests.test_inquiry_core import build, record, result, ts, use


@pytest.fixture
def chain(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="bad")),
            record(2, result("w")),
            record(
                12,
                use(
                    "fix",
                    "Edit",
                    file_path="/proj/B.ets",
                    old_string="bad",
                    new_string="good",
                ),
            ),
            record(13, result("fix")),
        ],
        second=[
            record(4, use("r", "Read", file_path="/proj/A.ets")),
            record(5, result("r", "bad")),
            record(7, use("w2", file_path="/proj/B.ets", content="bad")),
            record(8, result("w2")),
        ],
    )
    yield engine
    engine.store.close()


def document(engine):
    ref = engine.store.locate
    return {
        "schema": "inquiry/1",
        "target": {"file": "B.ets", "since": ts(10), "at": ts(15)},
        "findings": [
            {
                "id": "A",
                "title": "wrong value",
                "reason": "model reason",
                "changes": [ref("a.jsonl", 3), ref("a.jsonl", 4)],
                "nodes": [
                    {
                        "id": "origin",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(2),
                        "role": "origin",
                        "reason": "wrote bad value",
                        "evidence": [ref("a.jsonl", 1)],
                    },
                    {
                        "id": "consumer",
                        "kind": "agent",
                        "key": "b",
                        "at": ts(8),
                        "role": "propagated",
                        "reason": "read and retained bad value",
                        "evidence": [ref("b.jsonl", i) for i in (1, 2, 3, 4)],
                    },
                ],
            }
        ],
    }


def test_paths_replay_the_exact_manual_neighbors_without_version_edges(chain):
    doc = document(chain)
    graph = report.check(chain, json.dumps(doc), save=True)
    assert graph["document"] == doc and graph["tree"]["complete"]
    root = graph["tree"]["root"]
    assert root["since"] is None and graph["target"]["since"] == ts(10)
    origin = next(p for p in graph["tree"]["paths"] if p["node"] == "A:origin")
    assert [r["relation"] for r in origin["steps"]] == ["write", "read", "write"]
    assert [r["node"]["kind"] for r in origin["steps"]] == ["agent", "file", "agent"]
    scope = root
    for step in origin["steps"]:
        data = chain.query(
            {
                "op": scope["kind"],
                **{k: scope[k] for k in ("key", "at", "since")},
                "view": "neighbors",
                "report_id": graph["report_id"],
            }
        )
        assert step == next(row for row in data["rows"] if row["id"] == step["id"])
        scope = step["node"]
    assert chain.trace() == []


def test_late_read_and_same_timestamp_identity_keep_their_boundaries(chain):
    before = chain.query({"op": "agent", "key": "b", "at": ts(4), "view": "neighbors"})
    assert before["rows"][0]["strength"] == "candidate"
    assert len(before["rows"][0]["evidence"]) == 1
    after = chain.query(
        {"op": "agent", "key": "b", "at": ts(8), "since": ts(5), "view": "neighbors"}
    )
    assert after["rows"][0]["strength"] == "confirmed"
    assert after["rows"][0]["node"]["at"].startswith("2026-01-01T00:00:05")
    assert before["rows"][0]["id"] == after["rows"][0]["id"]


def test_searching_good_spec_does_not_make_it_an_input(chain):
    doc = document(chain)
    doc["findings"][0]["nodes"][0]["key"] = "b"
    doc["findings"][0]["nodes"][0]["at"] = ts(8)
    # A different actor's write may be relevant, but cannot support this actor's path.
    graph = report.check(chain, json.dumps(doc))
    origin = next(p for p in graph["tree"]["paths"] if p["node"] == "A:origin")
    assert origin["status"] == "unclosed" and not origin["steps"]


def test_normal_input_paths_are_displayed_without_changing_problem_closure(chain):
    doc = document(chain)
    doc["findings"][0]["nodes"].append(
        {
            "id": "input",
            "kind": "file",
            "key": "A.ets",
            "at": ts(5),
            "role": "context",
            "reason": "The inspected input, not a claim of fault",
            "evidence": [chain.store.locate("b.jsonl", 2)],
        }
    )
    graph = report.check(chain, json.dumps(doc))
    assert graph["document"] == doc
    assert graph["tree"]["complete"] and graph["tree"]["problem_nodes"] == 2
    path, = graph["tree"]["context_paths"]
    assert path["node"] == "A:input" and path["purpose"] == "context"
    assert path["status"] == "native"
    assert [r["relation"] for r in path["steps"]] == ["write", "read"]
    scope = graph["tree"]["root"]
    for step in path["steps"]:
        result = chain.query({"op": scope["kind"], **{k: scope[k] for k in ("key", "at", "since")}, "view": "neighbors"})
        assert step in result["rows"]
        scope = step["node"]


def test_repair_without_generation_fault_still_has_a_display_path(chain):
    doc = document(chain)
    doc["findings"][0]["nodes"] = [{
        "id": "fixer", "kind": "agent", "key": "a", "at": ts(13),
        "role": "repaired", "reason": "later requirement, not a generation fault",
        "evidence": [chain.store.locate("a.jsonl", 3)],
    }]
    graph = report.check(chain, json.dumps(doc))
    assert graph["tree"]["problem_nodes"] == 0 and graph["tree"]["paths"] == []
    path, = graph["tree"]["context_paths"]
    assert path["node"] == "A:fixer" and path["status"] == "native"
    assert len(path["steps"]) == 1 and path["steps"][0]["relation"] == "write"


def test_cached_supplement_cannot_reintroduce_a_contradictory_author(chain, monkeypatch):
    graph = report.check(chain, json.dumps(document(chain)), save=True)
    # Simulate a cache produced by the earlier quote-only validator. All refs
    # remain real; the allegation incorrectly assigns b's B write to a.
    target = next(n for n in graph["nodes"] if n["kind"] == "file" and n["key"] == "/proj/B.ets")
    author = next(n for n in graph["nodes"] if n["id"] == "A:origin")
    author["at"] = ts(15)
    ref = chain.store.locate("b.jsonl", 3)
    graph["edges"].append({"from": author["id"], "to": target["id"], "finding": "A",
        "relation": "write", "source": "model_review", "strength": "candidate", "operation": "old-overlay",
        "at": ts(7), "evidence": [ref], "claim": "a wrote B", "review": {
            "at": ts(7), "quotes": [{"ref": ref, "text": "bad"}]}})
    monkeypatch.setattr(report, "load_report", lambda *_a, **_k: graph)
    result = chain.query({"op": "file", "key": "B.ets", "at": ts(15), "view": "neighbors", "report_id": graph["report_id"]})
    assert not any(r["source"] == "model_review" for r in result["rows"])
    assert result["rejected_reviews"]


def test_cited_input_endpoint_is_visible_but_not_a_new_model_judgment(chain):
    graph = report.check(chain, json.dumps(document(chain)))
    path, = graph["tree"]["context_paths"]
    assert path["status"] == "native"
    assert [r["relation"] for r in path["steps"]] == ["write", "read"]
    node = next(n for n in graph["nodes"] if n["id"] == path["node"])
    assert node["generated_context"] and node["role"] == "context"
    assert node["key"] == "/proj/A.ets"
    assert graph["tree"]["problem_nodes"] == 2


def test_agent_input_judgment_cites_read_not_output_write(chain):
    doc = document(chain)
    doc["findings"][0]["nodes"].append({
        "id": "received", "kind": "agent", "key": "b", "at": ts(8),
        "role": "context", "reason": "received this input", "evidence": [chain.store.locate("b.jsonl", 2)],
    })
    graph = report.check(chain, json.dumps(doc))
    path = next(p for p in graph["tree"]["context_paths"] if p["node"] == "A:received")
    assert path["status"] == "native" and len(path["steps"]) == 1
    assert path["steps"][0]["relation"] == "write"
    assert graph["tree"]["complete"] and graph["tree"]["problem_nodes"] == 2


@pytest.mark.parametrize("cutoff", [ts(4), ts(15)])
def test_unrelated_or_not_yet_read_context_is_not_connected(chain, cutoff):
    doc = document(chain)
    # The source ref is real, but it is either before this input was returned
    # or describes B rather than a relationship involving the claimed A input.
    doc["findings"][0]["nodes"].append(
        {
            "id": "independent",
            "kind": "file",
            "key": "A.ets",
            "at": cutoff,
            "role": "context",
            "reason": "Independent lookup, not a proved delivered input",
            "evidence": [chain.store.locate("b.jsonl", 2 if cutoff == ts(4) else 3)],
        }
    )
    graph = report.check(chain, json.dumps(doc))
    assert graph["tree"]["complete"] and graph["tree"]["problem_nodes"] == 2
    path = next(p for p in graph["tree"]["context_paths"] if p["node"] == "A:independent")
    assert path["status"] == "unclosed" and not path["steps"]


def test_inverted_temporal_path_is_not_completed(tmp_path):
    engine = build(
        tmp_path,
        [
            record(6, use("w", file_path="/proj/A.ets", content="bad")),
            record(7, result("w")),
            record(
                12,
                use(
                    "fix",
                    "Edit",
                    file_path="/proj/B.ets",
                    old_string="bad",
                    new_string="good",
                ),
            ),
            record(13, result("fix")),
        ],
        second=[
            record(4, use("r", "Read", file_path="/proj/A.ets")),
            record(5, result("r", "bad")),
            record(8, use("out", file_path="/proj/B.ets", content="bad")),
            record(9, result("out")),
        ],
    )
    doc = document(engine)
    doc["findings"][0]["nodes"][0]["at"] = ts(7)
    doc["findings"][0]["nodes"][1]["at"] = ts(9)
    graph = report.check(engine, json.dumps(doc))
    origin = next(p for p in graph["tree"]["paths"] if p["node"] == "A:origin")
    # B's read predates A's alleged causal write. A's later repair of B also
    # cannot stand in for the different write cited in the origin claim.
    assert origin["status"] == "unclosed" and not origin["steps"]
    engine.store.close()


def opaque_document(engine):
    ref = engine.store.locate("a.jsonl", 1)
    return {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(5)},
        "findings": [
            {
                "id": "A",
                "title": "script write",
                "reason": "model reviewed script",
                "changes": [ref],
                "nodes": [
                    {
                        "id": "agent",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(3),
                        "role": "origin",
                        "reason": "script wrote file",
                        "evidence": [ref],
                    },
                    {
                        "id": "file",
                        "kind": "file",
                        "key": "A.ets",
                        "at": ts(3),
                        "role": "propagated",
                        "reason": "bad script output",
                        "evidence": [ref],
                    },
                ],
                "reviewed_edges": [
                    {
                        "from": "agent",
                        "to": "file",
                        "relation": "write",
                        "evidence": [ref],
                        "claim": "script literal writes A.ets",
                        "review": {
                            "at": ts(1),
                            "quotes": [
                                {
                                    "ref": ref,
                                    "text": "Path('/proj/A.ets').write_text('bad')",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_reviewed_script_edge_is_report_local_and_automatically_expandable(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "s",
                    "Bash",
                    command="python -c \"Path('/proj/A.ets').write_text('bad')\"",
                ),
            ),
            record(2, result("s", "done")),
        ],
    )
    before = engine.store.rows("SELECT * FROM effects")
    doc = opaque_document(engine)
    first_doc = json.loads(json.dumps(doc))
    first_doc["findings"][0].pop("reviewed_edges")
    first_doc["findings"][0]["edges"] = [{"from": "agent", "to": "file"}]
    first = report.check(engine, json.dumps(first_doc), save=True)
    doc["revision_of"] = first["report_id"]
    graph = report.check(engine, json.dumps(doc), save=True)
    assert graph["tree"]["complete"] and len(graph["edges"]) == 1
    assert (
        graph["edges"][0]["source"] == "model_review"
        and graph["edges"][0]["strength"] == "candidate"
    )
    assert all(p["status"] == "model_review" for p in graph["tree"]["paths"])
    q = {"op": "file", "key": "A.ets", "at": ts(5), "view": "neighbors"}
    assert engine.query(q)["total"] == 0
    assert engine.query({**q, "report_id": graph["report_id"]})["total"] == 1
    assert engine.store.rows("SELECT * FROM effects") == before and engine.trace() == []
    engine.store.close()


@pytest.mark.parametrize("failure", ["quote", "time", "direction", "no_review"])
def test_bad_review_cannot_create_a_dashed_edge(tmp_path, failure):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "s",
                    "Bash",
                    command="python -c \"Path('/proj/A.ets').write_text('bad')\"",
                ),
            ),
            record(2, result("s", "done")),
        ],
    )
    doc = opaque_document(engine)
    edge = doc["findings"][0]["reviewed_edges"][0]
    if failure == "quote":
        edge["review"]["quotes"][0]["text"] = "fabricated evidence"
    if failure == "time":
        edge["review"]["at"] = ts(0)
    if failure == "direction":
        edge["relation"] = "read"
    if failure == "no_review":
        del edge["review"]
    if failure == "no_review":
        with pytest.raises(ValueError):
            report.check(engine, json.dumps(doc))
    else:
        graph = report.check(engine, json.dumps(doc))
        assert not graph["edges"] and graph["unverified_edges"]
        assert graph["path_status"] == "needs_path"
    engine.store.close()


def test_neighborhood_rejects_stale_source_bytes(chain):
    from pathlib import Path

    source = Path(
        chain.store.rows("SELECT path FROM sources WHERE name='a.jsonl'")[0]["path"]
    )
    source.write_bytes(source.read_bytes().replace(b'"bad"', b'"BAD"'))
    with pytest.raises(ValueError, match="bytes changed"):
        chain.query({"op": "file", "key": "A.ets", "at": ts(9), "view": "neighbors"})


def test_stale_uncited_repair_receipt_cannot_close_a_history_path(chain):
    from pathlib import Path

    doc = document(chain)
    doc["findings"][0]["changes"] = [chain.store.locate("a.jsonl", 3)]
    source = Path(
        chain.store.rows("SELECT path FROM sources WHERE name='a.jsonl'")[0]["path"]
    )
    lines = source.read_bytes().splitlines(keepends=True)
    lines[3] = lines[3].replace(b'"ok"', b'"NO"')
    source.write_bytes(b"".join(lines))
    checked = report.check(chain, json.dumps(doc))
    assert checked["path_status"] == "needs_path"
    assert all(path["repair_anchor"] is None for path in checked["tree"]["paths"])
