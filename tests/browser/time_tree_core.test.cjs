/* Pure time-tree contract checks; no browser, service, transcript or model runs. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const template = fs.readFileSync(
  path.join(
    __dirname,
    "../../src/migloop/render/templates/time_tree_core.html",
  ),
  "utf8",
);
const script = /^\s*<script>\s*([\s\S]*?)\s*<\/script>\s*$/.exec(template);
assert.ok(script, "Core template must contain exactly one script");
const browser = { window: {}, module: { exports: {} } };
vm.runInNewContext(script[1], browser, { filename: "time_tree_core.html" });
const core = browser.module.exports;
assert.equal(browser.window.MigloopTimeTree, core);
const commonjs = { module: { exports: {} } };
vm.runInNewContext(script[1], commonjs);
assert.equal(typeof commonjs.module.exports.relation, "function");

let checks = 0;
function test(name, run) {
  try {
    run();
    checks += 1;
  } catch (error) {
    error.message = name + ": " + error.message;
    throw error;
  }
}
const copy = (value) => JSON.parse(JSON.stringify(value));
const at = "2026-09-10T10:00:04.000002Z";
const use = "2026-09-10T10:00:01.000001Z";
const fileScope = { kind: "file", key: "/project/A.ets", at, since_ts: null };
const agentScope = { kind: "agent", key: "agent-a", at, since_ts: null };
test("dispatch navigation is agent-to-agent, time bounded, and candidates stay candidates", () => {
  const row = {
    id: "dispatch-1",
    agent: "parent",
    ts: at,
    use_ts: use,
    done_ts: at,
    call_state: "returned",
    reference_status: "addressable",
    operation: {
      kind: "dispatch",
      parent: "parent",
      child: "child",
      status: "candidate",
      execution: "confirmed",
    },
    agent_query: {
      tool: "agent",
      args: { id: "parent", at, since_ts: null, view: "overview" },
    },
  };
  const child = { kind: "agent", key: "child", at, since_ts: null };
  const rel = core.relation(child, row, "dispatches");
  assert.equal(rel.target.key, "parent");
  assert.equal(rel.direction, "upstream");
  assert.equal(rel.status, "candidate");
  assert.equal(core.relation(fileScope, row, "dispatches"), null);
  assert.equal(core.relation({ ...child, at: use }, row, "dispatches"), null);
  assert.equal(
    core.relation(child, { ...row, call_state: "failed" }, "dispatches"),
    null,
  );
  const other = copy(row);
  other.operation.child = "different";
  assert.notEqual(core.operationKey(row), core.operationKey(other));
  assert.equal(core.relation(child, other, "dispatches"), null);
});
function operation(kind = "read") {
  return {
    id: "event-shared",
    agent: "agent-a",
    ts: at,
    use_ts: use,
    done_ts: at,
    call_state: "returned",
    reference_status: "addressable",
    operation: {
      kind,
      path: fileScope.key,
      status: "confirmed",
      execution: "confirmed",
      delivery: "content",
    },
    agent_query: {
      tool: "agent",
      args: { id: "agent-a", at: use, since_ts: null, view: "overview" },
    },
    file_query: {
      tool: "file",
      args: { path: fileScope.key, at, since_ts: null, view: "overview" },
    },
  };
}
function claim(id, kind, key, time = at) {
  return {
    id,
    finding: "finding-a",
    kind,
    key,
    at: time,
    reason: "A model assertion, not certified truth",
    role: "origin",
    binding: { status: "matched", canonical_key: key, at: time },
  };
}
function modelGraph() {
  return {
    identity: { bound: true },
    nodes: [
      claim("input", "file", fileScope.key),
      claim("actor", "agent", "agent-a"),
    ],
    edges: [],
  };
}
test("model dispatch edges need two bound agents and cannot masquerade as writes", () => {
  const graph = {
    identity: { bound: true },
    nodes: [claim("p", "agent", "parent"), claim("c", "agent", "child")],
  };
  const edge = {
    from: "p",
    to: "c",
    relation: "dispatch",
    binding: { status: "candidate" },
  };
  assert.equal(core.modelEdgeAllowed(graph, edge), true);
  assert.equal(
    core.modelEdgeAllowed(graph, { ...edge, relation: "write" }),
    false,
  );
  graph.nodes[1].binding.status = "unlocated";
  assert.equal(core.modelEdgeAllowed(graph, edge), false);
});

test("UTC canonicalization preserves microseconds and timezone rollover", () => {
  assert.equal(core.normalizeTime("2026-09-10T12:00:04.000002+02:00"), at);
  assert.equal(
    core.normalizeTime("2026-09-10T23:59:59.12-01:30"),
    "2026-09-11T01:29:59.120000Z",
  );
  assert.equal(
    core.normalizeTime("2026-01-01T00:00:00+00:30"),
    "2025-12-31T23:30:00.000000Z",
  );
  assert.equal(
    core.normalizeTime("0099-02-28T00:00:00Z"),
    "0099-02-28T00:00:00.000000Z",
  );
  assert.notEqual(
    core.normalizeTime(at),
    core.normalizeTime(at.replace("000002", "000001")),
  );
});
test("invalid, imprecise and impossible dates fail closed", () => {
  for (const value of [
    null,
    1,
    "",
    "latest",
    "2026-09-10",
    "2026-09-10T10:00:04",
    "2026-09-10T10:00:04.0000001Z",
    "2026-02-29T10:00:04Z",
    "2026-04-31T00:00:00Z",
    "2026-09-10T24:00:00Z",
    "2026-09-10T10:00:60Z",
    "2026-09-10T10:00:04+24:00",
    "2026-09-10T10:00:04+01:60",
    "0000-01-01T00:00:00Z",
    "0001-01-01T00:00:00+01:00",
  ]) {
    assert.throws(
      () => core.normalizeTime(value),
      { name: "TypeError" },
      String(value),
    );
  }
  assert.equal(
    core.normalizeTime("2024-02-29T10:00:04Z"),
    "2024-02-29T10:00:04.000000Z",
  );
});
test("scope identities bind exact entities, cutoff and start", () => {
  assert.equal(
    core.scopeKey({ ...fileScope, id: "opaque" }),
    core.scopeKey(fileScope),
  );
  assert.equal(
    core.scopeKey({ ...fileScope, at: "2026-09-10T12:00:04.000002+02:00" }),
    core.scopeKey(fileScope),
  );
  for (const update of [
    { kind: "agent" },
    { key: "/project/B.ets" },
    { at: at.replace("000002", "000001") },
    { since_ts: use },
  ]) {
    assert.notEqual(
      core.scopeKey({ ...fileScope, ...update }),
      core.scopeKey(fileScope),
    );
  }
  assert.equal(core.scope({ kind: "pool", at }).key, null);
  assert.equal(core.scope({ ...fileScope, since_ts: at }).since_ts, at);
});
test("scope rejects versions, navigation provenance and widening", () => {
  for (const update of [
    { kind: "event" },
    { key: "" },
    { at: "latest" },
    { v: 1 },
    { v: null },
    { via: "visit" },
    { since_ts: "2026-09-10T10:00:04.000003Z" },
  ]) {
    assert.throws(() => core.scope({ ...fileScope, ...update }), {
      name: "TypeError",
    });
  }
  assert.throws(() => core.scope({ kind: "pool", key: "/project/A.ets", at }), {
    name: "TypeError",
  });
});
test("completed read is available inclusively at its return cutoff", () => {
  const row = operation();
  const selected = core.relation(agentScope, row, "reads");
  assert.equal(selected.status, "confirmed");
  assert.equal(selected.target.at, at);
  assert.equal(selected.direction, "upstream");
  assert.equal(selected.evidence, row);
  assert.equal(
    core.relation(
      { ...agentScope, at: at.replace("000002", "000001") },
      row,
      "reads",
    ),
    null,
  );
  assert.equal(
    core.relation({ ...agentScope, since_ts: at }, row, "reads").status,
    "confirmed",
  );
});
test("read invocation alone remains an explicit candidate", () => {
  const row = operation();
  Object.assign(row, {
    ts: use,
    done_ts: null,
    call_state: "pending_or_unknown",
  });
  Object.assign(row.operation, { status: "candidate", execution: "unknown" });
  row.file_query.args.at = use;
  const selected = core.relation({ ...agentScope, at: use }, row, "candidates");
  assert.equal(selected.status, "candidate");
  assert.equal(selected.target.at, use);
  assert.equal(core.relation(agentScope, row, "reads"), null);
});
test("file navigation preserves request time rather than completion or query end", () => {
  const row = operation("write");
  const selected = core.relation(fileScope, row, "writes");
  assert.equal(selected.target.kind, "agent");
  assert.equal(selected.target.at, use);
  assert.equal(selected.direction, "upstream");
  assert.equal(
    core.relation({ ...fileScope, since_ts: at }, row, "writes").target
      .since_ts,
    null,
  );
  assert.equal(
    core.relation(agentScope, row, "writes").direction,
    "downstream",
  );
  assert.equal(
    core.relation(fileScope, operation(), "reads").direction,
    "downstream",
  );
  assert.equal(
    core.relation(fileScope, operation("delete"), "writes").kind,
    "delete",
  );
});
test("historical operation label does not certify content delivery or authorship", () => {
  const row = operation();
  row.operation.delivery = "metadata";
  assert.equal(
    core.relation(agentScope, row, "reads").label,
    "历史读取操作 · 已返回",
  );
  assert.equal(
    core.relation(fileScope, operation("write"), "writes").label,
    "历史写入操作 · 已返回",
  );
});
test("uncertain returned operation cannot enter confirmed sections", () => {
  for (const update of [
    { call_state: "failed" },
    { call_state: "ambiguous" },
    { done_ts: null },
    { done_ts: "2026-09-10T10:00:00Z" },
    { reference_status: "ambiguous_source" },
    { use_ts: null },
    { ts: use },
  ]) {
    assert.equal(
      core.relation(agentScope, { ...operation(), ...update }, "reads"),
      null,
    );
  }
  const row = operation();
  row.operation.execution = "unknown";
  assert.equal(core.relation(agentScope, row, "reads"), null);
});
test("failed explicit write remains a candidate when its query target is available", () => {
  const row = operation("write");
  row.call_state = "failed";
  Object.assign(row.operation, { status: "candidate", execution: "unknown" });
  assert.equal(core.relation(fileScope, row, "candidates").status, "candidate");
  assert.equal(core.relation(fileScope, row, "writes"), null);
});
test("mentions, unclassified targets and section mismatches cannot become relations", () => {
  for (const kind of [
    "mention",
    "possible_access",
    "code_host_intent",
    "unclassified_call",
  ]) {
    const row = operation(kind);
    row.operation.status = "candidate";
    assert.equal(core.relation(fileScope, row, "candidates"), null);
  }
  const row = operation();
  assert.equal(
    core.relation(
      fileScope,
      { ...row, operation: { ...row.operation, path: null } },
      "reads",
    ),
    null,
  );
  assert.equal(core.relation(fileScope, row, "writes"), null);
  assert.equal(core.relation(fileScope, row, "candidates"), null);
  assert.equal(core.relation({ kind: "pool", at }, row, "reads"), null);
  assert.equal(core.relation(agentScope, null, "reads"), null);
});
test("operation parent and query entity must match exactly", () => {
  assert.equal(
    core.relation(
      { ...fileScope, key: "/project/B.ets" },
      operation("write"),
      "writes",
    ),
    null,
  );
  assert.equal(
    core.relation({ ...agentScope, key: "agent-b" }, operation(), "reads"),
    null,
  );
  for (const update of [
    { tool: "agent" },
    { args: { path: "/other/A.ets", at } },
    { args: { path: fileScope.key, at: use } },
    { args: { path: fileScope.key, at, since_ts: use } },
    { args: { path: fileScope.key, at, v: 1 } },
    { args: { path: fileScope.key, at, via: "invented" } },
    { args: { path: fileScope.key, at: "latest" } },
    { scope: { ...fileScope, key: "/other/A.ets" } },
    { scope: { ...fileScope, since_ts: use } },
  ]) {
    const row = operation();
    row.file_query = { ...row.file_query, ...update };
    assert.equal(core.relation(agentScope, row, "reads"), null);
  }
  const row = operation("write");
  row.agent_query.args.at = at;
  assert.equal(core.relation(fileScope, row, "writes"), null);
});
test("valid inherited query scope tolerates equivalent timezone spelling", () => {
  const row = operation();
  row.file_query.scope = {
    ...fileScope,
    at: "2026-09-10T12:00:04.000002+02:00",
    id: "server-scope",
  };
  assert.equal(core.relation(agentScope, row, "reads").target.at, at);
});
test("operation identities distinguish shared events with multiple targets or kinds", () => {
  const first = operation("write"),
    second = copy(first),
    third = copy(first);
  second.operation.path = "/project/B.ets";
  third.operation.kind = "delete";
  assert.equal(first.id, second.id);
  assert.equal(new Set([first, second, third].map(core.operationKey)).size, 3);
  assert.equal(core.operationKey(first), core.operationKey(copy(first)));
});
test("claims require exact canonical entity, microsecond time and full historical scope", () => {
  const graph = modelGraph(),
    node = graph.nodes[0],
    original = JSON.stringify(node);
  assert.equal(core.claimMatches(graph, node, fileScope), true);
  assert.equal(
    core.claimMatches(graph, node, { ...fileScope, since_ts: use }),
    false,
  );
  for (const update of [
    { kind: "agent" },
    { key: "/other/A.ets" },
    { at: at.replace("000002", "000001") },
    { at: "latest" },
  ]) {
    assert.equal(
      core.claimMatches(graph, node, { ...fileScope, ...update }),
      false,
    );
  }
  assert.equal(
    JSON.stringify(node),
    original,
    "Reasons and model roles are preserved without mutation",
  );
});
test("matching node binding cannot override an unbound model document", () => {
  const graph = modelGraph();
  for (const bound of [false, undefined, "true", 1]) {
    graph.identity.bound = bound;
    assert.equal(core.claimMatches(graph, graph.nodes[0], fileScope), false);
  }
  graph.identity.bound = true;
  graph.nodes[0].binding.status = "unlocated";
  assert.equal(core.claimMatches(graph, graph.nodes[0], fileScope), false);
});
test("different findings at one coordinate retain their own assertions", () => {
  const graph = modelGraph(),
    first = graph.nodes[0],
    second = copy(first);
  second.id = "another-finding/input";
  second.finding = "finding-b";
  second.role = "context";
  second.reason = "Independent reason";
  assert.equal(core.claimMatches(graph, first, fileScope), true);
  assert.equal(core.claimMatches(graph, second, fileScope), true);
  assert.notEqual(first.reason, second.reason);
  assert.notEqual(first.role, second.role);
});
test("model edge filtering preserves only bound explicit read/write directions", () => {
  const graph = modelGraph();
  const edge = {
    from: "input",
    to: "actor",
    finding: "finding-a",
    relation: "read",
    binding: { status: "confirmed" },
  };
  assert.equal(core.modelEdgeAllowed(graph, edge), true);
  assert.equal(
    core.modelEdgeAllowed(graph, {
      ...edge,
      relation: "possible_read",
      binding: { status: "candidate" },
    }),
    true,
  );
  assert.equal(
    core.modelEdgeAllowed(graph, {
      ...edge,
      from: "actor",
      to: "input",
      relation: "write",
    }),
    true,
  );
  for (const update of [
    { relation: "delete" },
    { relation: "write" },
    { from: "missing" },
    { to: "input" },
    { binding: { status: "not_observed" } },
    { binding: { status: "unbound" } },
    { finding: "finding-b" },
    { drawable: false },
  ]) {
    assert.equal(core.modelEdgeAllowed(graph, { ...edge, ...update }), false);
  }
  graph.identity.bound = false;
  assert.equal(core.modelEdgeAllowed(graph, edge), false);
});
test("ambiguous, unbound and cross-finding model endpoints are not drawable", () => {
  const edge = {
    from: "input",
    to: "actor",
    relation: "read",
    binding: { status: "confirmed" },
  };
  for (const change of [
    (g) => g.nodes.push(copy(g.nodes[0])),
    (g) => (g.nodes[0].binding.status = "unbound"),
    (g) => (g.nodes[1].finding = "finding-b"),
    (g) => (g.nodes[0].at = "latest"),
    (g) => (g.nodes[0].binding.at = use),
  ]) {
    const graph = modelGraph();
    change(graph);
    assert.equal(core.modelEdgeAllowed(graph, edge), false);
  }
});

console.log("time_tree_core: " + checks + " checks passed");
