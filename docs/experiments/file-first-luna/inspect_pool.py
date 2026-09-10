"""Offline raw-record inventory for reference authors; no migloop ledger imports.

Exact target mentions select records, not proven effects. Non-target shell calls
with write-capable syntax are retained as a separate completeness-gap inventory.
Never executes historical commands or modifies input records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


WRITE_SYNTAX = re.compile(r"write_text|write_bytes|open\([^\n]*['\"](?:w|a|r\+)|\b(?:cp|mv|rm|tee|touch|sed\s+-i|apply_patch|patch)\b|(?<![=>])>{1,2}(?![=>])", re.I)


def texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from texts(child)


def scan(pool: Path, target: str) -> dict:
    leaf = target.replace("\\", "/").rsplit("/", 1)[-1]
    uses, results, mentions, gaps, files = [], {}, [], [], []
    for path in sorted(pool.rglob("*.jsonl")):
        relative = path.relative_to(pool).as_posix()
        digest = hashlib.sha256()
        for line, raw in enumerate(path.open("rb"), 1):
            digest.update(raw)
            row = json.loads(raw)
            base = {"file": relative, "line": line, "ts": row.get("timestamp"),
                    "record_sha256": hashlib.sha256(raw.rstrip(b"\r\n")).hexdigest()}
            content = (row.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block, item in enumerate(content):
                if not isinstance(item, dict):
                    continue
                loc = {**base, "block": block}
                if item.get("type") == "tool_use":
                    inp = item.get("input") or {}
                    body = "\n".join(texts(inp))
                    use = {**loc, "tool_use_id": item.get("id"), "tool": item.get("name"), "input": inp}
                    if leaf.casefold() in body.casefold():
                        uses.append(use)
                    elif item.get("name") in ("Bash", "Shell") and WRITE_SYNTAX.search(body):
                        gaps.append(use)
                elif item.get("type") == "tool_result":
                    identity = item.get("tool_use_id")
                    result = {**loc, "tool_use_id": identity, "is_error": item.get("is_error", False),
                              "content": item.get("content")}
                    results.setdefault((relative, identity), []).append(result)
                    if any(leaf.casefold() in text.casefold() for text in texts(item.get("content"))):
                        mentions.append({**loc, "tool_use_id": identity, "kind": "result_mentions"})
                elif any(leaf.casefold() in text.casefold() for text in texts(item)):
                    mentions.append({**loc, "kind": item.get("type")})
        files.append({"file": relative, "sha256": digest.hexdigest()})
    for use in uses + gaps:
        paired = results.get((use["file"], use["tool_use_id"]), [])
        use["results"] = paired
        use["pairing"] = "unique" if len(paired) == 1 else "missing" if not paired else "ambiguous"
    return {"schema": "file-first-raw-inventory/1", "pool": str(pool.resolve()), "target": target,
            "scope": "literal target mentions plus broad non-target write-syntax gaps; not exhaustive effect inference",
            "target_calls": sorted(uses, key=lambda r: (r["ts"] or "", r["file"], r["line"], r["block"])),
            "other_mentions": mentions, "unresolved_write_capability": gaps, "source_files": files}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("scan")
    collect.add_argument("--pool", type=Path, required=True)
    collect.add_argument("--target", required=True)
    collect.add_argument("--out", type=Path, required=True)
    show = sub.add_parser("show")
    show.add_argument("inventory", type=Path)
    show.add_argument("--after", default="")
    show.add_argument("--before", default="~")
    show.add_argument("--tool")
    show.add_argument("--contains", default="")
    show.add_argument("--line", type=int)
    show.add_argument("--file", default="")
    show.add_argument("--chars", type=int, default=600)
    show.add_argument("--gaps", action="store_true")
    records = sub.add_parser("records", help="Read original records, never execute their contents")
    records.add_argument("source", type=Path)
    records.add_argument("--match", default="")
    records.add_argument("--start", type=int, default=1)
    records.add_argument("--end", type=int, default=10**9)
    records.add_argument("--chars", type=int, default=600)
    records.add_argument("--kind", default="")
    args = ap.parse_args()
    if args.command == "scan":
        if args.out.exists() or args.out.resolve().is_relative_to(args.pool.resolve()):
            raise ValueError("Output must be new and outside input pool")
        data = scan(args.pool, args.target)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        print(json.dumps({"out": str(args.out), **{key: len(data[key]) for key in (
            "target_calls", "other_mentions", "unresolved_write_capability", "source_files")}}))
    elif args.command == "records":
        regex = re.compile(args.match, re.I) if args.match else None
        with args.source.open(encoding="utf-8") as handle:
            for line, raw in enumerate(handle, 1):
                if not args.start <= line <= args.end:
                    continue
                row = json.loads(raw)
                content = (row.get("message") or {}).get("content")
                blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
                for block, item in enumerate(blocks):
                    if not isinstance(item, dict) or args.kind and item.get("type") != args.kind:
                        continue
                    body = "\n".join(texts(item))
                    if regex and not regex.search(body):
                        continue
                    print(json.dumps({"line": line, "block": block, "ts": row.get("timestamp"),
                        "role": (row.get("message") or {}).get("role"), "type": item.get("type"),
                        "chars": len(body), "text": body[:args.chars]}, ensure_ascii=False))
    else:
        data = json.loads(args.inventory.read_text(encoding="utf-8"))
        for row in data["unresolved_write_capability" if args.gaps else "target_calls"]:
            if not args.after <= (row["ts"] or "") <= args.before:
                continue
            if args.tool and row["tool"] != args.tool or args.line and row["line"] != args.line:
                continue
            body = json.dumps(row["input"], ensure_ascii=False)
            if args.file not in row["file"] or args.contains.casefold() not in body.casefold():
                continue
            paired = row["results"]
            print(json.dumps({"at": f'{row["file"]}:{row["line"]}/{row["block"]}', "ts": row["ts"],
                "tool": row["tool"], "id": row["tool_use_id"], "input": body[:args.chars],
                "input_chars": len(body), "pairing": row["pairing"],
                "result": [{"line": r["line"], "ts": r["ts"], "error": r["is_error"],
                            "text": "\n".join(texts(r["content"]))[:args.chars]} for r in paired]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
