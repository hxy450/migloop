// Actual Chromium interaction; run against a live server, no investigator calls.
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const base =
  process.env.MIGLOOP_UI_URL ||
  "http://127.0.0.1:8877/api/insight1/fixchain/ff019d8a?probe=F10-01%2Frep1";
const out =
  process.env.MIGLOOP_UI_AUDIT ||
  "C:/Users/hongy/projects/_migloop-preview-20260911/time-tree-audit";
async function main() {
  fs.mkdirSync(out, { recursive: true });
  const t = await (
    await fetch("http://127.0.0.1:19652/json/new?about:blank", {
      method: "PUT",
    })
  ).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r, j) => {
    ws.onopen = r;
    ws.onerror = j;
  });
  let seq = 0;
  const pending = new Map(),
    errors = [],
    network = [],
    steps = [];
  let failed;
  ws.onmessage = (e) => {
    const x = JSON.parse(e.data);
    if (x.method === "Runtime.exceptionThrown")
      errors.push(x.params.exceptionDetails);
    if (x.method === "Network.responseReceived")
      network.push({
        url: x.params.response.url,
        status: x.params.response.status,
      });
    const p = pending.get(x.id);
    if (p) {
      pending.delete(x.id);
      clearTimeout(p.timer);
      x.error ? p.reject(Error(JSON.stringify(x.error))) : p.resolve(x.result);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = ++seq,
        timer = setTimeout(() => reject(Error("CDP timeout " + method)), 20000);
      pending.set(id, { resolve, reject, timer });
      ws.send(JSON.stringify({ id, method, params }));
    });
  const ev = async (expression) => {
    const r = await send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (r.exceptionDetails)
      throw Error(
        r.exceptionDetails.exception?.description ||
          JSON.stringify(r.exceptionDetails),
      );
    return r.result.value;
  };
  const delay = (ms) => new Promise((r) => setTimeout(r, ms));
  async function wait(expression) {
    for (let i = 0; i < 480; i++) {
      if (await ev(expression)) return;
      const e = await ev('document.querySelector("#errorbox")?.textContent');
      if (e) throw Error("Page error: " + e);
      await delay(250);
    }
    throw Error("Wait timeout: " + expression);
  }
  async function click(expression) {
    const p = await ev(
      `(()=>{const e=${expression};if(!e)throw Error('No click target: '+${JSON.stringify(expression)});e.scrollIntoView({block:'center',inline:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};})()`,
    );
    await send("Input.dispatchMouseEvent", {
      type: "mousePressed",
      ...p,
      button: "left",
      clickCount: 1,
    });
    await send("Input.dispatchMouseEvent", {
      type: "mouseReleased",
      ...p,
      button: "left",
      clickCount: 1,
    });
    await delay(100);
  }
  async function fill(selector, text) {
    await click(`document.querySelector(${JSON.stringify(selector)})`);
    await send("Input.dispatchKeyEvent", {
      type: "keyDown",
      key: "a",
      code: "KeyA",
      modifiers: 2,
      windowsVirtualKeyCode: 65,
    });
    await send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key: "a",
      code: "KeyA",
      modifiers: 2,
      windowsVirtualKeyCode: 65,
    });
    await send("Input.insertText", { text });
  }
  const state = () =>
    ev(
      `(()=>{const s=__timeTree.state(),r=document.querySelector('#canvas .node.root'),g=document.querySelector('#graph'),b=r?.getBoundingClientRect(),v=g.getBoundingClientRect();return{...s,renderedNodes:document.querySelectorAll('#canvas .node:not(.stub)').length,wires:document.querySelectorAll('#canvas .wire').length,error:document.querySelector('#errorbox').textContent,rootVisible:!!b&&b.bottom>v.top&&b.top<v.bottom&&b.right>v.left&&b.left<v.right,side:document.querySelector('#side').innerText};})()`,
    );
  async function record(name) {
    await delay(200);
    steps.push({ name, ...(await state()) });
    const shot = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(
      path.join(out, name + ".png"),
      Buffer.from(shot.data, "base64"),
    );
  }
  try {
    await send("Runtime.enable");
    await send("Page.enable");
    await send("Network.enable");
    await send("Emulation.setDeviceMetricsOverride", {
      width: 1600,
      height: 1000,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await send("Page.navigate", { url: base });
    await wait(
      '!!window.__timeTree?.state().roots.length && __timeTree.state().nodes.some(n=>n.scope.kind==="file"&&n.expanded)',
    );
    await record("01-report-loaded");
    const initial = await state();
    assert(initial.rootVisible, "Initial root must be visible");
    const trace = JSON.stringify(initial.trace),
      graph = JSON.stringify(initial.argument);
    await click('[...document.querySelectorAll("#canvas .node.agent")].at(0)');
    await wait(
      'document.querySelector("#side h2")?.textContent.includes("conv-member") && __timeTree.state().nodes.some(n=>n.scope.kind==="agent"&&n.expanded)',
    );
    await record("02-agent-inputs");
    await fill("#q", "MemberCenterPage");
    await click('document.querySelector("#directory .directory-item")');
    await wait(
      '__timeTree.state().roots[0]?.scope.kind==="file" && !!document.querySelector("#side details[data-section=\\"writes\\"]")',
    );
    await record("03-manual-after-report");
    await fill("#at", "2026-07-24T22:16:20.102000Z");
    await click('document.querySelector("#apply-time")');
    await wait(
      '__timeTree.state().roots[0]?.scope.at==="2026-07-24T22:16:20.102000Z"',
    );
    await record("04-earlier-cutoff");
    assert(
      (await state()).nodes.every(
        (n) => n.scope.at <= "2026-07-24T22:16:20.102000Z",
      ),
      "No future node after cutoff",
    );
    await click(
      '[...document.querySelectorAll("#side details > summary")].find(e=>e.textContent.startsWith("旧版本"))',
    );
    await wait(
      '[...document.querySelectorAll("#side button")].some(b=>/^v1 ·/.test(b.textContent))',
    );
    await click(
      '[...document.querySelectorAll("#side button")].find(b=>/^v1 ·/.test(b.textContent))',
    );
    await wait(
      '__timeTree.state().roots[0]?.scope.at!=="2026-07-24T22:16:20.102000Z"',
    );
    await record("05-version-time-shortcut");
    if (
      !(await ev(
        '[...document.querySelectorAll("#model-list details > summary")].find(s=>s.textContent.startsWith("A ·")).parentElement.open',
      ))
    )
      await click(
        '[...document.querySelectorAll("#model-list details > summary")].find(s=>s.textContent.startsWith("A ·"))',
      );
    await click(
      '[...document.querySelectorAll("#model-list button")].find(b=>b.textContent.includes("conv-member")&&b.textContent.includes("origin"))',
    );
    await wait('!!document.querySelector("#side .claim-detail")');
    await record("06-claim-on-time-node");
    await click(
      '[...document.querySelectorAll("#side .claim-detail details > summary")].find(s=>s.textContent.startsWith("支持证据"))',
    );
    await click(
      '[...document.querySelectorAll("#side .claim-detail button")].find(b=>b.textContent==="展开原文")',
    );
    await wait(
      '!!document.querySelector("#side .claim-detail .query-output pre")',
    );
    await record("07-original-evidence");
    const beforeDown = (await state()).nodes.length;
    await click(
      'document.querySelector("#side details[data-section=\\"writes\\"] > summary")',
    );
    await wait(
      '!!document.querySelector("#side details[data-section=\\"writes\\"] button")',
    );
    await click(
      '[...document.querySelectorAll("#side details[data-section=\\"writes\\"] button")].find(b=>b.textContent.startsWith("将本页操作"))',
    );
    await wait(`__timeTree.state().nodes.length>${beforeDown}`);
    await record("08-downstream-files");
    const overlap = await ev(
      `(()=>{const ns=[...document.querySelectorAll('#canvas .node:not(.stub)')].map(e=>({id:e.dataset.nodeId,r:e.getBoundingClientRect()}));return ns.flatMap((a,i)=>ns.slice(i+1).filter(b=>Math.min(a.r.right,b.r.right)>Math.max(a.r.left,b.r.left)+1&&Math.min(a.r.bottom,b.r.bottom)>Math.max(a.r.top,b.r.top)+1).map(b=>[a.id,b.id]));})()`,
    );
    assert.deepEqual(overlap, [], "Distinct time nodes must not overlap");
    const selectedScope = (await state()).roots[0].scope;
    await send("Page.reload");
    await wait(
      `window.__timeTree?.state().roots[0]?.scope.kind===${JSON.stringify(selectedScope.kind)} && __timeTree.state().roots[0]?.scope.at===${JSON.stringify(selectedScope.at)} && __timeTree.state().nodes.some(n=>n.expanded)`,
    );
    await record("09-reload-preserves-time");
    if (
      !(await ev(
        '[...document.querySelectorAll("#model-list details > summary")].find(s=>s.textContent.startsWith("D ·")).parentElement.open',
      ))
    )
      await click(
        '[...document.querySelectorAll("#model-list details > summary")].find(s=>s.textContent.startsWith("D ·"))',
      );
    await click(
      '[...document.querySelectorAll("#model-list details")].find(d=>d.querySelector(":scope > summary")?.textContent.startsWith("D ·")).querySelector("button")',
    );
    await wait(
      '!!document.querySelector("#canvas .wire.model") && !!document.querySelector("#side .claim-detail")',
    );
    await record("10-verified-model-edge");
    const done = await state();
    assert.equal(
      JSON.stringify(done.trace),
      trace,
      "Manual clicks must not mutate original trace",
    );
    assert.equal(
      JSON.stringify(done.argument),
      graph,
      "Manual clicks must not mutate model findings",
    );
    assert.equal(errors.length, 0, "No browser runtime errors");
  } catch (e) {
    failed = String(e);
    try {
      await record("failure");
    } catch {}
  } finally {
    const result = {
      url: base,
      target: t.id,
      passed: !failed,
      failure: failed,
      steps,
      errors,
      network,
      modelCalls: 0,
    };
    fs.writeFileSync(
      path.join(out, "audit.json"),
      JSON.stringify(result, null, 2),
    );
    console.log(
      JSON.stringify({
        passed: !failed,
        failure: failed,
        steps: steps.map((s) => ({
          name: s.name,
          nodes: s.renderedNodes,
          wires: s.wires,
          rootVisible: s.rootVisible,
          error: s.error,
        })),
        errors,
        report: path.join(out, "audit.json"),
      }),
    );
    ws.close();
  }
  if (failed) process.exitCode = 1;
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
