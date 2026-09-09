"""Versioned extensions that separate task scope, events and review coverage.

V1 remains strict and unchanged. The legacy-shaped view is used only for shared
schema validation; hashes, author text and downstream projections keep V2 data.
"""
from __future__ import annotations

from typing import Any

from . import atoms, coverage, coverage_receipt

SCHEMA = "migloop-verdict/2"
_EXTRA = {"target_file", "event_claims", "entry_events", "recommendation"}


def validate(data: dict[str, Any]) -> list[str]:
    from . import verdict, event_claims

    legacy = {**data, "schema": verdict.SCHEMA}
    errors = []
    declarations = data.get("coverage")
    if declarations is not None:
        errors.extend(coverage_receipt.validate(declarations))
        legacy["coverage"] = declarations.get("reviewed", []) if isinstance(declarations, dict) else []
    defs = data.get("defects")
    if isinstance(defs, list):
        legacy["defects"] = []
        for index, defect in enumerate(defs):
            if not isinstance(defect, dict):
                legacy["defects"].append(defect)
                continue
            legacy["defects"].append({key: value for key, value in defect.items() if key not in _EXTRA})
            target = defect.get("target_file")
            if (not isinstance(target, str) or not target.strip() or "@v" in target
                    or any(part == ".." for part in target.replace("\\", "/").split("/"))):
                errors.append(f"defects[{index}].target_file: 必须是无版本、无父路径跳转的文件路径")
            if "recommendation" in defect and (not isinstance(defect["recommendation"], str)
                                               or not defect["recommendation"].strip()):
                errors.append(f"defects[{index}].recommendation: 必须是非空建议文本，仍属模型主张")
            nodes = defect.get("nodes")
            for node_index, node in enumerate(nodes if isinstance(nodes, list) else []):
                if isinstance(node, dict) and node.get("role") in verdict.RED and "basis" not in node:
                    errors.append(f"defects[{index}].nodes[{node_index}].basis: v2红节点必须给出结构化双方依据")
            errors.extend(f"defects[{index}].{error}" for error in event_claims.validate(
                defect.get("event_claims", []), defect.get("entry_events", [])))
    return errors + verdict.validate(legacy)


def target_binding(ledger: atoms.Ledger, declaration: str, *, identity_bound: bool) -> dict[str, Any]:
    path, error = coverage._path(ledger, declaration) if identity_bound else (None, "账本身份未绑定")
    return {"declared_path": declaration, "canonical_path": path,
            "status": "matched" if path else "unbound" if not identity_bound else (
                "ambiguous" if error == "文件路径有歧义" else "unlocated"),
            "source": "model", "diag": error, "creates_node": False, "semantic_checked": False}


def extend(ledger: atoms.Ledger, source: dict[str, Any], result: dict[str, Any]) -> None:
    """Add independent projections without changing roles, fixed nodes or edges."""
    from . import event_claims

    bound = result["identity"]["bound"] is True
    for declared, projected in zip(source.get("defects") or [], result["defects"]):
        projected["target_binding"] = target_binding(ledger, declared["target_file"], identity_bound=bound)
        projected["event_claims"] = event_claims.build(ledger, declared.get("event_claims", []),
            declared.get("entry_events", []), identity_bound=bound)
        projected["recommendation"] = declared.get("recommendation")
