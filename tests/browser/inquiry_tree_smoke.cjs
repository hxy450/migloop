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
  document: { schema: "inquiry/1", target: { file: "/migration/harmony/AudioPlayer.ets", at: times.root },
    summary: {generation:"文件级生成总结：输入整理存在待核缺口。<img src=x onerror=alert(1)>",repair:"文件级修复总结：后续修改了输出，运行效果未证实。",unknown:["文件级未查明"],findings:["A","B","C"]},
    recommendations:[{target:"规格交接",action:"保留关键属性和来源",reason:"避免属性丢失而不是简单多查几层",validation:"比较同题输出并核对应属性",findings:["A"]}],
    findings: [
      { id: "A", title: "规格输入中的问题", reason: "完整原因 A", unknown: ["尚缺运行验证"], hypothesis: "待核机制 A", recommendation: "建议 A", boundary:{status:"unresolved",nodes:[],reason:"停止依据仍未查清，不能把局部写者当首因"} },
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
const repairs = [report.target.file, "/migration/harmony/SettingsPage.ets", "/migration/harmony/GuidePage.ets"];
const secondReport = {...report, report_id: "settings-report", target: {...report.target, file: repairs[1]},
  document: {...report.document, target: {...report.document.target, file: repairs[1]}},
  tree: {...report.tree, root: coordinate("file", repairs[1], times.root)}};
const summaries = [report, secondReport].map(r=>({id:r.report_id,file:r.target.file,at:times.root,count:3,title:"测试调查"}));
let noReports = false;
const requests = [];
let retryFailures=0;
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
          .replace("__INQUIRY_CONFIG__", JSON.stringify({ api_base: base, project: "Fixture project", fixchain_data_url: base + "/repairs" }))
          .replaceAll("__INQUIRY_ASSET_BASE__", base);
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); return res.end(page);
      }
      if (["/tree.js", "/viewer.js"].some(asset => url.pathname === base + asset)) {
        res.writeHead(200, { "Content-Type": "text/javascript; charset=utf-8" });
        return res.end(fs.readFileSync(path.join(root, "src/migloop/inquiry", path.basename(url.pathname))));
      }
      if (url.pathname === "/favicon.ico") { res.writeHead(204); return res.end(); }
      let data;
      if (url.pathname === base + "/repairs") data = {chains: repairs.map(file=>({file_abs:file}))};
      else if (url.pathname === base + "/api/info") data = { sources: 3, records: 128, latest_at: times.root, reports: [{ id: report.report_id }] };
      else if (url.pathname === base + "/api/report") {
        if(url.searchParams.get("id")==="slow")await sleep(150);
        data = url.searchParams.get("id")==="settings-report" ? secondReport : report;
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
        if(q.view==="catalog") data={at:times.root,files:[{path:report.target.file,n_events:2},{path:input.node.key,n_events:1}],agents:[{id:writer.node.key,label:"generator-worker",session:"session",parent:origin.node.key,n_events:1},{id:origin.node.key,label:"spec-author",session:"session",parent:null,n_events:1}]};
        else if(q.view==="overview") data={at:times.root,files:2,agents:3,report_limit:100,reports:noReports?[]:summaries.slice(0,1),reports_total:noReports?0:2,reports_next:noReports?null:1};
        else if(q.view==="reports") data={rows:summaries.slice(q.offset),total:2,next:null};
        else if(q.view==="history") {const rows=q.category==="all"?[...writes,...reads]:q.category==="reads"?reads:writes;data={scope,rows,total:rows.length,next:null,changes:writes.length,reads:reads.length};}
        else if(q.view==="operation") data={scope,id:q.id,at:q.id==="w1"?times.writer:times.root,content:q.id==="w1"?"WHOLE WRITE":q.id==="read"?"2\tPARTIAL READ":null,
          content_kind:q.id==="w1"?"write_body":q.id==="read"?"read_observation":null,
          changes:q.id==="w2"?[{text:"-OLD_VALUE\n+NEW_VALUE",kind:"edit"}]:[],originals:[original],note:"实际记录；可能只有片段，不推演完整文件"};
        else throw Error("Unexpected view "+q.view);
      }
      else if (url.pathname === base + "/api/query") {
        let body = ""; for await (const chunk of req) body += chunk;
        const q = JSON.parse(body); requests.push(q);
        if(q.include_reads && q.view!=="calls")throw Error("include_reads only belongs to calls");
        if (q.view === "neighbors") {
          let rows = [];
          if (q.key === report.target.file) rows = [writer, { ...writer, id: "native:w2" }, repair];
          if (q.key === writer.node.key) rows = [input, {...candidate,id:"native:guess",source:"indexed"}, later,
            row("native:r-empty","read",coordinate("file","/migration/specs/External.md",times.read)),
            row("native:r-retry","read",coordinate("file","/migration/specs/Retry.md",times.read))];
          if(q.key==="/migration/specs/Retry.md") {
            if(retryFailures++===0){res.writeHead(503,{"Content-Type":"application/json"});return res.end(JSON.stringify({error:"fixture temporary failure"}));}
            rows=[origin];
          }
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
      try {
        const lines = fs.readFileSync(active, "utf8").trim().split(/\r?\n/);
        if (/^\d+$/.test(lines[0]) && lines[1]?.startsWith("/devtools/")) { port = lines[0]; break; }
      } catch (error) {
        // On Windows Chrome can briefly lock the file while publishing it.
        if (!["ENOENT", "EBUSY", "EPERM"].includes(error.code)) throw error;
      }
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
    if(!liveUrl) {
      const migrationUrl=url.split("?")[0];
      noReports=true;
      await send("Page.navigate", {url:migrationUrl});
      await wait("!document.querySelector('#wrap').hidden && document.querySelectorAll('#repair-entries .ritem').length===3");
      assert.equal(await evaluate("document.querySelector('#attributions').textContent.includes('暂无归因结果')"),true);
      assert.equal(await evaluate("document.querySelectorAll('.attribution-load').length"),0);
      noReports=false;
      await send("Page.navigate", {url:migrationUrl});
      await wait("document.querySelectorAll('.attribution-load').length===2 && !document.querySelector('#wrap').hidden");
      assert.equal(await evaluate("document.querySelector('#attributions').nextElementSibling.id"),"repair-entries");
      assert.equal(await evaluate("document.querySelectorAll('#chips #load').length"),0);
      const repairText=await evaluate("document.querySelector('#repair-entries').textContent");
      await evaluate("document.querySelector('[data-report-id=\"settings-report\"] button').click()");
      await wait("migloopViewer.report?.report_id==='settings-report'");
      assert.equal(await evaluate("migloopViewer.tree.byId[migloopViewer.tree.root].scope.key"),repairs[1]);
      assert.equal(await evaluate("document.querySelector('#repair-entries').textContent"),repairText);
      await evaluate("document.querySelector('[data-report-id=\"tree-fixture\"] button').click()");
      await wait("migloopViewer.report?.report_id==='tree-fixture'");
      assert.equal(await evaluate("document.querySelector('#repair-entries').textContent"),repairText);
      assert.equal(await evaluate("document.querySelector('[data-report-id=\"tree-fixture\"] button').textContent"),"已载入");
    } else {
      await send("Page.navigate", { url });
      if(!new URL(url).searchParams.has("report") && !new URL(url).searchParams.has("report_id")) {
        await wait("!document.querySelector('#wrap').hidden && document.querySelector('.attribution-load')");
        const migrationShot=await send("Page.captureScreenshot", {format:"png"});
        fs.writeFileSync(path.join(out,"migration-before-load.png"),Buffer.from(migrationShot.data,"base64"));
        const entries=await evaluate("[...document.querySelectorAll('#repair-entries .ritem .lab')].map(n=>n.textContent)");
        assert(entries.length>0,"Real migration must have repaired files independent of its cards");
        const ids=await evaluate("[...document.querySelectorAll('.attribution-row')].map(n=>n.dataset.reportId)");
        for(const id of ids) {
          await evaluate("document.querySelector('[data-report-id=\""+id+"\"] button').click()");
          await wait("migloopViewer.report?.report_id==="+JSON.stringify(id));
          assert.deepEqual(await evaluate("[...document.querySelectorAll('#repair-entries .ritem .lab')].map(n=>n.textContent)"),entries);
          assert.equal(await evaluate("Object.values(migloopViewer.tree.byId).filter(n=>n.row?.strength==='candidate'&&n.row.source!=='model_review').length"),0);
        }
        await evaluate("document.querySelector('[data-report-id=\""+ids[0]+"\"] button').click()");
        await wait("migloopViewer.report?.report_id==="+JSON.stringify(ids[0]));
        fs.writeFileSync(path.join(out,"migration-audit.json"),JSON.stringify({repairedFiles:entries,reportIds:ids,loadedAll:true},null,2));
      }
    }
    await wait(process.env.INQUIRY_CARD_ONLY==="1" ? "window.migloopViewer?.tree && migloopViewer.report" : "window.migloopViewer?.tree && document.querySelector('#side .vrow')");
    let liveDiagnostic = null;
    const rootNode="migloopViewer.tree.byId[migloopViewer.tree.root]";
    if(liveUrl) {
      const initialShot = await send("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(path.join(out, "loaded-report.png"), Buffer.from(initialShot.data, "base64"));
      const problem = await evaluate("Object.values(migloopViewer.tree.byId).find(n=>n.claims.some(c=>c.role==='origin'))?.tid");
      if(problem) {
        await evaluate("migloopViewer.select("+JSON.stringify(problem)+")");
        await wait("document.querySelector('#side .quote')?.textContent.includes('模型判断')");
        const reasonShot = await send("Page.captureScreenshot", { format: "png" });
        fs.writeFileSync(path.join(out, "loaded-node-reason.png"), Buffer.from(reasonShot.data, "base64"));
      }
      if(process.env.INQUIRY_CARD_ONLY==="1") {
        await evaluate("document.querySelector('#load').click()");
        await wait("document.querySelector('#reportsDialog').open");
        await evaluate("document.querySelectorAll('#reportNotes details').forEach(n=>n.open=true);document.querySelectorAll('#reportNotes .quote .more').forEach(n=>n.click())");
        const cardDiagnostic=await evaluate("(()=>{const r=migloopViewer.report,t=migloopViewer.tree,text=document.querySelector('#reportNotes').textContent;return {report_id:r.report_id,source_sha256:r.source_sha256,nodes:Object.values(t.byId).length,seedEdges:Object.values(t.byId).filter(n=>n.row).length,unclosed:migloopViewer.hiddenPaths.length,recommendationsVisible:r.document.findings.filter(f=>typeof f.recommendation==='string'&&f.recommendation).every(f=>text.includes(f.recommendation)),reasonsVisible:r.document.findings.every(f=>text.includes(f.reason)),ordinaryCandidates:Object.values(t.byId).filter(n=>n.row?.strength==='candidate'&&n.row.source!=='model_review').length};})()");
        assert(cardDiagnostic.recommendationsVisible);assert(cardDiagnostic.reasonsVisible);
        assert.equal(cardDiagnostic.ordinaryCandidates,0);assert.equal(errors.length,0,errors.join("\n"));
        await evaluate("document.querySelectorAll('#reportNotes details').forEach(n=>n.open=true)");
        const cardShot=await send("Page.captureScreenshot",{format:"png"});
        fs.writeFileSync(path.join(out,"case-card-details.png"),Buffer.from(cardShot.data,"base64"));
        const audit={passed:true,url,errors,cardDiagnostic,checks:["saved report loaded by original tree UI","node claims inspectable","cause and recommendation text retained","ordinary candidates hidden","no JavaScript errors"]};
        fs.writeFileSync(path.join(out,"audit.json"),JSON.stringify(audit,null,2));console.log(JSON.stringify(audit));
        await send("Browser.close").catch(()=>{});return;
      }
      liveDiagnostic=await evaluate("(async()=>{const t=migloopViewer.tree,getTrace=()=>fetch((INQUIRY_CONFIG.api_base||'')+'/api/trace?session='+encodeURIComponent(migloopViewer.report.trace_session)).then(r=>r.json());const before=await getTrace(),seedEdges=Object.values(t.byId).filter(n=>n.row).length;await migloopViewer.expand(t.root);const first=t.byId[t.root].children.map(id=>t.byId[id]).find(n=>n.kind==='agent');if(first)await migloopViewer.expand(first.tid);const after=await getTrace();return {seedEdges,nodes:Object.values(t.byId).length,gaps:migloopViewer.hiddenPaths.length,traceUnchanged:JSON.stringify(before)===JSON.stringify(after),ordinaryCandidates:Object.values(t.byId).filter(n=>n.row?.strength==='candidate'&&n.row.source!=='model_review').length,errors:Object.values(t.byId).filter(n=>n.error).map(n=>n.error)};})()");
      assert(liveDiagnostic.traceUnchanged);assert.equal(liveDiagnostic.ordinaryCandidates,0);assert.deepEqual(liveDiagnostic.errors,[]);
      await evaluate("migloopViewer.select(migloopViewer.tree.root)");
      await wait("document.querySelector('#side .vrow')");
      await evaluate("[...document.querySelectorAll('#side .vrow .act .lnk')].find(n=>n.textContent==='原文').click()");
      await wait("document.querySelector('#side .srcblock .ln') || [...document.querySelectorAll('#side .sec')].some(n=>n.firstChild?.textContent==='原始调用与回执'&&n.querySelector('.lnk'))");
      if(!await evaluate("Boolean(document.querySelector('#side .srcblock .ln'))")) {
        assert.equal(await evaluate("document.querySelector('#side').textContent.includes('完整内容未知')"),true);
        await evaluate("[...document.querySelectorAll('#side .sec')].find(n=>n.firstChild?.textContent==='原始调用与回执').querySelector('.lnk').click()");
        await wait("[...document.querySelectorAll('#side .sec')].find(n=>n.firstChild?.textContent==='原始调用与回执').querySelector('pre')?.textContent.length>20");
      }
      assert.equal(await evaluate("document.querySelectorAll('#side .error').length"),0);
      await send("Page.navigate",{url:liveUrl.split('?')[0]+"#file=MemberCenterPage.ets"});
      await wait("migloopViewer.tree?.byId[migloopViewer.tree.root]?.scope.key.endsWith('/MemberCenterPage.ets') && !migloopViewer.tree.byId[migloopViewer.tree.root].busy && document.querySelector('#side .vrow')");
      liveDiagnostic.manualEntryWorks=await evaluate("migloopViewer.report===null && migloopViewer.tree.byId[migloopViewer.tree.root].children.length>1");
      assert(liveDiagnostic.manualEntryWorks,"old file hash opens a real manual tree");
      await evaluate("document.querySelector('#q').value='GuidePage.ets';document.querySelector('#q').dispatchEvent(new Event('input'));document.querySelector('#railbody .ritem .rrow').click()");
      await wait("document.querySelector('#railbody .vers .vline')");
      await evaluate("document.querySelector('#railbody .vers .vline').click()");
      await wait("migloopViewer.tree?.byId[migloopViewer.tree.root]?.scope.key.endsWith('/GuidePage.ets') && !migloopViewer.tree.byId[migloopViewer.tree.root].busy");
      const guideWriter=await evaluate("Object.values(migloopViewer.tree.byId).find(n=>n.aid?.includes(':aconv-guide-')).tid");
      await evaluate("document.querySelector('[data-tid=\""+guideWriter+"\"]').click()");
      await wait("Object.values(migloopViewer.tree.byId).some(n=>n.path?.endsWith('/resource-mapping.md'))");
      const guideInput=await evaluate("Object.values(migloopViewer.tree.byId).find(n=>n.path?.endsWith('/resource-mapping.md')).tid");
      await evaluate("document.querySelector('[data-tid=\""+guideInput+"\"]').click()");
      await wait("document.querySelector('.expansion-note')?.textContent.includes('未找到已确认的写者') && document.querySelector('#side .srcblock .ln')");
      liveDiagnostic.guideInput={
        terminal:await evaluate("document.querySelector('[data-tid=\""+guideInput+"\"] .chev').textContent"),
        originalVisible:await evaluate("document.querySelector('#side .srcblock').textContent.length>0"),
        fakeWriters:await evaluate("(migloopViewer.tree.byId['"+guideInput+"'].children||[]).length")};
      assert.equal(liveDiagnostic.guideInput.terminal,"·");assert(liveDiagnostic.guideInput.originalVisible);assert.equal(liveDiagnostic.guideInput.fakeWriters,0);
      await wait("document.querySelector('#railbody .vers .vline')");
      assert.equal(await evaluate("document.querySelector('#railbody .vers').textContent.includes('读取原文')"),false);
      await evaluate("document.querySelector('#zf').click()");
    } else {
      assert.equal(await evaluate(rootNode+".scope.key"),report.target.file);
      assert.equal(await evaluate("getComputedStyle(document.querySelector('#canvas .node')).height"),"30px");
      assert.equal(await evaluate("getComputedStyle(document.querySelector('#canvas .node')).width"),"196px");
      assert.equal(await evaluate("document.querySelector('#viewport')"),null,"original canvas");
      assert.equal(await evaluate("document.querySelector('#askai')"),null,"only load added");
      assert.equal(await evaluate("getComputedStyle(document.querySelector('[data-edge=\"model:review\"]')).strokeDasharray!=='none'"),true);
      const writerId=await evaluate(rootNode+".children[0]");
      await evaluate("document.querySelector('[data-tid=\""+writerId+"\"]').dispatchEvent(new MouseEvent('mouseenter'))");
      assert.equal(await evaluate("document.querySelectorAll('.wire.on').length>0"),true,"hover highlights incident edges");
      await evaluate("document.querySelector('[data-tid=\""+writerId+"\"]').dispatchEvent(new MouseEvent('mouseleave'))");
      assert.equal(await evaluate("document.querySelectorAll('.wire.on').length"),0);
      await evaluate("[...document.querySelectorAll('#side .vrow .act .lnk')].find(n=>n.textContent==='原文').click()");
      await wait("document.querySelector('#side .srcblock')?.textContent.includes('WHOLE WRITE')");
      await evaluate("[...document.querySelectorAll('[data-operation=\"w2\"] .act .lnk')].find(n=>n.textContent==='diff').click()");
      await wait("document.querySelector('.diffblock .dl-add')?.textContent.includes('NEW_VALUE')");
      assert.equal(await evaluate("document.querySelector('.diffblock .dl-del').textContent"),"-OLD_VALUE");
      await evaluate("[...document.querySelectorAll('#side .foldable>b')].find(n=>n.textContent.includes('读取观察')).click()");
      await wait("document.querySelector('[data-operation=\"read\"]')");
      await evaluate("document.querySelector('[data-operation=\"read\"] .act .lnk').click()");
      await wait("document.querySelector('#side .srcblock')?.textContent.includes('PARTIAL READ')");
      assert.equal(await evaluate("document.querySelector('#side').textContent.includes('可能是片段')"),true);
      await evaluate("migloopViewer.expand(migloopViewer.tree.root)");
      assert.equal(await evaluate(rootNode+".children.filter(id=>migloopViewer.tree.byId[id].row).length"),1,"prototype groups repeated writes by one writer");
      assert.equal(await evaluate(rootNode+".children.map(id=>migloopViewer.tree.byId[id]).find(n=>n.groupRows?.length===2).groupRows.length"),2,"grouping retains both original event IDs");
      await evaluate("migloopViewer.expand('"+writerId+"')");
      assert.equal(await evaluate("migloopViewer.tree.byId['"+writerId+"'].children.map(id=>migloopViewer.tree.byId[id]).filter(n=>n.scope?.key.includes('AudioSpec')).length"),2);
      await evaluate("migloopViewer.expand(migloopViewer.tree.byId['"+writerId+"'].children[0])");
      assert(requests.some(q=>q.key===input.node.key&&q.offset===1),"hidden-only page continues");
      await evaluate("migloopViewer.expand(migloopViewer.tree.root,'downstream')");
      assert.equal(await evaluate("migloopViewer.tree.rights.length"),1);
      assert.equal(await evaluate("Object.values(migloopViewer.tree.byId).some(n=>n.row?.id==='native:guess')"),false);
      const initial=JSON.stringify(traces);
      await evaluate("document.querySelector('#load').click()");
      await wait("document.querySelector('#reportsDialog').open");
      assert.equal(await evaluate("document.querySelector('#card-summary').textContent.includes('文件级生成总结')"),true);
      assert.equal(await evaluate("document.querySelector('#card-summary').textContent.includes('文件级修复总结')"),true);
      assert.equal(await evaluate("document.querySelector('#card-summary img')"),null,"model prose is text, never executable HTML");
      assert.equal(await evaluate("document.querySelector('#card-recommendations').textContent.includes('比较同题输出并核对应属性')"),true);
      assert.equal(await evaluate("document.querySelector('#reportNotes').textContent.includes('停止依据仍未查清')"),true);
      assert.equal(await evaluate("document.querySelector('#reportNotes').textContent.includes('尚未接入树')"),true);
      for(const text of ["尚缺运行验证","待核机制 A","建议 A","报告保留的未知事项","不是机检认证"])
        assert.equal(await evaluate("document.querySelector('#reportNotes').textContent.includes("+JSON.stringify(text)+")"),true);
      await evaluate("document.querySelector('#card-recommendations .lnk').click()");
      await wait("!document.querySelector('#reportsDialog').open");
      assert.equal(await evaluate("document.querySelector('#finding').value"),"A","recommendation returns to its actual finding, not a fabricated edge");
      assert.equal(await evaluate("document.querySelector('[data-edge=\"model:review\"]')"),null);
      await evaluate("migloopViewer.select(Object.values(migloopViewer.tree.byId).find(n=>n.claims.some(c=>c.id==='A:origin')).tid)");
      await wait("document.querySelector('#side').textContent.includes('原稿原因与范围都必须保留')");
      await evaluate("[...document.querySelectorAll('#side .quote .foldable>b')].find(n=>n.textContent.includes('原始依据')).click()");
      await wait("document.querySelector('#side .quote .foldable .lnk')");
      await evaluate("document.querySelector('#side .quote .foldable .lnk').click()");
      await wait("document.querySelector('#side .quote pre')?.textContent.includes('ORIGINAL EVIDENCE')");
      assert.equal(requests.at(-1).at,times.root);assert.equal(requests.at(-1).since,times.origin);
      await evaluate("migloopViewer.select(migloopViewer.tree.root);document.querySelector('#side .tag').click()");
      await wait("document.querySelector('#timeDialog').open");
      assert.equal(await evaluate("document.querySelector('#at').value"),times.root);
      await evaluate("document.querySelector('#at').value='2026-09-12T10:00:00.000003Z';document.querySelector('#applyTime').click()");
      await wait(rootNode+".scope.at==='2026-09-12T10:00:00.000003Z'&&!document.querySelector('#timeDialog').open");
      assert.equal(await evaluate("migloopViewer.report"),null);
      assert.equal(await evaluate("new URLSearchParams(location.search).has('report')"),false);
      await send("Page.reload");
      await wait("migloopViewer.tree?.byId[migloopViewer.tree.root]?.scope.at==='2026-09-12T10:00:00.000003Z' && !migloopViewer.tree.byId[migloopViewer.tree.root].busy");
      await evaluate("document.querySelector('#z1').click()");
      assert.equal(await evaluate("migloopViewer.zoom"),1);
      await evaluate("document.querySelector('#graph').dispatchEvent(new WheelEvent('wheel',{ctrlKey:true,deltaY:-1,cancelable:true}))");
      assert(await evaluate("migloopViewer.zoom>1"));
      await evaluate("document.querySelector('#railtog').click()");
      assert.equal(await evaluate("document.querySelector('#rail').classList.contains('closed')"),true);
      await evaluate("document.querySelector('#railtog').click()");
      assert.equal(await evaluate("document.querySelectorAll('#railbody .rkind').length"),2,"grouped file catalog");
      await evaluate("document.querySelector('#q').value='AudioPlayer';document.querySelector('#q').dispatchEvent(new Event('input'));document.querySelector('#railbody .ritem .rrow').click()");
      await wait("document.querySelector('#railbody .vline')");
      assert.equal(await evaluate("document.querySelector('#railbody .vers').textContent.includes('读取原文')"),false,"left entry lists writes only; read observations remain in the drawer");
      assert.equal(JSON.stringify(traces),initial,"manual UI leaves trace alone");
      assert(!requests.some(q=>q.op==="record_trace"));
      const race=await evaluate("(async()=>{const slow=migloopViewer.loadReport('slow');await migloopViewer.loadReport('tree-fixture');await slow;return new URLSearchParams(location.search).get('report')})()");
      assert.equal(race,"tree-fixture");
      await evaluate("migloopViewer.expand(migloopViewer.tree.byId[migloopViewer.tree.root].children[0])");
      const emptyId=await evaluate("Object.values(migloopViewer.tree.byId).find(n=>n.scope?.key==='/migration/specs/External.md').tid");
      await evaluate("document.querySelector('[data-tid=\""+emptyId+"\"]').click()");
      await wait("document.querySelector('.expansion-note')?.textContent.includes('未找到已确认的写者')");
      assert.equal(await evaluate("document.querySelector('[data-tid=\""+emptyId+"\"] .chev').textContent"),"·","empty upstream is visibly terminal, not a fake expand arrow");
      const emptyQueries=requests.filter(q=>q.key==='/migration/specs/External.md'&&q.view==='neighbors').length;
      await evaluate("document.querySelector('[data-tid=\""+emptyId+"\"]').click()");
      assert.equal(requests.filter(q=>q.key==='/migration/specs/External.md'&&q.view==='neighbors').length,emptyQueries,"known empty node stays inspectable without refetch");
      const retryId=await evaluate("Object.values(migloopViewer.tree.byId).find(n=>n.scope?.key==='/migration/specs/Retry.md').tid");
      await evaluate("document.querySelector('[data-tid=\""+retryId+"\"]').click()");
      await wait("document.querySelector('.expansion-note')?.textContent.includes('上游查询失败')");
      assert.equal(await evaluate("document.querySelector('[data-tid=\""+retryId+"\"] .chev').textContent"),"!");
      await evaluate("document.querySelector('.expansion-note .lnk').click()");
      await wait("migloopViewer.tree.byId['"+retryId+"'].loaded && !migloopViewer.tree.byId['"+retryId+"'].error && migloopViewer.tree.byId['"+retryId+"'].children.length===1");
      assert.equal(await evaluate("document.querySelector('.expansion-note').hidden"),true,"successful retry clears failure instead of claiming no writer");
      await evaluate("document.querySelector('#q').value='';document.querySelector('#q').dispatchEvent(new Event('input'));document.querySelector('#zf').click()");
    }
    assert.equal(errors.length, 0, errors.join("\n"));
    const screenshot = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(out, "inquiry-tree.png"), Buffer.from(screenshot.data, "base64"));
    const audit = { passed: true, url, errors, liveDiagnostic, queryCount: requests.length,
      checks: ["migration-first report loading", "repair catalog independent of reports", "report list pagination", "load buttons above all repaired files", "original compact shell", "single tree for saved and manual exploration", "ordinary candidates hidden",
        "model-review-only dashed edges", "write text and edit delta", "read observation expansion",
        "trace isolation", "precise cutoff", "load dialog", "only load control", "original hover highlight", "colored inline diffs", "original grouped catalog", "Ctrl-wheel zoom", "write-only entry timeline", "empty upstream remains inspectable", "no JavaScript errors"],
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
