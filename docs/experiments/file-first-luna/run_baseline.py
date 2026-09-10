"""Run the frozen Luna baseline, at most two investigators concurrently.

No model fallback or outer retry. Existing reports are never overwritten.
Stops scheduling on infrastructure/model identity failure or quota errors.
The only reads of the private reference are a SHA256 integrity check.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_job(runner, case, arm, rep, timeout):
    cmd = [sys.executable, "-X", "utf8", str(runner), "run", "--case-dir", str(case), "--arm", arm,
           "--rep", str(rep), "--backend", "codex", "--model", "gpt-5.6-luna", "--effort", "medium",
           "--tool-transport", "code-host", "--max-turns", "80", "--timeout-seconds", str(timeout),
           "--final-mode", "reference" if arm == "tools" else "document"]
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(cmd, env=env, capture_output=True)
    run = case / "runs" / arm / f"rep{rep}"
    metric_path = run / "metrics.json"
    metrics = read(metric_path) if metric_path.exists() else {}
    return {"case": case.name, "arm": arm, "rep": rep, "returncode": proc.returncode,
            "run_dir": str(run), "status": metrics.get("status", "harness_failure"),
            "actual_models": metrics.get("actual_models"), "actual_effort": metrics.get("actual_effort"),
            "recording_complete": metrics.get("recording_complete"),
            "verdict_ok": metrics.get("verdict_ok"), "usage": metrics.get("usage"),
            "end_to_end_wall_s": metrics.get("end_to_end_wall_s"),
            "harness_stdout": proc.stdout.decode("utf-8", errors="replace"),
            "harness_stderr": proc.stderr.decode("utf-8", errors="replace")}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--timeout-seconds", type=int, default=1800)
    args = ap.parse_args()
    baseline = args.baseline.resolve()
    manifest = read(baseline / "baseline.json")
    runner = HERE.parent / "2026-09-09-fidelity-cost/run_pair.py"
    if sha(runner) != manifest["runner_sha256"] or sha(baseline / "reference.json") != manifest["reference_sha256"]:
        raise ValueError("Frozen runner/reference changed")
    jobs = []
    for rep in (1, 2):
        for name in ("member-center", "splash", "dice-index"):
            for arm in (("raw", "tools") if rep == 1 else ("tools", "raw")):
                case = baseline / name
                if (case / "runs" / arm / f"rep{rep}").exists():
                    raise FileExistsError("Existing investigation; use saved results, no automatic retry")
                jobs.append((case, arm, rep))
    with (baseline / "queue.jsonl").open("x", encoding="utf-8", buffering=1) as journal:
        def emit(event):
            item = {"time": datetime.now(timezone.utc).isoformat(), **event}
            journal.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(json.dumps(item, ensure_ascii=False), flush=True)
        emit({"event": "start", "jobs": len(jobs), "concurrency": 2, "timeout_seconds_per_run": args.timeout_seconds,
              "max_turns_prompt_hint_not_enforced": 80, "hard_token_or_dollar_cap": None,
              "reference_sha256": manifest["reference_sha256"], "queue_script_sha256": sha(Path(__file__))})
        stopped = False
        with ThreadPoolExecutor(max_workers=2) as executor:
            pending = {}
            while jobs or pending:
                while jobs and len(pending) < 2 and not stopped:
                    case, arm, rep = jobs.pop(0)
                    emit({"event": "launch", "case": case.name, "arm": arm, "rep": rep})
                    future = executor.submit(run_job, runner, case, arm, rep, args.timeout_seconds)
                    pending[future] = (case.name, arm, rep)
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    identity = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {"case": identity[0], "arm": identity[1], "rep": identity[2],
                                  "status": "harness_failure", "error": repr(exc)}
                    emit({"event": "finish", **result})
                    if (result["status"] not in ("completed", "result_error", "timeout")
                        or result.get("actual_models") != ["gpt-5.6-luna"]
                        or result.get("actual_effort") != "medium"
                        or not result.get("recording_complete")):
                        stopped = True
                        emit({"event": "stop_scheduling", "reason": "infrastructure_or_identity_failure",
                              "remaining": len(jobs), "in_flight_allowed_to_finish": len(pending)})
        emit({"event": "end", "status": "stopped" if stopped else "finished",
              "unstarted": [{"case": c.name, "arm": a, "rep": r} for c, a, r in jobs]})
    return 1 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
