"""Call return facts and source previews never upgrade unknown file effects."""
import json

import pytest

from migloop import atoms, change_inventory, investigation, transcript_store
from migloop.filestory import Ev
from tests.test_atoms import MAIN_ID, _call, _ledger, _rec, _res, _use
from tests.test_change_inventory import PATH, PROOF, patch, raw_pool, scope, ts
from tests.test_code_host_intent import pool as code_host_pool


def candidate(tmp_path, *, result_at=6, is_error=False):
    records = _call(ts(5), "candidate", "Bash", {
        "command": "false && printf replacement > /proj/A.ets; true"},
        out="NATIVE RECEIPT /proj/A.ets", is_error=is_error)
    records[1]["timestamp"] = ts(result_at)
    return _ledger(tmp_path, records)


def resolve_pointer(ledger, address):
    value = transcript_store.resolve(ledger, address["ref"]).value
    for token in address["pointer"].split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def test_successful_native_return_does_not_confirm_conditional_effect(tmp_path):
    ledger = candidate(tmp_path)
    row, = change_inventory.build(ledger, scope())["rows"]
    assert row["status"] == "candidate_effect" and row["agent"] is None
    assert row["author_status"] == "unknown"
    assert row["call_return"]["status"] == "returned_success"
    assert row["call_return"]["success"] is True and row["call_return"]["unambiguous"]
    assert row["call_return"]["effect_certified"] is False
    request, = row["native_io"]["requests"]
    result, = row["native_io"]["results"]
    assert "false && printf" in request["preview"]
    assert "NATIVE RECEIPT" in result["preview"]
    assert request["pointer"] == "/message/content/0/input"
    assert result["pointer"] == "/message/content/0/content"
    for side in (request, result):
        value = transcript_store.readable(resolve_pointer(ledger, side))
        assert side["preview"] == value[side["preview_start"]:side["preview_start"] + 240]
        query = side["expand_query"]
        assert query["tool"] == "expand"
        assert query["args"]["refs"] == [{"ref": side["ref"], "pointer": side["pointer"]}]
        assert query["scope"]["since_ts"] is None and query["scope"]["at"] == scope()["at"].replace("Z", ".000000Z")


@pytest.mark.parametrize("failed,expected", [(True, "returned_failed"), (False, "returned_success")])
def test_success_failure_and_pending_are_cutoff_local(tmp_path, failed, expected):
    ledger = candidate(tmp_path, result_at=20, is_error=failed)
    early, = change_inventory.build(ledger, scope(at=10))["rows"]
    assert early["call_return"]["status"] == "pending"
    assert early["call_return"]["success"] is None
    assert early["native_io"]["results"] == []
    assert "NATIVE RECEIPT" not in json.dumps(early)
    late, = change_inventory.build(ledger, scope(at=25))["rows"]
    assert late["call_return"]["status"] == expected
    assert late["status"] == "candidate_effect" and late["agent"] is None


def test_prior_request_is_explicit_context_not_a_future_return(tmp_path):
    ledger = candidate(tmp_path, result_at=20)
    row, = change_inventory.build(ledger, scope(since=15, at=25))["rows"]
    assert row["call_return"]["status"] == "returned_success"
    assert row["native_io"]["requests"][0]["in_requested_range"] is False
    assert row["native_io"]["results"][0]["in_requested_range"] is True


@pytest.mark.parametrize("records,expected", [
    ([_rec(ts(1), "assistant", [_use("x", "Mystery", {"path": PATH})]),
      _rec(ts(2), "user", [_res("x")]), _rec(ts(3), "user", [_res("x")])], "ambiguous"),
    ([_rec(ts(1), "user", [_res("x", PATH)]),
      _rec(ts(2), "assistant", [_use("x", "Mystery", {"path": PATH})])], "ambiguous"),
    ([_rec(ts(1), "user", [_res("x", PATH)])], "returned_unknown"),
])
def test_ambiguous_reversed_and_orphan_raw_calls_do_not_certify_success(tmp_path, records, expected):
    ledger, _ = raw_pool(tmp_path, records)
    row, = change_inventory.build(ledger, scope())["unclassified_related"]["rows"]
    assert row["call_return"]["status"] == expected
    assert row["call_return"]["success"] is None
    assert row["effect_status"] == row["author_status"] == "unknown"


def test_future_duplicate_does_not_make_early_pair_ambiguous(tmp_path):
    ledger, _ = raw_pool(tmp_path, [*_call(ts(1), "x", "Mystery", {"path": PATH}),
                                  _rec(ts(20), "user", [_res("x")])])
    early, = change_inventory.build(ledger, scope(at=10))["unclassified_related"]["rows"]
    assert early["call_return"]["status"] == "returned_success"
    late, = change_inventory.build(ledger, scope(at=25))["unclassified_related"]["rows"]
    assert late["call_return"]["status"] == "ambiguous"


