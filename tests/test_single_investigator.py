"""Free source reading followed by the same investigator's checked graph.

No model calls. A valid graph/submission is deliberately not a correctness test.
"""
import asyncio
import json
from copy import deepcopy

import pytest

from migloop import (
    atom_queries,
    atoms,
    draft_check,
    investigation,
    submission,
    temporal_atom,
    time_receipts,
    transcript_store,
)
from tests.test_draft_check import recorded
from tests.test_submission import trace
from tests.test_temporal_atom import call, pool, result, ts
from tests.test_verdict import _pool
from tests.test_verdict_v3 import document


def test_source_line_opens_unknown_native_call_without_parser_or_agent_visit(tmp_path):
    ledger, _, source = pool(tmp_path, [call(1, "opaque", "UnrecognizedTool", path="/project/A.ets"),
                                        result(2, "opaque", "unclassified evidence survives")])
    args = {"source": source.name, "line": 2, "at": ts(3)}
    scalar = atom_queries.json_data(ledger, "record", args)
    batch = investigation.batch(ledger, [{"tool": "record", "args": args}])["items"][0]
    assert batch["status"] == "ok" and batch["data"] == scalar
    assert "unclassified evidence survives" in scalar["text"] and scalar["complete"]
    assert transcript_store.resolve(ledger, scalar["ref"]).line == 2
    assert scalar["scope"]["kind"] == "pool"
    assert "author" not in scalar and "relation" not in scalar
    wire = atom_queries.render_text(ledger, "/project", "record", args)
    receipt = time_receipts.parse(ledger, "record", args, wire)
    assert receipt["records"] == [scalar["ref"]] and receipt["relation"] is None


@pytest.mark.parametrize("changes", [{"line": 0}, {"line": True}, {"line": -1},
                                      {"line": 999}, {"source": "not-in-pool.jsonl"},
                                      {"source": "../agent-a1111111111111111.jsonl"},
                                      {"at": ts(0)}, {"since_ts": ts(3)}, {"ref": "raw:fake"}])
def test_source_line_rejects_bad_address_or_scope_without_fallback(tmp_path, changes):
    ledger, _, source = pool(tmp_path, [call(1, "w", "Write", file_path="/project/A.ets", content="body"), result(2, "w")])
    args = {"source": source.name, "line": 1, "at": ts(4), **changes}
    with pytest.raises((ValueError, TypeError)):
        atom_queries.json_data(ledger, "record", args)
    assert investigation.batch(ledger, [{"tool": "record", "args": args}])["items"][0]["status"] == "error"


def test_source_line_does_not_bypass_inherited_agent_or_file_scope(tmp_path):
    ledger = _pool(tmp_path)
    source = ledger.agents["agent-c"].sources[0]
    args = {"source": source, "line": 1}
    current = investigation.scope(ledger, "agent", "agent-f", "2026-01-01T02:30:00Z")
    with pytest.raises(ValueError, match="agent"):
        investigation.query(ledger, "record", {**args, "scope": current})
    current = investigation.scope(ledger, "file", "/proj/Unrelated.ets", "2026-01-01T02:30:00Z")
    with pytest.raises(ValueError, match="文件"):
        investigation.query(ledger, "record", {**args, "scope": current})


def test_source_line_ambiguity_and_old_ref_drift_are_independent(tmp_path):
    ledger, _, source = pool(tmp_path, [call(1, "opaque", "Unknown", text="first")])
    original = transcript_store.locate(ledger, source.name, 1)
    source.write_text(source.read_text(encoding="utf-8").replace("first", "changed"), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        transcript_store.resolve(ledger, original.ref)
    assert transcript_store.locate(ledger, source.name, 1).ref != original.ref
    other = tmp_path / "another" / source.name
    other.parent.mkdir()
    other.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    ledger.auxiliary_sources = [str(other)]
    with pytest.raises(ValueError, match="不唯一"):
        transcript_store.locate(ledger, source.name, 1)
    with pytest.raises(ValueError, match="ambiguous"):
        transcript_store.locate(ledger, str(source), 1)  # legacy reference key also collides


def test_old_record_receipt_hash_does_not_change_for_new_optional_fields(tmp_path):
    ledger, _, source = pool(tmp_path, [call(1, "opaque", "Unknown", text="body")])
    ref = transcript_store.locate(ledger, source.name, 1).ref
    args = {"ref": ref, "at": ts(3)}
    assert time_receipts.canonical("record", args) == {
        "ref": ref, "at": ts(3), "offset": 0, "max_chars": None, "include_undated": False}
    wire = atom_queries.render_text(ledger, "/project", "record", args)
    assert time_receipts.parse(ledger, "record", args, wire)


def test_qualified_registered_source_names_resolve_duplicate_basenames(tmp_path):
    import os
    ledger, _, source = pool(tmp_path, [call(1, "opaque", "Unknown", text="first")])
    other = tmp_path / "another" / source.name
    other.parent.mkdir()
    other.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    ledger.auxiliary_sources = [str(other)]
    ledger.source_metadata = {os.path.normcase(os.path.abspath(p)): {
        "logical_name": logical, "timestamp_policy": "record"} for p, logical in (
            (source, "root/agent.jsonl"), (other, "another/agent.jsonl"))}
    first = transcript_store.locate(ledger, "root/agent.jsonl", 1)
    second = transcript_store.locate(ledger, str(other), 1)
    assert first.ref != second.ref
    assert transcript_store.resolve(ledger, second.ref).path == os.path.normcase(os.path.abspath(other))
    with pytest.raises(ValueError, match="不唯一"):
        transcript_store.locate(ledger, source.name, 1)


def test_record_lookup_cannot_read_unregistered_existing_host_file(tmp_path):
    ledger, _, _ = pool(tmp_path, [call(1, "opaque", "Unknown", text="allowed")])
    outside = tmp_path / "not-registered.jsonl"
    outside.write_text('"must not expose"', encoding="utf-8")
    with pytest.raises(ValueError, match="登记池"):
        transcript_store.locate(ledger, str(outside), 1)


def test_actor_directory_is_not_earliest_page_and_candidates_are_not_writers(tmp_path):
    ledger = _pool(tmp_path)
    args = {"kind": "file", "key": "/proj/entry/A.ets", "at": "2026-01-01T02:30:00Z", "limit": 1}
    first = temporal_atom.query(ledger, **args)
    later = temporal_atom.query(ledger, **args, offset=1)
    assert first["participants"] == later["participants"]
    assert {row["agent"] for row in first["participants"]["rows"]} >= {"agent-c", "agent-f"}
    assert len(first["sections"]["writes"]["rows"]) == 1
    early = temporal_atom.query(ledger, **{**args, "at": "2026-01-01T00:30:00Z"})
    assert "agent-f" not in {row["agent"] for row in early["participants"]["rows"]}
    assert first["participants"]["historical_authorship_certified"] is False

    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    ledger, _, _ = pool(candidate_dir, [call(1, "w", "Write", file_path="/project/A.ets", content="body"), result(2, "w", failed=True)])
    data = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(4))
    actor, = data["participants"]["rows"]
    assert actor["candidates"] == 1 and actor["writes"] == 0


