"""Synthetic protocol regressions only; not migration-accuracy experiments."""

import copy
import json

import pytest

from migloop.inquiry.card import CardError
from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check, load_report
from migloop.inquiry.store import digest
from tests.test_inquiry_core import ts
from tests.test_inquiry_declared_tree import declared
from tests.test_inquiry_force_submission import opaque


def compact_document(old):
    finding = old["findings"][0]
    coordinates = {n["id"]: {"key": n["key"], "at": n["at"]} for n in finding["nodes"]}
    return {"target": {"key": old["target"]["file"], **{k: v for k, v in old["target"].items() if k != "file"}},
        "summary": finding["reason"], "recommendations": ["Check the actual attribute against the source; benefit not yet measured."],
        "nodes": [{**coordinates[n["id"]], "reason": n["reason"],
                   "problem": n["role"] in ("origin", "propagated")} for n in finding["nodes"]],
        "edges": [{k: coordinates[e[k]] for k in ("from", "to")} for e in finding["edges"]]}


def test_compact_auto_identity_evidence_temporal_chain_and_original_replay(declared):
    engine, old = declared
    doc = compact_document(old)
    original = json.dumps(doc, ensure_ascii=False, indent=2)
    graph = check(engine, original, save=True)
    assert graph["mechanical_status"] == "valid" and graph["delivery"]["status"] == "ready_for_review"
    assert graph["submitted_document"] == doc and graph["source_sha256"] == digest(original.encode())
    assert all(n["evidence"] and not n["semantic_verified"] for n in graph["nodes"])
    assert {n["role"] for n in graph["nodes"]} == {"problem", "context"}
    assert any(len(p["steps"]) == 3 for p in graph["tree"]["paths"])
    # No system-attached evidence is relabeled as model-explained changes.
    assert not graph["coverage"]["explained"] and graph["coverage"]["unattributed_native_writes"]
    assert not graph["delivery"]["coverage_verified"]
    saved = engine.store.rows("SELECT request FROM runs WHERE id=?", (graph["report_id"],))[0]
    assert saved["request"] == original
    loaded = load_report(Engine(engine.store), graph["report_id"])
    assert loaded["submitted_document"] == doc and loaded["nodes"] == graph["nodes"]
    assert loaded["edges"] == graph["edges"] and loaded["delivery"] == graph["delivery"]


def test_same_entity_different_times_are_not_merged_and_missing_bridge_stays_missing(declared):
    engine, old = declared
    doc = compact_document(old)
    del doc["edges"][1]
    graph = check(engine, json.dumps(doc))
    files = [n for n in graph["nodes"] if n["kind"] == "file"]
    assert len(files) == 2 and files[0]["id"] != files[1]["id"]
    assert graph["path_status"] == "needs_path" and graph["delivery"]["status"] == "draft"


def test_same_coordinate_single_definition_multiple_edges_and_no_fake_roles(declared):
    engine, old = declared
    doc = compact_document(old)
    doc["edges"].append({"from": doc["edges"][0]["from"], "to": doc["edges"][2]["to"]})
    graph = check(engine, json.dumps(doc))
    assert len(graph["nodes"]) == 4 and len(graph["edges"]) == 4
    assert all(n["role"] != "origin" for n in graph["nodes"])
    doc["nodes"].append(copy.deepcopy(doc["nodes"][0]))
    with pytest.raises(CardError, match="Declare once"):
        check(engine, json.dumps(doc))


def test_many_identity_errors_return_together_without_silent_autocorrection(declared):
    engine, old = declared
    doc = compact_document(old)
    doc["nodes"][0]["key"] = "nonexistent-agent.jsonl"
    doc["nodes"][1]["key"] = "/wrong/proj/A.ets"
    with pytest.raises(CardError) as exc:
        check(engine, json.dumps(doc), save=True)
    assert len(exc.value.issues) >= 2
    assert "nodes[0]" in str(exc.value) and "nodes[1]" in str(exc.value)
    assert "/proj/A.ets" in str(exc.value)
    assert not engine.store.rows("SELECT * FROM runs WHERE kind='report'")


