"""同一工程的 root 会话:找前后会话用的文件系统事实(会话解析层自用)。

从 crosschain.py 复制而来(collect_claude_project_roots / collect_project_roots / _first_record_ts),
让后续节点(followups)与会话总览(chain)不反过来 import 返修链路模块;返修链路拆出去时
crosschain 整块带走,这里不跟着动。与原函数的差别:首条时间戳跳过 api-request-blob 行。
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any

from .cc_records import is_request_replay


def same_project(cwd_a: str, cwd_b: str) -> bool:
    """两个 cwd 相等或一方是另一方的父目录。"""
    a = cwd_a.replace("\\", "/").rstrip("/").lower()
    b = cwd_b.replace("\\", "/").rstrip("/").lower()
    return bool(a and b) and (a == b or a.startswith(b + "/") or b.startswith(a + "/"))


def first_record_ts(path: str) -> str:
    """首条带 timestamp 的对话记录 —— CC transcript 的会话开始时间。
    文件 mtime 在拷贝/归档后不可靠,时间序一律以内容为准。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as stream:
            for line in stream:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict) or is_request_replay(rec):
                    continue
                ts = rec.get("timestamp")
                if ts:
                    return str(ts)
    except OSError:
        pass
    return ""


def claude_project_roots(cur_path: str, limit: int = 8) -> list[str]:
    """CC 同工程 = 同 transcript 目录(projects/<cwd-slug>/);全部主会话时间序。"""
    d = os.path.dirname(os.path.abspath(cur_path))
    rows = []
    for f in glob.glob(os.path.join(d, "*.jsonl")):
        ts = first_record_ts(f)
        if ts:
            rows.append((ts, os.path.abspath(f)))
    rows.sort()
    return [f for _, f in rows][:limit]


def codex_project_roots(cur_path: str, cur_cwd: str, limit: int = 8) -> list[str]:
    """codex 同工程树的全部主会话(含当前),按 rollout 文件名时间序。子代理 rollout 由
    iter_sessions 排除。"""
    from . import adapters

    codex: Any = adapters.get("codex")
    cur_abs = os.path.abspath(cur_path)
    out = [cur_abs]
    for cand in codex.iter_sessions(codex.default_root()):
        cand_abs = os.path.abspath(cand.path)
        if cand_abs == cur_abs:
            continue
        summary = codex.session_summary(cand.path) or {}
        if same_project(str(summary.get("cwd") or ""), cur_cwd):
            out.append(cand_abs)
    out.sort(key=lambda x: str(os.path.basename(x)))
    return out[:limit]
