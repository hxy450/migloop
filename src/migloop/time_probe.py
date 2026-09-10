"""V3 argument and real query-trace projection, independent of legacy via trees."""
from __future__ import annotations

import json
import os
from typing import Any

from . import atoms, verdict, verdict_v3


def is_v3_run(run_dir: str, report: str, calls: list[dict[str, Any]] | None = None) -> bool:
    block = verdict.extract_block(report)
    if block:
        candidate, errors = verdict.parse_block(*block)
        if isinstance(candidate, dict) and candidate.get("schema") == verdict_v3.SCHEMA:
            return True
        if errors and verdict_v3.SCHEMA in block[1]:
            return True
        if isinstance(candidate, dict) and candidate.get("schema") == "migloop-verdict-ref/1":
            checks = [row for row in calls or [] if row.get("tool") == "check"]
            if checks:
                draft = (checks[-1].get("input") or {}).get("draft")
                if isinstance(draft, str) and verdict_v3.SCHEMA in draft:
                    return True
    path = os.path.join(run_dir, "verdict.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as stream:
                saved = json.load(stream)
            return (isinstance(saved, dict) and isinstance(saved.get("data"), dict)
                    and saved["data"].get("schema") == verdict_v3.SCHEMA)
        except (OSError, ValueError):
            pass  # The legacy loader retains its original malformed-cache behavior.
    return False


def probe_payload(ledger: atoms.Ledger, run_dir: str, *, report: str,
                  calls: list[dict[str, Any]] | None, metadata: dict[str, Any],
                  trace_identity: dict[str, Any]) -> dict[str, Any]:
    from . import draft_check, investigation, probe, recorded_report, verdict_preview

    # Reuse original-document/check-reference authentication, not cached data alone.
    structured = probe._structured(ledger, run_dir, report, trace_identity=trace_identity, calls=calls)
    if not structured or structured.get("schema") != verdict_v3.SCHEMA:
        previous = structured or {}
        structured = verdict_v3.build(ledger, None, previous.get("errors") or ["v3 原文未通过认证"],
            {"raw": previous.get("raw"), "trace_identity": trace_identity})
        structured["document_source"] = previous.get("document_source") or {
            "kind": "unverified", "verified": False, "semantic_checked": False}
    query_trace = investigation.project_trace(ledger, calls or [])
    checked = draft_check.final_binding(ledger, calls, None,
        identity_bound=structured["identity"]["bound"] and trace_identity.get("bound") is True,
        final_document_sha256=structured["document_sha256"])
    preview = None
    native_origin = recorded_report.authenticate(run_dir, report, metadata)
    if structured.get("errors"):
        # Only the actual final response may bypass *display* all-or-nothing.
        # A saved verdict or its claimed hash is never a preview authority.
        block = verdict.extract_block(report)
        candidate, parse_errors = verdict.parse_block(*block) if block else (None, ["no block"])
        if (not parse_errors and isinstance(candidate, dict) and candidate.get("schema") == verdict_v3.SCHEMA
                and verdict_v3.validate(candidate) and native_origin["verified"]):
            preview = verdict_preview.build(ledger, candidate, raw=block[1], meta={"trace_identity": trace_identity})
            preview["document_source"] = native_origin
    selected = preview or structured
    graph = selected["argument_graph"]
    graph["document_source"] = selected.get("document_source") or {
        "kind": "unrecorded", "verified": False, "semantic_checked": False}
    if metadata.get("recording_complete") is True:
        # New recorded runs must corroborate even syntactically valid final
        # artifacts. A matching cached YAML is not native authorship.
        graph["document_source"] = native_origin
        if not native_origin["verified"]:
            graph["identity"] = {**graph["identity"], "bound": False, "status": "document_unverified"}
            graph["diagnostics"].append({"code": "native_final_unverified", "detail": native_origin.get("error")})
    return {"schema": "migloop-time-probe/1", "run": os.path.basename(os.path.dirname(os.path.abspath(run_dir))),
            "cost": metadata.get("cost_usd"), "turns": metadata.get("num_turns"), "report": report,
            "root": (selected.get("target") or {}).get("file"), "target": selected.get("target"),
            "legacy": False, "structured": structured, "argument_graph": graph, "query_trace": query_trace,
            "preview": preview, "partial_document": preview is not None,
            "native_report": native_origin,
            "trace_identity": trace_identity, "draft_check": checked,
            "findings": graph["findings"], "coverage": graph["coverage"], "diagnostics": graph["diagnostics"]}
