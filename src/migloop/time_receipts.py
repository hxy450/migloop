"""Runtime-generated temporal query receipts; no model-authored navigation.

Hashes bind recorded request/response bytes, not semantic truth or a digital
signature. Source/provider authentication remains the run recorder's job.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from . import atoms

MARKER = "\nMIGLOOP_TIME_RECEIPT "


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def canonical(tool: str, request: dict[str, Any]) -> dict[str, Any]:
    from .atom_queries import parameters
    args = {k: v for k, v in request.items() if k not in ("sid", "via")}
    if tool in ("file", "agent", "diff") and args.get("v") is None and args.get("at") is None:
        args["at"] = "latest"
    normalized = parameters(tool, args)
    # The old protocol had no view selector. Keep already-recorded request
    # hashes verifiable; do not reinterpret their bodies using today's default.
    # Explicit record/section selectors belong to the new request identity.
    if tool in ("file", "agent") and args.get("view") is None:
        normalized.pop("view", None)
    return normalized


def _request_matches(tool, request, expected):
    normalized = canonical(tool, request)
    if digest(normalized) == expected:
        return True
    # Earlier time receipts predate annotation pagination as well as atom
    # sections. Accept their old default-only canonical shape, not a different
    # explicit view or cursor. The original body hash is still checked below.
    from .temporal_annotation import FIELDS
    if request.get("view") is not None or any(request.get(k, default) != default for k, default in FIELDS.items()):
        return False
    for key in FIELDS:
        normalized.pop(key, None)
    return digest(normalized) == expected


def append(ledger: atoms.Ledger, tool: str, request: dict[str, Any], text: str, data: dict[str, Any]) -> str:
    node = data.get("node")
    if data.get("schema") == "migloop-time-state/1":
        node = {"kind": "file", "key": data["path"], "at": data["at"]}
    refs = ([r["ref"] for r in data.get("rows", [])] +
            [r["ref"] for r in data.get("undated", {}).get("rows", [])])
    if data.get("schema") == "migloop-raw-record/1":
        refs = [data["ref"]]
    if data.get("schema") == "migloop-time-atom/1":
        from .temporal_atom_text import preview_rows
        refs = [row["ref"] for row in preview_rows(data)]
    # State diff/blame already has legacy action references, no raw row receipt.
    raw_refs = [ref for ref in refs if isinstance(ref, str) and ref.startswith("raw:")]
    receipt = {"schema": "migloop-time-receipt/1", "tool": tool, "ledger": atoms.ledger_identity(ledger),
               "request_sha256": digest(canonical(tool, request)), "body_sha256": digest(text),
               "node": node, "raw_refs_sha256": digest(raw_refs), "raw_count": len(raw_refs),
               "relation": None}
    return text + MARKER + json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))


def parse(ledger: atoms.Ledger, tool: str, request: dict[str, Any], text: str) -> dict[str, Any] | None:
    body, separator, tail = text.rpartition(MARKER)
    if not separator:
        return None
    try:
        receipt = json.loads(tail)
        if (receipt.get("schema") != "migloop-time-receipt/1" or receipt["tool"] != tool
                or receipt["ledger"] != atoms.ledger_identity(ledger)
                or not _request_matches(tool, request, receipt["request_sha256"])
                or receipt["body_sha256"] != digest(body)):
            return None
        if tool == "record":
            match = re.match(r"# 原始记录 (raw:[0-9a-f]+:L[1-9][0-9]*:[0-9a-f]+) ·", body)
            refs = [match[1]] if match else []
        else:
            refs = re.findall(r"(?m)^- \S+ (raw:[0-9a-f]+:L[1-9][0-9]*:[0-9a-f]+) ·", body)
        if len(refs) != receipt["raw_count"] or digest(refs) != receipt["raw_refs_sha256"]:
            return None
        return {**receipt, "records": refs}
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def project(ledger: atoms.Ledger, calls: list[dict[str, Any]]) -> dict[str, Any]:
    from .probe import _unwrap_result
    rows = []
    for number, call in enumerate(calls, 1):
        args, text = call.get("input") or {}, _unwrap_result(call.get("text") or "")
        if MARKER not in text and args.get("at") is None and call.get("tool") != "record":
            continue
        receipt = parse(ledger, call.get("tool"), args, text)
        provenance = call.get("provenance") or {}
        verified = bool(receipt and call.get("has_result") and not call.get("is_error")
                        and not call.get("delivery_truncated") and not provenance.get("origin_unverified")
                        and provenance.get("complete_pair") is not False)
        rows.append({"step": number, "tool": call.get("tool"), "args": args,
                     "status": "recorded_response" if verified else "unverified_response",
                     "node": receipt["node"] if verified else None,
                     "records": receipt["records"] if verified else [], "relation": None,
                     "note": "记录查询范围和交付原文入口；不是读写边，不认证归因"})
    return {"schema": "migloop-time-trace/1", "steps": rows, "edges": [],
            "note": "实际调用序列；不把相邻查阅推断成历史关系，也不映射为最近版本。"}
