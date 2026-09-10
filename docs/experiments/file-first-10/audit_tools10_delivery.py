"""Descriptive delivery diagnostics from recorded traces; not attribution grading.

Reads immutable run artifacts without building a ledger or calling a model.
Hashes bind this audit to the files actually inspected; they do not authenticate
historical causality or independently re-verify the trace recorder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(base):
    base = Path(base)
    manifest = read(base / "manifest.json")
    failures, locations, rows = Counter(), defaultdict(list), []
    totals = Counter()
    for case in manifest["cases"]:
        for rep in range(1, manifest["repetitions"] + 1):
            directory = base / "runs" / case["id"] / f"rep{rep}"
            path = directory / "query-trace.json"
            row = {"case": case["id"], "rep": rep, "status": "pending"}
            if path.is_file():
                trace = read(path)
                if trace.get("schema") != "migloop-investigation-trace/1":
                    raise ValueError("Unsupported trace: " + str(path))
                counts = Counter()
                for step in trace["steps"]:
                    # Host wrappers and direct calls are NOT duplicate batch
                    # items. The recorder gives items only to a verified batch.
                    for item in step.get("items", []):
                        counts[item["status"]] += 1
                        if item["status"] in ("error", "deferred"):
                            key = (item["tool"], item["status"], item.get("error") or item.get("reason"))
                            failures[key] += 1
                            locations[key].append({"case": case["id"], "rep": rep,
                                "step": step["step"], "item_index": item["item_index"],
                                "args": item.get("args"), "scope": item.get("scope"),
                                "original_data_chars": item.get("original_data_chars")})
                totals.update(counts)
                row.update(status="observed", trace_sha256=sha(path), batch_items=dict(counts),
                           steps=len(trace["steps"]), historical_edges_in_query_trace=len(trace.get("edges", [])))
            rows.append(row)
    return {"schema": "migloop-tools10-delivery-audit/1", "base": str(base.resolve()),
            "manifest_sha256": sha(base / "manifest.json"), "expected_runs": len(rows),
            "observed_runs": sum(row["status"] == "observed" for row in rows),
            "batch_items": dict(totals), "batch_items_total": sum(totals.values()),
            "failure_groups": [{"tool": key[0], "status": key[1], "reason": key[2],
                                "count": count, "locations": locations[key]}
                               for key, count in failures.most_common()],
            "runs": rows, "model_calls": 0, "semantic_checked": False,
            "limitations": ["Counts describe recorded batch subitems only, not all scalar/host tool calls.",
                "ok may deliver only a prefix; error/deferred do not certify a read.",
                "Repeated failures are retained, not independent statistical trials.",
                "This is not an independent native-recorder verification or causal explanation of model errors."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.baseline)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("expected_runs", "observed_runs", "batch_items", "batch_items_total")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
