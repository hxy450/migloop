"""Readable protocol envelopes must not turn quoted commands into facts."""

import json

from migloop.inquiry.engine import content_text
from tests.test_inquiry_core import build, record, ts


def codex_output(value):
    return {
        "timestamp": ts(1),
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "call_id": "outer",
            "output": value,
        },
    }


def test_nested_codex_tool_output_is_readable_without_losing_receipt_metadata():
    receipt = {
        "chunk_id": "c",
        "exit_code": 0,
        "output": "line one\nBUILD SUCCESSFUL\ninstalled",
        "session_id": 71,
    }
    blocks = [
        {"type": "input_text", "text": "Script completed"},
        {"type": "input_text", "text": json.dumps(receipt)},
    ]
    projected = content_text(json.dumps(codex_output(json.dumps(blocks))))
    assert "line one\nBUILD SUCCESSFUL\ninstalled" in projected
    assert "exit_code: 0" in projected and "session_id: 71" in projected
    assert "chunk_id: c" in projected and "Script completed" in projected


def test_codex_request_decodes_arguments_not_program_text():
    command = "python -c \"print({'output': 'literal'})\"\nnext command"
    raw = {
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "exec_command",
            "arguments": json.dumps({"cmd": command, "workdir": "/workspace"}),
        },
    }
    projected = content_text(json.dumps(raw))
    assert command in projected
    assert "workdir: /workspace" in projected


def test_nested_projection_keeps_unknown_blocks_and_never_indexes_quoted_writes(
    tmp_path,
):
    quoted = {
        "type": "tool_use",
        "id": "fake",
        "name": "Write",
        "input": {"file_path": "A.ets", "content": "invented"},
    }
    body = [
        {"type": "input_text", "text": json.dumps(quoted)},
        {"type": "input_image", "image_url": "literal-image-data"},
    ]
    engine = build(tmp_path, [codex_output(body)])
    ref = engine.store.locate("a.jsonl", 1)
    projected = engine.query({"op": "open", "ref": ref, "at": ts(2)})
    assert "literal-image-data" in projected["text"]
    assert "invented" in projected["text"]
    assert engine.store.rows("SELECT * FROM effects") == []
    assert engine.store.rows("SELECT * FROM calls") == []
    raw = engine.query({"op": "open", "ref": ref, "at": ts(2), "pointer": ""})
    assert json.loads(raw["text"]) == codex_output(body)
    engine.store.close()


def test_arbitrary_json_source_strings_are_not_unwrapped():
    literal = '{"output":"not a protocol envelope","kind":"user-data"}'
    assert literal in content_text(
        json.dumps(record(1, {"type": "text", "text": literal}))
    )
    assert content_text(json.dumps(codex_output(literal))) == literal


def test_nested_window_selects_actual_output_lines_and_preserves_raw_source(tmp_path):
    body = json.dumps(
        [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "exit_code": 0,
                        "output": "unrelated one\nneedle\nunrelated two",
                    }
                ),
            },
        ]
    )
    engine = build(tmp_path, [codex_output(body)])
    ref = engine.store.locate("a.jsonl", 1)
    projected = engine.query(
        {
            "op": "open",
            "ref": ref,
            "at": ts(2),
            "terms": ["needle"],
            "context": 0,
        }
    )
    assert "needle" in projected["text"] and "unrelated one" not in projected["text"]
    assert "unrelated two" not in projected["text"]
    assert projected["original_content_lines"] > 3
    assert engine.store.source_record(ref)[0]["ref"] == ref
    engine.store.close()
