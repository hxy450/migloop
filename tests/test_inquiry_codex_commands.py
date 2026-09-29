"""Runtime receipt fixture from Mac DiceRoller, with sanitized paths/content."""
import copy
import json

import pytest

from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check
from migloop.inquiry.source_adapters.codex_commands import literal_read_paths
from migloop.inquiry.store import Store, describe_source, timestamp
from migloop.inquiry.viewer import viewer_query


def ts(second):
    return f"2026-01-01T00:00:{second:02d}Z"


def execution(command="sed -n '1,20p' spec.md", paths=("spec.md",)):
    return {"type": "event_msg", "timestamp": ts(2), "payload": {
        "type": "item_completed", "thread_id": "cx", "item": {
            "type": "CommandExecution", "id": "exec-native", "cwd": "file:///proj",
            "command": ["/bin/zsh", "-lc", command], "status": "completed", "exit_code": 0,
            "stdout": "gap=4\n", "stderr": "",
            "parsed_cmd": [{"type": "read", "path": p} for p in paths]}}}


def build(tmp_path, events):
    rows = [{"type": "session_meta", "timestamp": ts(0), "payload": {"id": "cx", "cwd": "/elsewhere"}}] + events
    path = tmp_path / "native.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return Store.build(tmp_path / "index.sqlite", [describe_source(path, path.name)])


def test_runtime_read_connects_card_and_preserves_original(tmp_path):
    read = execution()
    write = {"type": "event_msg", "timestamp": ts(4), "payload": {
        "type": "item_completed", "thread_id": "cx", "item": {
            "type": "FileChange", "id": "patch-native", "status": "completed",
            "changes": {"/proj/A.ets": {"type": "update", "unified_diff": "-gap=4\n+gap=8"}}}}}
    s = build(tmp_path, [read, write])
    try:
        engine = Engine(s)
        effects = s.rows("SELECT * FROM effects ORDER BY at")
        assert [(r["op"], r["path"], r["strength"]) for r in effects] == [
            ("read", "/proj/spec.md", "confirmed"), ("write", "/proj/A.ets", "confirmed")]
        assert effects[0]["at"] == timestamp(ts(2))
        assert not engine.relations("agent", "cx", timestamp(ts(1)))
        meta, raw = s.source_record(effects[0]["result"])
        assert meta["line"] == 2 and json.loads(raw) == read
        original = viewer_query(engine, {"view": "operation", "kind": "agent", "key": "cx", "at": ts(5), "id": effects[0]["id"]})
        assert "gap=4" in original["content"]
        assert original["content_kind"] == "command_read_observation"
        draft = {"target": {"key": "/proj/A.ets", "at": ts(5)}, "summary": "fixture", "recommendations": ["fixture"],
                 "nodes": [{"key": "/proj/spec.md", "at": ts(2), "reason": "correct input"},
                           {"key": "cx", "at": ts(4), "reason": "deviation", "problem": True},
                           {"key": "/proj/A.ets", "at": ts(5), "reason": "target"}],
                 "edges": [{"from": 1, "to": 2}, {"from": 2, "to": 3}]}
        outcome = check(engine, json.dumps(draft), save=True)
        assert outcome["mechanical_status"] == "valid", outcome
        assert outcome["path_status"] == "complete", outcome
    finally:
        s.close()


def test_multi_file_output_is_not_fabricated_as_individual_file_body(tmp_path):
    event = execution("cat spec.md; printf '%s\\n' separator; cat other.md", ("spec.md", "other.md"))
    event["payload"]["item"]["stdout"] = "first\nseparator\nsecond\n"
    s = build(tmp_path, [event])
    try:
        rows = s.rows("SELECT * FROM effects")
        assert len(rows) == 2
        assert len(s.rows("SELECT * FROM calls")) == 1
        assert len(s.rows("SELECT * FROM tool_returns")) == 1
        for row in rows:
            body = viewer_query(Engine(s), {"view": "operation", "kind": "file", "key": row["path"], "at": ts(5), "id": row["id"]})
            assert "first\nseparator\nsecond" in body["content"]
            assert "合并输出" in body["note"]
    finally:
        s.close()


@pytest.mark.parametrize("change", [
    {"exit_code": 1}, {"status": "failed"}, {"status": "running"}, {"exit_code": None},
    {"stderr": "cat: missing file"}, {"stderr": None}, {"stdout": None}, {"parsed_cmd": []}, {"cwd": "relative"},
    {"parsed_cmd": [{"type": "read", "path": "other.md"}]},
    {"command": ["powershell", "-c", "cat spec.md"]},
])
def test_unconfirmed_execution_remains_call_not_read(tmp_path, change):
    event = execution()
    event["payload"]["item"].update(change)
    s = build(tmp_path, [event])
    try:
        assert not s.rows("SELECT * FROM effects")
        assert len(s.rows("SELECT * FROM calls")) == 1
        assert len(s.rows("SELECT * FROM tool_returns")) == 1
    finally:
        s.close()


@pytest.mark.parametrize("command", [
    "false && cat spec.md || true", "echo cat spec.md", "if false; then cat spec.md; fi",
    "python read.py spec.md", "cat $SOURCE", "cat spec.md > /tmp/out", "cd /other; cat spec.md",
    "cat spec.md | head -5", "sed -n '1e' spec.md", "cat '*.md'", "cat spec.md &",
    "printf -v PATH custom; cat spec.md",
])
def test_annotation_does_not_prove_a_script_or_skipped_branch(command):
    assert literal_read_paths(execution(command)["payload"]["item"]) == []


@pytest.mark.parametrize("change", ["foreign_owner", "undated", "missing_id", "duplicate"])
def test_read_requires_unique_owned_dated_runtime_event(tmp_path, change):
    event = execution()
    if change == "foreign_owner": event["payload"]["thread_id"] = "other"
    if change == "undated": event.pop("timestamp")
    if change == "missing_id": event["payload"]["item"].pop("id")
    events = [event, copy.deepcopy(event)] if change == "duplicate" else [event]
    s = build(tmp_path, events)
    try:
        assert not s.rows("SELECT * FROM effects WHERE strength='confirmed'")
    finally:
        s.close()


def test_quoted_runtime_json_in_model_output_does_not_create_execution(tmp_path):
    event = {"type": "response_item", "timestamp": ts(3), "payload": {
        "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(execution())}]}}
    s = build(tmp_path, [event])
    try:
        assert not s.rows("SELECT * FROM calls")
        assert not s.rows("SELECT * FROM effects")
    finally:
        s.close()


@pytest.mark.parametrize("command", ["cat spec.md", "cat -- spec.md", "head -n 5 spec.md", "tail -5 spec.md"])
def test_literal_reader_forms_use_execution_cwd(command):
    item = execution(command)["payload"]["item"]
    item["cwd"] = "file:///proj%20space/subdir"
    assert literal_read_paths(item) == ["/proj space/subdir/spec.md"]


def test_file_uri_windows_and_direct_argv():
    item = execution()["payload"]["item"]
    item.update(cwd="file:///C:/project", command=["cat", "spec.md"])
    assert literal_read_paths(item) == ["C:/project/spec.md"]
