"""Reference infrastructure tests, not tests that certify causal conclusions."""
import importlib.util
import json
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "docs/experiments/file-first-10/audit_reference.py"
spec = importlib.util.spec_from_file_location("file_first_10_audit_tests", SOURCE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def cc_use(identity="a", **arguments):
    return {"timestamp": "2026-01-01T10:00:01Z", "message": {"content": [
        {"type": "tool_use", "id": identity, "name": "Edit", "input": arguments}]}}


def cc_result(identity="a", error=False):
    return {"timestamp": "2026-01-01T10:00:02Z", "message": {"content": [
        {"type": "tool_result", "tool_use_id": identity, "is_error": error, "content": "ok"}]}}


def save(tmp_path, name, *rows):
    path = tmp_path / name
    path.write_bytes(b"\n".join(json.dumps(row).encode("utf-8") for row in rows) + b"\n")
    return path


def collect(tmp_path, target="entry/Target.ets"):
    return audit.inventory(audit.Pool(tmp_path).calls(), target, "2026-01-01T10:00:00Z", "2026-01-01T10:00:03Z")


def test_native_change_requires_path_and_receipt(tmp_path):
    save(tmp_path, "a.jsonl", cc_use(file_path="/project/entry/Target.ets"), cc_result())
    assert collect(tmp_path)["native_target_calls"][0]["confirmed_post_boundary_tool_receipt"]


def test_report_not_target_and_same_basename_not_same_path(tmp_path):
    save(tmp_path, "a.jsonl", cc_use(file_path="/elsewhere/Target.ets", new_string="entry/Target.ets was fixed"), cc_result())
    result = collect(tmp_path)
    assert not result["native_target_calls"]
    assert len(result["other_related_calls"]) == 1


@pytest.mark.parametrize("variant", ["duplicate_result", "duplicate_use", "wrong_source", "failed", "future", "missing", "before_use"])
def test_uncertain_change_does_not_qualify(tmp_path, variant):
    use, output = cc_use(file_path="entry/Target.ets"), cc_result()
    records = [use, output]
    if variant == "duplicate_result":
        records.append(output)
    elif variant == "duplicate_use":
        records.insert(0, use)
    elif variant == "wrong_source":
        save(tmp_path, "b.jsonl", output)
        records = [use]
    elif variant == "failed":
        records[-1] = cc_result(error=True)
    elif variant == "future":
        output["timestamp"] = "2026-01-01T10:00:04Z"
    elif variant == "missing":
        records = [use]
    elif variant == "before_use":
        records.reverse()
    save(tmp_path, "a.jsonl", *records)
    assert not collect(tmp_path)["native_target_calls"][0]["confirmed_post_boundary_tool_receipt"]


def test_time_offsets_compared_as_instants(tmp_path):
    use, output = cc_use(file_path="entry/Target.ets"), cc_result()
    use["timestamp"] = "2026-01-01T05:00:01-05:00"
    save(tmp_path, "a.jsonl", use, output)
    assert collect(tmp_path)["native_target_calls"][0]["confirmed_post_boundary_tool_receipt"]


def test_missing_timestamp_quarantined_and_opaque_calls_preserved(tmp_path):
    use = cc_use(file_path="entry/Target.ets")
    use.pop("timestamp")
    opaque = cc_use("b", arbitrary="run_the_unknown_script")
    opaque["message"]["content"][0]["name"] = "NeverHeardOfThisTool"
    save(tmp_path, "a.jsonl", use, cc_result(), opaque, cc_result("b"))
    result = collect(tmp_path)
    assert result["unknown_time_records"]
    assert len(result["other_calls_for_effect_review"]) == 1
    assert not result["native_target_calls"][0]["confirmed_post_boundary_tool_receipt"]


def test_codex_patch_receipt_not_commentary(tmp_path):
    patch = "*** Begin Patch\n*** Update File: /project/entry/Target.ets\n@@\n-old\n+new\n*** End Patch"
    use = {"timestamp": "2026-01-01T10:00:01Z", "type": "response_item", "payload": {
        "type": "custom_tool_call", "call_id": "c", "name": "apply_patch", "input": patch}}
    result = {"timestamp": "2026-01-01T10:00:02Z", "type": "response_item", "payload": {
        "type": "custom_tool_call_output", "call_id": "c", "output": "Success. Updated the following files:\nM /project/entry/Target.ets"}}
    save(tmp_path, "a.jsonl", use, result)
    assert collect(tmp_path)["native_target_calls"][0]["confirmed_post_boundary_tool_receipt"]


def test_inner_codex_patch_does_not_invent_outer_call_pair(tmp_path):
    row = {"timestamp": "2026-01-01T10:00:02Z", "type": "event_msg", "payload": {
        "type": "patch_apply_end", "call_id": "exec-inner-id", "success": True,
        "changes": {"/project/entry/Target.ets": {"type": "update", "unified_diff": "-old\n+new"}}}}
    save(tmp_path, "a.jsonl", row)
    data = collect(tmp_path)
    assert not data["native_target_calls"]
    effect = data["recorded_patch_effects"][0]
    assert effect["confirmed_post_boundary_effect_receipt"]
    assert effect["outer_call_id"] is None
    assert effect["effect_id"] == "exec-inner-id"


def test_claude_missing_error_flag_requires_native_success_receipt(tmp_path):
    result = cc_result()
    item = result["message"]["content"][0]
    item.pop("is_error")
    item["content"] = "The file /project/entry/Target.ets has been updated successfully."
    save(tmp_path, "a.jsonl", cc_use(file_path="entry/Target.ets"), result)
    assert collect(tmp_path)["native_target_calls"][0]["confirmed_post_boundary_tool_receipt"]
    item["content"] = "I think I fixed it."
    save(tmp_path, "a.jsonl", cc_use(file_path="entry/Target.ets"), result)
    assert not collect(tmp_path)["native_target_calls"][0]["confirmed_post_boundary_tool_receipt"]


@pytest.mark.parametrize("line", [0, -1, True, 3])
def test_witness_rejects_bad_line(tmp_path, line):
    save(tmp_path, "a.jsonl", {"text": "literal"})
    with pytest.raises(ValueError):
        audit.Pool(tmp_path).record({"source": "a.jsonl", "line": line})


def test_witness_rejects_forged_quote_and_hash(tmp_path):
    source = save(tmp_path, "a.jsonl", {"text": "real value"})
    pool = audit.Pool(tmp_path)
    w = {"source": "a.jsonl", "line": 1, "selector": ["text"], "contains": ["invented"]}
    with pytest.raises(ValueError, match="literal"):
        pool.witness(w)
    with pytest.raises(ValueError, match="drifted"):
        pool.witness({**w, "sha256": "forged"})
    before = source.read_bytes()
    verified = pool.witness({**w, "contains": ["real"]})
    assert verified["verified"] == "location_and_literal_only_not_semantic_support"
    assert source.read_bytes() == before


def test_witness_rejects_path_escape(tmp_path):
    save(tmp_path, "a.jsonl", {"text": "outside"})
    child = tmp_path / "child"
    child.mkdir()
    with pytest.raises(ValueError, match="escapes"):
        audit.Pool(child).record({"source": "../a.jsonl", "line": 1})


def test_malformed_json_fails_instead_of_silent_coverage(tmp_path):
    (tmp_path / "a.jsonl").write_text("{incomplete\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        audit.Pool(tmp_path).calls()
