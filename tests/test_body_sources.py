"""Recorded text remains discoverable even when no file state can be replayed."""
import json

import pytest

from migloop import body_sources, investigation, temporal
from migloop.filestory import FileStory
from tests.test_raw_events import cc, codex, pointer, pool, result, ts, use


def test_original_write_body_is_not_filtered_by_failed_or_pending_execution(tmp_path):
    ledger, _ = pool(tmp_path, [
        cc(0, use("w", "Write", file_path="/p/A.ets", content="FIRST_FULL_BODY")),
        cc(5, result("w", "failure", is_error=True)),
    ])
    assert not ledger.stories  # No reconstruction or parsed Action is needed.
    early = body_sources.query(ledger, "/p/A.ets", ts(1))
    row, = early["events"]
    assert row["body_extent"] == "complete_requested_body"
    assert row["call_state"] == "pending_or_unknown"
    assert pointer(ledger, row) == "FIRST_FULL_BODY"
    later = body_sources.query(ledger, "/p/A.ets", ts(10))
    assert later["events"][0]["call_state"] == "failed"
    assert not row["author_certified"] and not row["current_state_certified"]
    expanded = investigation.query(ledger, "expand", {**row["query"]["args"], "scope": row["query"]["scope"]})
    assert expanded["items"][0]["records"][0]["text"] == "FIRST_FULL_BODY"


def test_late_read_body_only_admitted_at_return_and_under_its_native_target(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use("r", "Read", file_path="/p/A.ets")),
                              cc(5, result("r", "BODY_WITHOUT_FILENAME"))])
    assert body_sources.query(ledger, "/p/A.ets", ts(4))["total"] == 0
    visible = body_sources.query(ledger, "/p/A.ets", ts(6), ts(3))
    row, = visible["events"]
    assert row["record_ts"] == temporal.Window.parse(ts(5)).at
    assert row["body_extent"] == "unknown_read_extent"
    expanded = investigation.query(ledger, "expand", {**row["query"]["args"], "scope": row["query"]["scope"]})
    assert expanded["items"][0]["records"][0]["text"] == "BODY_WITHOUT_FILENAME"
    wrong = {**row["query"]["scope"], "key": "/p/B.ets"}
    assert investigation.query(ledger, "expand", {**row["query"]["args"], "scope": wrong})["items"][0]["status"] == "error"


def test_duplicate_reads_and_future_requests_do_not_authenticate_targets(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use("r", "Read", file_path="/p/A.ets")),
                              cc(1, use("r", "Read", file_path="/p/B.ets")),
                              cc(5, result("r", "AMBIGUOUS_BODY"))])
    assert body_sources.query(ledger, "/p/A.ets", ts(6))["total"] == 0
    assert body_sources.query(ledger, "/p/B.ets", ts(6))["total"] == 0


def test_partial_and_full_read_are_reported_extents_not_file_authorship(tmp_path):
    out = cc(5, result("r", "1→line"))
    out["toolUseResult"] = {"type": "text", "file": {"filePath": "/p/A.ets", "content": "line",
                                                   "startLine": 1, "numLines": 1, "totalLines": 1}}
    ledger, _ = pool(tmp_path, [cc(0, use("r", "Read", file_path="/p/A.ets")), out])
    row, = body_sources.query(ledger, "/p/A.ets", ts(6))["events"]
    assert row["body_extent"] == "reported_full_read"
    assert row["pointer"] == "/toolUseResult/file/content" and pointer(ledger, row) == "line"
    assert not row["author_certified"]


def test_outer_read_metadata_cannot_be_borrowed_by_sibling_results(tmp_path):
    out = cc(5, result("r", "partialA"), result("other", "other body"))
    out["toolUseResult"] = {"file": {"filePath": "/p/A.ets", "content": "UNBOUND_OUTER_BODY",
                                    "startLine": 1, "numLines": 1, "totalLines": 1}}
    ledger, _ = pool(tmp_path, [cc(0, use("r", "Read", file_path="/p/A.ets")), out])
    row, = body_sources.query(ledger, "/p/A.ets", ts(6))["events"]
    assert row["body_extent"] == "unknown_read_extent" and pointer(ledger, row) == "partialA"


