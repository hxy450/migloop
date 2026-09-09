"""A cached interpretation cannot override or manufacture its author document."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from migloop import atoms, probe, verdict
from tests.test_draft_check import data
from tests.test_submission import trace
from tests.test_verdict import _pool, _run_dir


def setup(tmp_path, *, final=True, saved_raw=True, mode=None, repaired=False):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    doc["defects"][0]["nodes"][0]["reason"] = "ORIGINAL_REASON"
    raw = json.dumps(doc, ensure_ascii=False, indent=2)
    saved = {"data": deepcopy(doc), "errors": [], "found": True, "kind": "json",
             "harness_identity": atoms.ledger_identity(ledger), "repaired": repaired}
    if saved_raw:
        saved["raw"] = raw
    if mode:
        saved["submission"] = {"mode": mode, "status": "accepted"}
    report = "```json\n" + raw + "\n```" if final else "No structured final document"
    return ledger, doc, saved, report


def build(tmp_path, ledger, saved, report):
    run = _run_dir(tmp_path, [], report, saved)
    before = Path(run, "verdict.json").read_bytes()
    got = probe._structured(ledger, run, report, trace(ledger), [])
    assert Path(run, "verdict.json").read_bytes() == before
    return got


@pytest.mark.parametrize("mode", [None, "inline"])
def test_raw_data_disagreement_never_labels_saved_reason_as_model_original(tmp_path, mode):
    ledger, doc, saved, report = setup(tmp_path, mode=mode)
    saved["data"]["defects"][0]["nodes"][0]["reason"] = "SAVED_ONLY_REASON"
    got = build(tmp_path, ledger, saved, report)
    assert got["errors"] and not got["roles"] and not got["defects"]
    assert got["raw"] == saved["raw"] and "ORIGINAL_REASON" in got["raw"]
    assert got["document_source"]["kind"] == "invalid_saved"
    assert got["document_source"]["raw_matches_data"] is False
    assert not got["document_sha256"] and got["submission"]["status"] != "accepted"


@pytest.mark.parametrize("raw", ["{}", "invalid: [", "", 27])
def test_invalid_saved_raw_cannot_hide_behind_valid_data_or_final(tmp_path, raw):
    ledger, doc, saved, report = setup(tmp_path)
    saved["raw"] = raw
    got = build(tmp_path, ledger, saved, report)
    assert got["errors"] and not got["roles"] and not got["fixed"]
    assert got["raw"] == raw and not got["document_source"]["verified"]


@pytest.mark.parametrize("saved_raw", [True, False])
def test_matching_inline_uses_original_final_text_and_records_content_identity(tmp_path, saved_raw):
    ledger, doc, saved, report = setup(tmp_path, saved_raw=saved_raw, mode="inline")
    # Canonical identity, not presentation whitespace, links cache and final.
    report = "```json\n" + json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n```"
    got = build(tmp_path, ledger, saved, report)
    assert got["errors"] == [] and got["raw"] == verdict.load_block(report)["raw"]
    assert got["document_source"]["kind"] == "final_inline"
    assert got["document_source"]["verified"] is True
    assert got["document_source"]["semantic_checked"] is False
    assert got["submission"]["mode"] == "inline" and got["submission"]["status"] == "accepted"


@pytest.mark.parametrize("final", [True, False])
@pytest.mark.parametrize("repaired", [True, False])
def test_legacy_consistent_document_stays_readable_but_not_final_authenticated(tmp_path, final, repaired):
    ledger, doc, saved, report = setup(tmp_path, final=final, repaired=repaired)
    saved["data"]["notes"] = "legacy interpretation with original saved body"
    saved["raw"] = json.dumps(saved["data"])
    got = build(tmp_path, ledger, saved, report)
    assert got["errors"] == [] and got["raw"] == saved["raw"] and got["roles"]
    assert got["document_source"]["kind"] == ("saved_schema_repair" if repaired else "legacy_saved")
    assert got["document_source"]["verified"] is False
    assert got["document_source"]["raw_matches_data"] is True
    assert got["submission"]["mode"] == "saved_document" and got["submission"]["status"] == "legacy_unverified"


@pytest.mark.parametrize("final", [True, False])
def test_new_inline_submission_must_match_final_even_when_saved_body_is_consistent(tmp_path, final):
    ledger, doc, saved, report = setup(tmp_path, final=final, mode="inline", repaired=True)
    saved["data"]["notes"] = "another document"
    saved["raw"] = json.dumps(saved["data"])
    got = build(tmp_path, ledger, saved, report)
    assert got["errors"] and not got["roles"] and not got["document_sha256"]
    assert got["document_source"]["kind"] == "invalid_saved"


@pytest.mark.parametrize("final", [True, False])
def test_data_without_any_matching_original_cannot_create_claims(tmp_path, final):
    ledger, doc, saved, report = setup(tmp_path, final=final, saved_raw=False)
    saved["data"]["notes"] = "unbacked saved data"
    got = build(tmp_path, ledger, saved, report)
    assert got["errors"] and not got["roles"] and not got["document_source"]["verified"]


def test_legacy_notes_revalidation_keeps_warning_and_saved_source(tmp_path):
    ledger, doc, saved, report = setup(tmp_path, final=False)
    doc["notes"] = ["one", "two"]
    saved.update(data=None, raw=json.dumps(doc), errors=["notes previously rejected"])
    got = build(tmp_path, ledger, saved, report)
    assert got["errors"] == [] and got["revalidated"]
    assert got["previous_errors"] == saved["errors"] and got["notes"] == "one\n\ntwo"
    assert got["document_source"]["kind"] == "legacy_saved"
    assert got["submission"]["status"] == "legacy_unverified"
