"""Summarize saved baseline metrics and explicit manual grades; never LLM-score.

Missing/failed runs and unknown usage stay visible. No zero-filled cost savings.
"""
import argparse
import hashlib
import json
from pathlib import Path


def read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--grades", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    manifest = read(args.baseline / "baseline.json")
    ref = read(args.baseline / "reference.json")
    if sha(args.baseline / "reference.json") != manifest["reference_sha256"]:
        raise ValueError("Reference drift")
    grade_doc = read(args.grades) if args.grades else {"runs": []}
    if args.grades and grade_doc["reference_sha256"] != manifest["reference_sha256"]:
        raise ValueError("Grades use a different reference")
    grades = {}
    for grade in grade_doc["runs"]:
        key = (grade["case"], grade["arm"], grade["rep"])
        if key in grades:
            raise ValueError("Duplicate run grade")
        grades[key] = grade
    rows = []
    for case in ref["cases"]:
        units = {issue["id"]: issue for issue in case["issues"]}
        for rep in (1, 2):
            for arm in ("raw", "tools"):
                run = args.baseline / case["case"] / "runs" / arm / f"rep{rep}"
                metric = read(run / "metrics.json") if (run / "metrics.json").exists() else {}
                usage = metric.get("usage") or {}
                total = (usage["input_total"] + usage["output"] if
                         isinstance(usage.get("input_total"), (int, float)) and isinstance(usage.get("output"), (int, float)) else None)
                row = {"case":case["case"], "arm":arm, "rep":rep, "status":metric.get("status", "not_started"),
                       "actual_models":metric.get("actual_models"), "actual_effort":metric.get("actual_effort"),
                       "recording_complete":metric.get("recording_complete"), "verdict_ok":metric.get("verdict_ok"),
                       "coverage_counts":metric.get("coverage_counts"), "tokens_total":total,
                       "input_uncached":usage.get("input_uncached"), "cache_read":usage.get("cache_read"),
                       "input_total":usage.get("input_total"), "output":usage.get("output"),
                       "wall_seconds":metric.get("end_to_end_wall_s"), "adjudicated":False}
                grade = grades.get((case["case"], arm, rep))
                if grade:
                    if metric.get("status") not in ("completed", "result_error", "timeout"):
                        raise ValueError("Cannot grade unfinished/absent run")
                    actual_ids = [g["id"] for g in grade["issues"]]
                    if len(set(actual_ids)) != len(actual_ids) or set(actual_ids) != set(units):
                        raise ValueError("Every reference issue must receive one explicit grade")
                    for g in grade["issues"]:
                        if (len(g["facts"]) != len(units[g["id"]]["required"]) or
                            any(type(x) not in (int,float) or x not in (0,0.5,1) for x in g["facts"]) or
                            not g.get("note")):
                            raise ValueError("Invalid/unexplained criterion grade")
                    errors = grade.get("material_errors") or []
                    passed = [g["id"] for g in grade["issues"] if all(x == 1 for x in g["facts"])
                              and not any(e.get("issue") in (None,g["id"]) for e in errors)]
                    row.update(adjudicated=True, fact_points=sum(sum(g["facts"]) for g in grade["issues"]),
                        fact_maximum=sum(len(g["facts"]) for g in grade["issues"]),
                        matched_topics=sum(bool(g["topic_found"]) for g in grade["issues"]), topics_total=len(units),
                        complete_attributions=len(passed), complete_attribution_ids=passed,
                        file_pass=len(passed)==len(units) and not errors and not grade.get("citation_support_errors"),
                        material_error_count=len(errors), citation_support_error_count=len(grade.get("citation_support_errors") or []),
                        delivery_failure=bool(grade.get("delivery_failure")),
                        semantic_assessable=not grade.get("delivery_failure",False),
                        report_artifact_sha256=sha(run / ("verdict.yaml" if arm=="tools" and (run/"verdict.yaml").exists() else "result.json")))
                rows.append(row)
    groups = {}
    for arm in ("raw", "tools"):
        all_rows = [r for r in rows if r["arm"]==arm]
        scored = [r for r in all_rows if r["adjudicated"]]
        groups[arm] = {"scheduled":len(all_rows), "completed":sum(r["status"]=="completed" for r in all_rows),
                       "adjudicated":len(scored), "fact_points":sum(r["fact_points"] for r in scored),
                       "fact_maximum":sum(r["fact_maximum"] for r in scored),
                       "matched_topics":sum(r["matched_topics"] for r in scored),
                       "topics_maximum":sum(r["topics_total"] for r in scored),
                       "complete_attributions":sum(r["complete_attributions"] for r in scored),
                       "file_pass":sum(r["file_pass"] for r in scored),
                       "delivery_failures":sum(r.get("delivery_failure",False) for r in scored),
                       "assessable_fact_maximum":sum(r["fact_maximum"] for r in scored if r.get("semantic_assessable")),
                       "material_errors":sum(r["material_error_count"] for r in scored)}
        for field in ("tokens_total","input_total","input_uncached","cache_read","output","wall_seconds"):
            groups[arm][field] = sum(r[field] for r in all_rows) if all(r[field] is not None for r in all_rows) else None
    pairs = []
    for raw in [r for r in rows if r["arm"]=="raw"]:
        tool = next(r for r in rows if r["case"]==raw["case"] and r["rep"]==raw["rep"] and r["arm"]=="tools")
        if raw["status"]==tool["status"]=="completed" and raw["tokens_total"] and tool["tokens_total"] is not None:
            pairs.append({"case":raw["case"], "rep":raw["rep"],
                "token_saving":1-tool["tokens_total"]/raw["tokens_total"],
                "wall_saving":1-tool["wall_seconds"]/raw["wall_seconds"] if raw["wall_seconds"] and tool["wall_seconds"] is not None else None,
                "quality_equivalence_established":False})
    report = {"schema":"migloop-file-first-summary/1", "reference_sha256":manifest["reference_sha256"],
              "grade_status":grade_doc.get("status", "not_adjudicated"),
              "grades_sha256":sha(args.grades) if args.grades else None,
              "all_runs_completed":all(r["status"]=="completed" for r in rows),
              "all_runs_adjudicated":all(r["adjudicated"] for r in rows), "groups":groups, "paired_cost":pairs, "runs":rows}
    if groups["raw"]["tokens_total"] and groups["tools"]["tokens_total"] is not None:
        file_savings = []
        for case in ref["cases"]:
            sample = [r for r in rows if r["case"]==case["case"]]
            raw_total = sum(r["tokens_total"] for r in sample if r["arm"]=="raw")
            tool_total = sum(r["tokens_total"] for r in sample if r["arm"]=="tools")
            file_savings.append({"case":case["case"],"token_saving":1-tool_total/raw_total})
        report["aggregate_cost"] = {
            "token_saving_total":1-groups["tools"]["tokens_total"]/groups["raw"]["tokens_total"],
            "token_saving_file_macro":sum(r["token_saving"] for r in file_savings)/len(file_savings),
            "wall_saving_total":1-groups["tools"]["wall_seconds"]/groups["raw"]["wall_seconds"]
                if groups["raw"]["wall_seconds"] and groups["tools"]["wall_seconds"] is not None else None,
            "file_savings":file_savings,"quality_equivalence_established":False}
    if args.out:
        with args.out.open("x",encoding="utf-8") as handle:
            json.dump(report,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!="runs"},ensure_ascii=False))


if __name__ == "__main__":
    main()
