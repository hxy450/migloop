"""Export mechanical audit evidence using the run's frozen source, never truth scores.

One invocation audits one case. An optional separately frozen viewer may reparse the
same recording; both source versions are recorded and ledger binding still applies.
The output must be new and outside pool/source/run; original artifacts never change.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import sys


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--arm", choices=("tools", "raw"), default="tools")
    parser.add_argument("--rep", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--viewer-source", type=Path, help="Explicit alternative viewer; never changes the investigator's source or artifacts")
    args = parser.parse_args()
    case_dir = args.case_dir.resolve()
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    run = case_dir / "runs" / args.arm / f"rep{args.rep}"
    output = args.output.resolve()
    viewer = (args.viewer_source or Path(case["source"])).resolve()
    protected = (Path(case["pool"]).resolve(), Path(case["source"]).resolve(), run, viewer)
    if output.exists() or any(output.is_relative_to(root) for root in protected):
        raise ValueError("Audit destination must be new and outside pool/source/run")
    harness_path = Path(__file__).resolve().parents[1] / "2026-09-09-fidelity-cost/run_pair.py"
    spec = importlib.util.spec_from_file_location("attribution_audit_harness", harness_path)
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    integrity = harness.check_frozen(case_dir, case)
    if not all(integrity[key] for key in ("pool_unchanged", "source_unchanged", "task_unchanged")):
        raise RuntimeError(f"Cannot authenticate changed inputs: {integrity}")
    os.environ["MIGLOOP_FROZEN_POOL"] = case["pool"]
    service, _, _ = harness.load_modules(viewer)
    from migloop import probe
    ledger = service.session_ledger(case["current_root"])
    payload = probe.probe_payload(ledger, str(run), service.fixchain_payload(case["current_root"]))
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    structure = payload.get("structured") or {}
    trajectory = payload.get("trajectory") or {}
    nodes = [node for defect in structure.get("defects", []) for node in defect.get("nodes", [])]
    edges = [edge for defect in structure.get("defects", []) for edge in defect.get("edges", [])]
    evidence = [item for defect in structure.get("defects", [])
                for item in (defect.get("repair", {}).get("evidence", []) +
                             [ref for node in defect.get("nodes", []) for ref in node.get("evidence", [])])]
    doc = {
        "schema": "migloop-attribution-run-audit/1", "case": case["case"], "run_dir": str(run),
        "source_code_id": case["source_code_id"], "task_sha256": case["common_task_sha256"],
        "viewer": {"source": str(viewer), "source_digest": harness.inventory(viewer / "src/migloop")["content_digest"],
                   "same_as_investigator": viewer == Path(case["source"]).resolve()},
        "integrity": integrity, "trace_identity": payload.get("trace_identity"),
        "conclusion_identity": structure.get("identity"),
        "schema_errors": structure.get("errors", []),
        "nodes": {"total": len(nodes), "resolved": sum(node.get("ok") is True for node in nodes)},
        "evidence_status": dict(Counter(item.get("status") for item in evidence)),
        "conclusion_edge_status": dict(Counter(edge.get("status") for edge in edges)),
        "explicit_edge_status": dict(Counter(edge.get("status") for edge in edges if edge.get("implicit") is False)),
        "implicit_adjacency_status": dict(Counter(edge.get("status") for edge in edges if edge.get("implicit") is True)),
        "entry_role_conflicts": [{"defect": node.get("defect"), "node": node.get("spec"), "role": node.get("role")}
                                 for node in nodes if node.get("entry") and node.get("role") not in ("进入·错", "进入·缺")],
        "coverage": payload.get("coverage"),
        "draft_check": payload.get("draft_check"),
        "trajectory_summary": {key: trajectory.get(key) for key in ("mode", "root", "verification", "verification_note")},
        "visit_status": dict(Counter(visit.get("status") for visit in trajectory.get("visits", []))),
        "transition_status": dict(Counter(hop.get("relation_status") for hop in trajectory.get("transitions", []))),
        "metrics": {key: metrics.get(key) for key in ("status", "actual_models", "actual_effort", "wall_s",
                    "end_to_end_wall_s", "usage", "verdict_ok", "coverage_complete", "recording_complete", "draft_check")},
        "boundary": "Mechanical checks authenticate recorded locations, identities and ledger relations only; no attribution truth score or attention/behavior proof.",
        "payload": payload,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(doc, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: value for key, value in doc.items() if key not in ("payload", "coverage", "trace_identity")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
