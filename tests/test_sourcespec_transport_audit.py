"""Independent SourceSpec transport/probe audit. Synthetic evidence only."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import http.client
import json
import os
from pathlib import Path
import threading

import pytest

from migloop import atoms, investigation, mcp_server, probe, serve, service, time_probe, transcript_store as store, verdict_v3
from tests.test_atoms import _call, _rec
from tests.test_cc_source_discovery import SID, dump

AT = "2026-01-01T00:03:00Z"
SINCE = "2026-01-01T00:00:00Z"


@pytest.fixture
def source_http(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    root = dump(pool / f"{SID}.jsonl", [
        _rec(SINCE, "user", "synthetic input for A.ets", cwd="/proj"),
        *_call("2026-01-01T00:01:00Z", "write-1", "Write", {"file_path": "/proj/A.ets", "content": "line\n"}, "ok")])
    auxiliary = []
    for number in (1, 2):
        path = pool / SID / f"workflows/w{number}/journal.jsonl"
        dump(path, [{"type": "result", "timestamp": "2099-01-01T00:00:00Z", "agentId": "invented-actor",
                     "result": f"A.ets aux needle {number} <img src=x onerror=bad()>"}])
        auxiliary.append(path)
    note = pool / SID / "tool-results/note.txt"
    note.parent.mkdir(parents=True)
    note.write_text("A.ets aux needle plain text\nsecond line\n", encoding="utf-8")
    auxiliary.append(note)
    for key, value in {"MIGLOOP_FROZEN_POOL": str(pool), "MIGLOOP_FROZEN_ANCHOR": root,
                       "MIGLOOP_FROZEN_ROOTS": json.dumps([root])}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(service, "_LEDGER_CACHE", {})
    monkeypatch.setattr(service, "run_stage_intervals", lambda *_: [])
    # Real extract_trace/observation scope/discovery/collect/build, not a hand-made registry.
    ledger = service.session_ledger(root)
    monkeypatch.setattr(service, "locate_session", lambda sid, _roots=None: root)
    server = serve.make_server(root, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    original = deepcopy(ledger)
    hashes = {p: p.read_bytes() for p in pool.rglob("*") if p.is_file()}

    def post(request):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            conn.request("POST", "/api/insight1/atom/fixture/batch", json.dumps(request).encode(), {"Content-Type": "application/json"})
            response = conn.getresponse()
            assert response.status == 200
            return json.loads(response.read())
        finally:
            conn.close()

    yield {"ledger": ledger, "root": root, "auxiliary": auxiliary, "post": post, "tmp": tmp_path}
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert ledger == original
    assert hashes == {p: p.read_bytes() for p in pool.rglob("*") if p.is_file()}


def qualified(ledger, path, number=1):
    return store.read_record(str(path), number, source=store.source_spec(ledger, str(path))).ref


def mcp_batch(ledger, request):
    class Backend:
        async def get_ledger(self, _sid):
            return ledger

        async def get_session_cwd(self, _sid):
            return "/proj"

    blocks = asyncio.run(mcp_server.build_server(Backend()).call_tool("batch", {"sid": "fixture", **request}))
    text = "".join(b.text for b in blocks)
    receipt = investigation.parse_receipt("batch", request, text)
    assert receipt
    return text, receipt["data"]


def doc(ledger, evidence):
    aid = next(iter(ledger.agents))
    return {"schema": verdict_v3.SCHEMA, "ledger": atoms.ledger_identity(ledger),
            "target": {"file": "/proj/A.ets", "since_ts": SINCE, "at": AT},
            "findings": [{"id": "F", "title": "synthetic model claim", "reason": "MODEL_REASON_UNCHANGED",
                "status": "unknown", "changes": [], "unknown": ["attachment author/time are not established"],
                "nodes": [{"id": "actor", "kind": "agent", "key": aid, "at": AT, "role": "context",
                           "reason": "model context claim, not a certified input", "evidence": [evidence]},
                          {"id": "file", "kind": "file", "key": "/proj/A.ets", "at": AT, "role": "context",
                           "reason": "model file claim", "evidence": [evidence]}],
                "edges": [{"from": "actor", "to": "file", "relation": "possible_write", "evidence": [evidence],
                           "claim": "synthetic unsupported edge must not be certified"}]}]}


def test_service_ledger_qualified_addresses_keep_empty_owners_and_unknown_time(source_http):
    ledger = source_http["ledger"]
    registry = store.sources(ledger)
    assert len(registry) == 4
    assert "invented-actor" not in ledger.agents
    for path in source_http["auxiliary"]:
        ref = qualified(ledger, path)
        assert len(ref.split(":")[1]) == 40
        assert registry[os.path.normcase(str(path))] == set()
        assert store.resolve(ledger, ref).ts is None
        assert len(store.read_record(str(path), 1).ref.split(":")[1]) == 20
    assert investigation.scope(ledger, at="latest")["at"].startswith("2026-01-01T00:01:")


@pytest.mark.parametrize("legacy", [False, True])
def test_actual_http_mcp_batch_preserve_ref_scope_unknown_and_partial_failures(source_http, legacy):
    ledger = source_http["ledger"]
    path = source_http["auxiliary"][-1]  # unique basename, valid old reference
    ref = store.read_record(str(path), 1).ref if legacy else qualified(ledger, path)
    pool_scope = {"kind": "pool", "key": None, "at": AT, "since_ts": SINCE}
    aid = next(iter(ledger.agents))
    request = {"requests": [
        {"tool": "search", "args": {"q": "aux needle", "at": AT, "include_undated": True}},
        {"tool": "record", "args": {"ref": ref, "include_undated": True}, "scope": pool_scope},
        {"tool": "record", "args": {"ref": ref}, "scope": pool_scope},
        {"tool": "record", "args": {"ref": ref, "include_undated": True},
         "scope": {**pool_scope, "kind": "agent", "key": aid}}], "max_chars": 60000}
    text, actual = mcp_batch(ledger, request)
    assert source_http["post"](request) == actual
    assert [item["status"] for item in actual["items"]] == ["ok", "ok", "error", "error"]
    hits = actual["items"][0]["data"]["undated"]["rows"]
    assert len(hits) == 3 and all(r["agents"] == [] and r["ts"] is None for r in hits)
    delivered = actual["items"][1]
    assert delivered["data"]["ref"] == ref and delivered["data"]["ts"] is None
    assert delivered["data"]["text"] == path.read_text(encoding="utf-8").splitlines()[0]
    assert delivered["scope"]["kind"] == "pool"
    assert [row["ref"] for row in delivered["delivery"]["records"]] == [ref]
    assert all(not item["delivery"]["records"] for item in actual["items"][2:])
    call = {"tool": "batch", "input": request, "text": text, "has_result": True,
            "provenance": {"complete_pair": True}}
    trace = investigation.project_trace(ledger, [call])
    assert trace["edges"] == [] and trace["steps"][0]["status"] == "recorded_response"
    assert [item["status"] for item in trace["steps"][0]["items"]] == ["ok", "ok", "error", "error"]
    for change in ({"text": text + "changed"}, {"provenance": {"complete_pair": True, "origin_unverified": True}}):
        rejected = investigation.project_trace(ledger, [{**call, **change}])
        assert rejected["steps"][0]["status"] == "unverified_response"
        assert rejected["edges"] == [] and not rejected["steps"][0]["delivery"]["records"]


def test_duplicate_legacy_basename_ref_does_not_gain_preferred_owner(source_http):
    ledger = source_http["ledger"]
    old = store.read_record(str(source_http["auxiliary"][0]), 1).ref
    request = {"requests": [{"tool": "record", "args": {"ref": old, "at": AT, "include_undated": True}}]}
    _, data = mcp_batch(ledger, request)
    assert source_http["post"](request) == data
    assert data["items"][0]["status"] == "error"
    assert not data["items"][0]["delivery"]["records"]
    assert "ambiguous" in str(data["items"][0])


def test_aux_evidence_retained_in_probe_but_cannot_prove_author_or_input(source_http):
    ledger, path = source_http["ledger"], source_http["auxiliary"][0]
    ref = qualified(ledger, path)
    document = doc(ledger, ref)
    result = verdict_v3.build(ledger, document)
    graph = result["argument_graph"]
    assert graph["identity"]["bound"]
    assert all(n["evidence"][0]["status"] == "undated" for n in graph["nodes"])
    assert graph["edges"][0]["binding"]["status"] == "not_observed"
    report = "```json\n" + json.dumps(document) + "\n```"
    run = source_http["tmp"] / "manual-run"
    run.mkdir()
    view = time_probe.probe_payload(ledger, str(run), report=report, calls=[], metadata={},
        trace_identity={"bound": True, "status": "matched", "current": atoms.ledger_identity(ledger)})
    # This hand-made preview is not upgraded into a recorded native final.
    assert view["native_report"]["verified"] is False
    assert view["query_trace"]["steps"] == [] and view["query_trace"]["edges"] == []
    before = deepcopy(graph)
    investigation.query(ledger, "record", {"ref": ref, "at": AT, "include_undated": True})
    assert verdict_v3.build(ledger, document)["argument_graph"] == before
