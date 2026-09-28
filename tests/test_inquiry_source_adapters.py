"""One evidence contract across three native transports, including negative cases."""
import json
import sqlite3

import pytest

from migloop.inquiry.source_adapters import adapter_for, identity, parts
from migloop.inquiry.source_adapters.export import events, freeze_deveco
from migloop.inquiry.store import Store, describe_source, timestamp
from migloop.inquiry.native_text import change_payloads, change_outline
from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check
from tests.test_inquiry_core import record, result, ts, use


def document(status="completed", end=1767225604000):
    def message(mid, pid, tool, data, start, finish, output):
        return {"info": {"id": mid, "role": "assistant", "modelID": "test-model"}, "parts": [
            {"id": pid, "type": "tool", "tool": tool, "callID": pid,
             "state": {"input": data, "status": status, "output": output,
                       "time": {"start": start, "end": finish}}}]}
    return {"info": {"id": "ses_test", "directory": "/proj", "parentID": "ses_parent"}, "messages": [
        message("m1", "p1", "read", {"filePath": "/proj/spec.md"}, 1767225601000, 1767225602000, "gap=4"),
        message("m2", "p2", "edit", {"filePath": "/proj/A.ets", "oldString": "gap=4", "newString": "gap=8"},
                1767225603000, end, "written"),
    ]}


def rows_for(platform):
    if platform == "deveco":
        return list(events(document()))
    if platform == "claude":
        return [dict(r, sessionId="session", agentId="worker", cwd="/proj") for r in [
            record(1, use("r", "Read", file_path="/proj/spec.md")), record(2, result("r", "gap=4")),
            record(3, use("w", "Edit", file_path="/proj/A.ets", old_string="gap=4", new_string="gap=8")),
            record(4, result("w"))]]
    rows = [{"type": "session_meta", "timestamp": ts(0), "payload": {"id": "cx", "cwd": "/proj"}}]
    for second, cid, name, data in [(1, "r", "read_file", {"path": "/proj/spec.md"}),
        (3, "w", "apply_patch", "*** Begin Patch\n*** Update File: /proj/A.ets\n@@\n-gap=4\n+gap=8\n*** End Patch")]:
        rows += [{"type": "response_item", "timestamp": ts(second), "payload": {
            "type": "custom_tool_call" if name == "apply_patch" else "function_call", "call_id": cid,
            "name": name, "input" if name == "apply_patch" else "arguments": data if name == "apply_patch" else json.dumps(data)}},
            {"type": "response_item", "timestamp": ts(second+1), "payload": {
             "type": "custom_tool_call_output" if name == "apply_patch" else "function_call_output", "call_id": cid,
             "output": json.dumps({"output": "gap=4" if cid == "r" else "ok", "metadata": {"exit_code": 0}})}}]
    return rows


def index(tmp_path, rows):
    path = tmp_path / "native.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return Store.build(tmp_path / "index.sqlite", [describe_source(path, path.name)])


@pytest.mark.parametrize("platform", ["claude", "codex", "deveco"])
def test_platforms_share_effects_originals_and_checker(tmp_path, platform):
    rows = rows_for(platform)
    s = index(tmp_path, rows)
    try:
        effects = s.rows("SELECT * FROM effects ORDER BY at")
        assert [(e["op"], e["path"], e["strength"]) for e in effects] == [
            ("read", "/proj/spec.md", "confirmed"), ("write", "/proj/A.ets", "confirmed")]
        assert effects[0]["at"] == timestamp(ts(2))
        assert effects[1]["at"] == timestamp(ts(4))
        assert s.rows("SELECT platform FROM source_metadata")[0]["platform"] == platform
        for e in effects:
            meta, raw = s.source_record(e["request"])
            assert json.loads(raw) == rows[meta["line"]-1]
        delta = change_outline(change_payloads(s, effects[1]))
        assert delta and "-gap=4" in delta[0]["text"] and "+gap=8" in delta[0]["text"]
        draft = {"target": {"key": "/proj/A.ets", "at": ts(5)}, "summary": "fixture", "recommendations": ["fixture"],
                 "nodes": [{"key": "/proj/spec.md", "at": ts(2), "reason": "correct input"},
                           {"key": effects[1]["agent"], "at": ts(4), "reason": "deviation", "problem": True},
                           {"key": "/proj/A.ets", "at": ts(5), "reason": "target"}],
                 "edges": [{"from": 1, "to": 2}, {"from": 2, "to": 3}]}
        # Same compact graph contract; no platform fields required from the model.
        outcome = check(Engine(s), json.dumps(draft), save=True)
        assert outcome["mechanical_status"] == "valid", outcome
        assert outcome["path_status"] == "complete", outcome
    finally:
        s.close()


