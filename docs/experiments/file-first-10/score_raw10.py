"""Aggregate evidence-backed adjudications; never asks a model to grade.

No grades means pending, not 0% accuracy. Completed adjudications must cite exact
report spans and reference identifiers. The semantic decision remains reviewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_grade(base, case, rep, grade, *, contract_base=None):
    contract_base = base if contract_base is None else contract_base
    report_path = base/"runs"/case/f"rep{rep}"/"report.md"
    if not report_path.exists() or grade.get("report_sha256") != sha(report_path):
        raise ValueError("Adjudication report missing or changed")
    if grade.get("core_contract_sha256") != sha(contract_base/"private/scoring-core.json"):
        raise ValueError("Adjudication used a different scoring contract")
    contract = read(contract_base/"private/scoring-core.json")
    required = {k.split("/", 1)[1] for k in contract["units"] if k.startswith(case+"/")}
    units = grade.get("units", [])
    if {u["id"] for u in units} != required or len(units) != len(required):
        raise ValueError("Adjudication must account for every frozen unit exactly once")
    report = report_path.read_text(encoding="utf-8")
    for item in units + grade.get("claims", []):
        if not item.get("reason"):
            raise ValueError("Adjudication needs an explanation")
        spans = item.get("report_spans", [])
        if any(not isinstance(span, str) or not span or span not in report for span in spans):
            raise ValueError("Adjudication quotes text not present in final report")
    for unit in units:
        if unit.get("outcome") not in ("correct", "partial", "missing", "wrong"):
            raise ValueError("Invalid unit outcome")
        if unit["outcome"] in ("correct", "partial", "wrong") and not unit.get("report_spans"):
            raise ValueError("Nonmissing unit needs an exact report span")
        if unit["outcome"] in ("correct", "wrong") and not unit.get("evidence"):
            raise ValueError("Correct/wrong decisions need a reference or original evidence basis")
    claims = grade.get("claims", [])
    if len({c["id"] for c in claims}) != len(claims):
        raise ValueError("Duplicate claim ids")
    for claim in claims:
        if claim.get("outcome") not in ("supported", "contradicted", "unsupported_asserted_as_fact", "explicitly_hypothetical"):
            raise ValueError("Invalid claim outcome")
        if not claim.get("report_spans"):
            raise ValueError("Claim needs an exact report span")
        if claim.get("major_error") and (claim["outcome"] not in ("contradicted", "unsupported_asserted_as_fact") or not claim.get("evidence")):
            raise ValueError("Major error needs a substantive false assertion and source basis")
    asserted = [c for c in claims if c["outcome"] != "explicitly_hypothetical"]
    counts = {name: sum(u["outcome"] == name for u in units) for name in ("correct", "partial", "missing", "wrong")}
    major = sum(bool(c.get("major_error")) for c in claims)
    supported = sum(c["outcome"] == "supported" for c in asserted)
    return {"units": len(units), **counts, "correct_attribution_coverage": counts["correct"]/len(units),
            "asserted_claims": len(asserted), "supported_claims": supported,
            "attribution_precision": supported/len(asserted) if asserted else None,
            "major_errors": major, "file_pass": counts["correct"] == len(units) and major == 0}


def summarize(base, grades, *, contract_base=None):
    contract_base = base if contract_base is None else contract_base
    manifest = read(base/"manifest.json")
    rows = []
    for case in manifest["cases"]:
        for rep in range(1, manifest["repetitions"] + 1):
            directory = base/"runs"/case["id"]/f"rep{rep}"
            metric = read(directory/"metrics.json") if (directory/"metrics.json").exists() else {}
            grade_path = grades/case["id"]/f"rep{rep}.json"
            grade = validate_grade(base, case["id"], rep, read(grade_path), contract_base=contract_base) if grade_path.exists() else None
            if grade is None and metric.get("status") in ("timeout", "incomplete") and not (directory/"report.md").exists():
                contract = read(contract_base/"private/scoring-core.json")
                total = sum(k.startswith(case["id"]+"/") for k in contract["units"])
                grade = {"units": total, "correct": 0, "partial": 0, "missing": total, "wrong": 0,
                    "correct_attribution_coverage": 0, "asserted_claims": 0, "supported_claims": 0,
                    "attribution_precision": None, "major_errors": 0, "file_pass": False,
                    "automatic_basis": "Terminal run delivered no final answer, not a semantic claim of wrong attribution"}
            usage = metric.get("usage") or {}
            input_count, output_count = usage.get("input_total"), usage.get("output")
            tokens = input_count + output_count if isinstance(input_count, (int,float)) and isinstance(output_count, (int,float)) else None
            rows.append({"case": case["id"], "file": case["file"], "rep": rep,
                "status": metric.get("status", "running_or_not_started"), "grade": grade,
                "tokens_total": tokens, "input_tokens": input_count, "output_tokens": output_count,
                "cache_read_tokens": usage.get("cache_read"), "elapsed_seconds": metric.get("elapsed_seconds")})
    adjudicated = [r for r in rows if r["grade"] is not None]
    aggregate = None
    if len(adjudicated) == len(rows):
        # Equal repetitions per file: a run mean equals a file-macro mean.
        assertions = sum(r["grade"]["asserted_claims"] for r in rows)
        aggregate = {"file_macro_correct_attribution_coverage": mean(r["grade"]["correct_attribution_coverage"] for r in rows),
            "file_run_pass_rate": mean(r["grade"]["file_pass"] for r in rows),
            "attribution_precision": sum(r["grade"]["supported_claims"] for r in rows)/assertions if assertions else None,
            "major_errors": sum(r["grade"]["major_errors"] for r in rows),
            "caution": "10 development files from 3 related pools, not population accuracy or a tools comparison"}
    return {"runs_expected": len(rows), "runs_recorded": sum(r["status"] != "running_or_not_started" for r in rows),
            "runs_adjudicated": len(adjudicated), "aggregate": aggregate, "runs": rows}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--grades", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    data = summarize(args.baseline.resolve(), args.grades.resolve())
    body = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(body+"\n")
    print(body)
