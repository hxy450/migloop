// Dedicated browser only; source data and prior experiment runs are untouched.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const child = require("node:child_process");
const url = process.argv[2];
const out = process.argv[3];
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
    await wait('document.querySelectorAll("#graph .node").length === 3');
    assert.equal(
      await evaluate(
        'document.querySelectorAll("#graph path[marker-end]").length',
      ),
      2,
    );
    const initial = await evaluate("JSON.stringify({graph,trace})");
    await evaluate(
      'document.querySelectorAll("#graph .node")[1].dispatchEvent(new MouseEvent("click", {bubbles:true}))',
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
