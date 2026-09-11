"""Observed delivery failures as generic, answer-free invariants."""

import json
import re

import pytest

from migloop.inquiry import report
from tests.test_inquiry_core import build, record, result, ts, use


def test_result_filename_brings_back_opaque_request_only_after_result(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("s", "Bash", command="python batch.py")),
            record(3, result("s", "changed /proj/A.ets")),
        ],
    )
    early = engine.query({"op": "file", "key": "A.ets", "at": ts(2)})
    assert early["total"] == 0
    later = engine.query({"op": "file", "key": "A.ets", "at": ts(4)})
    assert {r["line"] for r in later["rows"]} == {1, 2}
    assert engine.store.rows("SELECT * FROM effects") == []
    engine.store.close()


def test_every_batch_item_has_independent_visible_result_even_after_huge_open(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="X" * 40000)),
            record(2, result("w")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 1)
    text = engine.investigate(
        [
            {"op": "open", "ref": ref, "at": ts(3)},
            {"op": "search", "at": ts(3), "terms": ["NO-HIT"]},
            {"op": "bogus"},
        ]
    )
    ids = re.findall(r"RESULT ([a-f0-9]+)", text)
    assert len(set(ids)) == 3
    assert "ERROR" in text and "total=0" in text
    assert len(text) <= engine.FRAME + 1000
    second = engine.page(ids[1], 0)
    assert "NO-HIT" in second and "X" * 100 not in second
    engine.store.close()


def test_bound_scope_and_link_preserve_reasons_without_copying_coordinates(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="one")),
            record(2, result("w")),
        ],
    )
    opened = engine.query(
        {"op": "file", "key": "A.ets", "at": ts(4), "since": ts(0), "view": "relations"}
    )
    link = opened["rows"][0]
    doc = {
        "schema": "inquiry/1",
        "target": {"scope": opened["scope_id"]},
        "findings": [
            {
                "id": "A",
                "title": "model title",
                "reason": "Unchanged model cause",
                "changes": [link["request"]],
                "nodes": [
                    {
                        "id": "agent",
                        "scope": link["from_scope"],
                        "role": "origin",
                        "reason": "actor cause",
                        "evidence": [link["request"]],
                    },
                    {
                        "id": "file",
                        "scope": link["to_scope"],
                        "role": "propagated",
                        "reason": "file cause",
                        "evidence": [link["result"]],
                    },
                ],
                "edges": [
                    {
                        "from": "agent",
                        "to": "file",
                        "link": link["link"],
                        "claim": "model propagation claim",
                    }
                ],
            }
        ],
    }
    checked = report.check(engine, json.dumps(doc))
    assert not checked["issues"] and len(checked["edges"]) == 1
    assert checked["nodes"][0]["reason"] == "actor cause"
    assert checked["document"]["target"] == doc["target"]
    assert checked["target"]["at"].startswith("2026-01-01T00:00:04")
    assert not checked["semantic_verified"]
    bad = json.loads(json.dumps(doc))
    bad["findings"][0]["edges"][0]["from"] = "file"
    assert not report.check(engine, json.dumps(bad))["edges"]
    engine.store.close()


def test_evidence_handle_still_checks_original_bytes(tmp_path):
    engine = build(
        tmp_path, [record(1, use("w", file_path="/proj/A.ets", content="one"))]
    )
    page = engine.query({"op": "agent", "key": "a", "at": ts(2)})
    ref = page["rows"][0]["cite"]
    assert ref.startswith("e-")
    opened = engine.query({"op": "open", "ref": ref, "at": ts(2)})
    assert "one" in opened["text"]
    path = tmp_path / "a.jsonl"
    path.write_bytes(path.read_bytes().replace(b"one", b"two"))
    with pytest.raises(ValueError, match="bytes changed"):
        engine.query({"op": "open", "ref": ref, "at": ts(2)})
    engine.store.close()


def test_call_description_and_paired_output_are_visible_not_promoted_to_write(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1, use("s", "Bash", command="python x.py", description="Change masks")
            ),
            record(2, result("s", "3 sites /proj/A.ets")),
        ],
    )
    data = engine.query({"op": "file", "key": "A.ets", "at": ts(3), "view": "calls"})
    assert len(data["rows"]) == 1 and "Change masks" in data["rows"][0]["excerpt"]
    assert "3 sites" in data["rows"][0]["excerpt"]
    assert engine.store.rows("SELECT * FROM effects") == []
    engine.store.close()


def test_literal_windows_are_explicit_and_do_not_lose_late_matches(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                {"type": "text", "text": "a\nneedle first\nb\nc\nd\nneedle second\ne"},
            )
        ],
    )
    ref = engine.store.locate("a.jsonl", 1)
    data = engine.query(
        {"op": "open", "ref": ref, "at": ts(2), "terms": ["needle"], "context": 0}
    )
    assert data["matched_lines"] == 2
    assert "needle first" in data["text"] and "needle second" in data["text"]
    assert "not whole" in data["selection"]
    engine.store.close()


def test_coverage_surfaces_opaque_call_without_assuming_a_modification(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("s", "Bash", command="python mystery.py")),
            record(2, result("s", "A.ets")),
        ],
    )
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(3), "since": ts(0)},
        "findings": [],
    }
    graph = report.check(engine, json.dumps(doc))
    assert graph["mechanical_status"] == "needs_revision"
    gap = graph["coverage"]["unassessed"][0]
    assert gap["recorded_effects"] == []
    doc["reviewed"] = [
        {
            "ref": gap["ref"],
            "effect": "unknown",
            "reason": "Opaque call does not establish a modification",
        }
    ]
    graph = report.check(engine, json.dumps(doc))
    assert (
        not graph["coverage"]["unassessed"] and len(graph["coverage"]["unknown"]) == 1
    )
    assert not graph["semantic_verified"]
    engine.store.close()


def test_deleting_edges_does_not_complete_native_evidence_graph(tmp_path):
    from tests.test_inquiry_core import valid_report

    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="one")),
            record(2, result("w")),
        ],
    )
    doc = valid_report(engine)
    doc["findings"][0]["edges"] = []
    graph = report.check(engine, json.dumps(doc))
    assert (
        graph["missing_evidence_links"]
        and graph["mechanical_status"] == "needs_revision"
    )
    assert graph["edges"] == []
    assert graph["document"] == doc
    engine.store.close()
