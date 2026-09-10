"""Paired scoring and provenance checks; no model calls or semantic judging."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "docs/experiments/file-first-10/score_tools10.py"
spec = importlib.util.spec_from_file_location("tools10_score_tests", SCRIPT)
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path):
    raw, tools, grades = (tmp_path / name for name in ("baseline-v1", "tools-v1", "tools-grades"))
    core = raw / "private/scoring-core.json"
    write(core, {"units": {"F/unit": "frozen core"}})
    common = {"cases": [{"id": "F", "file": "File.ets", "pool": str(tmp_path / "pool")}],
              "repetitions": 1, "model": "gpt-5.6-luna", "effort": "medium", "concurrency": 2, "timeout_seconds": 1800}
    write(raw / "manifest.json", {**common, "schema": "migloop-file-first-raw10-baseline/1",
          "status": "frozen_ready_for_raw", "artifacts": [{"path": "private/scoring-core.json", "sha256": score.sha(core)}]})
    write(tools / "manifest.json", {**common, "schema": "migloop-file-first-tools10-baseline/1",
          "status": "frozen_ready_for_tools", "raw_base": str(raw), "raw_manifest_sha256": score.sha(raw / "manifest.json"),
          "code_digest": "frozen-code-digest", "prepare_elapsed_seconds": 4.5})
    for base in (raw, tools):
        report = base / "runs/F/rep1/report.md"
        report.parent.mkdir(parents=True)
        report.write_text("Correct reason. More evidence is unknown.", encoding="utf-8")
    grade = {"report_sha256": score.sha(report), "core_contract_sha256": score.sha(core),
             "units": [{"id": "unit", "outcome": "correct", "reason": "Frozen source supports the core",
                        "report_spans": ["Correct reason."], "evidence": ["source.jsonl:1"]}],
             "claims": [{"id": "c1", "outcome": "supported", "reason": "Supported cause",
                         "report_spans": ["Correct reason."], "evidence": ["source.jsonl:1"], "major_error": False}]}
    return raw, tools, grades, grade


def verdict(tools, *, valid=True):
    body = {"schema": "migloop-tools10-final-verification/1", "found": valid,
            "data": {"schema": "migloop-verdict/3"} if valid else None,
            "errors": [] if valid else ["Missing final document"],
            "report_sha256": score.sha(tools / "runs/F/rep1/report.md"), "semantic_checked": False,
            "verification": {"identity": {"bound": valid}, "diagnostics": [],
                             "argument_graph": {"nodes": [], "edges": []}}}
    write(tools / "runs/F/rep1/verdict.json", body)
    return body


@pytest.mark.parametrize("outcome", ["correct", "partial", "missing", "wrong"])
@pytest.mark.parametrize("claim", ["supported", "contradicted", "unsupported_asserted_as_fact", "explicitly_hypothetical"])
def test_identical_semantics_for_each_unit_and_claim_outcome(tmp_path, outcome, claim):
    raw, tools, grades, grade = fixture(tmp_path)
    grade["units"][0]["outcome"] = outcome
    grade["claims"][0].update(outcome=claim, major_error=claim in ("contradicted", "unsupported_asserted_as_fact"))
    write(grades / "F/rep1.json", grade)
    tools_result = score.summarize(tools, grades)
    raw_result = score.RAW.summarize(raw, grades)
    assert tools_result["runs"][0]["grade"] == raw_result["runs"][0]["grade"]
    assert tools_result["aggregate"] == raw_result["aggregate"]


def test_pending_is_not_zero_even_when_mechanical_checks_pass(tmp_path):
    _, tools, grades, _ = fixture(tmp_path)
    verdict(tools)
    write(tools / "runs/F/rep1/metrics.json", {"status": "completed"})
    result = score.summarize(tools, grades)
    assert result["aggregate"] is None and result["semantic_totals"] is None
    assert result["runs_adjudicated"] == 0 and result["runs"][0]["grade"] is None
    assert result["mechanical"]["document_checks_passed"] == 1


def test_bad_format_is_independent_from_correct_semantic_grade(tmp_path):
    _, tools, grades, grade = fixture(tmp_path)
    verdict(tools, valid=False)
    write(grades / "F/rep1.json", grade)
    result = score.summarize(tools, grades)
    assert result["mechanical"]["document_checks_passed"] == 0
    assert result["aggregate"]["file_run_pass_rate"] == 1
    assert result["semantic_totals"]["unit_weighted_correct_attribution_coverage"] == 1


@pytest.mark.parametrize("field,value,match", [
    ("core_contract_sha256", "another-rubric", "different scoring contract"),
    ("report_sha256", "another-report", "report missing or changed"),
    ("report_spans", ["The final report did not say this."], "not present")])
def test_rejects_wrong_rubric_report_and_quote(tmp_path, field, value, match):
    _, tools, grades, grade = fixture(tmp_path)
    if field == "report_spans":
        grade["units"][0][field] = value
    else:
        grade[field] = value
    write(grades / "F/rep1.json", grade)
    with pytest.raises(ValueError, match=match):
        score.summarize(tools, grades)


def test_tools_local_contract_cannot_replace_raw_contract(tmp_path):
    _, tools, grades, grade = fixture(tmp_path)
    local = tools / "private/scoring-core.json"
    write(local, {"units": {"F/unit": "different easier rubric"}})
    grade["core_contract_sha256"] = score.sha(local)
    write(grades / "F/rep1.json", grade)
    with pytest.raises(ValueError, match="different scoring contract"):
        score.summarize(tools, grades)


@pytest.mark.parametrize("mutation", ["raw_manifest", "core", "dev", "case", "setting", "raw_binding"])
def test_rejects_changed_frozen_bindings(tmp_path, mutation):
    raw, tools, grades, _ = fixture(tmp_path)
    manifest = score.read(tools / "manifest.json")
    if mutation == "raw_manifest":
        write(raw / "manifest.json", {**score.read(raw / "manifest.json"), "changed": True})
    elif mutation == "core":
        write(raw / "private/scoring-core.json", {"units": {"F/unit": "changed"}})
    else:
        if mutation == "dev":
            manifest["status"] = "frozen_dev_smoke_only"
        elif mutation == "case":
            manifest["cases"][0]["file"] = "Different.ets"
        elif mutation == "setting":
            manifest["effort"] = "high"
        else:
            manifest["raw_manifest_sha256"] = "wrong"
        write(tools / "manifest.json", manifest)
    with pytest.raises(ValueError):
        score.summarize(tools, grades)


def test_frozen_core_artifact_must_be_unique(tmp_path):
    raw, tools, grades, _ = fixture(tmp_path)
    manifest = score.read(raw / "manifest.json")
    manifest["artifacts"] *= 2
    write(raw / "manifest.json", manifest)
    write(tools / "manifest.json", {**score.read(tools / "manifest.json"), "raw_manifest_sha256": score.sha(raw / "manifest.json")})
    with pytest.raises(ValueError, match="uniquely registered"):
        score.summarize(tools, grades)


def test_contract_base_is_keyword_only(tmp_path):
    raw, tools, grades, grade = fixture(tmp_path)
    with pytest.raises(TypeError):
        score.RAW.validate_grade(tools, "F", 1, grade, raw)
    with pytest.raises(TypeError):
        score.RAW.summarize(tools, grades, raw)


def test_terminal_no_answer_uses_same_raw_rule_and_original_contract(tmp_path):
    raw, tools, grades, _ = fixture(tmp_path)
    for base in (raw, tools):
        (base / "runs/F/rep1/report.md").unlink()
        write(base / "runs/F/rep1/metrics.json", {"status": "timeout"})
    result = score.summarize(tools, grades)
    assert result["runs"][0]["grade"] == score.RAW.summarize(raw, grades)["runs"][0]["grade"]
    assert result["semantic_totals"]["missing"] == 1
    assert result["semantic_totals"]["wrong"] == 0


def test_token_costs_and_three_timings_are_separate(tmp_path):
    _, tools, grades, _ = fixture(tmp_path)
    write(tools / "runs/F/rep1/metrics.json", {"status": "completed",
          "usage": {"input_total": 100, "cache_read": 80, "output": 20},
          "elapsed_seconds": 9, "investigator_elapsed_seconds": 9, "system_elapsed_seconds": 12,
          "postprocess": {"status": "completed", "elapsed_seconds": 2}})
    costs = score.summarize(tools, grades)["costs"]
    for field, expected in (("input_tokens", 100), ("cache_read_tokens", 80), ("uncached_input_tokens", 20),
                            ("output_tokens", 20), ("tokens_total", 120), ("investigator_elapsed_seconds", 9),
                            ("system_elapsed_seconds", 12), ("postprocess_elapsed_seconds", 2)):
        assert costs[field]["sum"] == expected and costs[field]["complete"]
    assert costs["prepare_elapsed_seconds"] == 4.5


def test_missing_costs_are_not_imputed_zero_or_legacy_time(tmp_path):
    _, tools, grades, _ = fixture(tmp_path)
    write(tools / "runs/F/rep1/metrics.json", {"status": "completed", "elapsed_seconds": 9, "usage": {"input_total": 100}})
    costs = score.summarize(tools, grades)["costs"]
    for field in ("cache_read_tokens", "tokens_total", "output_tokens", "investigator_elapsed_seconds", "system_elapsed_seconds"):
        assert costs[field]["sum"] is None
        assert costs[field]["observed_runs"] == 0 and not costs[field]["complete"]


def test_verifier_failure_is_unobserved_not_pass_or_fail(tmp_path):
    _, tools, grades, _ = fixture(tmp_path)
    write(tools / "runs/F/rep1/verdict.json", {"schema": "migloop-tools10-final-verification/1",
          "data": None, "errors": ["Frozen verifier failed"], "semantic_checked": False})
    result = score.summarize(tools, grades)
    assert result["mechanical"]["runs_with_verdict"] == 1
    assert result["mechanical"]["document_checks_observed"] == 0
    assert result["runs"][0]["mechanical"]["document_checks_pass"] is None


def test_reference_occurrences_not_double_counted_via_findings(tmp_path):
    _, tools, grades, _ = fixture(tmp_path)
    body = verdict(tools)
    node = {"evidence": [{"ref": "r1", "status": "ok"}], "counterevidence": [{"ref": "r2", "status": "undated"}]}
    edge = {"evidence": [{"ref": "r1", "status": "ok"}, {"ref": "r3", "status": "outside_scope"}]}
    body["verification"]["argument_graph"].update(nodes=[node], edges=[edge], findings=[{"nodes": [node], "edges": [edge]}])
    body["verification"]["findings"] = copy.deepcopy(body["verification"]["argument_graph"]["findings"])
    write(tools / "runs/F/rep1/verdict.json", body)
    result = score.summarize(tools, grades)
    assert result["mechanical"]["reference_occurrences"] == 4
    assert result["mechanical"]["reference_status_counts"] == {"ok": 2, "outside_scope": 1, "undated": 1}
    assert result["aggregate"] is None


@pytest.mark.parametrize("mutation", ["report", "verdict", "missing_verdict", "provenance"])
def test_rejects_stale_run_diagnostics_or_provenance(tmp_path, mutation):
    _, tools, grades, _ = fixture(tmp_path)
    body = verdict(tools)
    path = tools / "runs/F/rep1/verdict.json"
    metric = {"postprocess": {"verdict_sha256": score.sha(path)}}
    if mutation == "report":
        (tools / "runs/F/rep1/report.md").write_text("Changed final report", encoding="utf-8")
    elif mutation == "verdict":
        write(path, {**body, "errors": ["Changed diagnostics"]})
    elif mutation == "missing_verdict":
        path.unlink()
    else:
        metric["tools_manifest_sha256"] = "different-run-binding"
    write(tools / "runs/F/rep1/metrics.json", metric)
    with pytest.raises(ValueError):
        score.summarize(tools, grades)


def test_cli_only_creates_new_output_and_never_overwrites(tmp_path, capsys):
    _, tools, grades, _ = fixture(tmp_path)
    out = tmp_path / "new-tools-scores.json"
    args = ["--baseline", str(tools), "--grades", str(grades), "--out", str(out)]
    score.main(args)
    before = out.read_bytes()
    assert score.read(out)["aggregate"] is None
    with pytest.raises(FileExistsError):
        score.main(args)
    assert out.read_bytes() == before
    capsys.readouterr()
