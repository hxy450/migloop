"""The job supplies the repaired target; the graph proves declared handoffs."""
import copy
import json

import pytest

from migloop.inquiry.feedback import compact_feedback
from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, ts, use


@pytest.fixture(params=["Edit", "Bash", "Read", "none"])
def target_path(tmp_path, request):
    rows = [record(1, use("input", "Read", file_path="/proj/spec.md")),
            record(2, result("input", "gap must be 4")),
            record(3, use("write", "Write", file_path="/proj/Output.ets", content="gap=8")),
            record(4, result("write"))]
    if request.param != "none":
        args = ({"command": "python repair.py /proj/Output.ets"} if request.param == "Bash"
                else {"file_path": "/proj/Output.ets"})
        if request.param == "Edit":
            args.update(old_string="gap=8", new_string="gap=4")
        rows += [record(11, use("later", request.param, **args)), record(12, result("later"))]
    engine = build(tmp_path, rows)
    document = {"target": {"key": "/proj/Output.ets", "since": ts(10), "at": ts(15)},
                "summary": "Synthetic input/output mismatch", "recommendations": ["Check the input value"],
                "nodes": [{"key": "/proj/spec.md", "at": ts(2), "reason": "Synthetic correct input"},
                          {"key": "a.jsonl", "at": ts(4), "reason": "Synthetic wrong output", "problem": True}],
                "edges": [{"from": 1, "to": 2}, {"from": 2, "to": "target"}]}
    try:
        yield engine, document
    finally:
        engine.store.close()


def test_declared_path_does_not_require_repair_proof(target_path):
    engine, document = target_path
    graph = check(engine, json.dumps(document), save=True)
    assert graph["mechanical_status"] == "valid"
    assert graph["path_status"] == "complete"
    assert graph["delivery"]["status"] == "ready_for_review"
    assert len(graph["edges"]) == 2
    assert graph["path_feedback"] == []
    assert all(p["repair_anchor"] is None for p in graph["tree"]["paths"] + graph["tree"]["context_paths"])
    assert not graph["semantic_verified"]


def test_missing_handoff_still_blocks_and_identifies_node(target_path):
    engine, document = target_path
    document["edges"].pop()
    graph = check(engine, json.dumps(document), save=True)
    assert graph["path_status"] == "needs_path" and graph["delivery"]["status"] == "draft"
    failure = next(p for p in graph["path_feedback"] if p["where"] == "nodes[1]")
    assert failure["code"] == "disconnected_path" and failure["key"] == "a"
    assert failure["dead_ends"] == [{"key": "a", "at": failure["at"], "where": "nodes[1]"}]
    assert failure["next_step"]
    assert compact_feedback(graph)["paths"] == graph["path_feedback"]


def test_disconnected_normal_input_is_not_hidden_by_complete_problem_path(target_path):
    engine, document = target_path
    document["edges"].pop(0)
    graph = check(engine, json.dumps(document))
    assert all(p["status"] == "native" for p in graph["tree"]["paths"])
    assert graph["path_status"] == "needs_path" and graph["delivery"]["status"] == "draft"
    assert any(p["where"] == "nodes[0]" for p in graph["path_feedback"])


def test_bad_force_still_cannot_replace_the_missing_connection(target_path):
    engine, document = target_path
    document = copy.deepcopy(document)
    document["edges"][1].update(force=True, reason="First submission cannot override", evidence=[{"source": "a.jsonl", "line": 3}])
    graph = check(engine, json.dumps(document))
    assert graph["mechanical_status"] == "needs_revision"
    assert graph["unverified_edges"][0]["code"] == "force_before_feedback"
