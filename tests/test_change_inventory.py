"""Inventory effects without inventing authors, repair boundaries or state changes."""
from dataclasses import replace

import pytest

from migloop import atoms, change_inventory, transcript_store
from migloop.evidence import FileProof
from migloop.filestory import Ev
from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call, _rec, _res, _use
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


@pytest.mark.parametrize("success", [True, False])
def test_native_diff_preserves_exact_delta_without_outer_actor_or_full_state(tmp_path, success):
    ledger, _ = raw_pool(tmp_path, [patch(success=success)])
    row, = change_inventory.native_effects(ledger, scope())[0]
    diff = change_inventory.native_diff(ledger, row, max_chars=12)
    assert diff["diff"] == "@@ -1 +1 @@\n" and diff["truncated"] and diff["diff_chars"] > 12
    assert diff["agent"] is None and diff["effect_ts"] is None and diff["changed_time_unknown"]
    assert diff["effect_status"] == ("confirmed_change" if success else "candidate_effect")
    assert not diff["semantic_checked"]
    with pytest.raises(ValueError, match="身份"):
        change_inventory.native_diff(ledger, {**row, "native": {**row["native"], "call_id": "outer"}})
    with pytest.raises(ValueError, match="目标"):
        change_inventory.native_diff(ledger, {**row, "path": "/other/A.ets"})


def test_native_add_without_delta_is_not_a_fabricated_diff(tmp_path):
    record = patch()
    record["payload"]["changes"][PATH] = {"type": "add", "content": "new\n"}
    ledger, _ = raw_pool(tmp_path, [record])
    row, = change_inventory.native_effects(ledger, scope())[0]
    assert change_inventory.native_diff(ledger, row) is None


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
    assert output["unclassified_related"]["raw_query"]["tool"] == "events"
    assert output["unclassified_related"]["non_native_mentions"]["total"] == 1
    assert output["unclassified_related"]["total"] == 0


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


def test_unparsed_dynamic_shell_stdout_remains_related_not_a_writer(tmp_path):
    ledger = _ledger(tmp_path, _call(ts(5), "loop", "Bash", {
        "command": "python -c \"import glob; [f(p) for p in glob.iglob(root + '/**/*', recursive=True)]\""},
        out="processed /proj/A.ets with dynamic substitutions"))
    output = change_inventory.build(ledger, scope())
    assert output["rows"] == []
    related = output["unclassified_related"]
    row, = related["rows"]
    assert related["total"] == related["review_required_total"] == 1
    assert row["call_id"] == "loop" and row["category"] == "shell" and row["status"] == "returned"
    assert row["effect_status"] == row["author_status"] == "unknown" and row["agent"] is None
    assert row["association"] == "lexical_mention_not_effect"
    assert row["matched_parts"] == [{"ref": row["pointers"][1]["ref"], "pointer": "/message/content/0"}]
    assert "dynamic substitutions" in row["pointers"][1]["preview"]
    assert all(len(p.get("preview", "")) <= 240 for p in row["pointers"])
    assert row["pointers"][1]["preview_kind"] == "decoded_native_payload_excerpt"
    for pointer in row["pointers"]:
        assert transcript_store.resolve(ledger, pointer["ref"]).line == pointer["line"]
        assert pointer["query"]["scope"] == output["scope"]


def test_known_changes_and_observation_evidence_are_deducted_before_paging(tmp_path):
    ledger = observations(tmp_path, [*_call(ts(3), "write1", "Write", {"file_path": PATH, "content": "middle"}),
                                    *_call(ts(5), "write2", "Write", {"file_path": PATH, "content": "new\n"})])
    output = change_inventory.build(ledger, scope(), limit=1)
    assert output["total"] == 3 and len(output["rows"]) == 1
    related = output["unclassified_related"]
    assert related["total"] == 0 and related["excluded_covered_total"] == 4
    assert not related["complete"] and not related["causal_complete"]
    assert "0余项不等于0修改、0缺陷" in related["note"]


