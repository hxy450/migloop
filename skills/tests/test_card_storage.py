"""Compact storage is a lossless migration of authored claims, not new analysis."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migloop-memory-maintain/scripts"))
from memorylib.card_storage import check_summary, compact_card, compact_store
from memorylib.cases import pack
from memorylib.common import fingerprint, load, write_new
from memorylib.registry import Memory, revision_of, validate_case
from test_memory_bundle import prepared, memory_with


def legacy_card(prepared):
    card = copy.deepcopy(prepared["card"])
    card["schema"] = "migloop-case/1"
    card["provenance"] = load(prepared["meta"])
    card.pop("graph_evidence", None)
    card["node_provenance"] = {"agent.jsonl": card["provenance"]["sources"][0]}
    card["validation"]["graph_checks"] = [{"graph": 1,
        "draft_sha256": fingerprint(card["draft"]["graphs"][0]), "receipt": {
            "schema": "inquiry-graph/1", "report_id": "report-1", "mechanical_status": "valid",
            "path_status": "needs_path", "semantic_verified": False,
            "delivery": {"status": "draft", "coverage_verified": False},
            "nodes": [{"id": "a", "key": "agent.jsonl", "kind": "agent", "at": "2026-01-01T00:00:02Z", "reason": "long reason"},
                      {"id": "f", "key": "/app/src/Page.ets", "kind": "file", "at": "2026-01-01T00:00:10Z"}],
            "edges": [{"from": "a", "to": "f", "relation": "write", "source": "native_evidence",
                       "strength": "certain", "at": "2026-01-01T00:00:02Z", "evidence": ["event:2"],
                       "review": {"quotes": [{"text": "long transcript"}]}}],
            "document": {"huge": "x" * 50000}, "submitted_document": {"huge": "x" * 50000},
            "coverage": {"unassessed": ["irrelevant operation"] * 1000}, "tree": {"huge": "x" * 50000}}}]
    card["revision"] = revision_of(card)
    return card


def test_compaction_preserves_claims_evidence_and_honest_status(prepared):
    old = legacy_card(prepared)
    new = compact_card(old)
    assert new["draft"] == old["draft"] and new["claims"] == old["claims"]
    assert new["id"] == old["id"] and new["revision"] != old["revision"]
    assert new["provenance"]["observed"] == old["provenance"]["observed"]
    assert new["provenance"]["analysis"] == old["provenance"]["analysis"]
    assert new["graph_evidence"][0]["edges"][0]["evidence"] == ["event:2"]
    status = new["validation"]["graph_checks"][0]["receipt"]
    assert status["mechanical_status"] == "valid" and status["path_status"] == "needs_path"
    assert status["delivery"] == {"status": "draft", "coverage_verified": False}
    assert status["semantic_verified"] is False
    assert "node_provenance" not in new and "coverage" not in status
    assert len(json.dumps(new)) < len(json.dumps(old)) / 10
    assert compact_card(new) == new
    validate_case(new)


def test_card_only_pins_related_transcripts(prepared):
    old = legacy_card(prepared)
    old["provenance"]["sources"] += [{"source": "unrelated.jsonl", "sha256": "a" * 64,
                                       "model_timeline": ["not relevant"] * 1000}]
    old["revision"] = revision_of(old)
    new = compact_card(old)
    assert set(new["provenance"]["sources"]) == {"agent.jsonl"}
    assert "not relevant" not in json.dumps(new)


def test_tampered_legacy_or_compact_card_rejected(prepared):
    old = legacy_card(prepared)
    old["draft"]["summary"] = "changed"
    with pytest.raises(ValueError, match="revision hash"):
        compact_card(old)
    new = compact_card(legacy_card(prepared))
    new["graph_evidence"][0]["edges"][0]["evidence"] = ["invented"]
    with pytest.raises(ValueError, match="revision hash"):
        validate_case(new)


def test_full_receipt_cannot_sneak_into_new_format(prepared):
    card = compact_card(legacy_card(prepared))
    card["validation"]["graph_checks"][0]["receipt"]["coverage"] = {}
    with pytest.raises(ValueError, match="debug output"):
        validate_case(card)


def test_store_migration_rebinds_all_history_without_reactivating(prepared):
    old = legacy_card(prepared)
    path = prepared["root"] / "legacy.json"
    write_new(path, old)
    prepared.update(card=old, card_path=path)
    memory = memory_with(prepared)
    memory.withdraw(old["id"], "test withdrawal", memory.current()["revision"], claim="diagnosis")
    before = {str(p.relative_to(memory.root)): p.read_bytes() for p in memory.root.rglob('*.json')}
    out = prepared["root"] / "compact"
    result = compact_store(memory, out)
    migrated = Memory(out)
    head = migrated.current()
    assert head["cases"][old["id"]]["withdrawn_claims"] == ["diagnosis"]
    assert head["lessons"]["lesson-text"]["status"] == "needs_review"
    assert head["lessons"]["lesson-text"]["version"] == memory.current()["lessons"]["lesson-text"]["version"]
    for p in (out / "snapshots").glob('*.json'):
        state = migrated.current(p.stem)
        for identity, info in state["cases"].items():
            card = migrated.case(identity, info["revision"], state)
            assert card["schema"] == "migloop-case/2" and card["draft"] == old["draft"]
        for lesson in state["lessons"].values():
            for ref in lesson["evidence"]:
                assert ref["claim"] in migrated.case(ref["case"], ref["revision"], state)["claims"]
    assert before == {str(p.relative_to(memory.root)): p.read_bytes() for p in memory.root.rglob('*.json')}
    assert result["claims_changed"] is False
    with pytest.raises(ValueError, match="new directory"):
        compact_store(memory, out)


def test_migration_is_idempotent_and_refuses_in_store_output(prepared):
    memory = memory_with(prepared)
    out = prepared["root"] / "compact"
    assert compact_store(memory, out)["revision"] == memory.current()["revision"]
    with pytest.raises(ValueError, match="outside"):
        compact_store(memory, memory.root / "nested")


def test_feedback_retains_actionable_errors_not_repeated_payload():
    edge = {"from": "a", "to": "b", "code": "no_write", "diagnostic": "No write before cutoff",
            "force_eligible": True, "next_call": {"tool": "action", "ref": "event:2"},
            "where": ["edges[0]"], "coordinates": {"from": 1, "to": "target"},
            "inspect": {"op": "file", "key": "/app/src/Page.ets", "view": "relations"},
            "document": "irrelevant repeated material"}
    summary = check_summary({"status": "rejected", "error": "Check the timestamp",
                             "unverified_edges": [edge], "coverage": ["huge"] * 100,
                             "tree": {"paths": [{"diagnostic": "Missing repair anchor"}],
                                      "context_paths": [{"diagnostic": "Missing repair anchor"}]}})
    assert summary["error"] == "Check the timestamp"
    assert summary["unverified_edges"][0] == {k: v for k, v in edge.items() if k != "document"}
    assert summary["path_diagnostics"] == ["Missing repair anchor"]
    assert "coverage" not in summary


@pytest.mark.parametrize("debug", [False, True])
def test_pack_full_receipt_is_opt_in_and_cannot_overwrite(prepared, monkeypatch, debug):
    pytest.importorskip("migloop.inquiry")
    from migloop.inquiry.store import Store, Source
    db = prepared["root"] / "index.sqlite"
    Store.build(db, [Source(str(prepared["pool"] / "agent.jsonl"), "agent.jsonl", "agent", "/app")]).close()
    raw = legacy_card(prepared)["validation"]["graph_checks"][0]["receipt"]
    monkeypatch.setattr("migloop.inquiry.report.check", lambda *a, **kw: copy.deepcopy(raw))
    output, debug_path = prepared["root"] / "checked.json", prepared["root"] / "debug.json"
    result = pack(prepared["job"], prepared["root"] / "draft.json", output, db,
                  debug_path if debug else None)
    assert "document" not in result["validation"]["graph_checks"][0]["receipt"]
    assert load(output)["draft"] == prepared["draft"]
    if debug:
        assert load(debug_path)[0]["receipt"] == raw
        with pytest.raises(ValueError, match="new, separate"):
            pack(prepared["job"], prepared["root"] / "draft.json", prepared["root"] / "again.json", db, debug_path)
        assert not (prepared["root"] / "again.json").exists()
    else:
        assert not debug_path.exists()


def test_migration_preserves_stale_lesson_source_revisions(prepared):
    old = legacy_card(prepared)
    path = prepared["root"] / "legacy.json"
    write_new(path, old)
    prepared.update(card=old, card_path=path)
    memory = memory_with(prepared)
    updated = copy.deepcopy(old)
    updated["draft"]["summary"] = "Revised claim"
    updated["claims"]["diagnosis"]["text"] = "Revised claim"
    updated["revision"] = revision_of(updated)
    new_path = prepared["root"] / "updated.json"
    write_new(new_path, updated)
    memory.ingest([new_path], memory.current()["revision"])
    out = prepared["root"] / "compact"
    compact_store(memory, out)
    migrated = Memory(out)
    head = migrated.current()
    lesson = head["lessons"]["lesson-text"]
    assert lesson["status"] == "needs_review"
    evidence = lesson["evidence"][0]
    assert evidence["revision"] != head["cases"][old["id"]]["revision"]
    assert migrated.case(old["id"], evidence["revision"])["draft"] == old["draft"]
    assert migrated.case(old["id"])["draft"] == updated["draft"]
