// Read-only browser acceptance over a recorded single-investigator run.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const endpoint = process.env.MIGLOOP_TEST_CDP || 'http://127.0.0.1:19652';
const url = 'http://127.0.0.1:8877/api/insight1/fixchain/ff019d8a?probe=single-20260911%2Frep1';
const out = process.env.MIGLOOP_UI_AUDIT || 'C:/Users/hongy/projects/_migloop-preview-20260911/single-ui-audit';

async function main() {
  if (fs.existsSync(out) && fs.readdirSync(out).length) throw Error('Never overwrite a previous audit');
  fs.mkdirSync(out, {recursive: true});
  let ready = false;
  for (let attempt = 0; attempt < 50 && !ready; attempt++) {
    ready = await fetch(endpoint + '/json/version').then(r => r.ok).catch(() => false);
    if (!ready) await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!ready) throw Error('Dedicated test browser did not start');
  const tab = await (await fetch(endpoint + '/json/new?about:blank', {method: 'PUT'})).json();
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  const pending = new Map(), errors = [], stages = [];
  let sequence = 0;
  ws.onmessage = event => {
    const row = JSON.parse(event.data);
    if (row.method === 'Runtime.exceptionThrown') errors.push(row.params.exceptionDetails);
    const waiter = pending.get(row.id);
    if (waiter) {
      pending.delete(row.id); clearTimeout(waiter.timeout);
      row.error ? waiter.reject(Error(JSON.stringify(row.error))) : waiter.resolve(row.result);
    }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => {pending.delete(id); reject(Error('CDP timeout: ' + method));}, 20000);
    pending.set(id, {resolve, reject, timeout});
    ws.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const wait = async expression => {
    const until = Date.now() + 120000;
    while (Date.now() < until) {
      if (await evaluate(expression)) return;
      const error = await evaluate('document.querySelector("#errorbox")?.textContent');
      if (error) throw Error(error);
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    throw Error('Page condition timed out: ' + expression);
  };
  const capture = async name => {
    const state = await evaluate('({state:__timeTree.state(),side:document.querySelector("#side").innerText,wires:document.querySelectorAll("#canvas .wire").length})');
    stages.push({name, ...state});
    const screenshot = await send('Page.captureScreenshot', {format: 'png'});
    fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(screenshot.data, 'base64'));
    return state;
  };
  try {
    await send('Runtime.enable'); await send('Page.enable');
    await send('Emulation.setDeviceMetricsOverride', {width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false});
    await send('Page.navigate', {url});
    await wait('window.__timeTree?.state().argument?.nodes.length===4 && !!document.querySelector("#side .claim-detail .reason")');
    const initial = await capture('01-model-claim');
    assert.equal(initial.state.argument.document_source.verified, true);
    assert.equal(initial.state.argument.edges.filter(e => e.binding.status === 'confirmed').length, 1);
    assert.equal(initial.state.argument.edges.filter(e => e.binding.status === 'not_observed').length, 1);
    assert(initial.side.includes('模型主张'));
    const originalTrace = JSON.stringify(initial.state.trace);
    const originalArgument = JSON.stringify(initial.state.argument);
    await evaluate(`void __timeTree.open({kind:'file',key:${JSON.stringify(initial.state.argument.target.file)},at:'2026-07-24T22:16:20.102Z',since_ts:null})`);
    await wait('document.querySelector("#side details[data-section=participants]")?.innerText.includes("aslice8-pay")');
    await capture('02-full-actor-directory');
    await evaluate(`[...document.querySelectorAll('#side details[data-section=participants] .row')].find(r=>r.innerText.includes('aslice8-pay')).querySelector('button').click()`);
    await wait('(()=>{const s=__timeTree.state(),n=s.nodes.find(n=>n.id===s.selected);return n?.scope.key.includes("aslice8-pay") && document.querySelector("#side").dataset.scope===MigloopTimeTree.scopeKey(n.scope) && !!document.querySelector("#side details[data-section=dispatches]");})()');
    const after = await capture('03-independent-agent');
    assert.equal(JSON.stringify(after.state.trace), originalTrace, 'Manual opening cannot forge model visits');
    assert.equal(JSON.stringify(after.state.argument), originalArgument, 'Manual opening cannot rewrite model claims');
    assert.equal(errors.length, 0);
    fs.writeFileSync(path.join(out, 'audit.json'), JSON.stringify({url, passed: true, errors, stages}, null, 2));
    console.log(JSON.stringify({passed: true, stages: stages.map(s=>s.name), out}));
  } catch (error) {
    fs.writeFileSync(path.join(out, 'audit.json'), JSON.stringify({url, passed: false, error: String(error), errors, stages}, null, 2));
    throw error;
  } finally {
    await fetch(endpoint + '/json/close/' + tab.id).catch(() => {});
    ws.close();
    // Only use this script with its dedicated test browser.
    const browser = await (await fetch(endpoint + '/json/version')).json();
    const closing = new WebSocket(browser.webSocketDebuggerUrl);
    await new Promise(resolve => { closing.onopen = resolve; closing.onerror = resolve; });
    if (closing.readyState === WebSocket.OPEN) closing.send(JSON.stringify({id:1,method:'Browser.close'}));
    closing.close();
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
