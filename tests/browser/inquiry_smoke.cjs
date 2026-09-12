// Dedicated browser only; source data and prior experiment runs are untouched.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const child = require("node:child_process");
const url = process.argv[2];
const out = process.argv[3];
const modelReport = process.argv.includes("--model-report");
const endpoint = "http://127.0.0.1:19653";

async function main() {
  assert(url && out, "usage: inquiry_smoke.cjs URL EMPTY_ARTIFACT_DIRECTORY");
  if (fs.existsSync(out)) throw Error("Never overwrite previous artifacts");
  fs.mkdirSync(out, { recursive: true });
  const profile = fs.mkdtempSync(path.join(out, "chrome-profile-"));
  const browser = child.spawn(
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--remote-debugging-port=19653",
      "--user-data-dir=" + profile,
      "about:blank",
    ],
    { windowsHide: true, stdio: "ignore" },
  );
  let ws, send;
  const errors = [];
  try {
    let ready = false;
    for (let i = 0; i < 100 && !ready; i++) {
      ready = await fetch(endpoint + "/json/version")
        .then((r) => r.ok)
        .catch(() => false);
      if (!ready) await new Promise((r) => setTimeout(r, 100));
    }
    assert(ready, "dedicated Chrome startup");
    const tab = await (
      await fetch(endpoint + "/json/new?about:blank", { method: "PUT" })
    ).json();
    ws = new WebSocket(tab.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = reject;
    });
    let seq = 0;
    const pending = new Map();
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.method === "Runtime.exceptionThrown")
        errors.push(data.params.exceptionDetails);
      const item = pending.get(data.id);
      if (item) {
        pending.delete(data.id);
        clearTimeout(item.timer);
        data.error
          ? item.reject(Error(JSON.stringify(data.error)))
          : item.resolve(data.result);
      }
    };
    send = (method, params = {}) =>
      new Promise((resolve, reject) => {
        const id = ++seq;
        const timer = setTimeout(() => {
          pending.delete(id);
          reject(Error("CDP timeout " + method));
        }, 15000);
        pending.set(id, { resolve, reject, timer });
        ws.send(JSON.stringify({ id, method, params }));
      });
    const evaluate = async (expression) => {
      const data = await send("Runtime.evaluate", {
        expression,
        awaitPromise: true,
        returnByValue: true,
      });
      if (data.exceptionDetails)
        throw Error(JSON.stringify(data.exceptionDetails));
      return data.result.value;
    };
    const wait = async (expression) => {
      for (let i = 0; i < 100; i++) {
        if (await evaluate(expression)) return;
        await new Promise((r) => setTimeout(r, 100));
      }
      throw Error("page condition timed out: " + expression);
    };
    await send("Runtime.enable");
    await send("Page.enable");
    await send("Emulation.setDeviceMetricsOverride", {
      width: 1600,
      height: 1100,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await send("Page.navigate", { url });
    await wait(modelReport
      ? 'typeof graph !== "undefined" && graph?.nodes?.length > 0'
      : 'document.querySelectorAll("#graph .node").length === 3');
    if (modelReport) {
      assert.equal(await evaluate('document.getElementById("reports").value'),
        await evaluate('graph.report_id'), 'selector differs from the displayed report');
      const ids = await evaluate('graph.document.findings.map(f=>f.id)');
      for (const id of ids) {
        const counts = await evaluate(`(() => {
          document.getElementById('findings').value=${JSON.stringify(id)};
          document.getElementById('findings').dispatchEvent(new Event('change'));
          const id=${JSON.stringify(id)};
          return {expectedNodes:graph.nodes.filter(n=>n.finding===id).length,
            actualNodes:document.querySelectorAll('#graph .node').length,
            expectedEdges:graph.edges.filter(e=>e.finding===id).length,
            actualEdges:document.querySelectorAll('#graph path[marker-end]').length};
        })()`);
        assert.equal(counts.actualNodes, counts.expectedNodes);
        assert.equal(counts.actualEdges, counts.expectedEdges);
        const shot = await send("Page.captureScreenshot", { format: "png" });
        fs.writeFileSync(path.join(out, `finding-${id.replace(/[^a-zA-Z0-9_-]/g, "_")}.png`), Buffer.from(shot.data, "base64"));
      }
      await evaluate(`document.getElementById('findings').value=${JSON.stringify(ids[0])};draw()`);
    }
    assert.equal(
      await evaluate(
        'document.querySelectorAll("#graph path[marker-end]").length',
      ),
      modelReport ? await evaluate('graph.edges.filter(e=>e.finding===document.getElementById("findings").value).length') : 2,
    );
    const initial = await evaluate("JSON.stringify({graph,trace})");
    await evaluate(
      `document.querySelectorAll("#graph .node")[${modelReport ? 0 : 1}].dispatchEvent(new MouseEvent("click", {bubbles:true}))`,
    );
    assert(
      (await evaluate('document.getElementById("reason").innerText')).includes(
        "模型主张",
      ),
    );
    await evaluate('document.querySelector("#reason button").click()');
    await wait('document.querySelectorAll("#records .row").length > 0');
    assert.equal(
      await evaluate("JSON.stringify({graph,trace})"),
      initial,
      "manual exploration changed recorded investigation",
    );
    await evaluate(
      '[...document.querySelectorAll("#records button")].find(b=>b.textContent==="展开原文").click()',
    );
    await wait('document.getElementById("original").textContent.length > 100');
    const validImage = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(
      path.join(out, "inquiry-valid.png"),
      Buffer.from(validImage.data, "base64"),
    );
    if (modelReport) {
      if (process.argv.includes('--scope-interval')) {
        // Synthetic display fixture only: no report resubmit or stored graph mutation.
        const interval = await evaluate(`(async()=>{
          const node=graph.nodes.find(n=>!n.generated_context);
          const since=new Date(Date.parse(node.at)-60000).toISOString();
          showNode({...node,since});
          document.querySelector('#reason button').click();
          return {expected:since,actual:document.getElementById('since').value};
        })()`);
        assert.equal(interval.actual,interval.expected,'node exploration dropped since');
        assert.equal(await evaluate('JSON.stringify({graph,trace})'),initial);
        fs.writeFileSync(path.join(out,'scope-interval.json'),JSON.stringify(interval,null,2));
      }
      if (process.argv.includes('--input-views')) {
        const views = await evaluate(`(async()=>{
          const target=graph.target;
          const request={op:'file',key:target.file,at:target.at,view:'calls',limit:100};
          const folded=await api('/api/query',request);
          await query(request);
          const unfold=[...document.querySelectorAll('#records button')].find(b=>b.textContent.includes('只读形状调用'));
          if(folded.folded_read_calls && !unfold) throw Error('missing unfold control');
          const all=await api('/api/query',{...request,include_reads:true});
          if(folded.unfold) await query(folded.unfold);
          const owner=folded.participants.find(p=>p.input_scope);
          if(!owner) throw Error('no input owner');
          const inputRequest={op:'agent',scope:owner.input_scope,view:'inputs'};
          const inputs=await api('/api/query',inputRequest);
          await query(inputRequest);
          return {folded:folded.folded_read_calls,visible:folded.total,all:all.total,
            inputTotal:inputs.total,expectedAt:inputs.scope.at,actualAt:document.getElementById('at').value,
            expectedAgent:inputs.scope.key,actualAgent:document.getElementById('key').value,
            resultButtons:document.querySelectorAll('#records .row button').length};
        })()`);
        assert.equal(views.visible+views.folded,views.all);
        assert.equal(views.actualAt,views.expectedAt);
        assert.equal(views.actualAgent,views.expectedAgent);
        if(views.inputTotal) assert(views.resultButtons>0);
        assert.equal(await evaluate('JSON.stringify({graph,trace})'),initial);
        fs.writeFileSync(path.join(out,'input-views.json'),JSON.stringify(views,null,2));
      }
      if (process.argv.includes('--outline')) {
        const outline = await evaluate(`(async()=>{
          const q={op:'file',key:graph.target.file,at:graph.target.at,view:'outline',limit:100};
          const data=await api('/api/query',q);await query(q);
          return {expected:data.rows.length,actual:document.querySelectorAll('#records .row').length,
            snapshots:data.rows.flatMap(r=>r.outline).filter(r=>r.kind==='snapshot_folded').length,
            foldedLabel:document.getElementById('records').innerText.includes('快照'),
            opaqueQuery:data.opaque_query};
        })()`);
        assert.equal(outline.actual,outline.expected);
        if(outline.snapshots) assert(outline.foldedLabel);
        assert.equal(outline.opaqueQuery.view,'calls');
        assert.equal(await evaluate('JSON.stringify({graph,trace})'),initial);
        fs.writeFileSync(path.join(out,'outline.json'),JSON.stringify(outline,null,2));
      }
      if (process.argv.includes('--evidence-review')) {
        const checked=await evaluate(`(async()=>{
          const section=document.getElementById('evidence-review');
          if(!section) throw Error('missing mechanical review');
          section.open=true;
          const node=graph.nodes.find(n=>graph.evidence_review.timeline.some(t=>t.node===n.id));
          showNode(node);
          const timelineShown=document.getElementById('reason').innerText.includes('实际发生于');
          const input=await query({op:'agent',key:graph.nodes.find(n=>n.kind==='agent').key,at:graph.target.at,view:'inputs'});
          const returns=await query(input.tool_return_query);
          const visibleReturns=[...document.querySelectorAll('#records button')].filter(b=>b.textContent==='展开原文').length;
          const review=await query({op:'review',report_id:graph.report_id,offset:0,limit:1});
          const reviewVisible=document.querySelectorAll('#records .row').length;
          const post=graph.evidence_review.post_write_returns?.[0];
          let postSince=null;
          if(post) {const later=await query(post.all_returns_query);postSince=later.scope.since;}
          const follow=graph.evidence_review.cited_check_followups?.[0];
          let followSince=null;
          if(follow) {const later=await query(follow.all_returns_query);followSince=later.scope.since;}
          const coverage=await query({op:'review',report_id:graph.report_id,view:'coverage',offset:0,limit:2});
          const coverageVisible=document.querySelectorAll('#records .row').length;
          return {timelineShown,returnTotal:returns.total,expected:input.tool_return_total,
            visibleRows:visibleReturns,expectedRows:returns.rows.length,
            reviewVisible,reviewExpected:review.rows.length,postSince,expectedSince:post?.since||null,
            followSince,expectedFollowSince:follow?.since||null,
            coverageVisible,coverageExpected:coverage.rows.length};
        })()`);
        assert(checked.timelineShown);
        assert.equal(checked.returnTotal,checked.expected);
        assert.equal(checked.visibleRows,checked.expectedRows);
        assert.equal(checked.reviewVisible,checked.reviewExpected);
        assert.equal(checked.postSince,checked.expectedSince);
        assert.equal(checked.followSince,checked.expectedFollowSince);
        assert.equal(checked.coverageVisible,checked.coverageExpected);
        assert.equal(await evaluate('JSON.stringify({graph,trace})'),initial);
        fs.writeFileSync(path.join(out,'evidence-review.json'),JSON.stringify(checked,null,2));
      }
      assert.equal(errors.length, 0);
      const result = {passed:true, url, errors, model_report:true, report_mutated:false,
        checks:["all findings match submitted graph", "node reason", "manual query isolation", "raw expansion"]};
      fs.writeFileSync(path.join(out, "audit.json"), JSON.stringify(result,null,2));
      console.log(JSON.stringify(result));
      return;
    }
    const before = await evaluate("graph.edges.length");
    const diagnostic = await evaluate(`(async()=>{
      const doc=structuredClone(graph.document);
      doc.findings[0].edges[0].relation='write';
      const checked=await api('/api/report',{document:JSON.stringify(doc)});
      await loadGraph(checked);
      return {edges:graph.edges.length,gaps:graph.unverified_edges.length};
    })()`);
    assert.equal(diagnostic.edges, before - 1);
    assert.equal(diagnostic.gaps, 1);
    assert.equal(
      await evaluate('document.getElementById("kind").value'),
      "file",
    );
    assert.equal(
      await evaluate(
        'document.querySelectorAll("#graph path[marker-end]").length',
      ),
      1,
    );
    const image = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(
      path.join(out, "inquiry-checked.png"),
      Buffer.from(image.data, "base64"),
    );
    assert.equal(errors.length, 0);
    fs.writeFileSync(
      path.join(out, "audit.json"),
      JSON.stringify({ passed: true, url, errors, diagnostic }, null, 2),
    );
    console.log(
      JSON.stringify({
        passed: true,
        url,
        out,
        checks: [
          "real graph",
          "node reason",
          "manual query isolation",
          "raw expansion",
          "invalid edge not drawn",
        ],
      }),
    );
  } finally {
    if (ws) ws.close();
    const info = await fetch(endpoint + "/json/version")
      .then((r) => r.json())
      .catch(() => null);
    if (info) {
      const closing = new WebSocket(info.webSocketDebuggerUrl);
      await new Promise((resolve) => {
        closing.onopen = resolve;
        closing.onerror = resolve;
      });
      if (closing.readyState === WebSocket.OPEN)
        closing.send(JSON.stringify({ id: 1, method: "Browser.close" }));
      await new Promise((resolve) => setTimeout(resolve, 300));
      closing.close();
    }
    if (browser.exitCode === null) browser.kill();
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
