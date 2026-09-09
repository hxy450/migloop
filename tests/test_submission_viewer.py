import asyncio
import json

import pytest

from migloop import atoms, findings, mcp_server, probe, service, verdict
from tests.test_draft_check import data, recorded
from tests.test_submission import reference, trace
from tests.test_submission import pair
from tests.test_verdict import _pool, _run_dir


def test_viewer_reauthenticates_reference_instead_of_trusting_saved_document(tmp_path):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    draft = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    report = reference(ledger, draft, doc)
    saved = {"data": {**doc, "notes": "tampered saved interpretation"}, "errors": [], "found": True,
             "kind": "json", "raw": "tampered", "harness_identity": atoms.ledger_identity(ledger),
             "submission": {"mode": "checked_draft_ref"}}
    run = _run_dir(tmp_path, [], report, saved)
    got = probe._structured(ledger, run, report, trace(ledger), [recorded(ledger, draft)])
    assert got["errors"] == [] and got["raw"] == draft
    assert got["notes"] != "tampered saved interpretation"
    assert got["submission"]["status"] == "accepted"
    direct = verdict.build(ledger, doc, [], {"kind": "json", "raw": draft, "trace_identity": trace(ledger),
                                            "harness_identity": atoms.ledger_identity(ledger)})
    resolved, inline = findings.project(got), findings.project(direct)
    assert resolved.pop("document_source")["verified"] is True
    inline.pop("document_source")
    assert resolved == inline


@pytest.mark.parametrize("failure", ["no_trace", "truncated", "changed_final"])
def test_saved_reference_cannot_hide_a_broken_authentication_chain(tmp_path, failure):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    draft = json.dumps(doc)
    report = reference(ledger, draft, doc)
    saved = {"data": doc, "errors": [], "found": True, "kind": "json", "raw": draft,
             "harness_identity": atoms.ledger_identity(ledger), "submission": {"mode": "checked_draft_ref"}}
    run = _run_dir(tmp_path, [], report, saved)
    calls = [recorded(ledger, draft)]
    if failure == "no_trace": calls = []
    if failure == "truncated": calls[0]["delivery_truncated"] = True
    if failure == "changed_final": report = "final response without explicit ref"
    got = probe._structured(ledger, run, report, trace(ledger), calls)
    assert got["errors"] and not got["defects"] and not got["document_sha256"]
    assert findings.project(got)["items"] == {}


def test_final_mode_is_explicit_and_keeps_the_full_reference_available(monkeypatch):
    assert mcp_server.guide_text("document", topic="full") == mcp_server.GUIDE
    assert mcp_server.guide_text("reference", topic="full").startswith(mcp_server.GUIDE)
    with pytest.raises(ValueError): mcp_server.guide_text("typo")
    monkeypatch.setenv("MIGLOOP_FINAL_MODE", "reference")
    expected = mcp_server.guide_text()
    assert "migloop-verdict-ref/1" in expected
    assert service.atom_text("unused", "guide", {}) == expected
    pytest.importorskip("mcp")
    blocks = asyncio.run(mcp_server.build_server().call_tool("guide", {}))
    assert blocks[0].text == expected


def test_archived_findings_are_a_separate_lossless_projection(tmp_path):
    raw = "schema: migloop-verdict/1\nnotes: unchanged\n"
    projection = {"schema": findings.SCHEMA, "items": {}, "audit": {"semantic_checked": False}}
    got = pair.write_submission_artifacts(tmp_path, {
        "kind": "yaml", "raw": raw, "data": {"schema": verdict.SCHEMA}, "errors": [],
        "submission": {"status": "accepted", "mode": "inline"}, "findings": projection})
    assert got["document_artifact"] == "verdict.yaml" and got["findings_artifact"] == "findings.json"
    assert (tmp_path / "verdict.yaml").read_bytes() == raw.encode("utf-8")
    assert json.loads((tmp_path / "findings.json").read_text(encoding="utf-8")) == projection
    with pytest.raises(FileExistsError):
        pair.write_submission_artifacts(tmp_path, {"submission": {"status": "rejected"}})
