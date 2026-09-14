"""Coordinates first, server feedback, then evidence-backed report-only overrides."""

import copy
import json

import pytest

from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check, load_report
from tests.test_inquiry_core import build, record, result, ts, use
from tests.test_inquiry_declared_tree import declared


@pytest.fixture
def opaque(tmp_path):
    engine = build(tmp_path, [
        record(1, use("s", "Bash", command="python patch.py /proj/A.ets")),
        record(2, result("s", "wrote /proj/A.ets")),
        record(3, {"type": "text", "text": "I wrote /proj/A.ets"})],
        second=[record(1, use("other", "Bash", command="python other.py /proj/B.ets")),
                record(2, result("other", "wrote /proj/B.ets"))])
    loc = engine.store.locate
    doc = {"schema": "inquiry/1", "target": {"file": "/proj/A.ets", "at": ts(5)}, "findings": [
        {"id": "A", "title": "script write", "reason": "a's script writes target", "changes": [loc("a.jsonl", 1)],
         "nodes": [{"id": "writer", "kind": "agent", "key": "a.jsonl", "at": ts(3),
                    "role": "origin", "reason": "script writer", "evidence": [loc("a.jsonl", 1)]},
                   {"id": "target", "kind": "file", "key": "/proj/A.ets", "at": ts(5),
                    "role": "repaired", "reason": "target", "evidence": [loc("a.jsonl", 2)]}],
         "edges": [{"from": "writer", "to": "target"}]}]}
    yield engine, doc
    engine.store.close()


def forced(engine, doc, previous=None):
    result = copy.deepcopy(doc)
    if previous:
        result["revision_of"] = previous
    result["findings"][0]["edges"][0].update(force=True, claim="script writes the target; model interpretation",
        evidence=[engine.store.locate("a.jsonl", 1)],
        review={"at": ts(1), "quotes": [{"ref": engine.store.locate("a.jsonl", 1), "text": "python patch.py /proj/A.ets"}]})
    return result


def test_bare_coordinates_bind_full_declared_chain_without_evidence_handles(declared):
    engine, doc = declared
    for n in doc["findings"][0]["nodes"]:
        if n["kind"] == "agent":
            n["key"] += ".jsonl"
    doc["findings"][0]["edges"] = [{"from": e["from"], "to": e["to"]} for e in doc["findings"][0]["edges"]]
    graph = check(engine, json.dumps(doc), save=True)
    assert graph["mechanical_status"] == "valid" and graph["path_status"] == "complete"
    assert len(graph["edges"]) == 3 and all(e["evidence"] for e in graph["edges"])
    assert graph["document"] == doc
    assert load_report(engine, graph["report_id"])["document"] == doc


def test_first_force_is_rejected_and_cannot_authorize_itself(opaque):
    engine, doc = opaque
    first = check(engine, json.dumps(forced(engine, doc)), save=True)
    assert not first["edges"] and first["unverified_edges"][0]["code"] == "force_before_feedback"
    retry = check(engine, json.dumps(forced(engine, doc, first["report_id"])))
    assert not retry["edges"]
    # Nor can a later ordinary draft retroactively make the first saved force valid.
    check(engine, json.dumps(doc), save=True)
    assert not load_report(engine, first["report_id"])["edges"]


def test_checked_force_is_dashed_persistent_and_does_not_mutate_facts(opaque):
    engine, doc = opaque
    before = engine.store.rows("SELECT * FROM effects")
    first = check(engine, json.dumps(doc), save=True)
    assert first["unverified_edges"][0]["force_eligible"]
    source = forced(engine, doc, first["report_id"])
    second = check(engine, json.dumps(source), save=True)
    edge, = second["edges"]
    assert edge["source"] == "model_review" and edge["strength"] == "candidate" and edge["force"]
    assert edge["checked_after"] == first["report_id"] and not edge["semantic_verified"]
    assert load_report(Engine(engine.store), second["report_id"])["edges"] == second["edges"]
    q = {"op": "file", "key": "/proj/A.ets", "at": ts(5), "view": "neighbors"}
    assert not engine.query(q)["rows"]
    rows = engine.query({**q, "report_id": second["report_id"]})["rows"]
    assert len(rows) == 1 and rows[0]["source"] == "model_review"
    assert engine.store.rows("SELECT * FROM effects") == before
    third = check(engine, json.dumps(forced(engine, doc, second["report_id"])))
    assert third["edges"]  # An unchanged accepted override can survive another revision.


@pytest.mark.parametrize("fault", ["agent", "time", "target", "quote", "text_only", "foreign_call", "future", "missing_review", "new_edge"])
def test_force_does_not_bypass_hard_errors_or_changed_endpoints(opaque, fault):
    engine, doc = opaque
    first = check(engine, json.dumps(doc), save=True)
    revision = forced(engine, doc, first["report_id"])
    f = revision["findings"][0]
    edge = f["edges"][0]
    if fault == "agent":
        f["nodes"][0]["key"] = "does-not-exist"
    elif fault == "time":
        f["nodes"][0]["at"] = ts(4)
    elif fault == "target":
        revision["target"]["at"] = ts(6)
    elif fault == "quote":
        edge["review"]["quotes"][0]["text"] = "fabricated"
    elif fault in ("text_only", "foreign_call"):
        ref = engine.store.locate("a.jsonl" if fault == "text_only" else "b.jsonl", 3 if fault == "text_only" else 1)
        edge["evidence"] = [ref]
        edge["review"] = {"at": ts(3 if fault == "text_only" else 1),
                          "quotes": [{"ref": ref, "text": "I wrote" if fault == "text_only" else "python other.py"}]}
    elif fault == "future":
        edge["review"]["at"] = ts(6)
    elif fault == "missing_review":
        edge.pop("review")
    else:
        edge["from"], edge["to"] = edge["to"], edge["from"]
    if fault == "target":
        with pytest.raises(ValueError, match="different target"):
            check(engine, json.dumps(revision))
    else:
        graph = check(engine, json.dumps(revision))
        assert not graph["edges"] and graph["mechanical_status"] == "needs_revision"


