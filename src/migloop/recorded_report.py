"""Compare displayed final text to native recording, independently of schema.

This is local provenance checking, not a signature, semantic approval, or proof
against an administrator rewriting every artifact. Cached verdicts are not read.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MAX_RECORDING_BYTES = 64 * 1024 * 1024


def authenticate(run_dir: str, report: str, metadata: dict[str, Any]) -> dict[str, Any]:
    root = Path(run_dir)
    native = root / "transcript.jsonl"
    if not native.exists():
        native = root / "events.jsonl"
    out = {"kind": "native_final_inline", "verified": False, "semantic_checked": False,
           "schema_checked": False, "source": native.name, "line": None,
           "report_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest(),
           "note": "仅核展示正文与本次录制最终文本相同；不是签名或因果正确性证明。"}
    try:
        if native.stat().st_size > MAX_RECORDING_BYTES:
            raise ValueError("原始录制超过核验上限；未猜测最终文本")
        with native.open("rb") as stream:
            content = stream.read(MAX_RECORDING_BYTES + 1)
        if len(content) > MAX_RECORDING_BYTES:
            raise ValueError("原始录制超过核验上限")
        signature = hashlib.sha256(content).hexdigest()
        out["recording_sha256"] = signature
        expected = metadata.get("transcript_sha256") if native.name == "transcript.jsonl" else None
        if expected is not None and expected != signature:
            raise ValueError("录制哈希与运行元数据不一致")
        candidate = None
        completed = False
        for number, line in enumerate(content.decode("utf-8-sig").splitlines(), 1):
            row = json.loads(line)
            if not isinstance(row, dict):
                raise TypeError("原始录制含非对象记录")
            payload = row.get("payload")
            if native.name == "events.jsonl":
                item = row.get("item") or {}
                if row.get("type") == "item.completed" and item.get("type") == "agent_message":
                    candidate = (item.get("text"), number)
                    completed = False
                if row.get("type") == "turn.completed":
                    completed = True
                elif row.get("type") in ("turn.started", "turn.failed"):
                    candidate = None
                    completed = False
                continue
            if row.get("type") == "response_item" and isinstance(payload, dict):
                if payload.get("type") in ("function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output"):
                    candidate, completed = None, False
                if payload.get("type") == "message" and payload.get("role") == "user":
                    candidate, completed = None, False
                if payload.get("type") == "message" and payload.get("role") == "assistant":
                    blocks = payload.get("content")
                    if payload.get("phase") in ("final", "final_answer") and isinstance(blocks, list):
                        texts = [block.get("text") for block in blocks if isinstance(block, dict)
                                 and block.get("type") in ("output_text", "text")]
                        candidate = ("\n".join(texts), number) if texts and all(isinstance(t, str) for t in texts) else (None, number)
                        completed = False
                    else:
                        candidate, completed = None, False
            elif row.get("type") == "event_msg" and isinstance(payload, dict):
                if payload.get("type") in ("task_started", "turn_started", "turn_aborted"):
                    candidate = None
                    completed = False
                elif payload.get("type") == "task_complete":
                    terminal = payload.get("last_agent_message")
                    # Prefer the explicit final response; terminal corroboration
                    # must agree when both native forms are present.
                    if isinstance(terminal, str):
                        if candidate is not None and candidate[0] != terminal:
                            raise ValueError("最终消息与任务完成记录冲突")
                        candidate = candidate or (terminal, number)
                    completed = candidate is not None
            elif row.get("type") == "assistant" and isinstance(row.get("message"), dict):
                message = row["message"]
                blocks = message.get("content")
                if message.get("stop_reason") == "end_turn" and isinstance(blocks, list):
                    texts = [b.get("text") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
                    candidate = ("\n".join(texts), number) if texts and all(isinstance(t, str) for t in texts) else (None, number)
                    completed = True
                else:
                    candidate, completed = None, False
            elif row.get("type") == "user":
                candidate, completed = None, False
        if candidate is None or not completed:
            raise ValueError("没有可核验的本次最终完成文本")
        out["line"] = candidate[1]
        if candidate[0] != report:
            raise ValueError("展示正文与最后一次原始最终回复不一致")
        out["verified"] = True
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
        out["error"] = str(exc)
    return out
