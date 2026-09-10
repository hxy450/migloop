"""Offline dossier/recording audit. Never executes recorded commands or calls models.

The saved v1 reference is evidence to inspect, not a semantic oracle. This script
authenticates original bytes, extracts amendment witnesses, and distinguishes
native model-visible tool returns from the CLI's command-output event stream.
Text matches are navigation aids, NOT proof of source identity or comprehension.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)


def select(row, selector):
    for key in selector:
        row = row[key]
    return row


def returned_text(value):
    """Only textual content blocks, never block types or other metadata."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(returned_text(item) for item in value)
    if isinstance(value, dict):
        if value.get("type") in ("input_text", "text", "output_text") and isinstance(value.get("text"), str):
            return value["text"]
        if "content" in value:
            return returned_text(value["content"])
    return ""


class Originals:
    def __init__(self, pool):
        self.pool = Path(pool).resolve()
        self.cache = {}

    def record(self, relative, line, digest=None):
        path = (self.pool / relative).resolve()
        if not path.is_relative_to(self.pool) or type(line) is not int or line < 1:
            raise ValueError("Invalid original record location")
        if path not in self.cache:
            self.cache[path] = path.read_bytes().splitlines()
        records = self.cache[path]
        if line > len(records):
            raise ValueError("Original line missing")
        raw = records[line - 1]
        signature = hashlib.sha256(raw).hexdigest()
        if digest and signature != digest:
            raise ValueError(f"Original hash drift: {relative}:{line}")
        return json.loads(raw), signature


def witness(originals, spec, relative):
    row, signature = originals.record(relative, spec["line"])
    value = select(row, spec["selector"])
    if not isinstance(value, str):
        raise ValueError(f"Witness field must be text: {spec['id']}")
    excerpts = []
    for needle in spec.get("contains", []):
        offset = value.find(needle)
        if offset < 0:
            raise ValueError(f"Missing witness literal: {spec['id']}: {needle}")
        excerpts.append({"start_char": offset, "text": needle})
    for needle in spec.get("absent", []):
        if needle in value:
            raise ValueError(f"Unexpected witness literal: {spec['id']}: {needle}")
    return {**spec, "file": relative, "record_sha256": signature,
            "timestamp": row.get("timestamp"), "field_sha256": hashlib.sha256(value.encode()).hexdigest(),
            "field_chars": len(value), "excerpts": excerpts,
            "absence_scope": "Selected field only, not whole session or historical filesystem",
            "authentication": "literal_fields_only_not_causal_truth"}


def native_calls(path):
    """Pair model-visible response items by explicit call_id; no proximity pairing."""
    uses, outputs, headers = {}, {}, []
    for line, raw in enumerate(Path(path).read_bytes().splitlines(), 1):
        row = json.loads(raw)
        if row.get("type") != "response_item":
            continue
        payload = row.get("payload") or {}
        kind, identity = payload.get("type"), payload.get("call_id")
        if kind == "message" and payload.get("role") == "developer":
            body = "\n".join(strings(payload.get("content")))
            if "<skills_instructions>" in body:
                headers.append({"line": line, "kind": "host_skills_instructions",
                                "sha256": hashlib.sha256(body.encode()).hexdigest()})
        if not isinstance(identity, str) or not identity:
            continue
        entry = {"line": line, "timestamp": row.get("timestamp"), "payload": payload}
        if kind in ("function_call", "custom_tool_call"):
            uses.setdefault(identity, []).append(entry)
        elif kind in ("function_call_output", "custom_tool_call_output"):
            outputs.setdefault(identity, []).append(entry)
    calls = []
    for identity, entries in uses.items():
        returned = outputs.get(identity, [])
        unique = len(entries) == len(returned) == 1 and returned[0]["line"] > entries[0]["line"]
        first = entries[0]
        payload = first["payload"]
        request = payload.get("input", payload.get("arguments", ""))
        text = returned_text(returned[0]["payload"].get("output")) if unique else None
        calls.append({"step": len(calls) + 1, "call_id": identity, "tool": payload.get("name"),
                      "use_line": first["line"], "result_line": returned[0]["line"] if unique else None,
                      "use_lines": [x["line"] for x in entries], "result_lines": [x["line"] for x in returned],
                      "pairing": "unique" if unique else "missing_or_ambiguous", "input": request,
                      "text": text, "visible_chars": len(text) if text is not None else None,
                      "truncation_marker": text is not None and any(t in text.lower() for t in
                          ("truncated output", "bytes omitted", "tokens truncated"))})
    return {"calls": calls, "host_instructions": headers,
            "orphan_output_ids": sorted(set(outputs) - set(uses)),
            "scope": "Native response-item tool-return text; excludes reasoning and command-event aggregate output"}


