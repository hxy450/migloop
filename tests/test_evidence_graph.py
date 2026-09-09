"""Recorded navigation and evidence-supported dataflow are different projections."""
from copy import deepcopy
from dataclasses import replace

import pytest

from migloop import atoms, probe, verdict
from tests.test_trajectory import _pool, _run_dir


def node(kind, key, v=1):
    return {"id": probe._traj_id(kind, key, v), "kind": kind, "key": key, "v": v}


def tree(ledger, left, right, steps=(2,)):
    checked = probe._relation_check(ledger, left, right)
    return {"mode": "via", "nodes": [left, right],
            "visits": [{"step": 1, "node": left["id"], "status": "opened", "verified": True},
                       *[{"step": s, "node": right["id"], "status": "opened", "verified": True} for s in steps]],
            "transitions": [{"step": s, "from": left["id"], "to": right["id"],
                             "source": "declared", **deepcopy(checked)} for s in steps], "searches": []}


def project(ledger, trajectory, bound=True):
    return probe._evidence_graph(ledger, trajectory, {"bound": bound})


def test_read_reverses_navigation_and_merges_without_mutating_trace(tmp_path):
    ledger = _pool(tmp_path)
    ag, fl = node("agent", "agent-c"), node("file", "/proj/spec/pages/A.md")
    trajectory = tree(ledger, ag, fl, (2, 3))
    before = deepcopy(trajectory)
    graph = project(ledger, trajectory)
    assert graph["schema"] == "migloop-evidence-graph/1"
    assert graph["scope"] == "recorded_transitions" and graph["complete"] is False
    assert graph["semantic_checked"] is False and graph["model_relations"] == []
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert (edge["from"], edge["to"], edge["kind"]) == (fl["id"], ag["id"], "read")
    assert edge["status"] == "true" and edge["steps"] == [2, 3]
    assert edge["source_of_claim"] == "ledger"
    assert edge["evidence"][0]["source"] and edge["evidence"][0]["use_line"]
    assert graph["counts"]["projected_transitions"] == 2
    assert graph["counts"]["confirmed_read"] == 1
    assert trajectory == before


def test_write_follows_effect_direction_not_query(tmp_path):
    ledger = _pool(tmp_path)
    ag, fl = node("agent", "agent-c"), node("file", "/proj/entry/A.ets")
    edge = project(ledger, tree(ledger, fl, ag))["edges"][0]
    assert (edge["from"], edge["to"], edge["kind"]) == (ag["id"], fl["id"], "write")


@pytest.mark.parametrize("basis", ["uncertain_version", "dependency_read", "overlapping_read", "unverified_read"])
def test_supported_read_candidates_do_not_become_confirmed(tmp_path, basis):
    ledger = _pool(tmp_path)
    ag, fl = node("agent", "agent-c"), node("file", "/proj/spec/pages/A.md")
    act = next(a for a in ledger.agents["agent-c"].actions if any(f.op == "read" for f in a.files))
    ref = next(f for f in act.files if f.op == "read")
    if basis == "uncertain_version":
        ref.certain = False
    elif basis == "dependency_read":
        ref.ev = replace(ref.ev, dep=True)
    elif basis == "overlapping_read":
        ref.observation_uncertain = True
    elif basis == "unverified_read":
        ref.ev = replace(ref.ev, proof=None)
    graph = project(ledger, tree(ledger, ag, fl))
    assert graph["counts"]["candidate_read"] == 1 and graph["counts"]["confirmed_read"] == 0
    assert graph["edges"][0]["status"] == "unknown"
    assert graph["edges"][0]["evidence"][0]["basis"] == basis


@pytest.mark.parametrize("basis", ["conditional_read", "read_candidate"])
@pytest.mark.parametrize("file_v", [1, 2])
def test_unversioned_path_candidate_never_projects_to_old_or_future_file_version(tmp_path, basis, file_v):
    ledger = _pool(tmp_path)
    path = "/proj/spec/pages/A.md"
    agent = ledger.agents["agent-f"]
    act = next(row for row in agent.actions if row.src is not None)
    if basis == "conditional_read":
        act.detail["conditional_reads"] = [path]
        expected_basis = "conditional_read"
    else:
        act.detail["read_candidates"] = [{"path": path, "via": "stdout", "proof": {
            "operation_basis": "output_locator", "execution": "unknown",
            "delivery": "unknown", "snapshot": "unknown", "rule": "test"}}]
        expected_basis = "unverified_read"
    if file_v == 2:
        old = ledger.stories[path].versions[0]
        ledger.stories[path].versions.append(replace(
            old, v=2, ts="2027-01-01T00:00:00Z", seq=999, by=atoms.EXTERNAL,
            by_ver=None, act_seq=None))
    ag, fl = node("agent", "agent-f"), node("file", path, file_v)
    checked = probe._relation_check(ledger, ag, fl)
    assert checked["relation_status"] == "unknown"
    assert checked["relation_kind"] == "候选"
    assert checked["relation"] is None
    assert checked["causal_from"] is None and checked["causal_to"] is None
    assert checked["relation_evidence"][0]["basis"] == expected_basis
    assert verdict._rel_read(ledger, fl, ag)[0] == "false"
    graph = project(ledger, tree(ledger, ag, fl))
    assert graph["edges"] == []
    assert graph["counts"]["candidate_read"] == 0
    assert graph["excluded"][0]["reason"] == "non_read_write"


