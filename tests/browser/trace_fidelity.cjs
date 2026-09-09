/* Offline browser regression. Requires Node >= 22 and an existing local Chrome CDP endpoint.
 * node tests/browser/trace_fidelity.cjs [http://127.0.0.1:19652]
 * Serves only deterministic fixtures on an ephemeral loopback port; never calls a model.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {readLayoutGeometry} = require('./layout_geometry.cjs');

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
 evidence_graph:{schema:'migloop-evidence-graph/1',scope:'recorded_transitions',complete:false,status:'projected',identity_bound:true,
   nodes:nodes.map(n=>n.id),edges:[],model_relations:[],counts:{confirmed_read:0,confirmed_write:0,candidate_read:0,candidate_write:0},
   note:'仅投影已记录关系，不是全账本图或完整根因图。'},
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
agents[0].reads.forEach(r=>{r.proof={execution:'confirmed',delivery:r.dep?'dependency':'content',operation_basis:'fixture_native_read',snapshot:'reported',rule:'fixture'};});
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
    if(run.startsWith('source-')){
      const kind=run.slice(7), verified=['final_inline','checked_draft_ref'].includes(kind);
      body.structured.document_source={kind,verified,semantic_checked:false,raw_matches_data:kind==='invalid_saved'?false:true,
        final_matches_document:kind==='final_inline'?true:kind==='legacy_saved'?false:null,note:'SOURCE_NOTE <img src=x onerror="window.sourceXss=1">'};
      if(kind==='invalid_saved'){body.structured.identity.bound=false;body.structured.errors=['保存稿 raw 与 data 不一致'];body.roles={};}
    }
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
    if(run==='draft-check') body.steps.push({i:8,tool:'check',ok:true,args:{draft:'schema: migloop-verdict/1'},node:null,
      provenance:{format:'codex_rollout',path:'transcript.jsonl',pairing:'call_id'},call_id:'draft-check-8'});
    if(run.startsWith('draft-state-')){
      const status=run.slice('draft-state-'.length), empty=status==='not_checked';
      body.draft_check={status,semantic_checked:false,final_document_sha256:'final-hash',
        checks:empty?[]:[{step:8,call_id:'<img src=x onerror="window.draftXss=1">',status:'needs_review',counts:{errors:12,warnings:4,total:16},
          draft_sha256:'draft-hash',document_sha256:'document-hash',verified:status==='matched',
          issues:status==='unverifiable'?undefined:Array.from({length:12},(_,i)=>({code:'issue_'+i,severity:'error',
            message:i===0?'<img src=x onerror="window.issueXss=1">':i===11?'LAST_RETURNED_ISSUE':'diagnostic '+i,
            extra:{location:'nodes['+i+']'}})),
          omitted_issues:status==='unverifiable'?undefined:4,
          coverage:status==='unverifiable'?undefined:{checked:true,target:file,counts:{expected:7,unresolved:2},accounted:true,semantic_checked:false}}],
        matched_check:status==='matched'?8:null,check_calls:empty?0:1,draft_chars:200,returned_chars:80};
    }
    if(run.startsWith('with-basis')){
      const basis=(tag)=>({expected:tag+' EXPECTED <img src=x onerror="window.basisXss=1">',
        actual:tag+' ACTUAL\noutput statement',counterevidence:tag+' COUNTER <b>not HTML</b>',
        expected_evidence:[{type:'action',ref:'#a:41@L41',original_ref:'  #a:41@L41  ',status:'ok',aid:'agent-a',v:1,seq:41}],
        actual_evidence:[{type:'text',ref:'missing <script>window.basisXss=2</script>',status:'missing'},
          {type:'node',ref:'file:/fixture/A.ets@v1',status:'ok',node:{kind:'file',key:file,v:1,ok:true}}],
        source:'model',semantic_checked:false});
      for(let i=0;i<2;i++){
        const value=basis(i?'B':'A');
        if(run==='with-basis-tail-reference') value.expected_evidence.push(
          {type:'action',ref:'#a:43@L43',status:'ok',aid:'agent-a',v:3,seq:43},
          {type:'action',ref:'#missing:44@L44',status:'ok',aid:'agent-missing',v:8,seq:44});
        Object.assign(body.roles['agent-a'][i],{basis:value,basis_evidence_bad:1});
        Object.assign(body.structured.defects[i].nodes[0],{basis:structuredClone(value),basis_evidence_bad:1});
      }
      if(run==='with-basis-unbound') body.structured.identity={bound:false,match:false,status:'mismatch'};
    }
    if(run==='legacy'){body.structured=null;body.legacy=true;delete body.trace_identity;delete body.evidence_graph;}
    if(run.startsWith('findings')){
      const snapshot='document-sha:', first=claim(structuredClone(roles[0])), second=claim(roles[1]);
      first.evidence.push({type:'text',ref:'<img src=x onerror="window.findingXss=1">',original_ref:'  INVALID <img src=x onerror="window.findingXss=1">  ',status:'missing'});
      Object.assign(first,{basis_status:'complete',source:'model',semantic_checked:false});
      first.basis={expected:'EXPECTED',actual:'ACTUAL',counterevidence:'COUNTER',expected_evidence:[first.evidence[0]],actual_evidence:[first.evidence[1]],source:'model',semantic_checked:false};
      const invalid={...first,spec:'agent:agent-a@v99',v:99,ok:false,diag:'版本越界，原坐标保留',reason:'INVALID_REASON <script>window.findingXss=2</script>',basis_status:'invalid_legacy'};
      const item=(id,title,causes)=>({id:snapshot+id,defect:id,title,causes,source:'model',audit:{semantic_checked:false},
        boundary:'BOUNDARY <b>只是文本</b>',repair:{before:{kind:'file',key:file,v:1,spec:'file:'+file+'@v1',ok:true},after:{kind:'file',key:file,v:3,spec:'file:'+file+'@v3',ok:true}}});
      body.findings={schema:'migloop-findings/1',document_sha256:'document-sha',identity:{bound:true},errors:[],
        files:[{path:file,versions:[1,3],item_ids:[snapshot+'A',snapshot+'B'],associations:[
          {item_id:snapshot+'A',anchor:'before',node:'file:'+file+'@v1',source:'model',node_checked:true,repair_semantic_checked:false}]}],
        items:{[snapshot+'A']:item('A','文件事项甲 <b>非HTML</b>',[first,invalid]),[snapshot+'B']:item('B','文件事项乙',[second]),
          [snapshot+'C']:item('C','没有文件归属，不能借 root',[first])},unbound_items:[snapshot+'C'],audit:{semantic_checked:false,scope_complete:false}};
      if(run==='findings-unbound'){
        body.findings.identity.bound=false;body.findings.files=[];
        body.findings.unbound_items=Object.keys(body.findings.items);
      }
    }
    if(run.startsWith('consistency')){
      const advice={code:'entry_role_conflict',level:'warning',defect:'A',node:'agent:agent-a@v1',message:'声明间需核对 <b>不判原因真假</b>'};
      body.structured.consistency={checked:true,semantic_checked:false,advisories:[advice]};
      body.structured.defects[0].advisories=[advice];body.structured.defects[1].advisories=[];
      if(run==='consistency-unbound'){
        body.structured.identity={bound:false,status:'missing',match:null};body.structured.consistency.checked=false;
      }
    }
    if(run.startsWith('relations')){
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
      body.evidence_graph.edges=[
        {id:'rw-1',from:root,to:aid,kind:'read',status:'unknown',source_of_claim:'ledger',label:'候选·读',
         notes:['条件读取待核'],steps:[2],evidence:body.trajectory.transitions[0].relation_evidence},
        {id:'rw-2',from:bid,to:root,kind:'write',status:'true',source_of_claim:'ledger',label:'账本·写',
         notes:['写于 agent v1'],steps:[3],evidence:[{aid:'agent-b',seq:12,basis:'write',source:'/fixture/original.jsonl',use_line:6,result_line:7}]}];
      body.evidence_graph.counts={confirmed_read:0,confirmed_write:1,candidate_read:1,candidate_write:0};
      if(run==='relations-unbound'){body.evidence_graph.identity_bound=null;body.trace_identity.bound=null;}
      if(run==='relations-conflict')body.trace_identity.bound=false;
      if(run==='relations-missing-trace')delete body.trace_identity;
      if(run==='relations-claim-only'){
        body.evidence_graph.edges[0].source_of_claim='model';
        body.evidence_graph.edges[1].evidence=[];
      }
    }
    if(run==='forest-layout'){
      // Same structural cause as real C4: a search-entry ancestor is moved to a
      // separate column, while its ordinary descendant has an upstream stub.
      const b=body.trajectory.nodes.find(n=>n.id===bid);
      Object.assign(b,{side:'unlinked',search_source:{step:8,hit:1},opened:[9]});
      const leaf=body.trajectory.nodes.find(n=>n.id===fid+'@1');
      Object.assign(leaf,{source:'查过',search_source:{step:10,hit:1},opened:[11]});
      const child={id:'agent:agent-a@2',kind:'agent',key:'agent-a',v:2,label:'Agent A v2',parent:bid,side:'up',source:'查过',opened:[12],unseen:2,unseen_neighbors:[{kind:'file',key:file,v:2}]};
      const unrelated={id:fid+'@2',kind:'file',key:file,v:2,label:'A.ets@v2',parent:root,side:'unlinked',source:'查过',search_source:{step:13,hit:1},opened:[14],unseen:0};
      body.trajectory.nodes.push(child,unrelated);
      for(const [step,from,to,source] of [[9,null,bid,'search'],[11,null,leaf.id,'search'],[12,bid,child.id,'declared'],[14,null,unrelated.id,'search']]){
        const n=body.trajectory.nodes.find(n=>n.id===to),search_source=n.search_source;
        body.trajectory.transitions.push({step,from,to,source,search_source,relation_status:'not_checked'});
        body.trajectory.visits.push({step,tool:n.kind,node:to,requested_node:to,status:'opened',verified:true,search_source});
      }
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
  else if(url.pathname==='/atom/agent'){
    body=structuredClone(agents.find(a=>a.id==='agent-'+url.searchParams.get('id'))||agents[0]);
    if(activeFixture==='read-proof'){
      body.reads=[{path:file,v:1,at:1,certain:true,dep:false,self_written:true,proof:{execution:'unknown',delivery:'metadata',rule:'unsupported'}},
        {path:file,v:2,at:1,certain:true,dep:false}];
    }
  }
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
    await until("window.__mig && __mig.xt() && __mig.xt().walk && document.querySelectorAll('.wire.route').length === 0");
    await check('all transitions including revisit, multi-parent and self-loop remain only in the timeline',"JSON.stringify(__mig.probe().trajectory.transitions.map(n=>n.step))==='[2,3,4,5,6]' && JSON.stringify([...document.querySelectorAll('.navigation-event')].map(n=>Number(n.dataset.step)))==='[2,3,4,5,6]' && document.querySelectorAll('.wire').length===0");
    await evaluate("window.originalTrajectory=JSON.stringify(__mig.probe().trajectory)");
    await check('one entity per exact version',"Object.values(__mig.xt().byId).filter(n=>n.traj).length === 4");
    await check('unqueried conclusion version has no checked badge',"[...document.querySelectorAll('#canvas .node')].some(n=>n.textContent.startsWith('A.ets@v1') && n.textContent.includes('未查询') && !n.querySelector('.badge.step'))");
    await check('rejected visit overrides successful transport status',"[...document.querySelectorAll('#probe .st')].some(n=>n.textContent.startsWith('✗7') && n.textContent.includes('被拒 · 未打开'))");
    await check('structured summary excludes prose ring metrics',"!document.querySelector('#probe').textContent.includes('判定落到树上') && !document.querySelector('#probe').textContent.includes('报告的环') && document.querySelector('#probe').textContent.includes('结构化结论 2 项')");
    await check('revisits, partial deliveries, unqueried claims and rejected visits counted separately',"document.querySelector('.visit-summary').textContent==='成功版本访问 6 次 · 其中 1 次返回截断／非全文 · 未打开 1 次 · 去重已查版本节点 3 个 · 图中版本节点 4 个'");
    await check('unrelated navigation is neutral and explicitly noncausal',"[...document.querySelectorAll('.badge.navigation')].some(n=>n.textContent==='探索跳转：未核出直接账本边' && n.title.includes('不是因果边') && !n.classList.contains('stale')) && [...document.querySelectorAll('.wire.route title')].every(n=>n.textContent.includes('不是因果边'))");
    const point=await evaluate("(()=>{document.querySelector('.navigation-timeline').open=true;const n=document.querySelector('.navigation-event[data-step=\"4\"]');n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
    await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
    await check('timeline transition responds to a real mouse click without inventing an edge',"document.querySelector('#canvas .node.sel').textContent.startsWith('Agent A v1') && document.querySelectorAll('.wire.route').length===0");
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
    await check('expansion preserves all transitions and does not promote layout parents',"document.querySelectorAll('.wire').length===0 && JSON.stringify(__mig.probe().trajectory)===window.originalTrajectory");
    await evaluate("__mig.setCand(true)");
    await check('candidate toggle preserves recorded route',"document.querySelectorAll('.wire.route').length===0 && JSON.stringify(__mig.probe().trajectory)===window.originalTrajectory");
    await evaluate("__mig.setCand(false)");
    await evaluate("[...document.querySelectorAll('.dchips span')].find(n=>n.textContent==='全部').click(); [...document.querySelectorAll('#probe .pn')].find(n=>n.textContent.includes('A.ets@v1')).click()");
    await check('clicking conclusion keeps route and exposes rejected visit honestly',"__mig.xt().walk===true && document.querySelectorAll('.wire.route').length===0 && document.querySelector('#side').textContent.includes('被拒 · 未打开')");
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
    await check('wrappers retain source, IDs and physical lines without becoming visits',"document.querySelector('.st[data-call-kind=\"wrapper\"] .t').title.includes('codex_rollout') && document.querySelector('.st[data-call-kind=\"wrapper\"] .t').title.includes('host-0') && document.querySelector('.st[data-call-kind=\"wrapper\"] .t').title.includes('100 → 101') && __mig.probe().trajectory.visits.length===7 && document.querySelectorAll('.wire.route').length===0");
    await evaluate("__mig.load('other-calls')");
    await until("document.querySelector('.call-summary').dataset.other==='1'");
    await check('unrecognized host calls are not counted as MCP or wrapper',"document.querySelector('.call-summary').dataset.mcp==='7' && document.querySelector('.call-summary').dataset.wrapper==='0' && document.querySelectorAll('.st[data-call-kind=\"other\"]').length===1");
    await evaluate("__mig.load('legacy')");
    await until("__mig.probe().legacy===true");
    await check('legacy prose ring display remains readable',"document.querySelector('#probe').textContent.includes('报告的环') && document.querySelector('.visit-summary').textContent.includes('0 环')");
    await evaluate("__mig.load('navigation')");
    await until("__mig.xt().transitions.length===8");
    await check('same file versions labeled as navigation without inventing a relation',"__mig.xt().transitions.find(t=>t.step===8).navigation==='同文件版本导航' && __mig.xt().transitions.find(t=>t.step===8).relation===null && document.querySelector('.navigation-event[data-step=\"8\"]').textContent.includes('同文件版本导航') && document.querySelectorAll('.wire').length===0");
    await check('same agent versions labeled as navigation without inventing a relation',"__mig.xt().transitions.find(t=>t.step===9).navigation==='同agent版本导航' && __mig.xt().transitions.find(t=>t.step===9).relation===null && [...document.querySelectorAll('.badge.navigation')].some(n=>n.textContent==='同agent版本导航')");
    await check('identical basenames at different full paths remain exploratory jumps',"__mig.xt().transitions.find(t=>t.step===10).navigation==='探索跳转：未核出直接账本边' && [...document.querySelectorAll('#canvas .node')].some(n=>n.title.startsWith('/else/A.ets'))");
    await evaluate("[...document.querySelectorAll('#canvas .node')].find(n=>n.textContent.startsWith('A.ets@v2')).click()");
    await check('file drawer uses neutral navigation badge and a noncausal note',"document.querySelector('#side .pill.navigation').textContent==='同文件版本导航' && !document.querySelector('#side .pill.navigation').classList.contains('warn') && document.querySelector('#side').textContent.includes('查询导航,不是因果边')");
    await evaluate("__mig.load('relations')");
    await until("document.querySelectorAll('.wire.evidence').length===2");
    await check('uncertain relation has distinct text, amber dotted stroke and original note',"(()=>{const p=document.querySelector('.wire.route[data-step=\"2\"]');return p.dataset.relationStatus==='unknown' && getComputedStyle(p).stroke==='rgb(155, 116, 29)' && getComputedStyle(p).strokeDasharray==='2px, 4px' && p.querySelector('title').textContent.includes('条件读取待核') && document.querySelector('.route-step[data-step=\"2\"]').textContent.includes('候选') && document.querySelector('.badge.relation-candidate').textContent.includes('条件读取待核')})()");
    await check('verified relation keeps blue with explicit ledger text',"(()=>{const p=document.querySelector('.wire.route[data-step=\"3\"]');return p.dataset.relationStatus==='true' && getComputedStyle(p).stroke==='rgb(43, 108, 176)' && document.querySelector('.route-step[data-step=\"3\"]').textContent.includes('账本')})()");
    await check('two red endpoints never turn an exploratory route into a red causal edge',"document.querySelectorAll('#canvas .node.p-chain').length>=2 && !document.querySelector('.wire.route[data-step=\"6\"]') && document.querySelector('.navigation-event[data-step=\"6\"]')!==null");
    await check('search event is visible without a third atom or fake parent read',"!document.querySelector('.wire.route[data-step=\"9\"]') && document.querySelector('.navigation-event[data-step=\"9\"]').textContent.includes('搜索 #8') && __mig.xt().transitions.find(t=>t.step===9).a===null && Object.values(__mig.xt().byId).filter(n=>n.traj).every(n=>['file','agent'].includes(n.kind))");
    await check('write arrow uses causal direction opposite to query and keeps all query events',"(()=>{const p=document.querySelector('.wire.evidence[data-step=\"3\"]');return p.dataset.from==='agent:agent-b@1' && p.dataset.to==='file:/fixture/A.ets@3' && p.dataset.kind==='write' && __mig.probe().trajectory.transitions[1].from==='file:/fixture/A.ets@3' && document.querySelectorAll('.navigation-event').length===6})()");
    await check('evidence counts and incomplete scope remain separate from claims and navigation',"document.querySelector('.evidence-graph-summary').textContent.includes('确定读 0 / 写 1 · 候选读 1 / 写 0 · 导航转移 6') && document.querySelector('#probe').textContent.includes('不是全账本图或完整根因图') && __mig.probe().evidence_graph.complete===false");
    await evaluate("window.relationTrace=JSON.stringify(__mig.probe().trajectory);document.querySelector('.navigation-timeline').open=true;__mig.setCand(true)");
    await check('expanding timeline or lexical toggle does not alter projection or original trace',"document.querySelectorAll('.wire.evidence').length===2 && JSON.stringify(__mig.probe().trajectory)===window.relationTrace && document.querySelectorAll('.navigation-event').length===6");
    const writePoint=await evaluate("(()=>{const n=document.querySelector('.route-step[data-step=\"3\"]');const r=n.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
    await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...writePoint});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...writePoint});
    await check('write edge click opens semantic destination not original query target',"document.querySelector('#canvas .node.sel').textContent.startsWith('A.ets@v3')");
    await evaluate(clickAgent);
    await check('candidate drawer keeps original relation evidence',"document.querySelector('#side .relation-evidence').textContent.includes('/fixture/original.jsonl') && document.querySelector('#side .relation-evidence').textContent.includes('conditional_read')");
    await evaluate("[...document.querySelectorAll('#canvas .node')].find(n=>n.textContent.startsWith('A.ets@v1')).click()");
    await check('search navigation drawer retains actual call and forwarding boundary',"document.querySelector('#side .search-source').textContent.includes('toolu_search_8') && document.querySelector('#side .search-source').textContent.includes('不证明外层')");
    await evaluate(clickAgent+";document.querySelector('#side .rootbtn').click()");
    await until("__mig.xt().walk!==true && document.querySelectorAll('.wire.relation-uncertain').length===1");
    await check('manual ledger browsing preserves uncertain read flags without treating them as definite edges',"(()=>{const p=document.querySelector('.wire.relation-uncertain');return !p.classList.contains('chain') && getComputedStyle(p).stroke==='rgb(155, 116, 29)' && document.querySelector('#canvas').textContent.includes('读取窗口重叠') && Object.values(__mig.xt().byId).find(n=>n.kind==='file'&&n.anchorV===1).relationUncertain===false})()");
    await evaluate("__mig.setCand(false)");
    await check('uncertain recorded reads are not hidden by the lexical candidate toggle',"Object.values(__mig.xt().byId).filter(n=>n.relationUncertain).every(n=>!n.possible&&!n.hidden) && document.querySelectorAll('.wire.relation-uncertain').length===1");
    for(const run of ['relations-unbound','relations-missing-trace','relations-claim-only']){
      await evaluate('__mig.load('+JSON.stringify(run)+')');
      await until('__mig.probe().runDir==='+JSON.stringify(run)+' && __mig.xt()?.evidenceMode');
      await check(run+' cannot promote model/unlocated/unbound relationship lines',"document.querySelectorAll('.wire').length===0 && __mig.probe().trajectory.transitions.length===6 && document.querySelectorAll('.navigation-event').length===6");
    }
    await evaluate("__mig.load('relations-conflict')");
    await until("__mig.probe().runDir==='relations-conflict' && __mig.xt()===null");
    await check('explicit trace conflict overrides even a supplied bound evidence projection',"document.querySelectorAll('.wire').length===0 && document.querySelectorAll('#canvas .node').length===0 && __mig.probe().trajectory.transitions.length===6");
    await evaluate("__mig.load('coverage')");
    await until("__mig.xt() && __mig.xt().walk && document.querySelectorAll('.wire.route').length===0");
    await check('coverage distinguishes accounted items, missing versions and unconfirmed candidates',"document.querySelector('.coverage-summary').textContent==='已交代 3/5 项 · 尚未有效交代 2 项' && document.querySelector('.repair-coverage').textContent.includes('记录版本 3 个 · 未确认候选 2 个（候选不等于修复）') && document.querySelector('.repair-coverage').textContent.includes('尚未登记：记录版本 1 个、候选 1 个')");
    await check('historical denominator remains visible after candidate policy changes',"document.querySelector('.repair-coverage').textContent.includes('按运行时保存的清单对账') && document.querySelector('.repair-coverage').textContent.includes('未改写历史分母')");
    await check('registered unknown and not-repair declarations are not presented as verified conclusions',"[...document.querySelectorAll('.coverage-item')].some(n=>n.dataset.state==='unresolved' && n.textContent.includes('已登记 · 仍未知（未查清）')) && [...document.querySelectorAll('.coverage-item')].some(n=>n.dataset.state==='not_repair' && n.textContent.includes('声明非修复（未验证）')) && document.querySelector('.repair-coverage').textContent.includes('解释与证据语义未核验')");
    await evaluate("window.coverageTreeIds=JSON.stringify(Object.keys(__mig.xt().byId));[...document.querySelectorAll('.coverage-item')].find(n=>n.dataset.target.endsWith('@v2')).querySelector('.coverage-file').click()");
    await until("document.querySelector('#side .vrow.anchor .vn')?.textContent==='v2'");
    await check('missing version opens actual ledger drawer without adding a queried node or changing route',"JSON.stringify(Object.keys(__mig.xt().byId))===window.coverageTreeIds && __mig.xt().walk && document.querySelectorAll('.wire.route').length===0 && document.querySelector('#side').textContent.includes('清单定位 · 不计入模型查询') && !Object.values(__mig.xt().byId).some(n=>n.kind==='file' && n.anchorV===2)");
    await evaluate("[...document.querySelectorAll('.dchips span')].find(n=>n.textContent.startsWith('B ')).click()");
    await check('defect switch retains the missing-version drawer and whole-manifest coverage',"document.querySelector('#side .vrow.anchor .vn').textContent==='v2' && document.querySelectorAll('.coverage-item').length===5 && document.querySelector('.coverage-summary').dataset.accounted==='3'");
    const candidatePoint=await evaluate("(()=>{const b=[...document.querySelectorAll('.coverage-item')].find(n=>n.dataset.target==='"+candidateTwo+"').querySelector('.coverage-action');b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
    await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...candidatePoint});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...candidatePoint});
    await until("[...document.querySelectorAll('.coverage-item')].find(n=>n.dataset.target==='"+candidateTwo+"').textContent.includes('EVIDENCE 202')");
    await check('candidate action click opens original evidence without new versions or problem coloring',"JSON.stringify(Object.keys(__mig.xt().byId))===window.coverageTreeIds && document.querySelectorAll('.wire.route').length===0 && !document.querySelector('.coverage-item .r-err') && !document.querySelector('.coverage-item .r-carry')");
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
    await check('legacy identity is explicitly unrecorded without falsely marking verification',"document.querySelector('.trace-identity').textContent.includes('调查身份未记录 · 历史查询未认证') && document.querySelector('.trace-identity').dataset.status!=='matched' && document.querySelectorAll('.wire.route').length===0");
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
    await until("__mig.probe().runDir==='fixture' && document.querySelectorAll('.wire.route').length===0");
    await evaluate("window.beforeConsistencyColors=[...document.querySelectorAll('#canvas .node')].map(n=>n.className).join('|');window.beforeConsistencyVisits=JSON.stringify(__mig.probe().trajectory.visits)");
    await evaluate("__mig.load('consistency')");
    await until("document.querySelector('.consistency-locate')!==null");
    await check('consistency warnings are not schema failure and never recolor nodes',"document.querySelector('.consistency-advisories').textContent.includes('声明自洽检查，不判断原因真假') && !document.querySelector('#probe .bad') && !document.querySelector('.consistency-advisory b') && [...document.querySelectorAll('#canvas .node')].map(n=>n.className).join('|')===window.beforeConsistencyColors && JSON.stringify(__mig.probe().trajectory.visits)===window.beforeConsistencyVisits");
    await evaluate("document.querySelector('.consistency-advisory').open=true;document.querySelector('.consistency-locate').click()");
    await check('consistency warning locates only an existing node and preserves raw warning',"document.querySelector('#canvas .node.sel').textContent.startsWith('Agent A v1') && document.querySelector('.consistency-raw').textContent.includes('entry_role_conflict') && Object.values(__mig.xt().byId).filter(n=>n.traj).length===4 && document.querySelectorAll('.wire.route').length===0");
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
    await check('older file version never reuses latest-version time anchor',"document.querySelector('#side .time-scope').dataset.anchor==='2026-01-01T00:00:01.000000Z' && document.querySelectorAll('.wire.route').length===0");
    await evaluate(clickAgent);
    await until("document.querySelector('#side .time-scope')?.dataset.requestedVersion==='1' && document.querySelector('#side .tag').textContent.includes('Agent')");
    await check('agent drawer requests its own exact anchor without adding visits',"performance.getEntriesByType('resource').some(r=>r.name.includes('/atom/agent?scope_only=1')&&r.name.includes('v=1')) && document.querySelector('#side .time-scope').textContent.includes('后续活动不代表针对本文件的验证') && JSON.stringify(__mig.probe().trajectory.visits)===window.beforeScopeVisits");
    await send('Page.navigate',{url:origin+'/?probe=time-scope-failure'});
    await until("document.querySelector('#side .time-scope')?.textContent.includes('范围未加载')");
    await check('scope request failure does not imply absent later activity or alter graph',"document.querySelector('#side .time-scope').textContent.includes('fixture scope unavailable') && __mig.xt().walk && document.querySelectorAll('.wire.route').length===0 && !document.querySelector('#side .time-scope-summary')");
    await send('Page.navigate',{url:origin+'/?probe=tail-readers'});
    await until("__mig.xt()?.walk && document.querySelectorAll('.wire.route').length===0");
    await evaluate("[...document.querySelectorAll('#canvas .node')].find(n=>n.textContent.startsWith('A.ets@v1')).click()");
    await until("document.querySelector('#side .vrow.anchor .vn')?.textContent==='v1'");
    await check('tail reads keep evidence but never label feeding slots as agent versions',"document.querySelectorAll('.reader-row').length===7 && document.querySelectorAll('.reader-row[data-anchor-status=tail]').length===2 && document.querySelectorAll('.reader-row[data-anchor-status=unverified]').length===3 && document.querySelectorAll('.reader-version').length===2 && !document.querySelector('.reader-row[data-seq=\"307\"] .reader-version') && document.querySelector('#side').textContent.includes('收尾后读取（未形成v3）') && document.querySelector('#side').textContent.includes('收尾后读取（未形成v2）')");
    await evaluate("window.beforeTailTrace=JSON.stringify(__mig.probe().trajectory);window.beforeTailTree=JSON.stringify(Object.keys(__mig.xt().byId));document.querySelector('.reader-row[data-seq=\"302\"] .reader-action').click()");
    await until("document.querySelector('.reader-row[data-seq=\"302\"]').textContent.includes('EVIDENCE 302')");
    await check('tail original opens by actual action without fabricating a node or model visit',"JSON.stringify(__mig.probe().trajectory)===window.beforeTailTrace && JSON.stringify(Object.keys(__mig.xt().byId))===window.beforeTailTree && document.querySelectorAll('.wire.route').length===0 && !document.querySelector('.reader-row[data-seq=\"302\"] .reader-version') && performance.getEntriesByType('resource').some(r=>r.name.includes('/atom/action?id=agent-a&seq=302'))");
    await evaluate("document.querySelector('.reader-row[data-seq=\"305\"] .reader-action').click()");
    await until("document.querySelector('.reader-row[data-seq=\"305\"]').textContent.includes('EVIDENCE 305')");
    await check('legacy unknown owner remains raw-locatable but cannot navigate an invented version',"!document.querySelector('.reader-row[data-seq=\"305\"] .reader-version') && !performance.getEntriesByType('resource').some(r=>new URL(r.name).pathname==='/atom/agent'&&new URL(r.name).searchParams.get('id')==='agent-missing')");
    await evaluate("document.querySelector('#side .rootbtn').click()");
    await until("__mig.xt()?.walk!==true && Object.values(__mig.xt().byId).some(n=>n.isReader)");
    await check('non-query file expansion includes only actual reader effect versions',"(()=>{const ns=Object.values(__mig.xt().byId),rs=ns.filter(n=>n.isReader);return rs.length===2&&rs.every(n=>n.anchorVer===1)&&!ns.some(n=>n.kind==='agent'&&(n.aid==='agent-missing'||n.aid==='agent-absent'||n.anchorVer>({ 'agent-a':2,'agent-b':1 }[n.aid]||Infinity)))})()");
    await evaluate("document.querySelector('.reader-row[data-seq=\"301\"] .reader-version').click()");
    await until("__mig.xt()?.rootKind==='agent' && __mig.xt().byId[__mig.xt().root].anchorVer===1");
    await check('ordinary known reader keeps its exact agent navigation',"__mig.xt().byId[__mig.xt().root].aid==='agent-a' && !performance.getEntriesByType('resource').some(r=>{const u=new URL(r.name);return u.pathname==='/atom/agent'&&['3','8'].includes(u.searchParams.get('v'))})");
    await send('Page.navigate',{url:origin+'/?probe=fixture'});
    await until("__mig.xt()?.walk && document.querySelectorAll('.wire.route').length===0");
    await check('historical reports without basis do not acquire invented attribution fields',"!document.querySelector('.attribution-basis') && __mig.probe().structured.errors.length===0");
    await evaluate("window.beforeBasisColors=[...document.querySelectorAll('#canvas .node')].map(n=>n.className.replace(/ sel/g,'')).join('|');window.beforeBasisVisits=JSON.stringify(__mig.probe().trajectory.visits);__mig.load('with-basis')");
    await until("__mig.probe().runDir==='with-basis' && document.querySelector('#probe .attribution-basis')");
    await check('structured node attribution is collapsed and explicitly a model claim',"document.querySelectorAll('#probe .attribution-basis').length===2 && [...document.querySelectorAll('#probe .attribution-basis')].every(n=>!n.open&&n.dataset.source==='model'&&n.dataset.semanticChecked==='false'&&n.querySelector('summary').textContent==='归因对照（模型主张，未验证）')");
    await evaluate("window.beforeBasisDrawer=document.querySelector('#side .tag').textContent;document.querySelector('#probe .attribution-basis summary').click()");
    await check('expanding attribution neither navigates nor alters original node color or visits',"document.querySelector('#probe .attribution-basis').open && document.querySelector('#side .tag').textContent===window.beforeBasisDrawer && [...document.querySelectorAll('#canvas .node')].map(n=>n.className.replace(/ sel/g,'')).join('|')===window.beforeBasisColors && JSON.stringify(__mig.probe().trajectory.visits)===window.beforeBasisVisits");
    await check('basis fields and original references are escaped with separate bad-reference diagnostics',"document.querySelector('#probe .attribution-basis').textContent.includes('A EXPECTED <img') && document.querySelector('#probe .attribution-basis').textContent.includes('A COUNTER <b>not HTML</b>') && document.querySelector('#probe .basis-expected-evidence .mono').textContent==='  #a:41@L41  ' && document.querySelector('#probe .basis-evidence-note').textContent.includes('引用位置未核 1 条') && !document.querySelector('.attribution-basis img,.attribution-basis script,.attribution-basis b') && !window.basisXss");
    await evaluate("document.querySelector('#probe .basis-expected-evidence .more').click()");
    await until("document.querySelector('#probe .basis-expected-evidence').textContent.includes('EVIDENCE 41')");
    await check('expected evidence reuses the actual action loader without treating location as semantic support',"document.querySelector('#probe .attribution-basis').textContent.includes('位置可核不证明支持此归因') && document.querySelector('#probe .attribution-basis').textContent.includes('内容齐全不代表验证通过') && document.querySelector('#probe .basis-actual-evidence .verow.bad')!==null && JSON.stringify(__mig.probe().trajectory.visits)===window.beforeBasisVisits");
    await evaluate(clickAgent);
    await until("document.querySelector('#side .attribution-basis')!==null");
    await check('reason drawer exposes each defect own attribution basis without assigning verification',"document.querySelectorAll('#side .attribution-basis').length===2 && document.querySelector('#side .attribution-basis').textContent.includes('当时要求') && document.querySelector('#side .attribution-basis').textContent.includes('实际输出') && document.querySelector('#side .attribution-basis').textContent.includes('反证边界') && __mig.probe().roles['agent-a'].every(n=>n.checked==='not_checked')");
    await evaluate("[...document.querySelectorAll('.dchips span')].find(n=>n.textContent.startsWith('B ')).click()");
    await check('switching defects isolates both structured and drawer attribution',"document.querySelectorAll('#probe .attribution-basis').length===1 && document.querySelectorAll('#side .attribution-basis').length===1 && document.querySelector('#side .attribution-basis').textContent.includes('B EXPECTED') && !document.querySelector('#side .attribution-basis').textContent.includes('A EXPECTED') && !document.querySelector('#probe .attribution-basis').textContent.includes('A EXPECTED')");
    await evaluate("document.querySelector('#side .attribution-basis').open=true;document.querySelector('#side .basis-actual-evidence .lnk').click()");
    await check('actual node evidence keeps the existing exact-version navigation mechanism',"document.querySelector('#side .tag').textContent.includes('@v1') && document.querySelectorAll('.wire.route').length===0 && JSON.stringify(__mig.probe().trajectory.visits)===window.beforeBasisVisits");
    await evaluate("__mig.load('with-basis-unbound')");
    await until("__mig.probe().structured.identity.bound===false && document.querySelector('#probe .attribution-basis')");
    await check('unbound attribution retains text without source validation or action links',"document.querySelector('#probe .attribution-basis').textContent.includes('EXPECTED') && document.querySelector('#probe .attribution-basis').textContent.includes('历史引用未绑定') && !document.querySelector('.attribution-basis .lnk,.attribution-basis .more,.attribution-basis .verow.ok') && !document.querySelector('#canvas .node.p-chain')");
    await evaluate("__mig.load('draft-check')");
    await until("__mig.probe().runDir==='draft-check'");
    await check('draft check is a mechanical MCP event rather than an opened atom or edge',"document.querySelector('.call-summary').dataset.mcp==='8' && [...document.querySelectorAll('#probe .st')].some(n=>n.dataset.callKind==='mcp'&&n.classList.contains('na')&&n.textContent.includes('草稿机械核查事件')) && __mig.probe().trajectory.nodes.length===4 && __mig.probe().trajectory.visits.length===7 && document.querySelectorAll('.wire.route').length===0 && !Object.values(__mig.probe().byKey).flat().some(s=>s.i===8)");
    await evaluate("window.beforeDraftGraph=JSON.stringify(__mig.probe().trajectory);window.beforeDraftColors=[...document.querySelectorAll('#canvas .node')].map(n=>n.className.replace(/ sel/g,'')).join('|')");
    const draftLabels={matched:'草稿机检与当前稿一致（语义未核验）',mismatch:'最终稿与最后核查稿不同',
      not_checked:'未核查',unverifiable:'草稿核查不可核',invalid_final:'最终稿无效，无法核对草稿机检'};
    for(const [status,label] of Object.entries(draftLabels)){
      await evaluate("__mig.load('draft-state-"+status+"')");
      await until("document.querySelector('.draft-check-summary')?.dataset.status==='"+status+"'");
      await check('draft status '+status+' is diagnostic only and does not repaint or alter the graph',
        "document.querySelector('.draft-check-summary').textContent.includes("+JSON.stringify(label)+") && document.querySelector('.draft-check-summary').dataset.semanticChecked==='false' && !document.querySelector('.draft-check-summary').textContent.includes('✓') && !document.querySelector('.draft-check-summary .r-ok,.draft-check-summary .r-err') && JSON.stringify(__mig.probe().trajectory)===window.beforeDraftGraph && [...document.querySelectorAll('#canvas .node')].map(n=>n.className.replace(/ sel/g,'')).join('|')===window.beforeDraftColors");
      if(status==='unverifiable') await check('missing returned diagnostics do not become an invented zero-issue result',
        "document.querySelector('.draft-check-issues').textContent.includes('未提供诊断明细') && document.querySelector('.draft-check-omitted').textContent.includes('省略数量未记录') && document.querySelectorAll('.draft-check-issue').length===0");
    }
    await evaluate("document.querySelector('.draft-check-details').open=true");
    await check('draft diagnostic keeps source proofs escaped without claiming model attention',"document.querySelector('.draft-check-summary').textContent.includes('不证明模型阅读或采纳了反馈') && document.querySelector('.draft-check-details').textContent.includes('final-hash') && document.querySelector('.draft-check-details').textContent.includes('<img src=x') && !document.querySelector('.draft-check-details img') && !window.draftXss");
    await check('all supplied issues and omitted count remain visible and escaped',"document.querySelectorAll('.draft-check-issue').length===12 && document.querySelector('.draft-check-issues').textContent.includes('LAST_RETURNED_ISSUE') && document.querySelector('.draft-check-issue').textContent.includes('<img src=x') && document.querySelector('.draft-check-issue').textContent.includes('nodes[0]') && document.querySelector('.draft-check-omitted').textContent.includes('另省略 4 条') && !document.querySelector('.draft-check-issues img') && !window.issueXss");
    await check('returned coverage diagnostics retain unresolved counts without proving repair truth',"document.querySelector('.draft-check-coverage').textContent.includes('\"unresolved\": 2') && document.querySelector('.draft-check-coverage').textContent.includes('\"accounted\": true') && document.querySelector('.draft-check-record').textContent.includes('覆盖齐全不代表修复已确认') && document.querySelector('.draft-check-summary').dataset.semanticChecked==='false' && JSON.stringify(__mig.probe().trajectory)===window.beforeDraftGraph");
    await evaluate("__mig.load('with-basis-tail-reference')");
    await until("__mig.probe().runDir==='with-basis-tail-reference' && document.querySelector('#probe .basis-expected-evidence')");
    await check('locatable action references do not certify tail slots or unknown-owner agent versions',"(()=>{const rs=[...document.querySelectorAll('#probe .basis-expected-evidence .verow')],tail=rs.find(r=>r.textContent.includes('#a:43@L43')),unknown=rs.find(r=>r.textContent.includes('#missing:44@L44')),valid=rs.find(r=>r.textContent.includes('#a:41@L41'));return tail.classList.contains('ok')&&unknown.classList.contains('ok')&&!tail.querySelector('.lnk')&&!unknown.querySelector('.lnk')&&!!tail.querySelector('.more')&&!!unknown.querySelector('.more')&&!!valid.querySelector('.lnk')&&tail.textContent.includes('喂养槽 3')})()");
    await evaluate("window.beforeTailEvidence=JSON.stringify(__mig.probe().trajectory);document.querySelector('#probe .attribution-basis').open=true;[...document.querySelectorAll('#probe .basis-expected-evidence .verow')].find(r=>r.textContent.includes('#a:43@L43')).querySelector('.more').click()");
    await until("[...document.querySelectorAll('#probe .basis-expected-evidence .verow')].some(r=>r.textContent.includes('EVIDENCE 43'))");
    await check('tail citation retains exact raw action navigation without inventing an agent version',"JSON.stringify(__mig.probe().trajectory)===window.beforeTailEvidence && !Object.values(__mig.xt().byId).some(n=>n.kind==='agent'&&n.anchorVer===3) && __mig.probe().structured.defects[0].nodes[0].basis.expected_evidence[1].v===3 && __mig.probe().structured.defects[0].nodes[0].basis.expected_evidence[1].status==='ok'");
    await evaluate("__mig.load('findings')");
    await until("__mig.probe().runDir==='findings' && document.querySelector('.file-findings')");
    await check('per-file findings default to compact counts and never certify model associations',"!document.querySelector('.file-findings').open && document.querySelector('.file-findings > summary').textContent.includes('1 个文件 / 3 项 / 未绑定 1 项（模型主张）') && document.querySelector('.file-findings').dataset.semanticChecked==='false' && document.querySelector('.file-findings').textContent.includes('文件归属/修复关联：模型声明；版本坐标已核，修复语义未核验')");
    await evaluate("window.findingTrace=JSON.stringify(__mig.probe().trajectory);window.findingGraph=JSON.stringify(__mig.probe().evidence_graph);window.findingNodeIds=JSON.stringify(Object.keys(__mig.xt().byId));document.querySelector('.file-findings').open=true;document.querySelectorAll('.file-findings details').forEach(n=>n.open=true)");
    await check('per-file causes preserve exact model reasons, invalid coordinates and evidence diagnostics',"[...document.querySelectorAll('.finding-file .finding-reason')].some(n=>n.textContent===__mig.probe().roles['agent-a'][0].reason) && document.querySelector('.file-findings').textContent.includes('agent:agent-a@v99') && document.querySelector('.file-findings').textContent.includes('版本越界，原坐标保留') && [...document.querySelectorAll('.file-findings .verow.bad')].some(n=>n.textContent.includes('INVALID <img src=x') && n.textContent.includes('位置不存在'))");
    await check('findings render model HTML as text and complete basis never becomes semantic green',"!document.querySelector('.file-findings img,.file-findings script,.file-findings b') && !window.findingXss && document.querySelector('.finding-boundary').textContent==='BOUNDARY <b>只是文本</b>' && document.querySelector('.finding-cause[data-basis-status=\"complete\"]').textContent.includes('字段齐全（语义未验证）') && !document.querySelector('.finding-cause.r-ok,.finding-item.r-ok')");
    await check('unbound file association remains separate even when its agent coordinate exists',"document.querySelector('.finding-unbound').textContent.includes('不以 root 猜补') && !document.querySelector('.finding-unbound button,.finding-unbound .lnk,.finding-unbound .more') && JSON.stringify(__mig.probe().trajectory)===window.findingTrace && JSON.stringify(__mig.probe().evidence_graph)===window.findingGraph");
    await evaluate("document.querySelector('.finding-file .finding-locate').click()");
    await check('finding locates existing reason drawer without adding a node, edge or visit',"document.querySelector('#side').textContent.includes('A 独有原因') && JSON.stringify(__mig.probe().trajectory)===window.findingTrace && JSON.stringify(__mig.probe().evidence_graph)===window.findingGraph && JSON.stringify(Object.keys(__mig.xt().byId))===window.findingNodeIds");
    await evaluate("[...document.querySelectorAll('.dchips span')].find(n=>n.textContent.startsWith('B ')).click()");
    await check('finding causes follow selected defect without mixing other item reasons',"document.querySelector('.file-findings').textContent.includes('B 独有原因') && !document.querySelector('.file-findings').textContent.includes('A 独有原因') && !document.querySelector('.file-findings .finding-item[data-defect=\"A\"]')");
    await evaluate("__mig.load('findings-unbound')");
    await until("__mig.probe().runDir==='findings-unbound' && document.querySelector('.file-findings')");
    await check('unbound findings keep raw claims and references without borrowing current root or links',"document.querySelectorAll('.finding-file').length===0 && document.querySelectorAll('.finding-unbound .finding-item').length===3 && !document.querySelector('.file-findings button,.file-findings .lnk,.file-findings .more') && document.querySelector('.file-findings').textContent.includes('INVALID <img src=x') && document.querySelector('.file-findings').textContent.includes('不以根节点代替未知文件')");
    for(const kind of ['final_inline','checked_draft_ref','saved_schema_repair','legacy_saved','invalid_saved']){
      const run='source-'+kind;
      await evaluate('__mig.load('+JSON.stringify(run)+')');
      await until('__mig.probe().runDir==='+JSON.stringify(run)+' && document.querySelector(".document-source")?.dataset.kind==='+JSON.stringify(kind));
      await evaluate("window.sourceTrajectory=JSON.stringify(__mig.probe().trajectory);document.querySelector('.document-source').open=true");
      await check('document source '+kind+' preserves provenance without semantic approval or HTML',"document.querySelector('.document-source').dataset.semanticChecked==='false' && !document.querySelector('.document-source img') && !window.sourceXss && document.querySelector('.document-source').textContent.includes('SOURCE_NOTE <img') && document.querySelector('.document-source').textContent.includes('不认证根因') && JSON.stringify(__mig.probe().trajectory)===window.sourceTrajectory");
      if(kind==='legacy_saved'||kind==='saved_schema_repair') await check(kind+' is readable as a saved claim, never a verified final submission',"document.querySelector('.document-source').dataset.verified==='false' && document.querySelector('.document-source').textContent.includes('未认证为最终原文') && document.querySelector('#probe').textContent.includes('A 独有原因')");
      if(kind==='invalid_saved') await check('invalid saved document does not color claims while authenticated visits remain',"document.querySelectorAll('#canvas .node.p-chain').length===0 && document.querySelectorAll('#canvas .node.p-seen').length>0 && document.querySelector('#probe').textContent.includes('保存稿 raw 与 data 不一致')");
    }
    await evaluate("__mig.load('forest-layout')");
    await until("__mig.probe().runDir==='forest-layout' && __mig.xt()?.walk && Object.values(__mig.xt().byId).filter(n=>n.traj).length===6");
    await evaluate("window.forestTrace=JSON.stringify(__mig.probe().trajectory);window.forestEdges=JSON.stringify(__mig.probe().evidence_graph);window.forestIds=Object.values(__mig.xt().byId).filter(n=>n.traj).map(n=>n.trajId).join('|')");
    async function checkGeometry(label) {
      const geometry=await evaluate('('+readLayoutGeometry.toString()+')()');
      assert.deepEqual(geometry.overlaps,[],label+' non-overlap');
      assert.deepEqual(geometry.outside,[],label+' whole graph fitted');
      console.log('PASS '+label+' all atom/stub boxes separate and inside viewport');
    }
    await checkGeometry('independent search forest with descendant stubs');
    for(const width of [1200,2100,1600]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:false});
      await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
      await checkGeometry('search forest resized to '+width);
    }
    await evaluate("__mig.setCand(true);__mig.setCand(false);[...document.querySelectorAll('.dchips span')].find(n=>n.textContent.startsWith('B ')).click()");
    await checkGeometry('search forest after redraw and defect filter');
    await check('forest layout never changes semantic coordinates, visits, transitions or evidence graph',"JSON.stringify(__mig.probe().trajectory)===window.forestTrace && JSON.stringify(__mig.probe().evidence_graph)===window.forestEdges && Object.values(__mig.xt().byId).filter(n=>n.traj).map(n=>n.trajId).join('|')===window.forestIds && document.querySelectorAll('.navigation-event').length===9 && document.querySelectorAll('.wire.evidence').length===0");
    await evaluate("(()=>{const parent=Object.values(__mig.xt().byId).find(n=>n.trajId==='agent:agent-a@2'),stub=parent.children.map(t=>__mig.xt().byId[t]).find(n=>n.isLedgerStub);__mig.expandStub(stub.tid)})()");
    await checkGeometry('search-component stub expanded without positional aliasing');
    await check('expanding a search component does not mutate recorded investigation identities',"JSON.stringify(__mig.probe().trajectory)===window.forestTrace && JSON.stringify(__mig.probe().evidence_graph)===window.forestEdges && Object.values(__mig.xt().byId).filter(n=>n.traj).map(n=>n.trajId).join('|')===window.forestIds");
    // Atom caches are deliberately immutable within one page's ledger. Use a
    // fresh page when the synthetic ledger itself changes proof records.
    await send('Page.navigate',{url:origin+'/?probe=read-proof'});
    await until("window.__mig && __mig.probe()?.runDir==='read-proof' && __mig.xt()?.walk");
    await evaluate(clickAgent+";document.querySelector('#side .rootbtn').click()");
    await until("__mig.xt().walk!==true && document.querySelectorAll('.wire.relation-uncertain').length===2");
    await check('read proof and lifetime self-written label do not claim execution, delivery or order',"document.querySelector('#canvas').textContent.includes('执行依据未核') && document.querySelector('#canvas').textContent.includes('正文交付未核') && document.querySelector('#canvas').textContent.includes('旧记录·执行/交付依据未记录') && document.querySelector('#canvas').textContent.includes('同代理也写过') && !document.body.textContent.includes('写前读') && !document.querySelector('.wire.chain')");
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
