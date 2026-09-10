import json
import os

import pytest

from migloop import atoms, raw_events, transcript_store


@pytest.fixture(autouse=True)
def clear_native_cache():
    with raw_events._CACHE_LOCK:
        raw_events._CACHE.clear()
        raw_events._CACHE_BYTES = 0
    yield
    with raw_events._CACHE_LOCK:
        raw_events._CACHE.clear()
        raw_events._CACHE_BYTES = 0


def ts(minute):
    return f"2026-09-10T10:{minute:02d}:00Z"


def cc(minute, *blocks):
    return {"timestamp": ts(minute) if minute is not None else None, "type": "assistant",
            "message": {"role": "assistant", "content": list(blocks)}}


def use(identity="c1", name="Bash", **data):
    return {"type": "tool_use", "id": identity, "name": name, "input": data}


def result(identity="c1", text="ok", **extra):
    return {"type": "tool_result", "tool_use_id": identity, "content": text, **extra}


def codex(minute, kind, identity="c1", **data):
    return {"timestamp": ts(minute), "type": "response_item",
            "payload": {"type": kind, "call_id": identity, **data}}


def pool(tmp_path, rows, name="source.jsonl", aid="a"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) if not isinstance(r, str) else r
                              for r in rows) + "\n", encoding="utf-8")
    # Deliberately no Action collection or file/version stories.
    ledger = atoms.Ledger({}, {aid: atoms.AgentRec(aid, "s", sources=[str(path)])})
    return ledger, path


def pointer(ledger, access):
    value = transcript_store.resolve(ledger, access["ref"]).value
    for field in access["pointer"].split("/")[1:]:
        field = field.replace("~1", "/").replace("~0", "~")
        value = value[int(field)] if isinstance(value, list) else value[field]
    return value


def test_cc_blocks_pair_without_actions_and_payload_remains_accessible(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, {"type": "thinking", "thinking": "reason"},
                                      use(command="python arbitrary_unknown_script.py")),
                                  cc(1, result(text="UNIQUE_BIG_PAYLOAD"))])
    inventory = raw_events.inventory(ledger)
    event, = inventory["events"]
    assert event["status"] == "returned" and event["tool"] == "Bash"
    assert event["use"]["line"] == 1 and event["use"]["block"] == 1
    assert event["results"][0]["line"] == 2 and event["results"][0]["block"] == 0
    assert pointer(ledger, event["use"]["fields"]["input"])["command"].startswith("python")
    assert pointer(ledger, event["results"][0]["fields"]["output"]) == "UNIQUE_BIG_PAYLOAD"
    assert "UNIQUE_BIG_PAYLOAD" not in json.dumps(inventory)
    assert inventory["unknown_records"][0]["fields"] == ["/message/content/0"]
    assert inventory["complete"] and event["relation"] is None


@pytest.mark.parametrize("call_kind,return_kind,field", [
    ("function_call", "function_call_output", "arguments"),
    ("custom_tool_call", "custom_tool_call_output", "input"),
])
def test_codex_native_formats(tmp_path, call_kind, return_kind, field):
    ledger, _ = pool(tmp_path, [codex(0, call_kind, name="exec", **{field: "arbitrary command"}),
                                  codex(1, return_kind, output=[{"type": "text", "text": "result"}])])
    event, = raw_events.inventory(ledger)["events"]
    assert event["protocol"] == "codex" and event["status"] == "returned"
    assert event["use"]["block"] is None
    assert pointer(ledger, event["use"]["fields"]["input"]) == "arbitrary command"


def test_inner_patch_is_independent_even_with_same_id_as_outer_exec(tmp_path):
    patch = {"timestamp": ts(1), "type": "event_msg", "payload": {
        "type": "patch_apply_end", "call_id": "same", "success": True,
        "stdout": "updated", "changes": {"/p/A.ets": {"type": "update", "unified_diff": "-a\n+b"}}}}
    ledger, _ = pool(tmp_path, [codex(0, "custom_tool_call", "same", name="exec", input="tools.apply_patch(...)"),
                                  patch, codex(2, "custom_tool_call_output", "same", output="done")])
    events = raw_events.inventory(ledger)["events"]
    assert len(events) == 2
    outer = next(e for e in events if e["protocol"] == "codex")
    inner = next(e for e in events if e["protocol"] == "codex_patch")
    assert outer["results"][0]["line"] == 3
    assert inner["status"] == "independent" and inner["use"] is None
    assert inner["results"][0]["line"] == 2 and outer["id"] != inner["id"]
    assert pointer(ledger, inner["results"][0]["fields"]["changes"])["/p/A.ets"]["type"] == "update"


