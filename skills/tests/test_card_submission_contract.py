"""Small authoring surface and actionable feedback survive skill packaging."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migloop-memory-maintain/scripts"))
from memorylib.card_storage import check_summary
from memorylib.cases import DraftError, _graph_shape, pack
from memorylib.common import load
from test_memory_bundle import prepared


def test_shape_errors_name_all_bad_fields(prepared):
    graph = copy.deepcopy(prepared["draft"]["graphs"][0])
    graph["nodes"][0]["at"] = "not a timestamp"
    graph["nodes"][0]["problem"] = "true"
    graph["edges"][0]["from"] = 0
    errors = _graph_shape(graph, "graphs[2]")
    assert {e["where"] for e in errors} >= {
        "graphs[2].nodes[0].at", "graphs[2].nodes[0].problem", "graphs[2].edges[0].from"}


def test_optional_prose_inherits_without_rewriting_authored_card(prepared):
    draft = copy.deepcopy(prepared["draft"])
    draft.pop("unknown")
    graph = draft["graphs"][0]
    graph.pop("summary")
    graph.pop("recommendations")
    graph["target"]["at"] = graph["target"]["at"].replace("Z", "+00:00")
    path = prepared["root"] / "minimal.json"
    path.write_text(json.dumps(draft), encoding="utf-8")
    out = prepared["root"] / "minimal-case.json"
    result = pack(prepared["job"], path, out, draft_only=True)
    assert load(out)["draft"] == draft
    view = load(Path(result["views"]) / "target-1.json")
    assert view["summary"] == draft["summary"]
    assert view["recommendations"] == draft["recommendations"]


def test_path_feedback_not_flattened_and_optional_links_not_reported_missing():
    failure = {"where": "nodes[1]", "key": "worker", "at": "2026-01-01T00:00:10Z",
               "code": "time_reversal", "diagnostic": "late input",
               "blocked_branches": [{"upstream": {"at": "10", "evidence": ["read"]},
                                     "downstream": {"at": "6", "evidence": ["write"]}}],
               "next_step": "Inspect the two operations"}
    summary = check_summary({"path_feedback": [failure], "tree": {"huge": "not persisted"},
                             "missing_evidence_links": [{"not": "a required connection"}]})
    assert summary["path_feedback"] == [failure]
    assert "tree" not in summary and "missing_evidence_links" not in summary


def test_core_coordinate_errors_remain_structured(prepared, monkeypatch):
    from migloop.inquiry.card import CardError
    from migloop.inquiry.store import Store, Source
    db = prepared["root"] / "index.sqlite"
    Store.build(db, [Source(str(prepared["pool"] / "agent.jsonl"), "agent.jsonl", "agent", "/app")]).close()
    issues = [{"where": "nodes[0]", "error": "Unknown transcript", "query": {"op": "catalog", "kind": "source"}}]
    def reject(*args, **kwargs):
        raise CardError(issues)
    monkeypatch.setattr("migloop.inquiry.report.check", reject)
    result = pack(prepared["job"], prepared["root"] / "draft.json", prepared["root"] / "rejected.json", db)
    receipt = result["validation"]["graph_checks"][0]["receipt"]
    assert receipt["code"] == "invalid_card" and isinstance(receipt["issues"], list)
    assert receipt["issues"][0]["where"] == ["nodes[0]"]
    assert receipt["issues"][0]["query"]["kind"] == "source"
