"""Unknown attribution can expose bounded navigation without inventing an author."""
from copy import deepcopy

import pytest

from migloop import atoms, atoms_text
from tests.test_atoms import MAIN_ID, _call, _ledger


TARGET = "/proj/entry/A.ets"


def fixture(tmp_path):
    return _ledger(tmp_path, [
        *_call("2026-01-01T00:00:00Z", "seed", "Write", {"file_path": TARGET, "content": "a\n"}),
        *_call("2026-01-01T00:00:10Z", "gap", "Edit", {"file_path": TARGET, "old_string": "missing", "new_string": "b"}),
        *_call("2026-01-01T00:00:20Z", "edit", "Edit", {"file_path": TARGET, "old_string": "b", "new_string": "c"}),
    ])


def recovery(ledger, v=3):
    result = atoms.blame(ledger, TARGET, v, changed=True)
    assert result["known"] is False and result["lines"] == [] and result["summary"] == []
    return result["recovery"]


def test_unknown_changed_blame_returns_real_snapshot_and_native_patch_without_line_owner(tmp_path):
    ledger = fixture(tmp_path)
    diag = recovery(ledger)
    assert diag["nearest_snapshot"]["v"] == 1
    assert diag["nearest_snapshot"]["writer"] == {"id": MAIN_ID, "v": 1}
    assert diag["nearest_snapshot"]["event"]["ref"].endswith("@L1")
    assert diag["first_gap"]["reason"] == "edit-miss"
    assert diag["target_patch"]["kind"] == "native"
    assert "-b" in diag["target_patch"]["text"] and "+c" in diag["target_patch"]["text"]
    assert diag["intervening"]["formal_versions"]["count"] == 1
    assert diag["semantic_checked"] is False
    assert any(q["tool"] == "agent" and q["args"] == {"id": MAIN_ID, "v": 1, "reads": True} for q in diag["next_queries"])
    text = atoms_text.render_blame(ledger, TARGET, 3, changed=True)
    assert "最近可靠全文" in text and "不是被替换行作者" in text and "edit-miss" in text
    assert "@L1" in text and "-b" in text


@pytest.mark.parametrize("mutation", ["sealed", "failed", "missing_time", "late_done", "ambiguous_pointer"])
def test_snapshot_selector_fails_closed_on_unavailable_or_untrusted_anchor(tmp_path, mutation):
    ledger = fixture(tmp_path)
    first = ledger.agents[MAIN_ID].actions[0]
    version = ledger.stories[TARGET].versions[0]
    if mutation == "sealed":
        version.sealed = True
    elif mutation == "failed":
        first.ok = False
    elif mutation == "missing_time":
        first.done_ts = None
    elif mutation == "late_done":
        first.done_ts = "2026-01-01T00:00:21Z"
    else:
        ledger.loc_ambiguous.add(next(key for key, seq in ledger.by_loc.items() if seq == first.seq))
    assert recovery(ledger)["nearest_snapshot"] is None


def test_unknown_cutoff_does_not_guess_temporal_scope(tmp_path):
    ledger = fixture(tmp_path)
    ledger.stories[TARGET].versions[-1].ts = "no-time"
    diag = recovery(ledger)
    assert diag["scope"]["status"] == "unknown"
    assert diag["nearest_snapshot"] is None
    assert all(not bucket["count_checked"] for bucket in diag["intervening"].values())


def test_future_sealed_previous_version_is_not_reused_as_available_history(tmp_path):
    ledger = fixture(tmp_path)
    previous = ledger.stories[TARGET].versions[1]
    previous.content, previous.sealed = "future read\n", True
    assert recovery(ledger)["nearest_snapshot"]["v"] == 1


def test_overlapping_failed_or_unfinished_candidate_prevents_snapshot_certification(tmp_path):
    ledger = fixture(tmp_path)
    action = deepcopy(ledger.agents[MAIN_ID].actions[1])
    action.seq = 100
    action.ts, action.done_ts, action.ok = "2026-01-01T00:00:00.500Z", None, None
    action.files, action.ver = [], None
    action.detail = {"effect_candidates": [TARGET], "unfinished": True}
    ledger.agents[MAIN_ID].actions.append(action)
    diag = recovery(ledger)
    assert diag["nearest_snapshot"] is None
    assert diag["intervening"]["explicit_effect_candidates"]["count"] == 1
    row = diag["intervening"]["explicit_effect_candidates"]["items"][0]
    assert row["temporal_relation"] == "overlaps_cutoff" and row["writer_confirmed"] is False


def test_failed_write_stays_candidate_and_bins_are_bounded_and_distinct(tmp_path):
    ledger = fixture(tmp_path)
    for i in range(6):
        action = deepcopy(ledger.agents[MAIN_ID].actions[1])
        action.seq = 100 + i
        action.ts = f"2026-01-01T00:00:{12+i:02d}Z"
        action.done_ts = f"2026-01-01T00:00:{13+i:02d}Z"
        action.ok, action.ver, action.files = False, None, []
        action.detail = {"effect_candidates": [TARGET], "touched": [TARGET]}
        ledger.agents[MAIN_ID].actions.append(action)
    diag = recovery(ledger)
    bucket = diag["intervening"]["explicit_effect_candidates"]
    assert bucket["count"] == 6 and len(bucket["items"]) == 3 and bucket["remainder"] == 3
    assert all(item["tool_status"] is False and not item["writer_confirmed"] for item in bucket["items"])
    assert all(len(bucket["items"]) <= 3 for bucket in diag["intervening"].values())


