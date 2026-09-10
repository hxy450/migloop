"""Reviewer tools authenticate evidence, not causal truth. No model calls."""
import importlib.util
import json
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / "docs/experiments/file-first-luna/review-v2/audit.py"
spec = importlib.util.spec_from_file_location("file_review_audit", MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def records(path, *values):
    path.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values), encoding="utf-8")


def item(kind, identity, **kwargs):
    return {"type": "response_item", "payload": {"type": kind, "call_id": identity, **kwargs}}


def test_witness_checks_exact_field_and_records_boundary(tmp_path):
    records(tmp_path / "a.jsonl", {"text": "real evidence", "other": "fake"})
    witness = audit.witness(audit.Originals(tmp_path), {"id": "x", "line": 1,
        "selector": ["text"], "contains": ["real"], "absent": ["fake"]}, "a.jsonl")
    assert witness["excerpts"] == [{"start_char": 0, "text": "real"}]
    assert witness["authentication"] == "literal_fields_only_not_causal_truth"


@pytest.mark.parametrize("line,path", [(0, "a.jsonl"), (2, "a.jsonl"), (1, "../a.jsonl")])
def test_original_location_fail_closed(tmp_path, line, path):
    records(tmp_path / "a.jsonl", {"text": "real"})
    with pytest.raises(ValueError):
        audit.Originals(tmp_path).record(path, line)


def test_original_hash_mismatch_rejected(tmp_path):
    records(tmp_path / "a.jsonl", {"text": "real"})
    with pytest.raises(ValueError, match="hash drift"):
        audit.Originals(tmp_path).record("a.jsonl", 1, "forged")


@pytest.mark.parametrize("contains,absent", [(["fake"], []), ([], ["real"])])
def test_false_witness_assertion_rejected(tmp_path, contains, absent):
    records(tmp_path / "a.jsonl", {"text": "real"})
    with pytest.raises(ValueError):
        audit.witness(audit.Originals(tmp_path), {"id": "x", "line": 1,
            "selector": ["text"], "contains": contains, "absent": absent}, "a.jsonl")


def test_native_delivery_excludes_command_aggregate_and_metadata(tmp_path):
    path = tmp_path / "trace.jsonl"
    records(path, item("custom_tool_call", "c", name="exec", input="historical code; never execute"),
            {"type": "event_msg", "payload": {"type": "item_completed", "item": {"aggregated_output": "SECRET not delivered"}}},
            item("custom_tool_call_output", "c", output=[{"type": "input_text", "text": "visible", "meta": "not delivered"}]))
    calls = audit.native_calls(path)["calls"]
    assert calls[0]["text"] == "visible"
    assert calls[0]["result_line"] == 3
    assert calls[0]["visible_chars"] == 7


@pytest.mark.parametrize("duplicate", ["input", "output"])
def test_ambiguous_pairs_not_accepted(tmp_path, duplicate):
    path = tmp_path / "trace.jsonl"
    request = item("custom_tool_call", "c", name="exec", input="request")
    response = item("custom_tool_call_output", "c", output="result")
    records(path, request, response, request if duplicate == "input" else response)
    call = audit.native_calls(path)["calls"][0]
    assert call["pairing"] != "unique" and call["text"] is None


def test_output_cannot_pair_by_proximity_or_before_request(tmp_path):
    path = tmp_path / "trace.jsonl"
    records(path, item("custom_tool_call_output", "c", output="too early"),
            item("custom_tool_call", "c", name="exec", input="request"),
            item("custom_tool_call_output", "different", output="unrelated"))
    data = audit.native_calls(path)
    assert data["calls"][0]["text"] is None
    assert data["orphan_output_ids"] == ["different"]


def test_probe_does_not_call_query_echo_delivered_evidence(tmp_path):
    path = tmp_path / "trace.jsonl"
    records(path, item("custom_tool_call", "c", name="exec", input="search AC14"),
            item("custom_tool_call_output", "c", output="no match"))
    found = audit.probes(audit.native_calls(path)["calls"], [{"id": "x", "needles": ["AC14"]}])
    assert [o["field"] for o in found[0]["occurrences"]] == ["input"]
    assert "Miss is not proof" in found[0]["interpretation"]


def test_escaped_text_and_missing_text_are_not_semantic_judgments():
    assert audit.locate(json.dumps("x\ny"), "x\ny")["encoding_depth"] == 1
    assert audit.locate(None, "x") is None


def test_no_overwrite(tmp_path):
    path = tmp_path / "report.json"
    audit.write_new(path, {"original": True})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        audit.write_new(path, {"original": False})
    assert path.read_bytes() == before