def test_related_paging_counts_all_calls_and_folds_readonly_after_other_calls(tmp_path):
    calls = [*_call(ts(1), "read", "Read", {"file_path": PATH}),
             *_call(ts(1), "grep", "Grep", {"pattern": "x", "path": PATH}),
             *_call(ts(1), "glob", "Glob", {"pattern": PATH})]
    for index in range(43):
        calls += _call(ts(5), f"unknown-{index:02}", "UnparsedTool", {"text": PATH})
    ledger, _ = raw_pool(tmp_path, calls)
    output = change_inventory.build(ledger, scope(), related_limit=2)
    related = output["unclassified_related"]
    assert related["total"] == 46 and related["review_required_total"] == 43
    assert related["readonly"] == {"total": 3, "tool_counts": {"Read": 1, "Grep": 1, "Glob": 1},
                                   "display": "collapsed", "included_in_total_and_pagination": True}
    assert related["category_counts"]["unknown_tool"] == 43
    assert related["ordering"] == "non_readonly_first_then_recorded_time"
    assert [r["call_id"] for r in related["rows"]] == ["unknown-00", "unknown-01"]
    assert related["next_query"] == {"tool": "changes", "scope": output["scope"],
                                     "args": {"related_offset": 2, "related_limit": 2}}
    next_page = change_inventory.build(ledger, scope(), **related["next_query"]["args"])["unclassified_related"]
    assert next_page["offset"] == 2 and next_page["total"] == 46
    tail = change_inventory.build(ledger, scope(), related_offset=43, related_limit=3)["unclassified_related"]
    assert [r["tool"] for r in tail["rows"]] == ["Read", "Grep", "Glob"]
    assert tail["remaining"] == 0 and tail["next_query"] is None
    assert change_inventory.build(ledger, scope())["unclassified_related"]["limit"] == 8


def test_same_record_multiple_native_calls_do_not_cross_deduct(tmp_path):
    ledger = _ledger(tmp_path, [
        _rec(ts(1), "assistant", [_use("write", "Write", {"file_path": PATH, "content": "new"}),
                                  _use("unknown", "Bash", {"command": "echo /proj/A.ets"})]),
        _rec(ts(2), "user", [_res("write"), _res("unknown")])])
    output = change_inventory.build(ledger, scope())
    assert len(output["rows"]) == 1 and output["rows"][0]["status"] == "confirmed_change"
    related = output["unclassified_related"]
    assert related["excluded_covered_total"] == 1 and related["total"] == 1
    assert related["rows"][0]["call_id"] == "unknown"
    assert related["rows"][0]["pointers"][0]["block"] == 1


def test_quoted_commands_and_other_file_writes_only_add_related_locators(tmp_path):
    ledger = _ledger(tmp_path, [
        *_call(ts(1), "quote", "Bash", {"command": "echo 'sed -i s/a/b/ /proj/A.ets'"}),
        *_call(ts(3), "other", "Write", {"file_path": "/other/B.ets", "content": "reference /proj/A.ets"})])
    output = change_inventory.build(ledger, scope())
    assert output["rows"] == []
    related = output["unclassified_related"]
    assert related["total"] == 2 and related["excluded_covered_total"] == 0
    assert all(r["effect_status"] == "unknown" and r["agent"] is None for r in related["rows"])


def test_future_result_cannot_backflow_target_status_or_related_count(tmp_path):
    calls = _call(ts(5), "late", "Bash", {"command": "python arbitrary_dynamic.py"}, out=PATH, is_error=True)
    calls[1]["timestamp"] = ts(20)
    ledger, _ = raw_pool(tmp_path, calls)
    early = change_inventory.build(ledger, scope(at=10))["unclassified_related"]
    assert early["total"] == 0
    late = change_inventory.build(ledger, scope(at=25))["unclassified_related"]
    assert late["total"] == 1 and late["rows"][0]["status"] == "failed"
    result_only = change_inventory.build(ledger, scope(since=15, at=25))["unclassified_related"]
    assert result_only["rows"][0]["status"] == "result_only"
    assert [p["line"] for p in result_only["rows"][0]["pointers"]] == [2]
    assert result_only["rows"][0]["pointers"][0]["failed"] is True


