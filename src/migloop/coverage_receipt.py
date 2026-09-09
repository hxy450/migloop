"""Authenticated manifest complements, never fabricated review declarations.

The receipt certifies a denominator. Only explicit reviewed rows are model
claims; the remaining identities are system-owned ``not_investigated`` items.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from . import atoms, coverage

SCHEMA = "migloop-coverage-receipt/1"
_KEYS = {"manifest_sha256", "reviewed", "complement"}


def receipt(manifest: dict[str, Any]) -> dict[str, Any]:
    # Hash the entire declared manifest, including its selection policy, order,
    # scope, event identities and diagnostics. Do not hash a rendered summary.
    body = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"schema": SCHEMA, "ledger": manifest.get("ledger"), "target": manifest.get("file"),
            "manifest_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "versions": len(manifest.get("items") or []),
            "candidates": len(manifest.get("candidates") or []),
            "valid": not manifest.get("errors"), "semantic_checked": False}


def validate(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["coverage v2 必须是 manifest_sha256 / reviewed / complement 映射"]
    errors = []
    if set(value) != _KEYS:
        errors.append("coverage v2 必须且只能包含 manifest_sha256 / reviewed / complement")
    digest = value.get("manifest_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append("coverage.manifest_sha256 必须是清单提供的64位小写摘要")
    if not isinstance(value.get("reviewed"), list):
        errors.append("coverage.reviewed 必须是逐项声明列表")
    if value.get("complement") != "not_investigated":
        errors.append("coverage.complement 只能是 not_investigated，不能批量宣称已解释或题外")
    return errors


def reconcile(ledger: atoms.Ledger, manifest: dict[str, Any], declaration: Any,
              defects: Any, *, identity_bound: bool = False) -> dict[str, Any]:
    shape_errors = validate(declaration)
    rows = declaration.get("reviewed") if isinstance(declaration, dict) else None
    out = coverage.reconcile(ledger, manifest, rows, defects, identity_bound=identity_bound)
    proof = receipt(manifest)
    matched = (not shape_errors and identity_bound is True and proof["valid"]
               and manifest.get("ledger") == atoms.ledger_identity(ledger)
               and declaration["manifest_sha256"] == proof["manifest_sha256"])
    out.update(mode="manifest_complement", receipt=proof, manifest_identity_valid=bool(matched),
               reviewed_rows=out["rows"], not_investigated=[], complement_rows=[],
               declarations_complete=False, semantic_checked=False)
    out["counts"].update(reviewed=out["counts"]["accounted"], not_investigated=0)
    for message in shape_errors:
        out["errors"].append({"code": "receipt_shape", "message": message})
    if not matched:
        out["errors"].append({"code": "receipt_mismatch", "message": "清单摘要/账本/目标未匹配；不展开未调查补集"})
        out.update(complete=False, status="invalid_receipt")
        return out

    # Only genuine absences become system complement rows. Invalid/duplicate
    # explicit declarations remain errors and cannot disappear in the complement.
    complement = list(out["missing"])
    out["not_investigated"] = complement
    out["complement_rows"] = [
        {"target": target, "status": "not_investigated", "source": "system_manifest",
         "model_claim": False, "semantic_checked": False} for target in complement]
    out["errors"] = [row for row in out["errors"] if row["code"] != "missing"]
    out["missing"] = out["missing_versions"] = out["missing_candidates"] = []
    out["counts"].update(accounted=out["counts"]["accounted"] + len(complement),
                         not_investigated=len(complement), missing=0, missing_versions=0, missing_candidates=0)
    out["complete"] = not out["errors"]
    out["declarations_complete"] = out["complete"] and not complement
    out["status"] = "accounted_with_uninvestigated" if out["complete"] and complement else (
        "accounted" if out["complete"] else "invalid")
    out["scope"] += " v2 补集只表示未调查，不是模型逐项审阅、题外判定或语义完备证明。"
    return out
