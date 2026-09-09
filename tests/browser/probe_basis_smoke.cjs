/* Read-only real-page verification of attribution basis and draft-check display.
 * node tests/browser/probe_basis_smoke.cjs PAGE_URL NEW_SCREENSHOT
 * Uses existing Chrome CDP 19652. Missing fields are reported, never synthesized.
 * Python/PyYAML are used only to parse the preserved raw model block, with -B.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');

const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const isCheck = step => /^(?:mcp__migloop__)?check$/.test(String(step.tool || ''));
const rawFields = ['expected', 'actual', 'counterevidence'];

function parseModelBlock(structured) {
  if (typeof structured?.raw !== 'string' || !structured.raw.trim()) return {status:'missing'};
  const repo = path.resolve(__dirname, '../..');
  const code = 'import json,sys\nfrom migloop.verdict import parse_block\n' +
    'p=json.load(sys.stdin)\ndata,errors=parse_block(p["kind"],p["raw"])\n' +
    'print(json.dumps({"data":data,"errors":errors},ensure_ascii=False))\n';
  const run = spawnSync(process.env.MIGLOOP_PYTHON || 'python', ['-X','utf8','-B','-c',code], {
    input:JSON.stringify({kind:structured.kind || 'yaml',raw:structured.raw}), encoding:'utf8',
    timeout:20000,maxBuffer:8*1024*1024,
    env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONPATH:path.join(repo,'src') +
      (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : '')}
  });
  assert.equal(run.status,0,'read-only raw model block parser: '+(run.stderr || run.error || ''));
  const result = JSON.parse(run.stdout);
  return {status:result.errors.length?'invalid':'parsed',...result};
}

async function main() {
  const [url, output, ...extra] = process.argv.slice(2);
  if (!url || !output || extra.length || new URL(url).hostname !== '127.0.0.1') {
    throw Error('Require exactly a loopback PAGE_URL and NEW_SCREENSHOT path');
  }
  if (fs.existsSync(output)) throw Error('Refuse to overwrite screenshot');
  const endpoint='http://127.0.0.1:19652';
  const target=await (await fetch(endpoint+'/json/new?about:blank',{method:'PUT'})).json();
  const socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  let serial=0;const pending=new Map(),errors=[];
  socket.onmessage=event=>{
    const msg=JSON.parse(event.data);
    if(msg.method==='Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
    const wait=pending.get(msg.id);
    if(wait){pending.delete(msg.id);clearTimeout(wait.timer);msg.error?wait.reject(Error(JSON.stringify(msg.error))):wait.resolve(msg.result);}
  };
  const send=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},20000);
    pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));
  });
  const evaluate=async expression=>{
    const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  const until=async(expression,label)=>{
    for(let i=0;i<100;i++){
      if(await evaluate(expression)) return;
      await new Promise(resolve=>setTimeout(resolve,300));
    }
    throw Error('Page timeout: '+label);
  };
  const snapshot=()=>evaluate(`(() => {
    const p=__mig.probe(),x=__mig.xt();
    return {trajectory:JSON.stringify(p.trajectory || null),steps:JSON.stringify(p.steps || []),
      treeIds:Object.keys(x?.byId || {}).sort(),drawn:[...document.querySelectorAll('#canvas .wire.route')]
        .map(n=>Number(n.dataset.step)).sort((a,b)=>a-b)};
  })()`);
  const fieldDOM = `box=>({source:box.dataset.source,semanticChecked:box.dataset.semanticChecked,
    fields:Object.fromEntries(['expected','actual','counterevidence'].map(k=>[k,box.querySelector('.basis-'+k+' .basis-text')?.textContent])),
    expected_refs:[...box.querySelectorAll('.basis-expected-evidence .verow .mono')].map(n=>n.textContent),
    actual_refs:[...box.querySelectorAll('.basis-actual-evidence .verow .mono')].map(n=>n.textContent),
    unbound_refs:[...box.querySelectorAll('.verow.unbound')].map(n=>n.textContent),
    navigation:box.querySelectorAll('.lnk,.more,button,a').length})`;
  const compareBasis=(display,node,bound)=>{
    assert.equal(display.source,'model');assert.equal(display.semanticChecked,'false');
    for(const key of rawFields) assert.equal(display.fields[key],node.basis[key] || '未填写（不推测）','basis '+key+' matches model-derived payload');
    for(const group of ['expected','actual']){
      const refs=(node.basis[group+'_evidence'] || []).map(e=>typeof e.original_ref==='string'?e.original_ref:e.ref);
      if(bound) assert.deepEqual(display[group+'_refs'],refs,group+' reference spelling preserved');
      else for(const ref of refs) assert(display.unbound_refs.some(text=>text.includes(ref)),'historical reference remains visible');
    }
    if(!bound) assert.equal(display.navigation,0,'unbound historical basis has no source or node navigation');
  };
  try {
    await send('Page.enable');await send('Runtime.enable');
    await send('Emulation.setDeviceMetricsOverride',{width:2200,height:1500,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url});
    await until('!!(window.__mig && __mig.probe())','probe payload');
    const payload=await evaluate(`(() => {const p=__mig.probe();return {error:p.error || null,
      structured:p.structured || null,draft_check:p.draft_check || null,currentDefect:p.defect || null,
      steps:p.steps || [],trajectory:p.trajectory || null,trace_identity:p.trace_identity || null};})()`);
    if(payload.trajectory?.root) await until('!!__mig.xt()','trajectory rendered');
    const before=await snapshot(),missing=[];
    const checkSteps=payload.steps.filter(isCheck),checkNumbers=new Set(checkSteps.map(s=>s.i));
    assert(!(payload.trajectory?.visits || []).some(v=>checkNumbers.has(v.step)),'check calls are not version visits');
    assert(!(payload.trajectory?.transitions || []).some(t=>checkNumbers.has(t.step)),'check calls are not graph transitions');
    assert(!(payload.trajectory?.nodes || []).some(n=>(n.opened || []).some(i=>checkNumbers.has(i))),'check calls do not open atoms');
    for(const step of checkSteps){
      const rendered=await evaluate(`(() => {const row=[...document.querySelectorAll('#probe .st')]
        .find(n=>Number(n.querySelector('.no')?.textContent.match(/[0-9]+/)?.[0])===${JSON.stringify(step.i)});
        return row && {kind:row.dataset.callKind,nonNavigable:row.classList.contains('na'),text:row.textContent};})()`);
      assert(rendered && rendered.kind==='mcp' && rendered.nonNavigable && rendered.text.includes('草稿机械核查事件'),
        'check #'+step.i+' is visibly a non-navigation mechanical event');
    }
    let draft={status:'missing',uiCompared:false};
    if(payload.draft_check){
      const expected=payload.draft_check;
      await until('!!document.querySelector(".draft-check-summary")','draft-check status');
      const ui=await evaluate(`(() => {
        const box=document.querySelector('.draft-check-summary'),details=box.querySelector('.draft-check-details');details.open=true;
        return {status:box.dataset.status,semanticChecked:box.dataset.semanticChecked,text:box.textContent,
          records:[...box.querySelectorAll('.draft-check-record')].map(row=>({text:row.textContent,
            issues:[...row.querySelectorAll('.draft-check-issue')].map(n=>n.textContent),
            omitted:row.querySelector('.draft-check-omitted')?.textContent,
            coverage:row.querySelector('.draft-check-coverage')?.textContent}))};})()`);
      assert.equal(ui.status,expected.status,'draft status exactly matches actual payload');
      assert.equal(ui.semanticChecked,'false');
      assert(ui.text.includes('不证明模型阅读或采纳了反馈'),'no inferred model attention');
      assert.equal(ui.records.length,(expected.checks || []).length,'every supplied check is expandable');
      let provided=0,omitted=0,unknownOmission=0;
      for(let i=0;i<ui.records.length;i++){
        const record=ui.records[i],actual=expected.checks[i];
        if(Array.isArray(actual.issues)){
          assert.deepEqual(record.issues,actual.issues.map(issue=>typeof issue==='string'?issue:JSON.stringify(issue,null,2)),
            'all returned issues retain every field');
          provided+=actual.issues.length;
        }else assert(record.text.includes('未提供诊断明细'),'missing issues not represented as a clear result');
        if(Number.isInteger(actual.omitted_issues)&&actual.omitted_issues>=0){
          assert(record.omitted.includes('另省略 '+actual.omitted_issues+' 条'));omitted+=actual.omitted_issues;
        }else {assert(record.omitted.includes('省略数量未记录'));unknownOmission++;}
        if(actual.coverage!=null) assert.deepEqual(JSON.parse(record.coverage),actual.coverage,'coverage return preserved');
        else assert(record.text.includes('未提供覆盖诊断'));
      }
      draft={status:expected.status,uiCompared:true,checkCalls:expected.check_calls,records:ui.records.length,
        issuesProvided:provided,issuesOmitted:omitted,omissionUnknownRecords:unknownOmission,
        matchedCheck:expected.matched_check,semanticChecked:false};
    }else{
      missing.push('draft_check');
      assert.equal(await evaluate('document.querySelectorAll(".draft-check-summary").length'),0,'old payload gains no invented draft-check status');
    }
    const structured=payload.structured;
    const withBasis=(structured?.defects || []).flatMap(d=>(d.nodes || []).map((node,index)=>({defect:d.id,index,node})))
      .filter(item=>item.node.basis);
    let basis={status:'missing',uiCompared:false,modelOriginalCompared:false};
    if(withBasis.length){
      const chosen=withBasis.find(item=>item.defect===payload.currentDefect) || withBasis[0];
      const defect=chosen.defect;
      const switched=await evaluate(`(() => {
        const id=${JSON.stringify(defect)},p=__mig.probe();if(p.defect===id)return true;
        const chip=[...document.querySelectorAll('.dchips span')].find(n=>n.textContent.startsWith(id+' '));
        if(!chip)return false;chip.click();return __mig.probe().defect===id;})()`);
      assert(switched,'select a real defect without mutating probe data');
      const active=withBasis.filter(item=>item.defect===defect);
      const bound=structured.identity?.bound!==false && structured.identity?.match!==false && payload.trace_identity?.bound!==false;
      // Findings intentionally repeat a document's claims grouped by file.
      // Count the canonical per-node panel once; authenticate copies separately.
      const displayed=await evaluate(`[...document.querySelectorAll('#probe .pn .attribution-basis')].map(${fieldDOM})`);
      assert.equal(displayed.length,active.length,'current defect displays exactly its supplied basis entries');
      displayed.forEach((box,i)=>compareBasis(box,active[i].node,bound));
      const copies=await evaluate(`[...document.querySelectorAll('#probe .finding-item .attribution-basis')].map(n=>({
        defect:n.closest('.finding-item').dataset.defect,heading:n.closest('.finding-cause').querySelector('summary').textContent,
        box:(${fieldDOM})(n)}))`);
      for(const copy of copies){
        const item=active.find(item=>item.defect===copy.defect&&copy.heading.startsWith(item.node.spec+' '));
        assert(item,'file-grouped attribution copy belongs to an actual current-defect node');
        compareBasis(copy.box,item.node,bound);
      }
      const raw=parseModelBlock(structured);
      let originalCompared=false;
      if(raw.status==='parsed'){
        const rawDefect=(raw.data?.defects || []).find(d=>String(d.id)===String(defect));
        assert(rawDefect,'selected defect exists in preserved raw model block');
        for(const item of active){
          const original=rawDefect.nodes?.[item.index];
          assert(original && String(original.node).trim()===String(item.node.spec).trim(),'exact original node identity/order');
          for(const key of rawFields) assert.equal(item.node.basis[key],original.basis?.[key],'raw model '+key+' preserved');
          for(const key of ['expected_evidence','actual_evidence']) assert.deepEqual(
            (item.node.basis[key] || []).map(e=>typeof e.original_ref==='string'?e.original_ref:e.ref),original.basis?.[key] || [],
            'raw model references preserved');
        }
        originalCompared=true;
      }else{
        missing.push('raw_basis_comparison:'+raw.status);
        if(raw.status==='invalid') assert((structured.errors || []).length,'valid normalized basis cannot originate from an invalid raw block');
      }
      let drawer='not_exercised_unbound';
      if(bound){
        const clicked=await evaluate(`(() => {
          const n=${JSON.stringify(chosen.node)},entities=Object.values(__mig.xt()?.byId || {}).filter(e=>!e.hidden);
          const index=entities.findIndex(e=>e.kind===n.kind&&(e.kind==='file'?e.path:e.aid)===n.key
            &&(e.kind==='file'?e.anchorV:e.anchorVer)===n.v);
          if(index<0)return false;document.querySelectorAll('#canvas .node')[index].click();return true;})()`);
        assert(clicked,'basis subject is an actual existing graph node, not fabricated by this helper');
        await until('!!document.querySelector("#side .attribution-basis")','basis reason drawer');
        const matching=active.filter(item=>item.node.kind===chosen.node.kind&&item.node.key===chosen.node.key&&item.node.v===chosen.node.v);
        const side=await evaluate(`[...document.querySelectorAll('#side .attribution-basis')].map(${fieldDOM})`);
        assert.equal(side.length,matching.length,'drawer contains only this exact node and defect');
        side.forEach((box,i)=>compareBasis(box,matching[i].node,true));
        await until('!document.querySelector("#side").textContent.includes("账本装配中")','actual atom drawer response');
        drawer='checked';
      }else assert.equal(await evaluate('document.querySelectorAll("#probe .attribution-basis .lnk,#probe .attribution-basis .more").length'),0);
      await evaluate(`document.querySelectorAll('.attribution-basis').forEach(n=>{n.open=true;});
        (document.querySelector('#side .attribution-basis') || document.querySelector('#probe .attribution-basis'))?.scrollIntoView({block:'start'});`);
      basis={status:originalCompared?'checked_available_basis':'raw_comparison_missing',uiCompared:true,modelOriginalCompared:originalCompared,
        modelOriginalSource:'p.structured.raw parsed read-only with verdict.parse_block',defect,node:chosen.node.spec,
        nodeCount:active.length,drawer,semanticChecked:false};
    }else{
      missing.push('basis');
      assert.equal(await evaluate('document.querySelectorAll(".attribution-basis").length'),0,'missing basis remains missing');
      if(payload.error) assert(await evaluate(`document.querySelector('#probe').textContent.includes(${JSON.stringify(String(payload.error))})`),'load error is visible');
    }
    await evaluate(`document.querySelector('.draft-check-details')?.setAttribute('open','');
      document.querySelector('.draft-check-summary')?.scrollIntoView({block:'start'});`);
    await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    const after=await snapshot();
    assert.deepEqual(after,before,'expansion/defect selection preserves trajectory, steps, exact graph nodes and transitions');
    assert.deepEqual(errors,[],'no JavaScript exceptions');
    fs.mkdirSync(path.dirname(output),{recursive:true});
    const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    fs.writeFileSync(output,Buffer.from(shot.data,'base64'),{flag:'wx'});
    console.log(JSON.stringify({page:url,uiContractOk:true,missing,draft,basis,
      reportErrors:structured?.errors || [],loadError:payload.error,checkEvents:checkSteps.map(s=>s.i),
      trace:{present:!!payload.trajectory,nodes:payload.trajectory?.nodes?.length,visits:payload.trajectory?.visits?.length,
        transitions:payload.trajectory?.transitions?.length,sha256Before:sha(before.trajectory),sha256After:sha(after.trajectory),unchanged:true},
      errors,screenshot:output}));
  }finally{socket.close();await fetch(endpoint+'/json/close/'+target.id).catch(()=>{});}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
