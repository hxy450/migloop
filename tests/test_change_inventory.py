"""Inventory effects without inventing authors, repair boundaries or state changes."""
from dataclasses import replace

import pytest

from migloop import atoms, change_inventory, transcript_store
from migloop.evidence import FileProof
from migloop.filestory import Ev
from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call
from tests.test_raw_events import pool

PATH = "/proj/A.ets"
PROOF = FileProof("native_tool", "confirmed", "content", "full")


def ts(second):
    return f"2026-01-01T00:00:{second:02d}Z"


def scope(since=None, at=30, path=PATH):
    return {"kind": "file", "key": path, "at": ts(at), "since_ts": ts(since) if since is not None else None}


def patch(second=5, *, success=True, path=PATH, **extra):
    return {"timestamp": ts(second) if second is not None else None, "type": "event_msg", "payload": {
        "type": "patch_apply_end", "call_id": "inner-id", "success": success,
        "changes": {path: {"type": "update", "unified_diff": "@@ -1 +1 @@\n-old\n+new\n"}}, **extra}}


def raw_pool(tmp_path, rows):
    ledger, path = pool(tmp_path, rows)
    return atoms.build_ledger(ledger.agents), path


def observations(tmp_path, middle=(), *, before="old\n", after="new\n"):
    return _ledger(tmp_path, [*_read_call(ts(0), "before", PATH, before), *middle,
                              *_read_call(ts(10), "after", PATH, after)])


def test_independent_native_patch_needs_no_outer_id_pair_or_invented_author(tmp_path):
    rows = [
        {"timestamp": ts(1), "type": "response_item", "payload": {"type": "custom_tool_call",
         "call_id": "outer-id", "name": "functions.exec", "input": "a wrapper"}},
        patch(),
        {"timestamp": ts(6), "type": "response_item", "payload": {"type": "custom_tool_call_output",
         "call_id": "outer-id", "output": "{}"}}]
    ledger, _ = raw_pool(tmp_path, rows)
    output = change_inventory.build(ledger, scope())
    row, = output["rows"]
    assert row["status"] == "confirmed_change" and row["agent"] is None
    assert row["native"]["call_id"] == "inner-id" and row["use_ts"] is None
    assert row["source_agents_are_not_authors"] and row["author_status"] == "unknown"
    assert transcript_store.resolve(ledger, row["evidence"][0]).line == 2
    assert not output["complete"] and not row["semantic_checked"]


@pytest.mark.parametrize("extra", [{"success": False}, {"success": None}, {"conditional": True},
                                  {"success": True, "is_error": True}, {"success": True, "exit_code": 1}])
def test_failed_conditional_or_unconfirmed_native_never_enters_confirmed(tmp_path, extra):
    ledger, _ = raw_pool(tmp_path, [patch(**extra)])
    row, = change_inventory.build(ledger, scope())["rows"]
    assert row["status"] == "candidate_effect" and row["agent"] is None


def test_native_exact_path_not_basename_and_unknown_time_is_gap(tmp_path):
    ledger, _ = raw_pool(tmp_path, [patch(path="/different/A.ets"), patch(None)])
    output = change_inventory.build(ledger, scope())
    assert output["rows"] == []
    assert any(g["reason"] == "undated_native_effect" for g in output["gaps"])


def test_native_future_effect_and_nested_report_are_not_admitted(tmp_path):
    ledger, _ = raw_pool(tmp_path, [patch(20), {"timestamp": ts(2), "type": "message",
                                             "text": "report claims /proj/A.ets changed", "quoted": patch(2)}])
    output = change_inventory.build(ledger, scope(at=10))
    assert output["rows"] == []
    assert output["unclassified_related"]["query"]["tool"] == "events"


def test_same_source_line_path_deduplicates_parsed_action_and_native_patch(tmp_path):
    _, path = raw_pool(tmp_path, [patch()])
    event = Ev(ts(5), 1, "edit", PATH, "real", old="old", new="new", proof=PROOF)
    action = atoms.Action(ts(5), 1, "apply_patch", "write", done_ts=ts(5),
                          src=(str(path), 0, 0), tuid="inner-id", files=[atoms.FileRef("write", PATH, event)])
    ledger = atoms.build_ledger({"real": atoms.AgentRec("real", "s", actions=[action], sources=[str(path)])})
    row, = change_inventory.build(ledger, scope())["rows"]
    assert row["id"] == atoms.event_id(ledger, "real", 1)
    assert row["status"] == "confirmed_change" and len(row["native_corroboration"]) == 1
    assert len(row["evidence"]) == 1
    native, gaps = change_inventory.native_effects(ledger, scope())
    assert not gaps and native[0]["raw_only"] is False


