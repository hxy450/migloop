"""Offline integrity tests for the file-first experiment (no paid model calls)."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import subprocess

import pytest


EXPERIMENT = Path(__file__).resolve().parents[1] / "docs/experiments/file-first-luna"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, EXPERIMENT / file)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


inventory = load("file_first_inventory_tests", "inspect_pool.py")
prepare = load("file_first_prepare_tests", "prepare_baseline.py")


def rows(path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def use(identity, name="Read", **inputs):
    return {"timestamp":"2026-01-01T10:00:00Z", "message":{"role":"assistant", "content":[
        {"type":"tool_use", "id":identity, "name":name, "input":inputs}]}}


def result(identity, value="observed", error=False):
    return {"timestamp":"2026-01-01T10:00:01Z", "message":{"role":"user", "content":[
        {"type":"tool_result", "tool_use_id":identity, "content":value, "is_error":error}]}}


def test_pairing_never_crosses_transcript(tmp_path):
    rows(tmp_path / "one.jsonl", use("same", file_path="/x/Target.ets"))
    rows(tmp_path / "two.jsonl", result("same"))
    data = inventory.scan(tmp_path, "Target.ets")
    assert data["target_calls"][0]["pairing"] == "missing"


def test_ambiguous_returns_are_not_chosen(tmp_path):
    rows(tmp_path / "one.jsonl", use("a", file_path="/x/Target.ets"), result("a"), result("a"))
    data = inventory.scan(tmp_path, "Target.ets")
    assert data["target_calls"][0]["pairing"] == "ambiguous"


def test_failure_and_partial_effect_not_dropped(tmp_path):
    rows(tmp_path / "one.jsonl", use("a", "Bash", command="cp x Target.ets && false"), result("a", "failed", True))
    call = inventory.scan(tmp_path, "Target.ets")["target_calls"][0]
    assert call["results"][0]["is_error"]
    assert "effect" not in call


def test_report_mention_not_invented_as_target_write(tmp_path):
    rows(tmp_path / "one.jsonl", use("a", "Write", file_path="/x/report.md", content="Target.ets needs repair"), result("a"))
    call = inventory.scan(tmp_path, "Target.ets")["target_calls"][0]
    assert call["input"]["file_path"] == "/x/report.md"
    assert "author" not in call


def test_nonliteral_script_preserved_as_gap(tmp_path):
    rows(tmp_path / "one.jsonl", use("a", "Bash", command="python -c 'p.write_text(s)'"), result("a", "Target.ets: 1 site"))
    data = inventory.scan(tmp_path, "Target.ets")
    assert not data["target_calls"]
    assert len(data["unresolved_write_capability"]) == 1
    assert len(data["other_mentions"]) == 1


def test_scan_preserves_input_bytes_and_hash(tmp_path):
    path = tmp_path / "one.jsonl"
    rows(path, use("a", file_path="/x/Target.ets"), result("a", "中文"))
    before = path.read_bytes()
    data = inventory.scan(tmp_path, "Target.ets")
    assert path.read_bytes() == before
    assert data["source_files"][0]["sha256"] == hashlib.sha256(before).hexdigest()


@pytest.mark.parametrize("relative,line", [("../outside.jsonl", 1), ("one.jsonl", 0), ("one.jsonl", 20)])
def test_original_record_rejects_escape_zero_and_missing(tmp_path, relative, line):
    rows(tmp_path / "one.jsonl", result("a"))
    with pytest.raises(ValueError):
        prepare.original(tmp_path, relative, line)


def test_reference_witness_drift_fails(tmp_path):
    rows(tmp_path / "one.jsonl", result("a", "real"))
    entry = {"id":"x", "file":"one.jsonl", "line":1, "record_sha256":"forged"}
    with pytest.raises(ValueError, match="drift"):
        prepare.verify_legacy(tmp_path, entry)


def test_reference_quote_drift_fails_even_with_valid_location(tmp_path):
    rows(tmp_path / "one.jsonl", result("a", "real"))
    entry = {**prepare.witness(tmp_path, "one.jsonl", 1), "id":"x", "selector":["message","content",0,"content"],
             "excerpts":[{"start_char":0,"text":"invented"}]}
    with pytest.raises(ValueError, match="excerpt drift"):
        prepare.verify_legacy(tmp_path, entry)


def test_no_answer_labels_in_generic_task_template():
    template = (EXPERIMENT / "task-template.md").read_text(encoding="utf-8").split("---\n",1)[1]
    spec = json.loads((EXPERIMENT / "reference-spec.json").read_text(encoding="utf-8"))
    assert len(spec["cases"]) == 3
    assert sum(len(c["issues"]) for c in spec["cases"]) == 18
    for case in spec["cases"]:
        assert case["id"] not in template
        assert case["target_file"] not in template
        for issue in case["issues"]:
            assert issue["title"] not in template
            assert len(issue["required"]) == 3
            assert issue["changes"]


def test_artifact_writer_refuses_overwrite(tmp_path):
    target = tmp_path / "reference.json"
    prepare.write(target, {"original":True})
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        prepare.write(target, {"original":False})
    assert target.read_bytes() == before


def summary_fixture(tmp_path):
    ref = {"cases":[{"case":"example","issues":[{"id":"A","required":["fact"]}]}]}
    prepare.write(tmp_path / "reference.json", ref)
    reference_hash = prepare.digest(tmp_path / "reference.json")
    prepare.write(tmp_path / "baseline.json", {"reference_sha256":reference_hash})
    return reference_hash


def summary_cli(tmp_path, *extra):
    return subprocess.run([sys.executable,"-X","utf8",str(EXPERIMENT / "summarize_baseline.py"),
                           "--baseline",str(tmp_path),*extra],capture_output=True,text=True,encoding="utf-8")


def test_summary_missing_runs_do_not_become_zero_cost(tmp_path):
    summary_fixture(tmp_path)
    out = tmp_path / "out.json"
    result = summary_cli(tmp_path,"--out",str(out))
    assert result.returncode == 0, result.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert not data["all_runs_completed"]
    assert not data["paired_cost"]
    assert all(r["tokens_total"] is None for r in data["runs"])


def test_summary_cached_tokens_are_not_added_twice(tmp_path):
    summary_fixture(tmp_path)
    for arm, total in [("raw",100),("tools",50)]:
        dest = tmp_path / "example/runs" / arm / "rep1"
        dest.mkdir(parents=True)
        prepare.write(dest/"metrics.json", {"status":"completed","end_to_end_wall_s":10,
            "usage":{"input_total":total,"cache_read":40,"output":10}})
    result = summary_cli(tmp_path)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["paired_cost"][0]["token_saving"] == pytest.approx(1-60/110)
    assert data["paired_cost"][0]["quality_equivalence_established"] is False


def test_summary_rejects_grading_unfinished_report(tmp_path):
    h = summary_fixture(tmp_path)
    grade = {"reference_sha256":h,"runs":[{"case":"example","arm":"raw","rep":1,"issues":[]}]}
    prepare.write(tmp_path/"grades.json",grade)
    result = summary_cli(tmp_path,"--grades",str(tmp_path/"grades.json"))
    assert result.returncode != 0
    assert "unfinished" in result.stderr
