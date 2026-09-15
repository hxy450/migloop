/* Deterministic async disclosure regressions; real viewer functions, no server. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../src/migloop/inquiry/viewer.js'), 'utf8');
const functions = [
  source.slice(source.indexOf('    function rawLink('), source.indexOf('    function paintOriginal(')),
  source.slice(source.indexOf('    function actionRow('), source.indexOf('    async function rawRows(')),
].join('\n');

function element(tag, cls, text = '') {
  return {
    tag, cls, textContent: text, children: [], isConnected: true,
    classList: {add() {}},
    appendChild(child) { this.children.push(child); return child; },
    remove() { this.isConnected = false; },
  };
}

async function check(kind, scenario, fail) {
  const pending = [];
  const context = vm.createContext({
    el: element,
    lnk: (text, cls, click) => Object.assign(element('a', cls, text), {click}),
    document: {createTextNode: text => element('#text', '', text)},
    query: () => new Promise((resolve, reject) => pending.push({resolve, reject})),
  });
  vm.runInContext(functions, context);
  const parent = element('div');
  const scope = {at: '2026-01-01T00:00:00Z'};
  const link = kind === 'rawLink' ? context.rawLink(parent, 'ref', scope) : (() => {
    const row = context.actionRow({line: 1, cite: 'ref', excerpt: 'test'}, scope);
    parent.appendChild(row);
    return row.children.find(n => n.click);
  })();
  const panels = () => (kind === 'rawLink' ? parent : parent.children[0]).children.filter(n => n.tag === 'pre');
  const first = link.click();
  const old = panels()[0];
  let newest;
  if (scenario === 'detach') old.isConnected = false;
  else if (scenario !== 'active') {
    await link.click();
    if (scenario === 'reopen') {
      const second = link.click();
      newest = panels().at(-1);
      pending[1].resolve({text: 'new response'});
      await second;
    }
  }
  const before = newest && JSON.stringify(newest);
  if (fail) pending[0].reject(new Error('old error'));
  else pending[0].resolve({text: 'old response'});
  await first; // Closed disclosures must never reject, even on network failure.
  if (scenario === 'active') {
    assert(JSON.stringify(old).includes(fail ? 'old error' : 'old response'));
  } else {
    assert.equal(old.textContent, '加载原文…', `${kind}: inactive panel was updated`);
    if (newest) assert.equal(JSON.stringify(newest), before, `${kind}: stale response replaced a new opening`);
  }
}

(async () => {
  for (const kind of ['rawLink', 'actionRow']) {
    for (const scenario of ['active', 'close', 'reopen', 'detach']) {
      for (const fail of [false, true]) await check(kind, scenario, fail);
    }
  }
  console.log('16 disclosure checks passed: success/error, close/reopen/detach, both shared renderers.');
})().catch(error => { console.error(error); process.exitCode = 1; });
