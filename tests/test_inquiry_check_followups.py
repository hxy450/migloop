"""A cited check can have later receipts even if its actor never wrote the target."""

import json

from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, ts, use
from tests.test_inquiry_query_contract_regressions import document


def test_nonwriter_check_continues_to_later_receipt_without_creating_edges(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="code")),
            record(2, result("w")),
        ],
        [
            record(3, use("check", "Bash", command="compiler project")),
            record(4, result("check", "Compiler Error: some error", error=True)),
            record(5, use("again", "Bash", command="compiler project")),
            record(6, result("again", "BUILD SUCCESSFUL")),
        ],
    )
    doc = document(engine.store.locate("a.jsonl", 1))
    failed = engine.store.handle("e", {"ref": engine.store.locate("b.jsonl", 2)})
    doc["unexplained"] = [f"The model says last check failed ({failed})."]
    graph = check(engine, json.dumps(doc), save=True)
    rows = graph["evidence_review"]["cited_check_followups"]
    assert len(rows) == 1 and rows[0]["agent"] == "b"
    assert rows[0]["evidence"] == [failed]
    success = engine.store.handle("e", {"ref": engine.store.locate("b.jsonl", 4)})
    assert success in [r["cite"] for r in rows[0]["matches"]]
    assert rows[0]["not_validation_proof"] and rows[0]["not_absence_proof"]
    assert graph["document"] == doc and len(graph["edges"]) == 1
    assert not graph["semantic_verified"] and engine.trace() == []
    queried = engine.query({"op": "review", "report_id": graph["report_id"]})
    assert any(row["category"] == "cited_check_followups" for row in queried["rows"])
    engine.store.close()


def test_unquoted_future_undated_and_other_actor_checks_do_not_supply_followups(
    tmp_path,
):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="code")),
            record(2, result("w")),
            record(6, result("unquoted", "BUILD SUCCESSFUL")),
        ],
        [
            record(3, result("check", "BUILD FAILED")),
            record(10, result("future", "BUILD SUCCESSFUL")),
            record(None, result("undated", "BUILD SUCCESSFUL")),
        ],
    )
    doc = document(engine.store.locate("a.jsonl", 1))
    ref = engine.store.handle("e", {"ref": engine.store.locate("b.jsonl", 1)})
    doc["unexplained"] = [f"Recorded check {ref}"]
    rows = check(engine, json.dumps(doc))["evidence_review"]["cited_check_followups"]
    assert rows == []  # no later candidate; not evidence that nothing happened
    doc["unexplained"] = []
    assert (
        check(engine, json.dumps(doc))["evidence_review"]["cited_check_followups"] == []
    )
    engine.store.close()


def test_quoted_instructions_are_only_literal_candidates_and_latest_cite_bounds_window(
    tmp_path,
):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="code")),
            record(2, result("w")),
        ],
        [
            record(3, result("old", "BUILD FAILED")),
            record(4, result("docs", "README example: BUILD FAILED")),
            record(5, result("new", "README example: BUILD SUCCESSFUL")),
        ],
    )
    doc = document(engine.store.locate("a.jsonl", 1))
    older = engine.store.handle("e", {"ref": engine.store.locate("b.jsonl", 1)})
    newer = engine.store.handle("e", {"ref": engine.store.locate("b.jsonl", 2)})
    doc["unexplained"] = [f"{older} and {newer}"]
    graph = check(engine, json.dumps(doc))
    item = graph["evidence_review"]["cited_check_followups"][0]
    assert item["evidence"] == [newer]
    assert item["query"]["since"].startswith(ts(4)[:-1])
    assert item["not_validation_proof"] and len(graph["edges"]) == 1
    engine.store.close()
