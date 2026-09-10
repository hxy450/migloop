"""Numeric aggregation safeguards; no semantic model judging."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/"docs/experiments/file-first-10/score_raw10.py"
spec = importlib.util.spec_from_file_location("raw10_score_tests", SCRIPT)
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path, report="Correct reason. More evidence is unknown."):
    write(tmp_path/"private/scoring-core.json", {"units":{"F/unit":"core"}})
    write(tmp_path/"manifest.json", {"cases":[{"id":"F","file":"File.ets"}],"repetitions":1})
    target = tmp_path/"runs/F/rep1/report.md"
    target.parent.mkdir(parents=True)
    target.write_text(report, encoding="utf-8")
    grade = {"report_sha256":score.sha(target),"core_contract_sha256":score.sha(tmp_path/"private/scoring-core.json"),
        "units":[{"id":"unit","outcome":"correct","reason":"Source supports the core", "report_spans":["Correct reason."],"evidence":["source.jsonl:1"]}],
        "claims":[{"id":"c1","outcome":"supported","reason":"Supported cause", "report_spans":["Correct reason."],"evidence":["source.jsonl:1"],"major_error":False}]}
    return grade


def test_missing_adjudication_is_pending_not_zero(tmp_path):
    fixture(tmp_path)
    result = score.summarize(tmp_path, tmp_path/"grades")
    assert result["aggregate"] is None
    assert result["runs_adjudicated"] == 0


def test_cache_not_added_twice_and_correct_score(tmp_path):
    grade = fixture(tmp_path)
    write(tmp_path/"grades/F/rep1.json", grade)
    write(tmp_path/"runs/F/rep1/metrics.json", {"status":"completed","usage":{"input_total":100,"cache_read":80,"output":20}})
    result = score.summarize(tmp_path, tmp_path/"grades")
    assert result["runs"][0]["tokens_total"] == 120
    assert result["aggregate"]["file_macro_correct_attribution_coverage"] == 1


def test_exact_report_and_contract_required(tmp_path):
    grade = fixture(tmp_path)
    grade["report_sha256"] = "invented"
    with pytest.raises(ValueError, match="report"):
        score.validate_grade(tmp_path, "F", 1, grade)


def test_fabricated_quoted_span_fails(tmp_path):
    grade = fixture(tmp_path)
    grade["units"][0]["report_spans"] = ["The report never said this."]
    with pytest.raises(ValueError, match="not present"):
        score.validate_grade(tmp_path, "F", 1, grade)


def test_partial_is_not_major_false_claim(tmp_path):
    grade = fixture(tmp_path)
    grade["units"][0]["outcome"] = "partial"
    result = score.validate_grade(tmp_path, "F", 1, grade)
    assert result["correct_attribution_coverage"] == 0
    assert result["attribution_precision"] == 1
    assert result["major_errors"] == 0
    assert result["partial"] == 1


def test_no_claims_does_not_get_perfect_precision(tmp_path):
    grade = fixture(tmp_path)
    grade["claims"] = []
    assert score.validate_grade(tmp_path, "F", 1, grade)["attribution_precision"] is None


def test_hypothesis_not_counted_as_proven_or_false_fact(tmp_path):
    grade = fixture(tmp_path)
    grade["claims"][0]["outcome"] = "explicitly_hypothetical"
    result = score.validate_grade(tmp_path, "F", 1, grade)
    assert result["asserted_claims"] == 0
    assert result["attribution_precision"] is None


def test_major_error_cannot_be_omission_without_source_basis(tmp_path):
    grade = fixture(tmp_path)
    grade["claims"][0].update(major_error=True, outcome="unsupported_asserted_as_fact", evidence=[])
    with pytest.raises(ValueError, match="Major error"):
        score.validate_grade(tmp_path, "F", 1, grade)


def test_terminal_no_answer_counts_as_undelivered_not_wrong(tmp_path):
    write(tmp_path/"private/scoring-core.json", {"units":{"F/unit":"core"}})
    write(tmp_path/"manifest.json", {"cases":[{"id":"F","file":"File.ets"}],"repetitions":1})
    write(tmp_path/"runs/F/rep1/metrics.json", {"status":"timeout"})
    result = score.summarize(tmp_path, tmp_path/"grades")
    assert result["aggregate"]["file_macro_correct_attribution_coverage"] == 0
    assert result["aggregate"]["attribution_precision"] is None
    assert result["runs"][0]["grade"]["wrong"] == 0