@pytest.mark.parametrize("bound", [False, None])
def test_identity_missing_or_conflicting_never_projects_current_edges(tmp_path, bound):
    ledger = _pool(tmp_path)
    trajectory = tree(ledger, node("agent", "agent-c"), node("file", "/proj/entry/A.ets"))
    graph = project(ledger, trajectory, bound)
    assert graph["edges"] == [] and graph["identity_bound"] is bound
    assert graph["excluded"][0]["reason"] == "identity_unbound"


@pytest.mark.parametrize("change,reason", [
    ("search", "search"), ("dispatch", "non_read_write"), ("mention", "non_read_write"),
    ("self", "same_node"), ("navigation", "non_read_write"),
    ("unlocated", "unlocated_evidence"), ("false_location", "unlocated_evidence"),
    ("wrong_direction", "invalid_direction"), ("unopened", "unverified_visit"),
    ("unknown_endpoint", "invalid_endpoint"), ("model_source", "non_ledger_source"),
    ("source_missing", "unverified_source"),
])
def test_never_invents_read_write_from_navigation_or_unsupported_evidence(tmp_path, change, reason):
    ledger = _pool(tmp_path)
    trajectory = tree(ledger, node("agent", "agent-c"), node("file", "/proj/spec/pages/A.md"))
    tr = trajectory["transitions"][0]
    if change == "search":
        tr.update(source="search", **{"from": None})
    elif change in ("dispatch", "mention", "navigation"):
        tr["relation_kind"] = {"dispatch": "派发", "mention": "候选", "navigation": "未证实"}[change]
    elif change == "self":
        tr["to"] = tr["from"]
    elif change == "unlocated":
        tr["relation_evidence"] = []
    elif change == "false_location":
        tr["relation_evidence"][0]["use_line"] += 100
    elif change == "wrong_direction":
        tr["causal_from"], tr["causal_to"] = tr["causal_to"], tr["causal_from"]
    elif change == "unopened":
        trajectory["visits"][1]["verified"] = False
    elif change == "unknown_endpoint":
        trajectory["nodes"][1]["v"] = 900
    elif change == "source_missing":
        tr["source"] = None
    else:
        tr["relation_source"] = "model"
    graph = project(ledger, trajectory)
    assert graph["edges"] == [] and graph["excluded"][0]["reason"] == reason


def test_claim_only_nodes_and_legacy_layout_edges_are_not_new_relationships(tmp_path):
    ledger = _pool(tmp_path)
    trajectory = tree(ledger, node("agent", "agent-c"), node("file", "/proj/entry/A.ets"))
    trajectory["mode"] = "ledger"
    trajectory["edges"] = [{"from": n["id"], "to": trajectory["nodes"][1]["id"], "relation": "写"}
                           for n in trajectory["nodes"][:1]]
    trajectory["transitions"] = []
    graph = project(ledger, trajectory)
    assert graph["status"] == "legacy_unrecorded" and graph["edges"] == []
    assert len(graph["nodes"]) == 2


def test_public_payload_has_separate_projection_and_no_schema_dependency(tmp_path):
    ledger = _pool(tmp_path)
    calls = [("sessions", {}, "账本身份: " + atoms.ledger_identity(ledger)),
             ("agent", {"id": "agent-c", "v": 1, "via": "sessions"}, "# agent-c v1\n"),
             ("file", {"path": "/proj/spec/pages/A.md", "v": 1, "via": "agent:agent-c@v1"},
              "# spec/pages/A.md@v1\n")]
    payload = probe.probe_payload(ledger, _run_dir(tmp_path, calls, "```yaml\nschema: migloop-verdict/1\nroot: [\n```"))
    assert payload["structured"]["errors"]
    assert len(payload["evidence_graph"]["edges"]) == 1
    assert len(payload["trajectory"]["transitions"]) == 1
    assert "evidence_graph" not in payload["trajectory"]
