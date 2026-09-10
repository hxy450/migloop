"""Request-local parsing reuse must not become stale evidence or a global pool."""
from copy import deepcopy
import json

import pytest

from migloop import atoms, investigation, raw_events, transcript_store
from tests.test_temporal_atom import call, message, pool, result, ts


def calls(monkeypatch):
    original = raw_events._source_index_global
    seen = []
    def run(path, registry_key):
        seen.append((path, registry_key))
        return original(path, registry_key)
    monkeypatch.setattr(raw_events, "_source_index_global", run)
    return seen


def test_same_request_reuses_one_native_inventory_then_releases(tmp_path, monkeypatch):
    ledger, _, _ = pool(tmp_path, [call(1, "w", "Write", file_path="/project/A.ets", content="a"), result(2, "w")])
    seen = calls(monkeypatch)
    with raw_events.scan_scope():
        first = raw_events.inventory(ledger)
        second = raw_events.inventory(ledger)
        assert len(seen) == 1
        assert first["events"] == second["events"]
        assert first["cache"]["request_hit"] == 0 and second["cache"]["request_hit"] == 1
        assert raw_events._SCAN_REUSE.get()["retained_bytes"] <= raw_events._REQUEST_SCAN_BUDGET
    assert raw_events._SCAN_REUSE.get() is None
    raw_events.inventory(ledger)
    assert len(seen) == 2


def test_batch_changes_pages_reuse_parsing_without_changing_evidence(tmp_path, monkeypatch):
    rows = []
    for n in range(4):
        rows.extend([call(n * 2, f"w{n}", "Write", file_path="/project/A.ets", content=str(n)), result(n * 2 + 1, f"w{n}")])
    ledger, _, _ = pool(tmp_path, rows)
    requests = [{"tool": "changes", "args": {"path": "/project/A.ets", "at": ts(9), "offset": n, "limit": 1}}
                for n in range(4)]
    expected = [investigation.query(ledger, item["tool"], item["args"]) for item in requests]
    seen = calls(monkeypatch)
    got = investigation.batch(ledger, requests, 200000)
    assert len(seen) == 1
    assert [item["data"] for item in got["items"]] == expected
    assert all(item["status"] == "ok" for item in got["items"])
    assert raw_events._SCAN_REUSE.get() is None


def test_source_change_invalidates_reuse_and_original_reference(tmp_path, monkeypatch):
    ledger, _, path = pool(tmp_path, [message(1, "original content")])
    seen = calls(monkeypatch)
    old = transcript_store.read_record(str(path), 1).ref
    with raw_events.scan_scope():
        raw_events.inventory(ledger)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(call(2, "new", "Read", file_path="/project/A.ets")) + "\n")
        got = raw_events.inventory(ledger)
        assert len(seen) == 2 and len(got["events"]) == 1
        assert got["cache"]["request_hit"] == 0
        # Change size as well: rapid equal-length rewrites may share a Windows
        # mtime tick. The cache contract is mtime/size, not a file signature.
        path.write_text(path.read_text(encoding="utf-8").replace("original content", "changed and longer content!"), encoding="utf-8")
        raw_events.inventory(ledger)
        assert len(seen) == 3
        with pytest.raises(ValueError):
            transcript_store.resolve(ledger, old)


def test_owner_registry_changes_and_agent_scope_do_not_reuse_wrong_pool(tmp_path, monkeypatch):
    ledger, agent, path = pool(tmp_path, [call(1, "r", "Read", file_path="/project/A.ets"), result(2, "r")])
    seen = calls(monkeypatch)
    with raw_events.scan_scope():
        first = raw_events._scan(ledger)
        ledger.agents["new-owner"] = atoms.AgentRec("new-owner", "session", sources=[str(path)])
        second = raw_events._scan(ledger)
        assert len(seen) == 2
        assert first["events"][0].agents == {agent}
        assert second["events"][0].agents == {agent, "new-owner"}
        scoped = raw_events._scan(ledger, agent)
        # Parsed bytes can be reused; owners/agent scope are freshly projected.
        assert len(seen) == 2 and scoped["events"][0].agents == {agent}


def test_missing_source_appears_and_public_metadata_cannot_poison_cache(tmp_path, monkeypatch):
    ledger, _, _ = pool(tmp_path, [message(1, "source")])
    missing = tmp_path / "agent-b2222222222222222.jsonl"
    ledger.agents["missing-owner"] = atoms.AgentRec("missing-owner", "session", sources=[str(missing)])
    seen = calls(monkeypatch)
    with raw_events.scan_scope():
        first = raw_events.inventory(ledger)
        expected_gaps = deepcopy(first["gaps"])
        first["gaps"].clear()
        first["source_signatures"].clear()
        second = raw_events.inventory(ledger)
        assert len(seen) == 1 and second["gaps"] == expected_gaps
        assert second["source_signatures"]
        missing.write_text(json.dumps(message(2, "new source")) + "\n", encoding="utf-8")
        third = raw_events.inventory(ledger)
        assert len(seen) == 2 and not third["gaps"]


def test_nested_scope_and_exception_do_not_retain_request_memory(tmp_path):
    ledger, _, _ = pool(tmp_path, [message(1, "source")])
    state = None
    with pytest.raises(RuntimeError):
        with raw_events.scan_scope():
            raw_events.inventory(ledger)
            state = raw_events._SCAN_REUSE.get()
            with raw_events.scan_scope():
                assert raw_events._SCAN_REUSE.get() is state
            assert state["indexes"]
            raise RuntimeError("abort")
    assert raw_events._SCAN_REUSE.get() is None and state == {}


def test_oversized_request_inventory_is_served_without_retention(tmp_path, monkeypatch):
    ledger, _, _ = pool(tmp_path, [message(1, "source" * 100)])
    monkeypatch.setattr(raw_events, "_REQUEST_SCAN_BUDGET", 128)
    seen = calls(monkeypatch)
    with raw_events.scan_scope():
        first = raw_events.inventory(ledger)
        second = raw_events.inventory(ledger)
        assert len(seen) == 2
        assert first["events"] == second["events"]
        assert not raw_events._SCAN_REUSE.get()["indexes"]


def test_reused_index_still_applies_each_query_time_projection(tmp_path):
    ledger, _, _ = pool(tmp_path, [call(1, "r", "Read", file_path="/project/A.ets"),
                                  result(8, "r", "FUTURE_TEXT")])
    with raw_events.scan_scope():
        after = raw_events.query(ledger, ts(9))
        before = raw_events.query(ledger, ts(3))
        assert after["events"][0]["status"] == "returned"
        assert before["events"][0]["status"] == "pending_or_unknown"
        assert before["events"][0]["results"] == []
        assert "FUTURE_TEXT" not in str(before)