def test_same_call_id_never_pairs_across_sources(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use())], "first.jsonl")
    second, _ = pool(tmp_path, [cc(1, result())], "second.jsonl", "b")
    ledger.agents.update(second.agents)
    events = raw_events.inventory(ledger)["events"]
    assert {e["status"] for e in events} == {"pending", "orphan_result"}
    assert len({e["id"] for e in events}) == 2


@pytest.mark.parametrize("rows,status,anomaly", [
    ([cc(0, use()), cc(1, use()), cc(2, result())], "ambiguous", "duplicate_use"),
    ([cc(0, use()), cc(1, result()), cc(2, result())], "ambiguous", "duplicate_result"),
    ([cc(0, result()), cc(1, use())], "out_of_order", "out_of_order"),
    ([cc(2, use()), cc(1, result())], "out_of_order", "out_of_order"),
    ([cc(0, use(None)), cc(1, result(None))], "missing_call_id", "missing_call_id"),
])
def test_pairing_anomalies_are_not_discarded(tmp_path, rows, status, anomaly):
    ledger, _ = pool(tmp_path, rows)
    events = raw_events.inventory(ledger)["events"]
    assert all(e["status"] == status and anomaly in e["anomalies"] for e in events)
    assert sum(len(e["uses"]) + len(e["results"]) for e in events) == len(rows)


def test_same_record_pairing_respects_block_order(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use(), result(), result("reverse"), use("reverse"))])
    events = raw_events.inventory(ledger)["events"]
    assert [e["status"] for e in events] == ["returned", "out_of_order"]


@pytest.mark.parametrize("payload", [
    {"is_error": True}, {"success": False}, {"exit_code": 1}, {"output": {"exit_code": 2}},
])
def test_structured_failures_are_preserved(tmp_path, payload):
    ledger, _ = pool(tmp_path, [codex(0, "function_call", name="unknown", arguments="{}"),
                                  codex(1, "function_call_output", **payload)])
    assert raw_events.inventory(ledger)["events"][0]["status"] == "failed"


def test_failure_word_in_output_is_not_execution_proof(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use()), cc(1, result(text="quoted log says failed; exit code 1"))])
    assert raw_events.inventory(ledger)["events"][0]["status"] == "returned"


def test_nested_native_looking_json_is_not_an_extra_native_call(tmp_path):
    nested = json.dumps(cc(0, use("invented")))
    ledger, _ = pool(tmp_path, [cc(0, use(command=nested)), cc(1, result(text=nested)),
                              {"timestamp": ts(2), "type": "message", "text": nested}])
    data = raw_events.inventory(ledger)
    assert len(data["events"]) == 1 and data["events"][0]["call_id"] == "c1"
    assert len(data["unknown_records"]) == 1


def test_ordinary_unknown_malformed_and_nonobject_records_remain_reachable(tmp_path):
    ledger, _ = pool(tmp_path, [{"timestamp": ts(0), "type": "message", "text": "SPEC A.ets"},
                              {"timestamp": ts(1), "type": "unknown_future_kind", "code": "opaque A.ets"},
                              ["saved A.ets"], "{broken A.ets"])
    data = raw_events.inventory(ledger)
    assert not data["events"] and len(data["unknown_records"]) == 4
    assert not data["complete"] and data["gaps"][0]["line"] == 4
    for entry in data["unknown_records"]:
        assert transcript_store.resolve(ledger, entry["ref"]).line == entry["line"]
    result = raw_events.query(ledger, ts(5), path="/p/A.ets")
    assert result["unknown_records"]["total"] == 2 and result["undated"]["total"] == 2