def test_two_full_reads_with_unowned_difference_produce_only_observed_interval(tmp_path):
    ledger = observations(tmp_path)
    output = change_inventory.build(ledger, scope())
    row, = output["rows"]
    assert row["status"] == "observed_change" and row["agent"] is None
    assert row["use_ts"] is row["done_ts"] is row["change_time"] is None
    assert row["observed_at"].startswith(ts(11)[:-1])
    assert row["observation_interval"]["since"].startswith(ts(0)[:-1])
    assert len(row["evidence"]) == 4 and row["unassigned_effect_ids"] == []
    assert row["boundary_relation"] == "within_scope"
    assert not output["complete"]


def test_crossing_generation_boundary_is_not_proven_post_generation_change(tmp_path):
    ledger = observations(tmp_path)
    row, = change_inventory.build(ledger, scope(since=5))["rows"]
    assert row["boundary_relation"] == "crosses_since_boundary"
    assert row["occurred_in_scope"] == "not_proven" and "不能声称" in row["summary"]
    assert row["evidence_scope"]["since_ts"] is None  # Prior-side source remains inspectable.
    assert change_inventory.build(ledger, scope(since=15))["rows"] == []


def test_first_observation_and_equal_snapshots_are_not_changes(tmp_path):
    only = tmp_path / "only"
    only.mkdir()
    ledger = _ledger(only, _read_call(ts(10), "first", PATH, "anything"))
    assert change_inventory.build(ledger, scope())["rows"] == []
    same = tmp_path / "same"
    same.mkdir()
    assert change_inventory.build(observations(same, after="old\n"), scope())["rows"] == []


@pytest.mark.parametrize("bad", ["partial", "dependency", "delivery", "snapshot", "overlap", "conditional", "failed"])
def test_unreliable_read_cannot_supply_observation_change(tmp_path, bad):
    ledger = observations(tmp_path)
    action = next(a for a in ledger.agents[MAIN_ID].actions if a.tuid == "after")
    ref = action.files[0]
    if bad == "partial": ref.ev = replace(ref.ev, full=False)
    elif bad == "dependency": ref.ev = replace(ref.ev, dep=True)
    elif bad == "delivery": ref.ev = replace(ref.ev, proof=replace(PROOF, delivery="unknown"))
    elif bad == "snapshot": ref.ev = replace(ref.ev, proof=replace(PROOF, snapshot="partial"))
    elif bad == "overlap": ref.observation_uncertain = True
    elif bad == "conditional": ref.ev = replace(ref.ev, conditional=True)
    else: action.ok = False
    assert change_inventory.build(ledger, scope())["rows"] == []


def test_single_known_write_explains_difference_without_duplicate_observed_row(tmp_path):
    ledger = observations(tmp_path, _call(ts(5), "write", "Write", {"file_path": PATH, "content": "new\n"}))
    row, = change_inventory.build(ledger, scope())["rows"]
    assert row["status"] == "confirmed_change"


def test_single_known_edit_explains_difference_without_duplicate_observed_row(tmp_path):
    ledger = observations(tmp_path, _call(ts(5), "edit", "Edit", {"file_path": PATH, "old_string": "old", "new_string": "new"}))
    row, = change_inventory.build(ledger, scope())["rows"]
    assert row["status"] == "confirmed_change"


def test_multiple_writes_or_unexplained_write_do_not_create_unique_observed_author(tmp_path):
    ledger = observations(tmp_path, [*_call(ts(3), "first", "Write", {"file_path": PATH, "content": "middle"}),
                                    *_call(ts(5), "last", "Write", {"file_path": PATH, "content": "new\n"})])
    output = change_inventory.build(ledger, scope())
    assert [r["status"] for r in output["rows"]].count("confirmed_change") == 2
    observed = next(r for r in output["rows"] if r["status"] == "observed_change")
    assert observed["agent"] is None and len(observed["unassigned_effect_ids"]) == 2


def test_conditional_parsed_operation_stays_candidate_and_pure_mention_is_not_candidate(tmp_path):
    ledger = observations(tmp_path, _call(ts(5), "possible", "Bash", {"command": "false && printf x > /proj/A.ets; true"}, out=""))
    output = change_inventory.build(ledger, scope())
    assert not any(r["status"] == "confirmed_change" for r in output["rows"])
    assert any(r["status"] == "candidate_effect" for r in output["rows"])
    mention = tmp_path / "mention"
    mention.mkdir()
    ledger, _ = raw_pool(mention, [{"timestamp": ts(5), "type": "message", "text": "A.ets might need edits"}])
    assert change_inventory.build(ledger, scope())["rows"] == []