def test_pending_lexical_call_and_prior_request_association_respect_record_times(tmp_path):
    calls = _call(ts(5), "late", "Bash", {"command": "echo /proj/A.ets"}, out="done", is_error=True)
    calls[1]["timestamp"] = ts(20)
    ledger, _ = raw_pool(tmp_path, calls)
    early = change_inventory.build(ledger, scope(at=10))["unclassified_related"]
    assert early["total"] == 1 and early["rows"][0]["status"] == "pending_or_unknown"
    assert len(early["rows"][0]["pointers"]) == 1
    later = change_inventory.build(ledger, scope(since=15, at=25))["unclassified_related"]
    row, = later["rows"]
    assert row["status"] == "result_only" and row["tool"] is None
    assert row["association"] == "earlier_request_mention_not_effect"
    assert row["pointers"][0]["line"] == 2


def test_undated_calls_are_quarantined_not_counted_as_in_range(tmp_path):
    call = _call(ts(5), "unknown-time", "Bash", {"command": "echo /proj/A.ets"})[0]
    call["timestamp"] = None
    ledger, _ = raw_pool(tmp_path, [call])
    related = change_inventory.build(ledger, scope())["unclassified_related"]
    assert related["total"] == 0 and related["undated"]["total"] == 1
    assert related["undated"]["cutoff_evidence"] is False
    assert "query" not in related["undated"]["rows"][0]


def test_native_effect_deducted_but_other_path_same_basename_not_authenticated(tmp_path):
    ledger, _ = raw_pool(tmp_path, [patch(2), patch(5, path="/different/A.ets")])
    output = change_inventory.build(ledger, scope())
    assert len(output["rows"]) == 1
    related = output["unclassified_related"]
    assert related["excluded_covered_total"] == related["total"] == 1
    assert related["rows"][0]["classification"] == "unclassified_related"


def test_related_native_index_does_not_reread_each_record(tmp_path, monkeypatch):
    calls = [r for index in range(45) for r in _call(ts(5), f"call-{index}", "Unknown", {"path": PATH})]
    ledger, _ = raw_pool(tmp_path, calls)
    change_inventory.raw_events.inventory(ledger)  # Warm the shared source index once.
    def forbidden(*args, **kwargs):
        raise AssertionError("remainder must use cached native payloads, not reopen each original line")
    monkeypatch.setattr(transcript_store, "read_record", forbidden)
    related = change_inventory.build(ledger, scope(), related_offset=40, related_limit=5)["unclassified_related"]
    assert related["total"] == 45 and len(related["rows"]) == 5


def test_failed_and_pending_known_target_candidates_are_not_counted_twice(tmp_path):
    calls = [*_call(ts(1), "failed", "Write", {"file_path": PATH, "content": "x"}, is_error=True),
             *_call(ts(5), "pending", "Write", {"file_path": PATH, "content": "y"})]
    calls[-1]["timestamp"] = ts(20)
    ledger = _ledger(tmp_path, calls)
    output = change_inventory.build(ledger, scope(at=10))
    assert len(output["rows"]) == 2 and all(r["status"] == "candidate_effect" for r in output["rows"])
    assert output["unclassified_related"]["total"] == 0
    assert output["unclassified_related"]["excluded_covered_total"] == 2


def test_registered_only_counts_do_not_claim_unregistered_sources_are_complete(tmp_path):
    ledger, _ = raw_pool(tmp_path, [_rec(ts(1), "assistant", "unrelated registered message")])
    # This sibling file is deliberately absent from the registered source set.
    unregistered = tmp_path / "unregistered"
    unregistered.mkdir()
    raw_pool(unregistered, _call(ts(5), "missed", "Bash", {"command": "echo /proj/A.ets"}))
    related = change_inventory.build(ledger, scope())["unclassified_related"]
    assert related["total"] == 0 and related["source_count"] == 1
    assert related["counts_scope"] == "registered_sources_only" and related["registered_scan_ok"]
    assert not related["complete"] and "未注册来源" in related["note"]


def test_raw_source_gap_keeps_counts_explicitly_incomplete(tmp_path):
    ledger, _ = raw_pool(tmp_path, ["malformed A.ets"])
    related = change_inventory.build(ledger, scope())["unclassified_related"]
    assert related["gaps"] and not related["registered_scan_ok"] and not related["complete"]


@pytest.mark.parametrize("kwargs", [{"related_offset": -1}, {"related_offset": True},
                                    {"related_limit": 0}, {"related_limit": 201}])
def test_related_pagination_validation(tmp_path, kwargs):
    ledger, _ = raw_pool(tmp_path, [])
    with pytest.raises(ValueError):
        change_inventory.build(ledger, scope(), **kwargs)
