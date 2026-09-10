"""Offline witness and native-change audit; never imports migloop or runs history.

This validates provenance, NOT causal truth. Report-only modifications cannot
qualify a file. Outputs are new artifacts; source pools are never modified.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def instant(value):
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must have timezone")
    return result.astimezone(timezone.utc)


def text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from text_values(child)


def same_target(path, target):
    # Do not conflate AppScope/app.json5 with another directory's app.json5.
    if not isinstance(path, str):
        return False
    path, target = path.replace("\\", "/"), target.replace("\\", "/")
    return path == target or path.endswith("/" + target)


class Pool:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        self.rows = {}

    def load(self, relative):
        resolved = (self.path / relative).resolve(strict=True)
        if not resolved.is_relative_to(self.path):
            raise ValueError("Source escapes pool")
        if relative not in self.rows:
            raw = resolved.read_bytes()
            # Physical JSONL lines, not splitlines()'s additional separators.
            records = raw.split(b"\n")
            if records and records[-1] == b"":
                records.pop()
            self.rows[relative] = (digest(raw), [line.removesuffix(b"\r") for line in records])
        return self.rows[relative]

    def record(self, loc):
        _, lines = self.load(loc["source"])
        number = loc["line"]
        if type(number) is not int or not 1 <= number <= len(lines):
            raise ValueError("Invalid physical line")
        raw = lines[number - 1]
        if loc.get("sha256") and loc["sha256"] != digest(raw):
            raise ValueError("Witness bytes drifted")
        return json.loads(raw.decode("utf-8", errors="strict")), digest(raw)

    def witness(self, spec):
        row, signature = self.record(spec)
        value = row
        for part in spec.get("selector", []):
            if isinstance(value, list) and (type(part) is not int or not 0 <= part < len(value)):
                raise ValueError("Invalid field index")
            value = value[part]
        if not isinstance(value, str):
            raise ValueError("Witness must select an exact text field")
        literals = spec.get("contains")
        if not literals or not all(isinstance(x, str) and x for x in literals):
            raise ValueError("Witness needs nonempty literal excerpts")
        offsets = []
        for literal in literals:
            offset = value.find(literal)
            if offset < 0:
                raise ValueError(f"Witness literal not present: {spec.get('id')}")
            offsets.append({"start": offset, "text": literal})
        return {**spec, "sha256": signature, "timestamp": row.get("timestamp"),
                "field_sha256": digest(value.encode("utf-8")), "excerpts": offsets,
                "verified": "location_and_literal_only_not_semantic_support"}

    def calls(self):
        calls, sources, unsupported, patch_events = [], [], [], []
        for path in sorted(self.path.rglob("*.jsonl")):
            relative = path.relative_to(self.path).as_posix()
            signature, lines = self.load(relative)
            sources.append({"source": relative, "sha256": signature, "lines": len(lines)})
            uses, outputs = defaultdict(list), defaultdict(list)
            for number, raw in enumerate(lines, 1):
                row = json.loads(raw.decode("utf-8", errors="strict"))
                base = {"source": relative, "line": number, "sha256": digest(raw),
                        "timestamp": row.get("timestamp")}
                if row.get("type") == "event_msg":
                    event = row.get("payload") or {}
                    if event.get("type") == "patch_apply_end":
                        # Code-host inner events have their OWN ids. Preserve the
                        # observed effect without inventing an outer-call join.
                        patch_events.append({**base, "effect_id": event.get("call_id"),
                            "success": event.get("success"), "changes": event.get("changes"),
                            "outer_call_id": None,
                            "provenance": "native_patch_event_not_model_visible_return"})
                content = (row.get("message") or {}).get("content")
                if isinstance(content, list):
                    for index, item in enumerate(content):
                        if not isinstance(item, dict):
                            continue
                        loc = {**base, "block": index, "format": "claude"}
                        if item.get("type") == "tool_use":
                            uses[item.get("id")].append({**loc, "tool": item.get("name"),
                                "input": item.get("input"), "native": item})
                        elif item.get("type") == "tool_result":
                            outputs[item.get("tool_use_id")].append({**loc, "native": item})
                if row.get("type") == "response_item":
                    item = row.get("payload") or {}
                    kind = item.get("type")
                    loc = {**base, "format": "codex"}
                    if kind in ("function_call", "custom_tool_call"):
                        argument = item.get("input", item.get("arguments"))
                        if kind == "function_call" and isinstance(argument, str):
                            try:
                                argument = json.loads(argument)
                            except json.JSONDecodeError:
                                pass  # Preserve unparsed arguments; do not infer effect.
                        uses[item.get("call_id")].append({**loc, "tool": item.get("name"),
                                                           "input": argument, "native": item})
                    elif kind in ("function_call_output", "custom_tool_call_output"):
                        outputs[item.get("call_id")].append({**loc, "native": item})
            for identity in sorted(set(uses) | set(outputs), key=lambda x: str(x)):
                opened, returned = uses[identity], outputs[identity]
                pairing = "unique" if identity and len(opened) == len(returned) == 1 else "missing_or_ambiguous"
                if pairing == "unique":
                    start = (opened[0]["line"], opened[0].get("block", -1))
                    end = (returned[0]["line"], returned[0].get("block", -1))
                    if end <= start:
                        pairing = "out_of_order"
                calls.append({"source": relative, "call_id": identity, "uses": opened,
                              "results": returned, "pairing": pairing})
                if pairing != "unique":
                    unsupported.append({"source": relative, "call_id": identity, "pairing": pairing})
        return {"calls": calls, "sources": sources, "pairing_gaps": unsupported,
                "patch_events": patch_events}


def patch_paths(body):
    if not isinstance(body, str) or not body.startswith("*** Begin Patch"):
        return []
    if "*** End Patch" not in body:
        return []
    return re.findall(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", body, flags=re.M)


def native_target(use, target):
    name, argument = use.get("tool"), use.get("input")
    if use["format"] == "claude" and name in ("Write", "Edit", "MultiEdit") and isinstance(argument, dict):
        return same_target(argument.get("file_path"), target)
    if use["format"] == "codex" and name in ("apply_patch", "functions.apply_patch"):
        return any(same_target(path, target) for path in patch_paths(argument))
    return False


def result_success(result):
    item = result["native"]
    if result["format"] == "claude":
        # This is a native tool success receipt, not an independent disk snapshot.
        if "is_error" in item:
            return item["is_error"] is False
        body = item.get("content")
        return isinstance(body, str) and (
            body.startswith("File created successfully at:") or
            body.startswith("The file ") and " has been updated successfully" in body)
    body = item.get("output")
    if not isinstance(body, str):
        return False
    try:
        wrapper = json.loads(body)
    except json.JSONDecodeError:
        wrapper = None
    if isinstance(wrapper, dict):
        return wrapper.get("metadata", {}).get("exit_code") == 0 and "Success. Updated the following files:" in str(wrapper.get("output", ""))
    return "Success. Updated the following files:" in body and not re.search(r"\b(?:Error|Failed)\b", body)


def inventory(data, target, after, until):
    start, end = instant(after), instant(until)
    if start >= end:
        raise ValueError("Observation window is empty")
    native, mentions, other, unknown = [], [], [], []
    leaf = target.replace("\\", "/").rsplit("/", 1)[-1]
    for call in data["calls"]:
        uses, returns = call["uses"], call["results"]
        visible = []
        for side in uses + returns:
            try:
                time = instant(side.get("timestamp"))
            except (ValueError, TypeError):
                unknown.append({"source": side["source"], "line": side["line"], "call_id": call["call_id"]})
                continue
            if start < time <= end:
                visible.append(side)
        if not visible:
            continue
        item = {"source": call["source"], "call_id": call["call_id"], "pairing": call["pairing"],
                "use_lines": [x["line"] for x in uses], "result_lines": [x["line"] for x in returns]}
        targets = [use for use in uses if native_target(use, target)]
        if targets:
            confirmed = False
            if call["pairing"] == "unique":
                try:
                    t0, t1 = instant(uses[0]["timestamp"]), instant(returns[0]["timestamp"])
                    confirmed = start < t0 <= t1 <= end and result_success(returns[0])
                except (ValueError, TypeError):
                    pass
            native.append({**item, "confirmed_post_boundary_tool_receipt": confirmed,
                           "uses": uses, "results": returns})
        elif any(leaf.casefold() in "\n".join(text_values(x.get("native"))).casefold() for x in visible):
            mentions.append(item)
        else:
            # Retain ALL other native calls as an audit denominator, not just
            # commands recognized by a second heuristic parser. No write claim.
            other.append(item)
    patches = []
    for event in data.get("patch_events", []):
        if not isinstance(event.get("changes"), dict) or not any(same_target(p, target) for p in event["changes"]):
            continue
        try:
            time = instant(event["timestamp"])
        except (ValueError, TypeError):
            unknown.append({"source": event["source"], "line": event["line"], "effect_id": event["effect_id"]})
            continue
        if start < time <= end:
            patches.append({**event, "confirmed_post_boundary_effect_receipt": event["success"] is True})
    return {"target": target, "after": after, "until": until, "native_target_calls": native,
            "recorded_patch_effects": patches,
            "other_related_calls": mentions, "other_calls_for_effect_review": other,
            "unknown_time_records": unknown,
            "scope": "Recorded native calls only; receipts are not independent disk/behavior observations; shell effects require manual adjudication"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool", type=Path, required=True)
    ap.add_argument("--target", action="append", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    pool, out = Pool(args.pool), args.out.resolve()
    if out.exists() or out.is_relative_to(pool.path):
        raise ValueError("Output must be new and outside the source pool")
    data = pool.calls()
    result = {"schema": "file-first-10-native-audit/1", "pool": str(pool.path),
              "source_files": data["sources"], "pairing_gaps": data["pairing_gaps"],
              "files": [inventory(data, t, args.after, args.until) for t in args.target],
              "semantic_reference_validated": False}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"out": str(out), "source_files": len(data["sources"]),
        "pairing_gaps": len(data["pairing_gaps"]), "targets": [{"target": x["target"],
        "native_calls": len(x["native_target_calls"]), "successful_post_boundary": sum(
            c["confirmed_post_boundary_tool_receipt"] for c in x["native_target_calls"]),
        "patch_effect_receipts": sum(c["confirmed_post_boundary_effect_receipt"] for c in x["recorded_patch_effects"]),
        "related_calls": len(x["other_related_calls"]), "other_calls": len(x["other_calls_for_effect_review"])}
        for x in result["files"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
