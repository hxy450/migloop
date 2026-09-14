"""Numbered authoring must preserve the one canonical evidence/check pipeline."""

import copy
import json

import pytest

from migloop.inquiry.card import CardError
from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check, load_report
from tests.test_inquiry_compact_card import compact_document
from tests.test_inquiry_declared_tree import declared
from tests.test_inquiry_force_submission import opaque


def numbered(document):
    result = copy.deepcopy(document)
    coordinates = [{k: node[k] for k in ("key", "at")} for node in document["nodes"]]
    target = {k: document["target"][k] for k in ("key", "at")}
    for edge in result["edges"]:
        for key in ("from", "to"):
            edge[key] = coordinates.index(edge[key]) + 1 if edge[key] in coordinates else "target" if edge[key] == target else edge[key]
    return result


def test_numbered_and_explicit_edges_have_identical_graph_and_replay(declared):
    engine, old = declared
    explicit = compact_document(old)
    numbered_doc = numbered(explicit)
    before = check(engine, json.dumps(explicit))
    after = check(engine, json.dumps(numbered_doc), save=True)
    assert before["nodes"] == after["nodes"]
    assert before["edges"] == after["edges"]
    assert after["delivery"]["status"] == "ready_for_review"
    assert after["submitted_document"] == numbered_doc
    loaded = load_report(Engine(engine.store), after["report_id"])
    assert loaded["submitted_document"] == numbered_doc
    assert loaded["nodes"] == after["nodes"] and loaded["edges"] == after["edges"]


@pytest.mark.parametrize("invalid", [0, -1, 500, True, False, 1.0, "1", "origin", None])
def test_invalid_number_or_alias_does_not_select_a_different_node(declared, invalid):
    engine, old = declared
    doc = numbered(compact_document(old))
    doc["edges"][0]["from"] = invalid
    with pytest.raises(CardError, match="edges\\[0\\].from"):
        check(engine, json.dumps(doc), save=True)
    assert not engine.store.rows("SELECT 1 FROM runs WHERE kind='report'")


def test_number_does_not_skip_an_invalid_declaration_and_shift_targets(declared):
    engine, old = declared
    doc = numbered(compact_document(old))
    doc["nodes"][0]["key"] = "nonexistent-agent"
    with pytest.raises(CardError, match="Referenced nodes\\[0\\] is invalid"):
        check(engine, json.dumps(doc))


def test_missing_file_identity_points_to_file_catalog_not_transcripts(declared):
    engine, old = declared
    doc = numbered(compact_document(old))
    doc["nodes"][0]["key"] = "/unknown/source/spec.xml"
    with pytest.raises(CardError) as exc:
        check(engine, json.dumps(doc))
    assert any(issue.get("query") == {"op": "catalog", "kind": "file", "q": "spec.xml"}
               for issue in exc.value.issues)


def test_target_alias_does_not_need_duplicate_target_node(declared):
    engine, old = declared
    doc = compact_document(old)
    target = {k: doc["target"][k] for k in ("key", "at")}
    doc["nodes"] = [n for n in doc["nodes"] if {k: n[k] for k in ("key", "at")} != target]
    doc = numbered(doc)
    assert doc["edges"][-1]["to"] == "target"
    assert check(engine, json.dumps(doc))["delivery"]["status"] == "ready_for_review"


def test_numbered_force_has_same_feedback_gate_and_dashed_provenance(opaque):
    engine, old = opaque
    normal = numbered(compact_document(old))
    forced = copy.deepcopy(normal)
    forced["edges"][0].update(force=True, reason="Reviewed actual script, not a native inferred edge",
        evidence=[{"source": "a.jsonl", "line": 1}, {"source": "a.jsonl", "line": 2}])
    rejected = check(engine, json.dumps(forced), save=True)
    assert rejected["unverified_edges"][0]["code"] == "force_before_feedback"
    check(engine, json.dumps(normal), save=True)
    accepted = check(engine, json.dumps(forced), save=True)
    assert accepted["delivery"]["status"] == "ready_for_review"
    assert all(e["source"] == "model_review" and e["strength"] == "candidate" for e in accepted["edges"])
    assert not check(Engine(engine.store, session="outsider"), json.dumps(forced))["edges"]
