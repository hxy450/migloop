"""Synthetic delivery-only checks: no pool, subprocess, or history execution."""
from copy import deepcopy

import pytest

from migloop import delivery_budget as budget

SCOPE = {"kind": "file", "key": "/project/A.ets", "at": "2026-09-10T12:00:00Z",
         "since_ts": "2026-09-09T12:00:00Z", "bounds": "inclusive"}


def page(rows, *, offset=0, total=None, limit=None):
    total = total if total is not None else len(rows)
    limit = limit if limit is not None else len(rows)
    return {"rows": rows, "total": total, "offset": offset, "limit": limit,
            "remaining": max(0, total - offset - limit),
            "next_offset": offset + limit if offset + limit < total else None}


def view(count=6):
    rows = [{"ref": f"raw:source:L{i + 1}:hash{i}", "preview": "中文\n\"\\" * 80,
             "chars": 9000, "ts": "2026-09-10T00:00:00Z", "annotations": [
                 {"relation": "possible_write", "status": "candidate", "execution": "unknown"}]} for i in range(count)]
    return {"schema": "migloop-time-view/1", "scope": deepcopy(SCOPE),
            **page(rows, offset=3, total=20, limit=count), "undated": page([], total=7, limit=4),
            "counts": {"matched": 20, "undated": 7, "malformed": 2},
            "gaps": [{"source": "missing", "error": "unavailable"}],
            "receipt": {"schema": "migloop-query-receipt/1", "records": [r["ref"] for r in rows],
                        "undated_records": [], "scope": deepcopy(SCOPE), "navigation_is_relation": False}}