def test_late_read_cannot_supply_change_before_its_result(tmp_path):
    ledger = observations(tmp_path)
    assert change_inventory.build(ledger, scope(at=10))["rows"] == []


def test_unknown_candidate_time_is_gap(tmp_path):
    ledger = observations(tmp_path)
    ledger.agents[MAIN_ID].actions.append(atoms.Action("", 999, "Bash", "other", detail={"touched": [PATH]}))
    output = change_inventory.build(ledger, scope())
    assert any(g["reason"] == "unknown_use_time" for g in output["gaps"])


def test_stale_sources_refuse_inventory(tmp_path):
    ledger, path = raw_pool(tmp_path, [patch()])
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="源文件已变化"):
        change_inventory.build(ledger, scope())


def test_pagination_and_ids_are_stable_across_queries_and_pool_move(tmp_path):
    ledger, path = raw_pool(tmp_path, [patch(2), patch(5), patch(8)])
    all_rows = change_inventory.build(ledger, scope())["rows"]
    page = change_inventory.build(ledger, scope(), offset=1, limit=1)
    assert page["total"] == 3 and page["next_offset"] == 2 and page["rows"] == all_rows[1:2]
    other = tmp_path / "moved"
    other.mkdir()
    copied = other / path.name
    copied.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    moved = atoms.build_ledger({"new-registry-name": atoms.AgentRec("new-registry-name", "s", sources=[str(copied)])})
    assert [r["id"] for r in change_inventory.build(moved, scope())["rows"]] == [r["id"] for r in all_rows]


def test_pool_native_effects_scan_once_and_expose_only_observation_barrier(tmp_path, monkeypatch):
    record = patch()
    record["payload"]["changes"]["/proj/B.ets"] = {"type": "delete"}
    ledger, _ = raw_pool(tmp_path, [record, patch(20, success=False)])
    original = change_inventory.raw_events.inventory
    scans = []
    def inventory(*args):
        scans.append(1)
        return original(*args)
    monkeypatch.setattr(change_inventory.raw_events, "inventory", inventory)
    native, gaps = change_inventory.native_effects(ledger, {"kind": "pool", "at": ts(10)})
    assert len(scans) == 1 and not gaps
    assert {r["path"] for r in native} == {PATH, "/proj/B.ets"}
    assert all(r["raw_only"] and r["changed_time_unknown"] and r["use_ts"] is None and r["agent"] is None for r in native)
    assert all(r["observation_ts"].startswith(ts(5)[:-1]) for r in native)
    late, _ = change_inventory.native_effects(ledger, {"kind": "pool", "at": ts(25), "since_ts": ts(15)})
    assert len(late) == 1 and late[0]["status"] == "candidate_effect"


def test_overlapping_full_reads_do_not_invent_observation_order(tmp_path):
    ledger = _ledger(tmp_path, [*_read_call(ts(0), "one", PATH, "old"),
                              *_read_call(ts(0), "two", PATH, "new")])
    output = change_inventory.build(ledger, scope())
    assert not output["rows"]
    assert any(g["reason"] == "snapshot_order_unconfirmed" for g in output["gaps"])


def test_observed_id_does_not_depend_on_scope_start(tmp_path):
    ledger = observations(tmp_path)
    complete, = change_inventory.build(ledger, scope())["rows"]
    crossing, = change_inventory.build(ledger, scope(since=5))["rows"]
    assert complete["id"] == crossing["id"]
    assert complete["boundary_relation"] != crossing["boundary_relation"]


def test_missing_result_pointer_and_unknown_block_do_not_crash_inventory(tmp_path):
    ledger = observations(tmp_path)
    action = next(a for a in ledger.agents[MAIN_ID].actions if a.tuid == "after")
    action.src = (action.src[0], action.src[1], None)
    output = change_inventory.build(ledger, scope())
    assert not output["rows"]
    assert any(g.get("reason") == "missing_result_location" for g in output["gaps"])
    native = atoms.Action(ts(5), 999, "Write", "write", blk=None)
    record = transcript_store.read_record(ledger.agents[MAIN_ID].sources[0], 1)
    assert change_inventory._native_target(record, native, PATH) is False
