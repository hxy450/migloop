"""Read-only optional audit of frozen reports using an explicitly copied package.

No model calls or report/ledger identity rewriting. Generated diagnostics go only
to new files under --out-dir. The caller owns the source snapshot and browser.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_files(source):
    return [{"path": p.relative_to(source).as_posix(), "sha256": sha(p)}
            for p in sorted(source.rglob("*"))
            if p.is_file() and p.suffix in (".py", ".html", ".js", ".css")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="Copied directory containing migloop/")
    parser.add_argument("--tools-base", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--case", default="F10-01")
    parser.add_argument("--rep", type=int, default=1)
    args = parser.parse_args()
    source, baseline, out = args.source_root.resolve(), args.tools_base.resolve(), args.out_dir.resolve()
    outputs = [out / name for name in ("related-checks.json", "real-partial-probe.json", "probe-summary.json")]
    if any(path.exists() for path in outputs):
        raise ValueError("Refusing to overwrite an existing audit output")
    before = package_files(source)
    package_hash = hashlib.sha256(json.dumps(before, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest = json.loads((baseline / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen_ready_for_tools":
        raise ValueError("Expected a formal frozen tools baseline")
    config = json.loads((baseline / "settings" / (args.case + ".json")).read_text(encoding="utf-8"))
    for key in list(os.environ):
        if key.startswith("MIGLOOP_"):
            del os.environ[key]
    os.environ.update(config["mcp_servers"]["migloop"]["env"])
    sys.path.insert(0, str(source))
    from migloop import atoms, investigation, probe, service, transcript_store

    started = time.perf_counter()
    sid = os.environ["MIGLOOP_FROZEN_ANCHOR"]
    ledger = service.session_ledger(sid)
    wanted = {"toolu_01T6WkXMhD7rUsHaSaMPuhgx", "toolu_01DeqiV3n9uPH5cLqUA6a8Yn"}
    related = {"schema": "migloop-0723-related-snapshot-probe/1", "source_root": str(source),
               "package_digest": package_hash, "ledger": atoms.ledger_identity(ledger),
               "source_count": len(transcript_store.sources(ledger)), "results": []}
    print("Loaded snapshot ledger with " + str(related["source_count"]) + " sources", flush=True)
    for target in ("MemberCenterPage.ets", "SplashPage.ets"):
        found, offset, pages = {}, 0, []
        while True:
            data = investigation.changes(ledger, "entry/src/main/ets/pages/" + target,
                "2026-07-26T21:48:57.793Z", "2026-07-24T22:16:20.102Z",
                limit=100, related_offset=offset, related_limit=200)
            remainder = data["unclassified_related"]
            pages.append({key: remainder.get(key) for key in ("total", "offset", "limit", "remaining", "next_offset")})
            for row in remainder.get("rows", []):
                if row.get("call_id") in wanted:
                    found[row["call_id"]] = row
            next_offset = remainder.get("next_offset")
            if wanted <= found.keys() or next_offset is None:
                break
            assert isinstance(next_offset, int) and next_offset > offset and len(pages) < 20
            offset = next_offset
        assert wanted <= found.keys(), (target, list(found))
        for row in found.values():
            assert row["classification"] == "unclassified_related" and row["effect_status"] == "unknown"
            assert row["agent"] is None and row["author_status"] == "unknown"
        assert not any(call in row["id"] for call in wanted for row in data["rows"])
        related["results"].append({"target": target, "scope": data["scope"], "related_pages": pages,
                                   "changes_total": data["total"], "matched": list(found.values()),
                                   "not_in_changes_rows": True})
        print("Verified both unclassified calls for " + target, flush=True)
    run = baseline / "runs" / args.case / ("rep" + str(args.rep))
    report_hash, transcript_hash = sha(run / "report.md"), sha(run / "transcript.jsonl")
    projected = probe.probe_payload(ledger, str(run))
    graph = projected.get("argument_graph") or {}
    summary = {"schema": "migloop-real-partial-preview-audit/1", "source_root": str(source),
        "package_digest": package_hash, "package_files": before, "tools_manifest_sha256": sha(baseline / "manifest.json"),
        "run": str(run), "report_sha256": report_hash, "transcript_sha256": transcript_hash,
        "ledger": atoms.ledger_identity(ledger), "partial_document": projected.get("partial_document"),
        "native_report": projected.get("native_report"), "identity": graph.get("identity"),
        "nodes": len(graph.get("nodes", [])), "edges": len(graph.get("edges", [])),
        "invalid_edge_declarations": sum(not edge.get("drawable") for edge in graph.get("edge_declarations", [])),
        "schema_errors": (projected.get("preview") or {}).get("schema_errors", []),
        "elapsed_seconds": time.perf_counter() - started, "model_calls": 0, "semantic_checked": False,
        "source_unchanged": before == package_files(source),
        "run_unchanged": report_hash == sha(run / "report.md") and transcript_hash == sha(run / "transcript.jsonl")}
    assert summary["source_unchanged"] and summary["run_unchanged"]
    assert summary["partial_document"] and summary["native_report"]["verified"]
    # Do not rewrite a real report's ledger id to obtain a positive binding.
    assert summary["identity"]["bound"], summary["identity"]
    out.mkdir(parents=True, exist_ok=True)
    for path, value in zip(outputs, (related, projected, summary)):
        with path.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(json.dumps({key: value for key, value in summary.items() if key != "package_files"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