def test_code_host_return_is_only_outer_success_and_patch_stays_independent(tmp_path):
    ledger, _ = code_host_pool(tmp_path, success=False)
    output = change_inventory.build(ledger, scope())
    outer = next(row for row in output["rows"] if row.get("operation_basis") == "code_host_intent")
    assert outer["status"] == "candidate_effect" and outer["agent"] is None
    assert outer["call_return"]["status"] == "returned_success"
    assert outer["call_return"]["subject"] == "recorded_outer_call"
    assert outer["call_return"]["nested_execution"] == "unverified"
    assert outer["native_io"]["call_id"] == "outer-id"
    native = next(row for row in output["rows"] if row.get("native"))
    assert native["native_io"]["call_id"] == "independent-inner-id"
    assert native["call_return"]["status"] == "independent_event"
    assert native["call_return"]["success"] is False
    assert native["native_io"]["requests"] == []
    assert native["status"] == "candidate_effect" and native["agent"] is None


def test_codex_text_without_structured_status_or_action_is_unknown_return(tmp_path):
    records = [
        {"timestamp": ts(1), "type": "response_item", "payload": {"type": "custom_tool_call",
         "call_id": "outer", "name": "functions.exec", "input": "quoted /proj/A.ets"}},
        {"timestamp": ts(2), "type": "response_item", "payload": {"type": "custom_tool_call_output",
         "call_id": "outer", "output": '{"success":true,"exit_code":0}'}}]
    ledger, _ = raw_pool(tmp_path, records)
    row, = change_inventory.build(ledger, scope())["unclassified_related"]["rows"]
    assert row["call_return"]["status"] == "returned_unknown"
    assert row["call_return"]["subject"] == "recorded_outer_call"
    assert row["effect_status"] == "unknown"


def test_related_zero_is_counts_only_without_looping_next_page(tmp_path):
    records = [*_call(ts(1), "x", "Mystery", {"path": PATH}),
               _rec(None, "assistant", [_use("undated", "Mystery", {"path": PATH})])]
    ledger, _ = raw_pool(tmp_path, records)
    data = change_inventory.build(ledger, scope(), related_limit=0)["unclassified_related"]
    assert data["total"] == 1 and data["rows"] == [] and data["limit"] == 0
    assert data["remaining"] == 1 and data["next_offset"] is None and data["next_query"] is None
    assert data["count_only"] and data["undated"]["total"] == 1 and data["undated"]["rows"] == []
    assert data["undated"]["next_query"] is None
    resumed = change_inventory.build(ledger, scope(), **data["resume_query"]["args"])["unclassified_related"]
    assert resumed["rows"][0]["call_id"] == "x" and resumed["total"] == 1


def test_existing_write_capable_signal_only_changes_related_order(tmp_path):
    ledger = _ledger(tmp_path, [*_call(ts(1), "early", "Mystery", {"path": PATH}),
                                *_call(ts(5), "later", "Mystery", {"path": PATH})])
    later = next(action for action in ledger.agents[MAIN_ID].actions if action.tuid == "later")
    later.detail["write_capable"] = True  # Existing collector metadata, no new detector.
    related = change_inventory.build(ledger, scope(), related_limit=1)["unclassified_related"]
    row, = related["rows"]
    assert row["call_id"] == "later" and row["write_capable"]
    assert row["signal_scope"] == "call_not_target_effect"
    assert row["effect_status"] == row["author_status"] == "unknown" and row["agent"] is None
    assert related["total"] == 2 and related["next_offset"] == 1
    tail = change_inventory.build(ledger, scope(), related_offset=1, related_limit=1)["unclassified_related"]
    assert tail["rows"][0]["call_id"] == "early"


def test_previews_are_bounded_and_mutation_does_not_pollute_raw_cache(tmp_path):
    ledger = candidate(tmp_path)
    first, = change_inventory.build(ledger, scope())["rows"]
    first["native_io"]["results"][0]["fields"].clear()
    first["native_io"]["requests"][0]["expand_query"]["scope"]["at"] = "bad"
    first["call_return"]["status"] = "invented"
    second, = change_inventory.build(ledger, scope())["rows"]
    assert second["call_return"]["status"] == "returned_success"
    for side in second["native_io"]["requests"] + second["native_io"]["results"]:
        assert side["fields"] and len(side["preview"]) <= 240
        assert side["expand_query"]["scope"]["at"] != "bad"


def test_same_line_multiple_tools_preview_only_exact_call_blocks(tmp_path):
    ledger = _ledger(tmp_path, [
        _rec(ts(1), "assistant", [_use("other", "Mystery", {"path": "/other/B.ets"}),
                                  _use("target", "Write", {"file_path": PATH, "content": "TARGET"})]),
        _rec(ts(2), "user", [_res("other", "UNRELATED"), _res("target", "TARGET RETURN")])])
    row, = change_inventory.build(ledger, scope())["rows"]
    assert row["native_io"]["requests"][0]["pointer"] == "/message/content/1/input"
    assert row["native_io"]["results"][0]["pointer"] == "/message/content/1/content"
    assert "UNRELATED" not in json.dumps(row["native_io"])


