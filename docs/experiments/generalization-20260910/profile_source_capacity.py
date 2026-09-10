"""Bounded per-source accounting; no cache budget mutation, no model calls."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from profile_delivery import dump, package, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--eval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    before = package(args.repo)
    for name in ("profile_source_capacity.py", "profile_delivery.py"):
        source = Path(__file__).with_name(name)
        with (args.out / name).open("xb") as stream:
            stream.write(source.read_bytes())
    settings = json.loads((args.eval / "tools-v3/settings/F10-03.json").read_text(encoding="utf-8"))
    for key in list(os.environ):
        if key.startswith("MIGLOOP_"):
            del os.environ[key]
    os.environ.update(settings["mcp_servers"]["migloop"]["env"])
    sys.path.insert(0, str(args.repo / "src"))
    from migloop import raw_events, service, transcript_store
    started = datetime.now(timezone.utc).isoformat()
    ledger = service.session_ledger(os.environ["MIGLOOP_FROZEN_ANCHOR"])
    registry = transcript_store.sources(ledger)
    registry_key = raw_events._digest([(path, sorted(owners)) for path, owners in sorted(registry.items())])
    ceiling = 128 * 1024 * 1024
    rows = []
    for path in sorted(registry):
        clock = time.perf_counter()
        index, signature, status = raw_events._source_index(path, registry_key)
        built = time.perf_counter() - clock
        clock = time.perf_counter()
        size = raw_events._retained_size((registry_key, signature, path, index), ceiling)
        rows.append({"source": path, "source_bytes": os.stat(path).st_size,
                     "source_index_status": status, "index_seconds": built,
                     "counted_bytes": size, "count_is_complete": size <= ceiling,
                     "counting_seconds": time.perf_counter() - clock,
                     "native_parts": len(index["native"]), "unknown_records": len(index["unknown"]),
                     "gaps": len(index["gaps"])})
        del index
    remaining = ceiling
    admitted, skipped = [], []
    for row in rows:
        if row["count_is_complete"] and row["counted_bytes"] <= remaining:
            admitted.append(row["source"])
            remaining -= row["counted_bytes"]
        else:
            skipped.append(row["source"])
    after = package(args.repo)
    assert before == after
    result = {"schema": "migloop-source-capacity-audit/1", "started_at": started,
              "ended_at": datetime.now(timezone.utc).isoformat(), "source_count": len(rows),
              "per_entry_measurement_ceiling": ceiling, "rows": rows,
              "sum_counted_entry_bytes": sum(r["counted_bytes"] for r in rows),
              "sum_is_lower_bound": any(not r["count_is_complete"] for r in rows),
              "oversize_original_8mib": [r["source"] for r in rows if r["counted_bytes"] > 8 * 1024 * 1024],
              "greedy_128mib_sorted_source_simulation": {"admitted": admitted, "skipped": skipped,
                  "remaining_bytes": remaining, "used_bytes": ceiling - remaining,
                  "note": "Arithmetic only, not a new cache implementation. Follows sorted source order, never evicts."},
              "original_lru_budget": raw_events._CACHE_BUDGET,
              "original_source_cap": raw_events._MAX_SOURCE_CACHE_BYTES,
              "package_before": before, "package_after": after, "package_stable": before == after,
              "script_sha256": sha(Path(__file__)), "model_calls": 0,
              "note": "Counts each entry using production accounting, shared objects only deduplicated within an entry. Sum is not process RSS or unique pool heap. Retains no extra collection of source index graphs; production LRU remains unchanged."}
    dump(args.out / "result.json", result)
    print(json.dumps({"source_count": len(rows), "sum_counted_entry_bytes": result["sum_counted_entry_bytes"],
        "sum_is_lower_bound": result["sum_is_lower_bound"], "oversize_original_8mib": result["oversize_original_8mib"],
        "largest": sorted(rows, key=lambda x: x["counted_bytes"], reverse=True)[:4],
        "greedy_admitted": len(admitted), "greedy_remaining": remaining, "greedy_skipped": skipped}), flush=True)


if __name__ == "__main__":
    main()
