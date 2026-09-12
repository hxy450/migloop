/* The report and manual explorer share this temporal evidence tree.
 * Coordinates remain lossless strings: Date rounds microseconds.
 * A row is a historical upstream -> downstream edge, not a click direction.
 */
(function (global) {
  "use strict";
  const scopeIdentity = n => JSON.stringify([n.kind, n.key, n.at, n.since ?? null]);
  const validCoordinate = n => n && ["file", "agent"].includes(n.kind) &&
    typeof n.key === "string" && n.key.length && typeof n.at === "string" && n.at.length;
  // A human-view policy only: the MCP/index retain every candidate.
  const visibleRelation = row => Boolean(row && !row.time_unknown &&
    (row.strength === "confirmed" || (row.source === "model_review" && row.evidence?.length)));
  class EvidenceTreeModel {
    constructor(root) {
      if (!validCoordinate(root)) throw Error("开树需要文件或 Agent 的完整身份及截止时间。");
      this.nodes = new Map();
      this.sequence = 0;
      this.root = this.makeNode(root, null, null, "root");
      this.rights = [];
      this.downstream = { loaded: false, loading: false, next: null, error: "" };
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
    insert(parent, row, origin = "manual", direction = "upstream") {
      if (!row || !row.id || !validCoordinate(row.node) ||
          !["read", "write", "dispatch"].includes(row.relation) ||
          !["confirmed", "candidate"].includes(row.strength)) return null;
      if (!visibleRelation(row)) return null;
      // Neither a report nor a click can promote a candidate to confirmed.
      const key = JSON.stringify([row.id, scopeIdentity(row.node), row.strength, row.source]);
      if (direction === "downstream" && parent !== this.root) return null;
      const siblings = direction === "downstream" ? this.rights : parent.children;
      let child = siblings.find(n => n.edgeKey === key);
      if (child) { child.origins.add(origin); return child; }
      child = this.makeNode(row.node, parent, { ...row }, origin);
      child.edgeKey = key;
      child.isRight = direction === "downstream";
      siblings.push(child);
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
        if (steps.some(row => !visibleRelation(row))) {
          this.unclosed.push({ ...path, diagnostic: "路径含尚未由模型复核的候选关系，本页暂不画出。" });
          continue;
        }
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
      if (!this.root.collapsed) this.rights.forEach(n => rows.push({ node: n, depth: -1 }));
      return rows;
    }
  }

  // Ported from the original migloop/server fixchain.html measure/place layout.
  // Keep its compact rows and centered subtree packing; no report-path bias.
  const GEOMETRY = { width: 196, height: 30, gapY: 8, gapX: 74, top: 34, left: 24 };
  function measureTree(model) {
    const { width, height, gapY, gapX, top, left } = GEOMETRY;
    const positions = new Map(), extents = new Map(), controls = new Map();
    const kids = n => n.collapsed || n.reference ? [] : n.children;
    const more = n => !n.collapsed && kids(n).length && (!n.loaded || n.next != null || n.error);
    function measure(n) {
      const children = kids(n);
      const items = children.map(measure);
      if (more(n)) items.push(height);
      const ext = Math.max(height, items.reduce((a, b) => a + b, 0) + Math.max(0, items.length - 1) * gapY);
      extents.set(n.id, ext);
      return ext;
    }
    const visible = model.visible(), maxDepth = Math.max(...visible.map(v => v.depth));
    const colX = d => left + (maxDepth - d) * (width + gapX);
    const rightNodes = model.root.collapsed ? [] : model.rights;
    const rightMore = !model.root.collapsed && model.downstream.loaded && model.downstream.next != null;
    const rightCount = rightNodes.length + (rightMore ? 1 : 0);
    const rightHeight = Math.max(0, rightCount * (height + gapY) - gapY);
    const rootHeight = measure(model.root);
    function place(n, y0, depth) {
      const ext = extents.get(n.id);
      positions.set(n.id, { x: colX(depth), y: y0 + (ext - height) / 2 });
      let cy = y0;
      for (const child of kids(n)) { place(child, cy, depth + 1); cy += extents.get(child.id) + gapY; }
      if (more(n)) controls.set(n.id, { x: colX(depth + 1), y: cy });
    }
    place(model.root, top + Math.max(0, (rightHeight - rootHeight) / 2), 0);
    const root = positions.get(model.root.id);
    let ry = root.y + height / 2 - rightHeight / 2;
    for (const node of rightNodes) { positions.set(node.id, { x: colX(-1), y: ry }); ry += height + gapY; }
    if (rightMore) controls.set("downstream", { x: colX(-1), y: ry });
    // A continuation control needs its own column even if it has no child node.
    const minX = Math.min(left, ...[...controls.values()].map(p => p.x));
    const shift = left - minX;
    if (shift) for (const p of [...positions.values(), ...controls.values()]) p.x += shift;
    return { positions, controls, visible, maxDepth, colX: d => colX(d) + shift,
      width: colX(rightCount ? -1 : 0) + shift + width + 30,
      height: Math.max(rootHeight, rightHeight) + top + 40 };
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
      this.trace = [];
      this.finding = "";
      this.cache.clear();
      this.model = new EvidenceTreeModel(coordinate);
      this.selected = this.model.root.id;
      this.render();
      this.fit();
      this.select(this.model.root);
      await Promise.all([this.expand(this.model.root), this.expand(this.model.root, "downstream")]);
      this.fit();
    }
    select(node) {
      this.selected = node.id;
      this.render();
      this.onSelect?.(node);
    }
    async expand(node, direction = "upstream") {
      if (!node || node.reference || node.isRight) return;
      if (direction === "downstream" && node !== this.model.root) return;
      const state = direction === "downstream" ? this.model.downstream : node;
      if (state.loading) return;
      if (state.loaded && state.next == null) { node.collapsed = false; this.render(); return; }
      const model = this.model;
      state.loading = true;
      state.error = "";
      this.render();
      try {
        const q = {
          op: node.coordinate.kind, key: node.coordinate.key, at: node.coordinate.at,
          view: "neighbors", direction, limit: 100,
        };
        if (node.coordinate.since) q.since = node.coordinate.since;
        if (state.loaded && state.next != null) q.offset = state.next;
        if (this.report?.report_id) {
          q.report_id = this.report.report_id;
          if (this.finding) q.finding = this.finding;
        }
        let data;
        do {
          data = await this.api("/api/query", q);
          if (model !== this.model) return;
          if ((data.rows || []).some(visibleRelation) || data.next == null) break;
          q.offset = data.next; // Do not stop on a page containing only hidden candidates.
        } while (true);
        if (model !== this.model) return; // A changed root cannot receive stale rows.
        for (const row of data.rows || []) model.insert(node, row, "manual", direction);
        state.loaded = true;
        state.total = data.total;
        state.next = data.next ?? null;
        node.collapsed = false;
        this.markSeen(this.trace);
      } catch (error) {
        if (model === this.model) state.error = error.message;
      } finally {
        state.loading = false;
        if (model === this.model) { this.render(); this.onChange(); }
      }
    }
    async activate(node) {
      const model = this.model;
      this.select(node);
      if (node.isRight || node.reference || node.loading) return;
      if (node.children.length) { node.collapsed = !node.collapsed; this.render(); this.onChange(); }
      else await this.expand(node);
      if (model === this.model) this.focus(node);
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
    fit(automatic = true) {
      if (!this.bounds) return;
      // A tall history remains scrollable instead of shrinking its text away.
      this.zoom = Math.max(automatic ? 0.62 : 0.08, Math.min(1,
        (this.host.clientWidth - 8) / this.bounds.width,
        (this.host.clientHeight - 8) / this.bounds.height));
      this.render();
      if (automatic) this.focus(this.model.nodes.get(this.selected) || this.model.root);
      else { this.host.scrollLeft = 0; this.host.scrollTop = 0; }
    }
    focus(node) {
      const p = this.positions?.get(node.id);
      if (!p) return;
      this.host.scrollLeft = Math.max(0, (p.x + GEOMETRY.width / 2) * this.zoom - this.host.clientWidth / 2);
      this.host.scrollTop = Math.max(0, (p.y + GEOMETRY.height / 2) * this.zoom - this.host.clientHeight / 2);
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
        el("div", "cvempty", "左栏选文件或 agent 与截止时间，点开作为根。也可载入调查结论，自动展开它的证据路径。", this.host);
        return;
      }
      const layout = measureTree(this.model);
      const { width: W, height: H } = GEOMETRY;
      this.positions = layout.positions;
      this.bounds = { width: layout.width, height: layout.height };
      const spacer = el("div", "tree-spacer", null, this.host);
      spacer.style.width = layout.width * this.zoom + "px";
      spacer.style.height = layout.height * this.zoom + "px";
      const canvas = el("div", "tree-canvas canvas", null, spacer);
      canvas.style.width = layout.width + "px";
      canvas.style.height = layout.height + "px";
      canvas.style.transform = "scale(" + this.zoom + ")";
      const svg = (tag, attrs, parent) => {
        const n = doc.createElementNS("http://www.w3.org/2000/svg", tag);
        Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
        parent.append(n);
        return n;
      };
      const wires = svg("svg", { class: "tree-wires wires", width: layout.width, height: layout.height }, canvas);
      for (let depth = 0; depth <= layout.maxDepth; depth++) {
        const heading = el("div", "colhead" + (depth === 0 ? this.model.root.coordinate.kind === "file" ? " root" : " rootA" : ""),
          depth ? "上游 " + depth : "ROOT · " + (this.model.root.coordinate.kind === "file" ? "文件" : "agent"), canvas);
        heading.style.left = layout.colX(depth) + "px"; heading.style.width = W + "px";
      }
      if (layout.visible.some(v => v.depth === -1)) {
        const heading = el("div", "colhead down", this.model.root.coordinate.kind === "file" ? "下游 · 读者" : "下游 · 产出 / 派发", canvas);
        heading.style.left = layout.colX(-1) + "px"; heading.style.width = W + "px";
      }
      for (const { node, depth } of layout.visible) {
        const p = layout.positions.get(node.id);
        if (node.parent) {
          const parent = layout.positions.get(node.parent.id), row = node.row;
          const left = node.isRight ? parent : p, right = node.isRight ? p : parent;
          const x1 = left.x + W, y1 = left.y + H / 2, x2 = right.x, y2 = right.y + H / 2;
          const mid = (x1 + x2) / 2;
          const path = svg("path", {
            class: "tree-edge wire " + row.strength + (row.source === "model_review" ? " reviewed" : ""),
            d: "M" + x1 + "," + y1 + " C" + mid + "," + y1 + " " + mid + "," + y2 + " " + x2 + "," + y2,
            "data-edge": row.id, "data-strength": row.strength, "data-source": row.source || "indexed",
          }, wires);
          svg("title", {}, path).textContent = row.claim || row.relation;
        }
        const root = node === this.model.root;
        const bad = !root && node.claims.some(n => ["origin", "propagated"].includes(n.role));
        const card = el("div", "tree-node node " + node.coordinate.kind +
          (node.coordinate.kind === "agent" ? " gen" : "") +
          (root ? " root" : "") + (bad ? " historical-problem" : "") +
          (node.isRight ? " down" : "") + (node.row?.relation === "dispatch" ? " dispatch" : "") +
          (node.row?.strength === "candidate" ? " candidate" : "") +
          (node.modelSeen ? " seen" : "") + (node.id === this.selected ? " selected sel" : ""), null, canvas);
        Object.assign(card.dataset, { node: node.id, key: node.coordinate.key, at: node.coordinate.at,
          depth, origins: [...node.origins].join(" "), members: JSON.stringify(node.claims.map(n => n.id)) });
        card.style.left = p.x + "px"; card.style.top = p.y + "px";
        card.style.width = W + "px";
        card.tabIndex = 0; card.setAttribute("role", "button");
        const key = node.coordinate.key;
        const name = node.coordinate.kind === "file" ? key.split(/[\\/]/).pop() : key.split(":").pop();
        const relation = ({read:"读取输入",write:"写入",dispatch:"派发"})[node.row?.relation];
        const notes = [relation, bad && "历史问题 · 模型主张", node.modelSeen && "模型查过",
          node.origins.has("report") && "报告路径", node.origins.has("manual") && "人新展开",
          node.row?.strength === "candidate" && "候选", node.row?.source === "model_review" && "模型复核",
          node.row?.identity_known_at_cutoff === false && "当时身份未知", node.reference && "循环引用",
          node.error && "查询失败：" + node.error].filter(Boolean);
        card.title = key + "\n截至 " + node.coordinate.at + "\n" + notes.join(" · ");
        const heading = el("span", "tree-node-name", (node.row?.relation === "dispatch" ? "⇠ " : "") + name, card);
        heading.title = card.title;
        el("span", "tree-time", "@" + (node.coordinate.at.split("T")[1]?.slice(0,8) || node.coordinate.at), heading);
        // Full precision and badges live in the drawer/tooltip, not a tall card.
        el("span", "tree-badges", notes.join(" · "), card);
        el("span", "chev", node.error ? "!" : node.isRight ? "" : node.loading ? "…" :
          node.reference ? "↗" : node.children.length && !node.collapsed ? "▾" :
          node.loaded && !node.children.length && node.next == null ? "·" : "▸", card);
        card.onclick = () => this.activate(node);
        card.onkeydown = event => {
          if (event.key === "Enter" || event.key === " ") { event.preventDefault(); this.activate(node); }
        };
      }
      for (const [id, p] of layout.controls) {
        const downstream = id === "downstream";
        const node = downstream ? this.model.root : this.model.nodes.get(id);
        const state = downstream ? this.model.downstream : node;
        const button = el("button", "tree-more node leaf", state.loading ? "读取中…" : state.error ?
          "重试 · " + state.error : state.loaded ? "+ 继续展开" : "+ 展开其他上游", canvas);
        button.dataset.expand = node.id;
        button.style.left = p.x + "px"; button.style.top = p.y + "px"; button.style.width = W + "px";
        button.disabled = state.loading;
        button.onclick = () => this.expand(node, downstream ? "downstream" : "upstream");
      }
      const label = doc.getElementById("zoomValue");
      if (label) label.textContent = Math.round(this.zoom * 100) + "%";
    }
  }
  const exported = { EvidenceTreeModel, InquiryTree, scopeIdentity, measureTree, GEOMETRY, visibleRelation };
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  else global.InquiryEvidenceTree = exported;
})(typeof globalThis !== "undefined" ? globalThis : this);