def test_first_recorded_delta_is_not_called_file_creation(tmp_path):
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:00Z", "edit", "Edit", {"file_path": TARGET, "old_string": "a", "new_string": "b"}))
    result = atoms.blame(ledger, TARGET, 1, changed=True)
    assert "无前版记录" in result["note"] and "不是必然新建" in result["note"]
    assert "-a" in result["recovery"]["target_patch"]["text"]


def test_plain_unknown_blame_gets_same_recovery_but_known_blame_stays_unchanged(tmp_path):
    ledger = fixture(tmp_path)
    assert atoms.blame(ledger, TARGET, 3)["recovery"] == recovery(ledger)
    assert "recovery" not in atoms.blame(ledger, TARGET, 1)


def test_recovery_query_is_read_only(tmp_path):
    ledger = fixture(tmp_path)
    before = deepcopy(ledger)
    recovery(ledger)
    assert ledger == before


def add_mention(ledger, *, ambiguous=False, where="in", done="2026-01-01T00:00:13Z"):
    action = atoms.Action("2026-01-01T00:00:12Z", 100, "Bash", "other", done_ts=done,
                          tuid="mention", detail={"mentions": [(TARGET, "printed target", TARGET, where, "other")]})
    ledger.agents[MAIN_ID].actions.append(action)
    mention = atoms.Mention(action.ts, action.seq, MAIN_ID, 3, TARGET, "printed target",
                            ambiguous=ambiguous, where=where)
    ledger.mentions.setdefault(TARGET, []).extend([mention, deepcopy(mention)])


def test_pure_target_mentions_deduplicate_without_becoming_write_barriers(tmp_path):
    ledger = fixture(tmp_path)
    add_mention(ledger)
    diag = recovery(ledger)
    assert diag["nearest_snapshot"]["v"] == 1
    assert diag["intervening"]["explicit_effect_candidates"]["count"] == 0
    assert diag["intervening"]["unverified_target_mentions"]["count"] == 1


@pytest.mark.parametrize("kwargs", [{"ambiguous": True}, {"where": "out", "done": "2026-01-01T00:00:25Z"}])
def test_ambiguous_or_postcutoff_output_mentions_do_not_enter_window(tmp_path, kwargs):
    ledger = fixture(tmp_path)
    add_mention(ledger, **kwargs)
    assert recovery(ledger)["intervening"]["unverified_target_mentions"]["count"] == 0


def test_ambiguous_native_patch_pointer_does_not_supply_copyable_reference(tmp_path):
    ledger = fixture(tmp_path)
    action = ledger.agents[MAIN_ID].actions[-1]
    ledger.loc_ambiguous.add(next(key for key, seq in ledger.by_loc.items() if seq == action.seq))
    patch = recovery(ledger)["target_patch"]
    assert patch["available"] is False and patch["text"] == "" and patch["event"]["ref"] is None


def test_inconsistent_ref_proof_cannot_certify_the_version_snapshot(tmp_path):
    from dataclasses import replace
    ledger = fixture(tmp_path)
    ref = ledger.agents[MAIN_ID].actions[0].files[0]
    ref.ev = replace(ref.ev, proof=replace(ref.proof, execution="unknown"))
    assert recovery(ledger)["nearest_snapshot"] is None


def test_pending_call_has_copyable_input_locator_without_result_proof(tmp_path):
    from migloop.blame_recovery import _event
    ledger = fixture(tmp_path)
    action = ledger.agents[MAIN_ID].actions[1]
    action.src = (action.src[0], action.src[1], None)
    action.ok, action.done_ts = None, None
    event = _event(ledger, MAIN_ID, action)
    assert event["call_located"] is True and event["ref"].endswith("@L3")
    assert event["result_located"] is False and event["result_line"] is None


def test_success_metadata_without_result_locator_cannot_certify_snapshot(tmp_path):
    ledger = fixture(tmp_path)
    action = ledger.agents[MAIN_ID].actions[0]
    action.src = (action.src[0], action.src[1], None)
    assert recovery(ledger)["nearest_snapshot"] is None


def test_same_call_formal_part_does_not_hide_explicit_unknown_effect(tmp_path):
    ledger = fixture(tmp_path)
    action = ledger.agents[MAIN_ID].actions[1]
    action.detail.update(effect_candidates=[TARGET], touched=[TARGET], conditional=[TARGET])
    diag = recovery(ledger)
    assert diag["intervening"]["formal_versions"]["count"] == 1
    bucket = diag["intervening"]["explicit_effect_candidates"]
    assert bucket["count"] == 1
    assert bucket["items"][0]["also_recorded_versions"] == [2]
    assert bucket["items"][0]["writer_confirmed"] is False


def test_native_full_part_with_unknown_same_call_effect_is_not_a_safe_snapshot(tmp_path):
    ledger = fixture(tmp_path)
    action = ledger.agents[MAIN_ID].actions[0]
    action.detail["effect_candidates"] = [TARGET]
    diag = recovery(ledger)
    assert diag["nearest_snapshot"] is None
    assert diag["intervening"]["explicit_effect_candidates"]["items"][0]["also_recorded_versions"] == [1]