def record(ref="raw:source:L1:contenthash", *, length=10000, offset=7, field=False):
    result = {"schema": "migloop-raw-field/1" if field else "migloop-raw-record/1",
              "ref": ref, "scope": deepcopy(SCOPE), "offset": offset,
              "text": "中文\n\"\\" * (length // 5), "chars": length + offset + 11,
              "next_offset": offset + length}
    # The string has five Python characters, but more serialized JSON characters.
    if field:
        result.update(pointer="/payload/changes", field_sha256="original-field-hash", representation="decoded_string")
    return result


def expansion():
    return {"schema": "migloop-evidence-expansion/1", "scope": deepcopy(SCOPE),
            "gaps": [{"source": "missing", "reason": "unknown_source"}], "unknown_count": 3,
            "items": [{"item_index": i, "ref": f"#source:{i + 1}@L1", "pointer": None, "status": "ok",
                "withheld": [{"ref": f"raw:source:L99:hash{i}", "reason": "outside scope"}],
                "records": [record(f"raw:source:L{i + 1}:hash", field=True), record(f"raw:source:L{i + 20}:hash")]} for i in range(3)]}


def assert_bounded(result, amount):
    assert result["budget"] == amount and result["budget_scope"] == "serialized_data_only"
    assert result["data_chars"] <= amount
    if result["data"] is not None:
        assert budget.size(result["data"]) == result["data_chars"]


def test_already_fitting_body_is_unchanged_and_independent_copy():
    data = view()
    result = budget.fit(data, budget.size(data))
    assert result["status"] == "ok" and not result["budget_adjusted"]
    assert result["data"] == data and result["data"] is not data
    result["data"]["rows"][0]["ref"] = "not-original"
    assert data["rows"][0]["ref"].endswith("hash0")


@pytest.mark.parametrize("atom", [False, True])
def test_prior_body_navigation_folds_without_widening_the_evidence_window(atom):
    data = view(1)
    if atom:
        data = {"schema": "migloop-time-atom/1", "scope": deepcopy(SCOPE),
                "sections": {"writes": page([])}}
    prior_scope = {"kind": "file", "key": SCOPE["key"], "at": SCOPE["since_ts"], "since_ts": None}
    query = {"tool": "events", "scope": prior_scope, "args": {"view": "bodies", "limit": 40}}
    prior = {"total": 9, "remaining": 7, "scope": prior_scope, "query": query,
             "unknown_time_count": 2, "gaps": [{"source": "unreadable", "error": "missing"}],
             "entries": [{"ref": "raw:earlier:L1:abc", "locator_padding": "x" * 7000},
                         {"ref": "raw:earlier:L2:def", "locator_padding": "y" * 7000}]}
    data["body_sources"] = {"total": 0, "remaining": 0, "entries": [],
        "query": {"tool": "events", "scope": deepcopy(SCOPE), "args": {"view": "bodies"}},
        "before_window": prior}
    original = deepcopy(data)
    fitted = budget.fit(data, 3500)
    assert fitted["status"] == "ok"
    assert fitted["data"]["scope"] == SCOPE
    shown = fitted["data"]["body_sources"]["before_window"]
    assert shown["entries"] == [] and shown["remaining"] == shown["total"] == 9
    assert shown["unknown_time_count"] == 2 and shown["gaps"] == prior["gaps"]
    assert shown["query"] == query and shown["scope"] == prior_scope
    continuation = next(c for c in fitted["continuations"] if c.get("next_query") == query)
    assert continuation["remaining"] == 9
    from migloop import investigation
    assert "raw:earlier:" not in str(investigation._delivery(fitted["data"]))
    assert data == original
    assert_bounded(fitted, 3500)


@pytest.mark.parametrize("amount", [0, 20, 750, 1300, 2500, 5000])
def test_serialized_total_budget_and_original_object_unchanged(amount):
    data = view()
    original = deepcopy(data)
    result = budget.fit(data, amount)
    assert data == original
    assert_bounded(result, amount)
    assert result["continuations"]


def test_page_prefix_updates_offsets_remaining_limits_not_match_scope():
    data = view()
    result = budget.fit(data, 2200)
    body = result["data"]
    assert result["status"] == "ok" and 0 < len(body["rows"]) < len(data["rows"])
    assert body["scope"] == data["scope"] and body["total"] == 20 and body["offset"] == 3
    assert body["limit"] == body["actual_limit"] == len(body["rows"])
    assert body["requested_limit"] == data["limit"]
    assert body["next_offset"] == 3 + len(body["rows"])
    assert body["remaining"] == 20 - body["next_offset"]
    assert [r["ref"] for r in body["rows"]] == [r["ref"] for r in data["rows"]][:len(body["rows"])]
    assert body["gaps"] == data["gaps"] and body["counts"] == data["counts"]
    assert body["receipt"]["records"] == [r["ref"] for r in body["rows"]]
    assert all(r["annotations"] == data["rows"][0]["annotations"] for r in body["rows"])


def test_undated_and_unknown_event_pages_keep_independent_cursors_and_totals():
    data = {"schema": "migloop-raw-event-query/1", "scope": deepcopy(SCOPE), "events": [],
            **{k: v for k, v in page([], offset=2, total=13, limit=4).items() if k != "rows"},
            "unknown_records": page([{"id": str(i), "body": "x" * 200} for i in range(4)], offset=6, total=17),
            "undated": page([{"ref": f"raw:unknown:L{i}:hash", "ts": None} for i in range(4)], offset=8, total=15),
            "gaps": [], "source_count": 2}
    result = budget.fit(data, 1000)
    body = result["data"]
    assert body and body["total"] == 13 and body["events"] == []
    for name in ("undated", "unknown_records"):
        actual, source = body[name], data[name]
        assert actual["rows"] == source["rows"][:len(actual["rows"])]
        assert actual["offset"] == source["offset"] and actual["total"] == source["total"]
        assert actual["next_offset"] == source["offset"] + len(actual["rows"])
        continuation = next(c for c in result["continuations"] if c.get("page") == name + ".rows")
        assert continuation["offset"] == actual["next_offset"]
    assert all(r["ts"] is None for r in body["undated"]["rows"])


@pytest.mark.parametrize("field", [False, True])
def test_raw_character_prefix_preserves_refhash_scope_pointer_and_full_length(field):
    data = record(field=field)
    original = deepcopy(data)
    result = budget.fit(data, 1100)
    body = result["data"]
    assert body and 0 < len(body["text"]) < len(data["text"])
    assert body["text"] == data["text"][:len(body["text"])]
    for name in ("ref", "offset", "chars", "scope"):
        assert body[name] == data[name]
    assert body["next_offset"] == data["offset"] + len(body["text"])
    assert body["delivered_chars"] == len(body["text"]) and body["budget_truncated"]
    if field:
        assert body["pointer"] == data["pointer"] and body["field_sha256"] == "original-field-hash"
    continuation, = result["continuations"]
    assert continuation["offset"] == body["next_offset"] and continuation["ref"] == data["ref"]
    assert continuation["pointer"] == data.get("pointer") and continuation["scope"] == SCOPE
    assert data == original
    assert_bounded(result, 1100)


def test_expand_partial_first_record_and_explicit_remaining_refs():
    data = expansion()
    original = deepcopy(data)
    result = budget.fit(data, 1700)
    body = result["data"]
    assert body and body["items_total"] == 3 and body["items_delivered"] == 1
    first, = body["items"]
    assert first["records_total"] == 2 and first["records_delivered"] == 1
    assert first["delivery_status"] == "partial"
    assert first["withheld"] == data["items"][0]["withheld"]
    assert first["records"][0]["field_sha256"] == "original-field-hash"
    assert body["gaps"] == data["gaps"] and body["unknown_count"] == 3
    assert [c["item_index"] for c in result["continuations"] if c["kind"] == "expansion_item"] == [1, 2]
    record_cont = [c for c in result["continuations"] if c["kind"] == "record"]
    assert len(record_cont) == 6
    assert record_cont[0]["delivery_status"] == "partial" and record_cont[0]["offset"] > 7
    assert all(c["offset"] == 7 and c["delivery_status"] == "not_delivered" for c in record_cont[1:])
    assert all(c["scope"] == SCOPE for c in result["continuations"])
    assert data == original
    assert_bounded(result, 1700)


def test_expansion_receipt_only_contains_delivered_body_and_char_count():
    # The production collector reads the projected body, not continuation refs.
    from migloop.investigation import _delivery
    result = budget.fit(expansion(), 1700)
    delivered = _delivery(result["data"])["records"]
    assert len(delivered) == 1
    part = result["data"]["items"][0]["records"][0]
    assert delivered[0]["ref"] == part["ref"] and delivered[0]["chars"] == len(part["text"])
    assert delivered[0]["next_offset"] == part["next_offset"]


@pytest.mark.parametrize("original_truncated", [True, False])
def test_diff_prefix_preserves_original_diff_chars_and_does_not_fake_raw_offset(original_truncated):
    data = {"schema": "migloop-time-state/1", "tool": "diff", "scope": deepcopy(SCOPE), "known": False,
            "gaps": [{"paths": ["/project/A.ets"], "reason": "author_unknown"}],
            **page([{"ref": "#source:1@L5", "agent": None, "diff": "-old\n+new\n" * 700,
                     "diff_chars": 17000, "truncated": original_truncated, "basis": "observed_interval_not_single_writer"}])}
    result = budget.fit(data, 1100)
    body = result["data"]
    row, = body["rows"]
    assert row["diff_chars"] == 17000 and row["truncated"] is True
    assert row["agent"] is None and row["basis"] == data["rows"][0]["basis"]
    assert row["diff"] == data["rows"][0]["diff"][:len(row["diff"])]
    assert body["gaps"] == data["gaps"] and not body["known"]
    continuation, = result["continuations"]
    assert continuation["kind"] == "derived_diff_requery"
    assert continuation["args_patch"] == {"offset": 0, "limit": 1, "max_chars": 17000}
    assert "offset" not in row  # No invented character offset for a row-paged API.


def test_indivisible_metadata_defers_with_precise_original_continuation():
    data = {"schema": "migloop-time-changes/1", "scope": deepcopy(SCOPE),
            **page([{"id": "candidate:one", "status": "candidate_effect", "metadata": "m" * 5000}], offset=11, total=20),
            "gaps": [{"reason": "unknown_time"}]}
    result = budget.fit(data, 1000)
    assert result["status"] == "deferred" and result["data"] is None and result["data_chars"] == 0
    assert result["continuations"][0]["offset"] == 11
    assert result["continuations"][0]["scope"] == SCOPE


def test_large_gaps_are_not_silently_omitted_to_deliver_rows():
    data = view(1)
    data["gaps"].append({"error": "unknown" * 1000})
    result = budget.fit(data, 2000)
    assert result["status"] == "deferred" and result["data"] is None
    assert data["gaps"][1]["error"] == "unknown" * 1000


@pytest.mark.parametrize("schema", ["future-query/9", "migloop-time-view/2", None])
def test_unknown_schema_is_never_reinterpreted_as_known_page(schema):
    data = {"schema": schema, "scope": deepcopy(SCOPE), **page([{"ref": "raw:a:L1:hash", "text": "x" * 2000}])}
    small = budget.fit(data, 500)
    assert small["status"] == "deferred" and small["data"] is None
    assert small["continuations"][0]["kind"] == "repeat_original_query"
    large = budget.fit(data, 5000)
    assert large["data"] == data and not large["budget_adjusted"]


@pytest.mark.parametrize("amount", [-1, True, 1.5, "1000"])
def test_invalid_budget_is_not_silently_coerced(amount):
    with pytest.raises(ValueError):
        budget.fit(view(), amount)


def test_unrecognized_receipt_does_not_keep_a_false_delivery_claim():
    data = view()
    data["receipt"] = {"schema": "signed-future-receipt/1", "body_sha256": "original"}
    result = budget.fit(data, 1500)
    assert result["status"] == "deferred"
    assert "receipt" in result["reason"]


def test_trailing_requested_rows_not_already_materialized_are_not_fabricated():
    data = view(1)
    result = budget.fit(data, 1500)
    assert len(result["data"]["rows"]) == 1 and result["data"]["total"] == 20
    assert result["continuations"][0]["offset"] == 4


def test_empty_page_with_oversized_metadata_still_has_a_retry():
    data = {"schema": "migloop-time-changes/1", "scope": deepcopy(SCOPE),
            **page([]), "gaps": [{"reason": "large" * 1000}]}
    result = budget.fit(data, 700)
    assert result["status"] == "deferred" and result["data"] is None
    assert result["continuations"][0]["kind"] == "repeat_original_query"
    assert result["continuations"][0]["scope"] == SCOPE


def test_nonstring_unknown_schema_is_conservative_not_an_exception():
    result = budget.fit({"schema": ["future"], "text": "x" * 2000}, 500)
    assert result["status"] == "deferred" and result["data"] is None
    assert result["continuations"][0]["kind"] == "repeat_original_query"


def related_page(rows, *, offset=0, total=10, limit=8):
    result = page(rows, offset=offset, total=total, limit=limit)
    query = {"tool": "changes", "scope": deepcopy(SCOPE),
             "args": {"related_offset": offset, "related_limit": limit, "path": SCOPE["key"]}}
    result["query"] = query
    result["next_query"] = deepcopy(query) if result["next_offset"] is not None else None
    if result["next_query"]:
        result["next_query"]["args"]["related_offset"] = result["next_offset"]
    return result


def related_changes():
    related = related_page([{"id": f"related-{i}", "category": "shell", "status": "result_only",
        "effect_status": "unknown", "classification": "unclassified_related", "metadata": "x" * 6000} for i in range(2)])
    related.update(review_required_total=9, category_counts={"shell": 9, "readonly": 1},
                   status_counts={"result_only": 10}, readonly={"total": 1, "tool_counts": {"Read": 1}},
                   gaps=[{"source": "other", "reason": "undated native"}],
                   undated=related_page([{"ref": "raw:source:L7:stable-hash", "time_status": "unknown"}],
                                         offset=3, total=7, limit=2))
    related["undated"]["cutoff_evidence"] = False
    return {"schema": "migloop-time-changes/1", "scope": deepcopy(SCOPE), "gaps": [],
            **page([{"id": "known-write", "status": "confirmed_change", "evidence": ["raw:s:L1:hash"]}]),
            "unclassified_related": related}


def test_related_zero_delivery_restarts_at_zero_without_changing_scope_or_known_rows():
    data = related_changes()
    original = deepcopy(data)
    result = budget.fit(data, 2300)
    body = result["data"]
    assert body and body["rows"] == data["rows"] and body["scope"] == SCOPE
    related = body["unclassified_related"]
    assert related["rows"] == [] and related["limit"] == related["actual_limit"] == 0
    assert related["next_offset"] == 0 and related["remaining"] == 10
    assert related["next_query"] == {**data["unclassified_related"]["query"],
        "args": {"related_offset": 0, "related_limit": 8, "path": SCOPE["key"]}}
    assert related["query"] == data["unclassified_related"]["query"]
    for key in ("total", "review_required_total", "category_counts", "status_counts", "readonly", "gaps"):
        assert related[key] == data["unclassified_related"][key]
    follow = next(c for c in result["continuations"] if c.get("page") == "unclassified_related.rows")
    assert follow["args_patch"] == {"related_offset": 0, "related_limit": 8}
    assert follow["next_query"] == related["next_query"] and follow["scope"] == SCOPE
    # Refitting an already projected empty page must not turn actual limit 0
    # into an invalid continuation request or lose its offset 0.
    again = budget.fit(body, budget.size(body))
    follow_again = next(c for c in again["continuations"] if c.get("page") == "unclassified_related.rows")
    assert follow_again["args_patch"] == follow["args_patch"]
    assert data == original
    assert_bounded(result, 2300)


def test_related_undated_page_is_independent_and_never_becomes_cutoff_evidence():
    data = related_changes()
    result = budget.fit(data, 2300)
    parent = result["data"]["unclassified_related"]
    undated = parent["undated"]
    assert undated["rows"] == data["unclassified_related"]["undated"]["rows"]
    assert undated["next_offset"] == 4 and parent["next_offset"] == 0
    assert undated["remaining"] == 3 and undated["total"] == 7 and undated["cutoff_evidence"] is False
    assert undated["next_query"]["args"] == {"related_offset": 4, "related_limit": 2, "path": SCOPE["key"]}
    follow = next(c for c in result["continuations"] if c.get("page") == "unclassified_related.undated.rows")
    assert follow["args_patch"] == {"related_offset": 4, "related_limit": 2}
    assert follow["next_query"] == undated["next_query"]
    assert "offset" not in follow["args_patch"] and "limit" not in follow["args_patch"]


def test_main_page_zero_actual_limit_has_a_nonzero_requested_continuation():
    data = view(1)
    data["offset"] = 0
    data["rows"][0]["annotations"] = [{"large_indivisible_metadata": "x" * 5000}]
    data["undated"] = page([{"ref": "raw:unknown:L1:hash", "ts": None}], total=1)
    result = budget.fit(data, 1600)
    assert result["data"]["limit"] == 0 and result["data"]["next_offset"] == 0
    main = next(c for c in result["continuations"] if c.get("page") == "rows")
    assert main["args_patch"] == {"offset": 0, "limit": 1}


def test_terminal_related_query_is_recreated_after_budget_trims_the_last_page():
    data = related_changes()
    related = data["unclassified_related"]
    related.update(total=2, next_offset=None, remaining=0, next_query=None)
    result = budget.fit(data, 2300)
    fitted = result["data"]["unclassified_related"]
    assert fitted["next_offset"] == 0 and fitted["next_query"] is not None
    assert fitted["next_query"]["scope"] == related["query"]["scope"]
    assert fitted["next_query"]["args"]["related_offset"] == 0
    assert data["unclassified_related"]["next_query"] is None


def test_small_real_changes_function_and_budget_projection_keep_effects_and_related_prefix(tmp_path):
    # Only a synthetic 20-line source, not a frozen experiment pool or model run.
    from migloop import investigation
    from tests.test_atoms import _call, _ledger
    from tests.test_change_inventory import PATH, ts
    rows = _call(ts(0), "write", "Write", {"file_path": PATH, "content": "known\n"},
                 out="File created successfully at: " + PATH)
    for index in range(8):
        rows += _call(ts(index + 2), f"unknown-{index}", "UnparsedTool", {"text": PATH})
    unknown_time = _call(ts(12), "undated", "UnparsedTool", {"text": PATH})
    for row in unknown_time:
        row["timestamp"] = None
    ledger = _ledger(tmp_path, [*rows, *unknown_time])
    data = investigation.changes(ledger, PATH, ts(30), related_limit=8)
    original = deepcopy(data)
    result = budget.fit(data, budget.size(data) // 2)
    fitted = result["data"]
    assert fitted and fitted["rows"] == data["rows"] and fitted["scope"] == data["scope"]
    related, before = fitted["unclassified_related"], data["unclassified_related"]
    assert 0 < len(related["rows"]) < len(before["rows"])
    assert related["rows"] == before["rows"][:len(related["rows"])]
    assert related["total"] == before["total"] == 8
    assert related["review_required_total"] == before["review_required_total"] == 8
    assert all(row["effect_status"] == "unknown" and row["agent"] is None for row in related["rows"])
    assert related["next_query"]["args"] == {"related_offset": len(related["rows"]), "related_limit": 8}
    assert related["next_query"]["scope"] == before["query"]["scope"]
    assert related["undated"]["total"] == before["undated"]["total"] == 1  # Only the request mentions PATH.
    for key in ("category_counts", "status_counts", "readonly", "gaps"):
        assert related[key] == before[key]
    assert data == original
    assert_bounded(result, budget.size(data) // 2)
