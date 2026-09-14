"""Declared node identity must survive projection; proximity is not a handoff."""

import json

import pytest

from migloop.inquiry.report import check, load_report
from tests.test_inquiry_core import build, record, result, ts, use


@pytest.fixture
def declared(tmp_path):
    engine = build(tmp_path,
        [record(1, use("w", file_path="/proj/A.ets", content="bad")), record(2, result("w")),
         record(10, use("fix", "Edit", file_path="/proj/A.ets", old_string="bad", new_string="good")), record(11, result("fix"))],
        second=[record(3, use("r", "Read", file_path="/proj/A.ets")), record(4, result("r", "bad")),
                record(5, use("w2", file_path="/proj/A.ets", content="bad retained")), record(6, result("w2")),
                record(7, use("check", "Bash", command="build /proj/A.ets")), record(8, result("check", "BUILD SUCCESSFUL")),
                record(9, {"type": "text", "text": "BUILD SUCCESSFUL (assistant claim)"})])
    loc = engine.store.locate
    evidence = lambda src, a, b: [loc(src + ".jsonl", a), loc(src + ".jsonl", b)]
    def node(nid, kind, key, at, role, refs):
        return dict(id=nid, kind=kind, key=key, at=ts(at), role=role, reason=nid, evidence=refs)
    def edge(origin, destination, relation, refs):
        return dict(**{"from": origin, "to": destination}, relation=relation, evidence=refs, claim="model handoff claim")
    document = {"schema": "inquiry/1", "target": {"file": "A.ets", "since": ts(9), "at": ts(15)},
        "findings": [{"id": "A", "title": "same file handoff", "reason": "a introduces; b preserves; later fixed",
            "changes": evidence("a", 3, 4), "nodes": [
                node("origin", "agent", "a", 2, "origin", evidence("a", 1, 2)),
                node("input", "file", "A.ets", 4, "propagated", evidence("a", 1, 2)),
                node("consumer", "agent", "b", 8, "propagated", evidence("b", 1, 2) + evidence("b", 3, 4)),
                node("target", "file", "A.ets", 15, "repaired", evidence("a", 3, 4))],
            "edges": [edge("origin", "input", "write", evidence("a", 1, 2)),
                      edge("input", "consumer", "read", evidence("b", 1, 2)),
                      edge("consumer", "target", "write", evidence("b", 3, 4))],
            "unknown": [], "recommendation": "check preserved attribute; not a measured benefit"}], "unexplained": []}
    yield engine, document
    engine.store.close()


def test_declared_same_file_handoff_is_not_shortened_to_first_writer(declared):
    engine, document = declared
    graph = check(engine, json.dumps(document), save=True)
    assert graph["mechanical_status"] == "valid"
    path = next(p for p in graph["tree"]["paths"] if p["node"] == "A:origin")
    assert [s["relation"] for s in path["steps"]] == ["write", "read", "write"]
    assert path["basis"] == "declared"
    assert all(p["status"] != "unclosed" for p in graph["tree"]["paths"] + graph["tree"]["context_paths"])
    scope = graph["tree"]["root"]
    for step in path["steps"]:
        manual = engine.query({"op": scope["kind"], **{k: scope[k] for k in ("key", "at", "since")}, "view": "neighbors", "report_id": graph["report_id"]})
        assert step in manual["rows"]
        scope = step["node"]
    assert load_report(engine, graph["report_id"])["document"] == document


def test_missing_handoff_does_not_gain_an_entity_shortcut(declared):
    engine, document = declared
    del document["findings"][0]["edges"][1]
    graph = check(engine, json.dumps(document))
    path = next(p for p in graph["tree"]["paths"] if p["node"] == "A:origin")
    assert path["status"] == "unclosed" and not path["steps"]
    assert graph["path_status"] == "needs_path"
    # Real but not declared read is a suggestion, not a silently inserted edge.
    assert not any(e["relation"] == "read" for e in graph["edges"])


def test_unrelated_cited_input_is_not_forced_into_declared_graph(declared):
    engine, document = declared
    # Exclude a real read deliberately: a comparison is not a declared input.
    f = document["findings"][0]
    f["nodes"] = [n for n in f["nodes"] if n["id"] in ("consumer", "target")]
    f["edges"] = [f["edges"][2]]
    graph = check(engine, json.dumps(document))
    assert graph["missing_evidence_links"]  # Still offered for optional investigation.
    assert graph["mechanical_status"] == "valid"
    assert len(graph["edges"]) == 1 and graph["edges"][0]["relation"] == "write"


