"""Lossless, explicitly non-accepting preview of locally invalid v3 documents.

Callers must authenticate report text BEFORE invoking this module, or invoke it
as an explicit manual draft check. Nothing here authenticates cached documents,
repairs the submission, changes strict format metrics, or scans change inventory.
Only whitelisted model fields feed coordinate/relationship verification.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from copy import deepcopy
from typing import Any

from . import atoms, temporal, verdict_v3
from .time_scope import _time

SCHEMA = "migloop-verdict-preview/1"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_errors(value: Any, path: str = "", active: set[int] | None = None) -> list[str]:
    """Reject YAML dates, sets, non-string keys, aliases/cycles and NaN, not cast."""
    active = set() if active is None else active
    if value is None or type(value) in (str, int, bool):
        return []
    if type(value) is float:
        return [] if math.isfinite(value) else [f"{path or '/'}: non-finite JSON number"]
    if type(value) not in (dict, list):
        return [f"{path or '/'}: non-JSON type {type(value).__name__}; value not coerced"]
    if id(value) in active:
        return [f"{path or '/'}: recursive alias is not JSON"]
    active.add(id(value))
    errors = []
    for key, child in (value.items() if type(value) is dict else enumerate(value)):
        if type(value) is dict and type(key) is not str:
            errors.append(f"{path or '/'}: non-string JSON key ({type(key).__name__})")
            continue
        token = str(key).replace("~", "~0").replace("/", "~1")
        errors.extend(_json_errors(child, path + "/" + token, active))
    active.remove(id(value))
    return errors


def _fields(row: Any, allowed: set[str]) -> dict:
    return {key: deepcopy(value) for key, value in row.items() if key in allowed} if isinstance(row, dict) else {}


def _counts(rows: list) -> Counter:
    return Counter(row["id"] for row in rows if isinstance(row, dict) and verdict_v3._text(row.get("id")))


def _model_text(value: Any) -> bool:
    return isinstance(value, str) or isinstance(value, list) and all(isinstance(v, str) for v in value)


def _remarks(row: Any, allowed: set[str], where: str) -> list[dict]:
    return [{"location": where + "/" + key, "field": key, "value": deepcopy(value),
             "source": "model", "semantic_checked": False, "used_for_binding": False}
            for key, value in row.items() if key not in allowed and _model_text(value)] if isinstance(row, dict) else []


def _local_errors(errors: list[str], prefix: str) -> list[str]:
    return [error for error in errors if error.startswith((prefix + ".", prefix + ":"))]


def _binding(status: str, detail: str) -> dict:
    return {"status": status, "diag": detail, "semantic_checked": False, "state_binding": "not_proven"}


def _references(ledger, declared: Any, scope: dict, bound: bool) -> list[dict]:
    values = declared if isinstance(declared, list) else [declared]
    return [verdict_v3.resolve_evidence(ledger, value, scope=scope, bound=bound)
            if verdict_v3._text(value) else {"ref": value if isinstance(value, str) else None,
                "declaration": deepcopy(value), "status": "invalid",
                "diag": "原声明不是非空引用字符串", "scope": deepcopy(scope), "semantic_checked": False}
            for value in values]


def build(ledger: atoms.Ledger, document: dict, *, raw: str | None = None,
          meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an explicitly partial graph without accepting or repairing a draft.

    Original JSON document/hash and raw/hash remain separate from projections.
    ``meta`` contributes only harness/trace identity restrictions; supplied cache
    verification flags, nodes, coverage and hashes are never authority. Non-JSON
    parsed values fail closed with a raw hash and diagnostic, not a string cast.
    """
    meta = meta if isinstance(meta, dict) else {}
    raw = raw if raw is not None else meta.get("raw")
    original_raw = raw if isinstance(raw, str) else None
    json_errors = _json_errors(document)
    if not isinstance(document, dict):
        json_errors.append("顶层必须是映射")
    digest = None
    if not json_errors:
        try:
            digest = _hash(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
        except (TypeError, ValueError, OverflowError) as exc:
            json_errors.append("original document is not JSON-serializable: " + type(exc).__name__)
    source = document if not json_errors else {}
    errors = json_errors or verdict_v3.validate(source)
    current = atoms.ledger_identity(ledger)
    claimed = source.get("ledger")
    trace = meta.get("trace_identity") if isinstance(meta.get("trace_identity"), dict) else {}
    identity_ok = (claimed == current and meta.get("harness_identity") in (None, current)
                   and trace.get("bound") is not False)
    target = source.get("target")
    target_errors = [e for e in errors if e.startswith("target")]
    target_ok = isinstance(target, dict) and not target_errors
    if target_ok:
        try:
            file = target["file"]
            if "@v" in file or ".." in file.replace("\\", "/").split("/"):
                raise ValueError("target.file 不接受版本或父路径跳转")
            temporal.resolve_file(ledger, file)
        except (ValueError, TypeError, KeyError) as exc:
            target_ok = False
            target_errors.append(str(exc))
    bound = bool(not json_errors and source.get("schema") == verdict_v3.SCHEMA and identity_ok and target_ok)
    identity = {"current": current, "claimed": claimed, "bound": bound,
                "status": "matched" if bound else "unbound", "binding_scope": "ledger_and_coordinates_only",
                "semantic_checked": False}
    diagnostics = [{"code": "original_schema", "detail": error} for error in errors]
    if not bound:
        diagnostics.append({"code": "preview_global_unbound", "detail": "身份/schema/target 无效；局部声明不绑定当前账本"})
    diagnostics.extend({"code": "target_unbound", "detail": error} for error in target_errors)
    graph = {"schema": verdict_v3.GRAPH_SCHEMA, "projection_schema": SCHEMA, "partial_document": True,
             "original_schema_valid": not errors, "document_sha256": digest, "target": deepcopy(target),
             "identity": identity, "nodes": [], "edges": [], "findings": [], "coverage": [],
             "node_declarations": [], "edge_declarations": [], "model_remarks": [], "diagnostics": diagnostics,
             "complete": False, "coverage_checked": False, "semantic_checked": False}
    result = {"schema": SCHEMA, "source_schema": source.get("schema"), "partial_document": True,
              "original_schema_valid": not errors, "strict_status": "passed" if not errors else "failed",
              "schema_errors": errors, "errors": errors, "document_sha256": digest, "original_document_sha256": digest,
              "strict_document_sha256": digest if not errors else None,
              "raw": original_raw, "raw_sha256": _hash(original_raw) if original_raw is not None else None,
              "original_document": deepcopy(document) if not json_errors else None,
              "original_document_available": not json_errors, "identity": identity, "target": deepcopy(target),
              "authentication": {"status": "not_performed_by_preview", "caller_must_authenticate_report": True,
                                 "manual_draft_check_is_not_report_authentication": True},
              "document_source": {"kind": "preview_projection", "verified": False, "semantic_checked": False},
              "argument_graph": graph, "diagnostics": diagnostics, "semantic_checked": False}
    if json_errors:
        return result
    graph["model_remarks"].extend(_remarks(source, verdict_v3._TOP, ""))
    findings = source.get("findings") if isinstance(source.get("findings"), list) else []
    finding_counts = _counts(findings)
    display_finding_ids = set(finding_counts)
    for i, declared in enumerate(findings):
        location = f"/findings/{i}"
        if not isinstance(declared, dict):
            graph["findings"].append({"location": location, "declaration": deepcopy(declared),
                                      "schema_valid": False, "source": "model", "semantic_checked": False})
            continue
        model_id = declared.get("id")
        unique_finding = verdict_v3._text(model_id) and finding_counts[model_id] == 1
        finding_id = model_id if unique_finding else "@preview:" + location
        if not unique_finding:
            while finding_id in display_finding_ids:
                finding_id = "@" + finding_id
            display_finding_ids.add(finding_id)
        finding = {**_fields(declared, verdict_v3._FINDING - {"nodes", "edges"}), "id": finding_id,
            "declared_id": deepcopy(model_id), "display_id_only": not unique_finding,
            "location": location, "declaration": deepcopy(declared), "nodes": [], "edges": [],
            "source": "model", "semantic_checked": False,
            "schema_errors": _local_errors(errors, f"findings[{i}]"),
            "id_status": "unique" if unique_finding else "ambiguous" if verdict_v3._text(model_id) else "invalid"}
        finding["schema_valid"] = not finding["schema_errors"] and unique_finding
        graph["findings"].append(finding)
        graph["model_remarks"].extend(_remarks(declared, verdict_v3._FINDING, location))
        node_rows = declared.get("nodes") if isinstance(declared.get("nodes"), list) else []
        node_counts, nodes = _counts(node_rows), {}
        for j, original in enumerate(node_rows):
            pointer = location + f"/nodes/{j}"
            node = {**_fields(original, verdict_v3._NODE), "location": pointer,
                    "declaration": deepcopy(original), "finding": finding_id, "source": "model", "semantic_checked": False}
            valid = (isinstance(original, dict) and all(verdict_v3._text(original.get(k)) for k in ("id", "key", "reason"))
                     and verdict_v3._choice(original.get("kind"), ("file", "agent"))
                     and verdict_v3._choice(original.get("role"), verdict_v3.ROLES) and _time(original.get("at")) is not None)
            local_id = original.get("id") if isinstance(original, dict) else None
            unique_node = verdict_v3._text(local_id) and node_counts[local_id] == 1
            normal_id = unique_finding and unique_node
            node.update(id=verdict_v3._qualified(model_id, local_id) if normal_id else "@preview:" + pointer,
                        local_id=deepcopy(local_id), display_id_only=not normal_id,
                        schema_errors=_local_errors(errors, f"findings[{i}].nodes[{j}]"))
            if not valid:
                node["binding"] = _binding("invalid", "节点必需字段无效；不补时间、角色、身份或原因")
            elif not normal_id:
                node["binding"] = _binding("ambiguous", "finding/node ID 缺失或重复；保留全部声明，不择一")
            else:
                node["binding"] = verdict_v3._node_binding(ledger, original, bound, target["at"] if target_ok else "")
            node["schema_valid"] = bool(valid and normal_id and not node["schema_errors"])
            graph["node_declarations"].append(node)
            if not valid:
                diagnostics.append({"code": "preview_node_invalid", "location": pointer, "detail": node["binding"]["diag"]})
                continue
            if not normal_id:
                diagnostics.append({"code": "preview_node_ambiguous", "location": pointer, "detail": node["binding"]["diag"]})
            evidence_scope = verdict_v3._scope(node["kind"], node["binding"].get("canonical_key") or node["key"], node["at"])
            for field in ("evidence", "counterevidence"):
                node[field] = _references(ledger, original.get(field, []), evidence_scope,
                                           bound and normal_id and node["binding"]["status"] == "matched")
            graph["nodes"].append(node)
            finding["nodes"].append(node)
            if normal_id:
                nodes[local_id] = node
        edge_rows = declared.get("edges") if isinstance(declared.get("edges"), list) else []
        for j, original in enumerate(edge_rows):
            pointer = location + f"/edges/{j}"
            edge = {**_fields(original, verdict_v3._EDGE), "id": "@preview:" + pointer, "location": pointer,
                    "declaration": deepcopy(original), "finding": finding_id, "source": "model", "semantic_checked": False,
                    "schema_errors": _local_errors(errors, f"findings[{i}].edges[{j}]"), "drawable": False}
            valid = (isinstance(original, dict) and all(verdict_v3._text(original.get(k)) for k in ("from", "to", "claim"))
                     and verdict_v3._choice(original.get("relation"), verdict_v3.RELATIONS))
            left = nodes.get(original.get("from")) if valid else None
            right = nodes.get(original.get("to")) if valid else None
            operation = original["relation"].removeprefix("possible_") if valid else None
            expected = ("file", "agent") if operation == "read" else ("agent", "file")
            valid = bool(valid and left and right and (left["kind"], right["kind"]) == expected)
            if not valid:
                edge["binding"] = _binding("invalid", "端点缺失/歧义或方向不符；声明保留但不连线、不补 file")
            else:
                file_node = left if operation == "read" else right
                cutoff = min(_time(left["at"]), _time(right["at"])).isoformat()
                edge_scope = verdict_v3._scope("file", file_node["binding"].get("canonical_key") or file_node["key"], cutoff)
                refs = _references(ledger, original.get("evidence", []), edge_scope, bound)
                edge.update({"from": left["id"], "to": right["id"], "evidence": refs, "drawable": True,
                             "propagation": {"claim": original["claim"], "source": "model", "semantic_checked": False},
                             "binding": verdict_v3._edge_binding(ledger, original, left, right, refs, bound)})
                graph["edges"].append(edge)
                finding["edges"].append(edge)
            graph["edge_declarations"].append(edge)
            if not valid:
                diagnostics.append({"code": "preview_edge_invalid", "location": pointer, "detail": edge["binding"]["diag"]})
    coverage_rows = source.get("coverage") if isinstance(source.get("coverage"), list) else []
    coverage_counts = Counter(row["event"] for row in coverage_rows if isinstance(row, dict) and verdict_v3._text(row.get("event")))
    for i, original in enumerate(coverage_rows):
        row = _fields(original, {"event", "status", "finding", "reason"})
        local = _local_errors(errors, f"coverage[{i}]")
        event, finding_id = row.get("event"), row.get("finding")
        if verdict_v3._text(event) and coverage_counts[event] != 1:
            local.append("重复 event 的全部声明均无效，不择一")
        if finding_id is not None and (not verdict_v3._text(finding_id) or finding_counts[finding_id] != 1):
            local.append("finding 引用不存在、缺失或歧义；不拆分或补目标")
        row.update(declaration=deepcopy(original), location=f"/coverage/{i}", declared_status=row.get("status"),
                   status="invalid" if local else "unresolved", status_source="preview_mechanical",
                   binding=_binding("invalid" if local else "not_checked", "预览不扫描修改清单、不认证覆盖结论"),
                   schema_valid=not local, schema_errors=local, source="model", semantic_checked=False)
        graph["coverage"].append(row)
    return result
