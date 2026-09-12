"""Dispatch occurrence, later identity evidence, and repair anchors stay distinct."""

import json

import pytest

from migloop.inquiry import report
from tests.test_inquiry_core import build, record, result, ts, use


def dispatched(tmp_path, returned=10, native=True):
    metadata = {"toolUseResult": {"agentId": "b"}} if native else {}
    return build(
        tmp_path,
        [
            record(1, use("task", "Task", prompt="generate B.ets")),
            record(returned, result("task", "LATER_CHILD_IDENTITY"), **metadata),
            record(
                12,
                use(
                    "repair",
                    "Edit",
                    file_path="/proj/B.ets",
                    old_string="bad",
                    new_string="good",
                ),
            ),
            record(13, result("repair")),
        ],
        second=[
            record(4, use("write", file_path="/proj/B.ets", content="bad")),
            record(5, result("write")),
        ],
    )


def dispatch_document(engine):
    ref = engine.store.locate
    return {
        "schema": "inquiry/1",
        "target": {"file": "B.ets", "since": ts(11), "at": ts(15)},
        "findings": [
            {
                "id": "A",
                "title": "original issue",
                "reason": "model's cause",
                "changes": [ref("a.jsonl", 3), ref("a.jsonl", 4)],
                "nodes": [
                    {
                        "id": "parent",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(1),
                        "role": "origin",
                        "reason": "task constraint",
                        "evidence": [ref("a.jsonl", 1)],
                    },
                    {
                        "id": "child",
                        "kind": "agent",
                        "key": "b",
                        "at": ts(5),
                        "role": "propagated",
                        "reason": "generated bad output",
                        "evidence": [ref("b.jsonl", 1), ref("b.jsonl", 2)],
                    },
                ],
            }
        ],
    }


def test_early_candidate_rejects_changed_later_identity_mapping(tmp_path):
    engine = dispatched(tmp_path)
    try:
        query = {"op": "agent", "key": "b", "at": ts(5), "view": "neighbors"}
        candidate = engine.query(query)["rows"][0]
        assert candidate["strength"] == "candidate"
        assert engine.store.locate("a.jsonl", 2) not in candidate["evidence"]
        source = tmp_path / "a.jsonl"
        source.write_bytes(
            source.read_bytes().replace(b'"agentId": "b"', b'"agentId": "c"')
        )
        with pytest.raises(ValueError, match="bytes changed"):
            engine.query(query)
    finally:
        engine.store.close()


@pytest.mark.parametrize("returned,status", [(10, "candidate"), (2, "native")])
def test_sync_task_and_spawn_replay_identical_manual_dispatch_rows(
    tmp_path, returned, status
):
    engine = dispatched(tmp_path, returned)
    try:
        doc = dispatch_document(engine)
        original_dispatches = engine.store.rows("SELECT * FROM dispatches")
        graph = report.check(engine, json.dumps(doc), save=True)
        assert graph["document"] == doc
        parent = next(p for p in graph["tree"]["paths"] if p["node"] == "A:parent")
        assert parent["status"] == status
        assert [s["relation"] for s in parent["steps"]] == ["write", "dispatch"]
        bound = next(e for e in graph["edges"] if e["relation"] == "dispatch")
        assert bound["strength"] == "confirmed"  # observed at report cutoff 15
        assert bound["at"].startswith("2026-01-01T00:00:01")
        scope = graph["tree"]["root"]
        for expected in parent["steps"]:
            actual = engine.query(
                {
                    "op": scope["kind"],
                    **{k: scope[k] for k in ("key", "at", "since")},
                    "view": "neighbors",
                    "report_id": graph["report_id"],
                }
            )
            assert expected == next(
                row for row in actual["rows"] if row["id"] == expected["id"]
            )
            scope = expected["node"]
        step = parent["steps"][-1]
        assert step["node"]["key"] == "a" and step["node"]["at"].startswith(
            "2026-01-01T00:00:01"
        )
        assert step["identity_known_at_cutoff"] is (returned <= 5)
        if returned > 5:
            assert step["evidence"] == [engine.store.locate("a.jsonl", 1)]
            assert step["identity_basis"] == "retrospective_native_mapping"
            assert "LATER_CHILD_IDENTITY" not in json.dumps(step)
        assert engine.store.rows("SELECT * FROM dispatches") == original_dispatches
        assert engine.trace() == []
    finally:
        engine.store.close()


