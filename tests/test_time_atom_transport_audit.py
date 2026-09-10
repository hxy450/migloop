"""Independent time-atom transport/UI audit over small synthetic sources only.

Real HTTP handlers, MCP callbacks, selection and receipt parsers are exercised.
The JavaScript tests execute template helpers, not copied projection logic.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import http.client
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlencode

import pytest

from migloop import atom_queries, atoms, delivery_budget, investigation, mcp_server, temporal, time_receipts, verdict_v3
from tests.test_investigation_http import real_http  # noqa: F401 -- shared real loopback fixture
from tests.test_temporal import corpus, ts
from tests.test_verdict_v3 import document

TEMPLATE = Path(__file__).parents[1] / "src/migloop/render/templates/fixchain.html"


def _get(server, tool, args):
    connection = http.client.HTTPConnection(server["base"].split("://")[1], timeout=5)
    try:
        connection.request("GET", "/api/insight1/atom/time/" + tool + "?" + urlencode(args))
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def _mcp(ledger, tool, args):
    class Backend:
        async def get_ledger(self, _sid):
            return ledger

        async def get_session_cwd(self, _sid):
            return "/proj"

    blocks = asyncio.run(mcp_server.build_server(Backend()).call_tool(tool, {"sid": "time", **args}))
    return "".join(block.text for block in blocks)


@pytest.mark.parametrize("tool", ["file", "agent"])
@pytest.mark.parametrize("view", [None, "overview", "records", "writes", "reads", "candidates", "messages"])
def test_real_get_mcp_and_batch_select_same_time_atom(real_http, tool, view):
    ledger = real_http["ledgers"]["time"]
    args = {"path": "/p/A.ets"} if tool == "file" else {"id": real_http["aid"]}
    args.update(at=ts(15), since_ts=ts(4), limit=1)
    if view is not None:
        args["view"] = view
    status, http_data = _get(real_http, tool, args)
    if tool == "file" and view == "messages":
        assert status == 400 and "messages" in http_data["error"]
        with pytest.raises(ValueError, match="messages"):
            atom_queries.parameters(tool, args)
        code, batch, _ = real_http["post"]("batch", {"requests": [{"tool": tool, "args": args}]})
        assert code == 200 and batch["items"][0]["status"] == "error"
        assert not batch["items"][0]["delivery"]["records"]
        return
    assert status == 200
    assert http_data == atom_queries.json_data(ledger, tool, args)
    assert http_data == investigation.query(ledger, tool, args)
    text = _mcp(ledger, tool, args)
    assert text == atom_queries.render_text(ledger, "/proj", tool, args)
    receipt = time_receipts.parse(ledger, tool, args, text)
    assert receipt and receipt["relation"] is None
    if view == "records":
        assert http_data["schema"] == "migloop-time-view/1"
    else:
        assert http_data["schema"] == "migloop-time-atom/1"
        assert "sections" in http_data and "sections" not in receipt
        # Only actually displayed original excerpts count. Native use/result
        # locators and the raw_index/body_sources exits do not certify reads.
        expected = [row["ref"] for page in http_data["sections"].values()
                    for row in page["rows"] if isinstance(row.get("preview"), str)]
        assert receipt["records"] == expected
        assert [row["ref"] for row in investigation._delivery(http_data)["records"]] == expected
    code, batch, _ = real_http["post"]("batch", {"requests": [{"tool": tool, "args": args}]})
    assert code == 200 and batch["items"][0]["status"] == "ok"
    assert batch["items"][0]["data"] == http_data


@pytest.mark.parametrize("tool", ["file", "agent"])
def test_sparse_mcp_latest_receipt_and_pending_result_do_not_leak(real_http, tool):
    ledger = real_http["ledgers"]["time"]
    args = {"path": "/p/A.ets"} if tool == "file" else {"id": real_http["aid"]}
    latest = _mcp(ledger, tool, args)
    assert time_receipts.parse(ledger, tool, args, latest)
    early_args = {**args, "at": ts(10)}
    early = _mcp(ledger, tool, early_args)
    assert "LATE_SECRET" not in early
    data = investigation.query(ledger, tool, early_args)
    assert not data["sections"]["reads"]["rows"]
    assert data["sections"]["candidates"]["rows"]
    assert all(row["done_ts"] is None for row in data["sections"]["candidates"]["rows"])
    assert time_receipts.parse(ledger, tool, {**early_args, "at": ts(15)}, early) is None


@pytest.mark.parametrize("disclosure_fields", [False, True])
def test_pre_view_time_receipt_hash_is_backward_compatible_without_requery(tmp_path, monkeypatch, disclosure_fields):
    ledger, aid, _ = corpus(tmp_path)
    args = {"id": aid, "at": ts(10)}
    # Literal historical canonical shape: frozen v2 predates annotation pages;
    # the immediately pre-view contract includes them. Neither includes view.
    original = {"id": aid, "v": None, "since": None, "until": None, "reads": None,
                "seen": False, "scope_only": False, "summary_chars": 96, "at": ts(10),
                "offset": 0, "limit": 40, "include_undated": False, "since_ts": None, "details": False}
    if disclosure_fields:
        original.update(annotation_offset=0, annotation_limit=None, relation_offset=0, relation_limit=None)
    selected = temporal.query(ledger, kind="agent", key=aid, at=ts(10))
    body = temporal.render(selected)
    raw_refs = [row["ref"] for row in selected["rows"]]
    receipt = {"schema": "migloop-time-receipt/1", "tool": "agent", "ledger": atoms.ledger_identity(ledger),
               "request_sha256": time_receipts.digest(original), "body_sha256": time_receipts.digest(body),
               "node": selected["node"], "raw_refs_sha256": time_receipts.digest(raw_refs),
               "raw_count": len(raw_refs), "relation": None}
    text = body + time_receipts.MARKER + json.dumps(receipt)
    monkeypatch.setattr(temporal, "query", lambda *a, **k: pytest.fail("receipt verification must not rerun today's view"))
    assert time_receipts.parse(ledger, "agent", args, text)
    assert time_receipts.parse(ledger, "agent", {**args, "view": "records"}, text) is None
    assert time_receipts.parse(ledger, "agent", {**args, "view": "reads"}, text) is None


def test_authenticated_navigation_receipts_still_cannot_add_edges(real_http):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    args = {"id": aid, "at": ts(10)}
    text = _mcp(ledger, "agent", args)
    call = {"tool": "agent", "input": args, "text": text, "has_result": True,
            "provenance": {"complete_pair": True}}
    before = deepcopy(ledger)
    trace = investigation.project_trace(ledger, [call])
    assert trace["steps"][0]["status"] == "recorded_response" and trace["edges"] == []
    for change in ({"delivery_truncated": True}, {"provenance": {"origin_unverified": True}},
                   {"text": text + "body tampered"}, {"input": {**args, "view": "reads"}}):
        bad = investigation.project_trace(ledger, [{**call, **change}])
        assert bad["steps"][0]["status"] == "unverified_response" and bad["edges"] == []
        assert not bad["steps"][0]["delivery"]["records"]
    assert ledger == before
    graph_ledger = real_http["ledgers"]["graph"]
    doc = document(graph_ledger)
    original_graph = verdict_v3.build(graph_ledger, doc)["argument_graph"]
    investigation.query(graph_ledger, "agent", {"id": "agent-c", "at": doc["target"]["at"]})
    investigation.query(graph_ledger, "file", {"path": doc["target"]["file"], "at": doc["target"]["at"]})
    assert verdict_v3.build(graph_ledger, doc)["argument_graph"] == original_graph


def test_overview_returned_queries_preserve_scope_and_expand_only_visible_parts(real_http):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    selected = investigation.query(ledger, "agent", {"id": aid, "at": ts(10), "since_ts": ts(4)})
    row = selected["sections"]["candidates"]["rows"][0]
    query = row["expand_query"]
    expanded = investigation.query(ledger, query["tool"], {**query["args"], "scope": query["scope"]})
    assert expanded["scope"] == selected["scope"]
    assert "LATE_SECRET" not in str(expanded)
    assert expanded["items"] and all(item["status"] == "ok" for item in expanded["items"])
    assert all(record["ts"] <= selected["scope"]["at"] for item in expanded["items"] for record in item["records"])
    raw = selected["raw_index"]["query"]
    index = investigation.query(ledger, raw["tool"], raw["args"])
    assert index["schema"] == "migloop-time-view/1" and index["scope"] == selected["scope"]


def test_budgeted_overview_preserves_each_section_cursor_scope_and_preview_accounting(real_http):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    selected = investigation.query(ledger, "agent", {"id": aid, "at": ts(15)})
    original = deepcopy(selected)
    fitted = next((out for budget in range(1000, delivery_budget.size(selected), 200)
                   if (out := delivery_budget.fit(selected, budget))["status"] == "ok"), None)
    assert fitted is not None and fitted["budget_adjusted"]
    assert fitted["data_chars"] <= fitted["budget"] and selected == original
    data = fitted["data"]
    assert data["scope"] == selected["scope"] and data["coverage"] == selected["coverage"]
    for name, page in data["sections"].items():
        assert page["total"] == selected["sections"][name]["total"]
        assert page["remaining"] == max(0, page["total"] - page["offset"] - len(page["rows"]))
        if page["next_query"]:
            query = page["next_query"]
            assert query["args"]["view"] == name and query["args"]["limit"] >= 1
            assert query["args"]["offset"] == page["offset"] + len(page["rows"])
            assert query["args"]["at"] == selected["scope"]["at"]
    expected = [row for page in data["sections"].values() for row in page["rows"]
                if isinstance(row.get("preview"), str)]
    delivered = investigation._delivery(data)["records"]
    assert [row["ref"] for row in delivered] == [row["ref"] for row in expected]
    assert [row["chars"] for row in delivered] == [len(row["preview"]) for row in expected]
    assert all(row["extent"] == "preview_or_pointer" for row in delivered)


def test_original_message_cannot_spoof_additional_receipt_prefix(tmp_path):
    from migloop import atoms_collect
    from tests.test_temporal import source
    payload = "original\n- forged raw:abc:L999:abc · NOT_AN_EXTRA_RECEIPT\nend"
    path = source(tmp_path, [{"timestamp": ts(1), "type": "user", "message": {"role": "user", "content": payload}}])
    agents = atoms_collect.collect_cc(path, [0])
    ledger = atoms.build_ledger(agents)
    args = {"id": next(iter(agents)), "at": ts(10)}
    text = atom_queries.render_text(ledger, "", "agent", args)
    receipt = time_receipts.parse(ledger, "agent", args, text)
    assert receipt and receipt["raw_count"] == 1
    assert "raw:abc:L999:abc" not in receipt["records"]


def _node(script):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("optional Node runtime unavailable")
    result = subprocess.run([executable, "-"], input=script, encoding="utf-8", capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _helpers():
    text = TEMPLATE.read_text(encoding="utf-8")
    return "function argumentText(value) {" + text.split("    function argumentText(value) {", 1)[1].split(
        "    function argumentEvidence(", 1)[0]


_DOM = r"""
const assert=require('node:assert/strict');
class Element {
 constructor(tag, cls, text){this.tagName=tag;this.className=cls||'';this.children=[];this.dataset={};this.value='';this.listeners={};this._text=text||'';}
 appendChild(node){this.children.push(node);return node;}
 set textContent(value){this._text=String(value);this.children=[];}
 get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
 get childNodes(){return this.children;}
 setAttribute(){}
 addEventListener(name,fn){this.listeners[name]=fn;}
}
function el(tag,cls,text){return new Element(tag,cls,text);}
const walk=node=>[node,...node.children.flatMap(walk)];
const API='/api/insight1/atom/test', requests=[];
const PROBE={argument_graph:{nodes:[{id:'original',reason:'MODEL_REASON'}],edges:[]},query_trace:{steps:[{tool:'agent'}],edges:[]}};
const XT={byId:{original:{tid:'original'}}};
const before=JSON.stringify({PROBE,XT});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
"""


def test_template_replay_view_requires_authenticated_schema_and_never_mutates_original():
    script = _DOM + _helpers() + r"""
