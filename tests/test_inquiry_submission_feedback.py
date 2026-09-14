"""Submission feedback must not recommend a later observation as an earlier input."""

import asyncio
import copy
import json

import pytest

from migloop.inquiry.interfaces import build_mcp
from migloop.inquiry.report import check
from migloop.inquiry.store import iso, timestamp
from tests.test_inquiry_core import build, record, result, ts, use


@pytest.fixture
def chronology(tmp_path):
    engine = build(tmp_path, [
        record(1, use("w", file_path="/proj/A.ets", content="bad")), record(2, result("w")),
        record(11, use("fix", "Edit", file_path="/proj/A.ets", old_string="bad", new_string="good")),
        record(12, result("fix"))], second=[
        record(3, use("r", "Read", file_path="/proj/A.ets")), record(4, result("r", "bad")),
        record(5, use("w", file_path="/proj/A.ets", content="bad retained")), record(6, result("w")),
        record(9, use("later", "Read", file_path="/proj/A.ets")), record(10, result("later", "bad retained"))])
    loc = engine.store.locate
    def refs(src, *lines):
        return [loc(src + ".jsonl", n) for n in lines]
    def node(nid, kind, key, at, role, evidence):
        return dict(id=nid, kind=kind, key=key, at=ts(at), role=role, reason=nid, evidence=evidence)
    doc = {"schema": "inquiry/1", "target": {"file": "/proj/A.ets", "since": ts(11), "at": ts(15)},
        "findings": [{"id": "A", "title": "chronology", "reason": "input before output", "unknown": [],
            "changes": refs("a", 3, 4), "nodes": [
                node("origin", "agent", "a.jsonl", 2, "origin", refs("a", 1, 2)),
                node("input", "file", "/proj/A.ets", 10, "propagated", refs("a", 1, 2)),
                node("consumer", "agent", "b.jsonl", 10, "propagated", refs("b", 1, 2, 3, 4, 5, 6)),
                node("target", "file", "/proj/A.ets", 15, "repaired", refs("a", 3, 4))],
            "edges": [{"from": "origin", "to": "input"},
                      {"from": "input", "to": "consumer", "relation": "read",
                       "evidence": refs("b", 5, 6), "claim": "wrongly selected later read"},
                      {"from": "consumer", "to": "target"}]}], "unexplained": []}
    yield engine, doc
    engine.store.close()


def correct_read(engine, doc):
    doc = copy.deepcopy(doc)
    doc["findings"][0]["edges"][1]["evidence"] = [engine.store.locate("b.jsonl", n) for n in (1, 2)]
    return doc


def test_time_rejection_names_both_actual_operations_without_rewriting(chronology):
    engine, doc = chronology
    graph = check(engine, json.dumps(doc))
    assert graph["mechanical_status"] == "valid" and graph["path_status"] == "needs_path"
    path = next(p for p in graph["tree"]["paths"] if p["node"] == "A:origin")
    conflict, = path["blocked_branches"]
    assert conflict["code"] == "time_reversal"
    assert conflict["upstream"]["relation"] == "read"
    assert conflict["upstream"]["at"] == iso(timestamp(ts(10)))
    assert conflict["downstream"]["relation"] == "write"
    assert conflict["downstream"]["at"] == iso(timestamp(ts(6)))
    assert engine.store.locate("b.jsonl", 6) in conflict["upstream"]["evidence"]
    assert engine.store.locate("b.jsonl", 4) in conflict["downstream"]["evidence"]
    assert "00:00:10" in path["diagnostic"] and "00:00:06" in path["diagnostic"]
    assert graph["document"] == doc


def test_successful_alternative_does_not_inherit_rejected_branch_errors(chronology):
    engine, doc = chronology
    good = correct_read(engine, doc)
    good["findings"][0]["edges"].append(doc["findings"][0]["edges"][1])
    graph = check(engine, json.dumps(good))
    assert graph["path_status"] == "complete"
    assert all(not p.get("blocked_branches") for p in graph["tree"]["paths"])


def test_a_missing_connection_is_not_misreported_as_a_time_reversal(chronology):
    engine, doc = chronology
    doc["findings"][0]["edges"].pop(1)
    graph = check(engine, json.dumps(doc))
    assert graph["path_status"] == "needs_path"
    assert all(not p.get("blocked_branches") for p in graph["tree"]["paths"])


def test_mcp_keeps_optional_operations_separate_from_path_errors(chronology):
    engine, doc = chronology
    server = build_mcp(engine.store.path)
    async def run():
        bad = json.loads((await server.call_tool("submit", {"document": json.dumps(doc)}))[0].text)
        path = next(p for p in bad["paths"] if p["node"] == "A:origin")
        assert path["blocked_branches"][0]["code"] == "time_reversal"
        good = json.loads((await server.call_tool("submit", {"document": json.dumps(correct_read(engine, doc))}))[0].text)
        assert good["path_status"] == "complete" and not good["issues"]
        assert "missing_evidence_links" not in good
        related = good["related_evidence"]
        assert related["required"] is False
        later = next(r for r in related["operations"] if engine.store.source_record(r["result"])[0]["ref"] == engine.store.locate("b.jsonl", 6))
        assert later["at"] == iso(timestamp(ts(10))) and later["op"] == "read"
        assert later["agent"] == "b" and later["path"] == "/proj/A.ets"
    asyncio.run(run())


