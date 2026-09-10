"""Score reviewed tools-arm reports with the unchanged, frozen raw-arm rubric.

No model calls, semantic inference, repair, or writes to either run directory.
Mechanical format/reference diagnostics are not attribution accuracy. An absent
adjudication is pending; raw's terminal-no-final-answer rule is shared unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path


_spec = importlib.util.spec_from_file_location("tools10_shared_raw_score", Path(__file__).with_name("score_raw10.py"))
RAW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RAW)
read, sha = RAW.read, RAW.sha


def verify_contract(base):
    """Resolve the original frozen contract; a tools-local rubric is never used."""
    base = Path(base).resolve()
    manifest = read(base / "manifest.json")
    if (manifest.get("schema") != "migloop-file-first-tools10-baseline/1"
            or manifest.get("status") != "frozen_ready_for_tools"):
        raise ValueError("Expected an official frozen tools manifest, not a dev smoke")
    raw_base = Path(manifest["raw_base"]).resolve()
    raw_path = raw_base / "manifest.json"
    if raw_base == base or sha(raw_path) != manifest.get("raw_manifest_sha256"):
        raise ValueError("Frozen raw manifest binding changed")
    raw = read(raw_path)
    if (raw.get("schema") != "migloop-file-first-raw10-baseline/1"
            or raw.get("status") != "frozen_ready_for_raw"):
        raise ValueError("Expected the original frozen raw baseline")
    core = raw_base / "private/scoring-core.json"
    entries = [item for item in raw.get("artifacts", []) if item.get("path") == "private/scoring-core.json"]
    if len(entries) != 1 or entries[0].get("sha256") != sha(core):
        raise ValueError("Frozen scoring contract artifact changed or is not uniquely registered")
    for field in ("model", "effort", "repetitions", "concurrency", "timeout_seconds"):
        if field not in raw or manifest.get(field) != raw[field]:
            raise ValueError("Paired experiment setting differs: " + field)
    def cases(value):
        return [(case["id"], case["file"].replace("\\", "/"), str(Path(case["pool"]).resolve()))
                for case in value["cases"]]
    paired = cases(raw)
    if not paired or len({item[0] for item in paired}) != len(paired) or cases(manifest) != paired:
        raise ValueError("Paired experiment cases differ")
    return manifest, raw_base, {
        "raw_base": str(raw_base), "raw_manifest_sha256": sha(raw_path),
        "core_contract_sha256": sha(core), "tools_manifest_sha256": sha(base / "manifest.json"),
        "code_digest": manifest.get("code_digest"), "scorer_sha256": sha(Path(__file__)),
        "shared_validator_sha256": sha(Path(RAW.__file__)),
    }


def mechanical_result(directory, metric):
    """Read frozen verifier diagnostics only; do not turn them into grades."""
    path = directory / "verdict.json"
    expected = (metric.get("postprocess") or {}).get("verdict_sha256")
    if not path.exists():
        if expected:
            raise ValueError("Recorded mechanical verdict is missing")
        return None
    if expected and expected != sha(path):
        raise ValueError("Recorded mechanical verdict changed")
    verdict = read(path)
    if verdict.get("schema") != "migloop-tools10-final-verification/1":
        raise ValueError("Unknown mechanical verdict schema")
    report = directory / "report.md"
    claimed_sha = verdict.get("report_sha256")
    actual_sha = sha(report) if report.exists() else None
    if claimed_sha is not None and claimed_sha != actual_sha:
        raise ValueError("Mechanical verdict report missing or changed")
    bound = claimed_sha is not None and claimed_sha == actual_sha
    built = verdict.get("verification") or {}
    graph = built.get("argument_graph") or {}
    references = []
    # findings is another presentation of these same graph records, not extra checks.
    for node in graph.get("nodes", []):
        references.extend(node.get("evidence", []))
        references.extend(node.get("counterevidence", []))
    for edge in graph.get("edges", []):
        references.extend(edge.get("evidence", []))
    ref_counts = Counter(item.get("status", "unknown") for item in references)
    errors = verdict.get("errors", [])
    document = verdict.get("data")
    schema3 = isinstance(document, dict) and document.get("schema") == "migloop-verdict/3"
    validation_observed = bound and isinstance(verdict.get("found"), bool)
    return {
        "status": "observed" if validation_observed else "unbound_or_verifier_error",
        "verdict_sha256": sha(path), "report_sha256": actual_sha, "report_bound": bound,
        "document_found": verdict.get("found"), "schema3_document_present": schema3,
        "document_checks_pass": bool(verdict.get("found") and schema3 and not errors) if validation_observed else None,
        "document_error_count": len(errors), "identity_bound": (built.get("identity") or {}).get("bound"),
        "reference_occurrences": len(references), "reference_status_counts": dict(sorted(ref_counts.items())),
        "diagnostic_counts": dict(sorted(Counter(item.get("code", "unknown") for item in built.get("diagnostics", [])).items())),
        "semantic_checked": False,
        "caution": "Recorded schema/identity/reference checks only; resolved coordinates do not prove a causal claim",
    }


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _stat(values):
    observed = [value for value in values if _number(value)]
    return {"observed_runs": len(observed), "expected_runs": len(values),
            "sum": sum(observed) if observed else None,
            "mean": sum(observed) / len(observed) if observed else None,
            "complete": len(observed) == len(values)}


def summarize(base, grades):
    base, grades = Path(base).resolve(), Path(grades).resolve()
    manifest, raw_base, bindings = verify_contract(base)
    result = RAW.summarize(base, grades, contract_base=raw_base)
    for row in result["runs"]:
        directory = base / "runs" / row["case"] / f"rep{row['rep']}"
        metric = read(directory / "metrics.json") if (directory / "metrics.json").exists() else {}
        for field in ("raw_manifest_sha256", "tools_manifest_sha256", "code_digest"):
            if field in metric and metric[field] != bindings[field]:
                raise ValueError("Run provenance binding differs: " + field)
        postprocess = metric.get("postprocess") or {}
        # No cache double counting. Missing values remain missing, including timing.
        uncached = (row["input_tokens"] - row["cache_read_tokens"]
                    if _number(row["input_tokens"]) and _number(row["cache_read_tokens"])
                    and row["cache_read_tokens"] <= row["input_tokens"] else None)
        row.update(uncached_input_tokens=uncached,
                   investigator_elapsed_seconds=metric.get("investigator_elapsed_seconds"),
                   system_elapsed_seconds=metric.get("system_elapsed_seconds"),
                   postprocess_elapsed_seconds=postprocess.get("elapsed_seconds"),
                   postprocess_status=postprocess.get("status"),
                   report_sha256=sha(directory / "report.md") if (directory / "report.md").exists() else None,
                   mechanical=mechanical_result(directory, metric))
    fields = ("input_tokens", "cache_read_tokens", "uncached_input_tokens", "output_tokens", "tokens_total",
              "investigator_elapsed_seconds", "system_elapsed_seconds", "postprocess_elapsed_seconds")
    costs = {field: _stat([row[field] for row in result["runs"]]) for field in fields}
    costs.update(prepare_elapsed_seconds=manifest.get("prepare_elapsed_seconds"),
                 scope="Input includes cache; total = input + output. Structured final output is included, not discounted. "
                       "System time already includes investigator and postprocess; do not add them again. "
                       "Run-time sums are not concurrent experiment makespan. Preparation is separate. Missing costs are not zero.")
    checks = [row["mechanical"] for row in result["runs"] if row["mechanical"] is not None]
    observed = [check for check in checks if check["document_checks_pass"] is not None]
    reference_counts = Counter()
    for check in checks:
        reference_counts.update(check["reference_status_counts"])
    mechanical = {"runs_with_verdict": len(checks), "document_checks_observed": len(observed),
                  "document_checks_passed": sum(check["document_checks_pass"] for check in observed),
                  "reference_occurrences": sum(reference_counts.values()),
                  "reference_status_counts": dict(sorted(reference_counts.items())),
                  "semantic_checked": False,
                  "caution": "Independent process metrics, never accuracy or score bonuses; counts are declaration occurrences, not unique truths"}
    totals = None
    if result["aggregate"] is not None:
        totals = {field: sum(row["grade"][field] for row in result["runs"])
                  for field in ("units", "correct", "partial", "missing", "wrong", "asserted_claims", "supported_claims", "major_errors")}
        totals["unit_weighted_correct_attribution_coverage"] = totals["correct"] / totals["units"]
        totals["file_runs_passed"] = sum(row["grade"]["file_pass"] for row in result["runs"])
    return {"schema": "migloop-file-first-tools10-scores/1", "condition": "tools", "bindings": bindings,
            **result, "semantic_totals": totals, "costs": costs, "mechanical": mechanical,
            "caution": "Same frozen core and validator as raw. Descriptive paired development-set results, not evidence of general tool uplift."}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True, help="Official tools-v1 directory (not raw baseline-v1)")
    ap.add_argument("--grades", type=Path, required=True, help="Separate tools-adjudication-v1 directory")
    ap.add_argument("--out", type=Path, help="New output file; an existing file is never overwritten")
    args = ap.parse_args(argv)
    body = json.dumps(summarize(args.baseline, args.grades), ensure_ascii=False, indent=2)
    if args.out:
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(body + "\n")
    print(body)


if __name__ == "__main__":
    main()
