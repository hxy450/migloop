/* Read-only real-page time-scope check using an existing local Chrome.
 * node tests/browser/probe_scope_smoke.cjs PAGE_URL NEW_SCREENSHOT
 * Does not launch models, modify runs, or overwrite screenshots.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

async function main() {
  const [url, output, ...extra] = process.argv.slice(2);
  if (!url || !output || extra.length || new URL(url).hostname !== '127.0.0.1') {
    throw Error('Require exactly a loopback PAGE_URL and a NEW_SCREENSHOT path');
  }
  if (fs.existsSync(output)) throw Error('Refuse to overwrite screenshot');
  const endpoint = 'http://127.0.0.1:19652';
  const target = await (await fetch(endpoint + '/json/new?about:blank', {method: 'PUT'})).json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  const pending = new Map(), requests = new Map(), errors = [];
  let serial = 0;
  ws.onmessage = event => {
    const msg = JSON.parse(event.data), p = msg.params;
    if (msg.method === 'Runtime.exceptionThrown') errors.push(p.exceptionDetails.exception?.description || p.exceptionDetails.text);
    if (msg.method === 'Network.requestWillBeSent') requests.set(p.requestId, {url: p.request.url, method: p.request.method});
    if (msg.method === 'Network.responseReceived') Object.assign(requests.get(p.requestId) || {}, {status: p.response.status});
    if (msg.method === 'Network.loadingFinished') Object.assign(requests.get(p.requestId) || {}, {finished: true});
    if (msg.method === 'Network.loadingFailed') Object.assign(requests.get(p.requestId) || {}, {error: p.errorText});
    const waiting = pending.get(msg.id);
    if (waiting) {
      pending.delete(msg.id); clearTimeout(waiting.timer);
      msg.error ? waiting.reject(Error(JSON.stringify(msg.error))) : waiting.resolve(msg.result);
    }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++serial, timer = setTimeout(() => {
      pending.delete(id); reject(Error('CDP timeout: ' + method));
    }, 20000);
    pending.set(id, {resolve, reject, timer}); ws.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  const waitFor = async (expression, label) => {
    for (let i = 0; i < 100; i++) {
      if (await evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 300));
    }
    throw Error('Page timeout: ' + label);
  };
  const snapshot = () => evaluate(`(() => {
    const p=__mig.probe(), x=__mig.xt();
    return {trajectory:JSON.stringify(p.trajectory),steps:JSON.stringify(p.steps),
      nodes:p.trajectory.nodes.length,visits:p.trajectory.visits.length,transitions:p.trajectory.transitions.length,
      entities:Object.values(x.byId).filter(n=>!n.hidden).length,
      drawn:[...document.querySelectorAll('#canvas .wire.route')].map(n=>Number(n.dataset.step)).sort((a,b)=>a-b)};
  })()`);
  const viewport = () => evaluate(`(() => {
    const graph=document.querySelector('#graph'), g=graph.getBoundingClientRect();
    const toolbar=graph.querySelector('.toolbar').getBoundingClientRect();
    const bounds={left:Math.max(0,g.left+graph.clientLeft),top:Math.max(0,toolbar.bottom),
      right:Math.min(innerWidth,g.left+graph.clientLeft+graph.clientWidth),
      bottom:Math.min(innerHeight,g.top+graph.clientTop+graph.clientHeight)};
    const nodes=[...document.querySelectorAll('#canvas .node')].map(n=>{
      const r=n.getBoundingClientRect();
      return {label:n.firstChild?.textContent,title:n.title,left:r.left,top:r.top,right:r.right,bottom:r.bottom,
        inViewport:r.width>0&&r.height>0&&r.left>=bounds.left-1&&r.top>=bounds.top-1
          &&r.right<=bounds.right+1&&r.bottom<=bounds.bottom+1};
    });
    return {bounds,scrollLeft:graph.scrollLeft,scrollTop:graph.scrollTop,total:nodes.length,
      contained:nodes.filter(n=>n.inViewport).length,outside:nodes.filter(n=>!n.inViewport)};
  })()`);
  try {
    await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
    await send('Emulation.setDeviceMetricsOverride', {width: 2200, height: 1500, deviceScaleFactor: 1, mobile: false});
    await send('Page.navigate', {url});
    await waitFor('!!(window.__mig && __mig.probe()?.trajectory && __mig.xt()?.walk)', 'probe trajectory');
    const before = await snapshot();
    const initialViewport = await viewport();
    await evaluate("document.querySelector('#zf').click()");
    await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    const fittedViewport = await viewport();
    assert.equal(fittedViewport.contained, fittedViewport.total, 'fit places every rendered node inside the graph viewport');
    const selected = await evaluate(`(() => {
      const p=__mig.probe(), x=__mig.xt(), entities=Object.values(x.byId).filter(n=>!n.hidden);
      const root=x.byId[x.root];
      const node=root?.kind==='file' ? root : entities.find(n=>n.kind==='file'&&n.anchorV===2)
        || entities.find(n=>n.kind==='file');
      if(!node) return null;
      const index=entities.indexOf(node), element=document.querySelectorAll('#canvas .node')[index];
      if(!element) return null;
      element.click();
      return {path:node.path,v:node.anchorV,label:node.label};
    })()`);
    assert(selected && Number.isInteger(selected.v), 'an actual exact file version is opened');
    await waitFor(`!!document.querySelector('#side .time-scope[data-requested-version="${selected.v}"] .time-scope-roots')
      && !document.querySelector('#side').textContent.includes('账本装配中')`, 'completed file drawer and time scope');
    const requestEntry = [...requests.entries()].find(([, r]) => {
      const u = new URL(r.url);
      return u.pathname.endsWith('/file') && u.searchParams.get('scope_only') === '1'
        && u.searchParams.get('path') === selected.path && u.searchParams.get('v') === String(selected.v);
    });
    assert(requestEntry, 'drawer actually issued a scope_only=1 request for the selected exact version');
    const [requestId, request] = requestEntry;
    assert.equal(request.method, 'GET'); assert.equal(request.status, 200); assert(request.finished && !request.error);
    const response = await send('Network.getResponseBody', {requestId});
    const parsed = JSON.parse(response.base64Encoded ? Buffer.from(response.body, 'base64').toString('utf8') : response.body);
    assert.deepEqual(Object.keys(parsed), ['time_scope'], 'metadata-only response does not include historical body');
    const scope = parsed.time_scope;
    assert.equal(scope.schema, 'migloop-time-scope/1'); assert.equal(scope.anchor.status, 'valid');
    assert.equal(scope.anchor.key, selected.path); assert.equal(scope.anchor.v, selected.v);
    assert.equal(scope.negative_proof, false); assert.equal(scope.scope_complete, false);
    const maxObserved = Math.max(...scope.roots.map(r => Date.parse(r.observed_end)).filter(Number.isFinite));
    assert.equal(Date.parse(scope.latest_known_pool_time), maxObserved, 'pool endpoint equals recorded root-group maximum');
    const afterOpen = await snapshot();
    assert.deepEqual(afterOpen, before, 'opening metadata does not change nodes, visits, transitions, or query steps');
    const visible = await evaluate(`(() => {
      const body=document.querySelector('#side .time-scope'), details=body.querySelector('details');
      details.open=true; body.scrollIntoView({block:'start',inline:'nearest'});
      const r=body.getBoundingClientRect();
      return {anchor:body.dataset.anchor,requestedVersion:body.dataset.requestedVersion,
        sessions:[...body.querySelectorAll('.time-scope-root')].map(r=>r.dataset.session),
        text:body.textContent,expanded:details.open,top:r.top,bottom:r.bottom};
    })()`);
    await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    assert.equal(visible.anchor, scope.anchor.time); assert.equal(visible.requestedVersion, String(selected.v));
    assert(visible.expanded && visible.top >= 0 && visible.top < 1500, 'expanded time-scope section is visible');
    assert(visible.text.includes(scope.latest_known_pool_time));
    for (const sid of scope.other_later_sessions || []) assert(visible.text.includes(sid), 'other later root is explicitly displayed');
    assert(visible.text.includes('不代表验证成功或行为正确') && visible.text.includes('不新增调查访问或图边'),
      'metadata is not presented as successful validation or an investigation step');
    assert.deepEqual(await snapshot(), before, 'expanding roots leaves the original trajectory and steps unchanged');
    assert.deepEqual(errors, [], 'no JavaScript exceptions');
    fs.mkdirSync(path.dirname(output), {recursive: true});
    const screenshot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
    fs.writeFileSync(output, Buffer.from(screenshot.data, 'base64'), {flag: 'wx'});
    console.log(JSON.stringify({page:url,selected,counts:{nodes:before.nodes,visits:before.visits,transitions:before.transitions},
      trajectorySha256:crypto.createHash('sha256').update(before.trajectory).digest('hex'),
      initialViewport,fittedViewport,scopeRequest:request,anchor:scope.anchor,
      latestKnownPoolTime:scope.latest_known_pool_time,otherLaterSessions:scope.other_later_sessions,
      roots:scope.roots.map(r=>({session:r.session,root:r.root_agent,start:r.observed_start,end:r.observed_end})),
      scopeVisible:{top:visible.top,bottom:visible.bottom},unchangedAfterExpand:true,errors,screenshot:output}));
  } finally {
    ws.close(); await fetch(endpoint + '/json/close/' + target.id).catch(() => {});
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
