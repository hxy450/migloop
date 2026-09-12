// Deterministic UI contract test; fixture server and dedicated browser exit in finally.
// Usage: node tests/browser/inquiry_tree_smoke.cjs [NEW_ARTIFACT_DIRECTORY]
// Set INQUIRY_LIVE_URL to smoke-test an already running real report instead.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const http = require("node:http");
const child = require("node:child_process");
const root = path.resolve(__dirname, "../..");
const base = "/api/insight1/inquiry/tree-fixture";
const times = { root: "2026-09-12T09:00:00.000001Z", writer: "2026-09-12T08:00:00.000001Z",
  read: "2026-09-12T07:00:00.000001Z", origin: "2026-09-12T06:00:00.000001Z" };
const coordinate = (kind, key, at) => ({ kind, key, at, since: null });
const row = (id, relation, node, extra = {}) => ({ id, relation, node, at: node.at,
  strength: "confirmed", source: "indexed", evidence: ["e-12345678"], claim: "可定位的历史" + relation, ...extra });
const writer = row("native:w1", "write", coordinate("agent", "session:generator-worker", times.writer));
const input = row("native:r1", "read", coordinate("file", "/migration/specs/AudioSpec.md", times.read));
const origin = row("native:w0", "write", coordinate("agent", "session:spec-author", times.origin));
const candidate = row("model:review", "read", coordinate("file", "/migration/notes/Review.md", times.read),
  { strength: "candidate", source: "model_review", claim: "模型复核候选，保留虚线" });
const later = row("native:r2", "read", coordinate("file", input.node.key, "2026-09-12T07:00:00.000002Z"));
const repair = row("native:repair", "write", coordinate("agent", "session:fixer", times.root), { strength: "candidate" });
const report = {
  report_id: "tree-fixture", trace_session: "model-session", source_sha256: "fixture-sha",
  target: { file: "/migration/harmony/AudioPlayer.ets", at: times.root, since: null },
  document: { version: "inquiry/1", target: { file: "/migration/harmony/AudioPlayer.ets", at: times.root },
    findings: [
      { id: "A", title: "规格输入中的问题", reason: "完整原因 A", unknown: ["尚缺运行验证"], hypothesis: "待核机制 A", recommendation: "建议 A" },
      { id: "B", title: "候选输入", reason: "完整原因 B" },
      { id: "C", title: "未闭合来源", reason: "没有原生边，不画伪路径" },
    ], unexplained: ["报告保留的未知事项"] },
  nodes: [
    { id: "A:origin", finding: "A", ...origin.node, at: times.root, since: times.origin, scope: "s-original-claim",
      role: "origin", exists: true, reason: "原稿原因与范围都必须保留", evidence: ["e-abcdef12"] },
    { id: "B:origin", finding: "B", ...candidate.node, role: "origin", exists: true,
      reason: "候选输入仍未认证因果", evidence: ["e-12345678"] },
    { id: "C:origin", finding: "C", ...coordinate("agent", "unknown-author", times.origin),
      role: "unknown", exists: false, reason: "缺少历史连接", evidence: [] },
  ],
  edges: [], unverified_edges: [{ finding: "C", from: "C:origin", to: "target", diagnostic: "无可核的原生依据" }],
  issues: [], tree: { root: coordinate("file", "/migration/harmony/AudioPlayer.ets", times.root),
    paths: [
      { finding: "A", node: "A:origin", status: "candidate", steps: [writer, input, origin], repair_anchor: repair },
      { finding: "B", node: "B:origin", status: "model_review", steps: [writer, candidate], repair_anchor: repair },
      { finding: "C", node: "C:origin", status: "unclosed", steps: [], diagnostic: "缺少历史连接" },
    ] },
};
const traces = [{ id: "model-session", origin: "mcp", queries: [{ query: { op: "agent", ...writer.node } }],
  frames: [{ offset: 0 }], visibility: [] }];
