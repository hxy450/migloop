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
          .replace("__INQUIRY_ASSET_BASE__", base);
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); return res.end(page);
      }
      if (url.pathname === base + "/tree.js") {
        res.writeHead(200, { "Content-Type": "text/javascript; charset=utf-8" });
        return res.end(fs.readFileSync(path.join(root, "src/migloop/inquiry/tree.js")));
      }
      if (url.pathname === "/favicon.ico") { res.writeHead(204); return res.end(); }
      let data;
      if (url.pathname === base + "/api/info") data = { sources: 3, records: 128, latest_at: times.root, reports: [{ id: report.report_id }] };
      else if (url.pathname === base + "/api/report") data = report;
      else if (url.pathname === base + "/api/trace") data = traces;
      else if (url.pathname === base + "/api/frame") data = { text: "真实调查帧" };
      else if (url.pathname === base + "/api/query") {
        let body = ""; for await (const chunk of req) body += chunk;
        const q = JSON.parse(body); requests.push(q);
        if (q.view === "neighbors") {
          let rows = [];
          if (q.key === report.target.file) rows = [writer, { ...writer, id: "native:w2" }, repair];
          if (q.key === writer.node.key) rows = [input, candidate, later];
          if (q.key === input.node.key) rows = [origin];
          if (q.key === origin.node.key) rows = [row("native:dispatch", "dispatch", coordinate("agent", "session:parent", "2026-09-12T05:00:00.000001Z"),
            { strength: "candidate", occurrence_at: "2026-09-12T05:00:00.000001Z", confirmed_at: times.root,
              identity_known_at_cutoff: false, identity_basis: "子 Agent 身份来自稍后回执，本次查询截止时未知。", status: "identity_pending" })];
          if(q.direction==='downstream') rows=q.key===report.target.file ? [row('native:reader','read',coordinate('agent','session:reader',times.writer))] : [];
          data = { kind: "neighbors", scope: { kind: q.op, key: q.key, at: q.at }, rows, total: rows.length, next: null };
        } else if (q.op === 'catalog') data = {kind:'catalog',catalog_kind:q.kind,rows:[{key:report.target.file}],total:1,next:null};
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
      throw Error("Page condition timeout: " + expression);
    };
    await send("Runtime.enable");
    await send("Page.enable");
    await send("Emulation.setDeviceMetricsOverride", { width: 1720, height: 1020, deviceScaleFactor: 1, mobile: false });
    await send("Page.navigate", { url });
    await wait("window.inquiryTree?.model && document.querySelector('#structuredReport')");
    let liveDiagnostic = null;
    if (liveUrl) {
      liveDiagnostic = await evaluate(`(async () => {
        const before = await api('/api/trace?session=' + encodeURIComponent(inquiryTree.report.trace_session));
        const seedEdges = [...inquiryTree.model.nodes.values()].filter(n=>n.row).map(n=>n.row.id);
        const rootKey = inquiryTree.model.root.coordinate.key;
        await inquiryTree.expand(inquiryTree.model.root);
        const first = inquiryTree.model.root.children.find(n=>!n.reference);
        if (first) await inquiryTree.expand(first);
        const after = await api('/api/trace?session=' + encodeURIComponent(inquiryTree.report.trace_session));
        const origin = [...inquiryTree.model.nodes.values()].find(n=>n.claims.some(c=>c.role==='origin'));
        if (origin) inquiryTree.select(origin);
        const claim = origin?.claims.find(c=>c.evidence?.length);
        if (claim) await open(claim.evidence[0], claim.at);
        const originalOpened = !claim || document.querySelector('#original').textContent.length > 0;
        inquiryTree.fit();
        const rootRect = document.querySelector('.tree-node.root').getBoundingClientRect();
        const graphRect = document.querySelector('#graph').getBoundingClientRect();
        return { root: rootKey, seededEdges: seedEdges.length, displayedNodes: inquiryTree.model.visible().length,
          rootVisible: rootRect.top >= graphRect.top && rootRect.bottom <= graphRect.bottom,
          zoom: inquiryTree.zoom,
          originalOpened,
          manualFailures: [...inquiryTree.model.nodes.values()].filter(n=>n.error).map(n=>n.error),
          traceUnchanged: JSON.stringify(before)===JSON.stringify(after),
          gaps: inquiryTree.model.unclosed.length, report: inquiryTree.report.report_id,
          candidateEdges: [...document.querySelectorAll('.tree-edge.candidate')].length,
          reason: document.querySelector('#reason').textContent.slice(0,200) };
      })()`);
      assert(liveDiagnostic.root, 'real report has root');
      assert(liveDiagnostic.traceUnchanged, 'live manual expansion does not alter trace');
      assert(liveDiagnostic.originalOpened, 'real claim evidence opens at its original cutoff');
      assert(liveDiagnostic.rootVisible, 'root stays visible with the report path after expansion');
      assert(liveDiagnostic.zoom >= 0.62, 'original auto-fit has a 0.62 floor and a 1:1 control');
      assert.deepEqual(liveDiagnostic.manualFailures, [], 'live neighbors returned errors');
      assert.equal(await evaluate("document.querySelector('.tree-node.root').classList.contains('historical-problem')"), false);
      await evaluate("document.querySelector('#oneToOne').click()");
      liveDiagnostic.screenshotZoom = await evaluate("inquiryTree.zoom");
    } else {
    assert.equal(await evaluate("inquiryTree.model.root.coordinate.key"), report.target.file);
    assert.equal(await evaluate("document.querySelector('.tree-node.root').classList.contains('historical-problem')"), false);
    assert.equal(await evaluate("inquiryTree.model.root.children.length"), 1, "shared report prefix");
    assert.equal(await evaluate("getComputedStyle(document.querySelector('.tree-node')).height"), '30px', 'original compact height');
    assert.equal(await evaluate("getComputedStyle(document.querySelector('.tree-node')).width"), '196px', 'original compact width');
    assert.equal(await evaluate("getComputedStyle(document.querySelector('#graph')).backgroundImage"), 'none', 'original plain canvas');
    assert.equal(await evaluate("document.querySelector('.colhead').textContent.startsWith('ROOT')"), true);
    assert.equal(await evaluate("[...document.querySelectorAll('.tree-node')].every(n => n === document.querySelector('.tree-node.root') || +n.style.left.replace('px','') < +document.querySelector('.tree-node.root').style.left.replace('px',''))"), true, "root sits at right");
    assert.equal(await evaluate("getComputedStyle(document.querySelector('[data-edge=\"model:review\"]')).strokeDasharray !== 'none'"), true);
    assert.equal(await evaluate("document.querySelector('[data-edge=\"model:review\"]').dataset.strength"), "candidate");
    assert.equal(await evaluate("[...inquiryTree.model.nodes.values()].some(n=>n.coordinate.key==='unknown-author')"), false);
    assert.equal(await evaluate("document.querySelector('#gaps').textContent.includes('缺少历史连接')"), true);
    assert.equal(await evaluate("document.querySelector('.tree-node.agent').textContent.includes('模型查过')"), true);
    await evaluate("inquiryTree.select(inquiryTree.model.root)");
    assert.equal(await evaluate("document.querySelectorAll('[data-repair-anchor]').length"), 1, "repair evidence deduplicates across findings");
    assert.equal(await evaluate("document.querySelector('#reason').textContent.includes('目标修改依据 · 候选')"), true);
    assert.equal(await evaluate("[...inquiryTree.model.nodes.values()].some(n=>n.coordinate.key==='session:fixer')"), false, "repair anchor creates no automatic problem node");
    const initialTrace = JSON.stringify(traces);
    await evaluate("inquiryTree.expand(inquiryTree.model.root)");
    assert.equal(await evaluate("inquiryTree.model.root.children.length"), 3, "same-second different operation and repair candidate");
    assert.equal(await evaluate("inquiryTree.model.root.children[0].origins.has('report') && inquiryTree.model.root.children[0].origins.has('manual')"), true);
    await evaluate("inquiryTree.expand(inquiryTree.model.root.children[0])");
    assert.equal(await evaluate("inquiryTree.model.root.children[0].children.filter(n=>n.coordinate.key.includes('AudioSpec')).length"), 2, "microseconds preserved");
    assert.equal(JSON.stringify(traces), initialTrace, "manual calls leave model trace untouched");
    assert(!requests.some(q => q.op === "record_trace"), "no trace mutation request");
    await evaluate("inquiryTree.expand(inquiryTree.model.root,'downstream')");
    assert.equal(await evaluate("inquiryTree.model.rights.length"),1,'native reader goes to the right');
    assert.equal(await evaluate("inquiryTree.positions.get(inquiryTree.model.rights[0].id).x > inquiryTree.positions.get(inquiryTree.model.root.id).x"),true);
    assert.equal(await evaluate("document.querySelector('.colhead.down').textContent"),'下游 · 读者');
    await evaluate("document.querySelector('.tree-node.root').click()");
    assert.equal(await evaluate("inquiryTree.model.root.collapsed"),true,'clicking the node collapses its subtree');
    await evaluate("document.querySelector('.tree-node.root').click()");
    assert.equal(await evaluate("inquiryTree.model.root.collapsed"),false,'clicking again expands existing children');
    assert.equal(JSON.stringify(traces),initialTrace);
    await evaluate("document.querySelector('#findings').value='B'; document.querySelector('#findings').dispatchEvent(new Event('change'))");
    assert.equal(await evaluate("document.querySelector('#reason').textContent.includes('候选输入仍未认证因果')"), true, "switching findings refreshes node reasons");
    await evaluate("document.querySelector('#findings').value='A'; document.querySelector('#findings').dispatchEvent(new Event('change'))");
    assert.equal(await evaluate("document.querySelector('[data-edge=\"model:review\"]')===null"), true);
    assert.equal(await evaluate("document.querySelector('#findingText').textContent.includes('完整原因 A')"), true);
    await evaluate("inquiryTree.select([...inquiryTree.model.nodes.values()].find(n=>n.claims.some(c=>c.id==='A:origin')))");
    assert.equal(await evaluate("document.querySelector('#reason').textContent.includes('原稿原因与范围都必须保留')"), true);
    await evaluate("inquiryTree.expand([...inquiryTree.model.nodes.values()].find(n=>n.claims.some(c=>c.id==='A:origin')))");
    await evaluate("inquiryTree.select([...inquiryTree.model.nodes.values()].find(n=>n.row?.relation==='dispatch'))");
    assert.equal(await evaluate("document.querySelector('#reason').textContent.includes('身份来自稍后回执')"), true);
    assert.equal(await evaluate("document.querySelector('#reason').textContent.includes('身份尚未知')"), true);
    await evaluate("[...document.querySelectorAll('#reason button')].find(b=>b.textContent==='e-12345678').click()");
    await wait("document.querySelector('#original').textContent.includes('ORIGINAL EVIDENCE')");
    assert.equal(requests.at(-1).at, times.origin, "edge evidence keeps its source query cutoff");
    await evaluate("inquiryTree.select([...inquiryTree.model.nodes.values()].find(n=>n.claims.some(c=>c.id==='A:origin')))");
    await evaluate("[...document.querySelectorAll('#reason button')].find(b=>b.textContent==='e-abcdef12').click()");
    await wait("document.querySelector('#original').textContent.includes('ORIGINAL EVIDENCE')");
    assert.equal(requests.at(-1).at, times.root, "claim evidence uses original claim scope");
    await evaluate("document.querySelector('#rawRecord').closest('details').open=true");
    await wait("document.querySelector('#rawRecord').textContent==='FULL RAW RECORD'");
    await evaluate("inquiryTree.select(inquiryTree.model.root); [...document.querySelectorAll('#reason button')].find(b=>b.textContent==='查看原生差异').click()");
    await wait("document.querySelector('#records').textContent.includes('OLD_VALUE')");
    assert.equal(await evaluate("document.querySelector('#records').textContent.includes('NEW_VALUE')"), true);
    await evaluate("document.querySelector('#collapse').click()");
    assert.equal(await evaluate("inquiryTree.model.visible().length"), 1);
    await evaluate("document.querySelector('#restorePaths').click()");
    assert.equal(await evaluate("inquiryTree.model.visible().length>1"), true);
    const zoom = await evaluate("inquiryTree.zoom");
    await evaluate("document.querySelector('#zoomIn').click()");
    assert.equal(await evaluate("inquiryTree.zoom") > zoom, true);
    await evaluate("document.querySelector('#fit').click()");
    await evaluate("document.querySelector('#oneToOne').click()");
    assert.equal(await evaluate("inquiryTree.zoom"),1,'original 1:1 button');
    await evaluate("document.querySelector('#railtog').click()");
    assert.equal(await evaluate("document.querySelector('#rail').classList.contains('closed')"),true);
    await evaluate("document.querySelector('#railtog').click(); document.querySelector('#catalogFiles').click()");
    await wait("document.querySelector('[data-catalog-key]')!==null");
    await evaluate("document.querySelector('#kind').value='file'; document.querySelector('#key').value='/migration/harmony/AudioPlayer.ets'; document.querySelector('#at').value='2026-09-12T10:00:00.000003Z'; document.querySelector('#startTree').click()");
    await wait("inquiryTree.model.root.coordinate.at==='2026-09-12T10:00:00.000003Z' && inquiryTree.model.root.loaded");
    assert.equal(await evaluate("inquiryTree.report"), null);
    assert.equal(requests.at(-1).at, "2026-09-12T10:00:00.000003Z");
    assert.equal(requests.at(-1).report_id, undefined);
    await evaluate("reload()");
    assert.equal(await evaluate("document.querySelector('#at').value"), "2026-09-12T10:00:00.000003Z", "reload preserves chosen cutoff");
    await send("Page.navigate", { url: url.replace("?report=tree-fixture", "?probe=legacy-fixture") });
    await wait("document.querySelector('#status')?.textContent.includes('旧版报告未载入')");
    assert.equal(await evaluate("document.querySelector('#at').value"), times.root, "empty explorer defaults to latest indexed time");
    assert.equal(await evaluate("document.querySelector('#info').textContent.includes('Fixture project')"), true);
    assert.equal(await evaluate("inquiryTree.report"), null, "legacy probe is not silently loaded as inquiry report");
    await evaluate("document.querySelector('#load').click()");
    await wait("inquiryTree.report?.report_id==='tree-fixture'");
    await evaluate("document.querySelector('#findings').value='A'; document.querySelector('#findings').dispatchEvent(new Event('change')); inquiryTree.select([...inquiryTree.model.nodes.values()].find(n=>n.claims.some(c=>c.id==='A:origin')))");
    }
    assert.equal(errors.length, 0, errors.join("\n"));
    const screenshot = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(out, "inquiry-tree.png"), Buffer.from(screenshot.data, "base64"));
    const audit = { passed: true, url, errors, liveDiagnostic, queryCount: requests.length,
      checks: liveUrl ? ["real report root", "live upstream neighbors", "trace isolation", "node evidence", "no JavaScript errors"] :
        ["single renderer", "automatic/manual identity", "right root", "shared prefix", "candidate dash", "unclosed isolation",
        "microsecond and operation identity", "finding switch", "original scope", "native diff", "trace isolation", "new root cutoff", "zoom/collapse",
        "legacy link warning", "default cutoff preservation", "project label", "repair anchor evidence", "dispatch identity timing",
        "original compact geometry", "native right readers", "node click toggle", "catalog and rail", "1:1 zoom"],
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
