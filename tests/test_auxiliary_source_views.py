"""Non-actor raw material stays searchable without acquiring time/author edges."""
import json
import os

import pytest

from migloop import atoms, atoms_collect, cc_sources, investigation, temporal, transcript_store, verdict_v3
from tests.test_temporal_atom import message, ts


@pytest.fixture
def auxiliary_pool(tmp_path):
    root = tmp_path / "1234abcd-root.jsonl"
    root.write_text(json.dumps(message(0, "a root request")) + "\n", encoding="utf-8")
    journals = []
    for wf in ("wf-one", "wf-two"):
        path = tmp_path / root.stem / "subagents/workflows" / wf / "journal.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "result", "key": wf, "agentId": "some-claimed-agent",
                                    "result": "A.ets needs review: needle"}) + "\n", encoding="utf-8")
        journals.append(path)
    discovered = cc_sources.discover([str(root)])
    agents = atoms_collect.collect_cc_pool([str(root)], [0], sources=discovered)
    ledger = atoms.build_ledger(agents, auxiliary_sources=discovered.auxiliary_sources, source_metadata=discovered.source_metadata)
    return ledger, root, journals


def test_journals_are_full_pool_raw_sources_not_agent_inputs(auxiliary_pool):
    ledger, root, journals = auxiliary_pool
    assert len(ledger.agents) == 1
    assert "some-claimed-agent" not in ledger.agents
    assert {os.path.normcase(os.path.normpath(path)) for path in ledger.auxiliary_sources} == {
        os.path.normcase(str(path)) for path in journals}
    assert len(transcript_store.sources(ledger)) == 3
    main = next(iter(ledger.agents))
    assert set(transcript_store.sources(ledger, main)) == {os.path.normcase(str(root))}
    assert all(not action.files and action.src and os.path.normcase(os.path.normpath(action.src[0])) ==
               os.path.normcase(str(root)) for agent in ledger.agents.values() for action in agent.actions)


def test_unknown_time_raw_hits_require_explicit_expansion_and_remain_undated(auxiliary_pool):
    ledger, _, _ = auxiliary_pool
    common = {"q": "needle", "at": ts(10), "include_undated": True}
    data = investigation.query(ledger, "search", common)
    assert data["rows"] == []
    hits = data["undated"]["rows"]
    assert len(hits) == 2
    assert len({row["ref"] for row in hits}) == 2
    assert all(row["agents"] == [] and row["annotations"] == [] and row["reference_status"] == "addressable" for row in hits)
    for hit in hits:
        with pytest.raises(ValueError, match="时间未知"):
            temporal.record_data(ledger, hit["ref"], at=ts(10))
        raw = temporal.record_data(ledger, hit["ref"], at=ts(10), include_undated=True)
        assert "A.ets needs review" in raw["text"]
        assert raw["ts"] is None and raw["time_status"] == "undated"
        checked = verdict_v3.resolve_evidence(ledger, hit["ref"], scope={"at": ts(10)})
        assert checked["status"] == "undated"
        assert not checked["semantic_checked"]


def test_file_lexical_view_keeps_non_actor_records_without_inventing_file_story(auxiliary_pool):
    ledger, _, _ = auxiliary_pool
    data = investigation.query(ledger, "search", {"file": "A.ets", "q": "needle", "at": ts(10), "include_undated": True})
    assert len(data["undated"]["rows"]) == 2
    assert ledger.stories == {}
    assert all(row["annotations"] == [] for row in data["undated"]["rows"])


def test_raw_auxiliary_batch_receipt_retains_exact_delivered_originals(auxiliary_pool):
    ledger, _, journals = auxiliary_pool
    refs = [transcript_store.read_record(str(p), 1, source=transcript_store.source_spec(ledger, str(p))).ref for p in journals]
    requests = [{"tool": "record", "args": {"ref": ref, "at": ts(10), "include_undated": True}} for ref in refs]
    text = investigation.render_batch(ledger, requests, max_chars=20000)
    decoded = investigation.parse_receipt("batch", {"requests": requests, "max_chars": 20000}, text)
    assert decoded is not None
    assert [item["data"]["ref"] for item in decoded["data"]["items"]] == refs
    for item, path in zip(decoded["data"]["items"], journals):
        assert item["data"]["text"] == path.read_text(encoding="utf-8").rstrip("\n")
        assert item["data"]["ts"] is None
