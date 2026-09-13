"""Audit a saved inquiry/1 case card with the UI's loader; never fix its claims.

Exit 0: ready for human/semantic review; 1: loadable draft; 2: invalid or unavailable.
No model calls, new reports, persisted handles, or edits to the evidence database.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def audit(index_path, report_id, task):
    from migloop.inquiry.engine import Engine
    from migloop.inquiry.report import load_report
    from migloop.inquiry.store import Store, timestamp

    store = Store(index_path)
    try:
        # The normal loader can make deterministic navigation handles. Keep
        # these in a rolled-back transaction, not in the investigator's trace.
        store.db.execute("BEGIN")
        graph = load_report(Engine(store), report_id)
        target = graph["target"]
        target_errors = []
        if store.resolve_file(task["file"]) != store.resolve_file(target["file"]):
            target_errors.append("Card targets a different file than investigation.json")
        for field, expected in (("since", "generation_end"), ("at", "observation_end")):
            if timestamp(target.get(field)) != timestamp(task[expected], required=True):
                target_errors.append("Card target." + field + " differs from task." + expected)

        document = graph["document"]
        content_errors = []
        for finding in document["findings"]:
            fid = finding["id"]
            if not finding.get("changes"):
                content_errors.append({"finding": fid, "error": "No modification evidence in changes"})
            if not finding.get("nodes"):
                content_errors.append({"finding": fid, "error": "No explanatory nodes"})
            if not isinstance(finding.get("unknown"), list):
                content_errors.append({"finding": fid, "error": "unknown must be an explicit list; [] when none recorded"})
            if not isinstance(finding.get("recommendation"), str) or not finding["recommendation"].strip():
                content_errors.append({"finding": fid, "error": "State a bounded recommendation and verification, or why none is justified"})
            for node in finding.get("nodes", []):
                if not node.get("evidence"):
                    content_errors.append({"finding": fid, "node": node["id"], "error": "Node judgment has no original evidence; unresolved claims belong in unknown"})
        if not isinstance(document.get("unexplained"), list):
            content_errors.append({"error": "unexplained must be an explicit list"})
        if not document["findings"] and not document.get("unexplained"):
            content_errors.append({"error": "An empty card explains neither changes nor why investigation is unresolved"})

        coverage = graph["coverage"]
        paths = graph["tree"]["paths"]
        unresolved_paths = [p for p in paths if p["status"] == "unclosed"]
        ready = (not target_errors and not content_errors
                 and graph["mechanical_status"] == "valid"
                 and graph["path_status"] == "complete" and coverage["complete"])
        return {
            "report_id": report_id,
            "source_sha256": graph["source_sha256"],
            "loadable": True,
            "status": "ready_for_review" if ready else "draft",
            "semantic_verified": False,
            "browser_verified": False,
            "target_errors": target_errors,
            "card_content_errors": content_errors,
            "mechanical_status": graph["mechanical_status"],
            "path_status": graph["path_status"],
            "issues": graph["issues"],
            "unverified_edges": graph["unverified_edges"],
            "unclosed_paths": unresolved_paths,
            "missing_evidence_links": graph["missing_evidence_links"],
            "counts": {
                "findings": len(document["findings"]),
                "nodes": len(graph["nodes"]),
                "bound_edges": len(graph["edges"]),
                "model_review_edges": sum(e.get("source") == "model_review" for e in graph["edges"]),
            },
            "coverage": {
                "complete": coverage["complete"],
                "unattributed_native_writes": coverage["unattributed_native_writes"],
                "unassessed_count": len(coverage["unassessed"]),
                "unknown_count": len(coverage["unknown"]),
                "issues": coverage["issues"],
            },
            "review_queries": [
                {"op": "review", "report_id": report_id, "limit": 100},
                {"op": "review", "report_id": report_id, "view": "coverage", "limit": 100},
            ],
            "note": "The same loader as the UI accepted the card. This is not a browser test, causal proof, or proof that all relevant inputs were investigated. Review each claim against its original evidence. Preserve real unknowns instead of deleting claims to pass.",
        }
    finally:
        store.db.rollback()
        store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    try:
        task = json.loads(args.task.read_text(encoding="utf-8-sig"))
        runtime = task["runtime"]
        # The task is host-provided configuration, never a historical instruction.
        # Production may use an installed migloop package instead of code_root.
        if runtime.get("code_root"):
            sys.path.insert(0, str(Path(runtime["code_root"]).resolve()))
        result = audit(runtime["index_path"], args.report, task)
        code = 0 if result["status"] == "ready_for_review" else 1
    except (ValueError, TypeError, KeyError, OSError, ImportError, sqlite3.Error) as exc:
        result = {"report_id": args.report, "status": "invalid", "loadable": False,
                  "semantic_verified": False, "error": str(exc)}
        code = 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