const requests = [];
const liveUrl = process.env.INQUIRY_LIVE_URL;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function main() {
  const out = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), "inquiry-tree-check-"));
  if (process.argv[2]) { assert(!fs.existsSync(out), "Use a new artifact directory"); fs.mkdirSync(out, { recursive: true }); }
  const profile = fs.mkdtempSync(path.join(out, "chrome-profile-"));
  let browser, ws;
  const pending = new Map(), errors = [];
  let sequence = 0;
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://127.0.0.1");
      if (url.pathname === base + "/") {
        const page = fs.readFileSync(path.join(root, "src/migloop/inquiry/page.html"), "utf8")
          .replace("__INQUIRY_CONFIG__", JSON.stringify({ api_base: base, project: "Fixture project" }))
          .replaceAll("__INQUIRY_ASSET_BASE__", base);
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); return res.end(page);
      }
      if (["/tree.js", "/viewer.js"].some(asset => url.pathname === base + asset)) {
        res.writeHead(200, { "Content-Type": "text/javascript; charset=utf-8" });
        return res.end(fs.readFileSync(path.join(root, "src/migloop/inquiry", path.basename(url.pathname))));
      }
      if (url.pathname === "/favicon.ico") { res.writeHead(204); return res.end(); }
      let data;
      if (url.pathname === base + "/api/info") data = { sources: 3, records: 128, latest_at: times.root, reports: [{ id: report.report_id }] };
      else if (url.pathname === base + "/api/report") {
        if(url.searchParams.get("id")==="slow")await sleep(150);
        data = report;
      }
      else if (url.pathname === base + "/api/trace") data = traces;
      else if (url.pathname === base + "/api/frame") data = { text: "真实调查帧" };
      else if (url.pathname === base + "/api/view") {
        let body = ""; for await (const chunk of req) body += chunk;
        const q=JSON.parse(body), scope={kind:q.kind,key:q.key,at:q.at,since:q.since||null};
        const original={ref:"e-12345678",source:"fixture.jsonl",line:8,at:times.writer};
        const writes=q.key===report.target.file ? [
          {id:"w1",number:1,at:times.writer,op:"write",label:"写入",agent:writer.node.key,file:q.key,originals:[original]},
          {id:"w2",number:2,at:times.root,op:"write",label:"写入",agent:"session:fixer",file:q.key,originals:[original]}] : [];
        const reads=q.key===report.target.file ? [{id:"read",number:1,at:times.read,op:"read",label:"读取原文",agent:"session:reader",file:q.key,originals:[original]}] : [];
        if(q.view==="overview") data={at:times.root,files:2,agents:3,report_limit:100,reports:[{id:report.report_id,file:report.target.file,at:times.root,count:3,title:"测试调查"}]};
        else if(q.view==="history") {const rows=q.category==="reads"?reads:writes;data={scope,rows,total:rows.length,next:null,changes:writes.length,reads:reads.length};}
        else if(q.view==="operation") data={scope,id:q.id,content:q.id==="w1"?"WHOLE WRITE":q.id==="read"?"2\\tPARTIAL READ":null,
          content_kind:q.id==="w1"?"write_body":q.id==="read"?"read_observation":null,
          changes:q.id==="w2"?[{text:"-OLD_VALUE\\n+NEW_VALUE",kind:"edit"}]:[],originals:[original],note:"实际记录；可能只有片段，不推演完整文件"};
        else throw Error("Unexpected view "+q.view);
      }
      else if (url.pathname === base + "/api/query") {
        let body = ""; for await (const chunk of req) body += chunk;
        const q = JSON.parse(body); requests.push(q);
        if(q.include_reads && q.view!=="calls")throw Error("include_reads only belongs to calls");
        if (q.view === "neighbors") {
          let rows = [];
          if (q.key === report.target.file) rows = [writer, { ...writer, id: "native:w2" }, repair];
          if (q.key === writer.node.key) rows = [input, {...candidate,id:"native:guess",source:"indexed"}, later];
          if (q.key === input.node.key) rows = q.offset ? [origin] : [{...candidate,id:"native:guess",source:"indexed"}];
          if (q.key === origin.node.key) rows = [row("native:dispatch", "dispatch", coordinate("agent", "session:parent", "2026-09-12T05:00:00.000001Z"),
            { strength: "candidate", occurrence_at: "2026-09-12T05:00:00.000001Z", confirmed_at: times.root,
              identity_known_at_cutoff: false, identity_basis: "子 Agent 身份来自稍后回执，本次查询截止时未知。", status: "identity_pending" })];
          if(q.direction==='downstream') rows=q.key===report.target.file ? [row('native:reader','read',coordinate('agent','session:reader',times.writer))] : [];
          data = { kind: "neighbors", scope: { kind: q.op, key: q.key, at: q.at }, rows, total: rows.length, next: q.key===input.node.key && !q.offset && q.direction!=="downstream" ? 1 : null };
        } else if (q.op === 'catalog') data = {kind:'catalog',catalog_kind:q.kind,rows:[{key:q.kind==='file'?report.target.file:writer.node.key}],total:1,next:null};
        else if (q.op === "open") data = { source: "fixture.jsonl", line: 8, at: times.origin, text: q.pointer === "" ? "FULL RAW RECORD" : "ORIGINAL EVIDENCE", request_context: null };
        else if (q.view === "changes") data = { kind: "changes", rows: [{ at: times.origin, agent: "spec-author", strength: "confirmed",
          payloads: [{ tool: "Edit", block: 0, body: { old_string: "OLD_VALUE", new_string: "NEW_VALUE" } }],
          request: "e-12345678" }], total: 1, next: null };
        else data = { kind: "records", rows: [], total: 0, next: null };
      } else { res.writeHead(404); return res.end(JSON.stringify({ error: "Unexpected path " + req.url })); }
      res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" }); res.end(JSON.stringify(data));
    } catch (error) { errors.push(error.message); res.writeHead(500); res.end(JSON.stringify({ error: error.message })); }
  });
  try {
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    const url = liveUrl || "http://127.0.0.1:" + server.address().port + base + "/?report=tree-fixture";
    const executable = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
    browser = child.spawn(executable, ["--headless=new", "--disable-gpu", "--no-first-run",
      "--no-default-browser-check", "--remote-debugging-port=0", "--user-data-dir=" + profile, "about:blank"],
      { windowsHide: true, stdio: "ignore" });
    let port;
    for (let i = 0; i < 150; i++) {
      const active = path.join(profile, "DevToolsActivePort");
      if (fs.existsSync(active)) { port = fs.readFileSync(active, "utf8").split("\n")[0]; break; }
      await sleep(100);
    }
    assert(port, "Chrome did not become ready");
    const endpoint = "http://127.0.0.1:" + port;
    const tabs = await fetch(endpoint + "/json").then(r => r.json());
    ws = new WebSocket(tabs.find(t => t.type === "page").webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
    ws.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.method === "Runtime.exceptionThrown") errors.push(JSON.stringify(message.params.exceptionDetails));
      const task = pending.get(message.id);
      if (task) { clearTimeout(task.timer); pending.delete(message.id); message.error ? task.reject(Error(JSON.stringify(message.error))) : task.resolve(message.result); }
    };
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => { pending.delete(id); reject(Error("CDP timeout: " + method)); }, 15000);
      pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params }));
    });
    const evaluate = async expression => {
      const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
    };
    const wait = async expression => {
      for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(100); }
      throw Error("Page condition timeout: " + expression + "\n" + await evaluate("document.body.innerText.slice(-1600)") + "\n" + errors.join("\n"));
    };
    await send("Runtime.enable");
    await send("Page.enable");
    await send("Emulation.setDeviceMetricsOverride", { width: 1720, height: 1020, deviceScaleFactor: 1, mobile: false });
    await send("Page.navigate", { url });
    await wait("window.inquiryTree?.model && document.querySelector('#side .vrow')");
    let liveDiagnostic = null;
    if (liveUrl) {
      liveDiagnostic = await evaluate(`(async () => {
        const getTrace=()=>fetch((INQUIRY_CONFIG.api_base||'')+'/api/trace?session='+encodeURIComponent(inquiryTree.report.trace_session)).then(r=>r.json());
        const before=await getTrace();
        const seedEdges=[...inquiryTree.model.nodes.values()].filter(n=>n.row).length;
        await inquiryTree.expand(inquiryTree.model.root);
        const first=inquiryTree.model.root.children.find(n=>!n.reference);
        if(first)await inquiryTree.expand(first);
        const after=await getTrace();
        const origin=[...inquiryTree.model.nodes.values()].find(n=>n.claims.some(c=>c.role==='origin'));
        if(origin)inquiryTree.select(origin);
        inquiryTree.fit();
        return {root:inquiryTree.model.root.coordinate.key,seedEdges,nodes:inquiryTree.model.visible().length,
          traceUnchanged:JSON.stringify(before)===JSON.stringify(after),gaps:inquiryTree.model.unclosed.length,
          manualFailures:[...inquiryTree.model.nodes.values()].filter(n=>n.error).map(n=>n.error),
          ordinaryCandidates:[...inquiryTree.model.nodes.values()].filter(n=>n.row?.strength==='candidate' && n.row.source!=='model_review').length};
      })()`);
      assert(liveDiagnostic.traceUnchanged, "manual expansion leaves real model trace unchanged");
      assert.equal(liveDiagnostic.ordinaryCandidates,0);
      assert.deepEqual(liveDiagnostic.manualFailures,[]);
      await evaluate("inquiryTree.select(inquiryTree.model.root)");
      await wait("document.querySelector('#side .vrow')");
      await evaluate("[...document.querySelectorAll('#side .vrow button')].find(b=>b.textContent==='原文 / diff').click()");
      await wait("document.querySelector('#side .original pre')");
      liveDiagnostic.originalOpened=await evaluate("document.querySelector('#side .original pre').textContent.length>0");
      assert(liveDiagnostic.originalOpened);
      await evaluate("[...document.querySelectorAll('#side details')].find(d=>d.firstChild.textContent==='相关调用与记录').open=true");
      await wait("document.querySelector('#side .quote button')");
      await evaluate("[...document.querySelectorAll('#side details')].find(d=>d.firstChild.textContent==='片段来源 / 搜索历史').open=true;document.querySelector('#side input').value='30';[...document.querySelectorAll('#side button')].find(b=>b.textContent==='查找').click()");
      await wait("[...document.querySelectorAll('#side details')].find(d=>d.firstChild.textContent==='片段来源 / 搜索历史').querySelector('.quote')");
      await evaluate("inquiryTree.select(inquiryTree.model.root.children[0])");
      await wait("document.querySelector('#side .tag')?.textContent==='AGENT 原子' && [...document.querySelectorAll('#side details')].some(d=>d.firstChild.textContent==='其它工具返回')");
      await evaluate("[...document.querySelectorAll('#side details')].find(d=>d.firstChild.textContent==='其它工具返回').open=true;[...document.querySelectorAll('#side details')].find(d=>d.firstChild.textContent==='派发与任务').open=true");
      await wait("[...document.querySelectorAll('#side details')].find(d=>d.firstChild.textContent==='其它工具返回').querySelector('.quote')");
      await wait("[...document.querySelectorAll('#side details')].find(d=>d.firstChild.textContent==='派发与任务').querySelector('.quote')");
      assert.equal(await evaluate("document.querySelectorAll('#side .error').length"),0);
      await evaluate("inquiryTree.select(inquiryTree.model.root)");
      await wait("document.querySelector('#side .vrow')");
      await evaluate("document.querySelector('#z1').click()");
    } else {
      assert.equal(await evaluate("inquiryTree.model.root.coordinate.key"),report.target.file);
      assert.equal(await evaluate("inquiryTree.model.root.children.length"),1);
      assert.equal(await evaluate("(async()=>{const slow=migloopViewer.loadReport('slow');await migloopViewer.loadReport('tree-fixture');await slow;return new URLSearchParams(location.search).get('report')})()"),"tree-fixture","a late report response cannot replace a newer navigation");
      assert.equal(await evaluate("getComputedStyle(document.querySelector('.tree-node')).height"),"30px");
      assert.equal(await evaluate("getComputedStyle(document.querySelector('.tree-node')).width"),"196px");
      assert.equal(await evaluate("document.querySelector('#askai').disabled"),true,"unconnected AI is not a fake working button");
      assert.equal(await evaluate("document.querySelector('#structuredReport')"),null,"no investigator console");
      assert.equal(await evaluate("getComputedStyle(document.querySelector('[data-edge=\"model:review\"]')).strokeDasharray !== 'none'"),true);
      assert.equal(await evaluate("[...inquiryTree.model.nodes.values()].some(n=>n.coordinate.key==='unknown-author')"),false);
      assert.equal(await evaluate("document.querySelector('.tree-node.root').classList.contains('historical-problem')"),false);
      await evaluate("[...document.querySelectorAll('#side .vrow button')].find(b=>b.textContent==='原文 / diff').click()");
      await wait("document.querySelector('#side').textContent.includes('WHOLE WRITE')");
      await evaluate("[...document.querySelectorAll('#side .vrow')][1].querySelectorAll('button')[1].click()");
      await wait("document.querySelector('#side').textContent.includes('NEW_VALUE')");
      await evaluate("[...document.querySelectorAll('#side details')].find(d=>d.firstChild.textContent==='已知时刻的读取原文').open=true");
      await wait("document.querySelector('[data-operation=\"read\"]')");
      await evaluate("[...document.querySelectorAll('[data-operation=\"read\"] button')].find(b=>b.textContent==='原文').click()");
      await wait("document.querySelector('#side').textContent.includes('PARTIAL READ')");
      assert.equal(await evaluate("document.querySelector('#side').textContent.includes('可能只有片段')"),true);
      const initialTrace=JSON.stringify(traces);
      await evaluate("inquiryTree.expand(inquiryTree.model.root)");
      assert.equal(await evaluate("inquiryTree.model.root.children.length"),2,"raw repair candidate stays hidden");
      assert.equal(await evaluate("inquiryTree.model.root.children[0].origins.has('report') && inquiryTree.model.root.children[0].origins.has('manual')"),true);
      await evaluate("inquiryTree.expand(inquiryTree.model.root.children[0])");
      assert.equal(await evaluate("inquiryTree.model.root.children[0].children.filter(n=>n.coordinate.key.includes('AudioSpec')).length"),2,"microseconds preserved");
      assert.equal(await evaluate("[...inquiryTree.model.nodes.values()].some(n=>n.row?.id==='native:guess')"),false);
      await evaluate("inquiryTree.expand(inquiryTree.model.root.children[0].children[0])");
      assert(requests.some(q=>q.key===input.node.key && q.offset===1),"candidate-only page does not hide next confirmed page");
      await evaluate("inquiryTree.expand(inquiryTree.model.root,'downstream')");
      assert.equal(await evaluate("inquiryTree.model.rights.length"),1);
      assert.equal(JSON.stringify(traces),initialTrace);
      assert(!requests.some(q=>q.op==="record_trace"));
      await evaluate("document.querySelector('.tree-node.root').click()");
      assert.equal(await evaluate("inquiryTree.model.root.collapsed"),true);
      await evaluate("document.querySelector('.tree-node.root').click()");
      assert.equal(await evaluate("inquiryTree.model.root.collapsed"),false);
      await evaluate("document.querySelector('#finding').value='B';document.querySelector('#finding').dispatchEvent(new Event('change'))");
      await wait("document.querySelector('#side').textContent.includes('候选输入仍未认证因果')");
      await evaluate("document.querySelector('#finding').value='A';document.querySelector('#finding').dispatchEvent(new Event('change'))");
      await wait("document.querySelector('[data-claim=\"A:origin\"]')");
      assert.equal(await evaluate("document.querySelector('[data-edge=\"model:review\"]')"),null);
      await evaluate("document.querySelector('[data-claim=\"A:origin\"] details').open=true;document.querySelector('[data-claim=\"A:origin\"] button').click()");
      await wait("document.querySelector('[data-claim=\"A:origin\"]').textContent.includes('ORIGINAL EVIDENCE')");
      assert.equal(requests.at(-1).at,times.root,"claim evidence keeps original cutoff");
      assert.equal(requests.at(-1).since,times.origin,"claim evidence keeps original lower bound");
      await evaluate("document.querySelector('#load').click()");
      await wait("document.querySelector('#reportsDialog').open");
      assert.equal(await evaluate("document.querySelector('#reportNotes').textContent.includes('尚未连到树上')"),false,"finding A has no hidden path");
      await evaluate("document.querySelector('#reportsList button').click()");
      await wait("!document.querySelector('#reportsDialog').open");
      await evaluate("document.querySelector('#load').click()");
      await wait("document.querySelector('#reportNotes').textContent.includes('缺少历史连接')");
      await evaluate("document.querySelector('#closeReports').click();inquiryTree.select(inquiryTree.model.root)");
      await wait("document.querySelector('#side .head button')");
      await evaluate("document.querySelector('#side .head button').click()");
      await wait("document.querySelector('#timeDialog').open");
      assert.equal(await evaluate("document.querySelector('#at').value"),times.root);
      await evaluate("document.querySelector('#at').value='2026-09-12T10:00:00.000003Z';document.querySelector('#applyTime').click()");
      await wait("inquiryTree.model.root.coordinate.at==='2026-09-12T10:00:00.000003Z' && !document.querySelector('#timeDialog').open");
      assert.equal(await evaluate("inquiryTree.report"),null);
      assert.equal(await evaluate("document.querySelector('#finding').hidden"),true);
      assert.equal(await evaluate("[...inquiryTree.model.nodes.values()].some(n=>n.modelSeen)"),false,"exiting a report clears model-visit marks");
      assert.equal(await evaluate("inquiryTree.model.root.children.length"),2,"manual mode has confirmed writers only");
      assert.equal(await evaluate("new URLSearchParams(location.search).has('report')"),false,"manual time does not retain a report URL that overrides it on refresh");
      await send("Page.reload");
      await wait("inquiryTree.model?.root.coordinate.at==='2026-09-12T10:00:00.000003Z' && inquiryTree.model.root.loaded");
      assert.equal(await evaluate("inquiryTree.report"),null,"refresh preserves manual scope");
      await evaluate("document.querySelector('#z1').click();document.querySelector('#railtog').click()");
      assert.equal(await evaluate("inquiryTree.zoom"),1);
      assert.equal(await evaluate("document.querySelector('#rail').classList.contains('closed')"),true);
      await evaluate("document.querySelector('#railtog').click();document.querySelectorAll('#railbody .rsec')[1].querySelector('.rrow').click()");
      await wait("document.querySelector('#railbody .vline')");
      // The host job is deliberately a fixture. Production stays disabled until configured.
      await evaluate("migloopViewer.configure({investigate:async target=>{window.aiTarget=target;return 'tree-fixture'}});document.querySelector('#askai').click()");
      await wait("inquiryTree.report?.report_id==='tree-fixture' && document.querySelector('#askai').textContent==='AI 帮我查'");
      assert.equal(await evaluate("aiTarget.file"),report.target.file);
      await evaluate("migloopViewer.configure({});document.querySelector('#finding').value='A';document.querySelector('#finding').dispatchEvent(new Event('change'));document.querySelector('#z1').click()");
    }
    assert.equal(errors.length, 0, errors.join("\n"));
    const screenshot = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(out, "inquiry-tree.png"), Buffer.from(screenshot.data, "base64"));
    const audit = { passed: true, url, errors, liveDiagnostic, queryCount: requests.length,
      checks: ["original compact shell", "single tree for saved and manual exploration", "ordinary candidates hidden",
        "model-review-only dashed edges", "write text and edit delta", "read observation expansion",
        "trace isolation", "precise cutoff", "load dialog", "no fabricated AI runner", "no JavaScript errors"],
    };
    fs.writeFileSync(path.join(out, "audit.json"), JSON.stringify(audit, null, 2));
    console.log(JSON.stringify({ ...audit, artifacts: out }));
    await send("Browser.close").catch(() => {});
  } finally {
    if (ws) ws.close();
    for (const task of pending.values()) clearTimeout(task.timer);
    if (browser && browser.exitCode === null) browser.kill();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