def test_dispatch_queries_separate_occurrence_from_confirmation_and_time_window(
    tmp_path,
):
    engine = dispatched(tmp_path)
    try:

        def query(at, **extra):
            return engine.query(
                {"op": "agent", "key": "b", "at": ts(at), "view": "relations", **extra}
            )["dispatches"]

        assert query(0) == []
        early, late = query(5)[0], query(15)[0]
        assert early["id"] == late["id"] and early["at"] == late["at"]
        assert early["strength"] == "candidate" and early["result"] is None
        assert not early["identity_known_at_cutoff"]
        assert late["strength"] == "confirmed" and late["result"]
        assert late["confirmed_at"].startswith("2026-01-01T00:00:10")
        assert query(15, since=ts(2)) == []  # receipt is in range; occurrence is not
        backwards = engine.query(
            {
                "op": "agent",
                "key": "a",
                "at": ts(5),
                "view": "neighbors",
                "direction": "downstream",
            }
        )
        assert backwards["rows"][0]["node"]["key"] == "b"
        assert backwards["rows"][0]["strength"] == "candidate"
    finally:
        engine.store.close()


def test_late_receipt_cannot_satisfy_an_early_path_claim(tmp_path):
    engine = dispatched(tmp_path)
    try:
        doc = dispatch_document(engine)
        parent = doc["findings"][0]["nodes"][0]
        parent.update(at=ts(10), evidence=[engine.store.locate("a.jsonl", 2)])
        graph = report.check(engine, json.dumps(doc))
        path = next(p for p in graph["tree"]["paths"] if p["node"] == "A:parent")
        assert path["status"] == "unclosed"
    finally:
        engine.store.close()


def test_missing_native_parent_and_uncited_dispatch_never_add_report_edges(tmp_path):
    engine = dispatched(tmp_path, native=False)
    try:
        graph = report.check(engine, json.dumps(dispatch_document(engine)))
        assert not any(e["relation"] == "dispatch" for e in graph["edges"])
        assert (
            next(p for p in graph["tree"]["paths"] if p["node"] == "A:parent")["status"]
            == "unclosed"
        )
    finally:
        engine.store.close()
    other = tmp_path / "native"
    other.mkdir()
    engine = dispatched(other)
    try:
        doc = dispatch_document(engine)
        doc["findings"][0]["nodes"].pop(0)
        graph = report.check(engine, json.dumps(doc))
        assert not any(e["relation"] == "dispatch" for e in graph["edges"])
    finally:
        engine.store.close()


@pytest.mark.parametrize("tool", ["Read", "Bash"])
def test_read_or_lexical_target_reference_is_not_a_repair_anchor(tmp_path, tool):
    request = use(
        "check",
        tool,
        **(
            {"file_path": "/proj/A.ets"}
            if tool == "Read"
            else {"command": "grep bad /proj/A.ets"}
        ),
    )
    engine = build(
        tmp_path,
        [
            record(1, use("write", file_path="/proj/A.ets", content="bad")),
            record(2, result("write")),
            record(12, request),
            record(13, result("check", "bad")),
        ],
    )
    try:
        ref = engine.store.locate
        doc = {
            "schema": "inquiry/1",
            "target": {"file": "A.ets", "since": ts(10), "at": ts(15)},
            "findings": [
                {
                    "id": "A",
                    "title": "issue",
                    "reason": "model's claim",
                    "changes": [ref("a.jsonl", 3)],
                    "nodes": [
                        {
                            "id": "origin",
                            "kind": "agent",
                            "key": "a",
                            "at": ts(2),
                            "role": "origin",
                            "reason": "old write",
                            "evidence": [ref("a.jsonl", 1)],
                        }
                    ],
                }
            ],
        }
        graph = report.check(engine, json.dumps(doc))
        path = graph["tree"]["paths"][0]
        assert path["status"] == "unclosed" and path["repair_anchor"] is None
    finally:
        engine.store.close()


@pytest.mark.parametrize("kind,key", [("agent", "a"), ("file", "A.ets")])
def test_candidate_repair_cannot_make_native_or_zero_step_path_verified(
    tmp_path, kind, key
):
    engine = build(
        tmp_path,
        [
            record(1, use("write", file_path="/proj/A.ets", content="bad")),
            record(2, result("write")),
            record(
                12,
                use(
                    "fix",
                    "Edit",
                    file_path="/proj/A.ets",
                    old_string="bad",
                    new_string="good",
                ),
            ),
            record(13, result("fix", error=True)),
        ],
    )
    try:
        ref = engine.store.locate
        doc = {
            "schema": "inquiry/1",
            "target": {"file": "A.ets", "since": ts(10), "at": ts(15)},
            "findings": [
                {
                    "id": "A",
                    "title": "issue",
                    "reason": "model's claim",
                    "changes": [ref("a.jsonl", 3)],
                    "nodes": [
                        {
                            "id": "origin",
                            "kind": kind,
                            "key": key,
                            "at": ts(2),
                            "role": "origin",
                            "reason": "old write",
                            "evidence": [ref("a.jsonl", 1)],
                        }
                    ],
                }
            ],
        }
        graph = report.check(engine, json.dumps(doc))
        path = graph["tree"]["paths"][0]
        assert path["status"] == "candidate"
        assert path["repair_anchor"]["strength"] == "candidate"
        if kind == "file":
            assert path["steps"] == [] and path["anchor"]["strength"] == "confirmed"
    finally:
        engine.store.close()
