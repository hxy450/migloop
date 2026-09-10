"""Offline development-only performance audit; no model/historical execution.

Run each mode in a fresh process. Outputs are new audit artifacts only.
Instrumentation is in memory and is restored before returning.
"""
from __future__ import annotations

import argparse
from collections import Counter
import cProfile
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pstats
import statistics
import sys
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def package(repo):
    return {str(p.relative_to(repo)).replace("\\", "/"): sha(p)
            for p in sorted((repo / "src/migloop").rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def measured(name, fn, rows):
    start, cpu = time.perf_counter(), time.process_time()
    result = fn()
    row = {"phase": name, "wall_seconds": time.perf_counter() - start,
           "cpu_seconds": time.process_time() - cpu}
    rows.append(row)
    print(json.dumps(row), flush=True)
    return result


def profile(name, fn, out):
    profiler = cProfile.Profile()
    started = time.perf_counter()
    result = profiler.runcall(fn)
    elapsed = time.perf_counter() - started
    profiler.dump_stats(str(out / (name + ".prof")))
    stats = pstats.Stats(profiler)
    entries = []
    for (file, line, func), (primitive, calls, own, cumulative, callers) in stats.stats.items():
        entries.append({"file": file, "line": line, "function": func,
                        "primitive_calls": primitive, "calls": calls,
                        "self_seconds": own, "cumulative_seconds": cumulative})
    entries.sort(key=lambda x: x["cumulative_seconds"], reverse=True)
    watched = [x for x in entries if any(s in (x["file"] + ":" + x["function"])
               for s in ("deepcopy", "json", "delivery_budget", "_transcript_calls", "project_trace"))]
    dump(out / (name + "-profile.json"), {"profiled_wall_seconds": elapsed,
        "total_calls": stats.total_calls, "primitive_calls": stats.prim_calls,
        "top_cumulative": entries[:35], "watched": watched,
        "note": "cProfile changes timings; cumulative times overlap, never sum them."})
    return result


def replay(ledger, paths, out, phases):
    from migloop import atoms, delivery_budget, investigation
    request = json.loads(paths["dice24_request"].read_text(encoding="utf-8"))
    assert len(request["requests"]) == 24 and request["max_chars"] == 30000
    trace = json.loads(paths["entry_trace"].read_text(encoding="utf-8"))
    agent_original = next(s for s in trace["steps"] if s["step"] == 8)["args"]["requests"][5]
    agent = {"tool": "agent", "args": {**agent_original["args"],
             "view": "overview", "limit": 40, "details": False}}
    if "scope" in agent_original:
        agent["scope"] = agent_original["scope"]
    expanded = next(s for s in trace["steps"] if s["step"] == 18)["args"]["requests"][1]
    workloads = [("dice24", request["requests"], request["max_chars"]),
                 ("agent_overview", [agent], 12000), ("large_expand", [expanded], 6000)]
    dump(out / "requests.json", {"workloads": workloads,
        "agent_adjustment": "Existing F10-07 rep1 step8 item5: only view=overview, limit=40, details=false.",
        "expand_origin": "Unchanged F10-07 rep1 step18 item1, including explicit scope.",
        "dice24_origin": "Existing preformal v3 overview replay of development v2 step16; not a formal-v3 24-item model call."})
    original_query, original_fit = investigation.query, delivery_budget.fit
    results = []
    for name, requests, budget in workloads:
        selected, selections, fits = [], [], []

        def capture(ledger_arg, tool, args):
            started = time.perf_counter()
            try:
                data = original_query(ledger_arg, tool, args)
                selected.append(data)
                return data
            finally:
                selections.append({"tool": tool, "wall_seconds": time.perf_counter() - started})

        def fit(data, allowance):
            started = time.perf_counter()
            result = original_fit(data, allowance)
            fits.append({"wall_seconds": time.perf_counter() - started, "budget": allowance,
                         "status": result["status"], "original_data_chars": result["original_data_chars"],
                         "data_chars": result["data_chars"]})
            return result

        investigation.query, delivery_budget.fit = capture, fit
        try:
            projected = measured(name + ".real_batch",
                lambda: investigation.batch(ledger, requests, budget), phases)
        finally:
            investigation.query, delivery_budget.fit = original_query, original_fit
        if len(selected) != len(requests):
            raise RuntimeError("Query error: cached replay would not preserve request alignment")
        selection_hash = investigation.digest(selected)

        def cached_batch():
            position = iter(selected)
            investigation.query = lambda *args: next(position)
            try:
                return investigation.batch(ledger, requests, budget)
            finally:
                investigation.query = original_query

        repeats = []
        for number in range(5):
            start = time.perf_counter()
            candidate = cached_batch()
            repeats.append(time.perf_counter() - start)
            if investigation.digest(candidate) != investigation.digest(projected):
                raise RuntimeError("Cached fit replay changed output")
        profiled = profile(name + "-cached-fit", cached_batch, out)
        if investigation.digest(profiled) != investigation.digest(projected):
            raise RuntimeError("Profiled fit changed output")
        if investigation.digest(selected) != selection_hash:
            raise RuntimeError("Budget fit mutated selected input")
        body = measured(name + ".json_render",
            lambda: json.dumps(projected, ensure_ascii=False, separators=(",", ":")), phases)
        receipt = measured(name + ".receipt_hash", lambda: {
            "schema": "migloop-investigation-receipt/1", "ledger": atoms.ledger_identity(ledger),
            "request_sha256": investigation.digest({"requests": requests, "max_chars": budget}),
            "body_sha256": investigation.digest(body)}, phases)
        text = measured(name + ".receipt_append", lambda: body + investigation.MARKER +
            json.dumps(receipt, separators=(",", ":")), phases)
        wrapper = measured(name + ".mcp_json_wrapper", lambda: json.dumps({
            "content": [{"type": "text", "text": text}], "isError": False},
            ensure_ascii=False, separators=(",", ":")), phases)
        results.append({"name": name, "requests": len(requests), "budget": budget,
            "selection_seconds": sum(x["wall_seconds"] for x in selections), "selections": selections,
            "budget_fit_seconds": sum(x["wall_seconds"] for x in fits), "fit_calls": fits,
            "cached_fit_unprofiled_seconds": repeats,
            "cached_fit_unprofiled_median": statistics.median(repeats),
            "status_summary": projected["delivery_summary"],
            "selected_chars": sum(delivery_budget.size(x) for x in selected),
            "data_chars": projected["data_chars"], "batch_json_chars": len(body),
            "receipt_chars": len(text) - len(body), "mcp_envelope_chars": len(wrapper),
            "batch_json_bytes": len(body.encode()), "mcp_envelope_bytes": len(wrapper.encode()),
            "selected_sha256": selection_hash, "projected_sha256": investigation.digest(projected)})
        print(json.dumps({"workload": name, **{k: results[-1][k] for k in
            ("selection_seconds", "budget_fit_seconds", "cached_fit_unprofiled_median", "data_chars", "mcp_envelope_chars")}}), flush=True)
    return results


def postprocess(ledger, paths, out, phases):
    from migloop import atoms, delivery_budget, investigation, probe, verdict, verdict_v3, via
    run = paths["old_run"]
    fit_calls = []
    original_fit = delivery_budget.fit

    def fit(*args, **kwargs):
        fit_calls.append(1)
        return original_fit(*args, **kwargs)

    delivery_budget.fit = fit
    try:
        report = measured("postprocess.report_read", lambda: (run / "report.md").read_text(encoding="utf-8"), phases)
        calls = measured("postprocess.native_record_extraction", lambda: probe._transcript_calls(str(run)) or [], phases)
        identity = measured("postprocess.ledger_identity", lambda: atoms.ledger_identity(ledger), phases)
        trace_identity = measured("postprocess.trace_identity", lambda: via.trace_identity(ledger, calls, {}), phases)
        loaded = measured("postprocess.document_parse", lambda: verdict.load_block(report), phases)
        context = {"raw": loaded["raw"], "harness_identity": identity, "trace_identity": trace_identity}
        built = measured("postprocess.verdict_build", lambda: verdict_v3.build(
            ledger, loaded["data"], loaded["errors"], context), phases)
        trace = measured("postprocess.trace_projection", lambda: investigation.project_trace(ledger, calls), phases)
        rendered = measured("postprocess.artifact_json_render", lambda: json.dumps({
            "verification": built, "query_trace": trace}, ensure_ascii=False, indent=2), phases)
        profile("postprocess-native-extraction", lambda: probe._transcript_calls(str(run)) or [], out)
        profile("postprocess-verdict-build", lambda: verdict_v3.build(
            ledger, loaded["data"], loaded["errors"], context), out)
        profile("postprocess-trace-projection", lambda: investigation.project_trace(ledger, calls), out)
    finally:
        delivery_budget.fit = original_fit
    return {"native_calls": len(calls), "trace_steps": len(trace["steps"]),
        "native_tool_counts": dict(Counter(c.get("tool") for c in calls)),
        "fit_calls_in_entire_postprocess_including_profiles": len(fit_calls),
        "artifact_json_chars": len(rendered), "artifact_json_bytes": len(rendered.encode()),
        "document_errors": loaded["errors"], "identity_bound": built["identity"]["bound"],
        "identity": built["identity"], "trace_identity": trace_identity,
        "note": "Native extraction, identities, parse, build and trace projection separated. No original artifacts written; wrapper target checks and disk write cost excluded."}


def selection(ledger, paths, out, phases):
    from migloop import investigation
    batch = json.loads(paths["dice24_request"].read_text(encoding="utf-8"))
    request = batch["requests"][0]
    args = dict(request["args"])
    if "scope" in request:
        args["scope"] = request["scope"]
    samples = []
    selected = None
    for index in range(3):
        started = time.perf_counter()
        selected = investigation.query(ledger, request["tool"], args)
        samples.append(time.perf_counter() - started)
        print(json.dumps({"selection_repeat": index, "seconds": samples[-1]}), flush=True)
    profiled = profile("single-changes-selection",
        lambda: investigation.query(ledger, request["tool"], args), out)
    if investigation.digest(profiled) != investigation.digest(selected):
        raise RuntimeError("Profiled query changed selected evidence")
    return {"request": request, "unprofiled_seconds": samples,
            "unprofiled_median": statistics.median(samples),
            "selected_sha256": investigation.digest(selected),
            "selected_chars": len(json.dumps(selected, ensure_ascii=False, separators=(",", ":")))}


def cache_audit(ledger, paths, out, phases):
    from migloop import investigation, raw_events
    batch = json.loads(paths["dice24_request"].read_text(encoding="utf-8"))
    request = batch["requests"][0]
    args = dict(request["args"])
    if "scope" in request:
        args["scope"] = request["scope"]
    original = raw_events._source_index
    results, accesses = [], []

    def source_index(path, registry_key):
        before = time.perf_counter()
        value = original(path, registry_key)
        accesses.append({"source": path, "status": value[2],
                         "seconds": time.perf_counter() - before})
        return value

    raw_events._source_index = source_index
    try:
        for repeat in range(2):
            accesses = []
            before = time.perf_counter()
            data = investigation.query(ledger, request["tool"], args)
            elapsed = time.perf_counter() - before
            row = {"repeat": repeat, "seconds": elapsed,
                   "accesses": accesses, "counts": dict(Counter(a["status"] for a in accesses)),
                   "cache_entries_after": len(raw_events._CACHE),
                   "cache_bytes_after": raw_events._CACHE_BYTES,
                   "selected_sha256": investigation.digest(data)}
            results.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "accesses"}), flush=True)
    finally:
        raw_events._source_index = original
    return {"cache_budget_bytes": raw_events._CACHE_BUDGET,
            "max_source_cache_bytes": raw_events._MAX_SOURCE_CACHE_BYTES, "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--eval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("replay", "postprocess", "selection", "cache"), required=True)
    parser.add_argument("--postprocess-case", choices=("F10-03", "F10-07"), default="F10-03")
    parser.add_argument("--postprocess-rep", choices=(1, 2), type=int, default=1)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    with (args.out / "profile-script.py").open("xb") as stream:
        stream.write(Path(__file__).read_bytes())
    before = package(args.repo)
    paths = {"dice24_request": args.eval / "tools-v3-atom-overview-audit/20260910T164423Z/F10-03/request.json",
             "entry_trace": args.eval / "tools-v3/runs/F10-07/rep1/query-trace.json",
             "settings": args.eval / "tools-v3/settings/F10-03.json",
             "old_run": args.eval / f"tools-v3/runs/{args.postprocess_case}/rep{args.postprocess_rep}"}
    settings = json.loads(paths["settings"].read_text(encoding="utf-8"))["mcp_servers"]["migloop"]
    for key in list(os.environ):
        if key.startswith("MIGLOOP_"):
            del os.environ[key]
    os.environ.update(settings["env"])
    phases = []
    sys.path.insert(0, str(args.repo / "src"))
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    from migloop import service, transcript_store
    phases.append({"phase": "module_import", "wall_seconds": time.perf_counter() - start})
    sid = settings["env"]["MIGLOOP_FROZEN_ANCHOR"]
    ledger = measured("ledger_fresh_process", lambda: service.session_ledger(sid), phases)
    results = {"replay": replay, "postprocess": postprocess, "selection": selection, "cache": cache_audit}[args.mode](
        ledger, paths, args.out, phases)
    after = package(args.repo)
    source_stats = {p: [os.stat(p).st_size, os.stat(p).st_mtime_ns] for p in transcript_store.sources(ledger)}
    data = {"schema": "migloop-offline-delivery-profile/1", "mode": args.mode,
        "started_at": started_at, "ended_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(args.repo), "python": sys.version, "pid": os.getpid(),
        "script_sha256": sha(Path(__file__)), "package_before": before,
        "package_after": after, "package_stable": before == after,
        "inputs": {k: {"path": str(v), "sha256": sha(v)} for k, v in paths.items() if v.is_file()},
        "postprocess_input_hashes": {n: sha(paths["old_run"] / n) for n in ("report.md", "transcript.jsonl")},
        "source_count": len(source_stats), "source_stats": source_stats,
        "phases": phases, "results": results, "model_calls": 0,
        "limitations": ["Fresh Python cache, not guaranteed cold OS filesystem cache.",
            "cProfile changes timing; compare unprofiled measurements separately.",
            "One Dice development pool; no held-out answers or general accuracy inference.",
            "MCP wrapper size is a local envelope, not the investigator final token context.",
            "Warm replay is not model end-to-end performance; no model/network/queue overhead."]}
    dump(args.out / "result.json", data)
    print(json.dumps({"done": args.mode, "package_stable": before == after,
                      "result": str(args.out / "result.json")}), flush=True)
    if before != after:
        raise SystemExit("Runtime package changed during measurement")


if __name__ == "__main__":
    main()
