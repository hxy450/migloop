"""The skill's auditor reuses the UI loader, without silently repairing a report."""

import importlib.util
import json
from pathlib import Path

import pytest

from migloop.inquiry.report import check, load_report
from migloop.inquiry.web import dispatch_http
from tests.test_inquiry_core import build, record, result, ts, use


SCRIPT = Path(__file__).parents[1] / "docs/skills/migloop-investigate/scripts/check_card.py"
spec = importlib.util.spec_from_file_location("case_card_script", SCRIPT)
card = importlib.util.module_from_spec(spec)
spec.loader.exec_module(card)


def fixture_card(tmp_path, opaque=False):
    rows = [record(1, use("w", file_path="/proj/A.ets", content="bad")), record(2, result("w")),
            record(4, use("fix", "Edit", file_path="/proj/A.ets", old_string="bad", new_string="good")),
            record(5, result("fix"))]
    if opaque:
        rows += [record(6, use("opaque", "Bash", command="python opaque.py /proj/A.ets")), record(7, result("opaque"))]
    engine = build(tmp_path, rows)
    refs = [engine.store.locate("a.jsonl", line) for line in range(1, 5)]
    task = {"file": "A.ets", "generation_end": ts(3), "observation_end": ts(9)}
    document = {"schema": "inquiry/1", "target": {"file": "A.ets", "since": ts(3), "at": ts(9)},
                "findings": [{"id": "A", "title": "local mismatch", "reason": "original claim",
                    "changes": refs[2:], "nodes": [{"id": "writer", "kind": "agent", "key": "a", "at": ts(2),
                        "role": "origin", "reason": "original node claim", "evidence": refs[:2]}],
                    "unknown": [], "recommendation": "candidate check; effect not measured"}], "unexplained": []}
    return engine, task, document


def save_and_audit(engine, task, document):
    graph = check(engine, json.dumps(document), save=True)
    return graph, card.audit(engine.store.path, graph["report_id"], task)


def test_card_auditor_and_ui_load_identical_original_without_mutation(tmp_path):
    engine, task, document = fixture_card(tmp_path)
    try:
        graph = check(engine, json.dumps(document), save=True)
        before = {t: engine.store.rows("SELECT * FROM " + t) for t in ("runs", "handles", "frames", "visible")}
        audit = card.audit(engine.store.path, graph["report_id"], task)
        after = {t: engine.store.rows("SELECT * FROM " + t) for t in before}
        assert after == before
        status, body, _ = dispatch_http(engine.store.path, "/api/report?id=" + graph["report_id"])
        assert status == 200 and json.loads(body)["document"] == document
        assert audit["loadable"] and audit["status"] == "ready_for_review"
        assert audit["source_sha256"] == graph["source_sha256"]
        assert not audit["semantic_verified"] and not audit["browser_verified"]
    finally:
        engine.store.close()


def test_unassessed_effect_is_draft_not_complete_even_when_loader_accepts(tmp_path):
    engine, task, document = fixture_card(tmp_path, opaque=True)
    try:
        _, audit = save_and_audit(engine, task, document)
        assert audit["loadable"] and audit["status"] == "draft"
        assert audit["coverage"]["unassessed_count"] > 0
        assert not audit["coverage"]["complete"]
    finally:
        engine.store.close()


@pytest.mark.parametrize("change", ["different_file", "different_time", "no_advice", "false_reference", "unrelated_node"])
def test_invalid_claims_cannot_be_certified_as_a_ready_card(tmp_path, change):
    engine, task, document = fixture_card(tmp_path)
    try:
        if change == "different_file":
            task["file"] = "Other.ets"
        elif change == "different_time":
            task["generation_end"] = ts(2)
        elif change == "no_advice":
            document["findings"][0].pop("recommendation")
        elif change == "false_reference":
            document["findings"][0]["nodes"][0]["evidence"] = ["e-not-a-real-event"]
        else:
            document["findings"][0]["nodes"][0]["key"] = "unrelated-author"
        _, audit = save_and_audit(engine, task, document)
        assert audit["status"] != "ready_for_review"
        assert not audit["semantic_verified"]
        assert load_report(engine, audit["report_id"])["document"] == document
    finally:
        engine.store.close()


def test_script_failure_is_json_and_nonzero(tmp_path, capsys):
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"runtime": {"index_path": str(tmp_path / "absent.sqlite")}}))
    assert card.main(["--task", str(task), "--report", "missing"]) == 2
    data = json.loads(capsys.readouterr().out)
    assert not data["loadable"] and data["status"] == "invalid"
    assert not (tmp_path / "absent.sqlite").exists()
