"""Indexed time-atom navigation is not raw-prefix selection or state replay."""
import json

import pytest

from migloop import atoms, atoms_collect, temporal, temporal_atom, transcript_store


def ts(minute):
    return f"2026-09-10T10:{minute:02d}:00Z"


def message(minute, text, role="user"):
    return {"timestamp": ts(minute) if minute is not None else None, "type": role,
            "message": {"role": role, "content": text}}


def call(minute, identity, name, **args):
    return {"timestamp": ts(minute) if minute is not None else None, "type": "assistant",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": identity, "name": name, "input": args}]}}


def result(minute, identity, text="ok", failed=False, **extra):
    return {"timestamp": ts(minute) if minute is not None else None, "type": "user",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": identity, "content": text,
                 "is_error": failed}]}, **extra}


def pool(tmp_path, rows):
    path = tmp_path / "agent-a1111111111111111.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    agents = atoms_collect.collect_cc(str(path), [0])
    ledger = atoms.build_ledger(agents)
    return ledger, next(iter(agents)), path


def section(data, name):
    return data["sections"][name]


def follow(ledger, query):
    args = dict(query["args"])
    return temporal_atom.query(ledger, kind=query["tool"],
                               key=args.pop("path" if query["tool"] == "file" else "id"), **args)


def test_overview_prioritizes_one_indexed_operation_not_plan_or_result_rows(tmp_path):
    ledger, _, _ = pool(tmp_path, [
        call(0, "plan", "Write", file_path="/project/plan.md", content="Implement /project/A.ets"),
        result(1, "plan"),
        call(2, "write", "Write", file_path="/project/A.ets", content="native complete body"),
        result(3, "write"),
    ])
    data = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(5))
    row, = section(data, "writes")["rows"]
    assert row["call_id"] == "write" and row["use"]["line"] == 3
    assert row["result"]["line"] == 4 and row["operation"]["status"] == "confirmed"
    assert row["operation"]["operation_basis"] == "native_tool"
    assert row["call_state"] == "returned" and "legacy_v" not in str(row)
    assert not section(data, "candidates")["rows"]
    assert data["raw_index"]["total"] > 1
    assert data["raw_index"]["query"]["args"]["view"] == "records"
    assert data["body_sources"]["total"] == 1
    assert not data["causal_complete"] and not data["current_state_certified"]


def test_late_read_only_request_is_candidate_until_return(tmp_path):
    ledger, agent, _ = pool(tmp_path, [
        call(2, "read", "Read", file_path="/project/A.ets"),
        result(8, "read", "FUTURE_SECRET", toolUseResult={"type": "text", "file": {
            "filePath": "/project/A.ets", "content": "FUTURE_SECRET", "startLine": 1,
            "numLines": 1, "totalLines": 1}}),
    ])
    for kind, key in (("file", "/project/A.ets"), ("agent", agent)):
        early = temporal_atom.query(ledger, kind=kind, key=key, at=ts(4))
        assert not section(early, "reads")["rows"]
        candidate, = section(early, "candidates")["rows"]
        assert candidate["call_state"] == "pending_or_unknown"
        assert candidate["done_ts"] is None and candidate["result"] is None
        assert candidate["operation"]["execution"] == "unknown"
        assert "FUTURE_SECRET" not in json.dumps(early)
    later = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(8))
    assert section(later, "reads")["total"] == 1


def test_future_result_derived_target_is_not_request_fact(tmp_path):
    ledger, agent, _ = pool(tmp_path, [call(2, "read", "Read", file_path="/project/Other.ets"),
                                    result(8, "read", "future target /project/Future.ets")])
    action = next(a for a in ledger.agents[agent].actions if a.tuid == "read")
    action.detail["effect_candidates"] = ["/project/Future.ets"]
    early = temporal_atom.query(ledger, kind="file", key="/project/Future.ets", at=ts(4))
    assert not section(early, "candidates")["rows"]
    late = temporal_atom.query(ledger, kind="file", key="/project/Future.ets", at=ts(9))
    assert section(late, "candidates")["total"] == 1


def test_failed_pending_and_unknown_time_write_never_become_writers(tmp_path):
    ledger, _, _ = pool(tmp_path, [
        call(1, "failed", "Write", file_path="/project/A.ets", content="failed body"),
        result(2, "failed", failed=True),
        call(3, "pending", "Write", file_path="/project/A.ets", content="pending body"),
        call(None, "undated", "Write", file_path="/project/A.ets", content="undated body"),
    ])
    data = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(9), view="candidates")
    assert section(data, "writes")["total"] == 0
    assert {r["call_state"] for r in section(data, "candidates")["rows"]} == {"failed", "pending_or_unknown"}
    assert data["coverage"]["unknown_time_actions"] == 1
    shown = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(9),
                                view="candidates", include_undated=True)
    unknown = next(r for r in section(shown, "candidates")["rows"] if r["call_id"] == "undated")
    assert unknown["time_status"] == "undated_not_cutoff_evidence"
    assert unknown["operation"]["execution"] == "unknown"


