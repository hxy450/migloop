/* Offline browser regression. Requires Node >= 22 and an existing local Chrome CDP endpoint.
 * node tests/browser/trace_fidelity.cjs [http://127.0.0.1:19652]
 * Serves only deterministic fixtures on an ephemeral loopback port; never calls a model.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const repo = path.resolve(__dirname, '../..');
const file = '/fixture/A.ets';
const fid = 'file:' + file;
const aid = 'agent:agent-a@1';
const bid = 'agent:agent-b@1';
const root = fid + '@3';
const roles = [
  {key:'agent-a',kind:'agent',v:1,defect:'A',role:'进入·错',reason:'A 独有原因',entry:true,checked:'not_checked',evidence:[{type:'action',ref:'#a:1@L1',status:'ok',aid:'agent-a',v:1,seq:1}]},
  {key:'agent-a',kind:'agent',v:1,defect:'B',role:'正常',reason:'B 独有原因',checked:'not_checked',evidence:[{type:'action',ref:'#a:2@L2',status:'ok',aid:'agent-a',v:1,seq:2}]}
];
const legacyRole = {key:file,kind:'file',v:1,defect:'A',role:'带病传递',reason:'未查询版本的主张',checked:'not_checked',evidence:[]};
const nodes = [
  {id:root,kind:'file',key:file,v:3,label:'A.ets@v3',parent:null,side:'root',source:'查过',opened:[1,6],unseen:1,unseen_neighbors:[{kind:'agent',key:'agent-a',v:2}]},
  {id:aid,kind:'agent',key:'agent-a',v:1,label:'Agent A v1',parent:root,side:'up',source:'查过',opened:[2,4,5],unseen:0},
  {id:bid,kind:'agent',key:'agent-b',v:1,label:'Agent B v1',parent:root,side:'up',source:'查过',opened:[3],unseen:0},
  {id:fid+'@1',kind:'file',key:file,v:1,label:'A.ets@v1',parent:root,side:'unlinked',source:'结论',opened:[],unseen:0,note:'结论点名,没打开'}
];
const transitions = [
  {step:2,from:root,to:aid,relation:null,match:'账本无此边'},
  {step:3,from:root,to:bid,relation:null,match:'账本无此边'},
  {step:4,from:bid,to:aid,relation:null,match:'账本无此边'},
  {step:5,from:aid,to:aid,relation:null,match:'账本无此边'},
  {step:6,from:aid,to:root,relation:null,match:'账本无此边'}
];
const visits = [1,2,3,4,5,6].map(step=>{
  const tr=transitions.find(t=>t.step===step), id=tr ? tr.to : root;
  const n=nodes.find(n=>n.id===id);
  return {step,tool:n.kind,node:id,requested_node:id,from:tr?tr.from:null,status:'opened',verified:true,
    delivery_truncated:step===5,note:step===5?'返回截断／非全文：只收到可见片段，不证明全文交付':null,
    via:tr?tr.from.replace(/@(\d+)$/, '@v$1'):'sessions',scope:step===5?'窗口 v0→v1 · start=2 n=4':'正文 v'+n.v,
    result_ref:'toolu_'+step,args:n.kind==='file'?{path:file,v:n.v}:{id:n.key,v:n.v,since:step===5?0:undefined,start:step===5?2:undefined,n:step===5?4:undefined}};
});
visits.push({step:7,tool:'file',node:null,requested_node:fid+'@1',from:aid,status:'rejected',via:'agent:agent-a@v99',scope:'正文 v1',args:{path:file,v:1},note:'来处没有打开'});
const steps=visits.map(v=>{
  const n=nodes.find(n=>n.id===(v.node||v.requested_node));
  return {i:v.step,tool:v.tool,via:v.via,scope:v.scope,args:v.args,ok:true,chars:10,node:{kind:n.kind,path:n.kind==='file'?n.key:undefined,aid:n.kind==='agent'?n.key:undefined,v:n.v}};
});
function claim(r) { return {...r,ok:true,label:r.kind==='file'?'A.ets@v'+r.v:'Agent A v'+r.v,spec:r.kind+':'+r.key+'@v'+r.v}; }
const probe={run:'fixture',root:file,cost:0,steps,links:[],legacy:false,roles:{'agent-a':roles,[file]:[legacyRole]},fixed:[],defects:{A:'缺陷甲',B:'缺陷乙'},
 trace_identity:{bound:true,status:'matched',current:'fixture-ledger',source:'sessions',source_identities:['fixture-ledger']},
 structured:{identity:{match:true,bound:true,status:'matched'},errors:[],defects:[{id:'A',title:'缺陷甲',nodes:[claim(roles[0]),claim(legacyRole)],edges:[]},{id:'B',title:'缺陷乙',nodes:[claim(roles[1])],edges:[]}]},
 trajectory:{mode:'via',root,nodes,edges:[],visits,transitions,declared:[],side_title:'未查询 · 结论提及'}};
const candidateOne='candidate:'+'a'.repeat(20), candidateTwo='candidate:'+'b'.repeat(20);
function coverageFixture(body){
  body.repair_manifest_origin={source:'recorded',bound:true,policy:'legacy',current_policy:'execution-candidates/2',policy_changed:true};
  const item=v=>({node:fid+'@v'+v,v,writer:{id:'agent-a',v:1},event:{status:'recorded',seq:100+v,ref:'#a:'+(100+v)+'@L'+v},change:{text:'变化摘录',semantic_checked:false}});
  const candidate=(id,seq)=>({id,agent:'agent-b',file,seq,reason:'精确提及，执行效应未确认',ctx:'shell 候选命令，不据此认定写者',repair_confirmed:false,writer_confirmed:false,
    event:{status:'recorded',seq,ref:'#b:'+seq+'@L10',use_line:10,result_line:11,tool_use_id:'candidate-tool-'+seq}});
  const row=(target,status,reason)=>({canonical_target:target,canonical_node:target.startsWith('file:')?target:null,canonical_candidate:target.startsWith('candidate:')?target:null,
    status,reason,valid:true,defects:[],evidence:['#a:1@L1'],semantic_checked:false,evidence_checked:false});
  body.repair_manifest={ledger:'fixture-ledger',file,items:[1,2,3].map(item),candidates:[candidate(candidateOne,201),candidate(candidateTwo,202)],errors:[],
    scope:'仅当前账本返修版本及候选，不保证包含所有真实修复；候选不是作者认定。',candidate_scope:{window_scope:'同链参与者的动作窗口，不保证动作属于修复阶段。'}};
  body.coverage={provided:true,identity_bound:true,status:'incomplete',complete:false,semantic_checked:false,evidence_checked:false,
    rows:[row(fid+'@v1','explained','生成输入已有依据'),row(fid+'@v3','unresolved','缺少执行过程，仍未知'),row(candidateOne,'not_repair','模型声明只是检查，未独立验证')],
    missing_versions:[fid+'@v2'],missing_candidates:[candidateTwo],missing:[fid+'@v2',candidateTwo],unresolved:[fid+'@v3'],not_repair:[candidateOne],duplicates:[],errors:[],
    counts:{expected:5,provided:3,accounted:3,expected_versions:3,expected_candidates:2,missing_versions:1,missing_candidates:1,missing:2,unresolved:1,not_repair:1}};
  return row;
}
const versions=[1,2,3].map(v=>({v,by:v===2?'agent-b':'agent-a',by_name:v===2?'Agent B':'Agent A',by_ver:v===3?2:1,ts:'2026-01-01T00:00:0'+v+'Z',lines:1,content_known:false,source:'opaque'}));
const agents=['agent-a','agent-b'].map(id=>({id,label:id==='agent-a'?'Agent A':'Agent B',n_versions:id==='agent-a'?2:1,kind:'agent',session:'fixture',reads:[],writes:[],actions:[],inbox:[]}));
agents[0].reads=[
  {path:file,v:1,at:1,certain:false,dep:false,observation_uncertain:true},
  {path:file,v:1,at:1,certain:true,dep:false,observation_uncertain:false},
  {path:file,v:2,at:1,certain:false,dep:true,observation_uncertain:true}
];
const data={sid:'fixture',sid8:'fixture',project:'Trace fidelity regression',urls:{data:'/data',atom:'/atom',probe:'/probe',filediff:'/diff',report:null}};
const html=fs.readFileSync(path.join(repo,'src/migloop/render/templates/fixchain.html'),'utf8').replace('__FIXCHAIN_JSON__',JSON.stringify(data));
let activeFixture='fixture';
function timeScopeFixture(v, agent){
  const anchor='2026-01-01T00:00:0'+v+'.000000Z';
  const root=(session,id,end)=>({session,observed_start:'2026-01-01T00:00:00.000000Z',observed_end:end,
    root_present:true,root_agent:id,root_ambiguous:false,root_agents:[{id,versions:{first:1,last:3,count:3},source_paths:['/fixture/'+session+'.jsonl']}],
    after_anchor:{started:2,results_returned:1,observed_actions:2,known_straddling:1}});
  return {schema:'migloop-time-scope/1',anchor:{time:anchor,status:'valid',agent:agent||'agent-a',session:'fixture'},
    latest_known_pool_time:'2026-01-03T00:00:00.000000Z',later_sessions:['fixture','later-session'],other_later_sessions:['later-session'],
    roots:[root('fixture','__main__:fixture','2026-01-02T00:00:00.000000Z'),root('later-session','__main__:later','2026-01-03T00:00:00.000000Z'),
      {session:null,root_present:false,root_agents:[],observed_start:null,observed_end:null,after_anchor:null}],
    unknown_intervals:1,reversed_intervals:0,diagnostics:[],scope_complete:false,negative_proof:false,
    scope:'只汇总已提供动作时间；后续活动不证明验证成功，零计数不证明全局无活动。'};
}
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  let body;
  if(url.pathname==='/') {activeFixture=url.searchParams.get('probe')||'fixture';res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}
  if(url.pathname==='/data')body={chains:[]};
  else if(url.pathname==='/atom/index')body={agents,files:[{path:file,kind:'ets',n_versions:3,has_writer:true}]};
  else if(url.pathname==='/probe'){
    body=structuredClone(probe);
    const run=url.searchParams.get('run');
    activeFixture=run;
    if(run.startsWith('coverage')||run.startsWith('trace-')){
      const row=coverageFixture(body);
      if(run==='coverage-invalid'){
        body.coverage.rows.push({...body.coverage.rows[0],reason:'重复声明不可自动选优'});
        body.coverage.status='invalid';body.coverage.counts.accounted=2;body.coverage.counts.provided=4;
        body.coverage.duplicates=[{node:fid+'@v1',rows:[0,3]}];body.coverage.errors=[{code:'duplicates',node:fid+'@v1'}];
      }
      if(run==='coverage-complete'){
        body.coverage.rows.push(row(fid+'@v2','explained','补充的版本交代'),row(candidateTwo,'unresolved','候选已登记但未查清'));
        Object.assign(body.coverage,{complete:true,status:'complete',missing:[],missing_versions:[],missing_candidates:[],unresolved:[fid+'@v3',candidateTwo]});
        Object.assign(body.coverage.counts,{accounted:5,provided:5,missing:0,missing_versions:0,missing_candidates:0,unresolved:2});
      }
      if(run==='coverage-advisories'){
        const advice={code:'recorded_change_needs_basis',level:'warning',row:0,target:fid+'@v1',changed_lines:4,event_ref:'#a:101@L1',message:'有字面变化行，非修复声明仍需依据 <b>原文</b>'};
        body.coverage.rows[0]=row(fid+'@v1','not_repair','本次原状态保持，提示不是自动判错');
        Object.assign(body.coverage.rows[0],{row:0,advisories:[advice],claim_advisories_checked:true,recorded_changed_lines:4});
        body.coverage.rows.push(row(fid+'@v2','out_of_scope','本题未调查，可能是真实修复'),row(candidateTwo,'out_of_scope','候选仍需交代，不判无改动'));
        Object.assign(body.coverage,{complete:true,status:'complete',missing:[],missing_versions:[],missing_candidates:[],deferred:[fid+'@v2',candidateTwo],unconfirmed:[fid+'@v3',fid+'@v2',candidateTwo],
          advisories:[advice],claim_advisories_checked:true,not_repair:[fid+'@v1',candidateOne]});
        Object.assign(body.coverage.counts,{accounted:5,provided:5,missing:0,missing_versions:0,missing_candidates:0,deferred:2,unconfirmed:3,not_repair:2,advisories:1,advisory_rows:1});
      }
      if(run==='coverage-unprovided'){
        Object.assign(body.coverage,{provided:false,status:'unprovided',rows:[],unresolved:[],not_repair:[],missing_versions:[1,2,3].map(v=>fid+'@v'+v),missing_candidates:[candidateOne,candidateTwo]});
        Object.assign(body.coverage.counts,{accounted:0,provided:0,missing:5,missing_versions:3,missing_candidates:2,unresolved:0,not_repair:0});
      }
      if(run==='coverage-compat'){
        Object.assign(body.structured,{notes:['保留备注甲','<b>备注乙不是HTML</b>'],revalidated:true,previous_errors:['notes 必须是字符串']});
      }
      if(run==='coverage-absent-version'){
        body.repair_manifest.items[1]={...body.repair_manifest.items[1],v:99,node:fid+'@v99'};
        body.coverage.missing_versions=[fid+'@v99'];body.coverage.missing=[fid+'@v99',candidateTwo];
      }
      if(run==='trace-mismatch'){
        body.trace_identity={bound:false,status:'mismatch',current:'current-ledger',source:'sessions+harness',source_identities:['old-ledger'],harness_identity:'old-ledger',diag:'成功 sessions 记录与当前账本不匹配'};
        // Deliberately retain stale bound claims/nodes: the page must still fail closed on explicit trace conflict.
      }
      if(run==='trace-legacy')body.trace_identity={bound:null,status:'legacy',current:'fixture-ledger',source:null,diag:'查询轨迹身份未记录'};
    }
    if(run==='metrics'){
      body.steps.forEach(s=>{s.provenance={format:'codex_rollout_event',path:'transcript.jsonl',pairing:'item_runtime'};});
      for(let i=0;i<70;i++) body.steps.push({i:8+i,tool:'guide',ok:true,args:{},provenance:{format:'codex_rollout_event',path:'transcript.jsonl',pairing:'item_runtime'}});
      for(let i=0;i<41;i++) body.steps.push({i:78+i,tool:i%2?'functions.exec':'exec',ok:true,args:{input:'host wrapper'},call_id:'host-'+i,use_line:100+i*2,result_line:101+i*2,provenance:{format:'codex_rollout',path:'transcript.jsonl',pairing:'call_id'}});
    }
    if(run==='other-calls') body.steps.push({i:8,tool:'Bash',ok:true,args:{command:'read-only'},provenance:{format:'claude_transcript',path:'transcript.jsonl'}});
    if(run==='legacy'){body.structured=null;body.legacy=true;delete body.trace_identity;}
    if(run.startsWith('consistency')){
      const advice={code:'entry_role_conflict',level:'warning',defect:'A',node:'agent:agent-a@v1',message:'声明间需核对 <b>不判原因真假</b>'};
      body.structured.consistency={checked:true,semantic_checked:false,advisories:[advice]};
      body.structured.defects[0].advisories=[advice];body.structured.defects[1].advisories=[];
      if(run==='consistency-unbound'){
        body.structured.identity={bound:false,status:'missing',match:null};body.structured.consistency.checked=false;
      }
    }
    if(run==='relations'){
      const red={...legacyRole,v:3,reason:'两端红也不把探索线染红'};
      body.roles[file].push(red);body.structured.defects[0].nodes.push(claim(red));
      Object.assign(body.trajectory.transitions[0],{relation_status:'unknown',relation_label:'候选·条件读取待核',relation_note:'条件分支中提到，是否读到未知',relation_evidence:[{seq:11,basis:'conditional_read',source:'/fixture/original.jsonl',use_line:4,result_line:5}]});
      body.trajectory.nodes[1].relation_check={...body.trajectory.transitions[0]};
      Object.assign(body.trajectory.transitions[1],{relation_status:'true',relation:'写者 v3',relation_label:'账本·写者 v3',relation_note:'写于 agent v1'});
      body.trajectory.transitions.slice(2).forEach(t=>Object.assign(t,{relation_status:'false',relation_label:'查询导航·未核出直接账本边'}));
      const source={id:'abc',step:8,hit:1,call_id:'toolu_search_8',item_id:null,result_line:16,note:'只证明原生 search 返回，不证明外层执行包装完整转交模型'};
      body.steps.push({i:8,tool:'search',args:{q:'correct spec'},ok:true});
      body.trajectory.searches=[{...source,status:'verified',hits:[{kind:'file',key:file,v:1}]}];
      body.trajectory.nodes[3].opened=[9];body.trajectory.nodes[3].source='查过';body.trajectory.nodes[3].search_source=source;
      body.trajectory.transitions.push({step:9,from:null,to:fid+'@1',source:'search',search_source:source,relation:null,relation_status:'not_checked',relation_label:'搜索 #8 命中 1 · 查询导航',relation_note:source.note});
      body.trajectory.visits.push({step:9,tool:'file',node:fid+'@1',requested_node:fid+'@1',status:'opened',verified:true,via:'search:abc:1',search_source:source,args:{path:file,v:1}});
    }
    if(run==='navigation'){
      const added=[
        {id:fid+'@2',kind:'file',key:file,v:2,label:'A.ets@v2',parent:root,side:'up',source:'查过',opened:[8]},
        {id:'agent:agent-a@2',kind:'agent',key:'agent-a',v:2,label:'Agent A v2',parent:aid,side:'up',source:'查过',opened:[9]},
        {id:'file:/else/A.ets@2',kind:'file',key:'/else/A.ets',v:2,label:'Other A.ets@v2',parent:root,side:'up',source:'查过',opened:[10]}
      ];
      body.trajectory.nodes.push(...added);
      added.forEach(n=>{
        const step=n.opened[0], args=n.kind==='file'?{path:n.key,v:n.v}:{id:n.key,v:n.v};
        body.trajectory.transitions.push({step,from:n.parent,to:n.id,relation:null,match:'账本无此边'});
        body.trajectory.visits.push({step,tool:n.kind,node:n.id,requested_node:n.id,from:n.parent,status:'opened',verified:true,args});
        body.steps.push({i:step,tool:n.kind,ok:true,args,node:{kind:n.kind,path:n.kind==='file'?n.key:undefined,aid:n.kind==='agent'?n.key:undefined,v:n.v}});
      });
    }
    if(url.searchParams.get('run')==='no-root'||url.searchParams.get('run')==='empty'){
      body.trajectory.root=null;body.trajectory.nodes=[{...nodes[3],parent:null}];body.trajectory.transitions=[];
      body.trajectory.visits=visits.filter(v=>v.status==='rejected');body.steps=steps.filter(s=>s.i===7);
      if(url.searchParams.get('run')==='empty'){body.trajectory.nodes=[];body.structured.defects=[];body.roles={};}
    }
  }
  else if(url.searchParams.get('scope_only')==='1')body=activeFixture==='time-scope-failure'?{error:'fixture scope unavailable'}:
    {time_scope:timeScopeFixture(Number(url.searchParams.get('v')||3),url.searchParams.get('id'))};
  else if(url.pathname==='/atom/file'){
    const reader=(by,at,seq,extra={})=>({by,by_name:by,at,seq,v:1,ts:'2026-01-01T00:00:05Z',full:false,certain:true,...extra});
    const readers=activeFixture==='tail-readers' ? [
      reader('agent-a',1,301,{agent_v:1,feeding_slot:1,after_last_effect:false}),
      reader('agent-a',3,302,{agent_v:null,feeding_slot:3,after_last_effect:true}),
      reader('agent-b',2,303),reader('agent-b',1,304),reader('agent-missing',8,305),
      reader('agent-absent',null,306,{agent_v:null,feeding_slot:null,after_last_effect:false}),
      reader('agent-a',1,307,{agent_v:null,feeding_slot:1,after_last_effect:false})
    ] : [];
    body={path:file,v:3,versions,readers,mentions:[{by:'agent-b',by_name:'Agent B',by_ver:1,cls:'change',ctx:'lexical candidate',win:1}]};
  }
  else if(url.pathname==='/atom/agent')body=agents.find(a=>a.id==='agent-'+url.searchParams.get('id'))||agents[0];
  else if(url.pathname==='/atom/action')body={input:'ACTION '+url.searchParams.get('seq'),output:'EVIDENCE '+url.searchParams.get('seq')};
  else body={};
  res.setHeader('Content-Type','application/json; charset=utf-8');res.end(JSON.stringify(body));
});

async function main(){
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  const endpoint=process.argv[2]||'http://127.0.0.1:19652';
  const target=await (await fetch(endpoint+'/json/new?about:blank',{method:'PUT'})).json();
  const socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  let serial=0;const pending=new Map(),errors=[];
  socket.onmessage=event=>{
    const msg=JSON.parse(event.data);
    if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails.text+': '+(msg.params.exceptionDetails.exception?.description||''));
    if(msg.id&&pending.has(msg.id)){const p=pending.get(msg.id);pending.delete(msg.id);clearTimeout(p.timer);msg.error?p.reject(Error(JSON.stringify(msg.error))):p.resolve(msg.result);}
  };
  function send(method,params={}){return new Promise((resolve,reject)=>{const id=++serial;const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
  async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
  async function until(expression){for(let i=0;i<80;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,50));}throw Error('Condition failed: '+expression);}
  async function check(name,expression){assert.equal(await evaluate(expression),true,name);console.log('PASS '+name);}
  const clickAgent="[...document.querySelectorAll('#canvas .node')].find(n=>n.textContent.startsWith('Agent A v1')).click()";
  try{
    await send('Runtime.enable');await send('Page.enable');
    await send('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:origin+'/?probe=fixture'});
    await until("window.__mig && __mig.xt() && __mig.xt().walk && document.querySelectorAll('.wire.route').length === 5");
    await check('all transitions including revisit, multi-parent and self-loop',"JSON.stringify([...document.querySelectorAll('.wire.route')].map(n=>Number(n.dataset.step))) === '[2,3,4,5,6]'");
    await check('one entity per exact version',"Object.values(__mig.xt().byId).filter(n=>n.traj).length === 4");
    await check('unqueried conclusion version has no checked badge',"[...document.querySelectorAll('#canvas .node')].some(n=>n.textContent.startsWith('A.ets@v1') && n.textContent.includes('未查询') && !n.querySelector('.badge.step'))");
    await check('rejected visit overrides successful transport status',"[...document.querySelectorAll('#probe .st')].some(n=>n.textContent.startsWith('✗7') && n.textContent.includes('被拒 · 未打开'))");
    await check('structured summary excludes prose ring metrics',"!document.querySelector('#probe').textContent.includes('判定落到树上') && !document.querySelector('#probe').textContent.includes('报告的环') && document.querySelector('#probe').textContent.includes('结构化结论 2 项')");
    await check('revisits, partial deliveries, unqueried claims and rejected visits counted separately',"document.querySelector('.visit-summary').textContent==='成功版本访问 6 次 · 其中 1 次返回截断／非全文 · 未打开 1 次 · 去重已查版本节点 3 个 · 图中版本节点 4 个'");
    await check('unrelated navigation is neutral and explicitly noncausal',"[...document.querySelectorAll('.badge.navigation')].some(n=>n.textContent==='探索跳转：未核出直接账本边' && n.title.includes('不是因果边') && !n.classList.contains('stale')) && [...document.querySelectorAll('.wire.route title')].every(n=>n.textContent.includes('不是因果边'))");
    const point=await evaluate("(()=>{const r=document.querySelector('.route-step[data-step=\"4\"]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
    await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
    await check('transition step label responds to a real mouse click',"document.querySelector('#canvas .node.sel').textContent.startsWith('Agent A v1')");
    await evaluate(clickAgent);
    await check('all repeated visits and query windows preserved in drawer',"document.querySelectorAll('#side .pvisit').length===3 && document.querySelector('#side .pvisits').textContent.includes('start=2 n=4')");
    await check('partial return is still opened but never labelled as full delivery',"document.querySelectorAll('#side .delivery-truncated').length===1 && document.querySelector('#side .delivery-truncated').parentElement.textContent.includes('已打开') && document.querySelector('#side .pvisits').textContent.includes('不证明全文交付')");
    await evaluate("[...document.querySelectorAll('.dchips span')].find(n=>n.textContent.startsWith('A ')).click()");
    await check('A drawer isolated',"document.querySelector('#side').textContent.includes('A 独有原因') && !document.querySelector('#side').textContent.includes('B 独有原因')");
    await evaluate("[...document.querySelectorAll('.dchips span')].find(n=>n.textContent.startsWith('B ')).click()");
    await check('switch to B refreshes already-open drawer and evidence',"document.querySelector('#side').textContent.includes('B 独有原因') && !document.querySelector('#side').textContent.includes('A 独有原因') && document.querySelector('#side').textContent.includes('#a:2@L2') && !document.querySelector('#side').textContent.includes('#a:1@L1')");
    await evaluate("document.querySelector('#side .verow .more').click()");
    await until("document.querySelector('#side .verow').textContent.includes('EVIDENCE 2')");
    await check('node evidence opens correct action',"document.querySelector('#side .verow').textContent.includes('ACTION 2')");
    await evaluate("const stub=Object.values(__mig.xt().byId).find(n=>n.isLedgerStub);__mig.expandStub(stub.tid)");
    await check('exact missing writer version expanded',"Object.values(__mig.xt().byId).some(n=>n.aid==='agent-a' && n.anchorVer===2 && n.ledgerKid) && Object.values(__mig.xt().byId).filter(n=>n.aid==='agent-b').length===1");
    await check('expansion preserves all transitions',"document.querySelectorAll('.wire.route').length===5");
    await evaluate("__mig.setCand(true)");
    await check('candidate toggle preserves recorded route',"document.querySelectorAll('.wire.route').length===5");
    await evaluate("__mig.setCand(false)");
    await evaluate("[...document.querySelectorAll('.dchips span')].find(n=>n.textContent==='全部').click(); [...document.querySelectorAll('#probe .pn')].find(n=>n.textContent.includes('A.ets@v1')).click()");
    await check('clicking conclusion keeps route and exposes rejected visit honestly',"__mig.xt().walk===true && document.querySelectorAll('.wire.route').length===5 && document.querySelector('#side').textContent.includes('被拒 · 未打开')");
    await evaluate("document.querySelector('#side .rootbtn').click()");
    await until("__mig.xt().walk!==true && Object.values(__mig.xt().byId).some(n=>n.isRoot && n.anchorV===1)");
    await check('reroot does not claim queried v3 as queried v1',"!document.querySelector('#canvas .node.root .badge.step')");
    await evaluate("__mig.setCand(true)");
    await check('lexical candidate stays explicit in ledger exploration',"Object.values(__mig.xt().byId).filter(n=>n.possible).length>0 && Object.values(__mig.xt().byId).filter(n=>n.possible).every(n=>!n.hidden)");
    await evaluate("__mig.setCand(false)");
    await check('lexical candidate hidden without hiding structural nodes',"Object.values(__mig.xt().byId).filter(n=>n.possible).every(n=>n.hidden) && document.querySelectorAll('#canvas .node').length>0");
    await evaluate("__mig.load('no-root')");
    await until("__mig.xt() && __mig.xt().conclusionOnly===true");
    await check('conclusion-only payload does not invent a queried root',"!Object.values(__mig.xt().byId).some(n=>n.isRoot) && document.querySelectorAll('.wire.route').length===0 && document.querySelector('#rootlbl').textContent.includes('未查询结论')");
    await evaluate("__mig.load('empty')");
    await until("__mig.xt()===null");
    await check('all rejected payload clears previous graph',"document.querySelectorAll('#canvas .node').length===0 && document.querySelector('#rootlbl').textContent.includes('没有已核验')");
    await evaluate("__mig.load('metrics')");
    await until("document.querySelectorAll('#probe .st').length===118 && __mig.xt() && __mig.xt().walk");
    await check('118 native records split into 77 MCP queries and 41 wrappers',"document.querySelector('.call-summary').dataset.mcp==='77' && document.querySelector('.call-summary').dataset.wrapper==='41' && document.querySelector('.call-summary').dataset.other==='0' && document.querySelectorAll('.st[data-call-kind=\"mcp\"]').length===77 && document.querySelectorAll('.st[data-call-kind=\"wrapper\"]').length===41");
    await check('wrappers retain source, IDs and physical lines without becoming visits',"document.querySelector('.st[data-call-kind=\"wrapper\"] .t').title.includes('codex_rollout') && document.querySelector('.st[data-call-kind=\"wrapper\"] .t').title.includes('host-0') && document.querySelector('.st[data-call-kind=\"wrapper\"] .t').title.includes('100 → 101') && __mig.probe().trajectory.visits.length===7 && document.querySelectorAll('.wire.route').length===5");
    await evaluate("__mig.load('other-calls')");
    await until("document.querySelector('.call-summary').dataset.other==='1'");
    await check('unrecognized host calls are not counted as MCP or wrapper',"document.querySelector('.call-summary').dataset.mcp==='7' && document.querySelector('.call-summary').dataset.wrapper==='0' && document.querySelectorAll('.st[data-call-kind=\"other\"]').length===1");
    await evaluate("__mig.load('legacy')");
    await until("__mig.probe().legacy===true");
    await check('legacy prose ring display remains readable',"document.querySelector('#probe').textContent.includes('报告的环') && document.querySelector('.visit-summary').textContent.includes('0 环')");
    await evaluate("__mig.load('navigation')");
    await until("document.querySelectorAll('.wire.route').length===8");
    await check('same file versions labeled as navigation without inventing a relation',"__mig.xt().transitions.find(t=>t.step===8).navigation==='同文件版本导航' && __mig.xt().transitions.find(t=>t.step===8).relation===null && document.querySelector('.wire.route[data-step=\"8\"] title').textContent.includes('同文件版本导航')");
    await check('same agent versions labeled as navigation without inventing a relation',"__mig.xt().transitions.find(t=>t.step===9).navigation==='同agent版本导航' && __mig.xt().transitions.find(t=>t.step===9).relation===null && [...document.querySelectorAll('.badge.navigation')].some(n=>n.textContent==='同agent版本导航')");
    await check('identical basenames at different full paths remain exploratory jumps',"__mig.xt().transitions.find(t=>t.step===10).navigation==='探索跳转：未核出直接账本边' && [...document.querySelectorAll('#canvas .node')].some(n=>n.title.startsWith('/else/A.ets'))");
    await evaluate("[...document.querySelectorAll('#canvas .node')].find(n=>n.textContent.startsWith('A.ets@v2')).click()");
    await check('file drawer uses neutral navigation badge and a noncausal note',"document.querySelector('#side .pill.navigation').textContent==='同文件版本导航' && !document.querySelector('#side .pill.navigation').classList.contains('warn') && document.querySelector('#side').textContent.includes('查询导航,不是因果边')");
    await evaluate("__mig.load('relations')");
    await until("document.querySelectorAll('.wire.route').length===6");
    await check('uncertain relation has distinct text, amber dotted stroke and original note',"(()=>{const p=document.querySelector('.wire.route[data-step=\"2\"]');return p.dataset.relationStatus==='unknown' && getComputedStyle(p).stroke==='rgb(155, 116, 29)' && getComputedStyle(p).strokeDasharray==='2px, 4px' && p.querySelector('title').textContent.includes('条件读取待核') && document.querySelector('.route-step[data-step=\"2\"]').textContent.includes('候选') && document.querySelector('.badge.relation-candidate').textContent.includes('条件读取待核')})()");
    await check('verified relation keeps blue with explicit ledger text',"(()=>{const p=document.querySelector('.wire.route[data-step=\"3\"]');return p.dataset.relationStatus==='true' && getComputedStyle(p).stroke==='rgb(43, 108, 176)' && document.querySelector('.route-step[data-step=\"3\"]').textContent.includes('账本')})()");
    await check('two red endpoints never turn an exploratory route into a red causal edge',"(()=>{const p=document.querySelector('.wire.route[data-step=\"6\"]');return document.querySelectorAll('#canvas .node.p-chain').length>=2 && !p.classList.contains('chain') && getComputedStyle(p).stroke==='rgb(102, 120, 143)' && getComputedStyle(p).strokeDasharray==='5px, 3px'})()");
    await check('search event is visible without a third atom or fake parent read',"document.querySelector('.wire.route[data-step=\"9\"]').dataset.source==='search' && document.querySelector('.route-step[data-step=\"9\"]').textContent.includes('搜索 #8 → #9') && __mig.xt().transitions.find(t=>t.step===9).a===null && Object.values(__mig.xt().byId).filter(n=>n.traj).every(n=>['file','agent'].includes(n.kind))");
    await evaluate(clickAgent);
    await check('candidate drawer keeps original relation evidence',"document.querySelector('#side .relation-evidence').textContent.includes('/fixture/original.jsonl') && document.querySelector('#side .relation-evidence').textContent.includes('conditional_read')");
    await evaluate("[...document.querySelectorAll('#canvas .node')].find(n=>n.textContent.startsWith('A.ets@v1')).click()");
    await check('search navigation drawer retains actual call and forwarding boundary',"document.querySelector('#side .search-source').textContent.includes('toolu_search_8') && document.querySelector('#side .search-source').textContent.includes('不证明外层')");
    await evaluate(clickAgent+";document.querySelector('#side .rootbtn').click()");
    await until("__mig.xt().walk!==true && document.querySelectorAll('.wire.relation-uncertain').length===1");
    await check('manual ledger browsing preserves uncertain read flags without treating them as definite edges',"(()=>{const p=document.querySelector('.wire.relation-uncertain');return !p.classList.contains('chain') && getComputedStyle(p).stroke==='rgb(155, 116, 29)' && document.querySelector('#canvas').textContent.includes('读取窗口重叠') && Object.values(__mig.xt().byId).find(n=>n.kind==='file'&&n.anchorV===1).relationUncertain===false})()");
    await evaluate("__mig.setCand(false)");
    await check('uncertain recorded reads are not hidden by the lexical candidate toggle',"Object.values(__mig.xt().byId).filter(n=>n.relationUncertain).every(n=>!n.possible&&!n.hidden) && document.querySelectorAll('.wire.relation-uncertain').length===1");
    await evaluate("__mig.load('coverage')");
    await until("__mig.xt() && __mig.xt().walk && document.querySelectorAll('.wire.route').length===5");
    await check('coverage distinguishes accounted items, missing versions and unconfirmed candidates',"document.querySelector('.coverage-summary').textContent==='已交代 3/5 项 · 尚未有效交代 2 项' && document.querySelector('.repair-coverage').textContent.includes('记录版本 3 个 · 未确认候选 2 个（候选不等于修复）') && document.querySelector('.repair-coverage').textContent.includes('尚未登记：记录版本 1 个、候选 1 个')");
    await check('historical denominator remains visible after candidate policy changes',"document.querySelector('.repair-coverage').textContent.includes('按运行时保存的清单对账') && document.querySelector('.repair-coverage').textContent.includes('未改写历史分母')");
    await check('registered unknown and not-repair declarations are not presented as verified conclusions',"[...document.querySelectorAll('.coverage-item')].some(n=>n.dataset.state==='unresolved' && n.textContent.includes('已登记 · 仍未知（未查清）')) && [...document.querySelectorAll('.coverage-item')].some(n=>n.dataset.state==='not_repair' && n.textContent.includes('声明非修复（未验证）')) && document.querySelector('.repair-coverage').textContent.includes('解释与证据语义未核验')");
    await evaluate("window.coverageTreeIds=JSON.stringify(Object.keys(__mig.xt().byId));[...document.querySelectorAll('.coverage-item')].find(n=>n.dataset.target.endsWith('@v2')).querySelector('.coverage-file').click()");
    await until("document.querySelector('#side .vrow.anchor .vn')?.textContent==='v2'");
    await check('missing version opens actual ledger drawer without adding a queried node or changing route',"JSON.stringify(Object.keys(__mig.xt().byId))===window.coverageTreeIds && __mig.xt().walk && document.querySelectorAll('.wire.route').length===5 && document.querySelector('#side').textContent.includes('清单定位 · 不计入模型查询') && !Object.values(__mig.xt().byId).some(n=>n.kind==='file' && n.anchorV===2)");
    await evaluate("[...document.querySelectorAll('.dchips span')].find(n=>n.textContent.startsWith('B ')).click()");
    await check('defect switch retains the missing-version drawer and whole-manifest coverage',"document.querySelector('#side .vrow.anchor .vn').textContent==='v2' && document.querySelectorAll('.coverage-item').length===5 && document.querySelector('.coverage-summary').dataset.accounted==='3'");
    const candidatePoint=await evaluate("(()=>{const b=[...document.querySelectorAll('.coverage-item')].find(n=>n.dataset.target==='"+candidateTwo+"').querySelector('.coverage-action');b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
    await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...candidatePoint});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...candidatePoint});
    await until("[...document.querySelectorAll('.coverage-item')].find(n=>n.dataset.target==='"+candidateTwo+"').textContent.includes('EVIDENCE 202')");
    await check('candidate action click opens original evidence without new versions or problem coloring',"JSON.stringify(Object.keys(__mig.xt().byId))===window.coverageTreeIds && document.querySelectorAll('.wire.route').length===5 && !document.querySelector('.coverage-item .r-err') && !document.querySelector('.coverage-item .r-carry')");
    await evaluate("document.querySelector('#zf').click()");
    await check('fit still displays the entire recorded tree after coverage navigation',"(()=>{const g=document.querySelector('#graph').getBoundingClientRect(),t=document.querySelector('.toolbar').getBoundingClientRect();return [...document.querySelectorAll('#canvas .node')].every(n=>{const r=n.getBoundingClientRect();return r.left>=g.left-1 && r.right<=g.right+1 && r.top>=t.bottom-1 && r.bottom<=g.bottom+1})})()");
    await evaluate("__mig.load('coverage-invalid')");
    await until("document.querySelector('.coverage-summary').dataset.status==='invalid'");
    await check('duplicate declarations do not inflate accounted count or disappear as missing-zero',"document.querySelector('.coverage-summary').textContent==='已交代 2/5 项 · 尚未有效交代 3 项' && [...document.querySelectorAll('.coverage-item')].some(n=>n.dataset.state==='invalid' && n.textContent.includes('重复声明不可自动选优'))");
    await evaluate("__mig.load('coverage-complete')");
    await until("document.querySelector('.coverage-summary').dataset.status==='complete'");
    await check('complete means all items accounted for, not all candidates or defects resolved',"document.querySelector('.coverage-summary').textContent.includes('已交代 5/5 项') && document.querySelector('.repair-coverage').textContent.includes('清单交代齐全，不代表调查完整或全部修复已确认') && document.querySelectorAll('.coverage-item[data-state=\"unresolved\"]').length===2");
    await evaluate("__mig.load('coverage-unprovided')");
    await until("document.querySelector('.coverage-summary').dataset.status==='unprovided'");
    await check('missing coverage remains explicitly unprovided rather than inferred from defect count',"document.querySelector('.coverage-summary').textContent.includes('已交代 0/5 项') && document.querySelectorAll('.coverage-item[data-state=\"missing\"]').length===5 && document.querySelector('.repair-coverage').textContent.includes('不从散文或其他引用推测覆盖')");
    await evaluate("__mig.load('coverage-absent-version')");
    await until("document.querySelector('.coverage-item[data-target=\"file:/fixture/A.ets@v99\"]')!==null");
    await evaluate("document.querySelector('.coverage-item[data-target=\"file:/fixture/A.ets@v99\"] .coverage-file').click()");
    await until("document.querySelector('.repair-coverage').textContent.includes('当前原子未提供该版本')");
    await check('invalid version cannot create a phantom drawer or graph node',"!Object.values(__mig.xt().byId).some(n=>n.anchorV===99) && !document.querySelector('#side .tag').textContent.includes('@v99')");
    await evaluate("__mig.load('trace-mismatch')");
    await until("document.querySelector('.trace-identity').dataset.status==='mismatch' && __mig.xt()===null");
    await check('explicit trace conflict blocks stale bound graph, roles, step links and coverage links',"document.querySelector('#rootlbl').textContent.includes('当前账本不匹配') && document.querySelectorAll('#canvas .node').length===0 && document.querySelectorAll('#probe .st').length===7 && [...document.querySelectorAll('#probe .st')].every(n=>n.classList.contains('na')) && !document.querySelector('#probe .pn.r-err') && !document.querySelector('.coverage-file') && !document.querySelector('.coverage-action') && document.querySelector('.coverage-summary').textContent.includes('未绑定，不计为当前覆盖')");
    await evaluate("__mig.load('trace-legacy')");
    await until("document.querySelector('.trace-identity').dataset.status==='legacy' && __mig.xt() && __mig.xt().walk");
    await check('legacy identity is explicitly unrecorded without falsely marking verification',"document.querySelector('.trace-identity').textContent.includes('调查身份未记录 · 历史查询未认证') && document.querySelector('.trace-identity').dataset.status!=='matched' && document.querySelectorAll('.wire.route').length===5");
    await evaluate("__mig.load('coverage-compat')");
    await until("document.querySelector('.structured-compat')!==null");
    await check('revalidated historical notes show compatibility warning and preserve text safely',"document.querySelector('.structured-compat').textContent.includes('不是模型重跑') && document.querySelector('.structured-compat').textContent.includes('旧诊断：notes 必须是字符串') && document.querySelector('.structured-notes').textContent.includes('保留备注甲') && document.querySelector('.structured-notes').textContent.includes('<b>备注乙不是HTML</b>') && !document.querySelector('.structured-notes b')");
    await evaluate(clickAgent);
    await evaluate("new Promise(resolve=>setTimeout(resolve,200))");
    await evaluate("(()=>{const p=document.querySelector('#probe'),c=document.querySelector('.repair-coverage');p.scrollTop+=c.getBoundingClientRect().top-p.getBoundingClientRect().top})()");
    await check('coverage summary is visibly reachable inside the scrollable panel',"(()=>{const p=document.querySelector('#probe').getBoundingClientRect(),s=document.querySelector('.coverage-summary').getBoundingClientRect();return s.top>=p.top && s.bottom<=p.bottom})()");
    await evaluate("__mig.load('coverage-advisories')");
    await until("document.querySelector('.coverage-advisory-summary')!==null && document.querySelector('.coverage-summary').dataset.status==='complete'");
    await check('out-of-scope remains in the denominator and separate from not-repair',"document.querySelector('.coverage-summary').dataset.accounted==='5' && document.querySelectorAll('.coverage-item').length===5 && document.querySelectorAll('.coverage-item[data-state=\"out_of_scope\"]').length===2 && [...document.querySelectorAll('.coverage-item[data-state=\"out_of_scope\"]')].every(n=>n.textContent.includes('本题未调查（保留分母，不判非修复）')) && document.querySelector('.coverage-state-counts').dataset.deferred==='2' && document.querySelector('.coverage-state-counts').dataset.unconfirmed==='3'");
    await check('coverage amber advisory preserves original status and complete',"document.querySelector('.coverage-summary').dataset.status==='complete' && document.querySelector('.coverage-row-advisory').closest('.coverage-item').dataset.state==='not_repair' && document.querySelector('.coverage-advisory-summary').dataset.rows==='1' && getComputedStyle(document.querySelector('.coverage-advisory-summary')).color==='rgb(136, 101, 26)' && document.querySelector('.coverage-row-advisory').textContent.includes('#a:101@L1') && !document.querySelector('.coverage-row-advisory b')");
    await evaluate("__mig.load('fixture')");
    await until("__mig.probe().runDir==='fixture' && document.querySelectorAll('.wire.route').length===5");
    await evaluate("window.beforeConsistencyColors=[...document.querySelectorAll('#canvas .node')].map(n=>n.className).join('|');window.beforeConsistencyVisits=JSON.stringify(__mig.probe().trajectory.visits)");
    await evaluate("__mig.load('consistency')");
    await until("document.querySelector('.consistency-locate')!==null");
    await check('consistency warnings are not schema failure and never recolor nodes',"document.querySelector('.consistency-advisories').textContent.includes('声明自洽检查，不判断原因真假') && !document.querySelector('#probe .bad') && !document.querySelector('.consistency-advisory b') && [...document.querySelectorAll('#canvas .node')].map(n=>n.className).join('|')===window.beforeConsistencyColors && JSON.stringify(__mig.probe().trajectory.visits)===window.beforeConsistencyVisits");
    await evaluate("document.querySelector('.consistency-advisory').open=true;document.querySelector('.consistency-locate').click()");
    await check('consistency warning locates only an existing node and preserves raw warning',"document.querySelector('#canvas .node.sel').textContent.startsWith('Agent A v1') && document.querySelector('.consistency-raw').textContent.includes('entry_role_conflict') && Object.values(__mig.xt().byId).filter(n=>n.traj).length===4 && document.querySelectorAll('.wire.route').length===5");
    await evaluate("[...document.querySelectorAll('.dchips span')].find(n=>n.textContent.startsWith('B ')).click()");
    await check('consistency warning follows its own defect filter',"!document.querySelector('.consistency-advisory')");
    await evaluate("__mig.load('consistency-unbound')");
    await until("document.querySelector('.consistency-advisories')!==null && __mig.probe().structured.consistency.checked===false");
    await check('unbound consistency warnings retain text without current-node actions',"document.querySelector('.consistency-advisories').textContent.includes('仅保留历史提示') && !document.querySelector('.consistency-locate') && !document.querySelector('#probe .bad') && !document.querySelector('#canvas .node.p-chain')");
    await send('Page.navigate',{url:origin+'/?probe=time-scope'});
    await until("__mig.xt() && __mig.xt().walk && document.querySelector('#side .time-scope-summary')!==null");
    await check('file drawer time scope uses its requested version and labels pool limits',"document.querySelector('#side .time-scope').dataset.requestedVersion==='3' && document.querySelector('#side .time-scope').dataset.anchor==='2026-01-01T00:00:03.000000Z' && document.querySelector('#side .time-scope-summary').textContent.includes('2026-01-03') && document.querySelector('#side .time-scope-after').textContent.includes('其他会话：1 个')");
    await evaluate("window.beforeScopeGraph=JSON.stringify(Object.keys(__mig.xt().byId));window.beforeScopeVisits=JSON.stringify(__mig.probe().trajectory.visits);window.beforeScopeRequests=performance.getEntriesByType('resource').filter(r=>r.name.includes('scope_only=1')).length;document.querySelector('#side .time-scope-roots').open=true");
    await check('time scope expansion is metadata only with honest missing-root and returned-result labels',"document.querySelectorAll('#side .time-scope-root').length===3 && document.querySelector('#side .time-scope').textContent.includes('__main__:later') && document.querySelector('#side .time-scope').textContent.includes('未记录根 agent，不补造') && document.querySelector('#side .time-scope').textContent.includes('返回不代表成功') && !document.querySelector('#side .time-scope a,#side .time-scope button') && JSON.stringify(Object.keys(__mig.xt().byId))===window.beforeScopeGraph && JSON.stringify(__mig.probe().trajectory.visits)===window.beforeScopeVisits && performance.getEntriesByType('resource').filter(r=>r.name.includes('scope_only=1')).length===window.beforeScopeRequests");
    await evaluate("[...document.querySelectorAll('#canvas .node')].find(n=>n.textContent.startsWith('A.ets@v1')).click()");
    await until("document.querySelector('#side .time-scope')?.dataset.requestedVersion==='1'");
    await check('older file version never reuses latest-version time anchor',"document.querySelector('#side .time-scope').dataset.anchor==='2026-01-01T00:00:01.000000Z' && document.querySelectorAll('.wire.route').length===5");
    await evaluate(clickAgent);
    await until("document.querySelector('#side .time-scope')?.dataset.requestedVersion==='1' && document.querySelector('#side .tag').textContent.includes('Agent')");
    await check('agent drawer requests its own exact anchor without adding visits',"performance.getEntriesByType('resource').some(r=>r.name.includes('/atom/agent?scope_only=1')&&r.name.includes('v=1')) && document.querySelector('#side .time-scope').textContent.includes('后续活动不代表针对本文件的验证') && JSON.stringify(__mig.probe().trajectory.visits)===window.beforeScopeVisits");
    await send('Page.navigate',{url:origin+'/?probe=time-scope-failure'});
    await until("document.querySelector('#side .time-scope')?.textContent.includes('范围未加载')");
    await check('scope request failure does not imply absent later activity or alter graph',"document.querySelector('#side .time-scope').textContent.includes('fixture scope unavailable') && __mig.xt().walk && document.querySelectorAll('.wire.route').length===5 && !document.querySelector('#side .time-scope-summary')");
    await send('Page.navigate',{url:origin+'/?probe=tail-readers'});
    await until("__mig.xt()?.walk && document.querySelectorAll('.wire.route').length===5");
    await evaluate("[...document.querySelectorAll('#canvas .node')].find(n=>n.textContent.startsWith('A.ets@v1')).click()");
    await until("document.querySelector('#side .vrow.anchor .vn')?.textContent==='v1'");
    await check('tail reads keep evidence but never label feeding slots as agent versions',"document.querySelectorAll('.reader-row').length===7 && document.querySelectorAll('.reader-row[data-anchor-status=tail]').length===2 && document.querySelectorAll('.reader-row[data-anchor-status=unverified]').length===3 && document.querySelectorAll('.reader-version').length===2 && !document.querySelector('.reader-row[data-seq=\"307\"] .reader-version') && document.querySelector('#side').textContent.includes('收尾后读取（未形成v3）') && document.querySelector('#side').textContent.includes('收尾后读取（未形成v2）')");
    await evaluate("window.beforeTailTrace=JSON.stringify(__mig.probe().trajectory);window.beforeTailTree=JSON.stringify(Object.keys(__mig.xt().byId));document.querySelector('.reader-row[data-seq=\"302\"] .reader-action').click()");
    await until("document.querySelector('.reader-row[data-seq=\"302\"]').textContent.includes('EVIDENCE 302')");
    await check('tail original opens by actual action without fabricating a node or model visit',"JSON.stringify(__mig.probe().trajectory)===window.beforeTailTrace && JSON.stringify(Object.keys(__mig.xt().byId))===window.beforeTailTree && document.querySelectorAll('.wire.route').length===5 && !document.querySelector('.reader-row[data-seq=\"302\"] .reader-version') && performance.getEntriesByType('resource').some(r=>r.name.includes('/atom/action?id=agent-a&seq=302'))");
    await evaluate("document.querySelector('.reader-row[data-seq=\"305\"] .reader-action').click()");
    await until("document.querySelector('.reader-row[data-seq=\"305\"]').textContent.includes('EVIDENCE 305')");
    await check('legacy unknown owner remains raw-locatable but cannot navigate an invented version',"!document.querySelector('.reader-row[data-seq=\"305\"] .reader-version') && !performance.getEntriesByType('resource').some(r=>new URL(r.name).pathname==='/atom/agent'&&new URL(r.name).searchParams.get('id')==='agent-missing')");
    await evaluate("document.querySelector('#side .rootbtn').click()");
    await until("__mig.xt()?.walk!==true && Object.values(__mig.xt().byId).some(n=>n.isReader)");
    await check('non-query file expansion includes only actual reader effect versions',"(()=>{const ns=Object.values(__mig.xt().byId),rs=ns.filter(n=>n.isReader);return rs.length===2&&rs.every(n=>n.anchorVer===1)&&!ns.some(n=>n.kind==='agent'&&(n.aid==='agent-missing'||n.aid==='agent-absent'||n.anchorVer>({ 'agent-a':2,'agent-b':1 }[n.aid]||Infinity)))})()");
    await evaluate("document.querySelector('.reader-row[data-seq=\"301\"] .reader-version').click()");
    await until("__mig.xt()?.rootKind==='agent' && __mig.xt().byId[__mig.xt().root].anchorVer===1");
    await check('ordinary known reader keeps its exact agent navigation',"__mig.xt().byId[__mig.xt().root].aid==='agent-a' && !performance.getEntriesByType('resource').some(r=>{const u=new URL(r.name);return u.pathname==='/atom/agent'&&['3','8'].includes(u.searchParams.get('v'))})");
    const output=process.env.MIGLOOP_BROWSER_SCREENSHOT_DIR||path.join(repo,'docs/experiments/2026-09-09-trace-fidelity/screenshots');
    fs.mkdirSync(output,{recursive:true});
    const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    const screenshotPath=path.join(output,'02-repair-coverage-'+Date.now()+'.png');
    fs.writeFileSync(screenshotPath,Buffer.from(screenshot.data,'base64'));
    console.log('SCREENSHOT '+screenshotPath);
    assert.deepEqual(errors,[],'browser console exceptions');
    console.log('PASS no browser exceptions');
  }finally{
    await fetch(endpoint+'/json/close/'+target.id).catch(()=>{});socket.close();server.close();
  }
}
main().catch(e=>{console.error(e);server.close();process.exitCode=1;});
