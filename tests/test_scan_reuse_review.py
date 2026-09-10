"""Independent request-scan audit, adapted to request-local source admission.

Before the per-source replacement, the initial joint run had 14 passes and
three strict xfails: mid-scan registry changes returned addressable old data,
child Tasks refilled a released parent dict, and mutable tool names aliased the
cache. Those counterexamples remain below as ordinary regressions.
The first per-source revision also raised KeyError if an agent gained a source
between separate pool/agent registry snapshots; its shared-snapshot correction
is covered by the final explicit-retry regression.

No production changes or real pools. The mtime_ns/size cache signature is not a
cryptographic source digest: equal-length rewrites within a filesystem timestamp
tick are outside its invalidation guarantee. Explicit mutation tests change
size; they do not hide that limitation by hashing every source on each lookup.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextvars import copy_context
import json
import threading

import pytest

from migloop import atoms, raw_events, transcript_store
from tests.test_temporal_atom import call, message, result, ts


def raw_pool(tmp_path, rows, *, owner="owner-a", name="native.jsonl"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    ledger = atoms.build_ledger({owner: atoms.AgentRec(owner, "session", sources=[str(path)])})
    return ledger, path


def count_global_lookups(monkeypatch):
    seen, original = [], raw_events._source_index_global
    def counted(path, registry_key):
        seen.append((path, registry_key))
        return original(path, registry_key)
    monkeypatch.setattr(raw_events, "_source_index_global", counted)
    return seen


def test_late_result_never_associates_earlier_file_query_after_cache_warmup(tmp_path, monkeypatch):
    ledger, _ = raw_pool(tmp_path, [call(1, "r", "Read", file_path="/p/Other.ets"),
                                    result(8, "r", "future mention /p/Target.ets")])
    seen = count_global_lookups(monkeypatch)
    with raw_events.scan_scope():
        after = raw_events.query(ledger, ts(9), path="/p/Target.ets")
        before = raw_events.query(ledger, ts(3), path="/p/Target.ets")
        result_only = raw_events.query(ledger, ts(9), since_ts=ts(5), path="/p/Target.ets")
    assert len(seen) == 1 and len(after["events"]) == 1
    assert before["events"] == [] and "future mention" not in json.dumps(before)
    assert result_only["events"][0]["status"] == "result_only"
    assert not result_only["events"][0]["uses"]
    assert result_only["events"][0]["relation"] is None


def test_duplicate_basename_outside_selected_owner_invalidates_addressability(tmp_path, monkeypatch):
    ledger, _ = raw_pool(tmp_path / "first", [call(1, "r", "Read", file_path="/p/A.ets")])
    _, duplicate = raw_pool(tmp_path / "second", [message(2, "other owner")])
    seen = count_global_lookups(monkeypatch)
    with raw_events.scan_scope():
        first = raw_events.query(ledger, ts(9), agent="owner-a")
        ledger.agents["owner-b"] = atoms.AgentRec("owner-b", "session", sources=[str(duplicate)])
        second = raw_events.query(ledger, ts(9), agent="owner-a")
    assert len(seen) == 2 and first["events"][0]["reference_status"] == "addressable"
    assert second["events"][0]["reference_status"] == "ambiguous_source"
    assert not second["complete"] and second["source_count"] == 1
    with pytest.raises(ValueError, match="ambiguous"):
        transcript_store.resolve(ledger, first["events"][0]["uses"][0]["ref"])


def test_known_public_nested_metadata_does_not_poison_retained_scan(tmp_path):
    ledger, _ = raw_pool(tmp_path, [call(1, "r", "Read", file_path="/p/A.ets"),
                                    result(2, "r"), message(3, "unknown")])
    with raw_events.scan_scope():
        first = raw_events.inventory(ledger)
        expected = deepcopy(first)
        first["events"][0]["agents"].append("forged-owner")
        first["events"][0]["use"]["fields"]["input"]["ref"] = "forged"
        first["events"][0]["results"].clear()
        first["unknown_records"][0]["fields"].append("/forged")
        first["cache"]["hit"] = 9999
        second = raw_events.inventory(ledger)
    assert second["events"] == expected["events"]
    assert second["unknown_records"] == expected["unknown_records"]
    assert second["cache"]["hit"] != 9999


def test_cache_stats_on_reuse_count_source_hits_not_cached_owner_graphs(tmp_path):
    ledger, _ = raw_pool(tmp_path, [call(1, "r", "Read", file_path="/p/A.ets")])
    with raw_events.scan_scope():
        first = raw_events.inventory(ledger)
        second = raw_events.inventory(ledger)
    assert first["cache"]["request_hit"] == 0 and second["cache"]["request_hit"] == 1
    for name in ("hit", "miss", "oversize_not_cached"):
        assert second["cache"][name] == 0
    assert sum(first["cache"][name] for name in ("hit", "miss", "oversize_not_cached", "request_hit")) == 1
    assert second["cache"]["request_budget_bytes"] == raw_events._REQUEST_SCAN_BUDGET
    assert raw_events._SCAN_REUSE.get() is None


def test_native_event_payload_is_included_in_request_retention_limit(tmp_path, monkeypatch):
    ledger, _ = raw_pool(tmp_path, [call(1, "w", "Write", file_path="/p/A.ets", content="x" * 100000)])
    scan = raw_events._scan_uncached(ledger)
    assert raw_events._retained_size(scan["events"][0], 1_000_000) > 100000
    monkeypatch.setattr(raw_events, "_REQUEST_SCAN_BUDGET", 8000)
    seen = count_global_lookups(monkeypatch)
    with raw_events.scan_scope():
        first = raw_events.inventory(ledger)
        second = raw_events.inventory(ledger)
        state = raw_events._SCAN_REUSE.get()
        assert not state["indexes"]
        assert state["retained_bytes"] == sum(entry[-1] for entry in state["skipped"].values())
        assert state["retained_bytes"] <= raw_events._REQUEST_SCAN_BUDGET
    assert len(seen) == 2 and first["events"] == second["events"]


def test_independent_http_style_threads_have_separate_scope_and_release(tmp_path):
    ledger, _ = raw_pool(tmp_path, [call(1, "r", "Read", file_path="/p/A.ets")])
    barrier = threading.Barrier(2)
    def request(_):
        with raw_events.scan_scope():
            state = raw_events._SCAN_REUSE.get()
            raw_events.inventory(ledger)
            barrier.wait(timeout=5)
            identity = id(state)
            assert state["indexes"]
        assert raw_events._SCAN_REUSE.get() is None and state == {}
        return identity
    with ThreadPoolExecutor(max_workers=2) as executor:
        identities = list(executor.map(request, range(2)))
    assert identities[0] != identities[1]


def test_mid_scan_duplicate_registry_change_cannot_return_addressable_old_inventory(tmp_path, monkeypatch):
    ledger, _ = raw_pool(tmp_path / "first", [call(1, "r", "Read", file_path="/p/A.ets")])
    _, duplicate = raw_pool(tmp_path / "second", [message(2, "new duplicate source")])
    original, mutated = raw_events._source_index, False
    def change_after_source(path, registry_key):
        nonlocal mutated
        data = original(path, registry_key)
        if not mutated:
            ledger.agents["owner-b"] = atoms.AgentRec("owner-b", "session", sources=[str(duplicate)])
            mutated = True
        return data
    # Mutate inside the scan, after a source read but before registry recheck.
    monkeypatch.setattr(raw_events, "_source_index", change_after_source)
    try:
        with raw_events.scan_scope():
            got = raw_events.inventory(ledger)
    except ValueError:
        return  # Explicit unstable-source rejection is also safe.
    assert not got["complete"]
    assert all(not event["id_unique_in_registry"] for event in got["events"])


def test_inherited_child_task_cannot_repopulate_released_parent_scope(tmp_path):
    ledger, _ = raw_pool(tmp_path, [call(1, "r", "Read", file_path="/p/A.ets")])
    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        async def child():
            started.set()
            await release.wait()
            with raw_events.scan_scope():
                state = raw_events._SCAN_REUSE.get()
                raw_events.inventory(ledger)
            # reset(token) may restore the inactive inherited parent dictionary;
            # it must not restore a usable cache owned by this child execution.
            return state, raw_events._request_state()
        with raw_events.scan_scope():
            parent_state = raw_events._SCAN_REUSE.get()
            raw_events.inventory(ledger)
            task = asyncio.create_task(child())
            await started.wait()
        assert parent_state == {} and raw_events._SCAN_REUSE.get() is None
        release.set()
        child_state, remaining = await task
        assert child_state is not parent_state
        assert child_state == {} and remaining is None and parent_state == {}
    asyncio.run(exercise())


def test_mutable_unrecognized_native_tool_name_cannot_poison_cache(tmp_path):
    ledger, _ = raw_pool(tmp_path, [call(1, "r", {"display": ["original"]}, file_path="/p/A.ets")])
    with raw_events.scan_scope():
        first = raw_events.inventory(ledger)
        first["events"][0]["tool"]["display"][0] = "forged from consumer"
        second = raw_events.inventory(ledger)
    assert second["events"][0]["tool"] == {"display": ["original"]}


def test_copied_context_threads_do_not_borrow_active_parent_indexes(tmp_path):
    ledger, _ = raw_pool(tmp_path, [call(1, "r", "Read", file_path="/p/A.ets")])
    barrier = threading.Barrier(2)
    with raw_events.scan_scope():
        parent_state = raw_events._request_state()
        raw_events.inventory(ledger)
        def child():
            assert raw_events._request_state() is None
            with raw_events.scan_scope():
                own = raw_events._request_state()
                raw_events.inventory(ledger)
                barrier.wait(timeout=5)
                assert own is not parent_state and own["indexes"]
                identity = id(own)
            assert own == {} and raw_events._request_state() is None
            return identity
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(copy_context().run, child) for _ in range(2)]
            identities = [future.result(timeout=10) for future in futures]
        assert identities[0] != identities[1] and parent_state["indexes"]
    assert parent_state == {}


def test_first_fit_retains_earlier_indexes_and_accounts_skip_guard(tmp_path, monkeypatch):
    ledger, _ = raw_pool(tmp_path, [call(1, "a", "Read", file_path="/p/A.ets")], name="a.jsonl")
    for name in ("b", "c"):
        _, path = raw_pool(tmp_path, [call(1, name, "Read", file_path="/p/A.ets")], name=name + ".jsonl")
        ledger.agents[name] = atoms.AgentRec(name, "session", sources=[str(path)])
    measure = raw_events._retained_size
    def fixed_cost(value, ceiling):
        if isinstance(value, tuple) and len(value) == 3 and isinstance(value[2], dict) and "native" in value[2]:
            return 100
        if isinstance(value, tuple) and len(value) == 2:
            return 20
        return measure(value, ceiling)
    monkeypatch.setattr(raw_events, "_retained_size", fixed_cost)
    monkeypatch.setattr(raw_events, "_REQUEST_SCAN_BUDGET", 220)
    seen = count_global_lookups(monkeypatch)
    with raw_events.scan_scope():
        first = raw_events.inventory(ledger)
        state = raw_events._request_state()
        admitted = set(state["indexes"])
        assert len(admitted) == 2 and len(state["skipped"]) == 1
        assert state["retained_bytes"] == 220
        second = raw_events.inventory(ledger)
        assert set(state["indexes"]) == admitted
        assert second["cache"]["request_hit"] == 2
        assert state["retained_bytes"] == sum(v[-1] for v in state["indexes"].values()) + sum(v[-1] for v in state["skipped"].values())
    assert len(seen) == 4 and first["events"] == second["events"] and state == {}


def test_registry_change_between_pool_and_agent_snapshots_is_explicit_retry(tmp_path, monkeypatch):
    ledger, _ = raw_pool(tmp_path, [call(1, "a", "Read", file_path="/p/A.ets")], name="a.jsonl")
    _, new_path = raw_pool(tmp_path, [call(2, "b", "Read", file_path="/p/B.ets")], name="b.jsonl")
    original, changed = transcript_store.sources, False
    def registering(ledger_arg, agent=None):
        nonlocal changed
        selected = original(ledger_arg, agent)
        if ledger_arg is ledger and agent is None and not changed:
            ledger.agents["owner-a"].sources.append(str(new_path))
            changed = True
        return selected
    monkeypatch.setattr(transcript_store, "sources", registering)
    with raw_events.scan_scope(), pytest.raises(ValueError, match="registered source/owner mapping changed"):
        raw_events.query(ledger, ts(9), agent="owner-a")
