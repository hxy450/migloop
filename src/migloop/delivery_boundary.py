"""Model-visible delivery boundaries for recorded tool calls.

Runtime receipts and model-visible output are intentionally separate facts.
"""
from __future__ import annotations

from typing import Any


def derive(call: dict[str, Any] | None) -> dict[str, Any]:
    provenance = call.get("provenance") if isinstance(call, dict) else None
    provenance = provenance if isinstance(provenance, dict) else {}
    fmt = provenance.get("format")
    complete = provenance.get("complete_pair")
    basis = {"format": fmt, "pairing": provenance.get("pairing"),
             "call_id": call.get("call_id") if isinstance(call, dict) else None,
             "item_id": call.get("item_id") if isinstance(call, dict) else None,
             "use_line": call.get("use_line") if isinstance(call, dict) else None,
             "result_line": call.get("result_line") if isinstance(call, dict) else None,
             "full_body_delivery_verified": False,
             "recorded_truncation": bool(call and call.get("delivery_truncated"))}
    if fmt in ("codex_rollout_event", "codex_exec_events"):
        return {"server_returned": bool(call and call.get("has_result")),
                "model_visible": None, "model_output_recorded": False,
                "status": "runtime_only", **basis,
                "reason": "仅服务端/runtime返回；没有明确模型可见输出配对"}
    if fmt in ("codex_rollout", "claude_transcript"):
        visible = bool(complete is True and call and call.get("has_result"))
        return {"server_returned": bool(call and call.get("has_result")),
                "model_visible": True if visible else None, "model_output_recorded": visible,
                "status": "model_output_recorded" if visible else "unverified",
                **basis,
                "reason": "模型输出记录已按原生use/result配对" if visible else "原生use/result配对未核"}
    return {"server_returned": bool(call and call.get("has_result")),
            "model_visible": None, "model_output_recorded": False,
            "status": "unknown", **basis,
            "reason": "旧记录未记录模型可见边界"}


def inherited(parent: dict[str, Any] | None, child: dict[str, Any] | None = None) -> dict[str, Any]:
    """Batch children inherit the parent transport boundary, never improve it."""
    boundary = derive(parent)
    if isinstance(child, dict):
        boundary = dict(boundary)
        boundary["inherited_from_parent"] = True
    return boundary
