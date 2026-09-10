"""Bounded old-report reference audit. No ledger build, model, or cause reading.

Extracts only raw-reference strings and receipt metadata from one completed run;
reads at most --limit cited physical lines without printing their contents.
All outputs are new. Does not rewrite saved reports, receipts or source IDs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

from migloop import cc_sources, investigation, probe, transcript_store as store, verdict_v3


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def audit(base, case_id, rep, output, limit=8):
    base, output = Path(base).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    if not 1 <= limit <= 12:
        raise ValueError("At most twelve physical-line samples")
    run = base / "runs" / case_id / f"rep{rep}"
    metric = read(run / "metrics.json")
    if metric.get("status") != "completed" or metric.get("postprocess", {}).get("status") != "completed":
        raise ValueError("Only formally completed reports may be inspected")
    manifest = read(base / "manifest.json")
    case = next(c for c in manifest["cases"] if c["id"] == case_id)
    pool = next(p for p in manifest["pools"] if p["pool"] == case["pool"])
    refs = list(dict.fromkeys(re.findall(r"raw:[0-9a-f]{20}:L[1-9][0-9]*:[0-9a-f]{20}",
                                       (run / "report.md").read_text(encoding="utf-8"))))
    if not refs:
        raise ValueError("No old 20-hex report refs; select another completed old run")
    discovered = cc_sources.discover(pool["roots"])
    paths = [*discovered.actor_transcripts, *discovered.auxiliary_sources]
    # Source-only registry: this proves citation resolution, not a historical
    # ledger identity/actor rebuild. Production service identity is tested with
    # synthetic input separately, never replaced to make an old graph bind.
    ledger = SimpleNamespace(agents={}, auxiliary_sources=paths, source_metadata=discovered.source_metadata)
    preserved = [base / "manifest.json", run / "metrics.json", run / "report.md", run / "transcript.jsonl", run / "verdict.json"]
    before = {str(p): sha(p) for p in preserved if p.exists()}
    samples = []
    for ref in refs[:limit]:
        try:
            record = store.resolve(ledger, ref)
            qualified = store.read_record(record.path, record.line, source=store.source_spec(ledger, record.path))
            checked = verdict_v3.resolve_evidence(ledger, ref, scope={"at": case["observation_end"]})
            samples.append({"ref": ref, "source": Path(record.path).name, "line": record.line, "ts": record.ts,
                "preserved": record.ref == ref and checked.get("raw_ref") == ref,
                "qualified_key_chars": len(qualified.ref.split(":")[1]),
                "same_content": qualified.raw == record.raw, "status": checked["status"],
                "source_sha256": sha(record.path), "source_bytes": Path(record.path).stat().st_size})
        except (ValueError, OSError, UnicodeError) as error:
            samples.append({"ref": ref, "status": "rejected", "error": str(error)})
    receipts = []
    for call in probe._transcript_calls(str(run)) or []:
        if call.get("tool") not in ("batch", "changes", "expand") or not call.get("has_result"):
            continue
        text = probe._unwrap_result(call.get("text") or "")
        if investigation.MARKER not in text and investigation.WIRE_MARKER not in text:
            continue
        result = investigation.parse_receipt(call["tool"], call.get("input") or {}, text)
        receipts.append({"call_id": call.get("call_id"), "use_line": call.get("use_line"), "result_line": call.get("result_line"),
            "parsed": result is not None, "marker": "wire" if investigation.WIRE_MARKER in text else "original",
            "ledger": result["receipt"]["ledger"] if result else None,
            "body_sha256": result["receipt"]["body_sha256"] if result else None,
            "complete_pair": call.get("provenance", {}).get("complete_pair"),
            "origin_unverified": call.get("provenance", {}).get("origin_unverified", False)})
    # Compare the unchanged frozen resolver, in isolation, without replacing the
    # current package or constructing an old/new application ledger.
    script = '''import json,sys
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
from migloop import transcript_store as s
paths,refs=json.loads(sys.stdin.read())
ledger=SimpleNamespace(agents={'source_registry':SimpleNamespace(id='source_registry',sources=paths,actions=[])})
out=[]
for ref in refs:
 try:
  row=s.resolve(ledger,ref);out.append({'ref':ref,'preserved':row.ref==ref,'status':'resolved'})
 except (ValueError,OSError,UnicodeError) as e:
  out.append({'ref':ref,'status':'rejected','error':str(e)})
print(json.dumps(out))
'''
    kwargs = {"input": json.dumps([paths, refs[:limit]]), "text": True, "encoding": "utf-8",
              "capture_output": True, "timeout": 30, "check": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    frozen = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(base / "code/src")], **kwargs)
    old_resolution = json.loads(frozen.stdout)
    after = {p: sha(p) for p in before}
    result = {"schema": "migloop-sourcespec-legacy-audit/1", "utc": datetime.now(timezone.utc).isoformat(),
        "case": case_id, "rep": rep, "base": str(base), "original_artifacts": before,
        "unchanged": before == after, "old_refs_in_report": len(refs), "sampled": samples, "receipts": receipts,
        "frozen_v4_resolution": old_resolution,
        "same_acceptance_as_frozen": [s.get("preserved") is True for s in samples] == [s.get("preserved") is True for s in old_resolution],
        "current_modules": {m.__name__: sha(m.__file__) for m in (store, cc_sources, investigation, probe, verdict_v3)},
        "model_calls": 0, "ledger_builds": 0, "semantic_checked": False,
        "limits": "Reference/receipt compatibility only; no cause reading, new source pool, old ledger identity rebinding, or old outcome changes."}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    return {"output": str(output), "sampled": len(samples), "preserved": sum(s.get("preserved") is True for s in samples),
            "receipts": len(receipts), "parsed": sum(r["parsed"] for r in receipts), "unchanged": result["unchanged"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--rep", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(audit(args.base, args.case, args.rep, args.out, args.limit), ensure_ascii=False))