def test_future_return_status_body_and_duplicate_are_hidden(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use(command="known")),
                              cc(10, result(text="FUTURE_SECRET", is_error=True)), cc(11, result())])
    inventory = raw_events.inventory(ledger)
    assert inventory["events"][0]["status"] == "ambiguous"
    early = raw_events.query(ledger, ts(5))
    event, = early["events"]
    assert event["status"] == "pending_or_unknown" and event["results"] == []
    assert event["anomalies"] == [] and "FUTURE_SECRET" not in str(early)
    assert raw_events.query(ledger, ts(5), path="FUTURE_SECRET")["total"] == 0
    at_return = raw_events.query(ledger, ts(10))["events"][0]
    assert at_return["status"] == "failed" and len(at_return["results"]) == 1
    assert event["id"] == at_return["id"] == inventory["events"][0]["id"]


def test_since_filters_each_part_and_equal_offset_times_are_inclusive(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use()), cc(5, result())])
    output = raw_events.query(ledger, "2026-09-10T06:05:00-04:00", since_ts=ts(5))
    event, = output["events"]
    assert event["use"] is None and event["uses"] == [] and event["status"] == "result_only"
    assert event["results"][0]["line"] == 2


def test_undated_native_parts_do_not_complete_a_call(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use()), cc(None, result(text="UNDATED"))])
    output = raw_events.query(ledger, ts(5))
    assert output["events"][0]["status"] == "pending_or_unknown"
    assert output["undated"]["total"] == 1
    assert "UNDATED" not in json.dumps(output)


def test_path_is_lexical_and_uses_only_visible_matching_parts(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use(name="Write", file_path="/p/report.md", content="mentions A.ets")),
                              cc(1, result()), cc(2, use("other", file_path="/p/B.ets"))])
    output = raw_events.query(ledger, ts(5), path="/p/A.ets")
    assert output["total"] == 1
    event, = output["events"]
    assert event["association"] == "lexical_mention_not_effect" and event["relation"] is None
    assert "writer" not in event and event["matched_parts"][0]["line"] == 1


def test_query_paginates_after_scanning_and_keeps_unknown_entries(tmp_path):
    rows = [cc(i, use(str(i), command=f"operation{i}")) for i in range(10)]
    rows += [{"timestamp": ts(12), "type": "unknown", "text": "last"}]
    ledger, _ = pool(tmp_path, rows)
    first = raw_events.query(ledger, ts(20), limit=2)
    assert first["total"] == 10 and first["next_offset"] == 2 and first["remaining"] == 8
    last = raw_events.query(ledger, ts(20), path="operation9", limit=1)
    assert last["total"] == 1 and last["events"][0]["use"]["line"] == 10
    assert first["unknown_records"]["total"] == 1


def test_agent_scope_uses_sources_not_action_membership(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use())])
    second, _ = pool(tmp_path, [cc(1, use("other"))], "second.jsonl", "b")
    ledger.agents.update(second.agents)
    scoped = raw_events.query(ledger, ts(5), agent="a")
    assert scoped["total"] == 1 and scoped["source_count"] == 1
    with pytest.raises(ValueError, match="agent"):
        raw_events.query(ledger, ts(5), agent="missing")


def test_path_match_does_not_borrow_native_block_text_for_unknown_block(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, {"type": "text", "text": "ordinary other message"},
                                  use(command="touch A.ets"))])
    scoped = raw_events.query(ledger, ts(5), path="A.ets")
    assert scoped["total"] == 1 and scoped["unknown_records"]["total"] == 0


def test_source_append_refreshes_inventory_and_old_line_ref_survives(tmp_path):
    ledger, path = pool(tmp_path, [cc(0, use())])
    before = raw_events.inventory(ledger)["events"][0]
    saved = path.read_text(encoding="utf-8")
    path.write_text(saved + json.dumps(cc(1, result())) + "\n", encoding="utf-8")
    after = raw_events.inventory(ledger)["events"][0]
    assert after["id"] == before["id"] and after["status"] == "returned"
    assert after["use"]["ref"] == before["use"]["ref"]
    path.write_text(saved.replace('"Bash"', '"Read"'), encoding="utf-8")
    assert raw_events.inventory(ledger)["events"][0]["tool"] == "Read"
    with pytest.raises(ValueError, match="changed"):
        transcript_store.resolve(ledger, before["use"]["ref"])