def test_navigation_preserves_bounds_counts_and_excludes_code_host_literals(tmp_path):
    ledger, _ = pool(tmp_path, [cc(i, use(str(i), "Write", file_path="/p/A.ets", content=f"BODY_{i}")) for i in range(5)] +
                    [codex(5, "function_call", name="exec", arguments='Write("/p/A.ets", "NOT_EXECUTED")')])
    nav = body_sources.navigation(ledger, "/p/A.ets", ts(5), ts(1))
    assert nav["total"] == 4 and len(nav["entries"]) == 2 and nav["remaining"] == 2
    assert nav["query"]["scope"]["since_ts"] == temporal.Window.parse(ts(1)).at
    assert "NOT_EXECUTED" not in str(nav) and nav["kind_counts"] == {"write_request": 4}
    hidden = body_sources.navigation(ledger, "/p/A.ets", ts(5), ts(1), show=False)
    assert not hidden["entries"] and hidden["total"] == hidden["remaining"] == 4


def test_file_entry_lists_body_navigation_without_calling_replay(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use("w", "Write", file_path="/p/A.ets", content="SOURCE"))])
    data = investigation.query(ledger, "file", {"path": "/p/A.ets", "at": ts(3)})
    assert data["body_sources"]["total"] == 1
    assert investigation._delivery(data)["records"] == []
    raw = investigation.query(ledger, "file", {"path": "/p/A.ets", "at": ts(3), "view": "records"})
    assert raw["body_sources"]["total"] == 1
    assert not investigation._delivery(raw)["records"][0]["extent"].startswith("raw_segment")


def test_query_alias_cannot_retarget_an_absolute_native_write(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use("w", "Write", file_path="/A.ets", content="OTHER_ROOT_BODY"))])
    ledger.stories["/p/A.ets"] = FileStory("/p/A.ets")
    assert body_sources.query(ledger, "/p/A.ets", ts(3))["total"] == 0


@pytest.mark.parametrize("unknown", [use("r", "Read", file_path="/p/B.ets"), result("r", "undated other body")])
def test_undated_competing_parts_block_read_target_binding(tmp_path, unknown):
    ledger, _ = pool(tmp_path, [cc(0, use("r", "Read", file_path="/p/A.ets")),
                              cc(None, unknown), cc(5, result("r", "TIMED_BODY"))])
    data = body_sources.query(ledger, "/p/A.ets", ts(6))
    assert data["total"] == 0 and data["unknown_time_count"] == 1


def test_blank_read_call_id_does_not_locate_filename_free_result(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use(" ", "Read", file_path="/p/A.ets")),
                              cc(5, result(" ", "UNBOUND_BODY"))])
    assert body_sources.query(ledger, "/p/A.ets", ts(6))["total"] == 0


def test_nonstring_body_cursor_uses_same_json_representation_as_expand(tmp_path):
    content = [{"type": "text", "text": "abc"}]
    ledger, _ = pool(tmp_path, [cc(0, use("r", "Read", file_path="/p/A.ets")), cc(5, result("r", content))])
    row, = body_sources.query(ledger, "/p/A.ets", ts(6))["events"]
    expanded = investigation.query(ledger, "expand", {**row["query"]["args"], "scope": row["query"]["scope"]})
    record = expanded["items"][0]["records"][0]
    assert row["representation"] == record["representation"] == "json_value"
    assert row["chars"] == record["chars"] == len(json.dumps(content, ensure_ascii=False, separators=(",", ":")))


def test_unresolved_relative_targets_from_distinct_workdirs_are_not_one_native_file(tmp_path):
    one = {**cc(0, use("one", "Write", file_path="A.ets", content="one")), "cwd": "/one"}
    two = {**cc(1, use("two", "Write", file_path="A.ets", content="two")), "cwd": "/two"}
    ledger, _ = pool(tmp_path, [one, two])
    assert body_sources.query(ledger, "A.ets", ts(3))["total"] == 0


def test_duplicate_source_names_mark_unaddressable_body_navigation(tmp_path):
    from migloop import atoms
    left, right = tmp_path / "one", tmp_path / "two"
    left.mkdir()
    right.mkdir()
    ledger, _ = pool(left, [cc(0, use("one", "Write", file_path="/p/A.ets", content="one"))])
    _, path = pool(right, [cc(1, use("two", "Write", file_path="/p/A.ets", content="two"))], aid="b")
    ledger.agents["b"] = atoms.AgentRec("b", "s", sources=[str(path)])
    rows = body_sources.query(ledger, "/p/A.ets", ts(3))["events"]
    assert len(rows) == 2
    assert all(row["reference_status"] == "ambiguous_source" and row["query"] is None for row in rows)


@pytest.mark.parametrize("path", ["/A.ets", "C:/A.ets", "//host/share/A.ets", "C:A.ets"])
def test_absolute_or_drive_scoped_time_target_is_not_replaced_by_suffix(path, tmp_path):
    ledger, _ = pool(tmp_path, [])
    ledger.stories["/p/A.ets"] = FileStory("/p/A.ets")
    assert temporal.resolve_file(ledger, path) == path
    assert temporal.resolve_file(ledger, "A.ets") == "/p/A.ets"


