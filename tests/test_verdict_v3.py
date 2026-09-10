"""Time-scoped post-hoc claims never certify causality or invent connectivity."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from migloop import (
    atoms,
    draft_check,
    investigation,
    transcript_store,
    verdict,
    verdict_v3,
)
from tests.test_temporal import corpus, ts
from tests.test_verdict import _pool, _ref

END = "2026-01-01T02:30:00Z"
EARLY = "2026-01-01T00:30:00Z"


def raw_ref(ledger, aid, tool, *, result=True):
    action = next(a for a in ledger.agents[aid].actions if a.tool == tool)
    line = action.src[2 if result else 1] + 1
    return next(r.ref for r in transcript_store.records(action.src[0]) if r.line == line)


def document(ledger):
    read = raw_ref(ledger, "agent-c", "Read")
    write = raw_ref(ledger, "agent-c", "Write")
    return {"schema": verdict_v3.SCHEMA, "ledger": atoms.ledger_identity(ledger),
            "target": {"file": "/proj/entry/A.ets", "since_ts": "2026-01-01T01:00:00Z", "at": END},
            "findings": [{"id": "F", "title": "a bounded explanation", "reason": "author claim",
                "status": "explained", "changes": [], "unknown": ["initial intent not established"],
                "nodes": [
                    {"id": "spec", "kind": "file", "key": "/proj/spec/pages/A.md", "at": EARLY,
                     "role": "context", "reason": "claimed input", "evidence": [read]},
                    {"id": "actor", "kind": "agent", "key": "agent-c", "at": EARLY,
                     "role": "origin", "reason": "not a mechanically proven cause", "evidence": [write],
                     "counterevidence": [read]},
                    {"id": "file", "kind": "file", "key": "/proj/entry/A.ets", "at": EARLY,
                     "role": "propagated", "reason": "claimed outcome", "evidence": [write]}],
                "edges": [
                    {"from": "spec", "to": "actor", "relation": "read", "evidence": [read],
                     "claim": "reading did not prove the alleged defect was consumed"},
                    {"from": "actor", "to": "file", "relation": "write", "evidence": [write],
                     "claim": "writing did not prove problem propagation"}]}]}


def test_v3_roundtrip_time_coordinates_without_visits_or_via(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    before = deepcopy(doc)
    assert verdict.validate(doc) == []
    loaded = verdict.load_block("```json\n" + json.dumps(doc) + "\n```")
    assert loaded["data"] == doc
    built = verdict.build(ledger, doc, [], {})
    graph = built["argument_graph"]
    assert built["schema"] == verdict_v3.SCHEMA and built["identity"]["bound"] is True
    assert [e["binding"]["status"] for e in graph["edges"]] == ["confirmed", "confirmed"]
    assert all(e["semantic_checked"] is False and e["propagation"]["semantic_checked"] is False for e in graph["edges"])
    assert all(e["binding"]["state_binding"] == "not_proven" for e in graph["edges"])
    assert all("v" not in n and n["binding"]["view"] == "evidence_history" for n in graph["nodes"])
    assert graph["nodes"][0]["evidence"][0]["scope"]["since_ts"] is None
    assert graph["nodes"][0]["evidence"][0]["status"] == "ok"  # Input predates repair since_ts.
    assert graph["nodes"][1]["counterevidence"][0]["status"] == "ok"
    assert doc == before and "query_trace" not in built
    assert built["document_sha256"] == draft_check.document_hash(doc)


@pytest.mark.parametrize("change", ["latest", "timezone", "extra", "third_kind", "role", "duplicate"])
def test_strict_new_contract_does_not_loosen_legacy(tmp_path, change):
    doc = document(_pool(tmp_path))
    node = doc["findings"][0]["nodes"][0]
    if change == "latest": node["at"] = "latest"
    elif change == "timezone": node["at"] = "2026-01-01T00:30:00"
    elif change == "extra": node["semantic_checked"] = True
    elif change == "third_kind": node["kind"] = "event"
    elif change == "role": node["role"] = "verified_cause"
    else: doc["findings"][0]["nodes"].append(deepcopy(node))
    assert verdict.validate(doc)
    doc["schema"] = "migloop-verdict/2"
    assert verdict.validate(doc)  # No changed legacy key/coordinate rules.


def test_dangling_edge_unknown_author_and_no_edges_do_not_create_connectivity(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    finding = doc["findings"][0]
    finding["nodes"][1]["key"] = "unavailable-child"
    finding["edges"][0]["to"] = "missing-node"
    assert verdict.validate(doc) == []
    graph = verdict_v3.build(ledger, doc)["argument_graph"]
    assert len(graph["nodes"]) == 3 and len(graph["edges"]) == 2
    assert graph["nodes"][1]["binding"]["status"] == "unlocated"
    assert graph["edges"][0]["to"] == "F/missing-node"
    assert graph["edges"][0]["binding"]["status"] == "invalid"
    finding["edges"] = []
    assert verdict_v3.build(ledger, doc)["argument_graph"]["edges"] == []
    finding["nodes"] = []
    finding["status"] = "unknown"
    assert verdict_v3.build(ledger, doc)["argument_graph"]["nodes"] == []


def test_pure_mention_does_not_become_possible_operation(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    source = ledger.agents["agent-c"].sources[0]
    message = next(transcript_store.records(source)).ref
    for edge in doc["findings"][0]["edges"]:
        edge["relation"] = "possible_" + edge["relation"]
        edge["evidence"] = [message]
    graph = verdict_v3.build(ledger, doc)["argument_graph"]
    assert all(e["binding"]["status"] == "not_observed" for e in graph["edges"])
    assert all("不等于" in e["binding"]["diag"] for e in graph["edges"])


def test_code_host_intent_is_not_even_a_dotted_historical_read_write_edge(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    for action in ledger.agents["agent-c"].actions:
        if action.tool in ("Read", "Write"):
            action.detail["code_host_intents"] = [{"path": r.path, "op": r.op} for r in action.files]
            action.detail["effect_candidates"] = [r.path for r in action.files if r.op == "write"]
            action.detail["read_candidates"] = [{"path": r.path} for r in action.files if r.op == "read"]
            action.files = []
    for edge in doc["findings"][0]["edges"]:
        edge["relation"] = "possible_" + edge["relation"]
    graph = verdict_v3.build(ledger, doc)["argument_graph"]
    assert all(e["binding"]["status"] == "not_observed" for e in graph["edges"])
    assert all("意图" in e["binding"]["diag"] for e in graph["edges"])


def test_relation_direction_actor_and_source_are_not_inferred_from_prose(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    edge = doc["findings"][0]["edges"][0]
    edge["from"], edge["to"] = edge["to"], edge["from"]
    assert verdict_v3.build(ledger, doc)["argument_graph"]["edges"][0]["binding"]["status"] == "conflicting"
    doc = document(ledger)
    doc["findings"][0]["nodes"][1]["key"] = "agent-f"
    assert all(e["binding"]["status"] == "not_observed" for e in verdict_v3.build(ledger, doc)["argument_graph"]["edges"])


def test_tampered_out_of_time_and_legacy_citations_remain_visible(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    node = doc["findings"][0]["nodes"][1]
    action = next(a for a in ledger.agents["agent-c"].actions if a.tool == "Write")
    node["evidence"] = [_ref(ledger, action.seq), node["evidence"][0][:-1] + "x"]
    node["counterevidence"] = [raw_ref(ledger, "agent-f", "Write")]
    built = verdict_v3.build(ledger, doc)
    actual = built["argument_graph"]["nodes"][1]
    assert [r["status"] for r in actual["evidence"]] == ["ok", "invalid"]
    assert actual["evidence"][0]["raw_ref"].startswith("raw:")
    assert actual["counterevidence"][0]["status"] == "outside_scope"
    checked = draft_check.evaluate(ledger, json.dumps(doc))
    assert checked["semantic_checked"] is False and checked["counts"]["errors"] >= 2


def test_unbound_identity_never_resolves_current_evidence(tmp_path, monkeypatch):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["ledger"] = "another-pool"
    monkeypatch.setattr(transcript_store, "resolve", lambda *a: pytest.fail("must not resolve"))
    graph = verdict_v3.build(ledger, doc)["argument_graph"]
    assert all(n["binding"]["status"] == "unbound" for n in graph["nodes"])
    assert all(e["binding"]["status"] == "unbound" for e in graph["edges"])
    assert all(r["status"] == "unbound" for n in graph["nodes"] for r in n["evidence"])


def test_late_read_result_does_not_certify_earlier_input(tmp_path):
    ledger, aid, path = corpus(tmp_path)
    refs = list(transcript_store.records(path))
    doc = {"schema": verdict_v3.SCHEMA, "ledger": atoms.ledger_identity(ledger),
        "target": {"file": "/p/A.ets", "at": ts(20)}, "findings": [{"id": "F", "title": "late",
        "reason": "unknown", "status": "unknown", "nodes": [
            {"id": "f", "kind": "file", "key": "/p/A.ets", "at": ts(10), "role": "context", "reason": "x", "evidence": []},
            {"id": "a", "kind": "agent", "key": aid, "at": ts(10), "role": "context", "reason": "x", "evidence": []}],
        "edges": [{"from": "f", "to": "a", "relation": "read", "claim": "not proved",
                   "evidence": [refs[2].ref, refs[3].ref]}]}]}
    edge = verdict_v3.build(ledger, doc)["argument_graph"]["edges"][0]
    assert edge["binding"]["status"] != "confirmed"
    assert edge["binding"]["status"] != "candidate"
    assert edge["evidence"][1]["status"] == "outside_scope"


def test_read_does_not_require_invented_version_but_dependency_stays_candidate(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    ref = next(r for a in ledger.agents["agent-c"].actions for r in a.files if r.op == "read")
    ref.certain = False
    assert verdict_v3.build(ledger, doc)["argument_graph"]["edges"][0]["binding"]["status"] == "confirmed"
    ref.ev = replace(ref.ev, dep=True)
    assert verdict_v3.build(ledger, doc)["argument_graph"]["edges"][0]["binding"]["status"] == "candidate"


def test_coverage_reads_all_pages_and_keeps_unknown_event_declarations(tmp_path, monkeypatch):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["coverage"] = [{"event": "e1", "status": "not_repair", "reason": "a write is not automatically a defect"},
                       {"event": "missing", "status": "unresolved", "reason": "not located"}]
    doc["findings"][0]["changes"] = ["e2", "missing"]
    offsets = []
    def changes(*args, offset=0, **kwargs):
        offsets.append(offset)
        return {"rows": [{"id": "e1" if offset == 0 else "e2", "status": "confirmed_change"}],
                "next_offset": 200 if offset == 0 else None}
    monkeypatch.setattr(investigation, "changes", changes)
    graph = verdict_v3.build(ledger, doc)["argument_graph"]
    assert offsets == [0, 200]
    assert [(r["event"], r["status"]) for r in graph["coverage"]] == [("e1", "not_repair"), ("e2", "explained"), ("missing", "unresolved")]
    assert graph["coverage"][1]["assignment_mode"] == "explicit_finding_change_links"
    assert graph["coverage"][1]["semantic_checked"] is False
    assert graph["findings"][0]["change_bindings"][1]["status"] == "unlocated"
    assert graph["complete"] is False


def test_shared_change_links_do_not_require_redundant_coverage_or_certify_truth(tmp_path, monkeypatch):
    from copy import deepcopy
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["findings"][0]["changes"] = ["event"]
    other = deepcopy(doc["findings"][0])
    other.update(id="G", status="unknown")
    doc["findings"].append(other)
    monkeypatch.setattr(investigation, "changes", lambda *a, **k: {"rows": [{"id": "event"}], "next_offset": None})
    graph = verdict_v3.build(ledger, doc)["argument_graph"]
    row, = graph["coverage"]
    assert row["referenced_findings"] == ["F", "G"]
    assert row["status"] == "unresolved" and row["source"] == "model"
    assert row["binding"]["status"] == "matched" and not row["semantic_checked"]


def test_coverage_limit_reports_incomplete_instead_of_silently_using_first_page(tmp_path, monkeypatch):
    ledger = _pool(tmp_path)
    monkeypatch.setattr(verdict_v3, "MAX_CHANGE_ROWS", 1)
    monkeypatch.setattr(investigation, "changes", lambda *a, **k: {"rows": [{"id": "e"}], "next_offset": 200})
    graph = verdict_v3.build(ledger, document(ledger))["argument_graph"]
    assert any(d["code"] == "change_inventory_incomplete" for d in graph["diagnostics"])


@pytest.mark.parametrize("field", ["findings", "nodes", "edges", "coverage"])
@pytest.mark.parametrize("value", [None, False, "bad", 1])
def test_malformed_containers_are_diagnostics_not_exceptions(tmp_path, field, value):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    (doc if field in ("findings", "coverage") else doc["findings"][0])[field] = value
    assert verdict.validate(doc)
    assert verdict_v3.build(ledger, doc)["errors"]


@pytest.mark.parametrize("field", ["status", "kind", "role", "relation"])
@pytest.mark.parametrize("value", [[], {}])
def test_malformed_enums_never_raise_unhashable_type(tmp_path, field, value):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    finding = doc["findings"][0]
    row = finding if field == "status" else finding["edges"][0] if field == "relation" else finding["nodes"][0]
    row[field] = value
    assert verdict.validate(doc)
    assert verdict_v3.build(ledger, doc)["errors"]


def test_normalized_source_statistics_block_stale_inferred_edge(tmp_path):
    from pathlib import Path
    ledger = _pool(tmp_path)
    doc = document(ledger)
    ledger.source_stats = {verdict_v3._norm(path): stat for path, stat in ledger.source_stats.items()}
    assert verdict_v3.build(ledger, doc)["argument_graph"]["edges"][1]["binding"]["status"] == "confirmed"
    path = Path(ledger.agents["agent-c"].sources[0])
    path.write_text(path.read_text(encoding="utf-8") + '\n', encoding="utf-8")
    edge = verdict_v3.build(ledger, doc)["argument_graph"]["edges"][1]
    assert edge["evidence"][0]["status"] == "ok"  # Unchanged quoted line is still real.
    assert edge["binding"]["status"] == "unbound"  # But old parser state is not certified.


def test_legacy_block_citation_cannot_borrow_other_tool_on_same_raw_line(tmp_path):
    from tests.test_atoms import MAIN_ID, _ledger, _rec
    records = [
        _rec("2026-01-01T00:00:00Z", "assistant", [
            {"type": "tool_use", "id": "wa", "name": "Write", "input": {"file_path": "/proj/A.ets", "content": "a"}},
            {"type": "tool_use", "id": "wb", "name": "Write", "input": {"file_path": "/proj/B.ets", "content": "b"}}]),
        _rec("2026-01-01T00:00:01Z", "user", [
            {"type": "tool_result", "tool_use_id": "wa", "content": "File created successfully at: /proj/A.ets"},
            {"type": "tool_result", "tool_use_id": "wb", "content": "File created successfully at: /proj/B.ets"}])]
    ledger = _ledger(tmp_path, records, {})
    actions = [a for a in ledger.agents[MAIN_ID].actions if a.tool == "Write"]
    wrong_ref = _ref(ledger, actions[1].seq)
    doc = {"schema": verdict_v3.SCHEMA, "ledger": atoms.ledger_identity(ledger),
        "target": {"file": "/proj/A.ets", "at": END}, "findings": [{"id": "F", "title": "two blocks",
        "reason": "not proved", "status": "unknown", "nodes": [
            {"id": "a", "kind": "agent", "key": MAIN_ID, "at": END, "role": "context", "reason": "x"},
            {"id": "f", "kind": "file", "key": "/proj/A.ets", "at": END, "role": "context", "reason": "x"}],
        "edges": [{"from": "a", "to": "f", "relation": "write", "claim": "unproven", "evidence": [wrong_ref]}]}]}
    edge = verdict_v3.build(ledger, doc)["argument_graph"]["edges"][0]
    assert edge["evidence"][0]["action_seq"] == actions[1].seq
    assert edge["binding"]["status"] == "not_observed"
    doc["findings"][0]["edges"][0]["evidence"] = [raw_ref(ledger, MAIN_ID, "Write", result=False)]
    assert verdict_v3.build(ledger, doc)["argument_graph"]["edges"][0]["binding"]["status"] == "confirmed"


def test_same_entities_in_different_findings_do_not_merge_model_claims(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    first = deepcopy(doc["findings"][0])
    second = deepcopy(first)
    first["id"], first["nodes"][0]["id"] = "a/b", "c"
    second["id"], second["nodes"][0]["id"] = "a", "b/c"
    first["edges"] = second["edges"] = []
    second["nodes"][0]["role"] = "origin"
    doc["findings"] = [first, second]
    graph = verdict_v3.build(ledger, doc)["argument_graph"]
    assert len({n["id"] for n in graph["nodes"]}) == 6
    assert graph["nodes"][0]["role"] != graph["nodes"][3]["role"]


def test_checked_draft_reference_preserves_v3_document_and_hash(tmp_path):
    from migloop import submission
    from tests.test_draft_check import recorded
    from tests.test_submission import reference, trace
    ledger = _pool(tmp_path)
    doc = document(ledger)
    draft = json.dumps(doc, ensure_ascii=False)
    call = recorded(ledger, draft)
    final = reference(ledger, draft, doc)
    loaded = submission.load_submission(final, ledger, [call], trace(ledger), atoms.ledger_identity(ledger))
    assert loaded["data"] == doc and loaded["raw"] == draft
    assert loaded["submission"]["status"] == "accepted"
    doc["findings"][0]["recommendation"] = "new unchecked claim"
    assert draft_check.final_binding(ledger, [call], doc, identity_bound=True)["status"] == "mismatch"


def test_http_json_check_has_graph_text_check_does_not_and_build_runs_once(tmp_path, monkeypatch):
    from migloop import atom_queries
    ledger = _pool(tmp_path)
    doc = document(ledger)
    args = {"draft": json.dumps(doc)}
    original = verdict_v3.build
    builds = []
    def build(*args, **kwargs):
        builds.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(verdict_v3, "build", build)
    http = atom_queries.json_data(ledger, "check", args)
    assert len(builds) == 1
    assert http["argument_graph"]["schema"] == verdict_v3.GRAPH_SCHEMA
    assert http["argument_graph"]["nodes"]
    text = json.loads(atom_queries.render_text(ledger, "/proj", "check", args))
    assert len(builds) == 2  # Exactly once per separate request, not twice for JSON.
    assert "argument_graph" not in text
    assert {k: v for k, v in http.items() if k != "argument_graph"} == text
    assert http["issues"] == text["issues"] and http["coverage"] == text["coverage"]


def test_pending_action_missing_result_line_keeps_raw_citation_without_certifying_edge(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    invocation = raw_ref(ledger, "agent-c", "Write", result=False)
    action = next(a for a in ledger.agents["agent-c"].actions if a.tool == "Write")
    action.src = (action.src[0], action.src[1], None)
    action.done_ts = None
    doc["ledger"] = atoms.ledger_identity(ledger)
    doc["findings"][0]["edges"][1]["evidence"] = [invocation]
    resolved = verdict_v3.resolve_evidence(ledger, invocation, scope={"at": END})
    assert resolved["status"] == "ok" and resolved["textual_only"] is False
    edge = verdict_v3.build(ledger, doc)["argument_graph"]["edges"][1]
    assert edge["evidence"][0]["status"] == "ok"
    assert edge["binding"]["status"] == "not_observed"


@pytest.mark.parametrize("src,expected", [(None, set()), (("source", 0, None), {1}),
    (("source", True, -1), set()), (("source", 2, 3), {3, 4}), (("source", "2", 1.5), set())])
def test_action_lines_accepts_only_available_nonnegative_integer_coordinates(src, expected):
    assert verdict_v3._action_lines(src) == expected
