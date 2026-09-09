"""Re-render one completed file/action query; offline characters, not token savings.

Run separately for each source to avoid mixed Python module/builder identities.
No original run, source or pool is written. The recorded output is never replaced.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--rep", type=int, default=1)
    parser.add_argument("--step", type=int, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    case = json.loads((args.case_dir / "case.json").read_text(encoding="utf-8"))
    run = args.case_dir / "runs/tools" / f"rep{args.rep}"
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    if metrics.get("status") != "completed" or not metrics.get("recording_complete"):
        raise ValueError("Only completed, fully recorded runs are eligible")
    os.environ.update(MIGLOOP_FROZEN_POOL=case["pool"],
        MIGLOOP_FROZEN_ANCHOR=metrics.get("frozen_anchor") or "",
        MIGLOOP_FROZEN_ROOTS=json.dumps(metrics["frozen_roots"]) if metrics.get("frozen_anchor") else "")
    sys.path.insert(0, str(args.source.resolve() / "src"))
    from migloop import atom_queries, atoms, probe, service
    calls = probe._transcript_calls(str(run))
    if not calls or not 1 <= args.step <= len(calls):
        raise ValueError("Exact recorded step is unavailable")
    call = calls[args.step - 1]
    if call["tool"] not in ("file", "action") or call.get("is_error"):
        raise ValueError("Only file/action non-error calls can be compared")
    query = dict(call["input"])
    sid = query.pop("sid", case["current_root"])
    query.pop("via", None)  # No actual visit is created by a renderer comparison.
    ledger = service.session_ledger(sid)
    text = atom_queries.render_text(ledger, service.session_cwd(sid), call["tool"], query)
    print(json.dumps({"source": str(args.source.resolve()), "case": case["case"], "rep": args.rep,
        "step": args.step, "tool": call["tool"], "query": query,
        "ledger": atoms.ledger_identity(ledger), "chars": len(text),
        "body_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "recorded_chars": call.get("chars"), "recorded_return_unchanged": True,
        "source_transcript_sha256": hashlib.sha256((run / "transcript.jsonl").read_bytes()).hexdigest(),
        "boundary_lines": [line for line in text.splitlines() if any(word in line for word in
            ("未命中", "未展开", "请求正文不可满足", "没有交付", "原始动作", "完整索引仍可查"))],
        "semantic_checked": False, "token_savings_measured": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