def test_relative_time_hint_still_rejects_multiple_basename_matches(tmp_path):
    ledger, _ = pool(tmp_path, [])
    ledger.stories.update({path: FileStory(path) for path in ("/p/A.ets", "/q/A.ets")})
    with pytest.raises(ValueError, match="歧义"):
        temporal.resolve_file(ledger, "A.ets")
    assert temporal.resolve_file(ledger, "/A.ets") == "/A.ets"


def test_before_window_selects_latest_write_and_read_without_future_result_state(tmp_path):
    full = cc(4, result("r-new", "read body"))
    full["toolUseResult"] = {"file": {"filePath": "/p/A.ets", "content": "LATEST_READ_BODY",
                                    "startLine": 1, "numLines": 1, "totalLines": 1}}
    ledger, _ = pool(tmp_path, [
        cc(0, use("w-old", "Write", file_path="/p/A.ets", content="OLDER_WRITE_BODY")),
        cc(1, use("r-old", "Read", file_path="/p/A.ets")),
        cc(2, result("r-old", "OLDER_READ_BODY")),
        cc(3, use("w-middle", "Write", file_path="/p/A.ets", content="MIDDLE_BODY"),
           use("r-new", "Read", file_path="/p/A.ets")), full,
        cc(5, use("r-late", "Read", file_path="/p/A.ets")),
        cc(6, use("w-at-start", "Write", file_path="/p/A.ets", content="LATEST_WRITE_BODY")),
        cc(8, result("r-late", "LATE_READ_BODY"), result("w-at-start", "failed later", is_error=True)),
        cc(9, use("w-later", "Write", file_path="/p/A.ets", content="LATER_WRITE_BODY")),
    ])
    nav = body_sources.navigation(ledger, "/p/A.ets", ts(10), ts(6))
    before = nav["before_window"]
    assert before["scope"] == {"kind": "file", "key": "/p/A.ets",
                               "at": temporal.Window.parse(ts(6)).at, "since_ts": None}
    assert before["total"] == 5 and before["remaining"] == 3
    entries = {row["kind"]: row for row in before["entries"]}
    assert set(entries) == {"write_request", "read_response"}
    assert entries["write_request"]["call_id"] == "w-at-start"
    assert entries["write_request"]["call_state"] == "pending_or_unknown"
    assert entries["read_response"]["call_id"] == "r-new"
    assert entries["read_response"]["body_extent"] == "reported_full_read"
    assert nav["entries"][0]["call_state"] == "failed"
    assert all(row["query"]["scope"] == before["scope"] for row in before["entries"])
    assert all(not row["author_certified"] and not row["current_state_certified"] for row in before["entries"])
    assert not before["navigation_is_relation"] and not before["current_state_certified"]
    assert not any(body in json.dumps(nav) for body in
                   ("LATEST_READ_BODY", "LATEST_WRITE_BODY", "LATE_READ_BODY", "LATER_WRITE_BODY"))


def test_before_window_failed_write_is_proposal_and_failed_read_keeps_extent(tmp_path):
    ledger, _ = pool(tmp_path, [
        cc(0, use("w", "Write", file_path="/p/A.ets", content="PROPOSED_BODY")),
        cc(1, result("w", "write refused", is_error=True)),
        cc(2, use("r", "Read", file_path="/p/A.ets")),
        cc(3, result("r", "read refused", is_error=True)),
    ])
    before = body_sources.navigation(ledger, "/p/A.ets", ts(10), ts(4))["before_window"]
    rows = {r["kind"]: r for r in before["entries"]}
    assert rows["write_request"]["call_state"] == "failed"
    assert rows["write_request"]["body_extent"] == "complete_requested_body"
    assert rows["read_response"]["body_extent"] == "failed_read_response_not_file_content"
    assert rows["read_response"]["call_state"] == "failed"
    assert not rows["write_request"]["author_certified"]


def test_before_window_same_timestamp_ties_are_representatives_not_unique(tmp_path):
    ledger, _ = pool(tmp_path, [
        cc(0, use("read-one", "Read", file_path="/p/A.ets"),
           use("read-two", "Read", file_path="/p/A.ets")),
        cc(4, use("write-one", "Write", file_path="/p/A.ets", content="one"),
           use("write-two", "Write", file_path="/p/A.ets", content="two"),
           result("read-one", "one"), result("read-two", "two")),
    ])
    before = body_sources.navigation(ledger, "/p/A.ets", ts(9), ts(5))["before_window"]
    assert len(before["entries"]) == 2 and before["total"] == 4 and before["remaining"] == 2
    assert {r["kind"] for r in before["entries"]} == {"write_request", "read_response"}
    assert all(r["timestamp_tie_count"] == 2 and not r["selection_is_unique"] for r in before["entries"])
    assert before == body_sources.navigation(ledger, "/p/A.ets", ts(9), ts(5))["before_window"]
    request = before["query"]
    all_rows = investigation.query(ledger, request["tool"], {**request["args"], "scope": request["scope"]})
    assert all_rows["total"] == 4 and len(all_rows["events"]) == 4


