"""Load an inline verdict or an explicit reference to this run's last checked draft.

The reference is a commitment, not storage and not a semantic approval.  A draft
can only be recovered from a complete, authenticated ``check`` call supplied by
the caller.  Invalid references fail closed and never fall back to an earlier
check or silently rewrite canonical JSON into YAML.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from . import atoms, draft_check, verdict


SCHEMA = "migloop-verdict-ref/1"
_KEYS = {"schema", "ledger", "draft_sha256", "document_sha256"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _call_id(call: dict[str, Any]) -> Any:
    return call.get("call_id") or call.get("tool_use_id") or call.get("item_id") or call.get("id")


def _metadata(mode: str, *, status: str, **extra: Any) -> dict[str, Any]:
    return {"schema": "migloop-submission/1", "mode": mode, "status": status,
            "semantic_checked": False, **extra}


def _ref_error(kind: str | None, raw: str | None, errors: list[str], **meta: Any) -> dict[str, Any]:
    return {"found": raw is not None, "kind": kind, "raw": raw, "data": None,
            "errors": errors, "submission": _metadata("checked_draft_ref", status="rejected", **meta)}


def _draft_document(draft: str) -> tuple[str | None, str | None, Any, list[str]]:
    """Return exact document body and its kind without normalizing its bytes."""
    if draft.lstrip().startswith("```"):
        loaded = verdict.load_block(draft)
        return loaded.get("kind"), loaded.get("raw"), loaded.get("data"), list(loaded.get("errors") or [])
    kind = "json" if draft.lstrip().startswith("{") else "yaml"
    data, errors = verdict.parse_block(kind, draft)
    if data is not None and not errors:
        errors = verdict.validate(data)
    return kind, draft, data if not errors else None, list(errors)


def _identity_errors(ledger: atoms.Ledger, ref: dict[str, Any], trace_identity: Any,
                     harness_identity: str | None) -> list[str]:
    current = atoms.ledger_identity(ledger)
    errors: list[str] = []
    if ref.get("ledger") != current:
        errors.append("submission ledger 与当前账本身份不匹配")
    if not isinstance(trace_identity, dict) or trace_identity.get("bound") is not True:
        errors.append("查询轨迹未绑定当前账本")
        return errors
    if trace_identity.get("current") != current or trace_identity.get("match") is False:
        errors.append("查询轨迹的当前账本身份不匹配")
    observed = trace_identity.get("source_identities")
    if isinstance(observed, list) and any(value != current for value in observed):
        errors.append("查询轨迹混入其他账本身份")
    trace_harness = trace_identity.get("harness_identity")
    effective_harness = harness_identity if harness_identity is not None else trace_harness
    if effective_harness != current:
        errors.append("harness 身份缺失或与当前账本不匹配")
    if trace_harness is not None and trace_harness != current:
        errors.append("查询轨迹记录的 harness 身份不匹配")
    return errors


def load_submission(report: str, ledger: atoms.Ledger, calls: list[dict[str, Any]] | None,
                    trace_identity: dict[str, Any] | None,
                    harness_identity: str | None = None) -> dict[str, Any]:
    """Load a legacy inline v1 verdict or a checked-draft reference.

    The returned top-level ``found/kind/raw/data/errors`` fields intentionally
    match :func:`verdict.load_block`.  ``submission`` records provenance and the
    check warnings/errors without changing the submitted document.
    """
    block = verdict.extract_block(report or "")
    if block is None:
        loaded = verdict.load_block(report or "")
        return {**loaded, "submission": _metadata("inline", status="rejected",
                                                   reason="no_verdict_block")}
    ref_kind, ref_raw = block
    candidate, parse_errors = verdict.parse_block(ref_kind, ref_raw)
    ref_attempt = SCHEMA in ref_raw
    if parse_errors:
        if ref_attempt:
            return _ref_error(ref_kind, ref_raw, parse_errors, final_ref_kind=ref_kind,
                              final_ref_raw=ref_raw)
        loaded = verdict.load_block(report or "")
        return {**loaded, "submission": _metadata("inline", status="accepted" if not loaded["errors"] else "rejected")}
    if isinstance(candidate, dict) and candidate.get("schema") == verdict.SCHEMA:
        loaded = verdict.load_block(report or "")
        return {**loaded, "submission": _metadata("inline", status="accepted" if not loaded["errors"] else "rejected")}
    if not isinstance(candidate, dict) or candidate.get("schema") != SCHEMA:
        if ref_attempt:
            return _ref_error(ref_kind, ref_raw,
                              ["migloop-verdict-ref/1 必须是围栏块的顶层对象"],
                              final_ref_kind=ref_kind, final_ref_raw=ref_raw)
        loaded = verdict.load_block(report or "")
        return {**loaded, "submission": _metadata("inline", status="accepted" if not loaded["errors"] else "rejected")}

    extras = sorted(set(candidate) - _KEYS)
    missing = sorted(_KEYS - set(candidate))
    errors: list[str] = []
    if extras:
        errors.append("submission ref 未知键: " + ", ".join(extras))
    if missing:
        errors.append("submission ref 缺少键: " + ", ".join(missing))
    for key in ("draft_sha256", "document_sha256"):
        if not isinstance(candidate.get(key), str) or not _SHA256.fullmatch(candidate[key]):
            errors.append(f"submission ref {key} 必须是 64 位小写 SHA-256")
    if not isinstance(candidate.get("ledger"), str) or not candidate.get("ledger"):
        errors.append("submission ref ledger 必须是非空字符串")
    errors += _identity_errors(ledger, candidate, trace_identity, harness_identity)

    check_rows = [(step, call) for step, call in enumerate(calls or [], 1)
                  if call.get("tool") == "check"]
    if not check_rows:
        errors.append("本次 run 没有可认证的 check 调用")
        return _ref_error(ref_kind, ref_raw, errors, final_ref_kind=ref_kind,
                          final_ref_raw=ref_raw, ref=candidate)
    step, call = check_rows[-1]
    draft = (call.get("input") or {}).get("draft")
    if not isinstance(draft, str):
        errors.append("最后一次 check 没有完整 draft 字符串")
        return _ref_error(ref_kind, ref_raw, errors, final_ref_kind=ref_kind,
                          final_ref_raw=ref_raw, ref=candidate, source_check_step=step)
    draft_kind, raw, data, draft_errors = _draft_document(draft)
    if draft_errors or data is None or raw is None:
        errors += ["最后一次 check draft 无法作为完整 verdict 载入: " + value for value in draft_errors]
        return _ref_error(ref_kind, ref_raw, errors, final_ref_kind=ref_kind,
                          final_ref_raw=ref_raw, ref=candidate, source_check_step=step)

    raw_hash = hashlib.sha256(draft.encode("utf-8")).hexdigest()
    document_hash = draft_check.document_hash(data)
    if candidate.get("draft_sha256") != raw_hash:
        errors.append("submission ref draft_sha256 不匹配最后一次 check 输入")
    if candidate.get("document_sha256") != document_hash:
        errors.append("submission ref document_sha256 不匹配最后一次 check 文档")
    identity_bound = not _identity_errors(ledger, candidate, trace_identity, harness_identity)
    binding = draft_check.final_binding(ledger, calls, data, identity_bound=identity_bound,
                                        final_document_sha256=document_hash)
    last = binding["checks"][-1] if binding.get("checks") else None
    if binding.get("status") != "matched" or binding.get("matched_check") != step or not last or not last.get("verified"):
        errors.append("最后一次 check 未通过完整来源、返回与双哈希认证")
    if errors:
        return _ref_error(ref_kind, ref_raw, errors, final_ref_kind=ref_kind,
                          final_ref_raw=ref_raw, ref=candidate, source_check_step=step,
                          source_check_call_id=_call_id(call), binding=binding)

    return {"found": True, "kind": draft_kind, "raw": raw, "data": data, "errors": [],
            "submission": _metadata(
                "checked_draft_ref", status="accepted", ref=candidate,
                final_ref_kind=ref_kind, final_ref_raw=ref_raw,
                source_check_step=step, source_check_call_id=_call_id(call),
                draft_sha256=raw_hash, document_sha256=document_hash,
                check_status=last.get("status"), check_counts=last.get("counts"),
                check_issues=list(last.get("issues") or []),
                check_omitted_issues=last.get("omitted_issues"), binding=binding)}
