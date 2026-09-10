/* Deterministic v3 UI regression; no model, production service or run writes.
 * node tests/browser/argument_graph_smoke.cjs [http://127.0.0.1:19652]
 * Uses an existing local Chrome CDP endpoint and a temporary loopback fixture server.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {execFileSync} = require('node:child_process');

const at = '2026-01-01T00:00:20Z', since = '2026-01-01T00:00:10Z';
const scope = {kind: 'file', key: '/fixture/A.ets', at, since_ts: since};
const upstreamScope = {...scope, at: '2026-01-01T00:00:05Z', since_ts: null};
const ref = {ref: 'raw:abcdef:L3:123456', original_ref: 'raw:abcdef:L3:123456', status: 'ok', scope: upstreamScope};
function node(id, kind, key, role, time = at) {
  return {id, local_id: id.split('/')[1], finding: id.split('/')[0], kind, key, at: time, role,
    reason: 'reason for ' + id + ' <img src=x onerror="window.injected=true">', evidence: [ref],
    counterevidence: [{ref:'raw:late:L4:abcdef',status:'after_cutoff',diag:'Later than boundary'}],
    binding: {status:'matched',canonical_key:key,at:time},source:'model',semantic_checked:false};
}
const graph = {schema:'migloop-argument-graph/1',identity:{bound:true},target:{file:scope.key,since_ts:since,at},
  nodes:[node('A/input','file','/fixture/input.md','context',upstreamScope.at),
    node('A/author','agent','author-a','origin'),node('A/output','file',scope.key,'repaired'),
    node('A/isolated','file','/fixture/independent.md','context'),
    node('B/only','file',scope.key,'context','2026-01-02T00:00:20Z')],
  edges:[{finding:'A',from:'A/input',to:'A/author',relation:'read',claim:'explicit read claim',evidence:[ref],binding:{status:'confirmed',evidence:[ref]}},
    {finding:'A',from:'A/author',to:'A/output',relation:'possible_write',claim:'possible write only',evidence:[ref],binding:{status:'candidate',evidence:[ref]}},
    {finding:'A',from:'A/output',to:'A/isolated',relation:'read',claim:'unknown link <script>bad</script>',evidence:[],binding:{status:'not_observed',diag:'No direct source edge'}},
    {finding:'A',from:'A/missing',to:'A/unknown',relation:'write',claim:'invalid endpoints',evidence:[],binding:{status:'invalid'}}],
  findings:[{id:'A',title:'First <b>finding</b>',reason:'First reason',status:'explained',nodes:['A/input','A/author','A/output','A/isolated'],
    changes:[{reason:'change explanation'}],hypothesis:'Hypothesis, not certified',validation:'No device proof',unknown:'Unknown author'},
    {id:'B',title:'Second finding',reason:'Second reason',status:'unresolved',nodes:['B/only']}],
  coverage:{complete:false,missing:['another change']},diagnostics:['This is a fixture, not causal truth']};
const queryTrace = {schema:'migloop-query-trace/1',steps:[
  {step:1,tool:'search',args:{sid:'fixture',q:'needle',file:scope.key,at,since_ts:since,offset:30,scope:{...scope,id:'scope-display-id'}},scope,status:'recorded_response',delivery:{truncated:true,chars:18}},
  {step:2,tool:'diff',args:{path:scope.key,at,since_ts:since,max_chars:600},scope,status:'recorded_response',delivery:{kind:'diff',chars:600}},
  {step:3,tool:'record',args:{ref:ref.ref,offset:5,max_chars:100},scope:upstreamScope,status:'recorded_response',delivery:{offset:5,chars:100}},
  {step:4,tool:'batch',args:{requests:JSON.stringify([{tool:'search',args:{q:'batch needle'},scope},{tool:'diff',args:{path:scope.key},scope}]),max_chars:16000},status:'recorded_response',items:[
    {item_index:0,tool:'search',args:{q:'batch needle'},scope,status:'ok',delivery:{chars:20}},
    {item_index:1,tool:'diff',args:{path:scope.key},scope,status:'deferred',delivery:null}]},
  {step:5,tool:'changes',args:{path:scope.key,at,since_ts:since},scope,status:'recorded_response',delivery:{records:[]}}
]};
const probe = {run:'fixture-v3',argument_graph:graph,query_trace:queryTrace,steps:[],trajectory:{nodes:[],visits:[],transitions:[]}};
graph.nodes.at(-1).evidence=[{...ref,ref:'#author:1@L3',original_ref:'#author:1@L3',raw_ref:ref.ref,type:'legacy'}];
const backendProjection=JSON.parse(execFileSync(process.env.PYTHON || 'python',['-c',[
  'import json,tempfile,sys', 'sys.path.insert(0,"src")', 'from pathlib import Path', 'from migloop import verdict_v3',
  'from tests.test_verdict_v3 import document', 'from tests.test_verdict import _pool',
  'with tempfile.TemporaryDirectory(prefix="migloop-argument-browser-") as d:',
  ' ledger=_pool(Path(d))', ' print(json.dumps(verdict_v3.build(ledger,document(ledger))))'
].join('\n')],{cwd:path.resolve(__dirname,'../..'),encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONUTF8:'1'}}));
const data = {sid:'fixture',sid8:'fixture',project:'V3 UI',urls:{data:'/data',atom:'/atom',probe:'/probe',report:null}};
const template = fs.readFileSync(path.join(__dirname,'../../src/migloop/render/templates/fixchain.html'),'utf8');
const page = template.replace('__FIXCHAIN_JSON__',JSON.stringify(data));
const requests = [];
const server = http.createServer(async (req,res) => {
  const url = new URL(req.url,'http://127.0.0.1');
  if(url.pathname === '/') {res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end(page);return;}
  let body;
  if(req.method === 'POST') {
    const chunks=[]; for await(const chunk of req)chunks.push(chunk);
    const posted=JSON.parse(Buffer.concat(chunks).toString('utf8'));requests.push({path:url.pathname,body:posted});
    if(url.pathname === '/atom/check') body={argument_graph:graph,diagnostics:[],target:graph.target};
    else if(url.pathname === '/atom/batch') body={schema:'migloop-query-batch/1',ledger:'fixture',items:posted.requests.map((r,i)=>({
      item_index:i,tool:r.tool,args:r.args,scope:r.scope,status:'ok',delivery:{chars:50},data:r.tool==='record'
        ? {schema:'migloop-raw-record/1',text:'RAW <b>not markup</b>',next_offset:r.args.offset===0?5:null}
        : r.tool==='changes' ? {schema:'migloop-time-changes/1',rows:[{status:'observed_change',use_ts:null,done_ts:null,observed_at:at,change_time:null,agent:null}]}
        : {tool:r.tool,request:r.args,scope:r.scope,rows:[]}}))};
    else body={error:'Unexpected POST'};
  } else if(url.pathname === '/data') body={chains:[],t0:'2026-01-01T00:00:00Z'};
  else if(url.pathname === '/atom/index') body={files:[],agents:[]};
  else if(url.pathname === '/probe') body=url.searchParams.get('run')==='legacy'
    ? {run:'legacy',steps:[],links:[],roles:{},defects:{},legacy:true}
    : url.searchParams.get('run')==='backend' ? {...backendProjection,run:'backend',query_trace:{steps:[]}}
    : url.searchParams.get('run')==='unbound' ? {...probe,run:'unbound',trace_identity:{bound:false}} : probe;
  else body={error:'Unexpected GET'};
  res.writeHead(200,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify(body));
});

async function main() {
  const endpoint=process.argv[2] || 'http://127.0.0.1:19652';
  assert.equal(new URL(endpoint).hostname,'127.0.0.1','local CDP only');
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  let socket,target;
  try {
    target=await(await fetch(endpoint+'/json/new?about:blank',{method:'PUT'})).json();
    socket=new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
    let serial=0;const pending=new Map(),errors=[];
    socket.onmessage=event=>{const msg=JSON.parse(event.data);
      if(msg.method==='Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
      const waiter=pending.get(msg.id);if(waiter){pending.delete(msg.id);clearTimeout(waiter.timer);msg.error?waiter.reject(Error(JSON.stringify(msg.error))):waiter.resolve(msg.result);}};
    const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);
      pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
    const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;};
    const until=async(expression,label)=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100));}throw Error('Timeout '+label);};
    await send('Page.enable');await send('Runtime.enable');
    await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1200,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:origin+'/?probe=v3'});
    await until("document.querySelectorAll('.argument-card').length===4 && document.querySelectorAll('.argument-wire').length===2",'argument graph');
    assert.equal(await evaluate("document.querySelector('#graph').classList.contains('argument-mode')"),true);
    const snapshot=()=>evaluate("JSON.stringify({graph:__mig.probe().argument_graph,trace:__mig.probe().query_trace,trajectory:__mig.probe().trajectory})");
    const before=await snapshot();
    assert.deepEqual(await evaluate("[...document.querySelectorAll('.argument-wire')].map(n=>({from:n.dataset.from,to:n.dataset.to,status:n.dataset.status})).sort((a,b)=>a.from.localeCompare(b.from))"),
      [{from:'A/author',to:'A/output',status:'candidate'},{from:'A/input',to:'A/author',status:'confirmed'}]);
    assert.equal(await evaluate("document.querySelectorAll('.argument-break').length"),2,'unobserved and invalid edges stay visible breaks');
    assert(await evaluate("[...document.querySelectorAll('.argument-card')].find(n=>n.dataset.nodeId==='A/isolated').textContent.includes('独立材料 / 断点')"));
    assert(await evaluate("!document.querySelector('#argument-view').textContent.includes('@v')"),'no invented version');
    assert.equal(await evaluate("document.querySelectorAll('#argument-view b b,#side img,#argument-view script').length"),0,'model text escaped');
    assert(await evaluate("document.querySelector('#side .argument-node-reason').textContent.includes('reason for A/input')"));
    assert.equal(await evaluate("[...document.querySelectorAll('#side .argument-reference')].find(n=>n.textContent.includes('raw:late:')).querySelectorAll('button').length"),0,'late counterevidence remains nonnavigable');
    await evaluate("document.querySelector('#side .argument-open-original').click()");
    await until("document.querySelector('#side').textContent.includes('RAW <b>not markup</b>')",'original response');
    assert.deepEqual(requests.at(-1).body.requests[0],{tool:'record',args:{ref:ref.ref,offset:0,max_chars:12000},scope:upstreamScope},'upstream scope is not narrowed to repair interval');
    assert.equal(await evaluate("document.querySelectorAll('#side .query-recheck-result pre b').length"),0);
    await evaluate("document.querySelector('#side .query-next').click()");
    await until("document.querySelectorAll('#side .query-recheck-result').length===2",'record pagination');
    assert.equal(requests.at(-1).body.requests[0].args.offset,5);assert.deepEqual(requests.at(-1).body.requests[0].scope,upstreamScope);
    await evaluate("document.querySelector('.query-trace').open=true;[...document.querySelectorAll('.query-item')].find(n=>n.dataset.tool==='diff').querySelector('.query-recheck').click()");
    await until("[...document.querySelectorAll('.query-item')].find(n=>n.dataset.tool==='diff').querySelector('.query-recheck-result')",'diff replay');
    assert.deepEqual(requests.at(-1).body.requests[0],{tool:'diff',args:queryTrace.steps[1].args,scope});
    await evaluate("[...document.querySelectorAll('.query-item')].find(n=>n.dataset.tool==='search'&&!n.hasAttribute('data-item-index')).querySelector('.query-recheck').click()");
    await until("[...document.querySelectorAll('.query-item')].find(n=>n.dataset.tool==='search').querySelector('.query-recheck-result')",'search replay');
    const replayedSearch={...queryTrace.steps[0].args};delete replayedSearch.sid;delete replayedSearch.scope;
    assert.deepEqual(requests.at(-1).body.requests[0],{tool:'search',args:replayedSearch,scope},'routing and scope metadata removed only from replay, not historical display');
    await evaluate("[...document.querySelectorAll('.query-item')].find(n=>n.dataset.tool==='batch').querySelector('.query-recheck').click()");
    await until("[...document.querySelectorAll('.query-item')].find(n=>n.dataset.tool==='batch').querySelector('.query-recheck-result')",'batch replay');
    assert.deepEqual(requests.at(-1).body.requests,JSON.parse(queryTrace.steps[3].args.requests));
    assert.equal(requests.at(-1).body.max_chars,16000,'original batch budget preserved');
    assert.equal(await evaluate("document.querySelectorAll('.query-item[data-item-index]').length"),2,'batch items retained, including deferred');
    await evaluate("[...document.querySelectorAll('.query-item')].find(n=>n.dataset.tool==='changes').querySelector('.query-recheck').click()");
    await until("document.querySelector('.observation-time-note')",'observed change timestamps');
    const observation=await evaluate("JSON.parse(document.querySelector('.observation-time-note').parentNode.querySelector('pre').textContent).rows[0]");
    assert.equal(observation.observed_at,at);assert.equal(observation.use_ts,null);assert.equal(observation.done_ts,null);assert.equal(observation.change_time,null);
    assert(await evaluate("document.querySelector('.observation-time-note').textContent.includes('不等于修改时刻')"));
    assert.equal(await snapshot(),before,'viewer queries preserve graph, trace and trajectory');
    await evaluate("[...document.querySelectorAll('.argument-findings button')].find(n=>n.dataset.finding==='B').click()");
    assert.equal(await evaluate("document.querySelectorAll('.argument-card').length"),1);
    assert.equal(await evaluate("document.querySelectorAll('.argument-wire').length"),0);
    assert(await evaluate("document.querySelector('#side .argument-node-reason').textContent.includes('B/only')"),'finding reasons do not leak');
    assert.equal(await snapshot(),before,'finding selection is only presentation state');
    await evaluate("document.querySelector('#side .argument-open-original').click()");
    await until("document.querySelector('#side').textContent.includes('RAW <b>not markup</b>')",'legacy reference mapped original');
    assert.equal(requests.at(-1).body.requests[0].args.ref,ref.ref,'legacy spelling preserved but authenticated raw_ref used to open');
    const draft='schema: migloop-verdict/3\nnotes: "<script>unsafe</script>"';
    await evaluate(`(()=>{const box=document.querySelector('.draft-loader');box.open=true;box.querySelector('textarea').value=${JSON.stringify(draft)};box.querySelector('input').value='/fixture/A.ets';box.querySelector('.draft-submit').click();})()`);
    await until("__mig.probe().manual_input===true && document.querySelector('.manual-trace-note')",'manual document');
    assert.deepEqual(requests.findLast(r=>r.path==='/atom/check').body,{draft,file:'/fixture/A.ets'});
    assert.equal(await evaluate("__mig.probe().query_trace == null && __mig.probe().steps.length===0"),true,'manual document never inherits run trace');
    assert(await evaluate("document.querySelector('.query-trace').textContent.includes('没有实际调查轨迹')"));
    await evaluate("__mig.load('legacy')");
    await until("__mig.probe().run==='legacy'",'legacy load');
    assert.equal(await evaluate("document.querySelector('#graph').classList.contains('argument-mode')"),false,'legacy display restored');
    assert.equal(await evaluate("document.querySelectorAll('.draft-loader').length"),1,'paste remains available for old reports');
    await evaluate("__mig.load('backend')");
    await until("__mig.probe().run==='backend' && document.querySelectorAll('.argument-card').length===3 && document.querySelectorAll('.argument-wire').length===2",'real backend v3 projection');
    assert.deepEqual(await evaluate("[...document.querySelectorAll('.argument-card')].map(n=>n.dataset.nodeId)"),backendProjection.argument_graph.nodes.map(n=>n.id));
    assert(await evaluate("document.querySelectorAll('#side .argument-open-original').length>=2"),'nested operation evidence from real backend is expandable');
    assert.equal(await evaluate("document.querySelector('#side .argument-detail').dataset.semanticChecked"),'false');
    await evaluate("__mig.load('unbound')");
    await until("__mig.probe().run==='unbound' && document.querySelector('.argument-unbound')",'identity conflict');
    assert.equal(await evaluate("document.querySelectorAll('.argument-wire,.argument-open-original,.argument-inspect-node').length"),0,'identity conflict cannot promote stale positive bindings');
    assert.equal(await evaluate("document.querySelectorAll('.argument-card').length"),4,'unbound model material remains visible');
    assert.deepEqual(errors,[],'no browser exceptions');
    console.log(JSON.stringify({passed:true,checks:['v3 graph','finding isolation','explicit edges only','independent material','escaped text','record scope and pagination','search/diff/batch replay','immutable trace','manual paste','legacy compatibility','actual backend projection shape'],requests:requests.length}));
  } finally {if(socket)socket.close();if(target)await fetch(endpoint+'/json/close/'+target.id).catch(()=>{});await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
