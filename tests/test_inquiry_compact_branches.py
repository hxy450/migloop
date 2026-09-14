"""Shared inputs are one claim, with separately verified/displayed branches."""

import json
import subprocess

from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, ts, use


def test_shared_input_is_rendered_under_both_declared_consumers(tmp_path):
    engine = build(tmp_path, [
        record(1, use("spec", file_path="/proj/spec.md", content="bad contract")), record(2, result("spec")),
        record(11, use("x", "Read", file_path="/proj/X.ets")), record(12, result("x", "bad x")),
        record(13, use("y", "Read", file_path="/proj/Y.ets")), record(14, result("y", "bad y")),
        record(15, use("target", file_path="/proj/Target.ets", content="bad integration")), record(16, result("target")),
        record(19, use("fix", "Edit", file_path="/proj/Target.ets", old_string="bad", new_string="good")), record(20, result("fix"))], second=[
        record(3, use("spec-x", "Read", file_path="/proj/spec.md")), record(4, result("spec-x", "bad contract")),
        record(5, use("x", file_path="/proj/X.ets", content="bad x")), record(6, result("x")),
        record(7, use("spec-y", "Read", file_path="/proj/spec.md")), record(8, result("spec-y", "bad contract")),
        record(9, use("y", file_path="/proj/Y.ets", content="bad y")), record(10, result("y"))])
    try:
        def node(key, time):
            return {"key": key, "at": ts(time)}
        coordinates = [node("/proj/spec.md", 8), node("b.jsonl", 6), node("/proj/X.ets", 12),
                       node("b.jsonl", 10), node("/proj/Y.ets", 14), node("a.jsonl", 16)]
        target = node("/proj/Target.ets", 21)
        doc = {"target": {**target, "since": ts(18)}, "summary": "Two recorded deliveries of the same input claim.",
               "recommendations": ["Verify source contract and both consumers."],
               "nodes": [{**c, "reason": "A model claim, not a generated first-author label.", "problem": True} for c in coordinates],
               "edges": [{"from": coordinates[a], "to": coordinates[b]} for a, b in [(0, 1), (1, 2), (2, 5), (0, 3), (3, 4), (4, 5)]]}
        doc["edges"].append({"from": coordinates[5], "to": target})
        graph = check(engine, json.dumps(doc))
        assert graph["delivery"]["status"] == "ready_for_review"
        spec, = [n for n in graph["nodes"] if n["key"] == "/proj/spec.md"]
        arms = [p for p in graph["tree"]["paths"] if p["node"] == spec["id"]]
        assert len(arms) == 2 and all(p["status"] == "native" for p in arms)
        script = "const fs=require('fs'),{EvidenceTreeModel}=require('./src/migloop/inquiry/tree.js');const g=JSON.parse(fs.readFileSync(0,'utf8'));const t=new EvidenceTreeModel(g.tree.root);t.seed(g);console.log(JSON.stringify({gaps:t.unclosed,instances:[...t.nodes.values()].filter(n=>n.claims.some(c=>c.key==='/proj/spec.md')).map(n=>({id:n.id,parent:n.parent.id}))}));"
        rendered = subprocess.run(["node", "-e", script], input=json.dumps(graph), capture_output=True, text=True, check=True)
        result_tree = json.loads(rendered.stdout)
        assert not result_tree["gaps"] and len(result_tree["instances"]) == 2
        assert len({n["parent"] for n in result_tree["instances"]}) == 2
    finally:
        engine.store.close()