def locate(text, needle):
    """Find literal or JSON-escaped text, without treating a miss as absence proof."""
    if text is None:
        return None
    candidate = needle
    for depth in range(4):
        offset = text.find(candidate)
        if offset >= 0:
            return {"offset": offset, "encoding_depth": depth,
                    "excerpt": text[max(0, offset - 100):offset + min(len(candidate), 300) + 100]}
        candidate = json.dumps(candidate, ensure_ascii=False)[1:-1]
    return None


def probes(calls, specs):
    out = []
    for spec in specs:
        found = []
        for call in calls:
            for field in ("input", "text"):
                haystack = call.get(field)
                if not isinstance(haystack, str):
                    haystack = json.dumps(haystack, ensure_ascii=False)
                matches = [{"needle": needle, **hit} for needle in spec["needles"]
                           if (hit := locate(haystack, needle)) is not None]
                if matches:
                    found.append({"step": call["step"], "field": field, "use_line": call["use_line"],
                                  "result_line": call["result_line"], "truncation_marker": call["truncation_marker"],
                                  "matches": matches})
        out.append({**spec, "occurrences": found,
                    "interpretation": "Literal occurrence only; may be echoed query, quoted report, or another source. Miss is not proof of unread material."})
    return out


def write_new(path, data):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--spec", type=Path, default=Path(__file__).with_name("review-spec.json"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline, out = args.baseline.resolve(), args.out.resolve()
    ref = read(baseline / "reference.json")
    manifest = read(baseline / "baseline.json")
    spec = read(args.spec)
    if sha(baseline / "reference.json") != manifest["reference_sha256"]:
        raise ValueError("Frozen reference drift")
    aliases = read(Path(__file__).parents[1] / "reference-spec.json")["aliases"]
    pools = {case["case"]: Originals(read(baseline / case["case"] / "case.json")["pool"]) for case in ref["cases"]}
    if out.exists() or out.is_relative_to(baseline) or any(out.is_relative_to(p.pool) for p in pools.values()):
        raise ValueError("Output must be new and outside frozen baseline/raw pools")
    verified, changes, witnesses = [], [], []
    for case in ref["cases"]:
        name, originals = case["case"], pools[case["case"]]
        pool_manifest = read(baseline / name / "pool-manifest.json")
        for entry in pool_manifest["entries"]:
            path = (originals.pool / entry["path"]).resolve()
            if not path.is_relative_to(originals.pool) or sha(path) != entry["sha256"]:
                raise ValueError("Pool file drift")
        for entry in case["references"].values():
            originals.record(entry["file"], entry["line"], entry["record_sha256"])
            verified.append((name, entry["file"], entry["line"]))
        for entry in case.get("oracle_witnesses", []):
            row, _ = originals.record(entry["raw_jsonl"], entry["line_1based"], entry["record_sha256"])
            selector = [int(p) if p.isdigit() else p for p in entry["json_pointer"].strip("/").split("/")]
            if entry["quote"] not in select(row, selector):
                raise ValueError("Oracle excerpt drift")
        for entry in case.get("legacy_witnesses", []):
            row, _ = originals.record(entry["file"], entry["line"], entry["record_sha256"])
            value = select(row, entry.get("selector") or [])
            for excerpt in entry.get("excerpts") or []:
                start = excerpt["start_char"]
                if not isinstance(value, str) or value[start:start + len(excerpt["text"])] != excerpt["text"]:
                    raise ValueError("Legacy excerpt drift")
        ordered = sorted(case["registered_change_events"], key=lambda e: (e["timestamp"], e["file"], e["line"], e["block"]))
        for index, event in enumerate(ordered, 1):
            row, signature = originals.record(event["file"], event["line"])
            block = row["message"]["content"][event["block"]]
            returned, result_hash = originals.record(event["result"]["file"], event["result"]["line"], event["result"]["record_sha256"])
            result_block = returned["message"]["content"][event["result"]["block"]]
            if (block.get("type") != "tool_use" or result_block.get("type") != "tool_result"
                    or block.get("id") != event["tool_use_id"] or result_block.get("tool_use_id") != block["id"]
                    or event["file"] != event["result"]["file"] or result_block.get("is_error")):
                raise ValueError("Registered change pairing mismatch")
            changes.append({"id": f"{name}:{index:02}", "case": name, "target_file": case["target_file"],
                            "source": event["file"], "use_line": event["line"], "result_line": event["result"]["line"],
                            "tool_use_id": block["id"], "tool": block["name"], "timestamp": row.get("timestamp"),
                            "input": block["input"], "result": result_block,
                            "use_sha256": signature, "result_sha256": result_hash,
                            "prior_effect_basis": event["effect_basis"],
                            "status": "Previously inspected change; raw call/result reauthenticated, semantic cause not machine certified"})
    for entry in spec["witnesses"]:
        witnesses.append(witness(pools[entry["case"]], entry, aliases.get(entry.get("alias"), entry.get("file"))))
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / "change-events.json", changes)
    write_new(out / "witnesses.json", witnesses)
    runs = []
    for name in pools:
        for arm in ("raw", "tools"):
            for rep in (1, 2):
                run_path = baseline / name / "runs" / arm / f"rep{rep}"
                trace = native_calls(run_path / "transcript.jsonl")
                result = read(run_path / "result.json")
                relevant = [s for s in spec["probes"] if s["case"] == name]
                hits = probes(trace["calls"], relevant)
                tag = f"{name}-{arm}-{rep}"
                write_new(out / f"{tag}.json", {**trace, "probes": hits, "final_report": result["response_text"]})
                calls = trace["calls"]
                rows = [f"# {tag}: native model-visible query trace", "", "Read-only recording review, not execution or semantic grading.", "",
                        "| Step | Input line | Return line | Visible chars | Truncation marker | Request preview |", "|---|---:|---:|---:|---|---|"]
                for c in calls:
                    preview = str(c["input"]).replace("\n", " ").replace("|", "\\|")[:200]
                    rows.append(f"| {c['step']} | {c['use_line']} | {c['result_line']} | {c['visible_chars']} | {c['truncation_marker']} | {preview} |")
                with (out / f"{tag}.md").open("x", encoding="utf-8") as handle:
                    handle.write("\n".join(rows) + "\n")
                runs.append({"run": tag, "calls": len(calls), "host_instructions": trace["host_instructions"],
                             "truncated_returns": sum(c["truncation_marker"] for c in calls),
                             "ambiguous_pairs": sum(c["pairing"] != "unique" for c in calls),
                             "input_skill_steps": [c["step"] for c in calls if "SKILL.md" in str(c["input"])],
                             "transcript_sha256": sha(run_path / "transcript.jsonl"), "result_sha256": sha(run_path / "result.json")})
    summary = {"schema": "migloop-offline-review/2", "baseline": str(baseline), "spec_sha256": sha(args.spec),
               "script_sha256": sha(__file__), "reference_sha256": sha(baseline / "reference.json"),
               "verified_reference_locations": len(verified), "registered_changes": len(changes), "witnesses": len(witnesses),
               "runs": runs, "semantic_truth_certified": False, "opaque_effect_completeness_proven": False,
               "independent_reviewer": False, "paid_model_calls": 0, "production_code_changed": False}
    write_new(out / "audit.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
