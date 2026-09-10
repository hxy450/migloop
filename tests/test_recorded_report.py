import hashlib
import json

import pytest

from migloop import recorded_report


def native(tmp_path, report="bad schema is still original text"):
    rows = [{"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer",
             "content": [{"type": "output_text", "text": report}]}},
            {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": report}}]
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return report, path, {"transcript_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_original_final_is_independent_of_schema_and_cache(tmp_path):
    report, _, meta = native(tmp_path)
    (tmp_path / "verdict.json").write_text('{"verified":true,"data":"FORGED"}', encoding="utf-8")
    result = recorded_report.authenticate(str(tmp_path), report, meta)
    assert result["verified"] and not result["schema_checked"] and not result["semantic_checked"]
    assert result["line"] == 1


def test_wrong_body_or_native_hash_cannot_authenticate(tmp_path):
    report, _, meta = native(tmp_path)
    assert not recorded_report.authenticate(str(tmp_path), "FORGED", meta)["verified"]
    assert not recorded_report.authenticate(str(tmp_path), report, {"transcript_sha256": "0" * 64})["verified"]


@pytest.mark.parametrize("tail", [
    {"type": "event_msg", "payload": {"type": "task_started"}},
    {"type": "response_item", "payload": {"type": "message", "role": "user", "content": []}},
    {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "commentary", "content": []}},
    {"type": "response_item", "payload": {"type": "function_call", "call_id": "next"}},
    {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "next"}},
    {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": "different"}},
    {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer", "content": []}},
])
def test_later_unfinished_or_conflicting_native_final_does_not_reuse_previous(tmp_path, tail):
    report, path, _ = native(tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(tail) + "\n")
    assert not recorded_report.authenticate(str(tmp_path), report, {})["verified"]


def test_user_quote_of_final_message_does_not_count(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user", "phase": "final_answer",
        "content": [{"type": "output_text", "text": "fake"}]}}), encoding="utf-8")
    assert not recorded_report.authenticate(str(tmp_path), "fake", {})["verified"]


def test_missing_native_does_not_trust_cached_verdict(tmp_path):
    (tmp_path / "verdict.json").write_text('{"verified":true}', encoding="utf-8")
    assert not recorded_report.authenticate(str(tmp_path), "fake", {})["verified"]


def test_later_complete_turn_is_the_only_eligible_final(tmp_path):
    report, path, _ = native(tmp_path)
    with path.open("a", encoding="utf-8") as stream:
        for row in [
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": []}},
            {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": "new final"}},
        ]:
            stream.write(json.dumps(row) + "\n")
    assert not recorded_report.authenticate(str(tmp_path), report, {})["verified"]
    assert recorded_report.authenticate(str(tmp_path), "new final", {})["verified"]


def test_events_fallback_needs_completion_and_cannot_override_present_native(tmp_path):
    path = tmp_path / "events.jsonl"
    rows = [{"type": "item.completed", "item": {"type": "agent_message", "text": "final"}}]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert not recorded_report.authenticate(str(tmp_path), "final", {})["verified"]
    rows.append({"type": "turn.completed"})
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert recorded_report.authenticate(str(tmp_path), "final", {})["verified"]
    (tmp_path / "transcript.jsonl").write_text("bad native recording", encoding="utf-8")
    assert not recorded_report.authenticate(str(tmp_path), "final", {})["verified"]