def test_card_audit_uses_the_same_optional_evidence_projection(chronology):
    from migloop.inquiry.feedback import related_evidence
    from tests.test_inquiry_case_card import card
    engine, doc = chronology
    graph = check(engine, json.dumps(correct_read(engine, doc)), save=True)
    audit = card.audit(engine.store.path, graph["report_id"],
                       {"file": "/proj/A.ets", "generation_end": ts(11), "observation_end": ts(15)})
    assert "missing_evidence_links" not in audit
    assert audit["related_evidence"] == related_evidence(graph)


def test_submit_accepts_object_without_double_escaping_and_keeps_force_gate(chronology):
    from migloop.inquiry.report import load_report
    from migloop.inquiry.store import digest, encode
    engine, doc = chronology
    doc = correct_read(engine, doc)
    doc["findings"][0]["reason"] = 'Quote: python -c "print(\'value\')"\n多行原文，不替模型改写。'
    server = build_mcp(engine.store.path)
    async def run():
        submitted = json.loads((await server.call_tool("submit", {"card": doc}))[0].text)
        loaded = load_report(engine, submitted["report_id"])
        assert loaded["document"] == doc
        assert submitted["source_sha256"] == digest(encode(doc).encode())
        doc["findings"][0]["edges"][0].update(force=True, claim="cannot skip first feedback")
        rejected = json.loads((await server.call_tool("submit", {"card": doc}))[0].text)
        assert rejected["unverified_edges"][0]["code"] == "force_before_feedback"
    asyncio.run(run())


def test_submit_preserves_legacy_text_bytes_and_rejects_mixed_forms(chronology):
    from mcp.server.fastmcp.exceptions import ToolError
    from migloop.inquiry.store import digest
    engine, doc = chronology
    server = build_mcp(engine.store.path)
    source = json.dumps(correct_read(engine, doc), indent=4) + "\n"
    async def run():
        submitted = json.loads((await server.call_tool("submit", {"document": source}))[0].text)
        assert submitted["source_sha256"] == digest(source.encode())
        with pytest.raises(ToolError, match="not both"):
            await server.call_tool("submit", {"document": source, "card": doc})
    asyncio.run(run())


def test_wrong_readback_can_be_replaced_only_after_ordinary_script_feedback(tmp_path):
    engine = build(tmp_path, [record(3, use("w", file_path="/proj/A.ets", content="bad")),
        record(4, result("w"))], second=[
        record(5, use("fix", "Bash", command="python -c \"p.read_text(); p.write_text('good')\" /proj/A.ets")),
        record(6, result("fix", "wrote /proj/A.ets")),
        record(7, use("r", "Read", file_path="/proj/A.ets")), record(8, result("r", "good"))])
    loc = engine.store.locate
    def node(nid, kind, key, at, role, ref):
        return dict(id=nid, kind=kind, key=key, at=ts(at), role=role, reason=nid, evidence=[ref])
    script, receipt = loc("b.jsonl", 1), loc("b.jsonl", 2)
    doc = {"schema": "inquiry/1", "target": {"file": "/proj/A.ets", "since": ts(5), "at": ts(9)},
        "findings": [{"id": "A", "title": "readback is not input", "reason": "preserve handoff, correct its evidence",
            "changes": [script, receipt], "nodes": [
                node("origin", "agent", "a.jsonl", 4, "origin", loc("a.jsonl", 1)),
                node("input", "file", "/proj/A.ets", 8, "propagated", loc("a.jsonl", 1)),
                node("repair", "agent", "b.jsonl", 9, "repaired", script),
                node("target", "file", "/proj/A.ets", 9, "repaired", receipt)],
            "edges": [{"from": "origin", "to": "input"}, {"from": "input", "to": "repair"},
                      {"from": "repair", "to": "target"}]}]}
    try:
        first = check(engine, json.dumps(doc), save=True)
        assert len(first["unverified_edges"]) == 1
        doc["revision_of"] = first["report_id"]
        edges = doc["findings"][0]["edges"]
        edges[2].update(force=True, claim="script write", evidence=[script, receipt],
                        review={"at": ts(6), "quotes": [{"ref": receipt, "text": "wrote /proj/A.ets"}]})
        second = check(engine, json.dumps(doc), save=True)
        assert second["mechanical_status"] == "valid" and second["path_status"] == "needs_path"
        assert any(p["blocked_branches"] for p in second["tree"]["paths"])
        doc["revision_of"] = second["report_id"]
        edges[1].update(relation="read", claim="script's earlier input", evidence=[script])
        third = check(engine, json.dumps(doc), save=True)
        assert third["unverified_edges"][0]["force_eligible"]
        doc["revision_of"] = third["report_id"]
        edges[1].update(force=True, review={"at": ts(5), "quotes": [{"ref": script, "text": "p.read_text()"}]})
        fourth = check(engine, json.dumps(doc))
        assert fourth["mechanical_status"] == "valid" and fourth["path_status"] == "complete"
        assert len(fourth["edges"]) == 3 and sum(e.get("force", False) for e in fourth["edges"]) == 2
    finally:
        engine.store.close()
