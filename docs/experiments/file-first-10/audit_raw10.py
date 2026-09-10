"""Read-only post-run audit of the frozen raw baseline; no investigator calls.

The call index supports manual scope/delivery review. It does not certify that
arbitrary shell programs stayed in scope or that the model understood a return.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def audit(base):
    here = Path(__file__).resolve().parent
    runner = module(here / "run_raw10.py", "raw10_runner_audit")
    native_path = here.parent / "file-first-luna/review-v2/audit.py"
    native = module(native_path, "raw10_native_audit")
    manifest = runner.verify_manifest(base)
    rows, indexes = [], []
    for case in manifest["cases"]:
        for rep in range(1, manifest["repetitions"] + 1):
            directory = base / "runs" / case["id"] / f"rep{rep}"
            metric = read(directory / "metrics.json")
            trace = native.native_calls(directory / "transcript.jsonl")
            calls = trace["calls"]
            transcript_ok = sha(directory / "transcript.jsonl") == metric["transcript_sha256"]
            if not transcript_ok:
                raise ValueError(f"Transcript drift: {case['id']} rep{rep}")
            rows.append({
                "case": case["id"], "rep": rep, "status": metric["status"],
                "models": metric["actual_models"], "effort": metric["actual_effort"],
                "recording_complete": metric["recording_complete"],
                "host_skill_catalog_absent": metric["host_skill_catalog_absent"],
                "transcript_sha256_valid": transcript_ok,
                "native_outer_calls": len(calls),
                "native_return_chars": sum(c["visible_chars"] or 0 for c in calls),
                "returns_with_truncation_marker": sum(bool(c["truncation_marker"]) for c in calls),
                "unpaired_calls": sum(c["pairing"] != "unique" for c in calls),
                "orphan_output_ids": trace["orphan_output_ids"],
                "tool_names": sorted({c["tool"] for c in calls}),
            })
            indexes.append({"case": case["id"], "rep": rep, "calls": [
                {k: v for k, v in c.items() if k != "text"} for c in calls
            ]})
    return {
        "schema": "migloop-raw-baseline-recording-audit/1",
        "manifest_sha256": sha(base / "manifest.json"),
        "audit_script_sha256": sha(Path(__file__)),
        "native_parser_sha256": sha(native_path),
        "frozen_manifest_verified": True,
        "scope_status": "Call index requires manual program review; not an OS isolation proof",
        "truncation_semantics": "Markers in native returns; may include quoted historical markers, not a certified loss count",
        "round_semantics": "Outer tool calls, not inner batch calls or guaranteed serial reasoning turns",
        "runs": rows, "call_index": indexes,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    result = audit(args.baseline.resolve())
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"out": str(args.out), "runs": result["runs"]}, ensure_ascii=False))
