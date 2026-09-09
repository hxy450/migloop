"""Adversarial binding checks use only synthetic, local tool transcripts."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from migloop import atoms, draft_check, probe, verdict
from tests.test_draft_check import data, recorded
from tests.test_repair_coverage import PATH, candidate_action, splash_ledger
from tests.test_trajectory import _run_dir
from tests.test_verdict import _pool


def _saved_run(tmp_path, ledger, checked, displayed, *, raw=None, harness=None, calls=None):
    body = json.dumps(checked, ensure_ascii=False)
    transcript = [
        ("sessions", {"sid": "synthetic"}, "账本身份: " + atoms.ledger_identity(ledger)),
        ("check", {"sid": "synthetic", "draft": body}, draft_check.render(ledger, body)),
    ]
    run = _run_dir(tmp_path, calls or transcript,
                   "```json\n" + json.dumps(checked, ensure_ascii=False) + "\n```")
    saved = {"kind": "json", "data": displayed, "raw": raw, "errors": [],
             "found": True, "harness_identity": harness or atoms.ledger_identity(ledger)}
    (Path(run) / "verdict.json").write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    return run


def test_valid_legacy_alternate_source_remains_separate_from_actual_draft_binding(tmp_path):
    ledger = _pool(tmp_path)
    checked = data(ledger)
    displayed = deepcopy(checked)
    displayed["defects"][0]["nodes"][0]["reason"] = "New assertion not submitted to check"
    raw = json.dumps(displayed)
    run = _saved_run(tmp_path, ledger, checked, displayed, raw=raw)
    payload = probe.probe_payload(ledger, run)
    assert payload["trace_identity"]["bound"] is True
    assert payload["structured"]["defects"][0]["nodes"][0]["reason"] == displayed["defects"][0]["nodes"][0]["reason"]
    assert payload["structured"]["document_source"]["kind"] == "legacy_saved"
    assert payload["structured"]["document_source"]["verified"] is False
    assert payload["structured"]["document_source"]["raw_matches_data"] is True
    assert payload["structured"]["submission"]["status"] == "legacy_unverified"
    assert payload["draft_check"]["checks"][0]["verified"] is True
    assert payload["draft_check"]["status"] == "mismatch"
    assert payload["draft_check"]["final_document_sha256"] == draft_check.document_hash(displayed)


def test_unchecked_cached_interpretation_cannot_override_matching_raw_and_final(tmp_path):
    ledger = _pool(tmp_path)
    checked = data(ledger)
    displayed = deepcopy(checked)
    displayed["defects"][0]["nodes"][0]["reason"] = "Unbacked saved assertion"
    raw = json.dumps(checked)
    run = _saved_run(tmp_path, ledger, checked, displayed, raw=raw)
    payload = probe.probe_payload(ledger, run)
    assert payload["trace_identity"]["bound"] is True
    assert payload["structured"]["errors"] and not payload["roles"]
    assert not payload["structured"]["defects"] and payload["structured"]["raw"] == raw
    assert payload["structured"]["document_source"]["raw_matches_data"] is False
    assert payload["draft_check"]["status"] == "invalid_final"
    assert payload["draft_check"]["final_document_sha256"] is None


@pytest.mark.parametrize("raw_kind", ["different", "invalid"])
def test_valid_checked_data_cannot_authenticate_conflicting_or_invalid_saved_raw(tmp_path, raw_kind):
    ledger = _pool(tmp_path)
    checked = data(ledger)
    other = deepcopy(checked)
    other["notes"] = "An older raw block is not the displayed document."
    raw = {"different": json.dumps(other), "invalid": "{broken"}[raw_kind]
    run = _saved_run(tmp_path, ledger, checked, checked, raw=raw)
    payload = probe.probe_payload(ledger, run)
    assert payload["structured"]["errors"] and not payload["roles"]
    assert not payload["structured"]["defects"]
    assert payload["structured"]["document_source"]["kind"] == "invalid_saved"
    assert payload["structured"]["document_source"]["verified"] is False
    assert payload["draft_check"]["status"] == "invalid_final"
    assert payload["draft_check"]["matched_check"] is None
    assert payload["draft_check"]["semantic_checked"] is False
    assert payload["structured"]["raw"] == raw  # No repair or rewriting of saved artifacts.


def test_missing_cached_raw_uses_matching_actual_final_without_writing_artifacts(tmp_path):
    ledger = _pool(tmp_path)
    checked = data(ledger)
    run = Path(_saved_run(tmp_path, ledger, checked, checked, raw=None))
    before = {path.name: path.read_bytes() for path in run.iterdir() if path.is_file()}
    final = json.loads(before["result.json"])["result"]
    original = verdict.load_block(final)["raw"]
    payload = probe.probe_payload(ledger, str(run))
    assert not payload["structured"]["errors"]
    assert payload["structured"]["raw"] == original
    assert payload["structured"]["document_source"]["kind"] == "final_inline"
    assert payload["structured"]["document_source"]["verified"] is True
    assert payload["structured"]["document_source"]["semantic_checked"] is False
    assert payload["draft_check"]["status"] == "matched"
    assert payload["draft_check"]["checks"][0]["verified"] is True
    assert {path.name: path.read_bytes() for path in run.iterdir() if path.is_file()} == before


def test_saved_harness_identity_conflict_cannot_bind_a_displayed_document(tmp_path):
    ledger = _pool(tmp_path)
    checked = data(ledger)
    run = _saved_run(tmp_path, ledger, checked, checked, raw=json.dumps(checked), harness="different-ledger")
    payload = probe.probe_payload(ledger, run)
    assert payload["trace_identity"]["bound"] is True
    assert payload["structured"]["identity"]["bound"] is False
    assert payload["draft_check"]["status"] != "matched"
    assert payload["draft_check"]["matched_check"] is None


def test_schema_invalid_displayed_data_cannot_reuse_a_valid_raw_check(tmp_path):
    ledger = _pool(tmp_path)
    checked = data(ledger)
    invalid = deepcopy(checked)
    invalid["model_checked"] = True
    run = _saved_run(tmp_path, ledger, checked, invalid, raw=json.dumps(checked))
    payload = probe.probe_payload(ledger, run)
    assert payload["structured"]["errors"]
    assert payload["draft_check"]["status"] == "invalid_final"


def test_omitting_coverage_cannot_clear_a_supplied_repair_denominator():
    ledger, chains = splash_ledger()
    doc = {"schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger),
           "root": f"file:{PATH}@v54", "defects": []}
    assert verdict.validate(doc) == []  # Legacy schema still accepts missing coverage.
    result = draft_check.evaluate(ledger, json.dumps(doc), {"chains": chains}, PATH)
    assert result["status"] == "needs_review"
    assert result["coverage"]["checked"] is True
    assert result["coverage"]["counts"]["expected_versions"] == 3
    assert result["coverage"]["counts"]["missing_versions"] == 3
    assert any(issue["code"] == "coverage_incomplete" for issue in result["issues"])
    assert "coverage" not in doc


def test_missing_coverage_keeps_unconfirmed_execution_candidates_too():
    ledger, chains = splash_ledger()
    candidate_action(ledger, 100, touch=True)
    doc = {"schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger),
           "root": f"file:{PATH}@v54", "defects": []}
    result = draft_check.evaluate(ledger, json.dumps(doc), {"chains": chains}, PATH)
    counts = result["coverage"]["counts"]
    assert counts["expected_versions"] == counts["missing_versions"] == 3
    assert counts["expected_candidates"] == counts["missing_candidates"] == 1
    assert result["status"] == "needs_review" and result["semantic_checked"] is False


def test_supplied_pool_but_no_target_discloses_unchecked_coverage(tmp_path):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    doc["root"] = "agent:agent-c@v1"
    result = draft_check.evaluate(ledger, json.dumps(doc), {"chains": []})
    assert result["status"] == "needs_review"
    assert result["coverage"]["checked"] is False
    assert any(issue["code"] == "coverage_scope_unknown" for issue in result["issues"])


@pytest.mark.parametrize("last_result", [None, "not valid JSON"])
def test_later_incomplete_check_never_falls_back_to_an_earlier_match(tmp_path, last_result):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    body = json.dumps(doc)
    calls = [
        ("sessions", {}, "账本身份: " + atoms.ledger_identity(ledger)),
        ("check", {"draft": body}, draft_check.render(ledger, body)),
        ("check", {"draft": body}, last_result),
    ]
    run = _saved_run(tmp_path, ledger, doc, doc, raw=body, calls=calls)
    result = probe.probe_payload(ledger, run)["draft_check"]
    assert result["check_calls"] == 2
    assert result["checks"][0]["verified"] is True
    assert result["checks"][1]["verified"] is False
    assert result["status"] == "unverifiable" and result["matched_check"] is None


def test_hash_only_result_copied_into_unqualified_tool_is_not_provenance(tmp_path):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    run = _saved_run(tmp_path, ledger, doc, doc, raw=json.dumps(doc))
    path = Path(run) / "transcript.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace("mcp__migloop__check", "check"), encoding="utf-8")
    result = probe.probe_payload(ledger, run)["draft_check"]
    assert result["status"] == "unverifiable" and result["checks"][0]["verified"] is False


@pytest.mark.parametrize("format", ["codex_direct", "codex_runtime"])
def test_native_codex_pair_or_timed_leaf_can_bind_without_inventing_call_ids(tmp_path, format):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    body = json.dumps(doc)
    run = _saved_run(tmp_path, ledger, doc, doc, raw=body)
    path = Path(run) / "transcript.jsonl"
    # Keep the genuine paired identity event, replace only the check records.
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[:2]]
    output = draft_check.render(ledger, body)
    if format == "codex_direct":
        rows += [
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "native-check",
                "name": "mcp__migloop__check", "arguments": json.dumps({"draft": body})}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "native-check", "output": output}},
        ]
    else:
        rows.append({"type": "event_msg", "payload": {"type": "item_completed", "started_at_ms": 100,
            "completed_at_ms": 200, "item": {"type": "McpToolCall", "id": "exec-native-check", "server": "migloop",
                "tool": "check", "arguments": {"draft": body}, "status": "completed",
                "result": {"content": [{"type": "text", "text": output}]}}}})
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    calls = probe._transcript_calls(run)
    if format == "codex_runtime":
        assert calls[-1]["call_id"] is None
        assert calls[-1]["item_id"] == "exec-native-check"
    result = probe.probe_payload(ledger, run)["draft_check"]
    assert result["status"] == "matched" and result["checks"][0]["verified"] is True


def test_matched_warning_does_not_turn_into_a_clear_or_semantic_approval(tmp_path):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    doc["defects"][0]["nodes"][0]["role"] = "进入·错"
    call = recorded(ledger, json.dumps(doc))
    result = draft_check.final_binding(ledger, [call], doc, identity_bound=True)
    assert result["status"] == "matched"
    assert result["checks"][0]["status"] == "needs_review"
    assert result["checks"][0]["counts"]["warnings"] >= 1
    assert result["semantic_checked"] is False