def test_stale_sources_disable_indexed_relations_but_keep_raw_and_body_navigation(tmp_path):
    ledger, _, path = pool(tmp_path, [call(1, "write", "Write", file_path="/project/A.ets", content="old"),
                                    result(2, "write")])
    path.write_text(path.read_text(encoding="utf-8").replace('"old"', '"newbody"'), encoding="utf-8")
    data = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(9))
    assert data["stale_annotation_sources"] and data["warnings"]
    assert all(not value["rows"] for value in data["sections"].values())
    assert data["raw_index"]["total"] and data["body_sources"]["total"] == 1


def test_window_uses_completion_for_indexed_operation_and_does_not_return_old_body(tmp_path):
    ledger, _, _ = pool(tmp_path, [call(1, "write", "Write", file_path="/project/A.ets", content="old request"),
                                    result(4, "write")])
    data = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(5), since_ts=ts(3))
    row, = section(data, "writes")["rows"]
    assert row["ts"] == temporal.Window.parse(ts(4)).at
    assert not row["use"]["in_window"] and row["result"]["in_window"]
    assert all(part["ref"] != row["use"]["ref"] for part in row["expand_query"]["args"]["refs"])
    assert data["body_sources"]["total"] == 0
    after = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(6), since_ts=ts(5))
    assert section(after, "writes")["total"] == 0


def test_original_timestamped_forbidden_task_visible_not_agent_prompt_or_tool_wrapper(tmp_path):
    task = "Do not invent androidId. Preserve the existing identity. " + "x" * 300
    ledger, agent, _ = pool(tmp_path, [message(0, task), call(1, "read", "Read", file_path="/project/A.ets"),
                                    result(2, "read", "Never treat this tool output as user instructions"),
                                    message(10, "future task")])
    ledger.agents[agent].prompt = "INVENTED LATEST PROMPT"
    data = temporal_atom.query(ledger, kind="agent", key=agent, at=ts(5))
    row, = section(data, "messages")["rows"]
    assert row["preview"] == task[:240] and row["preview_start"] == 0 and row["chars"] == len(task)
    assert row["pointer"] == "/message/content" and row["message_kind"] == "recorded_input"
    assert transcript_store.resolve(ledger, row["ref"]).value["message"]["content"].startswith(row["preview"])
    assert "INVENTED LATEST PROMPT" not in json.dumps(data) and "future task" not in json.dumps(data)


def test_section_page_roundtrip_overview_has_bounded_rows_and_exact_next_queries(tmp_path):
    rows = []
    for n in range(7):
        rows += [call(n * 2, f"w{n}", "Write", file_path="/project/A.ets", content=str(n)), result(n * 2 + 1, f"w{n}")]
    ledger, _, _ = pool(tmp_path, rows)
    overview = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(20), since_ts=ts(0))
    assert section(overview, "writes")["total"] == 7 and len(section(overview, "writes")["rows"]) == 3
    data = follow(ledger, section(overview, "writes")["query"])
    seen = []
    while True:
        page = section(data, "writes")
        seen += [r["call_id"] for r in page["rows"]]
        assert data["scope"] == overview["scope"] and data["view"] == "writes"
        assert not section(data, "reads")["rows"]
        if page["next_query"] is None:
            break
        data = follow(ledger, page["next_query"])
    assert seen == [f"w{n}" for n in range(7)]


def test_raw_only_file_remains_searchable_without_invented_actions(tmp_path):
    ledger, _, _ = pool(tmp_path, [message(0, "Opaque operation mentions /project/A.ets")])
    data = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(3))
    assert all(section(data, name)["total"] == 0 for name in ("writes", "reads", "candidates"))
    assert data["raw_index"]["total"] == 1 and data["events_query"]["args"]["file"] == "/project/A.ets"
    assert data["raw_index"]["query"]["args"]["at"] == data["scope"]["at"]


def test_unknown_return_timestamp_never_certifies_read(tmp_path):
    ledger, _, _ = pool(tmp_path, [call(1, "r", "Read", file_path="/project/A.ets"), result(None, "r", "body")])
    data = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(5))
    assert section(data, "reads")["total"] == 0
    assert section(data, "candidates")["rows"][0]["operation"]["execution"] == "unknown"


