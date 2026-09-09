"""Read-only, bounded feedback on a model draft. Never a semantic truth judge."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import atoms, coverage, verdict

SCHEMA = "migloop-draft-check/1"
MAX_CHARS = 120_000
MAX_ISSUES = 40


def document_hash(data: Any) -> str | None:
    if data is None or verdict.validate(data):
        return None
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def parse(draft: str):
    if draft.lstrip().startswith("```"):
        loaded = verdict.load_block(draft)
        return loaded.get("data"), loaded["errors"]
    data, errors = verdict.parse_block("json" if draft.lstrip().startswith("{") else "yaml", draft)
    return data, errors or verdict.validate(data)


def evaluate(ledger: atoms.Ledger, draft: str, chain_payload: dict[str, Any] | None = None,
             file: str | None = None) -> dict[str, Any]:
    """Check declared coordinates/structure only; never echo or rewrite the draft.

    No raw action bodies, graph traversal, visits or external model calls. Coverage
    is checked only for the declared target, not the user's entire research task.
    """
    out: dict[str, Any] = {
        "schema": SCHEMA, "draft_sha256": hashlib.sha256(draft.encode("utf-8")).hexdigest()
        if isinstance(draft, str) else None, "semantic_checked": False, "status": "needs_review",
        "scope": "仅核此草稿的格式、声明坐标/引用/关系及已提供清单；不认证原因、原文支持程度、实际看过或任务完备。",
        "coverage": None, "identity_bound": False, "ledger": atoms.ledger_identity(ledger),
        "document_sha256": None, "issues": [],
    }
    issues: list[dict[str, Any]] = []

    def add(code: str, detail: str, where: str = "", severity: str = "error", node: str | None = None):
        issues.append({"code": code, "severity": severity, "where": where[:300],
                       "node": node[:500] if node else None, "detail": str(detail)[:650]})

    def finish():
        out["counts"] = {"errors": sum(r["severity"] == "error" for r in issues),
                         "warnings": sum(r["severity"] == "warning" for r in issues), "total": len(issues)}
        out["issues"] = issues[:MAX_ISSUES]
        out["omitted_issues"] = max(0, len(issues) - MAX_ISSUES)
        out["status"] = "needs_review" if issues else "mechanical_clear"
        out["next"] = ("按定位诊断修改或补查；无法确认就保留边界，不为清零删除缺陷。"
                       "没有诊断也不等于结论属实；正式输出必须与核过的草稿一致，否则此次核查不涵盖新结论。")
        return out

    if not isinstance(draft, str) or not draft.strip() or len(draft) > MAX_CHARS:
        add("draft_size", f"draft 必须是非空 YAML/JSON 文本，最多 {MAX_CHARS} 字符；未执行正文核查。")
        return finish()
    data, errors = parse(draft)
    if errors:
        for error in errors:
            add("schema", error)
        return finish()
    out["document_sha256"] = document_hash(data)
    bound = verdict.build(ledger, data, [], {})
    out["identity_bound"] = bound["identity"]["bound"]
    if not out["identity_bound"]:
        add("identity", bound["identity"]["diag"] or "草稿未绑定本账本")
        return finish()

    def node(n, where):
        if n and not n.get("ok"):
            add("invalid_node", n.get("diag") or "节点无法定位", where, node=n.get("spec"))

    def refs(values, where):
        for i, ref in enumerate(values or []):
            status = ref.get("status")
            if status != "ok":
                add("reference_drift" if status == "drifted" else "invalid_reference",
                    f"{ref.get('ref')}: {status};引用位置可核不代表原文支持断言",
                    f"{where}[{i}]", "warning" if status == "drifted" else "error")

    node(bound.get("root"), "root")
    for d in bound["defects"]:
        prefix = "defect:" + d["id"]
        for i, entry in enumerate(d["entry"]):
            node(entry, prefix + f".entry[{i}]")
        rep = d["repair"]
        for side in ("before", "after"):
            node(rep.get(side), prefix + ".repair." + side)
        refs(rep.get("evidence"), prefix + ".repair.evidence")
        for i, n in enumerate(d["nodes"]):
            at = prefix + f".nodes[{i}]"
            node(n, at)
            refs(n["evidence"], at + ".evidence")
            if n.get("basis"):
                for side in ("expected_evidence", "actual_evidence"):
                    refs(n["basis"][side], at + ".basis." + side)
        target_binding = d.get("target_binding")
        if target_binding and target_binding.get("status") != "matched":
            add("target_scope_unlocated", target_binding.get("diag") or "文件范围未解析；不创建版本或repair",
                prefix + ".target_file", "warning")
        for i, event in enumerate(d.get("event_claims") or []):
            at = prefix + f".event_claims[{i}]"
            binding = event["binding"]
            if binding.get("ok") is not True:
                add("invalid_event", binding.get("diag") or "事件原文不可唯一定位", at + ".event")
            elif binding.get("status") == "drifted":
                add("event_reference_drift", "按原始位置定位到动作，旧#n已漂移；未变更模型事件声明",
                    at + ".event", "warning")
            refs(event["evidence"], at + ".evidence")
            if event.get("basis"):
                for side in ("expected_evidence", "actual_evidence"):
                    refs(event["basis"][side], at + ".basis." + side)
            if event.get("entry") and event["role"] not in ("进入·错", "进入·缺", "无法确认"):
                add("event_entry_role_conflict", "事件进入点与角色声明不一致；不自动改变角色或节点", at, "warning")
        for i, edge in enumerate(d["edges"]):
            if edge.get("implicit"):
                continue  # Automatically adjacent items are not model edge claims.
            if edge["status"] != "true":
                definite = edge.get("claimed") in ("写", "读", "派发")
                add("edge_unconfirmed", edge["note"], prefix + f".edges[{i}]",
                    "error" if definite and edge["status"] in ("false", "not_checked") else "warning")
    for advice in bound["consistency"]["advisories"]:
        add(advice["code"], advice["message"], "defect:" + advice["defect"], "warning", advice.get("node"))
    if chain_payload is not None or "coverage" in data or file is not None:
        root = bound.get("root") or {}
        target = file or (root.get("key") if root.get("kind") == "file" and root.get("ok") else None)
        if chain_payload is None or not target:
            out["coverage"] = {"checked": False, "target": target}
            add("coverage_scope_unknown", "未提供链清单或目标文件，未认证对账；草稿 root 不等于用户任务范围。", severity="warning")
        else:
            manifest = coverage.manifest(ledger, chain_payload, target)
            reconciliation = coverage.reconcile_document(ledger, manifest, data.get("coverage"), data["defects"],
                                                        identity_bound=True, schema=data.get("schema"))
            out["coverage"] = {"checked": True, "target": target, "counts": reconciliation.get("counts"),
                               "accounted": reconciliation.get("complete"), "semantic_checked": False}
            if reconciliation.get("mode") == "manifest_complement":
                out["coverage"].update(mode="manifest_complement",
                    manifest_identity_valid=reconciliation["manifest_identity_valid"],
                    declarations_complete=reconciliation["declarations_complete"])
            if not reconciliation.get("complete"):
                add("coverage_incomplete", "清单仍有未交代或无效项: " + json.dumps(reconciliation.get("counts"), ensure_ascii=False), "coverage")
            for issue in reconciliation.get("errors") or []:
                add("coverage_" + issue["code"], json.dumps(issue, ensure_ascii=False), "coverage")
            for advice in reconciliation.get("advisories") or []:
                add(advice["code"], advice["message"], "coverage", "warning", advice.get("target"))
            # Position-check coverage citations too; this does not validate the reason.
            for i, row in enumerate(coverage.declared_rows(data.get("coverage"), data.get("schema")) or []):
                refs([verdict.resolve_evidence(ledger, ref) for ref in row["evidence"]], f"coverage[{i}].evidence")
    return finish()


def render(ledger: atoms.Ledger, draft: str, chain_payload: dict[str, Any] | None = None,
           file: str | None = None) -> str:
    return json.dumps(evaluate(ledger, draft, chain_payload, file), ensure_ascii=False, separators=(",", ":"))


def final_binding(ledger: atoms.Ledger, calls: list[dict[str, Any]] | None, final_data: Any,
                  *, identity_bound: bool, final_document_sha256: str | None = None) -> dict[str, Any]:
    """Authenticate the last delivered check against its input and final YAML.

    This binds a check event, including its warnings, not a semantic approval.
    Incomplete, truncated or foreign-provider returns cannot certify a draft.
    """
    current_hash = final_document_sha256 or document_hash(final_data)
    rows = []
    draft_chars = returned_chars = 0
    for step, call in enumerate(calls or [], 1):
        if call.get("tool") != "check":
            continue
        draft = (call.get("input") or {}).get("draft")
        text = call.get("text") or ""
        draft_chars += len(draft) if isinstance(draft, str) else 0
        returned_chars += len(text)
        row = {"step": step, "call_id": call.get("call_id") or call.get("id"), "verified": False,
               "status": "unverifiable", "counts": None, "draft_sha256": None, "document_sha256": None}
        rows.append(row)
        provenance = call.get("provenance") or {}
        origin = provenance.get("tool_origin") or {}
        if (not identity_bound or not call.get("has_result") or call.get("is_error")
                or call.get("delivery_truncated") or provenance.get("complete_pair") is not True
                or origin.get("verified") is not True or origin.get("leaf") != "check"
                or provenance.get("origin_unverified") or not isinstance(draft, str) or len(draft) > MAX_CHARS):
            continue
        try:
            result = json.loads(text)
        except (ValueError, TypeError):
            continue
        data, errors = parse(draft)
        raw_hash = hashlib.sha256(draft.encode("utf-8")).hexdigest()
        digest = document_hash(data) if not errors else None
        if (not isinstance(result, dict) or result.get("schema") != SCHEMA
                or result.get("ledger") != atoms.ledger_identity(ledger) or result.get("identity_bound") is not True
                or digest is None or result.get("document_sha256") != digest or result.get("draft_sha256") != raw_hash
                or result.get("semantic_checked") is not False
                or result.get("status") not in ("needs_review", "mechanical_clear")):
            continue
        counts, returned_issues = result.get("counts"), result.get("issues")
        if (not isinstance(counts, dict) or any(type(counts.get(k)) is not int or counts[k] < 0
                                               for k in ("errors", "warnings", "total"))
                or not isinstance(returned_issues, list) or len(returned_issues) > MAX_ISSUES
                or counts["total"] != counts["errors"] + counts["warnings"]
                or result.get("omitted_issues") != counts["total"] - len(returned_issues)
                or result["status"] != ("needs_review" if counts["total"] else "mechanical_clear")):
            continue
        row.update(verified=True, status=result["status"], counts=result.get("counts"),
                   draft_sha256=raw_hash, document_sha256=digest, issues=returned_issues,
                   omitted_issues=result["omitted_issues"], coverage=result.get("coverage"))
    last = rows[-1] if rows else None
    matched = bool(last and last["verified"] and last["document_sha256"] == current_hash)
    status = ("not_checked" if not rows else "invalid_final" if current_hash is None else
              "unverifiable" if not last["verified"] else "matched" if matched else "mismatch")
    return {"status": status, "semantic_checked": False, "checks": rows, "check_calls": len(rows),
            "draft_chars": draft_chars, "returned_chars": returned_chars,
            "final_document_sha256": current_hash, "matched_check": last["step"] if matched else None}
