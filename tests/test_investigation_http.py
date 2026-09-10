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
import os
from pathlib import Path
import subprocess
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
    monkeypatch.setattr(service, "fixchain_light", lambda _path: {
        "sid": "graph", "sid8": "graph", "project": "Synthetic HTTP integration", "fixes": [], "fixers": [],
    })
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
    mcp_data = json.loads(text.rpartition(investigation.MARKER)[0])
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


@pytest.mark.skipif(not os.environ.get("MIGLOOP_TEST_CDP"), reason="optional real-page test requires an existing loopback Chrome CDP endpoint")
def test_real_page_pastes_yaml_and_expands_evidence_through_real_http(real_http):
    """Opt in with MIGLOOP_TEST_CDP=http://127.0.0.1:19653; no mock routes.

    Chrome is supplied by the caller. This test closes only its own tab, and
    the fixture closes its real HTTP server. There is no model invocation.
    """
    yaml = pytest.importorskip("yaml")
    draft = yaml.safe_dump(document(real_http["ledgers"]["graph"]), allow_unicode=True, sort_keys=False)
    script = r"""
const assert=require('node:assert/strict');
const [base,endpoint,draft]=process.argv.slice(1);
async function main(){
  assert.equal(new URL(endpoint).hostname,'127.0.0.1');
  const target=await(await fetch(endpoint+'/json/new?about:blank',{method:'PUT'})).json();
  const socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  const pending=new Map(),requests=[],errors=[];let serial=0;
  socket.onmessage=event=>{const m=JSON.parse(event.data);
    if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);
    if(m.method==='Network.requestWillBeSent'&&m.params.request.method==='POST')requests.push(m.params.request);
    const p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial;
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},10000);
    pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;};
  const until=async(expression,label)=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100));}throw Error('Timeout '+label);};
  try{
    await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
    await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1200,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:base+'/api/insight1/fixchain/graph'});
    await until("window.__mig && document.querySelector('.draft-loader')",'real page');
    await evaluate(`(()=>{const loader=document.querySelector('.draft-loader');loader.open=true;
      loader.querySelector('textarea').value=${JSON.stringify(draft)};loader.querySelector('.draft-submit').click();})()`);
    await until("__mig.probe()?.manual_input===true && document.querySelectorAll('.argument-card').length===3",'real v3 check');
    const before=await evaluate("JSON.stringify(__mig.probe().argument_graph)");
    assert.equal(await evaluate("__mig.probe().argument_graph.identity.bound"),true);
    assert.equal(await evaluate("document.querySelectorAll('.argument-wire').length"),2);
    assert.equal(await evaluate("__mig.probe().query_trace == null && __mig.probe().steps.length===0"),true);
    const expected=await evaluate("(()=>{const e=__mig.probe().argument_graph.nodes[0].evidence[0];return {ref:e.raw_ref||e.ref,scope:e.scope};})()");
    await evaluate("document.querySelector('#side .argument-open-original').click()");
    await until("document.querySelector('#side .query-recheck-result pre')",'real record expansion');
    const record=await evaluate("JSON.parse(document.querySelector('#side .query-recheck-result pre').textContent)");
    assert.equal(record.schema,'migloop-raw-record/1');assert.equal(record.ref,expected.ref);
    assert.equal(record.scope.at,expected.scope.at);assert.equal(record.scope.since_ts,null);
    assert.equal(typeof record.text,'string');assert(record.text.length>0);
    assert.equal(await evaluate("JSON.stringify(__mig.probe().argument_graph)"),before);
    assert.equal(await evaluate("__mig.probe().query_trace == null"),true);
    assert.deepEqual(errors,[]);
    assert.equal(requests.length,2);assert(requests[0].url.endsWith('/atom/graph/check'));assert(requests[1].url.endsWith('/atom/graph/batch'));
    const check=JSON.parse(requests[0].postData),batch=JSON.parse(requests[1].postData);
    assert.equal(check.draft,draft);assert.equal(batch.requests[0].tool,'record');assert.equal(batch.requests[0].args.ref,expected.ref);
    assert.equal(batch.requests[0].scope.since_ts,null);
    console.log(JSON.stringify({passed:true,realHttp:true,nodes:3,edges:2,posts:2,manualTraceAbsent:true}));
  }finally{socket.close();await fetch(endpoint+'/json/close/'+target.id).catch(()=>{});}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
"""
    completed = subprocess.run(["node", "-e", script, real_http["base"], os.environ["MIGLOOP_TEST_CDP"], draft],
                               cwd=Path(__file__).resolve().parents[1], text=True, encoding="utf-8",
                               capture_output=True, timeout=35)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout.strip())
    assert result == {"passed": True, "realHttp": True, "nodes": 3, "edges": 2, "posts": 2, "manualTraceAbsent": True}
