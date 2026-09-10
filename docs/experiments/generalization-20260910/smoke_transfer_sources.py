"""No-model real stdio MCP source gate. Reports metadata/hashes, never bodies.

The first auxiliary file is selected only by relative path order. Empty-query
pool search has no answer-derived terms. Physical-line payload equality does
not certify newline/BOM delivery, causal meaning, historical actor or time.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FREEZE = load(Path(__file__).with_name("prepare_transfer_sources.py"), "source_gate_freeze")


def code_check(candidate, expected_manifest, expected_code):
    if FREEZE.file_hash(candidate / "manifest.json") != expected_manifest:
        raise ValueError("Candidate manifest SHA mismatch")
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    if manifest["code_digest"] != expected_code:
        raise ValueError("Candidate code binding mismatch")
    root = candidate / "code/src/migloop"
    rows = []
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            continue
        FREEZE.regular(path, directory=path.is_dir())
        if path.is_file():
            rows.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                         "sha256": FREEZE.file_hash(path)})
    value = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if value != expected_code:
        raise ValueError("Actual frozen code SHA mismatch")
    return {"manifest_sha256": expected_manifest, "code_digest": value, "files": len(rows)}


def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def cohort_smoke(candidate, cohort, output, python, progress):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from migloop import atoms, investigation, service, transcript_store as store

    env = {k: v for k, v in os.environ.items() if not k.startswith("MIGLOOP_") and k != "PYTHONPATH"}
    env.update(cohort["registry_env"], PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    for key in list(os.environ):
        if key.startswith("MIGLOOP_"):
            del os.environ[key]
    os.environ.update(cohort["registry_env"])
    pool = output / cohort["pool"]
    local_started = time.perf_counter()
    ledger = service.session_ledger(cohort["sid"])
    registry = store.sources(ledger)
    identity = atoms.ledger_identity(ledger)
    actual = sorted(Path(p).resolve().relative_to(pool).as_posix() for p in registry)
    assert actual == sorted(row["path"] for row in cohort["files"])
    auxiliary_keys = {os.path.normcase(os.path.abspath(p)) for p in ledger.auxiliary_sources}
    auxiliary = sorted((p for p in registry if p in auxiliary_keys),
                       key=lambda p: Path(p).resolve().relative_to(pool).as_posix())
    # Both supplied pools have UTF-8 auxiliary text; zero/failed samples fail.
    assert auxiliary
    selected = auxiliary[0]
    spec = store.source_spec(ledger, selected)
    original = list(store.records(selected, source=spec))
    assert original and not registry[selected] and spec.timestamp_policy == "unknown"
    assert all(r.ts is None for r in original)
    # Locate the selected physical line in the neutral unknown-time page order.
    # This is metadata-only indexing, not a semantic query or answer keyword.
    search_offset = 0
    for path in sorted(registry):
        if path == selected:
            break
        search_offset += sum(r.ts is None for r in store.records(path, source=store.source_spec(ledger, path)))
    all_aux_metadata = {"sources": len(auxiliary), "unowned": all(not registry[p] for p in auxiliary),
                        "unknown_timestamp_policy": all(store.source_spec(ledger, p).timestamp_policy == "unknown" for p in auxiliary)}
    local_seconds = time.perf_counter() - local_started
    print(json.dumps({"event": "local_registry_ready", "id": cohort["id"],
                      "auxiliary_count": len(auxiliary), "search_offset": search_offset}), flush=True)
    target = cohort["tasks"][0]["original_target"]
    at = cohort["observation_end"]
    expected_file = investigation.scope(ledger, "file", target, at)
    expected_pool = investigation.scope(ledger, "pool", at=at)
    entry = "import sys;sys.path.insert(0," + repr(str(candidate / "code/src")) + ");from migloop.mcp_server import main;main()"
    parameters = StdioServerParameters(command=str(python), args=["-I", "-B", "-X", "utf8", "-c", entry],
                                       env=env, cwd=str(pool))
    calls = progress["calls"]

    async def batch(session, requests, label, require_ok=True):
        request = {"sid": cohort["sid"], "requests": requests, "max_chars": 100000}
        started = time.perf_counter()
        result = await session.call_tool("batch", request)
        text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
        saved = investigation.parse_receipt("batch", request, text)
        if result.isError or saved is None:
            raise ValueError("Real MCP envelope/receipt failed: " + label)
        data = saved["data"]
        assert data["ledger"] == saved["receipt"]["ledger"] == identity
        calls.append({"label": label, "tool": "batch", "request": request,
                      "seconds": time.perf_counter() - started, "response_chars": len(text),
                      "response_sha256": sha_text(text), "receipt": saved["receipt"],
                      "receipt_verified": True, "items": [{"item_index": item["item_index"],
                          "tool": item["tool"], "status": item["status"], "scope": item.get("scope"),
                          "data_schema": item.get("data", {}).get("schema"), "delivery": item["delivery"],
                          "error_sha256": sha_text(item["error"]) if item.get("error") else None,
                          "original_data_chars": item.get("original_data_chars"),
                          "data_chars": len(json.dumps(item.get("data"), ensure_ascii=False)),
                          "budget_adjusted": item.get("budget_adjusted")}
                          for item in data["items"]]})
        print(json.dumps({"event": "mcp_batch_returned", "id": cohort["id"], "label": label,
                          "statuses": [item["status"] for item in data["items"]]}), flush=True)
        if require_ok:
            assert all(item["status"] == "ok" for item in data["items"])
        return data["items"]

    started = time.perf_counter()
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            print(json.dumps({"event": "mcp_initialized", "id": cohort["id"]}), flush=True)
            advertised = sorted(t.name for t in (await session.list_tools()).tools)
            assert {"batch", "file", "search", "record"} <= set(advertised)
            # Omitted view must take the actual overview default.
            requests = [{"tool": "file", "args": {"path": target, "at": at, "limit": 1}},
                        {"tool": "search", "args": {"q": "", "at": at, "include_undated": True,
                                                   "offset": search_offset, "limit": 1}}]
            items = await batch(session, requests, "neutral_overview_and_empty_pool_search", require_ok=False)
            file_data, search_data = [item.get("data") for item in items]
            file_ok = items[0]["status"] == "ok"
            file_diagnostic = None
            if file_ok:
                assert items[0]["scope"] == file_data["scope"] == expected_file
                assert file_data["schema"] == "migloop-time-atom/1" and file_data["view"] == "overview"
                assert file_data["raw_index"]["source_count"] == cohort["file_count"]
                assert not file_data["raw_index"]["gaps"]
                body_scope = file_data["body_sources"]["query"]["scope"]
                assert body_scope == {k: v for k, v in expected_file.items() if k != "id"}
            else:
                # Only classify a failed delivery's selected JSON sizes/counts.
                # This local diagnostic is not passed off as an MCP delivery.
                diagnostic_started = time.perf_counter()
                selected_data = investigation.query(ledger, "file", requests[0]["args"])
                file_diagnostic = {"basis": "local_selected_data_not_mcp_delivery",
                    "seconds": time.perf_counter() - diagnostic_started,
                    "top_level_chars": {k: len(json.dumps(v, ensure_ascii=False, separators=(",", ":")))
                                        for k, v in selected_data.items()},
                    "gap_groups": {}}
                for label, gaps in (("body_sources.gaps", selected_data["body_sources"]["gaps"]),
                                    ("coverage.native_source_gaps", selected_data["coverage"]["native_source_gaps"]),
                                    ("raw_index.gaps", selected_data["raw_index"]["gaps"])):
                    file_diagnostic["gap_groups"][label] = {"count": len(gaps),
                        "field_names": sorted(set(k for gap in gaps for k in gap)),
                        "source_suffix_counts": dict(Counter(Path(gap.get("source", "")).suffix for gap in gaps)),
                        "malformed_labeled_count": sum("malformed" in json.dumps(gap).lower() for gap in gaps)}
                del selected_data
            assert items[1]["status"] == "ok"
            assert items[1]["scope"] == search_data["scope"] == expected_pool
            assert search_data["source_count"] == cohort["file_count"] and not search_data["gaps"]
            observed, = search_data["undated"]["rows"]
            assert observed["ref"] == original[0].ref
            assert observed["ts"] is None and observed["time_status"] == "undated" and observed["agents"] == []
            assert not observed["annotations"]
            records = []
            for record in original:
                parts, offset = [], 0
                while True:
                    returned, = await batch(session, [{"tool": "record", "scope": expected_pool,
                        "args": {"ref": record.ref, "include_undated": True,
                                 "offset": offset, "max_chars": 12000}}], "aux_raw_record")
                    data = returned["data"]
                    assert returned["scope"] == data["scope"] == expected_pool
                    assert data["schema"] == "migloop-raw-record/1" and data["ref"] == record.ref
                    assert data["ts"] is None and data["time_status"] == "undated"
                    assert not data.get("agents") and not data.get("actor") and not data.get("agent")
                    assert data["offset"] == offset and data["chars"] == len(record.raw)
                    parts.append(data["text"])
                    next_offset = data["next_offset"]
                    if next_offset is None:
                        break
                    assert next_offset == offset + len(data["text"]) and next_offset > offset
                    offset = next_offset
                full = "".join(parts)
                assert full == record.raw
                records.append({"ref": record.ref, "line": record.line, "chars": len(full),
                                "payload_sha256": sha_text(full), "segments": len(parts),
                                "exact_physical_line_payload": True, "time_status": "undated", "ts": None,
                                "actor_asserted": False})
    return {"id": cohort["id"], "passed": file_ok, "model_calls": 0, "sid": cohort["sid"],
            "ledger": identity, "registered_count": len(actual), "advertised_tools": advertised,
            "local_registry_seconds": local_seconds, "mcp_seconds": time.perf_counter() - started,
            "all_aux_metadata": all_aux_metadata,
            "file": {"scope": expected_file, "status": items[0]["status"], "passed": file_ok,
                     "view": file_data["view"] if file_ok else None, "source_count": len(actual),
                     "body_scope_exact": True if file_ok else None,
                     "local_failure_diagnostic": file_diagnostic,
                     "sections": {k: {"total": v["total"], "rows": len(v["rows"])}
                                  for k, v in file_data["sections"].items()} if file_ok else None},
            "pool_search": {"scope": expected_pool, "query": "", "include_undated": True,
                            "offset": search_offset, "selected_aux_ref_delivered": observed["ref"],
                            "ts": None, "agents": [], "annotations": [], "gaps": search_data["gaps"]},
            "auxiliary_roundtrip": {"selection": "first auxiliary file by relative POSIX path order",
                "path": Path(selected).resolve().relative_to(pool).as_posix(),
                "file_bytes_sha256": FREEZE.file_hash(selected), "timestamp_policy": spec.timestamp_policy,
                "source_owners": sorted(registry[selected]), "records": records, "all_lines_returned": True,
                "physical_line_count": len(original), "payload_exact": True,
                "delimiter_boundary": "Record API strips physical CR/LF delimiters and first UTF-8 BOM; only line payloads were delivered and compared, not a byte-file download."},
            "calls": calls, "mcp_session_closed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--code-digest", required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--audit-name", default="smoke-source-v1.json")
    parser.add_argument("--cohort", help="Optional isolated diagnostic; result explicitly lists only this cohort")
    args = parser.parse_args()
    FREEZE.relative_name(args.audit_name)
    if "/" in args.audit_name or (args.out / args.audit_name).exists():
        raise FileExistsError("Smoke output must be new")
    source = FREEZE.verify(args.out)
    before = code_check(args.candidate, args.candidate_sha256, args.code_digest)
    sys.path.insert(0, str(args.candidate / "code/src"))
    rows = []
    for cohort in source["cohorts"]:
        if args.cohort and cohort["id"] != args.cohort:
            continue
        print(json.dumps({"event": "smoke_start", "id": cohort["id"]}), flush=True)
        progress = {"calls": []}
        try:
            row = asyncio.run(asyncio.wait_for(cohort_smoke(args.candidate, cohort, args.out, args.python, progress), 300))
        except Exception as exc:
            # Error text might include a source value; keep only type and hash.
            row = {"id": cohort["id"], "passed": False, "error_type": type(exc).__name__,
                   "error_sha256": sha_text(str(exc)), "model_calls": 0,
                   "error_locations": [{"file": Path(frame.filename).name, "line": frame.lineno,
                                        "function": frame.name} for frame in traceback.extract_tb(exc.__traceback__)],
                   "nested_errors": error_metadata(exc), **progress}
        rows.append(row)
        print(json.dumps({"event": "smoke_finish", "id": cohort["id"], "passed": row["passed"]}), flush=True)
    after = code_check(args.candidate, args.candidate_sha256, args.code_digest)
    FREEZE.verify(args.out)
    result = {"schema": "migloop-transfer-source-mcp-smoke/1", "created_at": datetime.now(timezone.utc).isoformat(),
              "source_manifest_sha256": FREEZE.file_hash(args.out / "source-manifest.json"),
              "script_sha256": FREEZE.file_hash(__file__), "candidate": str(args.candidate),
              "runtime_before": before, "runtime_after": after, "source_verified_before_after": True,
              "cohorts": rows, "passed": before == after and all(row["passed"] for row in rows),
              "cohort_selection": args.cohort or "all",
              "model_calls": 0, "gold_read": False,
              "limitation": "Offline actual MCP sample, not model delivery, OS sandbox or all-file expansion proof. All files registered/decode checked separately; one path-ordered auxiliary is fully expanded per cohort. Source bodies withheld from this metadata report."}
    FREEZE.save(args.out / args.audit_name, result)
    print(json.dumps({"passed": result["passed"], "audit": str(args.out / args.audit_name),
                      "sha256": FREEZE.file_hash(args.out / args.audit_name)}))


def error_metadata(exc):
    return {"type": type(exc).__name__, "message_sha256": sha_text(str(exc)),
            "locations": [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                          for f in traceback.extract_tb(exc.__traceback__)],
            "children": [error_metadata(child) for child in getattr(exc, "exceptions", [])]}


if __name__ == "__main__":
    main()
