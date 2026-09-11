"""Recheck final reports using COPIES of same-schema indexes, with no model calls."""

import argparse
import json
import sqlite3
import time
from pathlib import Path

from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check, parse
from migloop.inquiry.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("round", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.mkdir(parents=True)
    copies, results = {}, []
    for case in sorted(args.round.glob("F10-*")):
        manifest = json.loads((case / "manifest.json").read_text(encoding="utf-8"))
        old_path = Path(manifest["index_path"])
        if old_path not in copies:
            target = args.out / old_path.name
            source = sqlite3.connect(old_path.resolve().as_uri() + "?mode=ro", uri=True)
            dest = sqlite3.connect(target)
            source.backup(dest)
            dest.close()
            source.close()
            copies[old_path] = target
        run = case / "runs/inquiry/rep1"
        original = (run / "verdict.yaml").read_text(encoding="utf-8")
        old = json.loads((run / "verdict.json").read_text(encoding="utf-8"))
        store = Store(copies[old_path])
        engine = Engine(store, session=old["trace_session"])
        started = time.perf_counter()
        checked = check(engine, original)
        row = {
            "case": case.name,
            "report_id": old["report_id"],
            "seconds": time.perf_counter() - started,
            "document_unchanged": checked["document"] == parse(original),
            "source_sha_unchanged": checked["source_sha256"] == old["source_sha256"],
            "mechanical_status": checked["mechanical_status"],
            "nodes_before": len(old["nodes"]),
            "nodes_after": len(checked["nodes"]),
            "edges_before": len(old["edges"]),
            "edges_after": len(checked["edges"]),
            "issues": checked["issues"],
            "missing_links": len(checked["missing_evidence_links"]),
        }
        (args.out / (case.name + ".json")).write_text(
            json.dumps(checked, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        store.close()
    (args.out / "summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