def test_wrong_cutoff_lists_actual_result_time(declared):
    engine, old = declared
    doc = compact_document(old)
    doc["nodes"][0]["at"] = ts(1)
    doc["edges"][0]["from"]["at"] = ts(1)
    graph = check(engine, json.dumps(doc))
    error = graph["unverified_edges"][0]
    assert error["where"] == ["edges[0]"]
    assert error["coordinates"]["from"]["at"] == ts(1)
    from migloop.inquiry.store import timestamp
    assert any(timestamp(e["at"]) == timestamp(ts(2)) and not e["inside_cutoff"] for e in error["nearby_operations"])
    assert "completion" in error["next_step"]


def test_force_only_after_server_feedback_preserves_dashed_edge_and_frozen_parent(opaque):
    engine, old = opaque
    doc = compact_document(old)
    override = copy.deepcopy(doc)
    override["edges"][0].update(force=True, reason="The original script call names the target; reviewed but not statically parsed.",
        evidence=[{"source": "a.jsonl", "line": 1}, {"source": "a.jsonl", "line": 2}])
    first_force = check(engine, json.dumps(override), save=True)
    assert first_force["unverified_edges"][0]["code"] == "force_before_feedback"
    first = check(engine, json.dumps(doc), save=True)
    assert first["unverified_edges"][0]["force_eligible"]
    effects = engine.store.rows("SELECT * FROM effects")
    final = check(engine, json.dumps(override), save=True)
    assert final["delivery"]["status"] == "ready_for_review"
    assert final["revision_parent"] == first["report_id"]
    edge, = final["edges"]
    assert edge["source"] == "model_review" and edge["force"] and not edge["semantic_verified"]
    assert load_report(engine, final["report_id"])["edges"] == final["edges"]
    assert not load_report(engine, first_force["report_id"])["edges"]
    assert engine.store.rows("SELECT * FROM effects") == effects
    # Another investigation cannot inherit force authority.
    outsider = check(Engine(engine.store, session="another-investigation"), json.dumps(override))
    assert not outsider["edges"]


@pytest.mark.parametrize("ref", [{"source": "b.jsonl", "line": 1}, {"source": "a.jsonl", "line": 3}, "e-invented"])
def test_force_cannot_use_foreign_calls_messages_or_fabricated_refs(opaque, ref):
    engine, old = opaque
    doc = compact_document(old)
    check(engine, json.dumps(doc), save=True)
    doc["edges"][0].update(force=True, reason="claimed write", evidence=[ref])
    graph = check(engine, json.dumps(doc))
    assert not graph["edges"] and graph["delivery"]["status"] == "draft"
    assert graph["unverified_edges"][0]["code"] == "invalid_force_source"


def test_force_cannot_backdate_native_write_completion(declared):
    engine, old = declared
    doc = compact_document(old)
    doc["nodes"][0]["at"] = ts(1)
    doc["edges"][0]["from"]["at"] = ts(1)
    check(engine, json.dumps(doc), save=True)
    doc["edges"][0].update(force=True, reason="Request at 1 cannot certify completed write at 1", evidence=[{"source": "a.jsonl", "line": 1}])
    graph = check(engine, json.dumps(doc))
    assert "completes after" in graph["unverified_edges"][0]["diagnostic"]


