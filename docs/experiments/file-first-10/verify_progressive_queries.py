"""Execute two composed Member queries read-only; never execute stored commands."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from capture_text_delivery import dump, package


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--eval", type=Path, required=True)
    parser.add_argument("--render", type=Path, required=True)
    args = parser.parse_args()
    before = package(args.repo)
    settings = json.loads((args.eval / "tools-v2/settings/F10-01.json").read_text(encoding="utf-8"))
    os.environ.update(settings["mcp_servers"]["migloop"]["env"])
    trace = json.loads((args.eval / "tools-v2/runs/F10-01/rep1/query-trace.json").read_text(encoding="utf-8"))
    sid = next(step for step in trace["steps"] if step["step"] == 7)["args"]["sid"]
    audit = json.loads((args.render / "member-file-three.audit.json").read_text(encoding="utf-8"))
    requests = [next(row for row in audit["queries_displayed"] if row["label"].startswith(prefix))
                for prefix in ("继续主记录", "  读取该正文")]
    sys.path.insert(0, str(args.repo / "src"))
    from migloop import investigation, service
    clock = time.perf_counter()
    print("PROGRESSIVE_QUERY_SMOKE_START", flush=True)
    ledger = service.session_ledger(sid)
    records = []
    for entry in requests:
        query = entry["query"]
        result = investigation.query(ledger, query["tool"], {**query["args"], "scope": query["scope"]})
        for key in ("kind", "key", "at", "since_ts"):
            assert result["scope"][key] == query["scope"][key]
        record = {"label": entry["label"], "query": query, "schema": result["schema"], "scope": result["scope"]}
        if query["tool"] == "file":
            assert result["offset"] == 3 and len(result["rows"]) == 3 and result["next_offset"] == 6
            record.update(offset=3, returned_rows=3, next_offset=6,
                          refs=[row["ref"] for row in result["rows"]])
        else:
            part = result["items"][0]["records"][0]
            expected = query["args"]["refs"][0]
            assert part["ref"] == expected["ref"] and part["pointer"] == expected["pointer"]
            assert part["offset"] == 0 and len(part["text"]) == 12000 and part["next_offset"] == 12000
            record.update(ref=part["ref"], pointer=part["pointer"], offset=0, actual_chars=len(part["text"]),
                          next_offset=part["next_offset"], text_sha256=hashlib.sha256(part["text"].encode()).hexdigest())
        record["passed"] = True
        records.append(record)
        print("PASS " + entry["label"], flush=True)
    after = package(args.repo)
    result = {"schema": "progressive-query-smoke/1", "queries": records,
        "elapsed_seconds": round(time.perf_counter() - clock, 3), "package_before": before["sha256"],
        "package_after": after["sha256"], "package_stable": before == after,
        "read_material_not_added_to_default_example": True, "model_calls": 0}
    dump(args.render / "query-smoke.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    assert before == after


if __name__ == "__main__":
    main()