def test_missing_raw_pair_cannot_fall_back_to_optimistic_action_ok(tmp_path):
    ledger = candidate(tmp_path)
    action = next(a for a in ledger.agents[MAIN_ID].actions if a.tuid == "candidate")
    action.tuid = "not-the-native-id"
    row, = change_inventory.build(ledger, scope())["rows"]
    assert row["call_return"]["status"] == "ambiguous"
    assert row["call_return"]["success"] is None


def test_parsed_action_corroborated_by_independent_patch_has_no_invented_request(tmp_path):
    _, path = raw_pool(tmp_path, [patch()])
    event = Ev(ts(5), 1, "edit", PATH, "real", old="old", new="new", proof=PROOF)
    action = atoms.Action(ts(5), 1, "apply_patch", "write", done_ts=ts(5),
                          src=(str(path), 0, 0), tuid="inner-id", files=[atoms.FileRef("write", PATH, event)])
    ledger = atoms.build_ledger({"real": atoms.AgentRec("real", "s", actions=[action], sources=[str(path)])})
    row, = change_inventory.build(ledger, scope())["rows"]
    assert row["call_return"]["status"] == "independent_event"
    assert row["call_return"]["success"] is True
    assert row["native_io"]["requests"] == [] and row["native_io"]["result_total"] == 1


def test_many_large_returns_have_bounded_previews_but_exact_counts(tmp_path):
    records = [_rec(ts(1), "assistant", [_use("many", "Mystery", {"path": PATH})])]
    records += [_rec(ts(i + 2), "user", [_res("many", "x" * 3000 + PATH)]) for i in range(5)]
    ledger, _ = raw_pool(tmp_path, records)
    row, = change_inventory.build(ledger, scope())["unclassified_related"]["rows"]
    assert row["call_return"]["status"] == "ambiguous"
    assert row["native_io"]["result_total"] == 5 and row["native_io"]["parts_omitted"] == 3
    assert len(row["native_io"]["results"]) == 2
    assert all(side["preview_truncated"] and len(side["preview"]) <= 240 for side in row["native_io"]["results"])


def test_ambiguous_source_identity_never_certifies_call_return(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    ledger, _ = raw_pool(left, _call(ts(1), "same", "Mystery", {"path": PATH}))
    second, _ = raw_pool(right, _call(ts(1), "same", "Mystery", {"path": PATH}))
    ledger.agents["second"] = next(iter(second.agents.values()))
    rows = change_inventory.build(ledger, scope())["unclassified_related"]["rows"]
    assert len(rows) == 2
    assert all(row["call_return"]["status"] == "ambiguous" and row["agent"] is None for row in rows)


@pytest.mark.parametrize("since", [3, 15])
def test_real_scoped_changes_expand_queries_execute_without_scope_drift(tmp_path, since):
    ledger = candidate(tmp_path, result_at=20)
    data = investigation.changes(ledger, PATH, ts(25), since_ts=ts(since))
    assert data["scope"]["id"].startswith("scope:")
    row, = data["rows"]
    sides = row["native_io"]["requests"] + row["native_io"]["results"]
    for side in sides:
        query = side["expand_query"]
        if side["in_requested_range"]:
            assert side["scope_relation"] == "inherited"
            assert query["scope"] == data["scope"]
        else:
            assert side["scope_relation"] == "independent_antecedent"
            assert "id" not in query["scope"] and query["scope"]["since_ts"] is None
            assert query["scope"]["at"] == data["scope"]["at"]
        # Run the emitted request through the real scope validator, not merely
        # a mocked shape assertion. Both native request and result must expand.
        expanded = investigation.query(ledger, query["tool"], {**query["args"], "scope": query["scope"]})
        item, = expanded["items"]
        assert item["status"] == "ok" and item["records"][0]["pointer"] == side["pointer"]
        if side["scope_relation"] == "independent_antecedent":
            assert expanded["scope"]["id"] != data["scope"]["id"]


def test_real_related_scope_expansions_preserve_in_range_lower_bound(tmp_path):
    ledger = _ledger(tmp_path, _call(ts(5), "related", "Mystery", {"path": PATH}, out="receipt /proj/A.ets"))
    data = investigation.changes(ledger, PATH, ts(10), since_ts=ts(3))
    row, = data["unclassified_related"]["rows"]
    requests = [side["expand_query"] for side in row["native_io"]["requests"] + row["native_io"]["results"]]
    assert all(query["scope"] == data["scope"] for query in requests)
    batch = investigation.batch(ledger, requests)
    assert all(item["status"] == "ok" and item["data"]["items"][0]["status"] == "ok"
               for item in batch["items"])
