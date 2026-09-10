"""Rebuild one tools investigation's UI payload from frozen source and recordings.

Writes a new audit artifact outside the investigator pool. No model calls, no
inferred causal edges, no edits to saved reports. This checks payload projection,
not browser layout and not semantic truth.
"""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", type=Path, required=True)
    ap.add_argument("--rep", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    case = json.loads((args.case / "case.json").read_text(encoding="utf-8"))
    if args.out.exists() or args.out.resolve().is_relative_to(Path(case["pool"]).resolve()):
        raise ValueError("Audit output must be new and outside raw pool")
    sys.path.insert(0, str(Path(case["source"]) / "src"))
    os.environ.update(MIGLOOP_FROZEN_POOL=case["pool"], MIGLOOP_FROZEN_ANCHOR=case["current_root"],
                      MIGLOOP_FROZEN_ROOTS=json.dumps(case["roots"]), PYTHONDONTWRITEBYTECODE="1")
    from migloop import service, probe
    ledger = service.session_ledger(case["current_root"])
    run = args.case / "runs/tools" / f"rep{args.rep}"
    payload = probe.probe_payload(ledger, str(run), service.fixchain_payload(case["current_root"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    structured = payload.get("structured") or {}
    trajectory = payload.get("trajectory") or {}
    graph = payload.get("evidence_graph") or {}
    print(json.dumps({"out": str(args.out), "trace_identity": payload.get("trace_identity"),
        "defects": payload.get("defects"), "structured_errors": structured.get("errors"),
        "steps": len(payload["steps"]), "trajectory_keys": list(trajectory),
        "graph_keys": list(graph), "coverage": (payload.get("coverage") or {}).get("counts"),
        "semantic_validation_performed": False, "browser_layout_validation_performed": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
