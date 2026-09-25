"""Exercise the documented graph shapes, not the truth of example diagnoses.

Only coordinates and histories are synthetic here. Real examples are separately
checked against their cited transcripts; passing these tests is not an accuracy score.
"""
import copy
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

SKILLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILLS / "migloop-memory-maintain/scripts"))
from memorylib.card_contract import graph_shape
from migloop.inquiry.report import check
from migloop.inquiry.store import timestamp
from tests.test_inquiry_core import build, record, result, ts, use


def example_graph(index):
    text = (SKILLS / "migloop-build-cards/SKILL.md").read_text(encoding="utf-8")
    drafts = [yaml.safe_load(b) for b in re.findall(r"```yaml\n(.*?)\n```", text, re.S)]
    # The first is the placeholder template, followed by the two real examples.
    draft = drafts[index + 1]
    return {"summary": draft["summary"], "recommendations": draft["recommendations"],
            **copy.deepcopy(draft["graphs"][0])}


@pytest.mark.parametrize("index", [0, 1])
def test_complete_documented_example_satisfies_current_graph_schema(index):
    graph = example_graph(index)
    assert not graph_shape(graph)
    assert all(not edge.get("force") for edge in graph["edges"])
    assert any(node.get("problem") for node in graph["nodes"])


def test_documented_short_graph_binds_original_write_despite_later_writers(tmp_path):
    graph = example_graph(0)
    graph["target"] = {"key": "/proj/A.ets", "since": ts(11), "at": ts(20)}
    for node, key, second in zip(graph["nodes"], ["/proj/input.xml", "/proj/mapping.md", "a.jsonl"], [2, 4, 6]):
        node.update(key=key, at=ts(second), reason="Synthetic contract test")
    engine = build(tmp_path, [
        record(1, use("xml", "Read", file_path="/proj/input.xml")), record(2, result("xml", "size needed")),
        record(3, use("mapping", "Read", file_path="/proj/mapping.md")), record(4, result("mapping", "explicit size")),
        record(5, use("w", file_path="/proj/A.ets", content="bad size; old wiring")), record(6, result("w")),
    ], second=[
        record(7, use("r", "Read", file_path="/proj/A.ets")), record(8, result("r", "bad size; old wiring")),
        record(9, use("wire", "Edit", file_path="/proj/A.ets", old_string="old wiring", new_string="new wiring")),
        record(10, result("wire")),
        record(13, use("fix", "Edit", file_path="/proj/A.ets", old_string="bad size", new_string="good size")),
        record(14, result("fix")),
    ])
    try:
        checked = check(engine, json.dumps(graph))
        assert checked["mechanical_status"] == "valid", checked
        assert checked["path_status"] == "complete"
        assert len(checked["edges"]) == 3
        write, = [edge for edge in checked["edges"] if edge["relation"] == "write"]
        assert timestamp(write["at"]) == timestamp(ts(6))
        assert all(node["key"] != "b" for node in checked["nodes"])
    finally:
        engine.store.close()


def test_documented_cross_file_graph_needs_spec_and_actual_consumer(tmp_path):
    graph = example_graph(1)
    graph["target"] = {"key": "/proj/A.ets", "since": ts(11), "at": ts(20)}
    for node, key, second in zip(graph["nodes"], ["/proj/source.kt", "a.jsonl", "/proj/spec.md", "b.jsonl"], [2, 4, 6, 8]):
        node.update(key=key, at=ts(second), reason="Synthetic contract test")
    engine = build(tmp_path, [
        record(1, use("source", "Read", file_path="/proj/source.kt")), record(2, result("source", "integer px")),
        record(3, use("spec", file_path="/proj/spec.md", content="integer vp")), record(4, result("spec")),
    ], second=[
        record(5, use("r", "Read", file_path="/proj/spec.md")), record(6, result("r", "integer vp")),
        record(7, use("w", file_path="/proj/A.ets", content="integer vp")), record(8, result("w")),
        record(13, use("fix", "Edit", file_path="/proj/A.ets", old_string="integer vp", new_string="integer px")),
        record(14, result("fix")),
    ])
    try:
        checked = check(engine, json.dumps(graph))
        assert checked["mechanical_status"] == "valid", checked
        assert checked["path_status"] == "complete"
        assert len(checked["edges"]) == 4
        shortcut = copy.deepcopy(graph)
        shortcut["nodes"] = shortcut["nodes"][:2]
        shortcut["edges"] = [{"from": 1, "to": 2}, {"from": 2, "to": "target"}]
        rejected = check(engine, json.dumps(shortcut))
        assert rejected["mechanical_status"] == "needs_revision"
        assert rejected["unverified_edges"]
        assert rejected["path_status"] == "needs_path"
    finally:
        engine.store.close()
