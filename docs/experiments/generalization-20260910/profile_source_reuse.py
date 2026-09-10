"""Same-snapshot source-cache on/off and lossless wire cost audit."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextvars import copy_context
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import sys
from threading import Thread
import time

from profile_delivery import dump, package, sha


def canonical(value, excluded, path=""):
    if isinstance(value, list):
        return [canonical(x, excluded, path + "/" + str(i)) for i, x in enumerate(value)]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        where = path + "/" + key
        if key == "cache" and isinstance(item, dict) and {"budget_bytes", "max_source_bytes"} <= item.keys():
            performance = {"hit", "miss", "oversize_not_cached", "request_hit", "request_budget_bytes"}
            excluded.extend(where + "/" + k for k in item if k in performance)
            result[key] = {k: canonical(v, excluded, where + "/" + k)
                           for k, v in item.items() if k not in performance}
        else:
            result[key] = canonical(item, excluded, where)
    return result


def wire_audit(data, requests, budget, out, name):
    from migloop import investigation
    args = {"requests": requests, "max_chars": budget}

    def old_render():
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        receipt = {"schema": "migloop-investigation-receipt/1", "ledger": data["ledger"],
                   "request_sha256": investigation.digest(args), "body_sha256": investigation.digest(body)}
        return body + investigation.MARKER + json.dumps(receipt, separators=(",", ":"))

    def measure(fn):
        timings = []
        for _ in range(5):
            clock = time.perf_counter()
            text = fn()
            timings.append(time.perf_counter() - clock)
        return text, timings

    old, old_times = measure(old_render)
    new, new_times = measure(lambda: investigation.render_batch_data(data, requests, budget))
    decoded, decode_times = measure(lambda: investigation.parse_receipt("batch", args, new))
    old_decoded = investigation.parse_receipt("batch", args, old)
    assert decoded and old_decoded and decoded["data"] == old_decoded["data"] == data
    sizes = {}
    for label, text in (("old", old), ("new", new)):
        envelope = json.dumps({"content": [{"type": "text", "text": text}], "isError": False},
                              ensure_ascii=False, separators=(",", ":"))
        with (out / (name + "-" + label + ".txt")).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        sizes[label] = {"text_chars": len(text), "envelope_chars": len(envelope),
                        "text_bytes": len(text.encode()), "envelope_bytes": len(envelope.encode())}
    return {"sizes": sizes, "old_render_seconds": old_times, "new_render_seconds": new_times,
            "new_decode_seconds": decode_times, "old_render_median": statistics.median(old_times),
            "new_render_median": statistics.median(new_times), "new_decode_median": statistics.median(decode_times),
            "wire_chosen": investigation.WIRE_MARKER in new, "canonical_roundtrip_equal": True,
            "note": "Exact same projected data, old JSON and actual render_batch_data. No query in codec timings."}


def synthetic(out):
    from migloop import atoms, atoms_collect, raw_events, transcript_store
    p = out / "agent-a1111111111111111.jsonl"
    rows = [
        {"timestamp": "2026-09-10T10:01:00Z", "type": "assistant", "message": {"role": "assistant",
         "content": [{"type": "tool_use", "id": "read-1", "name": "Read", "input": {"file_path": "/p/A.ets"}}]}},
        {"timestamp": "2026-09-10T10:08:00Z", "type": "user", "message": {"role": "user",
         "content": [{"type": "tool_result", "tool_use_id": "read-1", "content": "FUTURE_BODY", "is_error": False}]}}]
    with p.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(json.dumps(row) for row in rows) + "\n")
    ledger = atoms.build_ledger(atoms_collect.collect_cc(str(p), [0]))
    old = transcript_store.read_record(str(p), 1).ref
    with raw_events.scan_scope():
        raw_events.inventory(ledger)
        second = raw_events.inventory(ledger)
        positive_hit = second["cache"]["request_hit"]
        late = raw_events.query(ledger, "2026-09-10T10:09:00Z")
        early = raw_events.query(ledger, "2026-09-10T10:03:00Z")
        assert late["events"][0]["status"] == "returned" and not early["events"][0]["results"]
        assert "FUTURE_BODY" not in str(early)
        state = raw_events._SCAN_REUSE.get()
        rows[0]["message"]["content"][0]["input"]["file_path"] = "/p/changed-longer.ets"
        p.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        changed = raw_events.inventory(ledger)
        assert changed["cache"]["request_hit"] == 0
        rejected = False
        try:
            transcript_store.resolve(ledger, old)
        except ValueError:
            rejected = True
        assert rejected
    assert state == {} and raw_events._SCAN_REUSE.get() is None
    try:
        with raw_events.scan_scope():
            raw_events.inventory(ledger)
            state = raw_events._SCAN_REUSE.get()
            raise RuntimeError("synthetic exit")
    except RuntimeError:
        pass
    assert state == {} and raw_events._SCAN_REUSE.get() is None

    async def task_test():
        with raw_events.scan_scope():
            raw_events.inventory(ledger)
            parent = raw_events._request_state()
            async def child():
                assert raw_events._request_state() is None
                with raw_events.scan_scope():
                    assert raw_events._request_state() is not parent
            await asyncio.create_task(child())
            assert raw_events._request_state() is parent

    asyncio.run(task_test())
    with raw_events.scan_scope():
        raw_events.inventory(ledger)
        observed = []
        context = copy_context()
        thread = Thread(target=lambda: context.run(lambda: observed.append(raw_events._request_state())))
        thread.start()
        thread.join()
        assert observed == [None]
    return {"repeat_request_hit": positive_hit, "source_change_request_hit": 0,
            "stale_reference_rejected": True, "late_result_not_backfilled": True,
            "normal_and_exception_cleanup": True, "child_task_isolated": True, "child_thread_isolated": True}


def main():
    parser = argparse.ArgumentParser()
    for name in ("repo", "eval", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reuse", choices=("on", "off"), required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    for name in ("profile_source_reuse.py", "profile_delivery.py"):
        path = Path(__file__).with_name(name)
        with (args.out / name).open("xb") as stream:
            stream.write(path.read_bytes())
    before = package(args.repo)
    settings_path = args.eval / "tools-v3/settings/F10-03.json"
    config = json.loads(settings_path.read_text(encoding="utf-8"))["mcp_servers"]["migloop"]["env"]
    for key in list(os.environ):
        if key.startswith("MIGLOOP_"):
            del os.environ[key]
    os.environ.update(config)
    sys.path.insert(0, str(args.repo / "src"))
    from migloop import delivery_budget, investigation, raw_events, service
    started = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()
    ledger = service.session_ledger(config["MIGLOOP_FROZEN_ANCHOR"])
    cold = time.perf_counter() - clock
    budget_original = raw_events._REQUEST_SCAN_BUDGET
    if args.reuse == "off":
        raw_events._REQUEST_SCAN_BUDGET = 0
    path = args.eval / "tools-v3-atom-overview-audit/20260910T164423Z/F10-03/request.json"
    request = json.loads(path.read_text(encoding="utf-8"))
    source_fn, query_fn, fit_fn = raw_events._source_index, investigation.query, delivery_budget.fit
    results = []
    for name, requests, budget in (("single_changes", request["requests"][:1], 30000),
                                   ("dice24", request["requests"], request["max_chars"])):
        counts, durations, states, selected = Counter(), Counter(), [], []
        peak_bytes = peak_entries = peak_skips = 0

        def source(*values, **kw):
            nonlocal peak_bytes, peak_entries, peak_skips
            value = source_fn(*values, **kw)
            counts[value[2]] += 1
            state = raw_events._request_state()
            if state is not None:
                if all(state is not known for known in states):
                    states.append(state)
                peak_bytes = max(peak_bytes, state["retained_bytes"])
                peak_entries = max(peak_entries, len(state["indexes"]))
                peak_skips = max(peak_skips, len(state["skipped"]))
            return value

        def query(*values, **kw):
            clock = time.perf_counter()
            data = query_fn(*values, **kw)
            durations["selection_seconds"] += time.perf_counter() - clock
            selected.append(data)
            return data

        def fit(*values, **kw):
            clock = time.perf_counter()
            value = fit_fn(*values, **kw)
            durations["fit_seconds"] += time.perf_counter() - clock
            counts["fit_calls"] += 1
            return value

        raw_events._source_index, investigation.query, delivery_budget.fit = source, query, fit
        clock, cpu = time.perf_counter(), time.process_time()
        try:
            data = investigation.batch(ledger, requests, budget)
        finally:
            raw_events._source_index, investigation.query, delivery_budget.fit = source_fn, query_fn, fit_fn
        elapsed, cpu_elapsed = time.perf_counter() - clock, time.process_time() - cpu
        clean = raw_events._SCAN_REUSE.get() is None and all(state == {} for state in states)
        assert clean and peak_bytes <= raw_events._REQUEST_SCAN_BUDGET
        exclusions = []
        selected_canonical = canonical(selected, exclusions)
        projected_canonical = canonical(data, exclusions)
        dump(args.out / (name + ".json"), data)
        dump(args.out / (name + "-selected.json"), selected)
        row = {"workload": name, "seconds": elapsed, "cpu_seconds": cpu_elapsed, **counts, **durations,
               "max_retained_bytes": peak_bytes, "max_retained_sources": peak_entries,
               "max_skip_guards": peak_skips, "request_state_released": clean,
               "data_chars": data["data_chars"], "status_summary": data["delivery_summary"],
               "selected_canonical_sha256": investigation.digest(selected_canonical),
               "projected_canonical_sha256": investigation.digest(projected_canonical),
               "excluded_performance_paths": exclusions}
        row["wire"] = wire_audit(data, requests, budget, args.out, name)
        results.append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ("wire", "excluded_performance_paths")}), flush=True)
    checks = synthetic(args.out)
    raw_events._REQUEST_SCAN_BUDGET = budget_original
    after = package(args.repo)
    assert before == after
    dump(args.out / "result.json", {"schema": "migloop-source-request-reuse-audit/1", "reuse": args.reuse,
         "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
         "ledger_fresh_process_seconds": cold, "configured_budget": budget_original,
         "effective_budget": budget_original if args.reuse == "on" else 0,
         "results": results, "synthetic_checks": checks, "package_before": before, "package_after": after,
         "package_stable": True, "request_sha256": sha(path), "script_sha256": sha(Path(__file__)),
         "model_calls": 0, "note": "Same-snapshot on/off. Only in-memory request budget changes; global LRU remains unchanged. No model latency claim."})
    print(json.dumps({"done": args.reuse, "synthetic_checks": checks}), flush=True)


if __name__ == "__main__":
    main()
