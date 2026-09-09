"""Authenticate bounded reference witnesses. Locator checks are not truth judgments."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(r"C:\Users\hongy\projects\_migloop-eval-20260909")
POOLS = {"dice": BASE / "v1/dice-entry/pool", "aippt0723": BASE / "v1/splash/pool",
         "codex830": BASE / "attribution10/codex-inputs/pool"}


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def witness(row, pool_name, cache):
    relative = row.get("relative_file") or row["file"]
    path = (POOLS[pool_name] / relative).resolve()
    if not path.is_relative_to(POOLS[pool_name].resolve()) or row["line"] < 1:
        raise ValueError(f"Witness outside its pool or invalid line: {row['id']}")
    if path not in cache:
        cache[path] = path.read_bytes().splitlines()
    raw = cache[path][row["line"] - 1]
    signature = hashlib.sha256(raw).hexdigest()
    if row.get("record_sha256") and row["record_sha256"].lower() != signature:
        raise ValueError(f"Record digest mismatch: {row['id']}")
    obj = json.loads(raw)
    all_text = list(strings(obj))
    for text in row.get("contains", []):
        if not any(text in field for field in all_text):
            raise ValueError(f"Missing literal {text!r}: {row['id']}")
    if "selector" in row:
        value = obj
        for key in row["selector"]:
            value = value[key]
        if not isinstance(value, str) or hashlib.sha256(value.encode()).hexdigest() != row["field_sha256"]:
            raise ValueError(f"Decoded field digest mismatch: {row['id']}")
        for excerpt in row.get("excerpts", []):
            start, text = excerpt["start_char"], excerpt["text"]
            if value[start:start + len(text)] != text:
                raise ValueError(f"Excerpt mismatch: {row['id']}")
    return {"id": row["id"], "pool": pool_name, "file": relative, "line": row["line"],
            "record_sha256": signature, "timestamp": obj.get("timestamp"),
            "tool_use_id": row.get("tool_use_id"), "contains": row.get("contains", []),
            "selector": row.get("selector"), "excerpts": row.get("excerpts", [])}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=Path(__file__).with_name("legacy-reference.json"))
    parser.add_argument("--freeze", type=Path, help="New witness snapshot; never overwrite")
    args = parser.parse_args()
    raw_ref = args.reference.read_bytes()
    reference = json.loads(raw_ref)
    legacy_path = Path(__file__).resolve().parents[1] / "2026-09-09-fidelity-cost/reference-evidence.json"
    legacy = json.loads(legacy_path.read_bytes())
    old = {r["id"]: r for r in legacy["records"]}
    needed = {key for case in reference["cases"] for key in case["evidence_ids"]}
    cache = {}
    rows = [witness(old[key], "dice" if old[key]["case"] == "dice" else "aippt0723", cache)
            for key in sorted(needed & old.keys())]
    rows += [witness(row, row["pool"], cache) for row in reference["extra_evidence"] if row["id"] in needed]
    if needed != {r["id"] for r in rows}:
        raise ValueError(f"Missing witnesses: {needed - {r['id'] for r in rows}}")
    result = {"schema": "migloop-attribution-witnesses/1", "reference_sha256": hashlib.sha256(raw_ref).hexdigest(),
              "cases": [c["id"] for c in reference["cases"]], "witnesses": rows,
              "scope": "Authenticates original records and literal excerpts only; not causal truth or exhaustive coverage."}
    if args.freeze:
        with args.freeze.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps({"cases": len(result["cases"]), "witnesses": len(rows), "locator_checks": "passed",
                      "reference_sha256": result["reference_sha256"], "frozen": str(args.freeze) if args.freeze else None}))


if __name__ == "__main__":
    main()