def test_source_change_during_scan_does_not_deliver_partial_inventory(tmp_path, monkeypatch):
    ledger, path = pool(tmp_path, [cc(0, use())])
    original = transcript_store.records

    def changing(path_arg, **kwargs):
        yield from original(path_arg, **kwargs)
        path.write_text(json.dumps(cc(0, use(command="changed content"))) + "\n", encoding="utf-8")

    monkeypatch.setattr(transcript_store, "records", changing)
    data = raw_events.inventory(ledger)
    assert not data["complete"] and not data["events"]
    assert "changed during inventory" in data["gaps"][0]["error"]


def test_missing_invalid_utf8_and_duplicate_names_are_explicit_gaps(tmp_path):
    ledger, path = pool(tmp_path, [cc(0, use())])
    path.write_bytes(b"\xff\n")
    data = raw_events.inventory(ledger)
    assert not data["complete"] and data["gaps"] and not data["events"]
    path.unlink()
    assert raw_events.inventory(ledger)["gaps"]
    path.write_text(json.dumps(cc(0, use())) + "\n", encoding="utf-8")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other, _ = pool(other_dir, [cc(0, use())], aid="b")
    ledger.agents.update(other.agents)
    data = raw_events.inventory(ledger)
    assert not data["complete"] and len(data["events"]) == 2 and len(data["gaps"]) == 2
    assert len({e["id"] for e in data["events"]}) == 1
    assert all(e["reference_status"] == "ambiguous_source" and not e["id_unique_in_registry"]
               for e in data["events"])


def test_event_ids_survive_moving_frozen_pool(tmp_path):
    rows = [cc(0, use()), cc(1, result()), cc(2, use(None)),
            {"timestamp": ts(3), "type": "event_msg", "payload": {
                "type": "patch_apply_end", "call_id": "patch", "success": True, "changes": {}}}]
    first_dir, second_dir = tmp_path / "first-pool", tmp_path / "moved-pool"
    first_dir.mkdir()
    second_dir.mkdir()
    first, _ = pool(first_dir, rows)
    second, _ = pool(second_dir, rows)
    before, after = raw_events.inventory(first), raw_events.inventory(second)
    assert [e["id"] for e in before["events"]] == [e["id"] for e in after["events"]]
    assert all(e["id_unique_in_registry"] for e in before["events"] + after["events"])
    assert before["events"][0]["source_path"] != after["events"][0]["source_path"]


def test_warm_inventory_and_query_do_not_redecode_source(tmp_path, monkeypatch):
    ledger, _ = pool(tmp_path, [cc(0, use(command="A.ets")), cc(1, result()),
                              {"timestamp": ts(2), "type": "unknown", "text": "A.ets"}])
    original, calls = transcript_store.records, []

    def counted(path, **kwargs):
        calls.append(path)
        yield from original(path, **kwargs)

    monkeypatch.setattr(transcript_store, "records", counted)
    first = raw_events.inventory(ledger)
    assert first["cache"]["miss"] == 1
    assert raw_events.inventory(ledger)["cache"]["hit"] == 1
    assert raw_events.query(ledger, ts(5), path="A.ets")["cache"]["hit"] == 1
    assert len(calls) == 1


def test_public_mutations_cannot_poison_cached_native_index(tmp_path):
    ledger, _ = pool(tmp_path, [cc(0, use()), cc(1, result()),
                              {"timestamp": ts(2), "type": "unknown", "text": "original"}, "{bad"])
    first = raw_events.inventory(ledger)
    ref = first["events"][0]["use"]["fields"]["input"]["ref"]
    first["events"][0]["use"]["fields"]["input"]["ref"] = "forged"
    first["events"][0]["results"][0]["fields"]["output"]["pointer"] = "/forged"
    first["unknown_records"][0]["fields"].append("/forged")
    first["unknown_records"][0]["agents"].append("forged")
    first["gaps"][0]["error"] = "forged"
    second = raw_events.inventory(ledger)
    assert second["cache"]["hit"] == 1
    assert second["events"][0]["use"]["fields"]["input"]["ref"] == ref
    assert "forged" not in json.dumps(second)


