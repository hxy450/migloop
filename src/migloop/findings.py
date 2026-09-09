"""Lossless per-file projection of attributed findings, never a truth promotion.

The author document remains migloop-verdict/1. This system-owned read model
groups that document's claims for UI/archive consumers without requiring the
model to repeat coordinates, audits or the recorded investigation trajectory.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .verdict import RED


SCHEMA = "migloop-findings/1"


def basis_status(node: dict[str, Any]) -> str:
    basis = node.get("basis")
    if basis is None:
        return "absent_warning" if node.get("role") in RED else "not_required"
    if not isinstance(basis, dict) or not all(basis.get(k) for k in (
            "expected", "actual", "expected_evidence", "actual_evidence", "counterevidence")):
        return "invalid_legacy"
    return "complete"


def project(structured: dict[str, Any] | None) -> dict[str, Any]:
    """Project validated verdict.build output; do not resolve new facts here.

    File node existence is machine checked. A defect's association with that
    file, repair intent, causality and recommendations remain model claims.
    Unbound items survive rather than being assigned to a convenient root.
    """
    document = structured or {}
    identity = document.get("identity") or {}
    digest = document.get("document_sha256")
    out: dict[str, Any] = {
        "schema": SCHEMA, "document_sha256": digest, "identity": deepcopy(identity),
        "document_source": deepcopy(document.get("document_source") or {
            "kind": "unrecorded", "verified": False, "semantic_checked": False}),
        "files": [], "items": {}, "unbound_items": [],
        "errors": list(document.get("errors") or []), "notes": deepcopy(document.get("notes")),
        "source_schema": document.get("schema"), "root": deepcopy(document.get("root")),
        "audit": {"semantic_checked": False, "scope_complete": False,
                  "note": "按模型声明的修复锚点归集；节点存在、引用可定位和机械边检查不证明归因正确。"},
    }
    if not digest or out["errors"]:
        return out
    files: dict[str, dict[str, Any]] = {}
    for defect in document.get("defects") or []:
        did = str(defect["id"])
        item_id = f"{digest}:{did}"
        causes = []
        for node in defect.get("nodes") or []:
            # Preserve even invalid coordinates and references, including their
            # diagnostics. Rendering should not silently erase disputed claims.
            causes.append({**deepcopy(node), "source": "model", "semantic_checked": False,
                           "basis_status": basis_status(node)})
        item = {
            "id": item_id, "defect": did, "title": defect.get("title"), "source": "model",
            "repair": deepcopy(defect.get("repair")), "entry": deepcopy(defect.get("entry") or []),
            "causes": causes, "edges": deepcopy(defect.get("edges") or []),
            "boundary": defect.get("boundary"), "recommendation": None,
            "recommendation_status": "not_provided_by_source_schema",
            "audit": {"semantic_checked": False,
                      "advisories": deepcopy(defect.get("advisories") or [])},
        }
        out["items"][item_id] = item
        bound = False
        repair = defect.get("repair") or {}
        for side in ("before", "after"):
            node = repair.get(side) or {}
            if not (identity.get("bound") is True and node.get("ok") is True
                    and node.get("kind") == "file" and isinstance(node.get("key"), str)
                    and type(node.get("v")) is int and node["v"] > 0):
                continue
            path = node["key"]
            bucket = files.setdefault(path, {"path": path, "versions": [], "item_ids": [],
                                            "node_source": "ledger", "associations": []})
            if node["v"] not in bucket["versions"]:
                bucket["versions"].append(node["v"])
            if item_id not in bucket["item_ids"]:
                bucket["item_ids"].append(item_id)
            bucket["associations"].append({"item_id": item_id, "anchor": side, "node": node["spec"],
                                           "source": "model", "node_checked": True,
                                           "repair_semantic_checked": False})
            bound = True
        if not bound:
            out["unbound_items"].append(item_id)
    for bucket in files.values():
        bucket["versions"].sort()
    out["files"] = list(files.values())
    return out
