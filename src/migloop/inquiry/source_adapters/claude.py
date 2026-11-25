"""Claude Code native JSONL. Request/result block slots remain unchanged."""
from ...cc_records import is_request_replay
from .base import Identity, message_role


class ClaudeAdapter:
    name = "claude"

    def matches(self, record):
        # 请求体快照(api-request-blob)不是对话:它的 tool_use/tool_result 与真实行同 id,
        # 认作 Claude 记录会给每次调用多配一对请求/结果。整行仍按原文入索引。
        if is_request_replay(record):
            return False
        return isinstance(record.get("message"), dict) or bool(record.get("sessionId"))

    def identity(self, record):
        sid = record.get("sessionId")
        if sid:
            return Identity(self.name, str(sid) + ":" + str(record.get("agentId") or "main"), record.get("cwd") or "")

    def input_role(self, record):
        message = dict(record.get("message") or {})
        message.setdefault("role", record.get("type"))
        return message_role(message)

    def parts(self, record):
        blocks = (
            (record.get("message") or {}).get("content")
            if isinstance(record.get("message"), dict)
            else None
        )
        if isinstance(blocks, list):
            for slot, block in enumerate(blocks):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    yield (
                        slot,
                        "cc",
                        "request",
                        block.get("id"),
                        block.get("name", ""),
                        block.get("input"),
                        None,
                    )
                elif block.get("type") == "tool_result":
                    error = block.get("is_error", False)
                    success = int(not error) if isinstance(error, bool) else None
                    metadata = record.get("toolUseResult")
                    child = metadata.get("agentId") if isinstance(metadata, dict) else None
                    yield (
                        slot,
                        "cc",
                        "result",
                        block.get("tool_use_id"),
                        "",
                        {"content": block.get("content"), "native_child_id": child},
                        success,
                    )
