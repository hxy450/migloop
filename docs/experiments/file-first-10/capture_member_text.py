"""Read-only capture of the original Member file request, no model or batch."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

from capture_text_delivery import dump, package, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--eval", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    before = package(args.repo)
    dump(args.out / "package-before.json", before)
    trace_path = args.eval / "tools-v2/runs/F10-01/rep1/query-trace.json"
    step = next(row for row in json.loads(trace_path.read_text(encoding="utf-8"))["steps"] if row["step"] == 7)
    request = step["args"]["requests"][2]
    assert request["tool"] == "file" and request["args"]["at"] == "2026-07-24T22:16:20.102Z"
    dump(args.out / "request.json", request)
    settings = json.loads((args.eval / "tools-v2/settings/F10-01.json").read_text(encoding="utf-8"))
    os.environ.update(settings["mcp_servers"]["migloop"]["env"])
    sys.path.insert(0, str(args.repo / "src"))
    from migloop import atoms, investigation, service
    started = time.perf_counter()
    print("MEMBER_FILE_CAPTURE_STARTED", flush=True)
    ledger = service.session_ledger(step["args"]["sid"])
    print("LEDGER_READY " + str(round(time.perf_counter() - started, 3)), flush=True)
    data = investigation.query(ledger, request["tool"], request["args"])
    dump(args.out / "selected.json", {"ledger": atoms.ledger_identity(ledger), "request": request, "data": data})
    after = package(args.repo)
    dump(args.out / "package-after.json", after)
    manifest = {"schema": "progressive-member-capture/1", "case": "F10-01", "step": 7, "item_index": 2,
        "elapsed_seconds": round(time.perf_counter() - started, 3), "trace_sha256": sha(trace_path.read_bytes()),
        "package_before": before["sha256"], "package_after": after["sha256"], "package_stable": before == after,
        "selected_sha256": sha((args.out / "selected.json").read_bytes()), "rows": len(data["rows"]), "total": data["total"]}
    dump(args.out / "capture.json", manifest)
    print(json.dumps(manifest), flush=True)
    assert before == after, "source package changed"


if __name__ == "__main__":
    main()