def test_renaming_local_labels_does_not_change_the_checked_atoms(opaque):
    engine, doc = opaque
    first = check(engine, json.dumps(doc), save=True)
    revision = forced(engine, doc, first["report_id"])
    f = revision["findings"][0]
    f["nodes"][0].update(id="renamed", key="a")
    f["edges"][0]["from"] = "renamed"
    assert check(engine, json.dumps(revision))["edges"]


def test_reviewed_edges_alias_cannot_bypass_first_submission(opaque):
    engine, doc = opaque
    revision = forced(engine, doc)
    f = revision["findings"][0]
    f["reviewed_edges"] = f.pop("edges")
    f["reviewed_edges"][0].pop("force")
    graph = check(engine, json.dumps(revision))
    assert not graph["edges"] and graph["unverified_edges"][0]["code"] == "force_before_feedback"


def test_multiple_writes_are_not_silently_reduced_to_one(declared):
    engine, doc = declared
    f = doc["findings"][0]
    f["nodes"][0]["at"] = ts(15)
    f["edges"] = [{"from": "origin", "to": "target"}]
    graph = check(engine, json.dumps(doc))
    assert len(graph["edges"]) == 2
    from migloop.inquiry.store import timestamp
    assert {timestamp(e["at"]) for e in graph["edges"]} == {timestamp(ts(2)), timestamp(ts(11))}


def test_native_candidate_cannot_become_solid_from_bare_endpoints(declared):
    engine, doc = declared
    f = doc["findings"][0]
    f["nodes"][0].update(at=ts(1), evidence=[])
    f["edges"] = [{"from": "origin", "to": "target"}]
    graph = check(engine, json.dumps(doc))
    assert not graph["edges"] and graph["unverified_edges"][0]["force_eligible"]


def test_a_bad_quote_can_be_corrected_without_losing_prior_server_feedback(opaque):
    engine, doc = opaque
    first = check(engine, json.dumps(doc), save=True)
    revision = forced(engine, doc, first["report_id"])
    revision["findings"][0]["edges"][0]["review"]["quotes"][0]["text"] = "typo"
    second = check(engine, json.dumps(revision), save=True)
    assert not second["edges"]
    third = check(engine, json.dumps(forced(engine, doc, second["report_id"])))
    assert third["edges"] and third["edges"][0]["force"]


def test_mcp_enforces_first_check_and_exposes_the_server_revision_hint(opaque):
    import asyncio
    from migloop.inquiry.interfaces import build_mcp
    engine, doc = opaque
    server = build_mcp(engine.store.path)
    async def run():
        first = json.loads((await server.call_tool("submit", {"document": json.dumps(doc)}))[0].text)
        assert first["revision_hint"]["revision_of"] == first["report_id"]
        assert first["unverified_edges"][0]["force_eligible"]
        second = json.loads((await server.call_tool("submit", {"document": json.dumps(forced(engine, doc, first["report_id"]))}))[0].text)
        assert second["bound_edges"] == 1 and second["mechanical_status"] == "valid"
    asyncio.run(run())


def test_changed_source_bytes_remove_a_previously_accepted_force(opaque):
    from pathlib import Path
    engine, doc = opaque
    first = check(engine, json.dumps(doc), save=True)
    second = check(engine, json.dumps(forced(engine, doc, first["report_id"])), save=True)
    path = Path(engine.store.rows("SELECT path FROM sources WHERE name='a.jsonl'")[0]["path"])
    path.write_bytes(path.read_bytes().replace(b'patch.py', b'other.py'))
    loaded = load_report(engine, second["report_id"])
    assert not loaded["edges"] and loaded["mechanical_status"] == "needs_revision"
    neighbors = engine.query({'op':'file','key':'/proj/A.ets','at':ts(5),'view':'neighbors','report_id':second['report_id']})
    assert not neighbors['rows'] and neighbors['rejected_reviews']


def test_a_read_after_file_cutoff_returns_actionable_feedback(declared):
    engine, doc = declared
    f = doc['findings'][0]
    f['nodes'][1]['at'] = ts(2)  # last write is NOT a cutoff that includes b's later read
    f['edges'] = [{'from':'input','to':'consumer'}]
    graph = check(engine, json.dumps(doc))
    warning, = graph['unverified_edges']
    assert not warning['force_eligible']
    assert 'No tool call/return' in warning['diagnostic']
    assert '00:00:03' in warning['diagnostic']


def test_unknown_local_node_is_reported_without_losing_other_feedback(opaque):
    engine, doc = opaque
    doc['findings'][0]['edges'].append({'from':'typo','to':'target'})
    graph = check(engine, json.dumps(doc))
    assert len(graph['unverified_edges']) == 2
    assert 'unknown node ID: typo' in graph['unverified_edges'][1]['diagnostic']


def test_repaired_root_can_cite_a_receipt_without_repeating_its_incoming_write(opaque):
    engine, doc = opaque
    first = check(engine, json.dumps(doc), save=True)
    second = check(engine, json.dumps(forced(engine, doc, first['report_id'])))
    endpoint, = second['tree']['context_paths']
    assert endpoint['node'] == 'A:target' and endpoint['status'] == 'model_review'
    assert endpoint['steps'] == []  # already the root, not an invented extra hop
    assert endpoint['anchor']['source'] == 'model_review'
