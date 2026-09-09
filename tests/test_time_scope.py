"""Time overviews describe observed windows, not completeness or build validation."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from migloop import atoms, time_scope


def agent(aid, session, times, *, versions=()):
    return atoms.AgentRec(aid, session, actions=[atoms.Action(use, i, "tool", "other", done_ts=done,
        ver=versions[i - 1] if i <= len(versions) else None, src=(f"/not-on-disk/{session}.jsonl", i, i + 1))
        for i, (use, done) in enumerate(times, 1)])


def ledger(*agents):
    return atoms.Ledger({}, {a.id: a for a in agents})


def test_c4_aug17_anchor_exposes_supplied_aug21_root_without_validation_claim():
    early = agent("__main__:01a009fe", "01a009fe", [
        ("2026-08-16T09:00:00Z", "2026-08-17T08:00:00Z")], versions=(252,))
    later = agent("__main__:01a021e5", "01a021e5", [
        ("2026-08-21T09:00:00Z", "2026-08-21T10:00:00Z")], versions=(231,))
    result = time_scope.overview(ledger(early, later), "2026-08-17T09:00:00Z", early.id)
    assert result["schema"] == "migloop-time-scope/1"
    assert result["other_later_sessions"] == ["01a021e5"]
    row = result["roots"][1]
    assert row["root_agent"] == later.id and row["root_versions"] == {"first": 231, "last": 231, "count": 1}
    assert row["after_anchor"] == {"started": 1, "results_returned": 1, "observed_actions": 1, "known_straddling": 0}
    assert result["search_window"] == {"since_ts": "2026-08-17T09:00:00.000000Z", "until_ts": "2026-08-21T10:00:00.000000Z"}
    assert result["latest_known_pool_time"] == result["search_window"]["until_ts"]
    assert not result["scope_complete"] and not result["negative_proof"] and "不证明" in result["scope"]
    assert "q" not in result["search_window"] and "sid" not in result["search_window"]


def test_late_tool_result_is_not_treated_as_available_before_its_call_finished():
    main = agent("__main__:a", "a", [("2026-08-17T00:00:00Z", "2026-08-17T00:10:00Z")])
    result = time_scope.overview(ledger(main), "2026-08-17T00:05:00Z", main.id)
    row = result["roots"][0]
    assert row["after_anchor"] == {"started": 0, "results_returned": 1, "observed_actions": 1, "known_straddling": 1}
    assert row["observed_use"]["max"] == "2026-08-17T00:00:00.000000Z"
    assert row["observed_done"]["max"] == "2026-08-17T00:10:00.000000Z"
    assert result["other_later_sessions"] == []


def test_noncanonical_iso_offsets_normalize_before_sorting_and_counting():
    first = agent("__main__:first", "full-uuid-session", [
        ("2026-08-21 08:00:00+08:00", "2026-08-20T22:30:00-02:00")], versions=(1,))
    second = agent("__main__:second", "second", [("2026-08-20T23:50:00+00:00", "2026-08-21T00:00:00.123456Z")])
    result = time_scope.overview(ledger(first, second), "2026-08-21T02:15:00+02:00", first.id)
    assert [r["session"] for r in result["roots"]] == ["second", "full-uuid-session"]
    row = result["roots"][1]
    assert row["observed_start"] == "2026-08-21T00:00:00.000000Z"
    assert row["observed_end"] == "2026-08-21T00:30:00.000000Z"
    assert row["after_anchor"]["started"] == 0 and row["after_anchor"]["results_returned"] == 1


def test_missing_done_and_unknown_use_do_not_create_precise_intervals():
    main = agent("__main__:a", "a", [("2026-08-17T00:00:00Z", None),
        ("2026-08-17T00:06:00Z", None), ("not-a-time", "2026-08-17T00:07:00Z"),
        ("2026-08-17T00:08:00", "")])
    result = time_scope.overview(ledger(main), "2026-08-17T00:05:00Z")
    row = result["roots"][0]
    assert row["unknown_timestamps"] == {"use_missing": 0, "use_invalid": 2, "done_missing": 3, "done_invalid": 0}
    assert row["unknown_intervals"] == 4 and row["after_anchor"]["known_straddling"] == 0
    assert row["after_anchor"]["started"] == 1 and row["after_anchor"]["results_returned"] == 1
    assert row["after_anchor"]["observed_actions"] == 2
    assert result["latest_known_pool_time"] == "2026-08-17T00:07:00.000000Z"


def test_missing_external_root_is_not_fabricated_or_loaded():
    child = agent("agent-supplied", "missing-root-session", [("2026-08-21T00:00:00Z", None)], versions=(4,))
    child.parent = "__main__:not-supplied"
    result = time_scope.overview(ledger(child), "2026-08-17T00:00:00Z", child.parent)
    row = result["roots"][0]
    assert not row["root_present"] and row["root_agent"] is None and row["root_versions"] is None
    assert row["root_agents"] == [] and row["agent_count"] == 1
    assert result["later_sessions"] == ["missing-root-session"] and result["other_later_sessions"] is None
    assert result["diagnostics"] and result["agent_count"] == 1


def test_multiple_root_records_in_same_declared_session_remain_ambiguous():
    result = time_scope.overview(ledger(
        agent("__main__:a", "same", [("2026-08-17T00:00:00Z", None)], versions=(1,)),
        agent("__main__:b", "same", [("2026-08-21T00:00:00Z", None)], versions=(7,))))
    row = result["roots"][0]
    assert row["root_present"] and row["root_ambiguous"] and row["root_agent"] is None
    assert row["root_versions"] is None and len(row["root_agents"]) == 2


@pytest.mark.parametrize("anchor", [None, "", "not-iso", "2026-08-17T00:00:00"])
def test_unknown_anchor_does_not_emit_zero_after_counts_or_a_search_window(anchor):
    main = agent("__main__:a", "a", [("2026-08-21T00:00:00Z", None)])
    result = time_scope.overview(ledger(main), anchor)
    assert result["roots"][0]["after_anchor"] is None
    assert result["later_sessions"] is None and result["search_window"] is None
    assert result["anchor"]["status"] == ("unanchored" if anchor is None else "invalid")


def test_empty_ledger_is_not_a_global_negative_proof():
    result = time_scope.overview(ledger(), "2026-08-17T00:00:00Z")
    assert result["roots"] == [] and result["latest_known_pool_time"] is None
    assert result["search_window"] is None and not result["negative_proof"] and not result["scope_complete"]


def test_reversed_times_are_flagged_not_silently_reordered_into_an_interval():
    main = agent("__main__:a", "a", [("2026-08-21T00:00:00Z", "2026-08-17T00:00:00Z")])
    result = time_scope.overview(ledger(main), "2026-08-19T00:00:00Z")
    row = result["roots"][0]
    assert row["reversed_intervals"] == 1 and row["after_anchor"]["known_straddling"] == 0
    assert row["after_anchor"]["started"] == 1 and row["after_anchor"]["results_returned"] == 0


def test_output_is_json_serializable_and_inputs_are_not_mutated():
    main = agent("__main__:a", "a", [("2026-08-17T00:00:00Z", "2026-08-17T01:00:00Z")], versions=(1,))
    source = ledger(main)
    before = deepcopy(source)
    result = time_scope.overview(source, "2026-08-17T00:30:00Z", main.id)
    assert source == before and source._identity is None
    assert json.loads(json.dumps(result)) == result


def test_for_file_uses_the_unique_selected_payload_version_without_guessing_latest():
    root = agent("__main__:a", "a", [("2026-08-17T00:00:00Z", "2026-08-21T00:00:00Z")])
    payload = {"path": "/proj/F.ets", "v": 1, "versions": [
        {"v": 1, "ts": "2026-08-17T00:00:00Z", "by": root.id},
        {"v": 2, "ts": "2026-08-18T00:00:00Z", "by": "other"}]}
    result = time_scope.for_atom(ledger(root), "file", payload)
    assert result["anchor"]["time"] == "2026-08-17T00:00:00.000000Z"
    assert result["anchor"]["agent"] == root.id and result["anchor"]["basis"] == "file_version"
    assert result["anchor"]["key"] == payload["path"]
    assert result["roots"][0]["after_anchor"]["results_returned"] == 1


def test_agent_until_uses_call_start_not_later_completed_output():
    root = agent("__main__:a", "a", [("2026-08-17T00:01:00Z", "2026-08-17T00:09:00Z"),
        ("2026-08-17T00:05:00Z", "2026-08-17T00:06:00Z")], versions=(None, 1))
    payload = {"id": root.id, "v": 1, "actions": [{"seq": 1, "ts": "2099-01-01T00:00:00Z"}]}
    selected = time_scope.for_atom(ledger(root), "agent", payload)
    assert selected["anchor"]["time"] == "2026-08-17T00:05:00.000000Z"
    limited = time_scope.for_atom(ledger(root), "agent", payload, until=1)
    assert limited["anchor"]["time"] == "2026-08-17T00:01:00.000000Z"
    assert limited["anchor"]["basis"] == "agent_until_use"
    assert limited["roots"][0]["after_anchor"]["results_returned"] == 2


@pytest.mark.parametrize("case", ["missing", "later", "invalid_ts", "foreign_agent", "duplicate", "wrong_type"])
def test_invalid_until_never_falls_back_to_an_apparently_valid_version_anchor(case):
    root = agent("__main__:a", "a", [("2026-08-17T00:05:00Z", "2026-08-17T00:06:00Z"),
        ("2026-08-17T00:02:00Z", "2026-08-17T00:10:00Z")], versions=(1, None))
    other = agent("__main__:b", "b", [("2026-08-17T00:00:00Z", None)])
    other.actions[0].seq = 99
    until = 2
    if case == "missing":
        until = 55
    elif case == "later":
        root.actions[1].ts = "2026-08-17T00:07:00Z"
    elif case == "invalid_ts":
        root.actions[1].ts = "not-known"
    elif case == "foreign_agent":
        until = 99
    elif case == "duplicate":
        root.actions.append(deepcopy(root.actions[1]))
    elif case == "wrong_type":
        until = "2"
    result = time_scope.for_atom(ledger(root, other), "agent", {"id": root.id, "v": 1}, until=until)
    assert result["anchor"]["status"] == "unknown" and result["anchor"]["time"] is None
    assert result["search_window"] is None and all(row["after_anchor"] is None for row in result["roots"])
    assert result["diagnostics"]


@pytest.mark.parametrize("kind,payload", [("file", {"v": 0, "versions": []}),
    ("file", {"v": 2, "versions": [{"v": 1, "ts": "2026-08-17T00:00:00Z"}]}),
    ("file", {"v": 1, "versions": [{"v": 1, "ts": "no-time"}]}),
    ("agent", {"id": "__main__:missing", "v": 1}), ("agent", {"id": "__main__:a", "v": 3})])
def test_unlocatable_atom_anchor_stays_unknown(kind, payload):
    root = agent("__main__:a", "a", [("2026-08-17T00:00:00Z", None)], versions=(1,))
    result = time_scope.for_atom(ledger(root), kind, payload)
    assert result["anchor"]["status"] == "unknown" and result["search_window"] is None


def test_for_atom_does_not_modify_payload_or_ledger():
    root = agent("__main__:a", "a", [("2026-08-17T00:00:00Z", None)], versions=(1,))
    source, payload = ledger(root), {"id": root.id, "v": 1}
    before = deepcopy((source, payload))
    time_scope.for_atom(source, "agent", payload)
    assert (source, payload) == before