def test_same_investigator_can_submit_graph_after_only_raw_reading(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    original = deepcopy(doc)
    draft = json.dumps(doc, ensure_ascii=False)
    response = draft_check.evaluate(ledger, draft, with_graph=True)
    assert response["presentation"]["nodes"] == 3 and response["presentation"]["edges"] == 2
    assert response["presentation"]["relation_bindings"] == {"confirmed": 2}
    assert all(value is False for value in response["evidence_policy"].values())
    calls = [{"tool": "exec_command", "input": {"cmd": "read original sources"}}, recorded(ledger, draft)]
    report = "```json\n" + json.dumps(response["submission_ref"]) + "\n```"
    got = submission.load_checked_submission(report, ledger, calls, trace(ledger), atoms.ledger_identity(ledger))
    assert not got["errors"] and got["data"] == original and got["raw"] == draft
    assert got["submission"]["source_check_step"] == 2
    assert got["submission"]["semantic_checked"] is False
    inline = "```json\n" + draft + "\n```"
    assert submission.load_checked_submission(inline, ledger, calls, trace(ledger), atoms.ledger_identity(ledger))["errors"]
    assert submission.load_checked_submission("done", ledger, calls, trace(ledger), atoms.ledger_identity(ledger))["errors"]
    calls[-1] = recorded(ledger, draft.replace("author claim", "different conclusion"))
    assert submission.load_submission(report, ledger, calls, trace(ledger), atoms.ledger_identity(ledger))["errors"]


def test_check_keeps_unconfirmed_claim_and_does_not_complete_graph(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["findings"][0]["edges"][0]["evidence"] = []
    original = deepcopy(doc)
    response = draft_check.evaluate(ledger, json.dumps(doc), with_graph=True)
    assert response["presentation"]["relation_bindings"] == {"not_observed": 1, "confirmed": 1}
    assert response["argument_graph"]["nodes"][1]["reason"] == original["findings"][0]["nodes"][1]["reason"]
    assert len(response["argument_graph"]["edges"]) == 2
    assert response["submission_ref"]  # gaps are allowed, never a semantic approval
    assert doc == original


def test_invalid_edge_reference_is_not_reported_only_as_missing_relation(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["findings"][0]["edges"][1]["evidence"] = ["raw:agent-c:L4"]
    response = draft_check.evaluate(ledger, json.dumps(doc), with_graph=True)
    issue, = [r for r in response["issues"] if r["code"] == "edge_evidence_unbound"]
    assert issue["severity"] == "error" and "raw:agent-c:L4" in issue["detail"]
    assert "不是关系被否定" in issue["detail"] and "record(source=" in issue["detail"]
    assert response["argument_graph"]["edges"][1]["binding"]["status"] == "not_observed"
    assert response["argument_graph"]["nodes"][1]["reason"] == doc["findings"][0]["nodes"][1]["reason"]


def test_actual_mcp_record_matches_shared_core(tmp_path):
    pytest.importorskip("mcp")
    from migloop import mcp_server
    ledger, _, source = pool(tmp_path, [call(1, "opaque", "Unknown", text="original")])

    class Backend:
        async def get_ledger(self, sid):
            return ledger

        async def get_session_cwd(self, sid):
            return "/project"

    args = {"source": source.name, "line": 1, "at": ts(3)}
    blocks = asyncio.run(mcp_server.build_server(Backend()).call_tool("record", {"sid": "test", **args}))
    expected = atom_queries.render_text(ledger, "/project", "record", args)
    assert blocks[0].text == expected


def test_single_runner_retains_raw_task_and_has_no_second_model_stage():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parents[1] / "docs/experiments/longchain-20260911/single.py"
    spec = importlib.util.spec_from_file_location("single_diagnostic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = "frozen task\r\n"
    supplied = module.prompt(raw, "frozen-session")
    assert supplied.startswith(raw)
    assert "不要求沿图走" in supplied and "最后一次check的submission_ref" in supplied
    assert "不要派给第二个模型" in supplied
    assert "Slice8" not in supplied and "价格" not in supplied
    compile(module.POSTPROCESS, "postprocess", "exec")
    assert "load_checked_submission" in module.POSTPROCESS
    assert "launch(" not in module.POSTPROCESS
