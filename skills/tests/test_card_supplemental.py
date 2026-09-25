"""End-to-end card pack preserves a reviewed missing input without indexing it."""
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "migloop-memory-maintain/scripts"
sys.path.insert(0, str(SCRIPTS))
from memorylib.cases import dispatch, pack
from memorylib.common import load, write_new
from memorylib.provenance import collect
from migloop.inquiry.store import Store, describe_source
from tests.test_inquiry_core import record, result, ts, use


def test_pack_retains_report_local_existence_basis(tmp_path):
    pool = tmp_path / "pool"
    pool.mkdir()
    source = pool / "writer.jsonl"
    rows = [record(1, use("r", "Bash", command="python inputs.py")), record(2, result("r", "good")),
            record(3, use("w", file_path="/app/Page.ets", content="bad")), record(4, result("w"))]
    for row in rows:
        row.update(sessionId="test-session", agentId="writer", cwd="/app")
    source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    metadata = tmp_path / "metadata.json"
    write_new(metadata, collect(pool))
    tasks = {"schema": "migloop-repair-triage/1", "scope": {"materials": [str(pool)], "project_roots": ["/app"],
             "generation_end": ts(5), "observation_end": ts(10)}, "issues": [{"title": "Synthetic test",
             "changes": [{"files": ["Page.ets"], "change": "Synthetic change", "evidence": ["writer.jsonl:L3"]}]}]}
    write_new(tmp_path / "tasks.json", tasks)
    dispatch(tmp_path / "tasks.json", metadata, tmp_path / "jobs")
    job = load(tmp_path / "jobs/jobs.json")["jobs"][0]["job"]
    db = tmp_path / "index.sqlite"
    Store.build(db, [describe_source(source, "writer.jsonl")]).close()
    draft = {"title": "Synthetic test", "when": "Implementation", "description": "Opaque script input", "summary": "Synthetic input/output discrepancy",
             "recommendations": ["Compare inputs"], "graphs": [{
             "target": {"key": "/app/Page.ets", "since": ts(5), "at": ts(10)}, "nodes": [
             {"key": "/app/inputs/spec.md", "at": ts(2), "reason": "Script input"},
             {"key": "writer.jsonl", "at": ts(4), "reason": "Output differs", "problem": True}],
             "edges": [{"from": 1, "to": 2}, {"from": 2, "to": "target"}]}]}
    write_new(tmp_path / "first.json", draft)
    first = pack(job, tmp_path / "first.json", tmp_path / "case-first.json", db)
    assert first["graph_checks"][0]["receipt"]["unverified_edges"][0]["force_eligible"]
    assert first["card"] is None and not (tmp_path / "case-first.json").exists()
    draft["graphs"][0]["edges"][0].update(force=True, reason="Opaque script reads this input",
                evidence=[{"source": "writer.jsonl", "line": 1}, {"source": "writer.jsonl", "line": 2}])
    write_new(tmp_path / "final.json", draft)
    final = pack(job, tmp_path / "final.json", tmp_path / "case-final.json", db)
    assert final["validation"]["graph_checks"][0]["receipt"]["delivery"]["status"] == "ready_for_review"
    card = load(tmp_path / "case-final.json")
    assert card["draft"] == draft
    declared, = [n for n in card["graph_evidence"][0]["nodes"] if n["key"] == "/app/inputs/spec.md"]
    assert declared["existence_basis"] == "model_review"
    assert load(tmp_path / "case-final.views/target-1.json")["edges"] == draft["graphs"][0]["edges"]
    store = Store(db)
    try:
        assert not store.rows("SELECT * FROM files WHERE path=?", (declared["key"],))
    finally:
        store.close()
