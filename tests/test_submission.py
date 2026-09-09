"""Checked-draft submissions are local, explicit, and fail closed."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from migloop import atoms, draft_check, submission, verdict
from tests.test_draft_check import data, recorded
from tests.test_verdict import _pool


RUNNER = Path(__file__).parents[1] / "docs/experiments/2026-09-09-fidelity-cost/run_pair.py"
spec = importlib.util.spec_from_file_location("submission_pair_harness", RUNNER)
assert spec and spec.loader
pair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pair)


def trace(ledger, **changes):
    identity = atoms.ledger_identity(ledger)
    row = {"current": identity, "bound": True, "match": True,
           "source_identities": [identity], "harness_identity": identity}
    row.update(changes)
    return row


def reference(ledger_obj, draft, document=None, **changes):
    document = document if document is not None else json.loads(draft)
    row = {"schema": submission.SCHEMA, "ledger": atoms.ledger_identity(ledger_obj),
           "draft_sha256": hashlib.sha256(draft.encode("utf-8")).hexdigest(),
           "document_sha256": draft_check.document_hash(document)}
    row.update(changes)
    return "```json\n" + json.dumps(row, ensure_ascii=False) + "\n```"


def accepted(tmp_path, *, doc=None, draft=None, calls=None, report=None, trace_identity=None,
             harness_identity=None):
    ledger = _pool(tmp_path)
    doc = doc or data(ledger)
    draft = draft if draft is not None else json.dumps(doc, ensure_ascii=False)
    calls = calls if calls is not None else [recorded(ledger, draft)]
    report = report if report is not None else reference(ledger, draft, doc)
    harness_identity = harness_identity if harness_identity is not None else atoms.ledger_identity(ledger)
    return ledger, submission.load_submission(report, ledger, calls,
                                               trace_identity or trace(ledger), harness_identity)


def test_inline_v1_is_unchanged_and_marked_inline(tmp_path):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    report = "summary\n```json\n" + json.dumps(doc, ensure_ascii=False) + "\n```"
    expected = verdict.load_block(report)
    got = submission.load_submission(report, ledger, [], None)
    for key in ("found", "kind", "raw", "data", "errors"):
        assert got[key] == expected[key]
    assert got["submission"]["mode"] == "inline" and got["submission"]["status"] == "accepted"


def test_inline_v1_can_mention_ref_schema_without_becoming_a_submission(tmp_path):
    ledger = _pool(tmp_path); doc = data(ledger)
    doc["notes"] = "Do not emit migloop-verdict-ref/1 yet."
    report = "```json\n" + json.dumps(doc) + "\n```"
    got = submission.load_submission(report, ledger, [], None)
    assert got["data"] == doc and got["submission"]["mode"] == "inline"


def test_valid_ref_loads_exact_last_checked_json_and_preserves_warnings(tmp_path):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    doc["defects"][0]["nodes"][0]["role"] = "进入·错"  # valid schema; missing basis is a warning
    draft = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    got = submission.load_submission(reference(ledger, draft, doc), ledger,
                                     [recorded(ledger, draft)], trace(ledger), atoms.ledger_identity(ledger))
    assert got["errors"] == [] and got["kind"] == "json" and got["raw"] == draft
    meta = got["submission"]
    assert meta["mode"] == "checked_draft_ref" and meta["status"] == "accepted"
    assert meta["check_status"] == "needs_review"
    assert any(issue["code"] == "missing_causal_basis" for issue in meta["check_issues"])
    assert meta["binding"]["matched_check"] == 1 and meta["semantic_checked"] is False


def test_fenced_checked_draft_extracts_body_without_canonical_rewrite(tmp_path):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    body = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    draft = "```json\n" + body + "```"
    got = submission.load_submission(reference(ledger, draft, doc), ledger,
                                     [recorded(ledger, draft)], trace(ledger), atoms.ledger_identity(ledger))
    assert got["errors"] == [] and got["raw"] == body and got["data"] == doc
    assert got["submission"]["draft_sha256"] == hashlib.sha256(draft.encode()).hexdigest()


@pytest.mark.parametrize("missing", ["draft_sha256", "document_sha256"])
def test_ref_requires_both_hashes(tmp_path, missing):
    ledger = _pool(tmp_path); doc = data(ledger); draft = json.dumps(doc)
    ref = json.loads(reference(ledger, draft, doc).splitlines()[1]); del ref[missing]
    report = "```json\n" + json.dumps(ref) + "\n```"
    got = submission.load_submission(report, ledger, [recorded(ledger, draft)], trace(ledger),
                                     atoms.ledger_identity(ledger))
    assert got["data"] is None and any("缺少键" in error for error in got["errors"])


@pytest.mark.parametrize("changed", ["raw_hash", "document_hash", "draft_after_check"])
def test_ref_rejects_changed_hash_or_draft(tmp_path, changed):
    ledger = _pool(tmp_path); doc = data(ledger); draft = json.dumps(doc)
    report = reference(ledger, draft, doc)
    calls = [recorded(ledger, draft)]
    if changed == "raw_hash":
        report = reference(ledger, draft, doc, draft_sha256="0" * 64)
    elif changed == "document_hash":
        report = reference(ledger, draft, doc, document_sha256="0" * 64)
    else:
        changed_doc = deepcopy(doc); changed_doc["notes"] = "new unchecked text"
        calls = [recorded(ledger, json.dumps(changed_doc))]
    got = submission.load_submission(report, ledger, calls, trace(ledger), atoms.ledger_identity(ledger))
    assert got["data"] is None and got["submission"]["status"] == "rejected"


@pytest.mark.parametrize("mode", ["ref", "trace", "harness", "observed"])
def test_any_identity_mix_fails_closed(tmp_path, mode):
    ledger = _pool(tmp_path); doc = data(ledger); draft = json.dumps(doc)
    report = reference(ledger, draft, doc, **({"ledger": "other"} if mode == "ref" else {}))
    tr = trace(ledger)
    harness = atoms.ledger_identity(ledger)
    if mode == "trace": tr["current"] = "other"
    if mode == "harness": harness = "other"
    if mode == "observed": tr["source_identities"].append("other")
    got = submission.load_submission(report, ledger, [recorded(ledger, draft)], tr, harness)
    assert got["data"] is None and any("身份" in error for error in got["errors"])


def test_truncated_or_bad_last_check_never_falls_back(tmp_path):
    ledger = _pool(tmp_path); doc = data(ledger); draft = json.dumps(doc)
    good = recorded(ledger, draft)
    truncated = recorded(ledger, draft, delivery_truncated=True)
    got = submission.load_submission(reference(ledger, draft, doc), ledger, [good, truncated],
                                     trace(ledger), atoms.ledger_identity(ledger))
    assert got["data"] is None and got["submission"]["binding"]["matched_check"] is None
    bad = recorded(ledger, draft, text="not json")
    got = submission.load_submission(reference(ledger, draft, doc), ledger, [good, bad],
                                     trace(ledger), atoms.ledger_identity(ledger))
    assert got["data"] is None and got["submission"]["source_check_step"] == 2


def test_no_final_ref_never_uses_a_checked_draft(tmp_path):
    ledger = _pool(tmp_path); doc = data(ledger); draft = json.dumps(doc)
    got = submission.load_submission("summary only", ledger, [recorded(ledger, draft)],
                                     trace(ledger), atoms.ledger_identity(ledger))
    assert got["found"] is False and got["data"] is None
    assert got["submission"] == {"schema": "migloop-submission/1", "mode": "inline",
                                  "status": "rejected", "semantic_checked": False,
                                  "reason": "no_verdict_block"}


def test_nested_json_cannot_smuggle_a_ref(tmp_path):
    ledger = _pool(tmp_path); doc = data(ledger); draft = json.dumps(doc)
    nested = {"wrapper": json.loads(reference(ledger, draft, doc).splitlines()[1])}
    report = "```json\n" + json.dumps(nested) + "\n```"
    got = submission.load_submission(report, ledger, [recorded(ledger, draft)], trace(ledger),
                                     atoms.ledger_identity(ledger))
    assert got["data"] is None and got["submission"]["mode"] == "checked_draft_ref"
    assert any("顶层对象" in error for error in got["errors"])


def test_materialize_writes_exact_document_and_metadata_without_overwriting(tmp_path):
    ledger = _pool(tmp_path); doc = data(ledger)
    body = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    loaded = submission.load_submission(reference(ledger, body, doc), ledger,
                                        [recorded(ledger, body)], trace(ledger), atoms.ledger_identity(ledger))
    run = tmp_path / "run"; run.mkdir()
    (run / "result.json").write_text("full final response", encoding="utf-8")
    (run / "transcript.jsonl").write_text("full check records", encoding="utf-8")
    pair.write_submission_artifacts(run, loaded)
    assert (run / "document.json").read_text(encoding="utf-8") == body
    meta = json.loads((run / "submission.json").read_text(encoding="utf-8"))
    assert meta["status"] == "accepted" and meta["document_artifact"] == "document.json"
    assert meta["final_response_artifact"] == "result.json" and meta["check_records_artifact"] == "transcript.jsonl"
    with pytest.raises(FileExistsError):
        pair.write_submission_artifacts(run, loaded)


def test_materialize_yaml_preserves_exact_checked_body(tmp_path):
    ledger = _pool(tmp_path)
    doc = {"schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger), "defects": []}
    body = ("schema: migloop-verdict/1\nledger: " + atoms.ledger_identity(ledger)
            + "\ndefects: []\n")
    loaded = submission.load_submission(reference(ledger, body, doc), ledger,
                                        [recorded(ledger, body)], trace(ledger), atoms.ledger_identity(ledger))
    run = tmp_path / "yaml-run"; run.mkdir()
    pair.write_submission_artifacts(run, loaded)
    assert (run / "verdict.yaml").read_text(encoding="utf-8") == body
    assert not (run / "document.json").exists()


def test_collect_verdict_uses_submission_only_when_frozen_source_has_module(tmp_path, monkeypatch):
    from migloop import coverage, probe, via

    ledger = _pool(tmp_path); doc = data(ledger); draft = json.dumps(doc)
    identity = atoms.ledger_identity(ledger)
    calls = [recorded(ledger, draft)]
    source = tmp_path / "source"
    (source / "src/migloop").mkdir(parents=True)
    for name in ("service.py", "coverage.py", "draft_check.py", "submission.py"):
        (source / "src/migloop" / name).write_text("# feature marker\n", encoding="utf-8")
    service = type("Service", (), {"session_ledger": staticmethod(lambda _root: ledger),
                                    "fixchain_payload": staticmethod(lambda _root: {"chains": []})})
    monkeypatch.setattr(pair, "load_modules", lambda _source: (service, atoms, verdict))
    monkeypatch.setattr(probe, "_transcript_calls", lambda _folder: calls)
    monkeypatch.setattr(via, "trace_identity", lambda *_args, **_kwargs: trace(ledger))
    case = {"source": str(source), "pool": str(tmp_path), "current_root": "synthetic", "roots": ["synthetic"], "file": "A.ets"}
    result = {"response_text": reference(ledger, draft, doc)}
    got = pair.collect_verdict(case, result, "tools", tmp_path, "reference")
    assert got["errors"] == [] and got["data"] == doc
    assert got["submission"]["mode"] == "checked_draft_ref"
    assert got["draft_check"]["status"] == "matched"


def test_final_mode_is_explicit_in_prompt_and_mcp_environment(tmp_path):
    case_dir = tmp_path / "case"; case_dir.mkdir()
    (case_dir / "common-task.md").write_text("same task", encoding="utf-8")
    case = {"source": str(tmp_path / "source"), "pool": str(tmp_path / "pool")}
    document = pair.build_prompt(case_dir, case, "tools", "native", "document")
    ref_prompt = pair.build_prompt(case_dir, case, "tools", "native", "reference")
    assert document.startswith("same task\n") and ref_prompt.startswith("same task\n")
    assert "当前 GUIDE 要求的 migloop-verdict YAML" in document
    assert "最终回复严格按 GUIDE 的 reference 模式" in ref_prompt and "双哈希引用" in ref_prompt
    assert "不再重写全文" in ref_prompt
    assert pair.mcp_server_config(case, "document")["env"]["MIGLOOP_FINAL_MODE"] == "document"
    assert pair.mcp_server_config(case, "reference")["env"]["MIGLOOP_FINAL_MODE"] == "reference"
