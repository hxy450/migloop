"""Only synthetic case/metrics fixtures; never load an investigation or oracle."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "docs/experiments/2026-09-09-attribution10/compare_suite.py"
spec = importlib.util.spec_from_file_location("compare_suite", SCRIPT)
assert spec and spec.loader
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def fixture(tmp_path, costs=None):
    costs = costs or {"A": {"raw": [100, 100], "tools": [50, 50]},
                      "B": {"raw": [1000, 1000], "tools": [900, 900]}}
    plan = {"schema": "migloop-paired-metrics-plan/1", "expected": {
        "backend": "codex", "model": "model-test", "effort": "medium"}, "cases": []}
    for i, (name, arms) in enumerate(costs.items()):
        cases = {arm: tmp_path / name / arm for arm in ("tools", "raw")}
        plan["cases"].append({"id": name, "tools_case": str(cases["tools"]), "raw_case": str(cases["raw"]), "reps": [1, 2]})
        for arm, directory in cases.items():
            case = {"schema": "migloop-pair-case/1", "case": name, "file": f"{name}.ets",
                    "common_task_sha256": str(i + 1) * 64, "pool_digest": "a" * 64,
                    "source": str(tmp_path / (arm + "-source")), "source_code_id": arm + "-code", "source_digest": ("b" if arm == "raw" else "c") * 64}
            dump(directory / "case.json", case)
            for rep, total in enumerate(arms[arm], 1):
                m = {"case": name, "arm": arm, "rep": rep, "status": "completed", "recording_complete": True,
                     "backend": "codex", "model_requested": "model-test", "effort": "medium", "actual_models": ["model-test"],
                     "actual_model_source": "transcript.turn_context", "actual_effort": "medium", "actual_efforts": ["medium"],
                     "actual_effort_source": "transcript.turn_context", "final_mode": "reference" if arm == "tools" else "document",
                     "runner_sha256": "d" * 64, "usage": {"input_total": total - 10, "output": 10,
                        "input_uncached": total - 30, "cache_read": 20, "cache_creation": 7, "thinking_reported": 9},
                     "wall_s": 10, "end_to_end_wall_s": 12,
                     "transcript": {"tool_calls": 3, "wrapper_count": 1, "pending_calls": 0, "malformed_lines": [],
                                    "unmatched_result_ids": [], "seq": [{"input": "DO_NOT_COPY_SENSITIVE_CONTENT"}]},
                     "integrity_before": {"pool_unchanged": True, "source_unchanged": True, "task_unchanged": True},
                     "integrity_after": {"pool_unchanged": True, "source_unchanged": True, "task_unchanged": True}}
                m.update({key: case[key] for key in ("common_task_sha256", "pool_digest", "source", "source_code_id", "source_digest")})
                dump(directory / "runs" / arm / f"rep{rep}" / "metrics.json", m)
    path = tmp_path / "plan.json"
    dump(path, plan)
    return path, plan


def metric_path(plan, case="A", arm="tools", rep=1):
    row = next(c for c in plan["cases"] if c["id"] == case)
    return Path(row[arm + "_case"]) / "runs" / arm / f"rep{rep}" / "metrics.json"


def mutate(path, update):
    value = json.loads(path.read_text(encoding="utf-8"))
    update(value)
    dump(path, value)


def test_primary_counts_cache_reasoning_once_and_reports_both_weightings(tmp_path):
    path, _ = fixture(tmp_path)
    report = compare.compare_plan(path)
    assert report["complete_summary"] is True and report["semantics_scored"] is False
    assert len(report["runs"]) == 8
    formal = report["formal_summary"]
    assert formal["pooled"]["raw_tokens"] == 2200 and formal["pooled"]["tools_tokens"] == 1900
    assert formal["pooled"]["savings_fraction"] == pytest.approx(300 / 2200)
    assert formal["case_macro"]["savings_fraction"] == pytest.approx(.3)
    assert report["cases"][0]["arms"]["tools"]["mean"]["primary_tokens"] == 50
    assert report["runs"][0]["observed"]["thinking_reported"] == 9
    assert report["runs"][0]["observed"]["cache_creation"] == 7
    assert "DO_NOT_COPY_SENSITIVE_CONTENT" not in json.dumps(report)
    assert report["cases"][0]["comparable"] is True  # raw/document vs tools/reference and source differences allowed


@pytest.mark.parametrize("state", ["missing", "starting", "timeout", "cli_error", "malformed", "recording_false", "pending", "parse_error", "usage_missing"])
def test_incomplete_plan_never_silently_drops_a_run_or_fills_zero(tmp_path, state):
    path, plan = fixture(tmp_path)
    target = metric_path(plan, rep=2)
    if state == "missing": target.unlink()
    elif state == "malformed": target.write_text("{broken", encoding="utf-8")
    else:
        def alter(m):
            if state in ("starting", "timeout", "cli_error"): m["status"] = state
            elif state == "recording_false": m["recording_complete"] = False
            elif state == "pending": m["transcript"]["pending_calls"] = 1
            elif state == "parse_error": m["transcript"]["malformed_lines"] = [9]
            else: m["usage"].pop("output")
        mutate(target, alter)
    report = compare.compare_plan(path)
    assert report["complete_summary"] is False and report["formal_summary"] is None
    assert len(report["runs"]) == 8
    run = next(r for r in report["runs"] if r["case_id"] == "A" and r["arm"] == "tools" and r["rep"] == 2)
    assert run["primary_tokens"] is None and run["diagnostics"]
    assert report["cases"][0]["arms"]["tools"]["mean"]["primary_tokens"] is None
    assert report["cases"][0]["savings_fraction"] is None
    partial = report["partial_descriptive"]
    assert partial["formal_comparison"] is False and partial["savings_fraction"] is None
    if state in ("timeout", "cli_error"):
        assert run["observed"]["primary_tokens"] == 50


@pytest.mark.parametrize("field,value", [("pool_digest", "e" * 64), ("common_task_sha256", "e" * 64),
    ("actual_models", ["different"]), ("model_requested", "different"), ("backend", "different"),
    ("actual_effort", "high"), ("effort", "high"), ("models_reported_by_context", ["different"]),
    ("arm", "raw"), ("rep", 99)])
def test_mismatched_or_wrong_run_metadata_blocks_formal_summary(tmp_path, field, value):
    path, plan = fixture(tmp_path)
    mutate(metric_path(plan), lambda m: m.update({field: value}))
    report = compare.compare_plan(path)
    assert not report["complete_summary"] and report["formal_summary"] is None


def test_both_arms_drifting_together_is_rejected_against_predefined_parameters(tmp_path):
    path, plan = fixture(tmp_path)
    for arm in ("tools", "raw"):
        for rep in (1, 2):
            mutate(metric_path(plan, arm=arm, rep=rep), lambda m: m.update(model_requested="other", actual_models=["other"]))
    assert not compare.compare_plan(path)["complete_summary"]


def test_case_task_or_pool_mismatch_is_not_hidden_by_consistent_run_summaries(tmp_path):
    path, plan = fixture(tmp_path)
    raw = Path(plan["cases"][0]["raw_case"])
    mutate(raw / "case.json", lambda c: c.update(common_task_sha256="f" * 64))
    for rep in (1, 2): mutate(metric_path(plan, arm="raw", rep=rep), lambda m: m.update(common_task_sha256="f" * 64))
    got = compare.compare_plan(path)
    assert not got["complete_summary"] and not got["cases"][0]["comparable"]


def test_missing_auxiliary_usage_and_wall_are_null_but_primary_can_be_complete(tmp_path):
    path, plan = fixture(tmp_path)
    def alter(m):
        m["usage"].pop("input_uncached"); m.pop("wall_s")
        # Missing parser counters are not interpreted as zero or as known errors.
        m["transcript"].pop("pending_calls"); m["transcript"].pop("malformed_lines")
    mutate(metric_path(plan), alter)
    report = compare.compare_plan(path)
    assert report["complete_summary"]
    mean = report["cases"][0]["arms"]["tools"]["mean"]
    assert mean["input_uncached"] is None and mean["wall_s"] is None
    assert report["runs"][0]["recording"]["pending_calls"] is None
    assert report["runs"][0]["diagnostics"]


def test_missing_actual_parameters_do_not_fall_back_to_requested(tmp_path):
    path, plan = fixture(tmp_path)
    mutate(metric_path(plan), lambda m: [m.pop(k, None) for k in ("actual_effort", "actual_efforts")])
    assert not compare.compare_plan(path)["complete_summary"]


@pytest.mark.parametrize("field,value", [("actual_models", ["model-test", None]),
    ("actual_effort", {"input": "DO_NOT_COPY_SENSITIVE_CONTENT"}),
    ("event_errors", [{"message": "DO_NOT_COPY_SENSITIVE_CONTENT"}]),
    ("result_is_error", True), ("returncode", 1)])
def test_explicit_invalid_or_error_records_cannot_hide_behind_other_good_fields(tmp_path, field, value):
    path, plan = fixture(tmp_path)
    def alter(m):
        m["transcript"]["models_reported_by_context"] = ["model-test"]
        m[field] = value
    mutate(metric_path(plan), alter)
    got = compare.compare_plan(path)
    assert not got["complete_summary"] and got["formal_summary"] is None
    assert "DO_NOT_COPY_SENSITIVE_CONTENT" not in json.dumps(got)


def test_missing_case_metadata_retains_every_run_and_observed_cost(tmp_path):
    path, plan = fixture(tmp_path)
    (Path(plan["cases"][0]["tools_case"]) / "case.json").unlink()
    got = compare.compare_plan(path)
    assert not got["complete_summary"] and len(got["runs"]) == 8
    assert got["runs"][0]["observed"]["primary_tokens"] == 50
    assert any(d["code"] == "missing_case" for d in got["runs"][0]["diagnostics"])


def test_zero_usage_is_observed_but_zero_raw_denominator_is_not_a_savings_claim(tmp_path):
    path, plan = fixture(tmp_path)
    for arm in ("raw", "tools"):
        for rep in (1, 2):
            mutate(metric_path(plan, arm=arm, rep=rep), lambda m: m["usage"].update(input_total=0, output=0))
    got = compare.compare_plan(path)
    assert got["complete_summary"]
    assert got["cases"][0]["arms"]["tools"]["mean"]["primary_tokens"] == 0
    assert got["cases"][0]["savings_fraction"] is None
    assert got["formal_summary"]["case_macro"]["savings_fraction"] is None
    assert got["formal_summary"]["pooled"]["savings_fraction"] == pytest.approx(.1)


@pytest.mark.parametrize("body", ['{"status":"completed","status":"completed"}', '{"status":NaN}'])
def test_ambiguous_or_nonstandard_json_never_silently_becomes_completed(tmp_path, body):
    path, plan = fixture(tmp_path)
    metric_path(plan).write_text(body, encoding="utf-8")
    got = compare.compare_plan(path)
    assert not got["complete_summary"] and len(got["runs"]) == 8
    assert any(d["code"] == "invalid_metrics" for d in got["runs"][0]["diagnostics"])


def test_relative_case_paths_resolve_from_plan_and_incomplete_cli_still_writes_report(tmp_path):
    path, plan = fixture(tmp_path)
    for row in plan["cases"]:
        for arm in ("tools", "raw"):
            row[arm + "_case"] = str(Path(row[arm + "_case"]).relative_to(path.parent))
    dump(path, plan)
    target = tmp_path / plan["cases"][0]["tools_case"] / "runs/tools/rep2/metrics.json"
    mutate(target, lambda m: m.update(status="starting"))
    before = target.read_bytes()
    output = tmp_path / "partial.json"
    assert compare.main(["--plan", str(path), "--output", str(output)]) == 2
    assert target.read_bytes() == before
    assert json.loads(output.read_text())["planned_runs"] == 8


@pytest.mark.parametrize("bad", [None, -1, True, "100", 1.5])
def test_unknown_or_invalid_primary_usage_never_becomes_zero(tmp_path, bad):
    path, plan = fixture(tmp_path)
    mutate(metric_path(plan), lambda m: m["usage"].update(input_total=bad))
    got = compare.compare_plan(path)
    assert not got["complete_summary"] and got["runs"][0]["observed"]["primary_tokens"] is None


def test_only_explicit_plan_case_and_metrics_paths_are_read_and_no_unplanned_run_selected(tmp_path, monkeypatch):
    path, plan = fixture(tmp_path)
    extra = metric_path(plan, rep=3)
    dump(extra, {"status": "completed", "usage": {"input_total": 1, "output": 1}})
    original = Path.read_bytes
    reads = []
    def guarded(file):
        assert file.name in ("plan.json", "case.json", "metrics.json")
        assert file != extra
        reads.append(file)
        return original(file)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    before = deepcopy(plan)
    got = compare.compare_plan(path)
    assert got["complete_summary"] and len(got["runs"]) == 8 and plan == before
    assert len([p for p in reads if p.name == "metrics.json"]) == 8


def test_cli_output_is_new_and_cannot_be_written_inside_a_case(tmp_path):
    path, plan = fixture(tmp_path)
    output = tmp_path / "summary.json"
    assert compare.main(["--plan", str(path), "--output", str(output)]) == 0
    before = output.read_bytes()
    with pytest.raises(FileExistsError): compare.write_report(compare.compare_plan(path), output)
    assert output.read_bytes() == before
    with pytest.raises(ValueError): compare.write_report(compare.compare_plan(path), Path(plan["cases"][0]["tools_case"]) / "new.json")


def test_report_cannot_write_into_shared_pool_or_source_outside_variant_case(tmp_path):
    path, plan = fixture(tmp_path)
    case_path = Path(plan["cases"][0]["tools_case"]) / "case.json"
    shared_pool = tmp_path / "shared-original-pool"
    mutate(case_path, lambda value: value.update(pool=str(shared_pool)))
    report = compare.compare_plan(path)
    for protected in (shared_pool, tmp_path / "tools-source"):
        with pytest.raises(ValueError, match="frozen pools and sources"):
            compare.write_report(report, protected / "new.json")
        assert not (protected / "new.json").exists()


def test_boolean_rep_is_not_a_valid_run_coordinate(tmp_path):
    path, plan = fixture(tmp_path)
    mutate(metric_path(plan), lambda value: value.update(rep=True))
    report = compare.compare_plan(path)
    assert not report["complete_summary"]
    assert any(row["code"] == "run_coordinate_mismatch" for row in report["runs"][0]["diagnostics"])


@pytest.mark.parametrize("kind", ["duplicate_case", "duplicate_rep", "empty_reps", "missing_expected", "duplicate_run"])
def test_plan_cannot_choose_or_count_the_same_run_twice(tmp_path, kind):
    path, plan = fixture(tmp_path)
    if kind == "duplicate_case": plan["cases"][1]["id"] = "A"
    elif kind == "duplicate_rep": plan["cases"][0]["reps"] = [1, 1]
    elif kind == "empty_reps": plan["cases"][0]["reps"] = []
    elif kind == "missing_expected": plan.pop("expected")
    else:
        plan["cases"][1]["tools_case"] = plan["cases"][0]["tools_case"]
    dump(path, plan)
    with pytest.raises(ValueError): compare.compare_plan(path)
