"""Synthetic missing-file regressions; not historical attribution claims."""
import copy
import json

import pytest

from migloop.inquiry.card import CardError
from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check, load_report
from tests.test_inquiry_core import build, record, result, ts, use


@pytest.fixture
def supplemental(tmp_path):
    engine = build(tmp_path, [
        record(1, use("opaque", "Bash", command="python load_inputs.py")),
        record(2, result("opaque", "required gap = 4")),
        record(3, use("w", file_path="/proj/Target.ets", content="gap = 8")), record(4, result("w")),
        record(5, {"type": "text", "text": "I read the inputs"}),
        record(6, use("native", "Read", file_path="/proj/other.md")), record(7, result("native", "other content")),
        record(8, use("late", "Bash", command="python delayed_inputs.py")), record(12, result("late", "late data")),
    ], second=[record(1, use("foreign", "Bash", command="python own_inputs.py")), record(2, result("foreign", "foreign"))])
    doc = {"target": {"key": "/proj/Target.ets", "since": ts(9), "at": ts(20)},
        "summary": "Synthetic test only: declared input was loaded by opaque script, output differs.",
        "recommendations": ["Compare received input and output"],
        "nodes": [{"key": "/proj/inputs/layout.md", "at": ts(2), "reason": "Synthetic file interpretation"},
                  {"key": "a.jsonl", "at": ts(4), "reason": "Synthetic deviation", "problem": True}],
        "edges": [{"from": 1, "to": 2}, {"from": 2, "to": "target"}]}
    yield engine, doc
    engine.store.close()


def supplement(doc, evidence=None):
    changed = copy.deepcopy(doc)
    changed["edges"][0].update(force=True, reason="Script resolves the input path dynamically; model-reviewed file effect",
        evidence=evidence if evidence is not None else [{"source": "a.jsonl", "line": 1}, {"source": "a.jsonl", "line": 2}])
    return changed


def test_unknown_file_gets_persisted_actionable_feedback_then_report_local_node(supplemental):
    engine, doc = supplemental
    tables = {table: engine.store.rows("SELECT * FROM " + table) for table in ("files", "effects", "sources")}
    first = check(engine, json.dumps(doc), save=True)
    assert first["mechanical_status"] == "needs_revision"
    assert first["delivery"]["status"] == "draft"
    assert first["issues"][0]["where"] == "nodes[0]"
    assert first["issues"][0]["code"] == "unrecorded_file"
    assert first["unverified_edges"][0]["force_eligible"]
    assert first["unverified_edges"][0]["coordinates"] == {"from": 1, "to": 2}
    final = check(engine, json.dumps(supplement(doc)), save=True)
    assert final["mechanical_status"] == "valid", final
    assert final["path_status"] == "complete"
    assert final["delivery"]["status"] == "ready_for_review"
    missing = next(n for n in final["nodes"] if n["key"] == doc["nodes"][0]["key"])
    assert missing["exists"] is False  # Never relabel a model review as an indexed fact.
    assert missing["existence_basis"] == "model_review" and missing["evidence"]
    assert not missing["semantic_verified"]
    assert final["edges"][0]["source"] == "model_review" and final["edges"][0]["strength"] == "candidate"
    for table, before in tables.items():
        assert engine.store.rows("SELECT * FROM " + table) == before
    for recheck in (False, True):
        loaded = load_report(engine, final["report_id"], recheck=recheck)
        assert loaded["nodes"] == final["nodes"] and loaded["edges"] == final["edges"]
    scope = {"op": "file", "key": missing["key"], "at": missing["at"], "view": "neighbors", "direction": "downstream"}
    assert not engine.query(scope)["rows"]
    rows = engine.query({**scope, "report_id": final["report_id"]})["rows"]
    assert len(rows) == 1 and rows[0]["source"] == "model_review"


def test_first_force_and_other_investigation_cannot_create_nodes(supplemental):
    engine, doc = supplemental
    early = check(engine, json.dumps(supplement(doc)), save=True)
    assert early["unverified_edges"][0]["code"] == "force_before_feedback"
    assert not early["unverified_edges"][0]["force_eligible"]
    check(engine, json.dumps(doc), save=True)
    final = check(engine, json.dumps(supplement(doc)), save=True)
    assert final["mechanical_status"] == "valid"
    assert load_report(engine, early["report_id"])["mechanical_status"] == "needs_revision"
    other = check(Engine(engine.store, session="other"), json.dumps(supplement(doc)))
    assert other["unverified_edges"][0]["code"] == "force_before_feedback"


@pytest.mark.parametrize("fault", ["key", "time", "agent"])
def test_permission_does_not_follow_changed_coordinates(supplemental, fault):
    engine, doc = supplemental
    check(engine, json.dumps(doc), save=True)
    changed = supplement(doc)
    if fault == "key":
        changed["nodes"][0]["key"] = "/proj/inputs/another.md"
    elif fault == "time":
        changed["nodes"][0]["at"] = ts(3)
    else:
        changed["nodes"][1]["key"] = "b.jsonl"
    checked = check(engine, json.dumps(changed))
    assert checked["unverified_edges"][0]["code"] == "force_before_feedback"
    assert checked["delivery"]["status"] == "draft"


