"""Real loopback HTTP integration over synthetic sources; no model or user data.

Only session lookup/loading is substituted. The stdlib handler, JSON adapters,
query kernel, MCP tool implementation and v3 parser/binder are real.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import http.client
import json
from pathlib import Path
import threading

import pytest

from migloop import atom_queries, atoms, investigation, serve, service, temporal, verdict_v3
from tests.test_temporal import corpus, ts
from tests.test_verdict import _pool
from tests.test_verdict_v3 import document


def _files(root: Path):
    return {str(p.relative_to(root)): (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def real_http(tmp_path, monkeypatch):
    time_dir, graph_dir = tmp_path / "time-source", tmp_path / "graph-source"
    time_dir.mkdir()
    graph_dir.mkdir()
    time_ledger, aid, time_path = corpus(time_dir)
    graph_ledger = _pool(graph_dir)
    ledgers = {"time": time_ledger, "graph": graph_ledger}
    paths = {"time": time_path, "graph": next(iter(graph_ledger.source_stats))}
    by_path = {paths[k]: ledger for k, ledger in ledgers.items()}

    def locate(sid, _roots=None):
        if sid not in paths:
            raise service.SessionLookupError("unknown synthetic session: " + sid)
        return paths[sid]

    monkeypatch.setattr(service, "locate_session", locate)
    monkeypatch.setattr(service, "session_ledger", lambda path: by_path[path])
    monkeypatch.setattr(service, "session_cwd", lambda _path: "/proj")
    monkeypatch.setattr(service, "fixchain_payload", lambda _path: {"chains": []})
    for ledger in ledgers.values():
        atoms.ledger_identity(ledger)
    original_ledgers, original_files = deepcopy(ledgers), _files(tmp_path)
    server = serve.make_server("time", "127.0.0.1", 0)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()

    def post(tool, data=None, *, sid="time", raw=None, length=None, route=None):
        payload = raw if raw is not None else json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if length is not None:
            headers["Content-Length"] = str(length)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            connection.request("POST", route or f"/api/insight1/atom/{sid}/{tool}", body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8")), dict(response.getheaders())
        finally:
            connection.close()

    yield {"post": post, "ledgers": ledgers, "aid": aid, "paths": paths,
           "base": f"http://127.0.0.1:{server.server_address[1]}"}
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)
    assert not worker.is_alive(), "test-owned HTTP server thread must terminate"
    assert _files(tmp_path) == original_files, "query POSTs may not add, overwrite or remove source/run files"
    assert ledgers == original_ledgers, "query POSTs may not rewrite ledger actions, versions or source identities"


def test_post_batch_record_source_line_matches_shared_scope_and_rejects_future(real_http):
    ledger = real_http["ledgers"]["time"]
    args = {"source": real_http["paths"]["time"], "line": 1, "at": ts(10)}
    status, response, _ = real_http["post"]("batch", {"requests": [{"tool": "record", "args": args}]})
    assert status == 200
    assert response["items"][0]["status"] == "ok"
    payload = response["items"][0]["data"]
    assert payload == atom_queries.json_data(ledger, "record", args)
    assert payload["ref"].startswith("raw:")
    status, rejected, _ = real_http["post"]("batch", {"requests": [
        {"tool": "record", "args": {**args, "at": "2020-01-01T00:00:00Z"}}]})
    assert status == 200 and rejected["items"][0]["status"] == "error"
    assert "data" not in rejected["items"][0]


def test_post_batch_matches_actual_mcp_and_shared_json_core(real_http):
    pytest.importorskip("mcp")
    from migloop import mcp_server

    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    args = {"requests": [
        {"tool": "agent", "args": {"id": aid, "at": ts(10), "limit": 2}},
        {"tool": "search", "args": {"q": "LONGTAIL", "at": ts(10)}},
        {"tool": "agent", "args": {"id": "not-in-synthetic-pool", "at": ts(10)}},
        {"tool": "search", "args": {"q": "LATE_SECRET", "at": ts(17)}},
    ], "max_chars": 100000}

    class Backend:
        async def get_ledger(self, sid):
            assert sid == "time"
            return ledger

        async def get_session_cwd(self, sid):
            return "/proj"

    blocks = asyncio.run(mcp_server.build_server(Backend()).call_tool("batch", {"sid": "time", **args}))
    text = "".join(block.text for block in blocks)
    mcp_data = investigation.parse_receipt("batch", args, text)["data"]
    status, data, headers = real_http["post"]("batch", args)
    assert status == 200
    assert data == mcp_data == atom_queries.json_data(ledger, "batch", args)
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Type"].startswith("application/json")
    assert [item["status"] for item in data["items"]] == ["ok", "ok", "error", "ok"]
    assert data["items"][0]["scope"]["kind"] == "agent"
    assert data["items"][1]["scope"]["kind"] == "pool", "independent search does not inherit preceding agent"
    assert "LATE_SECRET" not in str(data["items"][0])
    assert data["items"][3]["data"]["total"] == 1
    assert "edges" not in data and "query_trace" not in data


@pytest.mark.parametrize("syntax", ["yaml", "json"])
def test_post_v3_check_returns_real_graph_without_invented_trace(real_http, syntax):
    ledger = real_http["ledgers"]["graph"]
    doc = document(ledger)
    doc["findings"][0]["reason"] = "模型原文 <script>not execution</script>"
    if syntax == "yaml":
        yaml = pytest.importorskip("yaml")
        draft = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
    else:
        draft = json.dumps(doc, ensure_ascii=False)
    status, data, _ = real_http["post"]("check", {"draft": draft, "file": doc["target"]["file"]}, sid="graph")
    assert status == 200 and data["semantic_checked"] is False
    graph = data["argument_graph"]
    assert graph == verdict_v3.build(ledger, doc)["argument_graph"]
    assert graph["schema"] == "migloop-argument-graph/1" and graph["identity"]["bound"] is True
    assert graph["findings"][0]["reason"] == doc["findings"][0]["reason"]
    assert all("v" not in node for node in graph["nodes"])
    assert all(edge["binding"]["status"] == "confirmed" for edge in graph["edges"])
    assert all(edge["binding"]["state_binding"] == "not_proven" for edge in graph["edges"])
    assert all(edge["semantic_checked"] is False for edge in graph["edges"])
    assert graph["nodes"][0]["evidence"][0]["scope"]["since_ts"] is None
    assert "query_trace" not in data and "trajectory" not in data
    # The check result is not written into a run, and text/MCP feedback stays
    # compact while retaining the same diagnostics and coverage.
    compact = json.loads(atom_queries.render_text(ledger, "/proj", "check", {"draft": draft, "file": doc["target"]["file"]}, chains={"chains": []}))
    assert {k: v for k, v in data.items() if k != "argument_graph"} == compact


def _partial_document(ledger):
    doc = document(ledger)
    doc["unknown_top_level"] = ["SCHEMA_ERROR_REMAINS_VISIBLE"]
    peer = {**deepcopy(doc["findings"][0]["nodes"][1]), "id": "peer",
            "reason": "VALID_PEER_REASON <img src=x onerror=alert(1)>"}
    doc["findings"][0]["nodes"].append(peer)
    doc["findings"][0]["edges"].append({"from": "actor", "to": "peer", "relation": "write",
        "evidence": list(peer["evidence"]), "claim": "INVALID_AGENT_AGENT_WRITE"})
    return doc


def test_post_partial_preview_retains_errors_and_reasons_without_invalid_edge(real_http):
    doc = _partial_document(real_http["ledgers"]["graph"])
    status, data, _ = real_http["post"]("check", {"draft": json.dumps(doc), "file": doc["target"]["file"]}, sid="graph")
    assert status == 200 and data["partial_document"]
    assert data["status"] == "needs_review" and data["document_sha256"] is None
    graph = data["argument_graph"]
    assert graph["identity"]["bound"] and not graph["original_schema_valid"]
    assert len(graph["nodes"]) == 4 and len(graph["edges"]) == 2
    assert any("unknown_top_level" in str(issue) for issue in data["issues"])
    peer = next(node for node in graph["nodes"] if node["local_id"] == "peer")
    assert peer["reason"] == doc["findings"][0]["nodes"][-1]["reason"]
    invalid = next(edge for edge in graph["edge_declarations"] if edge["claim"] == "INVALID_AGENT_AGENT_WRITE")
    assert invalid["binding"]["status"] == "invalid" and invalid["drawable"] is False
    assert all(edge["claim"] != "INVALID_AGENT_AGENT_WRITE" for edge in graph["edges"])
    assert "query_trace" not in data and data["semantic_checked"] is False


def test_post_expand_enforces_both_bounds_and_records_partial_refusals(real_http):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    rows = temporal.query(ledger, kind="agent", key=aid, at=ts(17))["rows"]
    scope = investigation.scope(ledger, "agent", aid, ts(10), ts(4))
    args = {"scope": scope, "refs": [rows[i]["ref"] for i in (0, 1, 3)], "max_chars": 12000}
    status, data, _ = real_http["post"]("expand", args)
    assert status == 200 and data == atom_queries.json_data(ledger, "expand", args)
    assert data["scope"] == scope
    assert [item["status"] for item in data["items"]] == ["error", "ok", "error"]
    assert "LONGTAIL" in str(data) and "LATE_SECRET" not in str(data)
    assert "数值应该为42" not in str(data), "lower bound applies to source expansion too"
    conflict, body, _ = real_http["post"]("batch", {"requests": [
        {"tool": "search", "scope": scope, "args": {"at": ts(17), "q": "LATE_SECRET"}}]})
    assert conflict == 200 and body["items"][0]["status"] == "error"
    assert body["items"][0]["delivery"]["records"] == []


def test_post_changes_and_events_use_real_query_kernel(real_http):
    ledger = real_http["ledgers"]["graph"]
    args = {"path": "/proj/entry/A.ets", "at": "2026-01-01T02:30:00Z", "since_ts": "2026-01-01T01:00:00Z"}
    status, changes, _ = real_http["post"]("changes", args, sid="graph")
    assert status == 200 and changes == atom_queries.json_data(ledger, "changes", args)
    assert changes["rows"] and changes["complete"] is False
    assert any(row["status"] == "confirmed_change" for row in changes["rows"])
    event_args = {"scope": changes["scope"]}
    status, events, _ = real_http["post"]("events", event_args, sid="graph")
    expected = atom_queries.json_data(ledger, "events", event_args)
    # Cache hits are operational metadata, not a different query selection.
    assert status == 200
    assert {k: v for k, v in events.items() if k != "cache"} == {k: v for k, v in expected.items() if k != "cache"}
    assert events["events"] and events["causal_complete"] is False
    assert all(row["association"] == "lexical_mention_not_effect" for row in events["events"])
    reference = changes["rows"][0]["evidence"][0]
    status, expansion, _ = real_http["post"]("expand", {"refs": [reference], "scope": changes["scope"]}, sid="graph")
    assert status == 200 and expansion["items"][0]["status"] == "ok"


@pytest.mark.parametrize("raw", [b'{"broken":', b"[]", b"null", b'"scalar"', b"42", b"\xff"])
def test_post_invalid_json_or_nonobject_is_400_and_server_stays_available(real_http, raw):
    status, data, _ = real_http["post"]("batch", raw=raw)
    assert status == 400 and data["error"]
    status, data, _ = real_http["post"]("batch", {"requests": [{"tool": "search", "args": {"q": "LONGTAIL", "at": ts(10)}}]})
    assert status == 200 and data["items"][0]["status"] == "ok"


@pytest.mark.parametrize("length,expected", [(0, 413), (-1, 413), (1000001, 413), ("not-a-number", 400)])
def test_post_rejects_bad_or_oversized_content_length_before_reading_body(real_http, length, expected):
    status, data, _ = real_http["post"]("batch", raw=b"", length=length)
    assert status == expected and data["error"]


@pytest.mark.parametrize("route", ["/no-such-route", "/api/insight1/atom/time/file",
                                   "/api/insight1/atom/time/delete", "/api/insight1/atom/time/unknown"])
def test_post_unknown_or_nonpost_query_route_is_404(real_http, route):
    status, data, _ = real_http["post"]("unused", {}, route=route)
    assert status == 404 and data["error"] == "no such read-only query route"


def test_post_unknown_session_is_404(real_http):
    status, data, _ = real_http["post"]("batch", {"requests": [{}]}, sid="not-a-session")
    assert status == 404 and "synthetic session" in data["error"]


@pytest.mark.parametrize("data", [
    {"requests": []}, {"requests": [{}] * 25}, {"requests": "not-json"},
    {"requests": [{}], "extra": True}, {"requests": [{}], "max_chars": 999},
    {"requests": [{}], "max_chars": 400001}, {"requests": [{}], "max_chars": True},
])
def test_post_batch_limits_and_unknown_parameters_are_400(real_http, data):
    status, body, _ = real_http["post"]("batch", data)
    assert status == 400 and body["error"]


def test_post_budget_deferral_is_not_delivered_data(real_http):
    status, data, _ = real_http["post"]("batch", {"requests": [
        {"tool": "agent", "args": {"id": real_http["aid"], "at": ts(17)}}], "max_chars": 1000})
    assert status == 200 and data["items"][0]["status"] == "deferred"
    assert data["items"][0]["delivery"]["records"] == [] and "data" not in data["items"][0]
