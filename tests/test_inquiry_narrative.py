"""Synthesis is source-bound model text, not a second graph or a semantic pass."""

import json

import pytest

from migloop.inquiry.report import check, load_report
from tests.test_inquiry_case_card import card, fixture_card
from tests.test_inquiry_core import build, record, result, ts, use


def recommendation():
    return {"target": "generator handoff", "action": "carry expected value with output",
            "reason": "preserve the actual input contract", "validation": "rerun the same case and compare",
            "findings": ["A"]}


def test_synthesis_roundtrip_and_consolidated_advice_do_not_rewrite_nodes(tmp_path):
    engine, task, document = fixture_card(tmp_path)
    try:
        original = check(engine, json.dumps(document))
        document["findings"][0].pop("recommendation")
        document["recommendations"] = [recommendation()]
        encoded = json.dumps(document)
        saved = check(engine, encoded, save=True)
        reopened = load_report(engine, saved["report_id"])
        assert reopened["document"] == document
        assert reopened["nodes"] == original["nodes"] and reopened["edges"] == original["edges"]
        assert reopened["tree"] == original["tree"] and not reopened["semantic_verified"]
        assert card.audit(engine.store.path, saved["report_id"], task)["status"] == "ready_for_review"
    finally:
        engine.store.close()


def test_legacy_report_still_loads_without_invented_synthesis(tmp_path):
    engine, task, document = fixture_card(tmp_path)
    try:
        document.pop("summary")
        document.pop("recommendations")
        document["findings"][0].pop("boundary")
        saved = check(engine, json.dumps(document), save=True)
        assert load_report(engine, saved["report_id"])["document"] == document
        audit = card.audit(engine.store.path, saved["report_id"], task)
        assert audit["loadable"] and audit["status"] == "draft"
        assert audit["investigation_gaps"] and not audit["semantic_verified"]
    finally:
        engine.store.close()


@pytest.mark.parametrize("where", ["summary", "recommendations", "boundary"])
def test_new_narrative_text_cannot_hide_false_references(tmp_path, where):
    engine, _, document = fixture_card(tmp_path)
    try:
        if where == "summary":
            document["summary"]["generation"] += " e-deadbeef1234"
        elif where == "boundary":
            document["findings"][0]["boundary"]["reason"] += " e-deadbeef1234"
        else:
            document["recommendations"] = [{**recommendation(), "reason": "unsupported e-deadbeef1234"}]
        graph = check(engine, json.dumps(document))
        assert graph["mechanical_status"] == "needs_revision"
        assert any(issue.get("ref") == "e-deadbeef1234" for issue in graph["issues"])
    finally:
        engine.store.close()


@pytest.mark.parametrize("field,value", [
    ("summary", "not an object"),
    ("summary", {"generation": "x"}),
    ("recommendations", "not a list"),
    ("recommendations", [{"target": "generator"}]),
])
def test_invalid_narrative_shape_is_not_silently_ignored(tmp_path, field, value):
    engine, _, document = fixture_card(tmp_path)
    try:
        document[field] = value
        with pytest.raises(ValueError):
            check(engine, json.dumps(document))
    finally:
        engine.store.close()


@pytest.mark.parametrize("change", ["finding", "duplicate", "node", "role"])
def test_synthesis_and_boundary_ids_cannot_drift(tmp_path, change):
    engine, _, document = fixture_card(tmp_path)
    try:
        if change == "finding":
            document["summary"]["findings"] = ["invented"]
        elif change == "duplicate":
            document["summary"]["findings"] = ["A", "A"]
        else:
            document["findings"][0]["boundary"]["nodes"] = ["invented" if change == "node" else "writer"]
        with pytest.raises(ValueError):
            check(engine, json.dumps(document))
    finally:
        engine.store.close()


def test_honest_unresolved_boundary_remains_loadable_draft(tmp_path):
    engine, task, document = fixture_card(tmp_path)
    try:
        document["findings"][0]["boundary"] = {"status": "unresolved", "nodes": [], "reason": "earlier input contract not checked"}
        graph = check(engine, json.dumps(document), save=True)
        assert graph["path_status"] == "complete"  # A writer path alone must not clear this gap.
        audit = card.audit(engine.store.path, graph["report_id"], task)
        assert audit["loadable"] and audit["status"] == "draft" and audit["investigation_gaps"]
        assert audit["mechanical_status"] == "valid" and not audit["semantic_verified"]
    finally:
        engine.store.close()


def test_synthesis_cannot_expose_future_evidence(tmp_path):
    engine, _, document = fixture_card(tmp_path)
    try:
        document["target"]["at"] = ts(4)
        document["findings"][0]["changes"] = [engine.store.locate("a.jsonl", 3)]
        ref = engine.store.handle("e", {"ref": engine.store.locate("a.jsonl", 4)})
        document["summary"]["repair"] = "Future success " + ref
        graph = check(engine, json.dumps(document))
        assert any(i.get("where") == "summary" and i.get("ref") == ref for i in graph["issues"])
    finally:
        engine.store.close()


def test_connected_problem_does_not_certify_unrelated_stopping_input(tmp_path):
    engine = build(tmp_path,
        [record(1, use("w", file_path="/proj/A.ets", content="bad")), record(2, result("w")),
         record(4, use("f", "Edit", file_path="/proj/A.ets", old_string="bad", new_string="good")), record(5, result("f"))],
        second=[record(0, use("r", "Read", file_path="/proj/UnusedSpec.md")), record(0, result("r", "correct but not delivered to a"))])
    try:
        document = {"schema": "inquiry/1", "target": {"file": "A.ets", "since": ts(3), "at": ts(9)},
            "summary": {"generation": "claimed adequate input", "repair": "fixed", "unknown": [], "findings": ["A"]},
            "recommendations": [recommendation()], "unexplained": [], "findings": [{"id": "A", "title": "bad output", "reason": "claims b supplies sufficient input",
                "changes": [engine.store.locate("a.jsonl", 3)], "unknown": [],
                "nodes": [{"id": "writer", "kind": "agent", "key": "a", "at": ts(2), "role": "origin", "reason": "writes bad", "evidence": [engine.store.locate("a.jsonl", 1)]},
                          {"id": "input", "kind": "agent", "key": "b", "at": ts(2), "role": "context", "reason": "received correct input", "evidence": [engine.store.locate("b.jsonl", 2)]}],
                "boundary": {"status": "supported_input", "nodes": ["input"], "reason": "claimed stopping point"}}]}
        graph = check(engine, json.dumps(document), save=True)
        assert graph["path_status"] == "complete"
        audit = card.audit(engine.store.path, graph["report_id"], {"file": "A.ets", "generation_end": ts(3), "observation_end": ts(9)})
        assert audit["status"] == "draft"
        assert any(g.get("node") == "input" for g in audit["investigation_gaps"])
        assert not any(e["relation"] == "read" and e["to"] == "A:writer" for e in graph["edges"])
    finally:
        engine.store.close()
