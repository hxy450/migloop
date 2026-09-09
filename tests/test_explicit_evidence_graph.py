"""Explicit model declarations may select facts, never invent visits or facts."""
from copy import deepcopy
from dataclasses import replace

import pytest

from migloop import atoms, probe, verdict
from tests.test_evidence_graph import node, tree
from tests.test_trajectory import _pool, _run_dir


def document(ledger, left="agent:agent-c@v1", right="file:/proj/entry/A.ets@v1", relation="写"):
    data = {"schema": "migloop-verdict/1", "ledger": atoms.ledger_identity(ledger),
            "defects": [{"id": "A", "title": "model title", "nodes": [],
                         "edges": [{"from": left, "to": right, "relation": relation,
                                    "note": "model note is not action evidence"}]}]}
    built = verdict.build(ledger, data, [], {"kind": "yaml", "raw": "original text"})
    built["document_source"] = {"kind": "checked_draft_ref", "verified": True,
                                "semantic_checked": False}
    return built


def empty_trace():
    return {"mode": "via", "root": None, "nodes": [], "visits": [], "transitions": [], "searches": []}


def project(ledger, trajectory, structured, trace_bound=True):
    return probe._evidence_graph(ledger, trajectory, {"bound": trace_bound}, structured=structured)


def test_explicit_write_adds_only_unqueried_display_endpoints_and_raw_support(tmp_path):
    ledger = _pool(tmp_path)
    structured, trace = document(ledger), empty_trace()
    before = deepcopy((structured, trace))
    graph = project(ledger, trace, structured)
    assert graph["complete"] is False
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert (edge["from"], edge["to"], edge["kind"], edge["status"]) == (
        "agent:agent-c@1", "file:/proj/entry/A.ets@1", "write", "true")
    assert edge["source_of_claim"] == "model" and edge["relation_source"] == "ledger"
    assert edge["query_steps"] == edge["steps"] == []
    origin = edge["origins"][0]
    assert origin["selection_source"] == "checked_model_edge" and origin["source_of_claim"] == "model"
    assert origin["defect"] == "A" and origin["edge_index"] == 0
    assert origin["document_sha256"] == structured["document_sha256"]
    assert edge["evidence"][0]["source"] and edge["evidence"][0]["use_line"]
    assert all(n["opened"] == [] and n["source"] == "checked_model_edge" for n in graph["additional_nodes"])
    assert {n["id"] for n in graph["additional_nodes"]} == {edge["from"], edge["to"]}
    assert (structured, trace) == before


def test_explicit_read_uses_the_declared_direction_and_exact_observation(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger, "file:/proj/spec/pages/A.md@v1", "agent:agent-c@v1", "读")
    edge = project(ledger, empty_trace(), doc)["edges"][0]
    assert edge["kind"] == "read"
    assert edge["evidence"][0]["basis"] == "read"
    assert edge["evidence"][0]["observation"]["v"] == 1
    assert edge["evidence"][0]["observation"]["path"] == "/proj/spec/pages/A.md"
    reverse = document(ledger, "agent:agent-c@v1", "file:/proj/spec/pages/A.md@v1", "读")
    reverse["defects"][0]["edges"][0]["status"] = "true"  # cached flag cannot authorize reverse lookup
    assert project(ledger, empty_trace(), reverse)["edges"] == []


def test_same_relation_merges_sources_without_creating_query_steps_or_mutating_inputs(tmp_path):
    ledger = _pool(tmp_path)
    trace = tree(ledger, node("file", "/proj/entry/A.ets"), node("agent", "agent-c"), (2, 3))
    doc = document(ledger)
    other = deepcopy(doc["defects"][0]); other["id"] = "B"; doc["defects"].append(other)
    before = deepcopy((trace, doc))
    graph = project(ledger, trace, doc)
    assert len(graph["edges"]) == 1 and graph["additional_nodes"] == []
    edge = graph["edges"][0]
    assert edge["source_of_claim"] == "mixed" and edge["relation_source"] == "ledger"
    assert edge["query_steps"] == edge["steps"] == [2, 3]
    assert {o["selection_source"] for o in edge["origins"]} == {"recorded_transition", "checked_model_edge"}
    assert {o["defect"] for o in edge["origins"] if o["source_of_claim"] == "model"} == {"A", "B"}
    assert graph["counts"]["projected_transitions"] == 2
    assert graph["counts"]["projected_model_edges"] == 2
    assert len(edge["evidence"]) == 1
    assert (trace, doc) == before