@pytest.mark.parametrize("evidence", [
    [{"source": "b.jsonl", "line": 1}],
    [{"source": "a.jsonl", "line": 5}],
    [{"source": "missing.jsonl", "line": 1}],
    [{"source": "a.jsonl", "line": 9999}],
    ["e-invented"],
])
def test_missing_file_still_requires_actual_agent_call(supplemental, evidence):
    engine, doc = supplemental
    check(engine, json.dumps(doc), save=True)
    checked = check(engine, json.dumps(supplement(doc, evidence)))
    assert checked["mechanical_status"] == "needs_revision"
    assert checked["unverified_edges"][0]["code"] == "invalid_force_source"
    assert checked["nodes"][0]["existence_basis"] == "unverified"


@pytest.mark.parametrize("fault", ["unknown-agent", "agent-path", "bare-file", "node-force", "target"])
def test_hard_identity_errors_still_rejected(supplemental, fault):
    engine, doc = supplemental
    if fault == "unknown-agent":
        doc["nodes"][1]["key"] = "unknown.jsonl"
    elif fault == "agent-path":
        doc["nodes"][1]["key"] = "/pool/subagents/unknown.jsonl"
    elif fault == "bare-file":
        doc["nodes"][0]["key"] = "layout.md"
    elif fault == "node-force":
        doc["nodes"][0]["force"] = True
    else:
        doc["target"]["key"] = "/proj/unknown-target.ets"
    with pytest.raises(CardError):
        check(engine, json.dumps(doc), save=True)
    assert not engine.store.rows("SELECT * FROM runs WHERE kind='report'")


def test_no_calls_at_cutoff_no_force_permission(supplemental):
    engine, doc = supplemental
    doc["nodes"][0]["at"] = ts(0)
    first = check(engine, json.dumps(doc), save=True)
    assert not first["unverified_edges"][0]["force_eligible"]
    second = check(engine, json.dumps(supplement(doc)))
    assert second["unverified_edges"][0]["code"] == "force_before_feedback"


def test_native_read_of_different_file_cannot_create_missing_file(supplemental):
    engine, doc = supplemental
    for n in doc["nodes"]:
        n["at"] = ts(7)
    check(engine, json.dumps(doc), save=True)
    checked = check(engine, json.dumps(supplement(doc, [{"source": "a.jsonl", "line": 6}, {"source": "a.jsonl", "line": 7}])))
    assert checked["mechanical_status"] == "needs_revision"
    assert "contradicts" in checked["unverified_edges"][0]["diagnostic"]


def test_pending_opaque_call_cannot_backdate_its_later_return(supplemental):
    engine, doc = supplemental
    for n in doc["nodes"]:
        n["at"] = ts(9)
    check(engine, json.dumps(doc), save=True)
    checked = check(engine, json.dumps(supplement(doc, [{"source": "a.jsonl", "line": 8}])))
    assert checked["mechanical_status"] == "needs_revision"
    assert "completes after" in checked["unverified_edges"][0]["diagnostic"]


def test_unrelated_or_unforced_missing_nodes_remain_invalid(supplemental):
    engine, doc = supplemental
    doc["nodes"].append({"key": "/proj/inputs/unrelated.md", "at": ts(2), "reason": "No declared evidence"})
    check(engine, json.dumps(doc), save=True)
    checked = check(engine, json.dumps(supplement(doc)))
    assert checked["mechanical_status"] == "needs_revision"
    assert any(i["where"] == "nodes[2]" and i["code"] == "unrecorded_file" for i in checked["issues"])


def test_failed_source_recheck_cannot_keep_supplemental_node(supplemental):
    engine, doc = supplemental
    check(engine, json.dumps(doc), save=True)
    final = check(engine, json.dumps(supplement(doc)), save=True)
    from pathlib import Path
    source = Path(engine.store.rows("SELECT path FROM sources WHERE agent='a'")[0]["path"])
    source.write_text(source.read_text(encoding="utf-8").replace("required gap = 4", "tampered payload"), encoding="utf-8")
    loaded = load_report(engine, final["report_id"])
    assert loaded["mechanical_status"] == "needs_revision"
    assert loaded["nodes"][0]["existence_basis"] == "unverified"


