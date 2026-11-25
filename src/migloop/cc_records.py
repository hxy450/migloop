"""Claude Code 转录里哪些行是对话本身。

Claude Code ≥2.1.322 每发一次模型请求,会把请求体里的消息再落一行
``{"type": "api-request-blob", "hash": ..., "message": {"role": ..., "content": [...]}}``
(由同文件的 ``api-request`` 行按 hash 引用)。它是请求快照:没有 uuid、timestamp,
content 里的 tool_use / tool_result 与真实对话行同 id 重复。按对话读的解析器、收集器
和原始调用索引都必须跳过它,否则工具调用、写入、文本会再算一遍(Cashiro 主线 745 次
调用被算成 863 次,子代理 11,787 次被算成 15,185 次)。
"""

from __future__ import annotations

from typing import Any

#: 不是对话事件、只是请求体快照的记录类型
REQUEST_REPLAY_TYPES = frozenset({"api-request-blob"})


def is_request_replay(record: Any) -> bool:
    """这条记录是请求体快照(不是对话本身)。"""
    return isinstance(record, dict) and record.get("type") in REQUEST_REPLAY_TYPES
