"""Inspect request-size admission without raising the production memory cap."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from profile_delivery import dump, package, sha
from profile_scan_reuse import synthetic_checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--eval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    for name in ("profile_scan_capacity.py", "profile_scan_reuse.py", "profile_delivery.py"):
        source = Path(__file__).with_name(name)
        with (args.out / name).open("xb") as stream:
            stream.write(source.read_bytes())
    before = package(args.repo)
    setting = json.loads((args.eval / "tools-v3/settings/F10-03.json").read_text(encoding="utf-8"))
    for key in list(os.environ):
        if key.startswith("MIGLOOP_"):
            del os.environ[key]
    os.environ.update(setting["mcp_servers"]["migloop"]["env"])
    sys.path.insert(0, str(args.repo / "src"))
    from migloop import atoms, atoms_collect, raw_events, service
    started = datetime.now(timezone.utc).isoformat()
    ledger = service.session_ledger(os.environ["MIGLOOP_FROZEN_ANCHOR"])
    original = raw_events._retained_size
    observed = []

    def size(value, ceiling):
        clock = time.perf_counter()
        count = original(value, ceiling)
        if ceiling == raw_events._REQUEST_SCAN_BUDGET:
            observed.append({"ceiling": ceiling, "count_until_stop": count,
                             "seconds": time.perf_counter() - clock})
        return count

    raw_events._retained_size = size
    try:
        with raw_events.scan_scope():
            data = raw_events.inventory(ledger)
            state = raw_events._SCAN_REUSE.get()
            retained = state.get("retained_bytes", 0)
        clean = raw_events._SCAN_REUSE.get() is None and state == {}
    finally:
        raw_events._retained_size = original
    tiny = args.out / "agent-b2222222222222222.jsonl"
    row = {"timestamp": "2026-09-10T10:01:00Z", "type": "user",
           "message": {"role": "user", "content": "tiny synthetic input"}}
    with tiny.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    small = atoms.build_ledger(atoms_collect.collect_cc(str(tiny), [0]))
    with raw_events.scan_scope():
        raw_events.inventory(small)
        second = raw_events.inventory(small)
        tiny_retained = raw_events._SCAN_REUSE.get()["retained_bytes"]
        assert second["cache"]["request_reused"] is True
    checks = synthetic_checks(args.out)
    after = package(args.repo)
    assert clean and before == after
    result = {"schema": "migloop-request-scan-capacity/1", "started_at": started,
              "measurements": observed, "real_retained_bytes": retained,
              "real_request_reused": data["cache"]["request_reused"], "real_state_clean": clean,
              "tiny_request_reused": second["cache"]["request_reused"], "tiny_retained_bytes": tiny_retained,
              "synthetic_checks": checks, "package_before": before, "package_after": after,
              "package_stable": before == after, "script_sha256": sha(Path(__file__)),
              "model_calls": 0, "note": "Size accounting stops after cap; count_until_stop is a lower bound, not total graph size. No cap change."}
    dump(args.out / "result.json", result)
    print(json.dumps({k: result[k] for k in ("measurements", "real_retained_bytes", "tiny_request_reused", "tiny_retained_bytes", "real_state_clean")}), flush=True)


if __name__ == "__main__":
    main()
