"""Audit a saved inquiry/1 case card with the UI's loader; never fix its claims.

Exit 0: ready for human/semantic review; 1: loadable draft; 2: invalid or unavailable.
No model calls, new reports, persisted handles, or edits to the evidence database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def audit(index_path, report_id, task, *, require_declared=False):
    from migloop.inquiry.engine import Engine
    from migloop.inquiry.narrative import review_gaps
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

        if graph.get("submission_format") == "coordinates/1":
            from migloop.inquiry.feedback import compact_feedback
            feedback = compact_feedback(graph)
            paths = graph["tree"]["paths"] + graph["tree"].get("context_paths", [])
            return {**feedback, "loadable": True, "browser_verified": False,
                "status": "draft" if target_errors else graph["delivery"]["status"],
                "semantic_verified": False, "target_errors": target_errors,
                "card_content_errors": [], "investigation_gaps": review_gaps(graph),
                "declared_tree_required": True,
                "unclosed_paths": [p for p in paths if p["status"] == "unclosed"],
                "counts": {"nodes": len(graph["nodes"]), "bound_edges": len(graph["edges"]),
                    "problem_nodes": graph["tree"]["problem_nodes"],
                    "closed_problem_nodes": len({p["node"] for p in graph["tree"]["paths"]}
                        - {p["node"] for p in graph["tree"]["paths"] if p["status"] == "unclosed"}),
                    "model_review_edges": sum(e.get("source") == "model_review" for e in graph["edges"])},
                "note": graph["delivery"]["note"]}

        document = graph["document"]
        content_errors = []
        advised = {fid for item in document.get("recommendations", []) for fid in item["findings"]}
        for finding in document["findings"]:
            fid = finding["id"]
            if not finding.get("changes"):
                content_errors.append({"finding": fid, "error": "No modification evidence in changes"})
            if not finding.get("nodes"):
                content_errors.append({"finding": fid, "error": "No explanatory nodes"})
            if not isinstance(finding.get("unknown"), list):
                content_errors.append({"finding": fid, "error": "unknown must be an explicit list; [] when none recorded"})
            if fid not in advised and (not isinstance(finding.get("recommendation"), str) or not finding["recommendation"].strip()):
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
        investigation_gaps = review_gaps(graph)
        if require_declared:
            investigation_gaps.extend(
                {"finding": f["id"], "error": "Declare the evidence handoffs in edges; automatic history is not a delivered argument"}
                for f in document["findings"] if "edges" not in f)
            investigation_gaps.extend(
                {"finding": p["finding"], "node": p["node"], "error": "Unconfirmed native candidate is not a reviewed, displayable handoff"}
                for p in paths + graph["tree"].get("context_paths", []) if p["status"] == "candidate")
        ready = (not target_errors and not content_errors and not investigation_gaps
                 and graph["mechanical_status"] == "valid"
                 and graph["path_status"] == "complete" and coverage["complete"])
        from migloop.inquiry.feedback import related_evidence

        return {
            "report_id": report_id,
            "source_sha256": graph["source_sha256"],
            "loadable": True,
            "status": "ready_for_review" if ready else "draft",
            "semantic_verified": False,
            "browser_verified": False,
            "target_errors": target_errors,
            "card_content_errors": content_errors,
            "investigation_gaps": investigation_gaps,
            "declared_tree_required": require_declared,
            "check_results": graph.get("check_results", []),
            "mechanical_status": graph["mechanical_status"],
            "path_status": graph["path_status"],
            "issues": graph["issues"],
            "unverified_edges": graph["unverified_edges"],
            "unclosed_paths": unresolved_paths,
            "related_evidence": related_evidence(graph),
            "counts": {
                "findings": len(document["findings"]),
                "nodes": len(graph["nodes"]),
                "bound_edges": len(graph["edges"]),
                "model_review_edges": sum(e.get("source") == "model_review" for e in graph["edges"]),
                "problem_nodes": len(paths),
                "closed_problem_nodes": sum(p["status"] != "unclosed" for p in paths),
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


def console_page(result, offset=0, expected=None):
    """Read-only, hash-bound continuation; never silently shorten audit details."""
    body = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    identity = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if offset < 0 or offset > len(body):
        raise ValueError("audit offset outside body")
    if (offset and not expected) or (expected and expected != identity):
        raise ValueError("audit changed or --expect-sha256 missing; restart at offset 0")
    def size(text):
        return len(json.dumps(text, ensure_ascii=False).encode("utf-8"))
    if not offset and size(body) <= 9000:
        return body
    def render(end):
        return json.dumps({k: result[k] for k in (
            "report_id", "status", "loadable", "semantic_verified", "browser_verified") if k in result} | {
            "audit_page": {"body_sha256": identity, "chars": len(body), "start": offset,
                           "end": end, "next": end if end < len(body) else None, "text": body[offset:end]},
            "note": "Continue this script with --offset next --expect-sha256 body_sha256; full details are not omitted."
        }, ensure_ascii=False, separators=(",", ":"))
    low, high = offset, min(len(body), offset + 9000)
    while low < high:
        middle = (low + high + 1) // 2
        if size(render(middle)) <= 9000:
            low = middle
        else:
            high = middle - 1
    if size(render(low)) > 9000 or (low == offset and offset < len(body)):
        raise ValueError("audit response header exceeds budget")
    return render(low)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--report", required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--expect-sha256")
    parser.add_argument("--full", action="store_true", help="Unbounded JSON for programmatic capture to file, not model-visible stdout")
    args = parser.parse_args(argv)
    try:
        task = json.loads(args.task.read_text(encoding="utf-8-sig"))
        runtime = task["runtime"]
        # The task is host-provided configuration, never a historical instruction.
        # Production may use an installed migloop package instead of code_root.
        if runtime.get("code_root"):
            sys.path.insert(0, str(Path(runtime["code_root"]).resolve()))
        result = audit(runtime["index_path"], args.report, task, require_declared=True)
        code = 0 if result["status"] == "ready_for_review" else 1
    except (ValueError, TypeError, KeyError, OSError, ImportError, sqlite3.Error) as exc:
        result = {"report_id": args.report, "status": "invalid", "loadable": False,
                  "semantic_verified": False, "error": str(exc)}
        code = 2
    try:
        text = json.dumps(result, ensure_ascii=False, separators=(",", ":")) if args.full else console_page(result, args.offset, args.expect_sha256)
    except ValueError as exc:
        text = json.dumps({"status": "invalid", "error": str(exc)})
        code = 2
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