def test_unindexed_intermediate_file_requires_both_actual_handoffs(tmp_path):
    engine = build(tmp_path, [
        record(1, use("opaque-write", "Bash", command="python produce_contract.py")), record(2, result("opaque-write")),
    ], second=[
        record(3, use("opaque-read", "Bash", command="python load_contract.py")), record(4, result("opaque-read", "contract")),
        record(5, use("w", file_path="/proj/Target.ets", content="bad")), record(6, result("w")),
    ])
    doc = {"target": {"key": "/proj/Target.ets", "at": ts(10)}, "summary": "Synthetic cross-file path",
        "recommendations": [], "nodes": [
            {"key": "a.jsonl", "at": ts(2), "reason": "Synthetic origin", "problem": True},
            {"key": "/proj/contracts/layout.md", "at": ts(4), "reason": "Synthetic intermediate"},
            {"key": "b.jsonl", "at": ts(6), "reason": "Synthetic consumer"}],
        "edges": [{"from": 1, "to": 2}, {"from": 2, "to": 3}, {"from": 3, "to": "target"}]}
    try:
        first = check(engine, json.dumps(doc), save=True)
        assert len(first["unverified_edges"]) == 2 and all(e["force_eligible"] for e in first["unverified_edges"])
        doc["edges"][0].update(force=True, reason="Script writes this intermediate file", evidence=[{"source": "a.jsonl", "line": 1}])
        partial = check(engine, json.dumps(doc), save=True)
        assert partial["mechanical_status"] == "needs_revision" and len(partial["unverified_edges"]) == 1
        # Accepting the node through one edge cannot certify its other incident edge.
        assert partial["nodes"][1]["existence_basis"] == "model_review"
        doc["edges"][1].update(force=True, reason="Consumer script reads it", evidence=[{"source": "b.jsonl", "line": 1}])
        complete = check(engine, json.dumps(doc), save=True)
        assert complete["mechanical_status"] == "valid" and complete["path_status"] == "complete"
        assert len(complete["edges"]) == 3
        assert not engine.store.rows("SELECT * FROM files WHERE path=?", (doc["nodes"][1]["key"],))
    finally:
        engine.store.close()


def test_renderer_tree_keeps_supplemental_file_and_dashed_origin(supplemental):
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to exercise the browser tree model")
    engine, doc = supplemental
    check(engine, json.dumps(doc), save=True)
    graph = check(engine, json.dumps(supplement(doc)), save=True)
    tree_js = Path(__file__).resolve().parents[1] / "src/migloop/inquiry/tree.js"
    script = """
const fs = require('fs'), {EvidenceTreeModel} = require(process.argv[1]);
const graph = JSON.parse(fs.readFileSync(0, 'utf8'));
const tree = new EvidenceTreeModel(graph.tree.root); tree.seed(graph);
const rows = tree.visible().map(({node:n}) => ({key:n.coordinate.key, row:n.row, claims:n.claims}));
process.stdout.write(JSON.stringify({rows,unclosed:tree.unclosed}));
"""
    result = subprocess.run([node, "-e", script, str(tree_js)], input=json.dumps(graph), text=True,
                            encoding="utf-8", capture_output=True, check=True, timeout=30)
    rendered = json.loads(result.stdout)
    assert not rendered["unclosed"]
    file, = [r for r in rendered["rows"] if r["key"] == doc["nodes"][0]["key"]]
    assert file["row"]["source"] == "model_review" and file["row"]["strength"] == "candidate"
    assert any(n.get("existence_basis") == "model_review" and not n["exists"] for n in file["claims"])


def test_codex_tool_call_output_supports_the_same_missing_file_flow(tmp_path):
    rows = [
        {"timestamp": ts(1), "type": "response_item", "payload": {"type": "function_call", "call_id": "r",
            "name": "exec_command", "arguments": json.dumps({"cmd": "python load_inputs.py"})}},
        {"timestamp": ts(2), "type": "response_item", "payload": {"type": "function_call_output", "call_id": "r", "output": "required gap = 4", "exit_code": 0}},
        {"timestamp": ts(3), "type": "response_item", "payload": {"type": "function_call", "call_id": "w",
            "name": "Write", "arguments": json.dumps({"file_path": "/proj/Target.ets", "content": "gap = 8"})}},
        {"timestamp": ts(4), "type": "response_item", "payload": {"type": "function_call_output", "call_id": "w", "output": "ok", "exit_code": 0}},
    ]
    engine = build(tmp_path, rows)
    doc = {"target": {"key": "/proj/Target.ets", "at": ts(10)}, "summary": "Synthetic Codex case",
           "recommendations": [], "nodes": [
               {"key": "/proj/inputs/layout.md", "at": ts(2), "reason": "Script input"},
               {"key": "a.jsonl", "at": ts(4), "reason": "Output deviation", "problem": True}],
           "edges": [{"from": 1, "to": 2}, {"from": 2, "to": "target"}]}
    try:
        first = check(engine, json.dumps(doc), save=True)
        assert first["unverified_edges"][0]["force_eligible"]
        final = check(engine, json.dumps(supplement(doc)), save=True)
        assert final["delivery"]["status"] == "ready_for_review"
        assert final["nodes"][0]["existence_basis"] == "model_review" and not final["nodes"][0]["exists"]
    finally:
        engine.store.close()