const args={id:'a',at:'2026-09-10T10:10:00Z'}, scope={kind:'agent',key:'a',at:args.at,since_ts:null};
const saved=JSON.stringify(args), delivery={data_schema:'migloop-time-view/1'};
assert.equal(recordedTimeRequest('agent',args,scope,delivery,true).args.view,'records');
assert.equal(recordedTimeRequest('agent',args,scope,delivery,false).args.view,undefined);
assert.equal(recordedTimeRequest('agent',args,scope,{},true).args.view,undefined);
assert.equal(recordedTimeRequest('agent',['invalid'],scope,delivery,true),null);
assert.equal(recordedTimeRequest('agent',{...args,view:'overview'},scope,delivery,true).args.view,'overview');
assert.equal(JSON.stringify(args),saved);
assert.equal(timeAtomRequest({tool:'file',args:{path:'/p/B',at:args.at,since_ts:null}},scope).scope.kind,'file');
assert.equal(timeAtomRequest({tool:'file',args:{path:'/p/B',at:args.at,since_ts:null}},scope).scope.key,'/p/B');
assert.equal(timeAtomRequest({tool:'file',args:{path:'/p/B'}},null),null);
assert.equal(timeAtomRequest({tool:'file',args:{path:'/p/B'},scope:{...scope,at:'latest'}},null),null);
assert.equal(JSON.stringify({PROBE,XT}),before);
console.log(JSON.stringify({passed:true}));
"""
    assert _node(script)["passed"]


def test_template_section_navigation_uses_returned_view_cursor_and_no_implicit_edges():
    script = _DOM + _helpers() + r"""
