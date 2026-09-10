"""Read-only regression on the frozen MemberCenter pool; no model invocation.

This checks accessibility/cutoff semantics, not attribution accuracy. It never
executes transcript commands or rewrites any baseline/reference/run artifact.
"""
import argparse
import json
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from migloop import atoms, atoms_collect, temporal, temporal_state, time_receipts, atom_queries
from migloop.time_scope import _time, _iso


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case_json")
    args = parser.parse_args()
    case = json.loads(Path(args.case_json).read_text(encoding="utf-8"))
    t = perf_counter()
    ledger = atoms.build_ledger(atoms_collect.collect_cc_pool(case["roots"], [0]))
    print(json.dumps({"build_seconds": round(perf_counter() - t, 3), "agents": len(ledger.agents)}, ensure_ascii=False), flush=True)
    builder = atoms.resolve_agent(ledger, "agent-af0e3d2ae54dbf769")
    if builder is None:
        raise ValueError("not the expected frozen MemberCenter pool")
    read = next(a for a in builder.actions if any(r.op == "read" and r.path.endswith("MemberCenterPage.ets")
                                                   for r in a.files) and a.done_ts)
    start, done = _time(read.ts), _time(read.done_ts)
    if start is None or done is None or done <= start:
        raise ValueError("read does not have a usable nonzero execution interval")
    before = _iso(start + (done - start) / 2)
    after = _iso(done)
    before_data = temporal.query(ledger, kind="agent", key=builder.id, at=before, limit=200)
    after_data = temporal.query(ledger, kind="agent", key=builder.id, at=after, limit=200)
    result_line = read.src[2] + 1
    assert result_line not in {r["line"] for r in before_data["rows"]}
    assert result_line in {r["line"] for r in after_data["rows"]}
    legacy = [r for r in read.files if r.path.endswith("MemberCenterPage.ets")][0]
    print(json.dumps({"read": read.seq, "legacy_v": legacy.v, "legacy_certain": legacy.certain,
                      "use": read.ts, "done": read.done_ts, "result_line": result_line,
                      "late_result_excluded": True, "returned_result_searchable": True}, ensure_ascii=False), flush=True)
    t = perf_counter()
    file_args = {"file": case["file"], "at": after, "q": "priceDigits", "limit": 100}
    selected = atom_queries.json_data(ledger, "search", file_args)
    rows = selected["rows"]
    assert any(r["source"] == "agent-a68daf720e780b4c2.jsonl" and r["line"] == 592 for r in rows)
    response = atom_queries.render_text(ledger, "", "search", file_args)
    receipt = time_receipts.parse(ledger, "search", file_args, response)
    assert receipt and receipt["node"]["kind"] == "file" and receipt["relation"] is None
    print(json.dumps({"file_search_seconds_including_text_repeat": round(perf_counter() - t, 3),
                      "full_raw_records_scanned": selected["counts"]["records_scanned"],
                      "matching_records": selected["total"], "intervening_unversioned_script_L592_present": True,
                      "source_gaps": selected["gaps"], "receipt_bound": True}, ensure_ascii=False), flush=True)
    t = perf_counter()
    state = temporal_state.query(ledger, "blame", case["file"], after)
    print(json.dumps({"replay_seconds": round(perf_counter() - t, 3), "state_known": state["known"],
                      "origin_rows": state["total"], "time_gaps": len(state["gaps"]),
                      "note": "No semantic attribution score was measured."}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
