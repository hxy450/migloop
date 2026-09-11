"""Reindex to a NEW diagnostic path and review an immutable older report.

No model calls and no writes to the source index or historical transcript.
Copies handles only to resolve the original report's coordinates.
"""

import argparse
import json
import sqlite3
import time
from pathlib import Path

from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check
from migloop.inquiry.store import Source, Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_db", type=Path)
    parser.add_argument("report_id")
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.mkdir(parents=True)
    old = sqlite3.connect(args.old_db.resolve().as_uri() + "?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    rows = old.execute("SELECT * FROM sources").fetchall()
    sources = [
        Source(
            r["path"],
            r["name"],
            r["agent"],
            r["cwd"],
            "auto" if r["path"].endswith(".jsonl") else "text",
        )
        for r in rows
    ]
    stored = old.execute(
        "SELECT request FROM runs WHERE kind=? AND id=?", ("report", args.report_id)
    ).fetchone()
    if stored is None:
        raise ValueError("report not found")
    started = time.perf_counter()
    store = Store.build(args.out / "index.sqlite", sources)
    with store.db:
        store.db.executemany(
            "INSERT OR IGNORE INTO handles VALUES(?,?,?)",
            old.execute("SELECT * FROM handles"),
        )
    old.close()
    engine = Engine(store, session="diagnostic-older-report")
    imported = time.perf_counter() - started
    started = time.perf_counter()
    graph = check(engine, stored["request"], save=True)
    result = {
        "old_report": args.report_id,
        "display_report": graph["report_id"],
        "import_seconds": imported,
        "check_seconds": time.perf_counter() - started,
        "mechanical_status": graph["mechanical_status"],
        "document_unchanged": graph["document"] == json.loads(stored["request"]),
        "evidence_review": graph["evidence_review"],
    }
    (args.out / "review.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "evidence_review"},
            ensure_ascii=False,
        )
    )
    print(
        json.dumps(
            {
                k: len(v)
                for k, v in graph["evidence_review"].items()
                if isinstance(v, list)
            }
        )
    )
    store.close()


if __name__ == "__main__":
    main()