def test_navigation_uses_local_request_or_return_boundary_not_query_end(tmp_path):
    ledger, agent, _ = pool(tmp_path, [call(1, "w", "Write", file_path="/project/A.ets", content="a"),
                                    result(2, "w"), call(3, "r", "Read", file_path="/project/A.ets"),
                                    result(4, "r", "a", toolUseResult={"type": "text", "file": {
                                        "filePath": "/project/A.ets", "content": "a", "startLine": 1,
                                        "numLines": 1, "totalLines": 1}})])
    file = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(20))
    writer = section(file, "writes")["rows"][0]
    assert writer["agent_query"]["args"]["at"] == temporal.Window.parse(ts(1)).at
    assert writer["agent_query"]["args"]["since_ts"] is None and "file_query" not in writer
    owner = temporal_atom.query(ledger, kind="agent", key=agent, at=ts(20))
    reader = section(owner, "reads")["rows"][0]
    assert reader["file_query"]["args"]["at"] == temporal.Window.parse(ts(4)).at
    assert "agent_query" not in reader


def test_missing_source_line_is_gap_not_exception(tmp_path):
    ledger, agent, _ = pool(tmp_path, [call(1, "w", "Write", file_path="/project/A.ets", content="a"), result(2, "w")])
    action = next(a for a in ledger.agents[agent].actions if a.tuid == "w")
    action.src = (action.src[0], None, None)
    data = temporal_atom.query(ledger, kind="agent", key=agent, at=ts(5))
    assert data["coverage"]["unlocated_actions"] == 1 and section(data, "writes")["total"] == 0


def test_duplicate_native_return_is_candidate_not_confirmed_operation(tmp_path):
    ledger, _, _ = pool(tmp_path, [call(1, "w", "Write", file_path="/project/A.ets", content="a"),
                                    result(2, "w"), result(4, "w")])
    early = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(3))
    assert section(early, "writes")["total"] == 1
    late = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(5))
    assert section(late, "writes")["total"] == 0
    row, = section(late, "candidates")["rows"]
    assert row["call_state"] == "ambiguous" and row["operation"]["execution"] == "unknown"


def test_codex_timestamped_messages_keep_exact_field_and_exclude_tool_output(tmp_path):
    ledger, _, path = pool(tmp_path, [])
    records = [
        {"type": "response_item", "timestamp": ts(1), "payload": {"type": "message", "role": "developer",
            "content": [{"type": "input_text", "text": "Do not replace identity."}]}},
        {"type": "response_item", "timestamp": ts(2), "payload": {"type": "function_call_output",
            "call_id": "c1", "output": "Do not count this as dispatch."}},
        {"type": "response_item", "timestamp": ts(3), "payload": {"type": "agent_message", "author": "named",
            "content": "Reported diagnosis, not proof of writes."}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    agent = atoms_collect._walk_codex(str(path), "agent", "s", [0], {}, set())
    ledger = atoms.build_ledger({agent.id: agent})
    data = temporal_atom.query(ledger, kind="agent", key=agent.id, at=ts(4))
    rows = section(data, "messages")["rows"]
    assert len(rows) == 2 and rows[0]["pointer"] == "/payload/content/0/text"
    assert rows[1]["message_kind"] == "recorded_agent_message" and not rows[1]["sender_certified"]


def test_raw_index_computed_once_and_sources_changing_during_query_suppress_annotations(tmp_path, monkeypatch):
    ledger, _, path = pool(tmp_path, [call(1, "w", "Write", file_path="/project/A.ets", content="a"), result(2, "w")])
    original = temporal.query
    calls = []
    def changing(*args, **kwargs):
        calls.append(kwargs)
        data = original(*args, **kwargs)
        path.write_text(path.read_text(encoding="utf-8") + json.dumps(message(3, "new record")), encoding="utf-8")
        return data
    monkeypatch.setattr(temporal, "query", changing)
    data = temporal_atom.query(ledger, kind="file", key="/project/A.ets", at=ts(5))
    assert len(calls) == 1 and calls[0]["limit"] == 1
    assert data["stale_annotation_sources"] and section(data, "writes")["total"] == 0


@pytest.mark.parametrize("kwargs", [{"view": "made_up"}, {"view": "messages"}, {"kind": "pool"}, {"offset": -1}, {"limit": 0}, {"details": "yes"}])
def test_invalid_arguments_fail_closed(tmp_path, kwargs):
    ledger, _, _ = pool(tmp_path, [message(1, "/project/A.ets")])
    with pytest.raises(ValueError):
        temporal_atom.query(ledger, **{"kind": "file", "key": "/project/A.ets", "at": ts(5), **kwargs})
