"""Read-only delivery audit of paired review; never grades semantic correctness."""

import argparse
import importlib.util
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("review_delivery_helpers", HERE / "luna-audit.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def history_binding(parent, child, parent_id, parent_bytes):
    """Check a native parent reference/copy; caller must seal parent bytes."""
    meta = child[0]["payload"]
    base = meta.get("history_base", {})
    reference_ok = (
        meta.get("forked_from_id") == parent_id
        and meta.get("id", meta.get("session_id")) != parent_id
        and meta.get("history_mode") == "paginated"
        and base.get("thread_id") == parent_id
        and base.get("end_ordinal_exclusive") == parent[-1]["ordinal"] + 1
        and meta.get("forked_from_ordinal_exclusive") == parent[-1]["ordinal"] + 1
        and base.get("end_byte_offset") == parent_bytes
    )
    previous = [r["payload"] for r in parent if r.get("type") == "response_item"]
    current = [r["payload"] for r in child if r.get("type") == "response_item"]
    inline_ok = (bool(previous) and meta.get("forked_from_id") == parent_id
                 and meta.get("id", meta.get("session_id")) != parent_id
                 and current[:len(previous)] == previous)
    result = {"native_history_binding_confirmed": reference_ok or inline_ok,
              "mode": "immutable_parent_reference" if reference_ok else "inline_copy" if inline_ok else "unconfirmed",
              "history_base": base,
              "parent_final_ordinal": parent[-1]["ordinal"], "parent_bytes": parent_bytes,
              "limit": "Verifies native fork provenance, not which original content the model attended to; original copy-only alarm preserved."}
    return result


def audit_history_reference(out, identity, arm):
    """Separate audit preserves the initial copy-only alarm and frozen runs."""
    spec = importlib.util.spec_from_file_location("paired_history_runner", HERE / "run_paired_review.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    manifest = runner.verify(out)
    case = manifest["cases"][identity]
    run = out / identity / arm / "rep1"
    parent_path = Path(case["original"]) / "transcript.jsonl"
    parent, child = helpers.rows(parent_path), helpers.rows(run / "transcript.jsonl")
    result = history_binding(parent, child, case["parent_session"], parent_path.stat().st_size)
    result["parent_sha256"] = case["parent_sha256"]
    if result["native_history_binding_confirmed"]:
        result["usage"] = runner.review_usage(parent, child, (run.parent / "prompt.md").read_text(encoding="utf-8"))
    with (run / "fork-reference-audit.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


def audit(out, identity, arm):
    run = out / identity / arm / "rep1"
    target = run / "review-delivery.json"
    if target.exists():
        raise FileExistsError("Preserve previous audit")
    prompt = (out / identity / arm / "prompt.md").read_text(encoding="utf-8")
    native = helpers.rows(run / "transcript.jsonl")
    start = next(i for i, row in enumerate(native)
                 if row.get("type") == "response_item" and row["payload"].get("role") == "user"
                 and any(c.get("text") == prompt for c in row["payload"].get("content", []) if isinstance(c, dict)))
    calls, wrappers, finals = {}, [], []
    for line, row in enumerate(native[start + 1:], start + 2):
        if row.get("type") != "response_item":
            continue
        p = row["payload"]
        if p.get("type") in ("function_call", "custom_tool_call"):
            calls[p["call_id"]] = {"name": p["name"], "line": line, "input": p.get("arguments", p.get("input"))}
        elif p.get("type") in ("function_call_output", "custom_tool_call_output"):
            decoded = list(helpers.views(p.get("output")))
            wrappers.append({"line": line, "call_id": p.get("call_id"),
                             "tool": calls.get(p.get("call_id"), {}).get("name"), "views": decoded,
                             "truncated": any(re.search(r"Warning: truncated output|…\d+ tokens truncated…", text) for _, text in decoded)})
        elif p.get("type") == "message" and p.get("role") == "assistant" and p.get("phase") == "final_answer":
            finals.append("\n".join(c.get("text", "") for c in p.get("content", []) if isinstance(c, dict)))
    owned = {value for w in wrappers for _, text in w["views"]
             for value in re.findall(r"^RESULT ([0-9a-f]{16}) ", text, re.MULTILINE)}
    bodies, frames = [], []
    with sqlite3.connect((out / identity / "index.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        for frame in db.execute("SELECT * FROM frames ORDER BY run,offset"):
            if frame["run"] not in owned:
                continue
            matching = next((w for w in wrappers if any(frame["text"] in text for _, text in w["views"])), None)
            span = re.match(r"RESULT [0-9a-f]+ chars=\d+ range=(\d+):(\d+)\n", frame["text"])
            if not span:
                raise ValueError("Unknown frame format")
            frames.append({"run": frame["run"], "offset": int(span[1]), "end": int(span[2]),
                           "visible_complete": matching is not None,
                           "native_line": matching["line"] if matching else None})
        for batch in db.execute("SELECT * FROM runs WHERE kind='query' ORDER BY rowid"):
            if batch["id"] not in owned:
                continue
            selected = [f for f in frames if f["run"] == batch["id"]]
            data = json.loads(batch["data"])
            bodies.append({"id": batch["id"], "chars": len(batch["body"]),
                           "body_sent_complete": helpers.covered([(f["offset"], f["end"]) for f in selected], len(batch["body"])),
                           "body_visible_complete": helpers.covered([(f["offset"], f["end"]) for f in selected if f["visible_complete"]], len(batch["body"])),
                           "queries": [{"query": q["query"], "ok": q["ok"], "error": q.get("error"),
                                        "row_next": q.get("data", {}).get("next"), "total": q.get("data", {}).get("total")}
                                       for q in data]})
    result = {"semantic_verified": False, "model_calls": 0, "new_turn_native_start": start + 1,
              "tools": dict(Counter(c["name"] for c in calls.values())),
              "native_calls": calls, "wrappers": [{k: v for k, v in w.items() if k != "views"} for w in wrappers],
              "host_truncations": sum(w["truncated"] for w in wrappers),
              "frames_sent": len(frames), "frames_visible": sum(f["visible_complete"] for f in frames),
              "bodies": bodies, "query_stats": helpers.query_stats(bodies),
              "final_authenticated": bool(finals) and finals[-1].strip() == (run / "report.md").read_text(encoding="utf-8").strip()}
    with target.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("tools", "host_truncations", "frames_sent", "frames_visible", "query_stats", "final_authenticated")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--arm", choices=("raw", "inquiry"), required=True)
    args = parser.parse_args()
    audit(args.out.resolve(), args.case, args.arm)
    audit_history_reference(args.out.resolve(), args.case, args.arm)
