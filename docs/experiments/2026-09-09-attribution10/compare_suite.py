"""Read-only planned paired accounting, never an accuracy or semantic evaluator.

python compare_suite.py --plan PLAN.json --output NEW_REPORT.json

Plan: {"schema":"migloop-paired-metrics-plan/1",
       "expected":{"backend":"codex","model":"MODEL","effort":"medium"},
       "cases":[{"id":"CASE","tools_case":"tools/case","raw_case":"raw/case",
                 "reps":[1,2]}]}

Only the explicit plan, case.json and planned metrics.json files are opened.
Case paths are relative to the plan. No run discovery, best-rep selection,
transcript/result/report/oracle reading, provider calls or source imports.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any


PLAN_SCHEMA = "migloop-paired-metrics-plan/1"
REPORT_SCHEMA = "migloop-paired-metrics-report/1"
ARMS = ("tools", "raw")
FIELDS = ("primary_tokens", "input_total", "output", "input_uncached", "cache_read", "cache_creation",
          "thinking_reported", "wall_s", "end_to_end_wall_s", "call_count", "wrapper_count",
          "failed_calls", "rejected_calls")
MAX_JSON_BYTES = 64 * 1024 * 1024


def _diag(code: str, field: str, message: str, *, error: bool = True) -> dict[str, str]:
    return {"code": code, "field": field, "level": "error" if error else "warning", "message": message}


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if value >= 0 and math.isfinite(value) else None
    except OverflowError:
        return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("non-finite JSON constant")


def _read(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if path.is_symlink():
        raise ValueError("metadata file must not be a symbolic link")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("metadata file exceeds bounded JSON size")
    body = path.read_bytes()
    value = json.loads(body.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(value, dict):
        raise ValueError("metadata JSON must be an object")
    return value, {"path": str(path), "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def _metadata(path: Path, kind: str):
    try:
        data, source = _read(path)
        return data, source, []
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        # Do not quote offending JSON, which may contain embedded tool inputs.
        code = "missing_" + kind if isinstance(exc, FileNotFoundError) else "invalid_" + kind
        return None, {"path": str(path), "sha256": None, "bytes": None}, [
            _diag(code, kind, type(exc).__name__ + ": metadata unavailable or invalid")]


def _plan(path: Path):
    value, origin = _read(path)
    if value.get("schema") != PLAN_SCHEMA:
        raise ValueError("unsupported paired plan schema")
    expected = value.get("expected")
    if not isinstance(expected, dict) or set(expected) != {"backend", "model", "effort"} or not all(_text(x) for x in expected.values()):
        raise ValueError("plan.expected requires explicit backend/model/effort")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("plan.cases must be a nonempty list")
    ids, targets, normalized = set(), set(), []
    for row in cases:
        if not isinstance(row, dict) or set(row) != {"id", "tools_case", "raw_case", "reps"}:
            raise ValueError("each case requires id/tools_case/raw_case/reps only")
        ident, reps = row["id"], row["reps"]
        if not _text(ident) or ident in ids:
            raise ValueError("case IDs must be nonempty and unique")
        ids.add(ident)
        if (not isinstance(reps, list) or not reps or any(type(n) is not int or n < 1 for n in reps)
                or len(reps) != len(set(reps))):
            raise ValueError("reps must be explicit unique positive integers")
        parsed = {"id": ident, "reps": list(reps)}
        for arm in ARMS:
            if not _text(row[arm + "_case"]):
                raise ValueError("case paths must be explicit strings")
            directory = (path.parent / row[arm + "_case"]).resolve()
            parsed[arm + "_case"] = str(directory)
            for rep in reps:
                target = directory / "runs" / arm / f"rep{rep}" / "metrics.json"
                if target in targets:
                    raise ValueError("same planned metrics path occurs more than once")
                targets.add(target)
        normalized.append(parsed)
    return {"schema": PLAN_SCHEMA, "expected": dict(expected), "cases": normalized}, origin


def _string_set(value: Any) -> list[str] | None:
    if isinstance(value, str) and _text(value):
        return [value]
    if isinstance(value, list) and value and all(_text(x) for x in value):
        return sorted(set(value))
    return None


def _anomaly_count(value: Any) -> int | float | None:
    return len(value) if isinstance(value, list) else _number(value)


def _actual_sources(raw: dict[str, Any], errors: list) -> dict[str, Any]:
    sources = {name: _string_set(value) for name, value in raw.items()}
    for name, value in raw.items():
        if sources[name] is None and value not in (None, "", []):
            errors.append(_diag("actual_parameter_invalid", name, "Explicit parameter record has invalid shape; not ignored in favor of another source"))
    return sources


def _run(case_id, arm, rep, directory, case, case_source, case_errors, expected):
    path = directory / "runs" / arm / f"rep{rep}" / "metrics.json"
    metrics, origin, errors = _metadata(path, "metrics")
    errors = list(case_errors) + errors
    m, c = metrics or {}, case or {}
    transcript, native, usage = _object(m.get("transcript")), _object(m.get("native_events")), _object(m.get("usage"))
    observed = {k: _number(usage.get(k)) for k in ("input_total", "output", "input_uncached", "cache_read", "cache_creation", "thinking_reported")}
    for field in ("input_total", "output"):
        if type(usage.get(field)) is not int:
            observed[field] = None  # Provider token counters are integers, unlike wall-clock seconds.
    observed.update({k: _number(m.get(k)) for k in ("wall_s", "end_to_end_wall_s")})
    call_source = "metrics.transcript.tool_calls" if _number(transcript.get("tool_calls")) is not None else "metrics.native_events.tool_calls"
    observed["call_count"] = _number(transcript.get("tool_calls")) if call_source.startswith("metrics.transcript") else _number(native.get("tool_calls"))
    observed.update({k: _number(transcript.get(k)) for k in ("wrapper_count", "failed_calls", "rejected_calls")})
    observed["primary_tokens"] = (observed["input_total"] + observed["output"]
                                   if observed["input_total"] is not None and observed["output"] is not None else None)
    status = m.get("status") if _text(m.get("status")) else "missing_metrics" if metrics is None and errors[-1]["code"] == "missing_metrics" else "unknown"
    if status != "completed":
        errors.append(_diag("run_not_completed", "status", "Planned run has not completed successfully"))
    if m.get("recording_complete") is not True:
        errors.append(_diag("recording_not_complete", "recording_complete", "No explicit complete recording flag"))
    recording = {"complete": m.get("recording_complete") if isinstance(m.get("recording_complete"), bool) else None,
                 "pending_calls": _number(transcript.get("pending_calls")),
                 "native_pending_calls": _number(native.get("pending_calls")),
                 "malformed_lines": _anomaly_count(transcript.get("malformed_lines")),
                 "unmatched_results": _anomaly_count(transcript.get("unmatched_result_ids")),
                 "event_malformed_lines": _anomaly_count(m.get("event_malformed_lines")),
                 "event_errors": _anomaly_count(m.get("event_errors"))}
    for key, count in recording.items():
        if key != "complete" and count is not None and count > 0:
            errors.append(_diag("recording_conflict", key, "Explicit pending/parse/pairing/runtime anomaly contradicts complete successful recording"))
    for key in ("result_parse_error", "integrity_error", "harness_error"):
        if m.get(key):
            errors.append(_diag("reported_run_error", key, "Metrics declares an error; error body not copied"))
    if m.get("result_is_error") is True or (m.get("returncode") is not None and m.get("returncode") != 0):
        errors.append(_diag("reported_run_failure", "result_is_error/returncode", "Metrics declares unsuccessful provider result or process exit"))
    if observed["primary_tokens"] is None:
        errors.append(_diag("primary_usage_incomplete", "usage", "input_total and output must both be finite nonnegative numbers"))
    for field in FIELDS:
        if field != "primary_tokens" and observed.get(field) is None:
            errors.append(_diag("auxiliary_missing", field, "Not reported as a usable number; retained as null", error=False))
    if c.get("schema") != "migloop-pair-case/1":
        errors.append(_diag("case_schema", "case.schema", "Case metadata schema unavailable or unsupported"))
    for field, value in (("arm", arm), ("rep", rep), ("case", c.get("case"))):
        if m.get(field) != value or value is None or field == "rep" and type(m.get(field)) is not int:
            errors.append(_diag("run_coordinate_mismatch", field, "Metrics does not identify this planned run"))
    for field in ("common_task_sha256", "pool_digest"):
        if not _text(c.get(field)) or not _text(m.get(field)) or c.get(field) != m.get(field):
            errors.append(_diag("case_run_digest_mismatch", field, "Case/run task or pool identity missing or different"))
    for field in ("source_code_id", "source_digest"):
        if not _text(c.get(field)) or not _text(m.get(field)):
            errors.append(_diag("source_unrecorded", field, "Source identifier not fully recorded", error=False))
        elif c[field] != m[field]:
            errors.append(_diag("source_mismatch", field, "Case and metrics source identifiers conflict"))
    for stage in ("integrity_before", "integrity_after"):
        proof = _object(m.get(stage))
        for key in ("pool_unchanged", "source_unchanged", "task_unchanged"):
            if proof.get(key) is False:
                errors.append(_diag("reported_integrity_failure", stage + "." + key, "Recorded frozen-integrity check failed"))
    for field, want in (("backend", expected["backend"]), ("model_requested", expected["model"]), ("effort", expected["effort"])):
        if m.get(field) != want:
            errors.append(_diag("parameter_mismatch", field, "Requested parameter missing or different from the explicit plan"))
    model_sources = _actual_sources({"metrics.actual_models": m.get("actual_models"),
                     "metrics.models_reported_by_context": m.get("models_reported_by_context"),
                     "metrics.transcript.models_reported_by_context": transcript.get("models_reported_by_context")}, errors)
    effort_sources = _actual_sources({"metrics.actual_effort": m.get("actual_effort"),
                      "metrics.actual_efforts": m.get("actual_efforts"),
                      "metrics.transcript.efforts_reported_by_context": transcript.get("efforts_reported_by_context")}, errors)
    for name, sources, want in (("model", model_sources, expected["model"]), ("effort", effort_sources, expected["effort"])):
        reported = [v for v in sources.values() if v is not None]
        if not reported:
            errors.append(_diag("actual_parameter_unverified", name, "No actual parameter record; requested value is not a substitute"))
        elif any(values != [want] for values in reported):
            errors.append(_diag("actual_parameter_mismatch", name, "Actual parameter records differ from the plan or from each other"))
    if not _text(m.get("runner_sha256")):
        errors.append(_diag("runner_unrecorded", "runner_sha256", "Runner digest unavailable", error=False))
    eligible = not any(d["level"] == "error" for d in errors)
    return {"case_id": case_id, "arm": arm, "rep": rep, "run_dir": str(path.parent), "case_dir": str(directory),
            "status": status, "eligible_for_cost_accounting": eligible,
            "primary_tokens": observed["primary_tokens"] if eligible else None, "observed": observed,
            "identity": {"case": _text(c.get("case")), "file": _text(c.get("file")),
                "case_task_sha256": _text(c.get("common_task_sha256")), "metrics_task_sha256": _text(m.get("common_task_sha256")),
                "case_pool_digest": _text(c.get("pool_digest")), "metrics_pool_digest": _text(m.get("pool_digest"))},
            "recording": recording, "parameters": {"backend": _text(m.get("backend")), "model_requested": _text(m.get("model_requested")),
                "effort_requested": _text(m.get("effort")), "actual_model_sources": model_sources, "actual_effort_sources": effort_sources,
                "actual_model_source_label": _text(m.get("actual_model_source")), "actual_effort_source_label": _text(m.get("actual_effort_source")),
                **{k: _text(m.get(k)) for k in ("tool_transport", "final_mode")},
                **{k: _number(m.get(k)) for k in ("max_turns", "max_budget_usd", "timeout_s")}},
            "source": {"source_path": _text(m.get("source")), "source_code_id": _text(m.get("source_code_id")),
                       "source_digest": _text(m.get("source_digest")), "runner_sha256": _text(m.get("runner_sha256")),
                       "case_source_code_id": _text(c.get("source_code_id")), "case_source_digest": _text(c.get("source_digest")),
                       "origin": "metrics.json; compared with case.json where recorded"},
            "protected_input_roots": [str((directory / c[key]).resolve()) for key in ("pool", "source") if _text(c.get(key))],
            "metric_sources": {"usage": "metrics.usage (provider accounting summary)", "call_count": call_source,
                               "wall_s": "metrics.wall_s", "end_to_end_wall_s": "metrics.end_to_end_wall_s"},
            "metadata_files": {"case": case_source, "metrics": origin}, "diagnostics": errors}


def _mean(values):
    return sum(values) / len(values) if values and all(v is not None for v in values) else None


def _sum(values):
    return sum(values) if values and all(v is not None for v in values) else None


def _savings(tools, raw):
    return 1 - tools / raw if tools is not None and raw is not None and raw > 0 else None


def _arm(rows):
    complete = all(r["eligible_for_cost_accounting"] for r in rows)
    return {"planned_runs": len(rows), "completed_status_runs": sum(r["status"] == "completed" for r in rows),
            "eligible_runs": sum(r["eligible_for_cost_accounting"] for r in rows),
            "mean": {k: _mean([r["observed"][k] for r in rows]) if complete else None for k in FIELDS}}


def _partial(runs):
    arms = {}
    for arm in ARMS:
        rows = [r for r in runs if r["arm"] == arm]
        fields = {}
        for field in FIELDS:
            known = [r["observed"][field] for r in rows if r["observed"][field] is not None]
            fields[field] = {"observed_sum": sum(known) if known else None, "observed_mean": _mean(known),
                             "known_runs": len(known), "unknown_runs": len(rows) - len(known), "planned_runs": len(rows)}
        arms[arm] = {"status_counts": dict(Counter(r["status"] for r in rows)), "observed": fields}
    return {"formal_comparison": False, "savings_fraction": None, "arms": arms,
            "note": "Partial observations include failed/incomparable runs when numbers exist. Missing values are unknown, not zero. This is not a paired savings comparison."}


def compare_plan(plan_path: Path | str) -> dict[str, Any]:
    path = Path(plan_path).resolve()
    plan, origin = _plan(path)
    all_runs, cases, metadata_cache = [], [], {}
    for row in plan["cases"]:
        records, metadata = [], {}
        for arm in ARMS:
            directory = Path(row[arm + "_case"])
            case_path = directory / "case.json"
            if case_path not in metadata_cache:
                metadata_cache[case_path] = _metadata(case_path, "case")
            case, source, errors = metadata_cache[case_path]
            metadata[arm] = case or {}
            records.extend(_run(row["id"], arm, rep, directory, case, source, errors, plan["expected"]) for rep in row["reps"])
        checks = []
        for field in ("common_task_sha256", "pool_digest", "file"):
            left, right = metadata["tools"].get(field), metadata["raw"].get(field)
            if not _text(left) or not _text(right) or left != right:
                checks.append(_diag("pair_mismatch", field, "Both arms must declare the same task, pool and target file"))
        arms = {arm: _arm([r for r in records if r["arm"] == arm]) for arm in ARMS}
        comparable = not checks and all(r["eligible_for_cost_accounting"] for r in records)
        savings = _savings(arms["tools"]["mean"]["primary_tokens"], arms["raw"]["mean"]["primary_tokens"]) if comparable else None
        if comparable and savings is None:
            checks.append(_diag("undefined_savings", "primary_tokens", "Raw mean is zero; savings ratio is undefined", error=False))
        cases.append({"id": row["id"], "planned_reps": row["reps"], "comparable": comparable, "arms": arms,
                      "savings_fraction": savings, "savings_percent": savings * 100 if savings is not None else None,
                      "diagnostics": checks})
        all_runs.extend(records)
    complete = all(c["comparable"] for c in cases)
    formal = None
    if complete:
        totals = {arm: {field: _sum([r["observed"][field] for r in all_runs if r["arm"] == arm]) for field in FIELDS} for arm in ARMS}
        savings = _savings(totals["tools"]["primary_tokens"], totals["raw"]["primary_tokens"])
        macro = _mean([case["savings_fraction"] for case in cases])
        formal = {"pooled": {"raw_tokens": totals["raw"]["primary_tokens"], "tools_tokens": totals["tools"]["primary_tokens"],
                             "savings_fraction": savings, "savings_percent": savings * 100 if savings is not None else None},
                  "case_macro": {"cases": len(cases), "savings_fraction": macro, "savings_percent": macro * 100 if macro is not None else None},
                  "totals": totals}
    return {"schema": REPORT_SCHEMA, "complete_summary": complete, "semantics_scored": False,
            "expected": plan["expected"], "plan": {**plan, "source": origin},
            "accounting": {"primary": "usage.input_total + usage.output, exactly once; cache and reasoning are not added",
                           "case": "mean of every explicitly planned repetition; incomplete arm mean is null",
                           "pooled": "1 - tools token sum / raw token sum over all planned runs",
                           "case_macro": "equal-weight mean of per-case savings using each arm's planned-rep mean",
                           "recording": "metrics recording_complete plus explicit anomaly summaries; absent counters stay unknown",
                           "scope": "No semantic scoring, record-content inspection or independent frozen-file rehash. Sources are declared metrics/case identities.",
                           "final_modes": "tools reference and raw document are recorded as distinct modes, not rejected as a mismatch"},
            "planned_runs": len(all_runs), "status_counts": dict(Counter(r["status"] for r in all_runs)),
            "cases": cases, "runs": all_runs, "formal_summary": formal,
            "partial_descriptive": None if complete else _partial(all_runs)}


def write_report(report: dict[str, Any], output: Path | str) -> None:
    target = Path(output).resolve()
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite report: {target}")
    for row in report["plan"]["cases"]:
        if any(target.is_relative_to(Path(row[arm + "_case"])) for arm in ARMS):
            raise ValueError("Report must be outside the immutable input case directories")
    for row in report["runs"]:
        if any(target.is_relative_to(Path(root)) for root in row.get("protected_input_roots") or []):
            raise ValueError("Report must be outside the declared frozen pools and sources")
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with target.open("x", encoding="utf-8", newline="") as stream:
        stream.write(body)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = compare_plan(args.plan)
    write_report(report, args.output)
    print(json.dumps({"output": str(args.output.resolve()), "complete_summary": report["complete_summary"],
                      "planned_runs": report["planned_runs"], "semantics_scored": False}))
    return 0 if report["complete_summary"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
