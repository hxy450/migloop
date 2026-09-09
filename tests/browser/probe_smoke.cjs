/* Inspect a real local probe page. Does not launch a model or alter its run artifacts.
 * node tests/browser/probe_smoke.cjs PAGE_URL NEW_SCREENSHOT [CDP_ENDPOINT] [bound|unbound]
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const [url, output, endpoint = 'http://127.0.0.1:19652', mode = 'bound'] = process.argv.slice(2);
  if (!url || !output || new URL(url).hostname !== '127.0.0.1') throw Error('Require local URL and new screenshot path');
  assert(['bound', 'unbound'].includes(mode), 'explicit expected identity mode');
  if (fs.existsSync(output)) throw Error('Refuse to overwrite screenshot');
  const target = await (await fetch(endpoint + '/json/new?about:blank', {method: 'PUT'})).json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let serial = 0;
  const pending = new Map(), errors = [];
  ws.onmessage = event => {
    const msg = JSON.parse(event.data);
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
    const p = pending.get(msg.id);
    if (p) { pending.delete(msg.id); clearTimeout(p.timer); msg.error ? p.reject(Error(JSON.stringify(msg.error))) : p.resolve(msg.result); }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++serial, timer = setTimeout(() => { pending.delete(id); reject(Error('CDP timeout: ' + method)); }, 20000);
    pending.set(id, {resolve, reject, timer}); ws.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const r = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  };
  try {
    await send('Page.enable'); await send('Runtime.enable');
    await send('Emulation.setDeviceMetricsOverride', {width: 2000, height: 1300, deviceScaleFactor: 1, mobile: false});
    await send('Page.navigate', {url});
    let ready = false;
    for (let i = 0; i < 100; i++) {
      ready = await evaluate(mode === 'unbound'
        ? "!!(window.__mig && __mig.probe() && document.querySelector('.trace-identity'))"
        : "!!(window.__mig && __mig.probe() && __mig.xt() && __mig.xt().walk)");
      if (ready) break;
      await new Promise(resolve => setTimeout(resolve, 300));
    }
    assert(ready, 'real probe loaded');
    const state = await evaluate(`(() => {
      const p=__mig.probe(), x=__mig.xt();
      return {bound:p.structured?.identity?.bound, errors:p.structured?.errors,
        traceBound:p.trace_identity?.bound, identityBanner:document.querySelector('.trace-identity')?.dataset.status,
        colored:document.querySelectorAll('#canvas .node.p-chain, #canvas .node.p-seen').length,
        nodes:p.trajectory.nodes.length, displayed:Object.values(x?.byId||{}).filter(n=>n.traj).length,
        expected:p.trajectory.transitions.map(t=>t.step).sort((a,b)=>a-b),
        drawn:[...document.querySelectorAll('.wire.route')].map(n=>Number(n.dataset.step)).sort((a,b)=>a-b),
        visits:p.trajectory.visits.length, queries:p.steps.length, defects:Object.keys(p.defects)};
    })()`);
    assert.equal(state.bound, mode === 'bound', 'expected report identity binding');
    assert.deepEqual(state.errors, [], 'structured report schema valid');
    assert.equal(state.displayed, state.nodes, 'all exact entities displayed');
    assert.deepEqual(state.drawn, state.expected, 'every recorded transition drawn exactly once');
    if (mode === 'unbound') {
      assert.equal(state.traceBound, false, 'actual historical source mismatch');
      assert.equal(state.identityBanner, 'mismatch', 'mismatch is visible');
      assert.equal(state.colored, 0, 'no historical query or fault paint on current nodes');
      assert.equal(state.nodes, 0, 'no historical handles rebound to current ledger');
    }
    const reasonShown = mode === 'bound' && await evaluate(`(() => {
      const p=__mig.probe(), entities=Object.values(__mig.xt().byId).filter(n=>!n.hidden);
      const roles=Object.values(p.roles||{}).flat().filter(r=>!p.defect||r.defect===p.defect);
      const index=entities.findIndex(n=>roles.some(r=>r.kind===n.kind
        && r.key===(n.kind==='file'?n.path:n.aid) && r.v===(n.kind==='file'?n.anchorV:n.anchorVer)));
      // A later requirements addition can correctly have NO red nodes. Click a
      // real claim subject, not an arbitrary repair.after anchor with no reason.
      const subject=index>=0 ? document.querySelectorAll('#canvas .node')[index] : null;
      if(!subject) return false; subject.click();
      const norm=s=>(s||'').replace(/\s+/g,'');
      const text=norm(document.querySelector('#side').textContent);
      return __mig.probe().structured.defects.some(d=>d.nodes.some(n=>n.reason && text.includes(norm(n.reason))));
    })()`);
    if (mode === 'bound') assert(reasonShown, 'clicking a node shows a corresponding structured reason');
    assert.deepEqual(errors, [], 'no browser exceptions');
    fs.mkdirSync(path.dirname(output), {recursive: true});
    const shot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
    fs.writeFileSync(output, Buffer.from(shot.data, 'base64'), {flag: 'wx'});
    console.log(JSON.stringify({page:url, mode, ...state, reasonShown, screenshot:output}));
  } finally {
    ws.close(); await fetch(endpoint + '/json/close/' + target.id).catch(() => {});
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
