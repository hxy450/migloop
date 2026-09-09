from copy import deepcopy
import json

import pytest

from migloop import atoms, coverage, coverage_receipt, draft_check, submission, verdict
from tests.test_verdict import _pool, _ref, _seq_of
from tests.test_draft_check import data, recorded
from tests.test_submission import reference, trace


def document(ledger):
    result = data(ledger)
    result["schema"] = "migloop-verdict/2"
    result["defects"][0]["target_file"] = "/proj/entry/A.ets"
    result["defects"][0]["recommendation"] = "核对原始输入与输出；这仍是模型建议。"
    return result


def test_v2_roundtrip_hashes_original_document_not_legacy_validation_view(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    before = deepcopy(doc)
    raw = json.dumps(doc, ensure_ascii=False)
    parsed = verdict.load_block("```json\n" + raw + "\n```")
    assert parsed["data"] == doc and not parsed["errors"]
    built = verdict.build(ledger, doc, [], {})
    assert built["schema"] == "migloop-verdict/2"
    assert built["document_sha256"] == draft_check.document_hash(doc)
    assert built["defects"][0]["target_binding"]["canonical_path"] == "/proj/entry/A.ets"
    assert built["defects"][0]["recommendation"] == doc["defects"][0]["recommendation"]
    changed = deepcopy(doc)
    changed["defects"][0]["target_file"] = "Different.ets"
    assert draft_check.document_hash(doc) != draft_check.document_hash(changed)
    assert doc == before


def test_v2_extensions_are_rejected_under_v1_instead_of_silently_dropped(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["schema"] = verdict.SCHEMA
    errors = verdict.validate(doc)
    assert any("target_file" in error and "未知键" in error for error in errors)
    assert any("recommendation" in error for error in errors)


@pytest.mark.parametrize("target", [None, [], "", "../A.ets", "x/../A.ets", "file:A.ets@v2"])
def test_target_file_cannot_smuggle_a_version_or_traversal(tmp_path, target):
    doc = document(_pool(tmp_path))
    doc["defects"][0]["target_file"] = target
    assert any("target_file" in error for error in verdict.validate(doc))


def test_unknown_target_is_scope_not_a_new_file_node_or_repair(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["defects"][0].update(target_file="Missing.ets", nodes=[])
    before = deepcopy(ledger)
    result = verdict.build(ledger, doc, [], {})
    d = result["defects"][0]
    assert d["target_binding"]["status"] == "unlocated"
    assert d["target_binding"]["creates_node"] is False
    assert not d["nodes"] and not d["edges"] and not result["roles"] and not result["fixed"]
    assert d["repair"]["before"] is d["repair"]["after"] is None
    assert ledger == before


def test_unbound_identity_cannot_resolve_a_target_scope(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["ledger"] = "other-ledger"
    result = verdict.build(ledger, doc, [], {})
    target = result["defects"][0]["target_binding"]
    assert target["status"] == "unbound" and target["canonical_path"] is None


def test_checked_reference_preserves_v2_scope_recommendation_and_hashes(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    draft = json.dumps(doc, ensure_ascii=False)
    final = reference(ledger, draft, doc)
    call = recorded(ledger, draft)
    loaded = submission.load_submission(final, ledger, [call], trace(ledger), atoms.ledger_identity(ledger))
    assert loaded["data"] == doc and loaded["raw"] == draft
    assert loaded["submission"]["status"] == "accepted"
    altered = deepcopy(doc)
    altered["defects"][0]["recommendation"] = "未核新建议"
    assert draft_check.final_binding(ledger, [call], altered, identity_bound=True)["status"] == "mismatch"


def test_manifest_complement_draft_checks_only_reviewed_citations(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    chains = {"chains": [{"file_abs": "/proj/entry/A.ets", "fix_versions": [2]}]}
    manifest = coverage.manifest(ledger, chains, "/proj/entry/A.ets")
    doc["coverage"] = {"manifest_sha256": coverage_receipt.receipt(manifest)["manifest_sha256"],
                       "reviewed": [], "complement": "not_investigated"}
    assert verdict.validate(doc) == []
    result = draft_check.evaluate(ledger, json.dumps(doc), chains, "/proj/entry/A.ets")
    assert result["coverage"]["accounted"]
    assert result["coverage"]["counts"]["reviewed"] == 0
    assert result["coverage"]["counts"]["not_investigated"] == 1
    assert result["coverage"]["semantic_checked"] is False
    doc["coverage"]["reviewed"] = [{"node": "file:A.ets@v2", "status": "explained", "defects": ["A"],
                                     "reason": "model claim", "evidence": ["#fake:9@L99"]}]
    result = draft_check.evaluate(ledger, json.dumps(doc), chains, "/proj/entry/A.ets")
    assert any(row["code"] == "invalid_reference" for row in result["issues"])


def test_nodes_and_events_cannot_invent_third_type_edge_endpoints(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["defects"][0]["edges"] = [{"from": "event:E1", "to": "file:A.ets@v2", "relation": "写"}]
    assert any("坐标格式" in row for row in verdict.validate(doc))


def test_event_itself_is_checked_even_when_its_supporting_reference_is_real(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    actual_ref = _ref(ledger, _seq_of(ledger, "agent-c", "Write"))
    doc["defects"][0]["event_claims"] = [{"id": "E", "event": "#missing:999@L99",
        "role": "无法确认", "reason": "statement", "evidence": [actual_ref]}]
    result = draft_check.evaluate(ledger, json.dumps(doc))
    assert any(row["code"] == "invalid_event" for row in result["issues"])
    assert not any(row["code"] == "invalid_reference" for row in result["issues"])


def test_v2_red_node_requires_basis_but_legacy_contract_does_not_change(tmp_path):
    ledger = _pool(tmp_path)
    doc = document(ledger)
    doc["defects"][0]["nodes"][0]["role"] = "进入·错"
    assert any("v2红节点" in error for error in verdict.validate(doc))
    old = data(ledger)
    old["defects"][0]["nodes"][0]["role"] = "进入·错"
    assert verdict.validate(old) == []


@pytest.mark.parametrize("field", ["nodes", "event_claims", "entry_events", "coverage", "defects"])
@pytest.mark.parametrize("value", [False, 3, "bad", {}])
def test_malformed_v2_container_is_a_validation_error_not_an_exception(tmp_path, field, value):
    doc = document(_pool(tmp_path))
    if field in ("defects", "coverage"):
        doc[field] = value
    else:
        doc["defects"][0][field] = value
    assert verdict.validate(doc)