def test_compact_mcp_and_script_use_shared_delivery_status(declared):
    import asyncio
    import importlib.util
    from pathlib import Path
    from migloop.inquiry.interfaces import build_mcp
    engine, old = declared
    doc = compact_document(old)
    server = build_mcp(engine.store.path)
    async def run():
        return json.loads((await server.call_tool("submit", {"card": doc}))[0].text)
    reply = asyncio.run(run())
    assert reply["delivery"]["status"] == "ready_for_review" and reply["revision"]["tracked_by_server"]
    spec = importlib.util.spec_from_file_location("compact_audit", Path("docs/skills/migloop-investigate/scripts/check_card.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    task = {"file": old["target"]["file"], "generation_end": old["target"]["since"], "observation_end": old["target"]["at"]}
    audited = module.audit(engine.store.path, reply["report_id"], task)
    assert audited["status"] == reply["delivery"]["status"] and not audited["semantic_verified"]


@pytest.mark.parametrize("field,value", [("since", "not-a-time"), ("at", "10:10"), ("at", "2026-01-01T00:00:15")])
def test_bad_target_times_do_not_silently_expand_to_full_history(declared, field, value):
    engine, old = declared
    doc = compact_document(old)
    doc["target"][field] = value
    with pytest.raises(CardError, match="timezone-qualified"):
        check(engine, json.dumps(doc))


@pytest.mark.parametrize("ref", [7, None, {"path": "invented"}, ["not", "a", "reference"]])
def test_malformed_force_evidence_has_actionable_error_not_sql_stacktrace(opaque, ref):
    engine, old = opaque
    doc = compact_document(old)
    check(engine, json.dumps(doc), save=True)
    doc["edges"][0].update(force=True, reason="asserted script write", evidence=[ref])
    graph = check(engine, json.dumps(doc))
    assert graph["unverified_edges"][0]["code"] == "invalid_force_source"
    assert "reference string or {source, line}" in graph["unverified_edges"][0]["diagnostic"]


def test_first_force_stays_unapproved_after_more_later_reports(opaque):
    engine, old = opaque
    doc = compact_document(old)
    doc["edges"][0].update(force=True, reason="first override", evidence=[{"source": "a.jsonl", "line": 1}])
    first = check(engine, json.dumps(doc), save=True)
    ordinary = compact_document(old)
    check(engine, json.dumps(ordinary), save=True)
    successful = check(engine, json.dumps(doc), save=True)
    assert successful["edges"]
    replayed = load_report(engine, first["report_id"])
    assert replayed["revision_parent"] is None and not replayed["edges"]


def test_equivalent_timezone_and_transcript_alias_resolve_to_same_coordinate(declared):
    engine, old = declared
    doc = compact_document(old)
    doc["edges"][0]["from"] = {"key": "a.jsonl", "at": "2026-01-01T08:00:02+08:00"}
    assert check(engine, json.dumps(doc))["delivery"]["status"] == "ready_for_review"


def test_compact_reason_is_prose_not_an_implicit_evidence_submission(declared):
    engine, old = declared
    doc = compact_document(old)
    doc["nodes"][0]["reason"] += " asserted requirement e-deadbeef1234"
    graph = check(engine, json.dumps(doc))
    assert graph["edges"] and not graph["issues"]
    assert graph["delivery"]["status"] == "ready_for_review"
    assert "e-deadbeef1234" in graph["submitted_document"]["nodes"][0]["reason"]


def test_one_forced_relationship_can_bind_multiple_original_script_invocations(tmp_path):
    from tests.test_inquiry_core import build, record, result, use
    engine = build(tmp_path, [record(1, use("x", "Bash", command="python first.py /proj/A.ets")),
        record(2, result("x", "wrote /proj/A.ets")), record(3, use("y", "Bash", command="python second.py /proj/A.ets")),
        record(4, result("y", "wrote /proj/A.ets"))])
    try:
        actor = {"key": "a.jsonl", "at": ts(5)}
        target = {"key": "/proj/A.ets", "at": ts(6)}
        doc = {"target": target, "summary": "Two scripts in one declared handoff", "recommendations": ["Verify both invocations"],
            "nodes": [{**actor, "reason": "Both invocations are claimed writes", "problem": True}],
            "edges": [{"from": actor, "to": target}]}
        first = check(engine, json.dumps(doc), save=True)
        assert first["unverified_edges"][0]["force_eligible"]
        doc["edges"][0].update(force=True, reason="Both scripts rewrite this file", evidence=[{"source": "a.jsonl", "line": i} for i in range(1, 5)])
        final = check(engine, json.dumps(doc), save=True)
        assert final["delivery"]["status"] == "ready_for_review" and len(final["edges"]) == 2
        assert len({e["at"] for e in final["edges"]}) == 2
        assert all(e["source"] == "model_review" and e["strength"] == "candidate" for e in final["edges"])
        assert load_report(engine, final["report_id"])["edges"] == final["edges"]
    finally:
        engine.store.close()


@pytest.mark.parametrize("missing", ["reason", "evidence"])
def test_missing_force_fields_return_validation_feedback(opaque, missing):
    engine, old = opaque
    doc = compact_document(old)
    doc["edges"][0].update(force=True, reason="reviewed script", evidence=[{"source": "a.jsonl", "line": 1}])
    doc["edges"][0].pop(missing)
    with pytest.raises(CardError, match="force requires"):
        check(engine, json.dumps(doc))