def test_before_window_future_duplicate_does_not_rewrite_earlier_read_state(tmp_path):
    ledger, _ = pool(tmp_path, [
        cc(0, use("r", "Read", file_path="/p/A.ets")), cc(1, result("r", "EARLIER_BODY")),
        cc(7, use("r", "Read", file_path="/p/B.ets")), cc(8, result("r", "LATER_BODY")),
    ])
    nav = body_sources.navigation(ledger, "/p/A.ets", ts(9), ts(5))
    assert nav["total"] == 0
    row, = nav["before_window"]["entries"]
    assert row["kind"] == "read_response" and row["call_state"] == "returned"
    assert row["anomalies"] == [] and pointer(ledger, row) == "EARLIER_BODY"


def test_before_window_hidden_preserves_independent_query_without_entries(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use("w", "Write", file_path="/p/A.ets", content="BODY"))])
    assert "before_window" not in body_sources.navigation(ledger, "/p/A.ets", ts(9))
    hidden = body_sources.navigation(ledger, "/p/A.ets", ts(9), ts(5), show=False)
    assert hidden["entries"] == hidden["before_window"]["entries"] == []
    assert hidden["before_window"]["total"] == hidden["before_window"]["remaining"] == 1
    assert hidden["before_window"]["query"]["scope"]["since_ts"] is None
    assert hidden["before_window"]["query"]["scope"]["at"] == temporal.Window.parse(ts(5)).at


def test_before_window_expansion_is_independent_and_does_not_extend_original_admission(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use("r", "Read", file_path="/p/A.ets")),
                              cc(1, result("r", "FILENAME_FREE_EARLY_BODY"))])
    data = investigation.query(ledger, "file", {"path": "/p/A.ets", "at": ts(9), "since_ts": ts(5)})
    assert investigation._delivery(data)["records"] == []
    before = data["body_sources"]["before_window"]
    row, = before["entries"]
    assert not body_sources.admits_record(ledger, data["scope"], row["ref"])
    q = row["query"]
    actual = investigation.query(ledger, q["tool"], {**q["args"], "scope": q["scope"]})
    assert actual["items"][0]["records"][0]["text"] == "FILENAME_FREE_EARLY_BODY"
    denied = investigation.query(ledger, q["tool"], {**q["args"], "scope": data["scope"]})
    assert denied["items"][0]["status"] == "error"


def test_before_window_has_no_future_read_codex_shell_or_other_file_body(tmp_path):
    ledger, _ = pool(tmp_path, [
        cc(0, use("r", "Read", file_path="/p/A.ets")), cc(8, result("r", "LATE_BODY")),
        cc(1, use("shell", "Bash", command='echo "SHELL_BODY" > /p/A.ets')),
        cc(2, use("other", "Write", file_path="/other/A.ets", content="OTHER_BODY")),
        codex(3, "function_call", name="exec", arguments='Write("/p/A.ets", "CODE_HOST_BODY")'),
    ])
    before = body_sources.navigation(ledger, "/p/A.ets", ts(9), ts(5))["before_window"]
    assert before["entries"] == [] and before["total"] == 0
    assert not before["current_state_certified"]
    assert "shell" in before["note"] and "零项" in before["note"]


def test_before_window_retains_unknown_time_gap_and_duplicate_write_uncertainty(tmp_path):
    ledger, _ = pool(tmp_path, [
        cc(None, use("unknown", "Write", file_path="/p/A.ets", content="UNDATED_BODY")),
        cc(1, use("dup", "Write", file_path="/p/A.ets", content="FIRST")),
        cc(2, use("dup", "Write", file_path="/p/A.ets", content="SECOND")),
        cc(3, result("dup", "ok")),
    ])
    before = body_sources.navigation(ledger, "/p/A.ets", ts(9), ts(5))["before_window"]
    row, = before["entries"]
    assert before["unknown_time_count"] == 1 and before["total"] == 2
    assert "duplicate_use" in row["anomalies"] and row["call_state"] != "returned"
    assert row["timestamp_tie_count"] == 1 and row["selection_is_unique"]
    assert not row["author_certified"] and not row["current_state_certified"]