@pytest.mark.parametrize("wrong", ["actor", "direction", "time"])
def test_declared_read_does_not_accept_wrong_recipient_or_time(declared, wrong):
    engine, document = declared
    f = document["findings"][0]
    if wrong == "actor":
        f["edges"][1]["to"] = "origin"
        f["nodes"][0]["at"] = ts(6)
    elif wrong == "direction":
        f["edges"][1]["from"], f["edges"][1]["to"] = "consumer", "input"
    else:
        f["nodes"][2]["at"] = ts(3)
    graph = check(engine, json.dumps(document))
    assert graph["mechanical_status"] == "needs_revision" and graph["unverified_edges"]


def test_legacy_automatic_projection_still_loads_but_is_not_declared(declared):
    engine, document = declared
    del document["findings"][0]["edges"]
    graph = check(engine, json.dumps(document))
    assert graph["mechanical_status"] == "valid"
    assert all(p["basis"] == "cited_history" for p in graph["tree"]["paths"])


@pytest.mark.parametrize("fault", [None, "actor", "summary", "request", "tool", "late"])
def test_check_receipt_binds_native_call_not_assistant_summary(declared, fault):
    engine, document = declared
    f = document["findings"][0]
    loc = engine.store.locate
    item = {"node": "consumer", "request": loc("b.jsonl", 5), "result": loc("b.jsonl", 6),
            "tool": "Bash", "claim": "build returned success; target behavior not certified"}
    f["checks"] = [item]
    if fault == "actor":
        item["node"] = "origin"
        f["nodes"][0]["at"] = ts(8)
    elif fault == "summary":
        item["result"] = loc("b.jsonl", 7)
        f["nodes"][2]["at"] = ts(9)
    elif fault == "request":
        item["request"] = loc("b.jsonl", 1)
    elif fault == "tool":
        item["tool"] = "Read"
    elif fault == "late":
        f["nodes"][2]["at"] = ts(7)
    graph = check(engine, json.dumps(document))
    if fault is None:
        assert graph["mechanical_status"] == "valid"
        assert graph["check_results"][0]["status"] == "native_pair"
        assert not graph["check_results"][0]["semantic_verified"]
    else:
        assert graph["mechanical_status"] == "needs_revision"
        assert any("checks" in i["where"] for i in graph["issues"])
    assert graph["document"] == document


def test_new_delivery_requires_declared_edges_but_legacy_still_loads(tmp_path):
    from tests.test_inquiry_case_card import card, fixture_card

    engine, task, doc = fixture_card(tmp_path)
    try:
        graph = check(engine, json.dumps(doc), save=True)
        legacy = card.audit(engine.store.path, graph["report_id"], task)
        delivery = card.audit(engine.store.path, graph["report_id"], task, require_declared=True)
        assert legacy["loadable"] and delivery["loadable"]
        assert delivery["status"] == "draft" and delivery["declared_tree_required"]
        assert any("edges" in g["error"] for g in delivery["investigation_gaps"])
    finally:
        engine.store.close()


@pytest.mark.parametrize("mode", ["success", "failure", "summary", "wrong_block", "ambiguous", "future"])
def test_receipts_are_block_exact_and_do_not_certify_behavior(tmp_path, mode):
    engine = build(tmp_path, [
        record(1, use("x", "Bash", command="build A.ets"), use("y", "Read", file_path="/proj/log.txt")),
        record(2, result("x", "BUILD FAILED", error=True), result("y", "old BUILD SUCCESSFUL")),
        record(3, {"type": "text", "text": "BUILD SUCCESSFUL"})])
    try:
        loc = engine.store.locate
        item = {"node": "checker", "request": loc("a.jsonl", 1), "result": loc("a.jsonl", 2),
                "tool": "Bash", "request_block": 0, "result_block": 0, "claim": "this is a call, not a behavior proof"}
        if mode == "success":
            item.update(tool="Read", request_block=1, result_block=1)
        elif mode == "summary":
            item["result"] = loc("a.jsonl", 3)
        elif mode == "wrong_block":
            item["result_block"] = 1
        elif mode == "ambiguous":
            item.pop("request_block")
            item.pop("result_block")
        doc = {"schema": "inquiry/1", "target": {"file": "A.ets", "at": ts(1 if mode == "future" else 3)},
            "findings": [{"id": "A", "title": "check", "reason": "check", "changes": [], "edges": [],
                "nodes": [{"id": "checker", "kind": "agent", "key": "a", "at": ts(3), "role": "context", "reason": "check", "evidence": []}],
                "checks": [item]}]}
        graph = check(engine, json.dumps(doc))
        if mode in ("success", "failure"):
            bound, = graph["check_results"]
            assert bool(bound["protocol_success"]) == (mode == "success")
            assert not bound["semantic_verified"]  # Read log PASS is still just a Read.
        else:
            assert not graph["check_results"] and any("checks" in i["where"] for i in graph["issues"])
    finally:
        engine.store.close()