@pytest.mark.parametrize("mode", ["trace_mismatch", "missing_identity", "identity_mismatch", "legacy_saved",
                                  "no_document_source", "invalid_document", "implicit", "implicit_missing",
                                  "wrong_version", "missing_location", "unconfirmed_write", "dispatch"])
def test_untrusted_or_unsupported_model_edges_never_project(tmp_path, mode):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    trace_bound = mode != "trace_mismatch"
    if mode == "missing_identity": doc["identity"]["bound"] = None
    elif mode == "identity_mismatch": doc["identity"]["current"] = "other-ledger"
    elif mode == "legacy_saved": doc["document_source"] = {"kind": "legacy_saved", "verified": False}
    elif mode == "no_document_source": doc.pop("document_source")
    elif mode == "invalid_document": doc["errors"] = ["invalid original"]
    elif mode == "implicit": doc["defects"][0]["edges"][0]["implicit"] = True
    elif mode == "implicit_missing": doc["defects"][0]["edges"][0].pop("implicit")
    elif mode == "wrong_version": doc["defects"][0]["edges"][0]["to"]["v"] = 2
    elif mode == "missing_location":
        act = next(a for a in ledger.agents["agent-c"].actions if a.ver == 1)
        act.src = None
    elif mode == "unconfirmed_write": ledger.stories["/proj/entry/A.ets"].versions[0].proof = None
    elif mode == "dispatch":
        doc = document(ledger, "agent:__main__:abcdef12@v1", "agent:agent-c@v1", "派发")
    graph = project(ledger, empty_trace(), doc, trace_bound)
    assert graph["edges"] == [] and graph["additional_nodes"] == []
    if mode in ("implicit", "implicit_missing"):
        assert graph["counts"]["model_edges"] == graph["counts"]["excluded_model_edges"] == 0
        assert graph["counts"]["non_explicit_rows_ignored"] == 1 and graph["excluded_nonclaims"]
    else:
        assert graph["excluded_model_edges"]


@pytest.mark.parametrize("basis", ["conditional_read", "dependency", "unverified", "uncertain_version", "overlap"])
def test_model_unknown_read_does_not_create_a_version_edge(tmp_path, basis):
    ledger = _pool(tmp_path)
    act = next(a for a in ledger.agents["agent-c"].actions if any(r.op == "read" for r in a.files))
    ref = next(r for r in act.files if r.op == "read")
    if basis == "conditional_read":
        act.files.remove(ref); act.detail["conditional_reads"] = [ref.path]
    elif basis == "dependency": ref.ev = replace(ref.ev, dep=True)
    elif basis == "unverified": ref.ev = replace(ref.ev, proof=None)
    elif basis == "uncertain_version": ref.certain = False
    else: ref.observation_uncertain = True
    doc = document(ledger, "file:/proj/spec/pages/A.md@v1", "agent:agent-c@v1", "读")
    graph = project(ledger, empty_trace(), doc)
    assert graph["edges"] == [] and graph["additional_nodes"] == []
    assert doc["defects"][0]["edges"]  # retain diagnostic in the original structured projection


def test_bad_document_does_not_erase_authenticated_trace_edge(tmp_path):
    ledger = _pool(tmp_path)
    trace = tree(ledger, node("file", "/proj/entry/A.ets"), node("agent", "agent-c"))
    doc = document(ledger); doc["errors"] = ["invalid YAML"]
    graph = project(ledger, trace, doc)
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["source_of_claim"] == "ledger"


def test_public_payload_adds_checked_inline_edge_without_a_navigation_pair(tmp_path):
    ledger = _pool(tmp_path)
    raw = (f"```yaml\nschema: migloop-verdict/1\nledger: {atoms.ledger_identity(ledger)}\n"
           "defects:\n- id: A\n  title: t\n  nodes: []\n  edges:\n"
           "  - {from: 'agent:agent-c@v1', to: 'file:/proj/entry/A.ets@v1', relation: 写}\n```\n")
    run = _run_dir(tmp_path, [("sessions", {}, "账本身份: " + atoms.ledger_identity(ledger))], raw)
    p = probe.probe_payload(ledger, run)
    assert p["structured"]["document_source"]["verified"] is True
    assert p["trajectory"] is None or p["trajectory"]["visits"] == p["trajectory"]["transitions"] == []
    assert len(p["evidence_graph"]["edges"]) == 1
    assert p["evidence_graph"]["edges"][0]["query_steps"] == []