def test_deveco_request_does_not_contain_future_output():
    rows = list(events(document()))
    request = next(r for r in rows if r.get("phase") == "request")
    assert "output" not in request["part"]["state"]
    assert "written" not in json.dumps(request)
    result_row = next(r for r in rows if r.get("phase") == "result")
    assert result_row["origin"]["part"] == "p1"
    assert result_row["part"] == document()["messages"][0]["parts"][0]
    assert identity(rows[0]).parent == "ses_parent"


@pytest.mark.parametrize("status,end", [("error", 1767225604000), ("completed", None), ("completed", 1767225600000)])
def test_failed_undated_or_reversed_deveco_write_not_confirmed(tmp_path, status, end):
    s = index(tmp_path, list(events(document(status, end))))
    try:
        assert not s.rows("SELECT * FROM effects WHERE op='write' AND strength='confirmed'")
    finally:
        s.close()


def test_opaque_codex_exec_is_one_call_not_fictional_nested_writes(tmp_path):
    rows = rows_for("codex")[:1] + [{"type": "response_item", "timestamp": ts(1), "payload": {
        "type": "function_call", "call_id": "outer", "name": "exec", "arguments":
        'if (false) await tools.exec_command({cmd: "python patch.py /proj/Ghost.ets"})'}}]
    s = index(tmp_path, rows)
    try:
        assert len(s.rows("SELECT * FROM calls")) == 1
        assert not s.rows("SELECT * FROM effects")
        assert s.rows("SELECT path FROM files")  # navigation only
    finally:
        s.close()


def test_selected_db_export_is_read_only_stable_and_excludes_other_sessions(tmp_path):
    db_path = tmp_path / "native.db"
    c = sqlite3.connect(db_path)
    c.executescript("CREATE TABLE session(id TEXT,parent_id TEXT,directory TEXT);"
                   "CREATE TABLE message(id TEXT,session_id TEXT,time_created INT,data TEXT);"
                   "CREATE TABLE part(id TEXT,message_id TEXT,session_id TEXT,time_created INT,data TEXT);")
    for sid, parent in [("ses_test", None), ("ses_child", "ses_test"), ("ses_other", None)]:
        c.execute("INSERT INTO session VALUES(?,?,?)", (sid, parent, "/proj"))
        for m in document()["messages"]:
            c.execute("INSERT INTO message VALUES(?,?,?,?)", (m["info"]["id"], sid, 1, json.dumps(m["info"])))
            for p in m["parts"]:
                c.execute("INSERT INTO part VALUES(?,?,?,?,?)", (p["id"], m["info"]["id"], sid, 1, json.dumps(p)))
    c.commit()
    c.close()
    original = db_path.read_bytes()
    a = freeze_deveco(db_path, tmp_path / "one", "ses_test")
    b = freeze_deveco(db_path, tmp_path / "two", "ses_test")
    assert a["sources"] == b["sources"]
    assert {x["name"] for x in a["sources"]} == {"ses_test.jsonl", "ses_child.jsonl"}
    assert db_path.read_bytes() == original
    with pytest.raises(ValueError, match="explicit root"):
        freeze_deveco(db_path, tmp_path / "all")
    with pytest.raises(ValueError, match="must be new"):
        freeze_deveco(db_path, tmp_path / "one", "ses_test")


def test_unknown_record_never_creates_calls():
    assert adapter_for({"documentation": {"tool": "write"}}) is None
    assert list(parts({"documentation": {"tool": "write"}})) == []


@pytest.mark.parametrize("status,owner,confirmed", [("completed", "cx", True), ("failed", "cx", False),
                                                ("running", "cx", False), ("completed", "other", False)])
def test_codex_native_file_change_receipt(tmp_path, status, owner, confirmed):
    event = {"type": "event_msg", "timestamp": ts(4), "payload": {
        "type": "item_completed", "thread_id": owner, "item": {"type": "FileChange", "id": "exec-native",
        "status": status, "changes": {"/proj/A.ets": {"type": "update", "unified_diff": "-gap=4\n+gap=8"}}}}}
    rows = rows_for("codex")[:1] + [event]
    s = index(tmp_path, rows)
    try:
        writes = s.rows("SELECT * FROM effects WHERE strength='confirmed'")
        assert bool(writes) == confirmed
        if confirmed:
            assert writes[0]["basis"] == "codex_file_change"
            assert writes[0]["request"] is None
            assert "-gap=4" in change_outline(change_payloads(s, writes[0]))[0]["text"]
    finally:
        s.close()
