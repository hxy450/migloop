/* The report and manual explorer share this temporal evidence tree.
 * Coordinates remain lossless strings: Date rounds microseconds.
 * A row is a historical upstream -> downstream edge, not a click direction.
 */
(function (global) {
  "use strict";
  const scopeIdentity = n => JSON.stringify([n.kind, n.key, n.at, n.since ?? null]);
  const validCoordinate = n => n && ["file", "agent"].includes(n.kind) &&
    typeof n.key === "string" && n.key.length && typeof n.at === "string" && n.at.length;
  class EvidenceTreeModel {
    constructor(root) {
      if (!validCoordinate(root)) throw Error("开树需要文件或 Agent 的完整身份及截止时间。");
      this.nodes = new Map();
      this.sequence = 0;
      this.root = this.makeNode(root, null, null, "root");
      this.unclosed = [];
    }
    makeNode(coordinate, parent, row, origin) {
      const node = {
        id: "tree-" + this.sequence++, coordinate: { ...coordinate },
        parent, row, children: [], claims: [], anchors: [], repairAnchors: [], origins: new Set([origin]),
        collapsed: false, loaded: false, loading: false, next: null,
        error: "", reference: null, modelSeen: false,
      };
      if (parent) {
        for (let ancestor = parent; ancestor; ancestor = ancestor.parent) {
          if (scopeIdentity(ancestor.coordinate) === scopeIdentity(coordinate) ||
              (row && ancestor.row && ancestor.row.id === row.id)) {
            node.reference = ancestor.id;
            break;
          }
        }
      }
      this.nodes.set(node.id, node);
      return node;
    }
    insert(parent, row, origin = "manual") {
      if (!row || !row.id || !validCoordinate(row.node) ||
          !["read", "write", "dispatch"].includes(row.relation) ||
          !["confirmed", "candidate"].includes(row.strength)) return null;
      // Neither a report nor a click can promote a candidate to confirmed.
      const key = JSON.stringify([row.id, scopeIdentity(row.node), row.strength, row.source]);
      let child = parent.children.find(n => n.edgeKey === key);
      if (child) { child.origins.add(origin); return child; }
      child = this.makeNode(row.node, parent, { ...row }, origin);
      child.edgeKey = key;
      parent.children.push(child);
      parent.collapsed = false;
      return child;
    }
    seed(graph, finding = "") {
      const byId = new Map((graph.nodes || []).map(n => [n.id, n]));
      for (const path of graph.tree?.paths || []) {
        if (finding && path.finding !== finding) continue;
        if (path.repair_anchor) {
          const row = path.repair_anchor;
          const key = JSON.stringify([row.id, row.strength, row.source, scopeIdentity(row.node)]);
          let anchor = this.root.repairAnchors.find(a => a.key === key);
          if (!anchor) {
            anchor = { key, row, findings: new Set() };
            this.root.repairAnchors.push(anchor);
          }
          anchor.findings.add(path.finding);
        }
        if (path.status === "unclosed") { this.unclosed.push(path); continue; }
        const steps = path.steps || [];
        const coordinates = new Set([scopeIdentity(this.root.coordinate)]);
        const operations = new Set();
        const invalid = steps.some((row, index) => {
          if (!row?.id || !validCoordinate(row.node) ||
              !["read", "write", "dispatch"].includes(row.relation) ||
              !["confirmed", "candidate"].includes(row.strength)) return true;
          const identity = scopeIdentity(row.node);
          const repeated = coordinates.has(identity) || operations.has(row.id);
          coordinates.add(identity);
          operations.add(row.id);
          return repeated && index < steps.length - 1;
        });
        if (invalid) {
          this.unclosed.push({ ...path, diagnostic: path.diagnostic || "路径包含无效关系或未闭合的循环。" });
          continue;
        }
        let node = this.root;
        let closed = true;
        for (const row of path.steps || []) {
          if (node.reference) { closed = false; break; }
          const child = this.insert(node, row, "report");
          if (!child) { closed = false; break; }
          node = child;
        }
        if (!closed) {
          this.unclosed.push({ ...path, diagnostic: path.diagnostic || "路径包含无法展开的引用或无效关系。" });
          continue;
        }
        const claim = byId.get(path.node);
        if (claim && !node.claims.some(n => n.id === claim.id)) node.claims.push(claim);
        if (path.anchor) node.anchors.push({ row: path.anchor, finding: path.finding, claim: path.node, status: path.status });
      }
      // Only exact coordinates can share additional report claims. The path's
      // terminal claim above keeps its original, possibly wider query scope.
      for (const node of this.nodes.values()) {
        for (const claim of graph.nodes || []) {
          if ((!finding || claim.finding === finding) && claim.exists === true &&
              !this.unclosed.some(path => path.node === claim.id) &&
              scopeIdentity(node.coordinate) === scopeIdentity(claim) &&
              !node.claims.some(n => n.id === claim.id)) node.claims.push(claim);
        }
      }
      if (!graph.tree) this.unclosed.push({ diagnostic: "此报告未提供可核的时间路径，请从根节点手动展开。" });
    }
    visible() {
      const rows = [];
      const visit = (node, depth) => {
        rows.push({ node, depth });
        if (!node.collapsed && !node.reference) node.children.forEach(n => visit(n, depth + 1));
      };
      visit(this.root, 0);
      return rows;
    }
  }

  class InquiryTree {
    constructor(options) {
      this.host = options.host;
      this.api = options.api;
      this.onSelect = options.onSelect;
      this.onChange = options.onChange || (() => {});
      this.report = null;
      this.finding = "";
      this.cache = new Map();
      this.zoom = 1;
      this.selected = null;
      this.model = null;
      this.trace = [];
      this.host.addEventListener("wheel", event => {
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault();
        this.setZoom(this.zoom * (event.deltaY < 0 ? 1.12 : 0.89));
      }, { passive: false });
    }
    loadReport(report, finding = "") {
      this.report = report;
      this.finding = finding;
      this.cache.clear();
      this.setFinding(finding);
    }
    setFinding(finding) {
      this.finding = finding;
      if (!this.report) return;
      if (!this.cache.has(finding)) {
        const t = this.report.target || this.report.document.target;
        const root = this.report.tree?.root || { kind: "file", key: t.file, at: t.at, since: null };
        const model = new EvidenceTreeModel(root);
        model.seed(this.report, finding);
        this.cache.set(finding, model);
      }
      this.model = this.cache.get(finding);
      this.selected = null;
      this.markSeen(this.trace);
      this.render();
      this.fit();
    }
    async start(coordinate) {
      this.report = null;
      this.finding = "";
      this.cache.clear();
      this.model = new EvidenceTreeModel(coordinate);
      this.selected = this.model.root.id;
      this.render();
      this.fit();
      this.select(this.model.root);
      await this.expand(this.model.root);
      this.fit();
    }
    select(node) {
      this.selected = node.id;
      this.render();
      this.onSelect?.(node);
    }
    async expand(node) {
      if (!node || node.loading || node.reference) return;
      if (node.loaded && node.next == null) { node.collapsed = false; this.render(); return; }
      const model = this.model;
      node.loading = true;
      node.error = "";
      this.render();
      try {
        const q = {
          op: node.coordinate.kind, key: node.coordinate.key, at: node.coordinate.at,
          view: "neighbors", direction: "upstream", limit: 12,
        };
        if (node.coordinate.since) q.since = node.coordinate.since;
        if (node.loaded && node.next != null) q.offset = node.next;
        if (this.report?.report_id) {
          q.report_id = this.report.report_id;
          if (this.finding) q.finding = this.finding;
        }
        const data = await this.api("/api/query", q);
        if (model !== this.model) return; // A changed root cannot receive stale rows.
        for (const row of data.rows || []) model.insert(node, row, "manual");
        node.loaded = true;
        node.next = data.next ?? null;
        node.collapsed = false;
        this.markSeen(this.trace);
      } catch (error) {
        if (model === this.model) node.error = error.message;
      } finally {
        node.loading = false;
        if (model === this.model) { this.render(); this.onChange(); }
      }
    }
    markSeen(trace) {
      this.trace = trace || [];
      const queries = this.trace.filter(run => run.origin !== "manual").flatMap(run => [
        ...(run.queries || []).map(row => row.query || row.request || row),
        ...(run.context?.scope ? [{ op: run.context.scope.kind, ...run.context.scope }] : []),
      ]);
      for (const node of this.model?.nodes.values() || []) {
        const evidence = new Set([...(node.row?.evidence || []),
          ...node.claims.flatMap(c => c.evidence || []), ...node.anchors.flatMap(a => a.row.evidence || []),
          ...node.repairAnchors.flatMap(a => a.row.evidence || [])]);
        node.modelSeen = queries.some(q => {
          if (q.op === "open" && evidence.has(q.ref)) return true;
          if (q.scope && node.claims.some(c => c.scope === q.scope)) return true;
          return (q.op === node.coordinate.kind || q.kind === node.coordinate.kind) &&
            q.key === node.coordinate.key && q.at === node.coordinate.at &&
            (q.since ?? null) === (node.coordinate.since ?? null);
        });
      }
    }
    setZoom(value) {
      this.zoom = Math.max(0.25, Math.min(1.75, value));
      this.render();
    }
    fit() {
      if (!this.bounds) return;
      // A tall history remains scrollable instead of shrinking its text away.
      this.zoom = Math.max(0.75, Math.min(1, (this.host.clientWidth - 40) / this.bounds.width));
      this.render();
      this.host.scrollLeft = Math.max(0, this.host.scrollWidth - this.host.clientWidth);
      const focus = this.positions?.get(this.selected || this.model.root.id);
      this.host.scrollTop = focus ? Math.max(0, (focus.y + 36) * this.zoom - this.host.clientHeight / 2) : 0;
    }
    collapse() {
      for (const n of this.model?.nodes.values() || []) n.collapsed = true;
      this.render();
      this.fit();
    }
    paths() {
      if (this.report) {
        for (const n of this.model.nodes.values()) n.collapsed = false;
        this.render();
        this.fit();
      }
    }
    render() {
      this.host.replaceChildren();
      const doc = this.host.ownerDocument;
      const el = (tag, cls, text, parent) => {
        const n = doc.createElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        if (parent) parent.append(n);
        return n;
      };
      if (!this.model) {
        const empty = el("div", "tree-empty", null, this.host);
        el("div", "tree-empty-icon", "←", empty);
        el("h2", "", "从被修文件，回到问题来源", empty);
        el("p", "", "载入结论会自动展开证据路径，也可以输入对象和截止时间开始探索。", empty);
        el("p", "small muted", "文件 ← 写者 Agent ← 输入文件 / 派发父 Agent", empty);
        return;
      }
      const visible = this.model.visible();
      const maxDepth = Math.max(...visible.map(n => n.depth));
      const positions = new Map();
      let cursor = 48;
      const place = (node, depth) => {
        const children = node.collapsed || node.reference ? [] : node.children;
        let y;
        if (children.length) {
          children.forEach(child => place(child, depth + 1));
          // Keep the report's path and root aligned when other history is opened.
          const reported = children.filter(child => child.origins.has("report"));
          const aligned = reported.length ? reported : children;
          y = (positions.get(aligned[0].id).y + positions.get(aligned.at(-1).id).y) / 2;
        } else { y = cursor; cursor += 112; }
        positions.set(node.id, { x: 36 + (maxDepth - depth) * 282, y });
      };
      place(this.model.root, 0);
      this.positions = positions;
      this.bounds = { width: 36 + (maxDepth + 1) * 282, height: Math.max(260, cursor + 24) };
      const spacer = el("div", "tree-spacer", null, this.host);
      spacer.style.width = this.bounds.width * this.zoom + "px";
      spacer.style.height = this.bounds.height * this.zoom + "px";
      const canvas = el("div", "tree-canvas", null, spacer);
      canvas.style.width = this.bounds.width + "px";
      canvas.style.height = this.bounds.height + "px";
      canvas.style.transform = "scale(" + this.zoom + ")";
      canvas.style.left = Math.max(0, this.host.clientWidth - this.bounds.width * this.zoom - 20) + "px";
      const svg = (tag, attrs, parent) => {
        const n = doc.createElementNS("http://www.w3.org/2000/svg", tag);
        Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
        parent.append(n);
        return n;
      };
      const wires = svg("svg", { class: "tree-wires", width: this.bounds.width, height: this.bounds.height }, canvas);
      const defs = svg("defs", {}, wires);
      const marker = svg("marker", { id: "tree-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5,
        markerWidth: 5, markerHeight: 5, orient: "auto" }, defs);
      svg("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#9299aa" }, marker);
      const countByCoordinate = new Map();
      for (const { node } of visible) {
        const id = scopeIdentity(node.coordinate);
        countByCoordinate.set(id, (countByCoordinate.get(id) || 0) + 1);
      }
      for (const { node, depth } of visible) {
        const p = positions.get(node.id);
        if (node.parent) {
          const target = positions.get(node.parent.id);
          const row = node.row;
          const path = svg("path", {
            class: "tree-edge " + row.strength + (row.source === "model_review" ? " reviewed" : ""),
            d: "M" + (p.x + 232) + "," + (p.y + 34) + " C" + (p.x + 257) + "," + (p.y + 34) +
              " " + (target.x - 25) + "," + (target.y + 34) + " " + (target.x - 14) + "," + (target.y + 34),
            "marker-end": "url(#tree-arrow)", "data-edge": row.id,
            "data-strength": row.strength, "data-source": row.source || "indexed",
          }, wires);
          svg("title", {}, path).textContent = row.claim || row.relation;
        }
        if (node === this.model.root) {
          const title = el("div", "tree-column-title", this.report ? "被修文件 · 截止范围" : "探索起点", canvas);
          title.style.left = p.x + "px";
          title.style.top = Math.max(8, p.y - 27) + "px";
        }
        const bad = node !== this.model.root && node.claims.some(n => ["origin", "propagated"].includes(n.role));
        const card = el("div", "tree-node " + node.coordinate.kind +
          (node === this.model.root ? " root" : "") + (bad ? " historical-problem" : "") +
          (node.id === this.selected ? " selected" : ""), null, canvas);
        card.dataset.node = node.id;
        card.dataset.key = node.coordinate.key;
        card.dataset.at = node.coordinate.at;
        card.dataset.depth = depth;
        card.dataset.origins = [...node.origins].join(" ");
        card.dataset.members = JSON.stringify(node.claims.map(n => n.id));
        card.style.left = p.x + "px";
        card.style.top = p.y + "px";
        card.tabIndex = 0;
        card.setAttribute("role", "button");
        card.title = node.coordinate.key + "\n截至 " + node.coordinate.at;
        const heading = el("div", "tree-node-heading", null, card);
        el("span", "atom-icon", node.coordinate.kind === "file" ? "▤" : "◉", heading);
        const key = node.coordinate.key;
        const name = node.coordinate.kind === "file" ? key.split(/[\\/]/).pop() : key.split(":").pop();
        el("span", "tree-node-name", name, heading);
        const badges = el("div", "tree-badges", null, card);
        if (bad) el("span", "historical-tag", "历史问题", badges);
        if (node.row) el("span", "", ({ read: "读取输入", write: "写入", dispatch: "派发" })[node.row.relation], badges);
        if (node.row?.strength === "candidate") el("span", "candidate-tag", "候选", badges);
        if (node.row?.source === "model_review") el("span", "candidate-tag", "模型复核", badges);
        if (node.anchors.some(a => a.row.strength === "candidate")) el("span", "candidate-tag", "入边依据候选", badges);
        if (node.anchors.some(a => a.row.source === "model_review")) el("span", "candidate-tag", "入边模型复核", badges);
        if (node.repairAnchors.some(a => a.row.strength === "candidate")) el("span", "candidate-tag", "修改依据候选", badges);
        if (node.row?.relation === "dispatch" && node.row.identity_known_at_cutoff === false) el("span", "candidate-tag", "当时身份未知", badges);
        if (node.origins.has("report")) el("span", "", "报告路径", badges);
        if (node.origins.has("manual")) el("span", "manual-tag", "人新展开", badges);
        if (node.modelSeen) el("span", "seen-tag", "模型查过", badges);
        if (node.reference) el("span", "", "循环引用 ↗", badges);
        else if (countByCoordinate.get(scopeIdentity(node.coordinate)) > 1) el("span", "", "共享坐标", badges);
        el("div", "tree-time", node.coordinate.at, card);
        card.onclick = () => this.select(node);
        card.onkeydown = event => {
          if (event.key === "Enter" || event.key === " ") { event.preventDefault(); this.select(node); }
        };
        if (node.children.length) {
          const fold = el("button", "tree-fold", node.collapsed ? "+" : "−", card);
          fold.title = node.collapsed ? "展开已有上游" : "折叠此分支";
          fold.onclick = event => { event.stopPropagation(); node.collapsed = !node.collapsed; this.render(); };
        }
        const more = el("button", "tree-more", null, canvas);
        more.dataset.expand = node.id;
        more.style.left = p.x + "px";
        more.style.top = p.y + 77 + "px";
        more.style.width = "232px";
        if (node.reference) {
          more.textContent = "↗ 定位已有祖先 · 停止重复展开";
          more.onclick = () => {
            const ancestor = this.model.nodes.get(node.reference);
            this.select(ancestor);
            this.host.querySelector('[data-node="' + ancestor.id + '"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
          };
        } else {
          more.textContent = node.loading ? "读取历史关系…" : node.error ? "重试 · " + node.error :
            node.loaded && node.next != null ? "展开更多上游…" :
            node.loaded ? node.children.length ? "上游已读取" : "没有可核的更早关系" :
            node.children.length ? "+ 展开其他上游" : "+ 展开上游";
          more.disabled = node.loading || (node.loaded && node.next == null && !node.error);
          more.onclick = () => this.expand(node);
        }
      }
      const label = doc.getElementById("zoomValue");
      if (label) label.textContent = Math.round(this.zoom * 100) + "%";
    }
  }
  const exported = { EvidenceTreeModel, InquiryTree, scopeIdentity };
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  else global.InquiryEvidenceTree = exported;
})(typeof globalThis !== "undefined" ? globalThis : this);
