"""Read recorded Codex output surfaces without conflating runtime and model input.

No ledger, model, historical command, schema inference or proximity-based pairing.
This audit does not certify receipt validity, causal accuracy or comprehension.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_blocks(value):
    if isinstance(value, str):
        return value, True
    if isinstance(value, list) and all(isinstance(b, dict) and b.get("type") in ("input_text", "text")
            and isinstance(b.get("text"), str) for b in value):
        return "\n".join(b["text"] for b in value), True
    return "", False


def inspect(rows):
    calls, outputs, runtime, malformed = [], [], [], []
    for line, event in enumerate(rows, 1):
        if not isinstance(event, dict):
            malformed.append(line)
            continue
        p = event.get("payload")
        if not isinstance(p, dict):
            continue
        kind = p.get("type")
        if event.get("type") == "response_item":
            if kind in ("function_call", "custom_tool_call"):
                calls.append({"line": line, "call_id": p.get("call_id"), "tool": p.get("name"),
                              "namespace": p.get("namespace")})
            elif kind in ("function_call_output", "custom_tool_call_output"):
                text, decoded = text_blocks(p.get("output"))
                warnings = re.findall(r"(?:^|\n)Warning: truncated output \(original token count: (\d+)\)", text)
                outputs.append({"line": line, "call_id": p.get("call_id"), "text_decoded": decoded,
                    "recorded_text_chars": len(text) if decoded else None,
                    "recorded_text_sha256": hashlib.sha256(text.encode()).hexdigest() if decoded else None,
                    "explicit_truncation_warning": bool(warnings),
                    "reported_original_token_counts": [int(n) for n in warnings],
                    "full_text_certified": False})
        elif (event.get("type") == "event_msg" and kind == "item_completed"
                and isinstance(p.get("item"), dict) and p["item"].get("type") == "McpToolCall"):
            item = p["item"]
            result = item.get("result")
            text, decoded = text_blocks(result.get("content") if isinstance(result, dict) else result)
            runtime.append({"line": line, "item_id": item.get("id"), "reported_call_id": item.get("call_id"),
                "tool": item.get("tool"), "server": item.get("server"), "text_decoded": decoded,
                "runtime_text_chars": len(text) if decoded else None,
                "runtime_text_sha256": hashlib.sha256(text.encode()).hexdigest() if decoded else None})
    call_ids = Counter(c["call_id"] for c in calls if isinstance(c["call_id"], str) and c["call_id"])
    for output in outputs:
        candidates = [c for c in calls if isinstance(output["call_id"], str) and output["call_id"]
                      and c["call_id"] == output["call_id"]]
        output["direct_use_line"] = candidates[0]["line"] if len(candidates) == 1 and candidates[0]["line"] < output["line"] else None
    for row in runtime:
        ids = {v for v in (row["item_id"], row["reported_call_id"]) if isinstance(v, str) and v}
        matches = ids & call_ids.keys()
        row["matching_direct_ids"] = sorted(matches)
        row["id_link_status"] = ("unique_id_only" if len(matches) == 1 and call_ids[next(iter(matches))] == 1
                                 else "ambiguous" if matches else "unlinked")
        # Identity alone is not body/protocol equivalence. Never infer an outer
        # exec link from temporal adjacency, tool text or a shared argument.
        row["model_delivery_verified"] = False
    return {"schema": "migloop-host-delivery-audit/1", "runtime_calls": runtime, "visible_outputs": outputs,
        "counts": {"runtime_mcp_calls": len(runtime), "runtime_without_direct_id_link": sum(r["id_link_status"] == "unlinked" for r in runtime),
                   "model_output_records": len(outputs), "explicit_truncated_outputs": sum(r["explicit_truncation_warning"] for r in outputs),
                   "unknown_output_shapes": sum(not r["text_decoded"] for r in outputs)},
        "malformed_lines": malformed, "model_calls": 0, "semantic_checked": False,
        "note": "Runtime return is distinct from recorded model-input text. Exact IDs are diagnostic only; no parent/child relation is guessed. A missing truncation warning is not full-delivery proof."}


def audit(run):
    path = Path(run) / "transcript.jsonl"
    before = sha(path)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            rows.append(None)
    result = inspect(rows)
    if sha(path) != before:
        raise ValueError("Transcript changed during read; retry only after run completion")
    return {**result, "transcript": str(path.resolve()), "transcript_sha256": before}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    result = audit(args.run)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"counts": result["counts"], "transcript_sha256": result["transcript_sha256"], "model_calls": 0}))


if __name__ == "__main__":
    main()
