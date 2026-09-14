"""The review auditor checks what reached the new turn, not old context."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

DRIVER = Path(__file__).parents[1] / "docs/experiments/inquiry-20260911/audit_paired_review.py"
spec = importlib.util.spec_from_file_location("paired_delivery_test", DRIVER)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


@pytest.mark.parametrize("arm", ["raw", "inquiry"])
def test_review_audit_excludes_original_turn_and_authenticates_new_final(tmp_path, arm):
    branch = tmp_path / "F10-test" / arm
    run = branch / "rep1"
    run.mkdir(parents=True)
    (branch / "prompt.md").write_text("review prompt", encoding="utf-8")
    (run / "report.md").write_text("review result", encoding="utf-8")
    frame_id = "1234567890abcdef"
    body = "原始调用 content"
    frame = f"RESULT {frame_id} chars={len(body)} range=0:{len(body)}\n{body}\nEND FRAME next=none"
    native = [
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "old", "output": "Warning: truncated output"}},
        {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"text": "review prompt"}]}},
        {"type": "response_item", "payload": {"type": "function_call", "call_id": "new", "name": "mcp__inquiry__investigate", "arguments": "{}"}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "new", "output": frame if arm == "inquiry" else "raw command output"}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer", "content": [{"text": "review result"}]}},
    ]
    (run / "transcript.jsonl").write_text("\n".join(json.dumps(row) for row in native), encoding="utf-8")
    with sqlite3.connect(tmp_path / "F10-test/index.sqlite") as db:
        db.execute("CREATE TABLE frames (run TEXT, offset INTEGER, text TEXT)")
        db.execute("CREATE TABLE runs (id TEXT, kind TEXT, body TEXT, data TEXT)")
        db.execute("INSERT INTO frames VALUES (?,0,?)", (frame_id, frame))
        data = [{"query": {"op": "open"}, "ok": True, "data": {}}]
        db.execute("INSERT INTO runs VALUES (?,'query',?,?)", (frame_id, body, json.dumps(data)))
    audit_module.audit(tmp_path, "F10-test", arm)
    result = json.loads((run / "review-delivery.json").read_text(encoding="utf-8"))
    assert result["host_truncations"] == 0
    assert result["final_authenticated"]
    assert result["frames_visible"] == (1 if arm == "inquiry" else 0)
    assert result["query_stats"]["query_succeeded"] == (1 if arm == "inquiry" else 0)
    with pytest.raises(FileExistsError):
        audit_module.audit(tmp_path, "F10-test", arm)


@pytest.mark.parametrize("wrong", [None, "id", "parent", "ordinal", "bytes"])
def test_native_reference_requires_exact_parent_and_both_boundaries(wrong):
    parent = [{"type": "response_item", "ordinal": 7, "payload": {"type": "message", "role": "assistant"}}]
    meta = {"id": "child", "forked_from_id": "parent", "forked_from_ordinal_exclusive": 8,
            "history_mode": "paginated", "history_base": {
                "thread_id": "parent", "end_ordinal_exclusive": 8, "end_byte_offset": 900}}
    if wrong == "id":
        meta["id"] = "parent"
    elif wrong == "parent":
        meta["history_base"]["thread_id"] = "other"
    elif wrong == "ordinal":
        meta["history_base"]["end_ordinal_exclusive"] = 7
    elif wrong == "bytes":
        meta["history_base"]["end_byte_offset"] = 899
    result = audit_module.history_binding(parent, [{"type": "session_meta", "payload": meta}], "parent", 900)
    assert result["native_history_binding_confirmed"] == (wrong is None)
