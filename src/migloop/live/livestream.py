"""追加式 JSONL 的 byte-cursor 续读 —— 增量监控的传输层，与记录语义无关。

移植自 hmigbot-plus insight/livestream.py,给 codex 的 ``--live``(live/codexlive.py)用。
它是 ``live/monitor.py`` 流机制的**重写**（不是搬动）：CC 那份原样不动——它的归约语义
（活跃判定、workflow 状态机）是几个版本才校准对的，为了共用六十行读文件代码去重构它，
风险收益倒挂。两份实现的语义必须一致，由 ``tests/test_codex_live.py`` 钉住：

  · 只读新增字节（``seek(offset)``），文件没长直接返回
  · 流式写入的末段常是半条记录 —— 原始字节留存，下轮拼回，不丢不重读
  · 收尾的最后一条常没有末尾换行 —— tail 先试解析，成功即消费
  · 头 128 字节 SHA1 签名 + ``size < offset`` 检测文件被截断/替换 ——
    旧的累计量无法做减法，只能上报 reset 让调用方确定性重放
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TranscriptStream:
    """一个 transcript 文件的读取游标。可从 checkpoint 还原。"""

    path: str
    offset: int = 0
    pending_b64: str = ""
    head_sig: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "offset": self.offset,
            "pending_b64": self.pending_b64,
            "head_sig": self.head_sig,
            "meta": self.meta,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TranscriptStream:
        return cls(
            path=str(data.get("path") or ""),
            offset=int(data.get("offset") or 0),
            pending_b64=str(data.get("pending_b64") or ""),
            head_sig=str(data.get("head_sig") or ""),
            meta=dict(data.get("meta") or {}),
        )

    def _current_head_sig(self) -> str | None:
        """头 128 字节的 SHA1。文件太小时返回 None（还分不出身份）。"""
        try:
            if os.path.getsize(self.path) < 128:
                return None
            with open(self.path, "rb") as f:
                return hashlib.sha1(f.read(128)).hexdigest()
        except OSError:
            return None

    def read_new(self) -> tuple[list[dict[str, Any]], int, bool]:
        """返回 ``(新记录, 新增字节数, 是否需要重放)``。

        需要重放 = 文件被截断或整个替换。此时**不动游标**，由调用方丢弃
        全部状态后从零重来 —— 旧的累计量没法做减法。
        """
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return [], 0, False

        if size < self.offset:
            return [], 0, True
        sig = self._current_head_sig()
        if self.head_sig and sig and sig != self.head_sig:
            return [], 0, True
        if sig and not self.head_sig:
            self.head_sig = sig
        if size == self.offset:
            return [], 0, False

        with open(self.path, "rb") as f:
            f.seek(self.offset)
            fresh = f.read()
        self.offset += len(fresh)

        data = base64.b64decode(self.pending_b64 or "") + fresh
        parts = data.split(b"\n")
        tail = parts.pop()

        records: list[dict[str, Any]] = []
        for raw in parts:
            raw = raw.rstrip(b"\r")
            if not raw.strip():
                continue
            try:
                records.append(json.loads(raw.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        # 收尾的最后一条常没有换行:能解析就当场消费,否则原样留到下轮。
        if tail.strip():
            try:
                records.append(json.loads(tail.decode("utf-8")))
                tail = b""
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        self.pending_b64 = base64.b64encode(tail).decode("ascii") if tail else ""
        return records, len(fresh), False

    def reset(self) -> None:
        """确定性重放前清游标 —— 身份签名也要重取。"""
        self.offset = 0
        self.pending_b64 = ""
        self.head_sig = ""