def test_cache_invalidates_changed_signature_and_registry(tmp_path, monkeypatch):
    ledger, path = pool(tmp_path, [cc(0, use())])
    original, calls = transcript_store.records, []

    def counted(path_arg, **kwargs):
        calls.append(path_arg)
        yield from original(path_arg, **kwargs)

    monkeypatch.setattr(transcript_store, "records", counted)
    raw_events.inventory(ledger)
    before = path.stat()
    path.write_text(path.read_text(encoding="utf-8").replace('"Bash"', '"Read"'), encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 10_000_000))
    assert raw_events.inventory(ledger)["events"][0]["tool"] == "Read"
    assert len(calls) == 2
    # Owner and source registry changes invalidate even unchanged source bytes.
    ledger.agents["b"] = atoms.AgentRec("b", "s", sources=[str(path)])
    data = raw_events.inventory(ledger)
    assert data["events"][0]["agents"] == ["a", "b"] and len(calls) == 3
    other, _ = pool(tmp_path, [cc(1, use("other"))], "other.jsonl", "c")
    ledger.agents.update(other.agents)
    assert raw_events.inventory(ledger)["source_count"] == 2 and len(calls) == 5


def test_oversize_indexes_are_served_without_retention(tmp_path, monkeypatch):
    ledger, _ = pool(tmp_path, [cc(0, use(command="large" * 1000))])
    monkeypatch.setattr(raw_events, "_CACHE_BUDGET", 512)
    first = raw_events.inventory(ledger)
    second = raw_events.inventory(ledger)
    assert first["events"] and first["cache"]["oversize_not_cached"] == 1
    assert second["cache"]["oversize_not_cached"] == 1
    assert not raw_events._CACHE and raw_events._CACHE_BYTES == 0


def test_cache_lru_total_size_stays_bounded(tmp_path, monkeypatch):
    ledger, _ = pool(tmp_path, [cc(0, use())])
    raw_events.inventory(ledger)
    one_size = raw_events._CACHE_BYTES
    monkeypatch.setattr(raw_events, "_CACHE_BUDGET", one_size + 128)
    for number in range(1, 4):
        other, _ = pool(tmp_path, [cc(0, use())], f"source{number}.jsonl", f"a{number}")
        raw_events.inventory(other)
        assert 0 < raw_events._CACHE_BYTES <= raw_events._CACHE_BUDGET
    assert len(raw_events._CACHE) == 1


def test_source_changed_after_cache_hit_while_next_source_decodes_is_removed(tmp_path, monkeypatch):
    ledger, first_path = pool(tmp_path, [cc(0, use())], "a-first.jsonl")
    other, _ = pool(tmp_path, [cc(1, use("second"))], "b-second.jsonl", "b")
    ledger.agents.update(other.agents)
    raw_events.query(ledger, ts(5), agent="a")  # Warm only the first source.
    original = transcript_store.records

    def changing(path_arg, **kwargs):
        yield from original(path_arg, **kwargs)
        first_path.write_text(json.dumps(cc(0, use(command="changed while reading second"))) + "\n", encoding="utf-8")

    monkeypatch.setattr(transcript_store, "records", changing)
    data = raw_events.inventory(ledger)
    assert not data["complete"] and data["cache"]["hit"] == 1
    assert [e["source"] for e in data["events"]] == ["b-second.jsonl"]
    assert any(gap["source"] == "a-first.jsonl" and "changed during inventory" in gap["error"]
               for gap in data["gaps"])


@pytest.mark.parametrize("kwargs", [{"offset": -1}, {"limit": 0}, {"limit": True},
                                    {"path": ""}, {"path": "A.ets", "agent": "a"},
                                    {"since_ts": ts(11)}])
def test_invalid_query_is_rejected(tmp_path, kwargs):
    ledger, _ = pool(tmp_path, [])
    with pytest.raises(ValueError):
        raw_events.query(ledger, ts(10), **kwargs)
