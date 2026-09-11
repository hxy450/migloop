"""Weigh immutable native indexes once, without widening either memory budget."""
from migloop import raw_events
from tests.test_scan_reuse_review import raw_pool
from tests.test_temporal_atom import call, result, ts


def test_request_admission_reuses_global_weight_without_rewalking_bodies(tmp_path, monkeypatch):
    ledger, _ = raw_pool(tmp_path, [call(1, "write", "Write", file_path="/project/A.ets", content="x" * 10000), result(2, "write")])
    original, measured = raw_events._retained_size, []

    def count(value, ceiling):
        measured.append(ceiling)
        return original(value, ceiling)

    monkeypatch.setattr(raw_events, "_retained_size", count)
    with raw_events.scan_scope():
        first = raw_events.query(ledger, ts(3))
        second = raw_events.query(ledger, ts(3))
        state = raw_events._request_state()
        assert state["indexes"] and state["retained_bytes"] <= raw_events._REQUEST_SCAN_BUDGET
    assert len(measured) == 1
    assert first["events"] == second["events"]
    assert "_retained_bytes" not in str(first) and "_weighed_to" not in str(first)


def test_weight_lower_bound_cannot_admit_an_oversized_index(tmp_path, monkeypatch):
    ledger, _ = raw_pool(tmp_path, [call(1, "write", "Write", file_path="/project/A.ets", content="x" * 200000), result(2, "write")])
    monkeypatch.setattr(raw_events, "_MAX_SOURCE_CACHE_BYTES", 1024)
    monkeypatch.setattr(raw_events, "_REQUEST_SCAN_BUDGET", 2048)
    with raw_events.scan_scope():
        result_data = raw_events.query(ledger, ts(3))
        state = raw_events._request_state()
        assert not state["indexes"] and state["retained_bytes"] <= 2048
    assert result_data["events"] and raw_events._CACHE_BYTES <= raw_events._CACHE_BUDGET
