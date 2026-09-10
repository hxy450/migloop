"""Same-snapshot on/off request scan reuse comparison; development pool only."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from profile_delivery import dump, package, sha


def synthetic_checks(out):
    from migloop import atoms, atoms_collect, raw_events, transcript_store
    path = out / "agent-a1111111111111111.jsonl"
    original = {"timestamp": "2026-09-10T10:01:00Z", "type": "user",
                "message": {"role": "user", "content": "original synthetic input"}}
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(original) + "\n")
    ledger = atoms.build_ledger(atoms_collect.collect_cc(str(path), [0]))
    ref = transcript_store.read_record(str(path), 1).ref
    state = None
    with raw_events.scan_scope():
        raw_events.inventory(ledger)
        state = raw_events._SCAN_REUSE.get()
        original["message"]["content"] = "changed synthetic input with different size"
        path.write_text(json.dumps(original) + "\n", encoding="utf-8")
        updated = raw_events.inventory(ledger)
        stale_reference_rejected = False
        try:
            transcript_store.resolve(ledger, ref)
        except ValueError:
            stale_reference_rejected = True
        if updated["cache"].get("request_reused"):
            raise AssertionError("Changed source reused stale scan")
        if not stale_reference_rejected:
            raise AssertionError("Changed line accepted its old raw reference")
    normal_released = raw_events._SCAN_REUSE.get() is None and state == {}
    state = None
    try:
        with raw_events.scan_scope():
            raw_events.inventory(ledger)
            state = raw_events._SCAN_REUSE.get()
            raise RuntimeError("synthetic exception")
    except RuntimeError:
        pass
    exception_released = raw_events._SCAN_REUSE.get() is None and state == {}
    assert normal_released and exception_released
    return {"fixture": str(path), "source_change_reused": False,
            "stale_reference_rejected": stale_reference_rejected,
            "normal_context_released": normal_released,
            "exception_context_released": exception_released,
            "note": "Only this new synthetic source was modified. Fresh updated evidence may be read; stale references/scans must not be reused."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--eval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reuse", choices=("on", "off"), required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    for script in (Path(__file__), Path(__file__).with_name("profile_delivery.py")):
        with (args.out / script.name).open("xb") as stream:
            stream.write(script.read_bytes())
    before = package(args.repo)
    settings_path = args.eval / "tools-v3/settings/F10-03.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))["mcp_servers"]["migloop"]["env"]
    for key in list(os.environ):
        if key.startswith("MIGLOOP_"):
            del os.environ[key]
    os.environ.update(settings)
    sys.path.insert(0, str(args.repo / "src"))
    from migloop import delivery_budget, investigation, raw_events, service
    started = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()
    ledger = service.session_ledger(settings["MIGLOOP_FROZEN_ANCHOR"])
    cold = time.perf_counter() - clock
    configured_budget = raw_events._REQUEST_SCAN_BUDGET
    if args.reuse == "off":
        raw_events._REQUEST_SCAN_BUDGET = 0
    request_path = args.eval / "tools-v3-atom-overview-audit/20260910T164423Z/F10-03/request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    results = []
    original_scan, original_uncached = raw_events._scan, raw_events._scan_uncached
    original_query, original_fit = investigation.query, delivery_budget.fit
    for name, requests, budget in (("single_changes", request["requests"][:1], 30000),
                                    ("dice24", request["requests"], request["max_chars"])):
        stats = Counter()
        durations = Counter()
        states = []
        max_retained = 0

        def scan(*values, **kw):
            nonlocal max_retained
            data = original_scan(*values, **kw)
            stats["scan_calls"] += 1
            stats["scan_reused"] += bool(data.get("cache", {}).get("request_reused"))
            state = raw_events._SCAN_REUSE.get()
            if state is not None:
                if all(state is not known for known in states):
                    states.append(state)
                max_retained = max(max_retained, state.get("retained_bytes", 0))
            return data

        def uncached(*values, **kw):
            stats["uncached_scans"] += 1
            return original_uncached(*values, **kw)

        def query(*values, **kw):
            start = time.perf_counter()
            try:
                return original_query(*values, **kw)
            finally:
                stats["selection_calls"] += 1
                durations["selection_seconds"] += time.perf_counter() - start

        def fit(*values, **kw):
            start = time.perf_counter()
            try:
                return original_fit(*values, **kw)
            finally:
                stats["fit_calls"] += 1
                durations["fit_seconds"] += time.perf_counter() - start

        raw_events._scan, raw_events._scan_uncached = scan, uncached
        investigation.query, delivery_budget.fit = query, fit
        clock, cpu = time.perf_counter(), time.process_time()
        try:
            data = investigation.batch(ledger, requests, budget)
        finally:
            raw_events._scan, raw_events._scan_uncached = original_scan, original_uncached
            investigation.query, delivery_budget.fit = original_query, original_fit
        elapsed, cpu_elapsed = time.perf_counter() - clock, time.process_time() - cpu
        clean = raw_events._SCAN_REUSE.get() is None and all(state == {} for state in states)
        assert clean and max_retained <= raw_events._REQUEST_SCAN_BUDGET
        dump(args.out / (name + ".json"), data)
        row = {"workload": name, "seconds": elapsed, "cpu_seconds": cpu_elapsed,
               **stats, **durations, "max_request_retained_bytes": max_retained,
               "request_state_released": clean, "data_sha256": investigation.digest(data),
               "data_chars": data["data_chars"], "status_summary": data["delivery_summary"]}
        results.append(row)
        print(json.dumps(row), flush=True)
    checks = synthetic_checks(args.out)
    raw_events._REQUEST_SCAN_BUDGET = configured_budget
    after = package(args.repo)
    assert before == after
    dump(args.out / "result.json", {"schema": "migloop-request-scan-comparison/1",
        "reuse": args.reuse, "configured_budget": configured_budget,
        "effective_budget": configured_budget if args.reuse == "on" else 0,
        "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
        "ledger_fresh_process_seconds": cold, "results": results, "synthetic_checks": checks,
        "snapshot": str(args.repo), "package_before": before, "package_after": after,
        "package_stable": before == after, "script_sha256": sha(Path(__file__)),
        "request_sha256": sha(request_path), "settings_sha256": sha(settings_path),
        "model_calls": 0, "note": "Same snapshot and request. Off changes only in-memory _REQUEST_SCAN_BUDGET to zero. No production source/config edit; timings exclude output files and synthetic checks."})
    print(json.dumps({"done": args.reuse, "state_clean": checks, "result": str(args.out / "result.json")}), flush=True)


if __name__ == "__main__":
    main()
