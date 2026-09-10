"""One read-only Dice replay, saving the exact pre/post-budget trees locally.

Does not run transcript commands, investigators, or model APIs. The temporary
query wrapper only copies the actual batch selections before projection.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def dump(path: Path, value) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def package(repo: Path) -> dict:
    files = {str(path.relative_to(repo)).replace("\\", "/"): sha(path.read_bytes())
             for path in sorted((repo / "src/migloop").rglob("*"))
             if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    return {"files": files, "sha256": sha(json.dumps(files, sort_keys=True,
            separators=(",", ":")).encode("utf-8"))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--eval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    before = package(args.repo)
    dump(args.out / "package-before.json", before)
    run = args.eval / "tools-v2/runs/F10-03/rep1"
    trace_path = run / "query-trace.json"
    settings_path = args.eval / "tools-v2/settings/F10-03.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    step = next(row for row in trace["steps"] if row["step"] == 16)
    assert step["tool"] == "batch"
    request = step["args"]
    dump(args.out / "request.json", request)
    os.environ.update(json.loads(settings_path.read_text(encoding="utf-8"))
                      ["mcp_servers"]["migloop"]["env"])
    sys.path.insert(0, str(args.repo / "src"))
    from migloop import atoms, investigation, service, transcript_store

    started = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()
    print("COLD_REPLAY_STARTED " + started, flush=True)
    ledger = service.session_ledger(request["sid"])
    print("LEDGER_READY " + str(round(time.perf_counter() - clock, 3)), flush=True)
    original_query = investigation.query
    selected = []

    def capture(ledger_arg, tool, supplied):
        entry = {"item_index": len(selected), "tool": tool, "args": copy.deepcopy(supplied)}
        selected.append(entry)
        try:
            data = original_query(ledger_arg, tool, supplied)
            entry.update(status="ok", data=copy.deepcopy(data))
            return data
        except Exception as exc:
            entry.update(status="error", error=str(exc), error_type=type(exc).__name__)
            raise

    investigation.query = capture
    try:
        projected = investigation.batch(ledger, request["requests"], request["max_chars"])
    finally:
        investigation.query = original_query
    dump(args.out / "selected.json", {"schema": "text-prototype-selected/1",
        "ledger": atoms.ledger_identity(ledger), "items": selected})
    dump(args.out / "projected.json", projected)
    after = package(args.repo)
    dump(args.out / "package-after.json", after)
    manifest = {"schema": "text-prototype-capture/1", "case": "F10-03", "step": 16,
        "purpose": "offline renderer comparison only; no model call; not frozen experiment output",
        "started_at": started, "elapsed_seconds": round(time.perf_counter() - clock, 3),
        "trace": str(trace_path), "trace_sha256": sha(trace_path.read_bytes()),
        "settings_sha256": sha(settings_path.read_bytes()),
        "package_sha256_before": before["sha256"], "package_sha256_after": after["sha256"],
        "package_stable": before == after, "source_count": len(transcript_store.sources(ledger)),
        "selected_items": len(selected), "projected_summary": projected["delivery_summary"],
        "files": {name: sha((args.out / name).read_bytes()) for name in
                  ("request.json", "selected.json", "projected.json")}}
    dump(args.out / "capture.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    if before != after:
        raise SystemExit("Package changed during capture: do not use this sample for stable comparison")


if __name__ == "__main__":
    main()
