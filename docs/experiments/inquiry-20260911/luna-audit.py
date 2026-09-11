"""Offline native-delivery and same-investigator submission audit; no model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def views(value, path="output", depth=0):
    """Only decode whole valid JSON, never repair/trust a service-side packet."""
    if depth > 12:
        return
    if isinstance(value, str):
        yield path, value
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return
        if decoded != value:
            yield from views(decoded, path + "/json", depth + 1)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from views(child, f"{path}/{index}", depth + 1)
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from views(child, f"{path}/{key}", depth + 1)


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def covered(ranges, total):
    end = 0
    for start, stop in sorted(ranges):
        if start > end:
            return False
        end = max(end, stop)
    return end >= total


def audit(out):
    started = time.perf_counter()
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    sys.path.insert(0, str(manifest.get('code_root', out / "code/src")))
    from migloop.inquiry.engine import Engine
    from migloop.inquiry.store import Store

    run = out / "runs/inquiry/rep1"
    if (run / "delivery-audit.json").exists():
        raise FileExistsError("Never overwrite prior audit")
    events = rows(run / "events.jsonl")
    native = rows(run / "transcript.jsonl")
    calls, wrappers, finals = {}, [], []
    for line, row in enumerate(native, 1):
        if row.get("type") != "response_item":
            continue
        payload = row.get("payload") or {}
        typ = payload.get("type")
        if typ in ("custom_tool_call", "function_call"):
            calls[payload["call_id"]] = payload
        elif typ in ("custom_tool_call_output", "function_call_output"):
            call = calls.get(payload.get("call_id"), {})
            name = call.get("name", "")
            if name not in ("exec", "wait") and not name.startswith("mcp__"):
                continue
            output = payload.get("output")
            decoded = list(views(output))
            wrappers.append({"line": line, "call_id": payload.get("call_id"), "tool": name,
                             "output": output, "views": decoded,
                             "truncated": any(re.search(r"Warning: truncated output|…\d+ tokens truncated…", text)
                                              for _, text in decoded)})
        elif typ == "message" and payload.get("role") == "assistant" and payload.get("phase") == "final_answer":
            finals.append("\n".join(item.get("text", "") for item in payload.get("content", []) if isinstance(item, dict)))

    store = Store(manifest.get('index_path', out / "index.sqlite"))
    engine = Engine(store, origin="offline_audit")
    # Shared immutable source index may contain other investigators' logs. Only
    # results actually returned by this native run enter its delivery audit.
    owned = set()
    for event in events:
        item = event.get('item', {})
        if event.get('type') == 'item.completed' and item.get('type') == 'mcp_tool_call':
            for _, text in views(item.get('result')):
                owned.update(re.findall(r'^RESULT ([0-9a-f]{16}) ', text, re.M))
    frames, bodies, observations = [], [], []
    for frame in store.rows("SELECT * FROM frames ORDER BY run,offset"):
        if frame['run'] not in owned:
            continue
        match = next(((wrapper, path, text) for wrapper in wrappers for path, text in wrapper["views"]
                      if frame["text"] in text), None)
        if match:
            wrapper, path, text = match
        else:
            text = "No complete frame in recorded model-visible outputs"
        observations.append((frame["run"], frame["offset"], int(match is not None), text))
        span = re.match(r'RESULT [0-9a-f]+ chars=\d+ range=(\d+):(\d+)\n', frame['text'])
        if not span:
            raise ValueError('Unknown recorded frame format')
        frames.append({"run": frame["run"], "offset": frame["offset"], "end": int(span[2]), "sha256": frame["sha"],
                       "visible_complete": match is not None,
                       "wrapper_line": match[0]["line"] if match else None,
                       "decoded_path": match[1] if match else None})
    for query in store.rows("SELECT * FROM runs WHERE kind='query' ORDER BY rowid"):
        if query['id'] not in owned:
            continue
        length = len(query["body"])
        returned = [f for f in frames if f["run"] == query["id"]]
        all_ranges = [(f["offset"], f['end']) for f in returned]
        visible_ranges = [(f["offset"], f['end']) for f in returned if f["visible_complete"]]
        data = json.loads(query["data"])
        parts, cursor = [], 0
        for number, item in enumerate(data, 1):
            rendered = engine.render(number, item)
            stop = cursor + len(rendered)
            overlap = [(max(cursor, start) - cursor, min(stop, end) - cursor)
                       for start, end in visible_ranges if start < stop and end > cursor]
            parts.append({"query": item["query"], "ok": item["ok"],
                          "error": item.get("error"), "total": item.get("data", {}).get("total"),
                          "row_next": item.get("data", {}).get("next"),
                          "result_range": [cursor, stop],
                          "result_visible": "complete" if covered(overlap, len(rendered)) else "partial" if overlap else "none"})
            cursor = stop + 2
        if "\n\n".join(engine.render(i + 1, item) for i, item in enumerate(data)) != query["body"]:
            raise ValueError("Saved batch body differs from frozen renderer")
        bodies.append({"id": query["id"], "chars": length,
                       "body_sent_complete": covered(all_ranges, length),
                       "body_visible_complete": covered(visible_ranges, length),
                       "queries": parts})
    # Matching is read-only. Persist its observations in one short transaction,
    # rather than competing with another investigator once per frame.
    store.db.execute("PRAGMA busy_timeout=30000")
    with store.db:
        store.db.executemany("INSERT INTO visible VALUES(?,?,?,?)", observations)
    completed = [e["item"] for e in events if e.get("type") == "item.completed"]
    submissions = [i for i in completed if i.get("type") == "mcp_tool_call" and i.get("tool") == "submit"]
    final = (run / "report.md").read_text(encoding="utf-8")
    saved = store.rows("SELECT id,request,data FROM runs WHERE kind='report' ORDER BY rowid")
    selected = [r for r in saved if r["id"] in final and sha(r["request"]) in final]
    errors = []
    if len(selected) != 1:
        errors.append("Final report_id/hash does not uniquely select this index's original submission")
    if not finals or finals[-1].strip() != final.strip():
        errors.append("Final response is not authenticated against native final_answer")
    report = selected[0] if len(selected) == 1 else None
    graph = json.loads(report["data"]) if report else None
    native_bound = False
    if report:
        for submitted in submissions:
            if submitted.get("arguments", {}).get("document") != report["request"]:
                continue
            for _, text in views(submitted.get("result")):
                try:
                    result = json.loads(text)
                except ValueError:
                    continue
                if isinstance(result, dict) and result.get("report_id") == report["id"] and result.get("source_sha256") == sha(report["request"]):
                    native_bound = True
        if not native_bound:
            errors.append("No matching native MCP submit input/result")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        target = graph.get('target', graph["document"]["target"])
        case = manifest["case"]
        if not target["file"].replace("\\", "/").endswith(case["file"]):
            errors.append("Target file differs from frozen task")
        from migloop.inquiry.store import timestamp
        for key, expected in (("at", case["observation_end"]), ("since", case["generation_end"])):
            if timestamp(target.get(key)) != timestamp(expected):
                errors.append("Target time differs: " + key)
        with (run / "verdict.yaml").open("x", encoding="utf-8", newline="") as stream:
            stream.write(report["request"])
        graph["report_id"] = report["id"]
    result = {"model_calls": 0, "format_repair": False, "errors": errors,
              "native_submit_bound": native_bound, "report_id": report["id"] if report else None,
              "source_sha256": sha(report["request"]) if report else None,
              "semantic_verified": False,
              "tools": dict(Counter(i.get("tool", i.get("type")) for i in completed)),
              "host_wrappers": [{k: v for k, v in w.items() if k not in ("views", "output")} for w in wrappers],
              "frames": frames, "bodies": bodies,
              "summary": {"frames_sent": len(frames), "frames_visible_complete": sum(f["visible_complete"] for f in frames),
                          "bodies": len(bodies), "bodies_visible_complete": sum(b["body_visible_complete"] for b in bodies),
                          "host_truncated_wrappers": sum(w["truncated"] for w in wrappers)},
              "limit": "Recorded presentation only, not model attention or semantic correctness; no service packet used to fill visible gaps."}
    trace = [entry for entry in engine.trace() if entry['id'] in owned]
    for filename, value in (("delivery-audit.json", result), ("verdict.json", graph), ("query-trace.json", trace)):
        with (run / filename).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
    store.close()
    metric = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    import_cost = manifest.get('import_seconds')
    if import_cost is None:
        import_cost = json.loads((out / "import.json").read_text(encoding="utf-8"))["seconds"]
    elapsed = time.perf_counter() - started
    with (run / "system-cost.json").open("x", encoding="utf-8") as stream:
        json.dump({"offline_audit_seconds": elapsed, "model_calls": 0, "import_seconds": import_cost,
                   "warm_end_to_end_seconds": metric["elapsed_seconds"] + elapsed,
                   "cold_end_to_end_seconds": import_cost + metric["elapsed_seconds"] + elapsed}, stream, indent=2)
    return {"errors": errors, "report_id": result["report_id"], "summary": result["summary"],
            "nodes": len(graph["nodes"]) if graph else 0, "edges": len(graph["edges"]) if graph else 0,
            "mechanical_status": graph.get('mechanical_status') if graph else None,
            "unassessed_calls": len(graph.get('coverage', {}).get('unassessed', [])) if graph else None,
            "unknown_calls": len(graph.get('coverage', {}).get('unknown', [])) if graph else None,
            "missing_evidence_links": len(graph.get('missing_evidence_links', [])) if graph else None,
            "graph_issues": graph["issues"] if graph else [], "offline_audit_seconds": elapsed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    print(json.dumps(audit(parser.parse_args().out), ensure_ascii=False))
