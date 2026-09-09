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
 structured:{identity:{match:true,bound:true,status:'matched'},errors:[],defects:[{id:'A',title:'缺陷甲',nodes:[claim(roles[0]),claim(legacyRole)],edges:[]},{id:'B',title:'缺陷乙',nodes:[claim(roles[1])],edges:[]}]},
 trajectory:{mode:'via',root,nodes,edges:[],visits,transitions,declared:[],side_title:'未查询 · 结论提及'}};
const versions=[1,2,3].map(v=>({v,by:v===2?'agent-b':'agent-a',by_name:v===2?'Agent B':'Agent A',by_ver:v===3?2:1,ts:'2026-01-01T00:00:0'+v+'Z',lines:1,content_known:false,source:'opaque'}));
const agents=['agent-a','agent-b'].map(id=>({id,label:id==='agent-a'?'Agent A':'Agent B',n_versions:id==='agent-a'?2:1,kind:'agent',session:'fixture',reads:[],writes:[],actions:[],inbox:[]}));
const data={sid:'fixture',sid8:'fixture',project:'Trace fidelity regression',urls:{data:'/data',atom:'/atom',probe:'/probe',filediff:'/diff',report:null}};
const html=fs.readFileSync(path.join(repo,'src/migloop/render/templates/fixchain.html'),'utf8').replace('__FIXCHAIN_JSON__',JSON.stringify(data));
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  let body;
  if(url.pathname==='/') {res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}
  if(url.pathname==='/data')body={chains:[]};
  else if(url.pathname==='/atom/index')body={agents,files:[{path:file,kind:'ets',n_versions:3,has_writer:true}]};
  else if(url.pathname==='/probe'){
    body=structuredClone(probe);
    if(url.searchParams.get('run')==='no-root'||url.searchParams.get('run')==='empty'){
      body.trajectory.root=null;body.trajectory.nodes=[{...nodes[3],parent:null}];body.trajectory.transitions=[];
      body.trajectory.visits=visits.filter(v=>v.status==='rejected');body.steps=steps.filter(s=>s.i===7);
      if(url.searchParams.get('run')==='empty'){body.trajectory.nodes=[];body.structured.defects=[];body.roles={};}
    }
  }
  else if(url.pathname==='/atom/file')body={path:file,v:3,versions,readers:[],mentions:[{by:'agent-b',by_name:'Agent B',by_ver:1,cls:'change',ctx:'lexical candidate',win:1}]};
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
    const point=await evaluate("(()=>{const r=document.querySelector('.route-step[data-step=\"4\"]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
    await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
    await check('transition step label responds to a real mouse click',"document.querySelector('#canvas .node.sel').textContent.startsWith('Agent A v1')");
    await evaluate(clickAgent);
    await check('all repeated visits and query windows preserved in drawer',"document.querySelectorAll('#side .pvisit').length===3 && document.querySelector('#side .pvisits').textContent.includes('start=2 n=4')");
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
    await evaluate("__mig.load('fixture')");
    await until("__mig.xt() && __mig.xt().walk && document.querySelectorAll('.wire.route').length===5");
    await evaluate(clickAgent);
    const output=path.join(repo,'docs/experiments/2026-09-09-trace-fidelity/screenshots');
    fs.mkdirSync(output,{recursive:true});
    const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    fs.writeFileSync(path.join(output,'01-route-revisits-defects.png'),Buffer.from(screenshot.data,'base64'));
    assert.deepEqual(errors,[],'browser console exceptions');
    console.log('PASS no browser exceptions');
  }finally{
    await fetch(endpoint+'/json/close/'+target.id).catch(()=>{});socket.close();server.close();
  }
}
main().catch(e=>{console.error(e);server.close();process.exitCode=1;});
