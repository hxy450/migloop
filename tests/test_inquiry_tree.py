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
