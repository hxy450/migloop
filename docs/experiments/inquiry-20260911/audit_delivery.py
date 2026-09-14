"""Read saved drafts and feedback without changing any investigator artifact.

Reports structural changes, not semantic correction. Rejected schema submissions
live in the native transcript, not the saved-report list. No model calls.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


def judgments(document):
    return {f"{f['id']}:{n['id']}": {k: n.get(k) for k in ("role", "reason", "scope", "kind", "key", "at", "since", "evidence")}
            for f in document["findings"] for n in f.get("nodes", [])}


def transition(before, after):
    old, new = judgments(before), judgments(after)
    return {"removed": sorted(old.keys() - new.keys()), "added": sorted(new.keys() - old.keys()),
            "changed": [{"node": key, "before": old[key], "after": new[key]}
                        for key in sorted(old.keys() & new.keys()) if old[key] != new[key]],
            "semantic_corrections": None,
            "note": "IDs may be renamed or findings regrouped. Removal is not correction; compare meaning and original evidence before scoring."}


def audit(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    index = Path(manifest["index_path"])
    db = sqlite3.connect("file:" + index.as_posix() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute("SELECT id,request,data FROM runs WHERE kind='report' ORDER BY rowid").fetchall()
        drafts = []
        documents = []
        for row in rows:
            graph = json.loads(row["data"])
            digest = hashlib.sha256(row["request"].encode()).hexdigest()
            if digest != graph["source_sha256"]:
                raise ValueError("saved report digest mismatch: " + row["id"])
            doc = graph["document"]
            documents.append(doc)
            paths = graph["tree"]["paths"]
            drafts.append({"report_id": row["id"], "source_sha256": digest,
                "mechanical_status": graph["mechanical_status"], "issues": graph["issues"],
                "unverified_edges": graph["unverified_edges"],
                "findings": [{"id": f["id"], "title": f["title"], "reason": f["reason"], "boundary": f.get("boundary"),
                              "declared_edges": "edges" in f} for f in doc["findings"]],
                "problem_nodes": len(paths), "closed_problem_nodes": sum(p["status"] != "unclosed" for p in paths),
                "native_problem_paths": sum(p["status"] == "native" for p in paths),
                "reviewed_problem_paths": sum(p["status"] == "model_review" for p in paths),
                "longest_problem_path": max((len(p["steps"]) for p in paths if p["status"] != "unclosed"), default=0),
                "unclosed_context": sum(p["status"] == "unclosed" for p in graph["tree"].get("context_paths", [])),
                "check_results": graph.get("check_results", []), "coverage": graph["coverage"]})
        run = root / "runs/inquiry/rep1"
        metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8")) if (run / "metrics.json").is_file() else None
        return {"schema": "delivery-run-audit/1", "case": manifest["case"]["id"],
            "model": manifest["model"], "effort": manifest["effort"],
            "code_digest": manifest["code_inventory"]["content_digest"],
            "saved_drafts": drafts, "initial_to_final": transition(documents[0], documents[-1]) if documents else None,
            "metrics_available": metrics is not None, "metrics_path": str(run / "metrics.json"),
            "semantic_verified": False, "model_calls": 0,
            "note": "Frozen saved drafts, not every submission attempt. Original transcript records rejected schema submissions. No rescoring from field completeness, path length or disappearance of a claim."}
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.case_directory), ensure_ascii=False, indent=2))
