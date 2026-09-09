from copy import deepcopy

import pytest

from migloop import atoms, coverage, coverage_receipt
from tests.test_repair_coverage import PATH, declaration, splash_ledger


def fixture():
    ledger, chains = splash_ledger()
    manifest = coverage.manifest(ledger, chains, PATH)
    value = {"manifest_sha256": coverage_receipt.receipt(manifest)["manifest_sha256"],
             "reviewed": [declaration(52)], "complement": "not_investigated"}
    return ledger, manifest, value


def test_complement_is_not_a_model_claim_or_an_explanation():
    ledger, manifest, value = fixture()
    before = deepcopy(value)
    out = coverage_receipt.reconcile(ledger, manifest, value, ["A"], identity_bound=True)
    assert value == before
    assert out["complete"] and out["manifest_identity_valid"] and not out["declarations_complete"]
    assert out["counts"]["accounted"] == 3 and out["counts"]["reviewed"] == 1
    assert out["counts"]["not_investigated"] == 2 and len(out["rows"]) == 1
    assert out["not_investigated"] == [f"file:{PATH}@v53", f"file:{PATH}@v54"]
    assert all(row["source"] == "system_manifest" and row["model_claim"] is False for row in out["complement_rows"])
    assert out["deferred"] == out["unconfirmed"] == []
    assert out["semantic_checked"] is False


def test_zero_reviewed_and_valid_manifest_means_zero_investigated():
    ledger, manifest, value = fixture()
    value["reviewed"] = []
    out = coverage_receipt.reconcile(ledger, manifest, value, [], identity_bound=True)
    assert out["complete"] and out["counts"]["reviewed"] == 0
    assert out["counts"]["not_investigated"] == 3 and out["rows"] == []
    assert out["declarations_complete"] is False


@pytest.mark.parametrize("change", ["target", "ledger", "policy", "order", "delete", "evidence", "identity"])
def test_receipt_binds_full_manifest_and_identity_without_fallback(change):
    ledger, manifest, value = fixture()
    if change in ("target", "ledger", "policy"):
        manifest[{"target": "file", "ledger": "ledger", "policy": "policy"}[change]] = "changed"
    elif change == "order":
        manifest["items"].reverse()
    elif change == "delete":
        manifest["items"].pop()
    elif change == "evidence":
        manifest["items"][0]["event"]["id"] = "changed"
    out = coverage_receipt.reconcile(ledger, manifest, value, ["A"], identity_bound=change != "identity")
    assert not out["complete"] and not out["manifest_identity_valid"]
    assert out["not_investigated"] == out["complement_rows"] == []


@pytest.mark.parametrize("status", ["explained", "out_of_scope", "not_repair", "unresolved", None])
def test_complement_cannot_forge_review_outcome(status):
    ledger, manifest, value = fixture()
    value["complement"] = status
    out = coverage_receipt.reconcile(ledger, manifest, value, ["A"], identity_bound=True)
    assert not out["complete"] and not out["complement_rows"]


def test_bad_explicit_rows_do_not_disappear_inside_complement():
    ledger, manifest, value = fixture()
    value["reviewed"] = [declaration(52), declaration(52), declaration(53, status="invented")]
    out = coverage_receipt.reconcile(ledger, manifest, value, ["A"], identity_bound=True)
    assert not out["complete"]
    assert out["duplicates"] and out["invalid_status"]
    assert out["not_investigated"] == [f"file:{PATH}@v54"]
    assert out["counts"]["reviewed"] == 0


def test_legacy_reconcile_remains_strict_and_document_dispatch_is_explicit():
    ledger, manifest, value = fixture()
    old = coverage.reconcile_document(ledger, manifest, value, ["A"], identity_bound=True)
    assert not old["complete"] and old["invalid_rows"]
    new = coverage.reconcile_document(ledger, manifest, value, ["A"], identity_bound=True,
                                      schema="migloop-verdict/2")
    assert new["complete"]
    assert coverage.declared_rows(value, "migloop-verdict/2") is value["reviewed"]
    assert coverage.declared_rows(value) is value


def test_receipt_changes_for_added_candidate_and_manifest_errors():
    ledger, manifest, value = fixture()
    manifest["errors"].append({"code": "missing_input"})
    value["manifest_sha256"] = coverage_receipt.receipt(manifest)["manifest_sha256"]
    out = coverage_receipt.reconcile(ledger, manifest, value, ["A"], identity_bound=True)
    assert not out["complete"] and not out["manifest_identity_valid"]


def test_receipt_is_deterministic_and_never_changes_ledger():
    ledger, manifest, value = fixture()
    original = atoms.ledger_identity(ledger)
    assert coverage_receipt.receipt(manifest) == coverage_receipt.receipt(deepcopy(manifest))
    coverage_receipt.reconcile(ledger, manifest, value, ["A"], identity_bound=True)
    assert atoms.ledger_identity(ledger) == original