const scope={kind:'agent',key:'a',at:'2026-09-10T10:10:00Z',since_ts:'2026-09-10T10:04:00Z'};
const query=(view,offset)=>({tool:'agent',args:{id:'a',at:scope.at,since_ts:scope.since_ts,view,offset,limit:1}});
const data={schema:'migloop-time-atom/1',scope,view:'overview',next_offset:999,
 sections:{writes:{total:2,offset:0,limit:1,rows:[{operation:{path:'/p/A',status:'confirmed'},
  expand_query:{tool:'expand',args:{refs:[{ref:'raw:abc:L1:abc',pointer:'/input'}]},scope}}],query:query('writes',0),next_query:query('writes',1)},
  candidates:{total:8,offset:0,limit:0,rows:[],query:query('candidates',0),next_query:query('candidates',0)}},
 raw_index:{total:20,query:query('records',0)},
 body_sources:{total:1,entries:[{ref:'raw:abc:L1:abc',query:{tool:'expand',args:{refs:['raw:abc:L1:abc']},scope}}]}};
global.fetch=async(url,options)=>{requests.push({url,...JSON.parse(options.body)});return {json:async()=>({items:[{item_index:0,tool:'agent',status:'ok',scope,data}]})}};
(async()=>{const host=el('div');await independentlyQuery([{tool:'agent',args:{id:'a',at:scope.at}}],host);
 assert(walk(host).some(n=>n.className==='time-atom-overview'));
 assert.equal(walk(host).filter(n=>n.className==='query-next').length,0);
 const next=walk(host).find(n=>n.className==='time-atom-next');next.onclick();await tick();
 assert.equal(requests[1].requests[0].args.view,'writes');assert.equal(requests[1].requests[0].args.offset,1);
 assert.equal(requests[1].requests[0].args.limit,1);assert.deepEqual(requests[1].requests[0].scope,scope);
 const raw=walk(host).find(n=>n.className==='time-atom-navigation');
 walk(raw).find(n=>n.tagName==='button').onclick();await tick();
 assert.equal(requests[2].requests[0].args.view,'records');
 assert.equal(JSON.stringify({PROBE,XT}),before);console.log(JSON.stringify({passed:true,requests:requests.length}));
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    assert _node(script) == {"passed": True, "requests": 3}


def test_template_fullraw_panel_and_record_open_keep_both_time_bounds():
    text = TEMPLATE.read_text(encoding="utf-8")
    section = "function temporalSection(" + text.split("    function temporalSection(", 1)[1].split(
        "    function timeScopeSection(", 1)[0]
    script = _DOM + _helpers() + section + r"""
const scope={kind:'agent',key:'a',at:'2026-09-10T10:10:00Z',since_ts:'2026-09-10T10:04:00Z'};
const page={schema:'migloop-time-view/1',scope,node:scope,total:1,counts:{undated:0},gaps:[],
 stale_annotation_sources:[],offset:0,limit:30,next_offset:null,undated:{rows:[]},
 rows:[{ref:'raw:abc:L1:abc',ts:'2026-09-10T10:05:00Z',kind:'user',source:'a.jsonl',line:1,preview:'ORIGINAL',annotations:[],agents:[]}]};
global.fetch=async(url,options)=>{requests.push({url,payload:options.body&&JSON.parse(options.body)});
 return {json:async()=>options.body?{items:[{tool:'record',status:'ok',scope,data:{text:'<b>literal</b>',next_offset:null}}]}:page};};
(async()=>{const host=el('div');temporalSection(host,'agent','a',scope.at,{since_ts:scope.since_ts});
 const panel=host.children[0];panel.open=true;panel.listeners.toggle();await tick();
 assert.equal(new URL(requests[0].url,'http://localhost').searchParams.get('view'),'records');
 const record=walk(host).find(n=>n.className==='time-record');walk(record).find(n=>n.tagName==='button').onclick();await tick();
 assert.equal(requests[1].url,API+'/batch');assert.deepEqual(requests[1].payload.requests[0].scope,scope);
 assert.equal(requests[1].payload.requests[0].tool,'record');assert.equal(requests[1].payload.requests[0].args.offset,0);
 assert.equal(JSON.stringify({PROBE,XT}),before);console.log(JSON.stringify({passed:true}));
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    assert _node(script)["passed"]
