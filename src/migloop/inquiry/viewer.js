/* Human explorer on the original fixchain shell. Investigator controls stay out. */
(function () {
  "use strict";
  const config = window.INQUIRY_CONFIG || {},
    $ = (id) => document.getElementById(id);
  let overview = null,
    report = null,
    detailEpoch = 0,
    railEpoch = 0,
    navigationEpoch = 0,
    railTimer,
    timeScope = null,
    investigator = null;
  const short = (key) =>
    String(key || "")
      .replace(/\\/g, "/")
      .split("/")
      .pop();
  const actor = (key) =>
    String(key || "未知归属")
      .split(":")
      .pop()
      .replace(/-[0-9a-f]{16,}$/i, "");
  const when = (at) => (at ? at.slice(5, 19).replace("T", " ") : "时间未知");
  const coordinate = (n) => ({
    kind: n.kind,
    key: n.key,
    at: n.at,
    since: n.since || null,
  });
  const atom = (scope, extra = {}) => {
    const { kind, ...values } = coordinate(scope);
    return { op: kind, ...values, ...extra };
  };
  function el(tag, cls, text, parent) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    if (parent) parent.append(n);
    return n;
  }
  function button(text, parent, action, cls = "act") {
    const b = el("button", cls, text, parent);
    b.onclick = () => guard(action);
    return b;
  }
  async function api(route, data) {
    const response = await fetch((config.api_base || "") + route, {
      method: data === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json" },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
    const value = await response.json();
    if (!response.ok) throw Error(value.error || "读取失败");
    return value;
  }
  const query = (q) => api("/api/query", q);
  const view = (scope, name, extra = {}) =>
    api("/api/view", { ...coordinate(scope), view: name, ...extra });
  async function guard(fn) {
    try {
      return await fn();
    } catch (error) {
      const p = el(
        "p",
        "error",
        error.message,
        document.querySelector("dialog[open]") || $("side"),
      );
      p.scrollIntoView({ block: "nearest" });
    }
  }
  const tree = new InquiryEvidenceTree.InquiryTree({
    host: $("viewport"),
    api,
    onSelect: (n) => guard(() => showNode(n)),
    onChange: syncRoot,
  });
  window.inquiryTree = tree;
  function syncRoot() {
    if (!tree.model) return;
    const r = tree.model.root.coordinate;
    $("rootlbl").textContent =
      "从 " +
      (r.kind === "file" ? short(r.key) : actor(r.key)) +
      " @ " +
      when(r.at) +
      " 出发";
    $("rootlbl").title = r.key + "\n" + r.at;
  }
  function exitReport() {
    report = null;
    $("finding").hidden = true;
    $("unload").hidden = true;
    $("load").textContent = "载入调查";
  }
  async function openRoot(scope) {
    const epoch = ++navigationEpoch;
    const resolved = await view(scope, "history", { limit: 1 });
    if (epoch !== navigationEpoch) return;
    scope = resolved.scope;
    exitReport();
    ++detailEpoch;
    await tree.start(coordinate(scope));
    if (epoch !== navigationEpoch) return;
    syncRoot();
    try {
      const url = new URL(location.href);
      for (const name of ["report", "report_id", "probe"])
        url.searchParams.delete(name);
      url.hash = new URLSearchParams({
        kind: scope.kind,
        key: scope.key,
        at: scope.at,
        ...(scope.since ? { since: scope.since } : {}),
      }).toString();
      history.replaceState(null, "", url);
    } catch (_) {}
  }
  function section(title, parent, open = true) {
    const box = el("details", "sec", null, parent);
    box.open = open;
    el("summary", "", title, box);
    return box;
  }
  function originals(items, parent, scope) {
    const box = section("原始依据", parent, false);
    for (const item of items || [])
      button(item.source + ":" + item.line, box, async () => {
        const data = await query({
          op: "open",
          ref: item.ref,
          at: scope.at,
          pointer: "",
        });
        el("pre", "srcblock", data.text, box);
      });
  }
  async function showOperation(row, scope, host) {
    if (host.childNodes.length) {
      host.replaceChildren();
      return;
    }
    el("span", "empty-note", "读取原文…", host);
    const data = await view(scope, "operation", { id: row.id });
    host.replaceChildren();
    if (data.content != null) {
      el(
        "b",
        "",
        data.content_kind === "write_body"
          ? "这次写入的全文"
          : "这次读取返回的原文",
        host,
      );
      el("pre", "srcblock", data.content, host);
    }
    for (const change of data.changes || [])
      if (change.kind !== "snapshot_folded")
        el("pre", "diffblock", change.text, host);
    el("p", "empty-note", data.note, host);
    originals(data.originals, host, scope);
  }
  async function historyRows(scope, parent, category = "changes", offset = 0) {
    const data = await view(scope, "history", { category, offset, limit: 20 });
    if (!data.total)
      el(
        "div",
        "empty-note",
        category === "reads"
          ? "没有可确认的 Read 记录"
          : "此范围内没有可确认的写入记录",
        parent,
      );
    for (const row of data.rows) {
      const box = el(
        "div",
        "vrow" + (row.at === scope.at ? " anchor" : ""),
        null,
        parent,
      );
      box.dataset.operation = row.id;
      el("span", "vn", String(row.number), box);
      const middle = el("div", "", null, box),
        t = el("span", "t", when(row.at), middle);
      t.title = row.at + " · UTC";
      el(
        "span",
        "meta",
        row.label +
          " · " +
          (scope.kind === "file" ? actor(row.agent) : short(row.file)),
        middle,
      );
      const actions = el("div", "", null, box),
        contents = el("div", "original", null, box);
      button("以此为根", actions, () =>
        openRoot({ kind: scope.kind, key: scope.key, at: row.at }),
      );
      button(category === "reads" ? "原文" : "原文 / diff", actions, () =>
        showOperation(row, scope, contents),
      );
      if (scope.kind === "file" && row.agent)
        button(category === "reads" ? "读者" : "写者", actions, () =>
          openRoot({ kind: "agent", key: row.agent, at: row.at }),
        );
      if (scope.kind === "agent")
        button("文件", actions, () =>
          openRoot({ kind: "file", key: row.file, at: row.at }),
        );
    }
    if (data.next != null) {
      const more = button("继续展开", parent, async () => {
        more.remove();
        await historyRows(scope, parent, category, data.next);
      });
    }
    return data;
  }
  function lazy(title, parent, loader) {
    const box = section(title, parent, false);
    let loaded = false;
    box.ontoggle = () => {
      if (box.open && !loaded) {
        loaded = true;
        guard(() => loader(box));
      }
    };
    return box;
  }
  async function rawRows(scope, parent, viewName, terms = [], offset = 0) {
    const data = await query(
      atom(scope, {
        view: viewName,
        terms,
        ...(viewName === "calls" ? { include_reads: true } : {}),
        offset,
        limit: 20,
      }),
    );
    if (!data.rows.length)
      el("div", "empty-note", "此范围没有匹配记录", parent);
    for (const row of data.rows) {
      const box = el("div", "quote", null, parent);
      el("b", "", when(row.at), box);
      el("div", "", row.excerpt || row.summary || "", box);
      button("原文", box, async () => {
        const full = await query({
          op: "open",
          ref: row.ref || row.cite,
          at: scope.at,
          ...(scope.since ? { since: scope.since } : {}),
        });
        el("pre", "srcblock", full.text, box);
      });
    }
    if (data.next != null) {
      const more = button("继续展开", parent, async () => {
        more.remove();
        await rawRows(scope, parent, viewName, terms, data.next);
      });
    }
  }
  function showReasons(node, parent) {
    for (const claim of (node.claims || []).filter(
      (c) => !c.generated_context,
    )) {
      const box = el(
        "div",
        "quote " +
          (["origin", "propagated"].includes(claim.role) ? "cause" : ""),
        null,
        parent,
      );
      box.dataset.claim = claim.id;
      el(
        "b",
        "",
        {
          origin: "AI 判断 · 问题进入",
          propagated: "AI 判断 · 问题保留",
          context: "AI 判断 · 输入或背景",
          repaired: "AI 判断 · 修复",
          unknown: "AI 判断 · 尚未确定",
        }[claim.role] || "AI 判断",
        box,
      );
      el("div", "", claim.reason, box);
      const refs = section("依据", box, false);
      for (const ref of claim.evidence || [])
        button("查看原始记录", refs, async () => {
          const q = { op: "open", ref, at: claim.at };
          if (claim.since) q.since = claim.since;
          const data = await query(q);
          el("pre", "srcblock", data.text, refs);
        });
    }
    if (node.row?.source === "model_review") {
      const box = el("div", "quote", null, parent);
      el("b", "", "虚线 · 模型复核补充", box);
      el("div", "", node.row.claim, box);
      const refs = section("复核依据", box, false);
      for (const ref of node.row.evidence || [])
        button("原文", refs, async () => {
          const data = await query({
            op: "open",
            ref,
            at: node.parent?.coordinate.at || node.coordinate.at,
          });
          el("pre", "srcblock", data.text, refs);
        });
    }
  }
  async function showNode(node) {
    const epoch = ++detailEpoch,
      scope = coordinate(node.coordinate),
      side = $("side");
    side.replaceChildren();
    const head = el(
      "div",
      "head " + (scope.kind === "file" ? "file" : "gen"),
      null,
      side,
    );
    el("div", "tag", scope.kind === "file" ? "文件原子" : "AGENT 原子", head);
    el(
      "h3",
      "",
      scope.kind === "file" ? short(scope.key) : actor(scope.key),
      head,
    );
    el("div", "sub", scope.key, head);
    button("截至 " + when(scope.at) + " UTC", head, () => {
      timeScope = scope;
      $("timeName").textContent = scope.key;
      $("at").value = scope.at;
      $("timeDialog").showModal();
    });
    button("以此为根开树 →", head, () => openRoot(scope), "rootbtn");
    const body = el("div", "body", null, side);
    showReasons(node, body);
    if (node.error) el("p", "error", node.error, body);
    if (scope.kind === "file") {
      const changes = section("版本脊柱 · 已确认的写入时刻", body, true);
      await historyRows(scope, changes);
      if (epoch !== detailEpoch) return;
      lazy("已知时刻的读取原文", body, (box) =>
        historyRows(scope, box, "reads"),
      );
    } else {
      const inputs = section("已确认的读取", body, true);
      await historyRows(scope, inputs, "reads");
      if (epoch !== detailEpoch) return;
      lazy("产出时间线", body, (box) => historyRows(scope, box, "changes"));
      lazy("派发与任务", body, async (box) => {
        const relations = await query(
          atom(scope, { view: "relations", limit: 1 }),
        );
        for (const d of (relations.dispatches || []).filter(
          (d) => d.child === scope.key && d.strength === "confirmed",
        )) {
          button("派发自 " + actor(d.parent), box, () =>
            openRoot({ kind: "agent", key: d.parent, at: d.at }),
          );
          button("派发指令", box, async () => {
            const raw = await query({
              op: "open",
              ref: d.request,
              at: scope.at,
            });
            el("pre", "srcblock", raw.text, box);
          });
        }
        await rawRows(scope, box, "messages");
      });
    }
    lazy("相关调用与记录", body, (box) => rawRows(scope, box, "calls"));
    if (scope.kind === "agent")
      lazy("其它工具返回", body, (box) => rawRows(scope, box, "returns"));
    const search = section(
        scope.kind === "file" ? "片段来源 / 搜索历史" : "搜索历史",
        body,
        false,
      ),
      text = el("input", "", null, search);
    text.placeholder = "输入代码片段或关键词";
    const found = el("div", "", null, search);
    button("查找", search, async () => {
      found.replaceChildren();
      const terms = [text.value.trim()].filter(Boolean);
      if (!terms.length) return;
      if (scope.kind === "file") {
        const data = await query({
          op: "blame",
          key: scope.key,
          at: scope.at,
          ...(scope.since ? { since: scope.since } : {}),
          terms,
          limit: 20,
        });
        for (const row of data.rows || []) {
          const box = el("div", "quote", null, found);
          el("b", "", when(row.at) + " · " + actor(row.agent), box);
          for (const h of row.term_deltas || [])
            el(
              "pre",
              "diffblock",
              "OLD\n" +
                h.old_lines.join("\n") +
                "\nNEW\n" +
                h.new_lines.join("\n"),
              box,
            );
        }
        if (data.next != null)
          el(
            "div",
            "empty-note",
            "先列 20 条片段命中；下方原文记录可继续展开。",
            found,
          );
      }
      await rawRows(scope, found, "records", terms);
    });
  }
  function railSection(title, parent, closed = false) {
    const box = el("div", "rsec" + (closed ? " closed" : ""), null, parent),
      heading = el("div", "rsh", title, box);
    el("span", "chev", "▾", heading);
    heading.onclick = () => box.classList.toggle("closed");
    return el("div", "rlist", null, box);
  }
  function railItem(kind, key, parent) {
    const item = el("div", "ritem", null, parent),
      row = el("div", "rrow", null, item),
      label = el(
        "span",
        "lab mono",
        kind === "file" ? short(key) : actor(key),
        row,
      );
    label.title = key;
    el("span", "pill", kind === "file" ? "文件" : "agent", row);
    const times = el("div", "vers", null, item);
    let loaded = false;
    row.onclick = () =>
      guard(async () => {
        item.classList.toggle("open");
        if (loaded || !item.classList.contains("open")) return;
        loaded = true;
        const scope = { kind, key, at: overview.at };
        button("最新记录时刻 · 打开", times, () => openRoot(scope));
        const data = await view(scope, "history", {
          category: "changes",
          limit: 100,
        });
        for (const event of data.rows) {
          const line = el("div", "vline", null, times);
          el("span", "vn", String(event.number), line);
          const t = el("span", "t", when(event.at), line);
          t.title = event.at;
          line.onclick = () =>
            guard(() => openRoot({ kind, key, at: event.at }));
        }
        if (data.next != null)
          el("div", "rempty", "更多时刻可在右侧版本脊柱展开", times);
        if (!data.total)
          el("div", "rempty", "没有已确认写入；仍可打开历史记录", times);
      });
  }
  async function renderRail() {
    const epoch = ++railEpoch,
      term = $("q").value.trim(),
      lists = await Promise.all(
        ["file", "agent"].map((kind) =>
          query({ op: "catalog", kind, q: term, limit: 40 }),
        ),
      );
    if (epoch !== railEpoch) return;
    const body = $("railbody");
    body.replaceChildren();
    const saved = (overview.reports || []).filter(
      (r) => !term || (r.file || "").toLowerCase().includes(term.toLowerCase()),
    );
    if (saved.length) {
      const group = railSection("已有调查 (" + saved.length + ")", body);
      for (const r of saved) {
        const row = el("div", "ritem", null, group);
        const b = button(short(r.file), row, () => loadReport(r.id), "rrow");
        b.title = r.title;
      }
    }
    lists.forEach((data, index) => {
      const kind = index ? "agent" : "file",
        group = railSection(
          (index ? "agent" : "文件") + " (" + data.total + ")",
          body,
          index === 1 && !term,
        );
      data.rows.forEach((r) => railItem(kind, r.key, group));
      if (data.next != null) {
        const more = button("继续展开目录", group, async () => {
          const page = await query({
            op: "catalog",
            kind,
            q: term,
            offset: data.next,
            limit: 40,
          });
          data.next = page.next;
          page.rows.forEach((r) => railItem(kind, r.key, group));
          if (data.next == null) more.remove();
        });
      }
    });
  }
  function reportNotes() {
    const box = $("reportNotes");
    box.replaceChildren();
    if (!report) return;
    if (tree.model.unclosed.length) {
      const d = section(
        tree.model.unclosed.length + " 条节点结论尚未连到树上",
        box,
        false,
      );
      for (const p of tree.model.unclosed)
        el("p", "empty-note", p.node + " · " + p.diagnostic, d);
    }
    const d = section("本次调查的结论", box, false);
    for (const f of report.document.findings) {
      const q = el("div", "quote", null, d);
      el("b", "", f.title, q);
      el("div", "", f.reason, q);
    }
  }
  async function loadReport(id) {
    const epoch = ++navigationEpoch;
    const graph = await api("/api/report?id=" + encodeURIComponent(id));
    if (epoch !== navigationEpoch) return;
    report = graph;
    tree.loadReport(graph);
    $("finding").replaceChildren();
    el("option", "", "全部问题", $("finding")).value = "";
    for (const f of graph.document.findings)
      el("option", "", f.id + " · " + f.title, $("finding")).value = f.id;
    $("finding").hidden = false;
    $("unload").hidden = false;
    $("load").textContent = "已载入 · " + short(graph.target.file);
    const trace = await api(
      "/api/trace?session=" + encodeURIComponent(graph.trace_session),
    );
    if (epoch !== navigationEpoch) return;
    tree.markSeen(trace);
    tree.select(tree.model.root);
    syncRoot();
    reportNotes();
    $("reportsDialog").close();
    const url = new URL(location.href);
    for (const name of ["report_id", "probe"]) url.searchParams.delete(name);
    url.searchParams.set("report", id);
    url.hash = "";
    history.replaceState(null, "", url);
  }
  async function reportList() {
    const data = await api("/api/view", { view: "overview" });
    overview = data;
    const list = $("reportsList");
    list.replaceChildren();
    for (const r of data.reports) {
      const row = el("div", "report-row", null, list),
        label = el(
          "span",
          "",
          short(r.file) + " · " + r.count + " 项结论",
          row,
        );
      el("small", "", r.title, label);
      button("载入", row, () => loadReport(r.id));
    }
    if (!data.reports.length)
      el("p", "empty-note", "暂无调查结果，可以导入已有结果文件。", list);
    if (data.reports.length === data.report_limit)
      el(
        "p",
        "empty-note",
        "此处列出最近 " + data.report_limit + " 份结果。",
        list,
      );
    reportNotes();
    $("reportsDialog").showModal();
  }
  $("load").onclick = () => guard(reportList);
  $("closeReports").onclick = () => $("reportsDialog").close();
  $("importReport").onchange = async () => {
    const file = $("importReport").files[0];
    if (!file) return;
    $("reportError").textContent = "";
    try {
      const graph = await api("/api/report", { document: await file.text() });
      await loadReport(graph.report_id);
      overview = await api("/api/view", { view: "overview" });
      await renderRail();
    } catch (error) {
      $("reportError").textContent = error.message;
    }
  };
  $("finding").onchange = () => {
    tree.setFinding($("finding").value);
    tree.select(
      [...tree.model.nodes.values()].find((n) =>
        n.claims.some((c) => c.role === "origin"),
      ) || tree.model.root,
    );
    reportNotes();
  };
  $("unload").onclick = () => guard(() => openRoot(tree.model.root.coordinate));
  $("railtog").onclick = () => $("rail").classList.toggle("closed");
  $("q").oninput = () => {
    clearTimeout(railTimer);
    ++railEpoch;
    railTimer = setTimeout(() => guard(renderRail), 250);
  };
  $("zo").onclick = () => tree.setZoom(tree.zoom * 0.8);
  $("zi").onclick = () => tree.setZoom(tree.zoom * 1.2);
  $("zf").onclick = () => tree.fit(false);
  $("z1").onclick = () => {
    tree.setZoom(1);
    if (tree.model) tree.focus(tree.model.root);
  };
  $("closeTime").onclick = () => $("timeDialog").close();
  $("applyTime").onclick = () =>
    guard(async () => {
      await openRoot({ ...timeScope, at: $("at").value });
      $("timeDialog").close();
    });
  // The host owns model choice and job lifecycle; only a returned report ID is
  // accepted, and its graph is rechecked by the normal report endpoint.
  window.migloopViewer = {
    loadReport,
    configure({ investigate } = {}) {
      investigator = typeof investigate === "function" ? investigate : null;
      $("askai").disabled = !investigator;
      $("askai").title = investigator
        ? "调查当前文件"
        : "尚未连接 AI 调查任务服务";
    },
  };
  $("askai").onclick = () =>
    guard(async () => {
      if (!investigator || tree.model?.root.coordinate.kind !== "file")
        throw Error("先选择被修文件，并连接 server 的 AI 调查服务。");
      const target = {
        file: tree.model.root.coordinate.key,
        at: tree.model.root.coordinate.at,
      };
      $("askai").disabled = true;
      $("askai").textContent = "调查中…";
      try {
        const id = await investigator(target);
        await loadReport(id);
      } finally {
        $("askai").disabled = !investigator;
        $("askai").textContent = "AI 帮我查";
      }
    });
  new ResizeObserver(() => {
    if (tree.model) tree.render();
  }).observe($("viewport"));
  guard(async () => {
    overview = await api("/api/view", { view: "overview" });
    $("counts").textContent =
      (config.project ? config.project + " · " : "") +
      "目录：" +
      overview.files +
      " 个文件 · " +
      overview.agents +
      " 个 agent";
    await renderRail();
    const p = new URLSearchParams(location.search),
      h = new URLSearchParams(location.hash.slice(1)),
      id =
        p.get("report") ||
        p.get("report_id") ||
        (!(h.get("key") || h.get("file")) && config.report_id);
    if (id) await loadReport(id);
    else if (h.get("key") || h.get("file"))
      await openRoot({
        kind: h.get("kind") || "file",
        key: h.get("key") || h.get("file"),
        at: h.get("at") || overview.at,
        since: h.get("since") || null,
      });
    else tree.render();
    if (p.has("probe")) {
      await reportList();
      $("reportError").textContent =
        "旧版调查格式尚未载入；请导入或选择当前结果。";
    }
  });
})();
