"""Validation words in later returns are navigable candidates, not a proof gate."""

import json

from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, use
from tests.test_inquiry_query_contract_regressions import document


def test_project_build_return_without_filename_is_reachable_after_target_write(
    tmp_path,
):
    engine = build(
        tmp_path,
        [
            record(1, use("write", file_path="A.ets", content="some program")),
            record(2, result("write")),
            record(3, use("build", "Bash", command="compiler build")),
            record(4, result("build", "BUILD SUCCESSFUL")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 1)
    doc = document(ref)
    graph = check(engine, json.dumps(doc))
    rows = graph["evidence_review"]["post_write_returns"]
    assert len(rows) == 1 and rows[0]["total"] == 1
    item = rows[0]
    assert item["matches"][0]["cite"] == engine.store.handle(
        "e", {"ref": engine.store.locate("a.jsonl", 4)}
    )
    assert item["not_validation_proof"] and item["not_absence_proof"]
    assert engine.query(item["all_returns_query"])["total"] == 2
    assert graph["document"] == doc and len(graph["edges"]) == 1
    assert engine.trace() == []  # server context lookup is NOT a model query
    engine.store.close()


def test_prior_other_agent_future_and_undated_markers_are_not_postwrite_evidence(
    tmp_path,
):
    engine = build(
        tmp_path,
        [
            record(1, result("earlier", "BUILD SUCCESSFUL")),
            record(2, use("write", file_path="A.ets", content="changed")),
            record(3, result("write")),
            record(10, result("future", "BUILD SUCCESSFUL")),
            record(None, result("undated", "BUILD SUCCESSFUL")),
        ],
        [record(4, result("other", "BUILD SUCCESSFUL"))],
    )
    doc = document(engine.store.locate("a.jsonl", 2))
    rows = check(engine, json.dumps(doc))["evidence_review"]["post_write_returns"]
    assert len(rows) == 1 and rows[0]["total"] == 0 and rows[0]["matches"] == []
    assert rows[0]["not_absence_proof"]
    engine.store.close()


def test_validation_words_in_readme_are_not_promoted_to_success_or_causal_edges(
    tmp_path,
):
    engine = build(
        tmp_path,
        [
            record(1, use("write", file_path="A.ets", content="code")),
            record(2, result("write")),
            record(3, use("read", "Read", file_path="README.md")),
            record(
                4,
                result(
                    "read", "The instructions say BUILD SUCCESSFUL, not a real build."
                ),
            ),
        ],
    )
    graph = check(engine, json.dumps(document(engine.store.locate("a.jsonl", 1))))
    item = graph["evidence_review"]["post_write_returns"][0]
    assert item["total"] == 1 and item["not_validation_proof"]
    assert item["matches"][0]["tools"] == ["Read"]
    assert (
        len(graph["edges"]) == 1
    )  # only the model-cited Write, not the automatic lookup
    assert graph["semantic_verified"] is False
    engine.store.close()
