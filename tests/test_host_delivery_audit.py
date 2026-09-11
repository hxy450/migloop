import importlib.util
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "docs/experiments/generalization-20260910/audit_host_delivery.py"
spec = importlib.util.spec_from_file_location("host_delivery_audit", path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def response(kind, **fields):
    return {"type": "response_item", "payload": {"type": kind, **fields}}


def runtime(**fields):
    return {"type": "event_msg", "payload": {"type": "item_completed", "item": {
        "type": "McpToolCall", "id": "exec-inner", "tool": "batch", "server": "migloop",
        "result": {"content": [{"type": "text", "text": "whole server result"}]}, **fields}}}


def test_nested_runtime_does_not_certify_truncated_model_output():
    report = audit.inspect([response("custom_tool_call", call_id="outer", name="exec"), runtime(),
        response("custom_tool_call_output", call_id="outer", output=[
            {"type": "input_text", "text": "Script completed\nOutput:\n"},
            {"type": "input_text", "text": "Warning: truncated output (original token count: 221603)\nhead…tail"}])])
    assert report["counts"]["explicit_truncated_outputs"] == 1
    assert report["runtime_calls"][0]["id_link_status"] == "unlinked"
    assert not report["runtime_calls"][0]["model_delivery_verified"]
    assert report["visible_outputs"][0]["direct_use_line"] == 1
    assert report["visible_outputs"][0]["reported_original_token_counts"] == [221603]


def test_explicit_id_is_not_by_itself_body_equivalence():
    report = audit.inspect([response("function_call", call_id="direct", name="mcp__migloop__batch"),
                            runtime(call_id="direct"), response("function_call_output", call_id="direct", output="not original")])
    assert report["runtime_calls"][0]["id_link_status"] == "unique_id_only"
    assert not report["runtime_calls"][0]["model_delivery_verified"]
    assert not report["visible_outputs"][0]["full_text_certified"]


def test_duplicate_ids_unrecognized_shape_and_missing_id_stay_unknown():
    report = audit.inspect([response("function_call", call_id="same"), response("function_call", call_id="same"),
        runtime(call_id="same"), response("function_call_output", call_id="same", output={"mystery": "text"}),
        response("function_call_output", output="no id"), None])
    assert report["runtime_calls"][0]["id_link_status"] == "ambiguous"
    assert report["counts"]["unknown_output_shapes"] == 1
    assert report["malformed_lines"] == [6]
    assert all(r["direct_use_line"] is None for r in report["visible_outputs"])
