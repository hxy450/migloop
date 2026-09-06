"""codex 子代理归约产物缓存 —— 与 claude.py 的 _SUB_CACHE 同款契约。

钉三条(与 tests/web/test_insight1_subcache.py 一一对应):命中与冷解析一致;
文件变化即失效;缓存不被下游回填污染。签名是 (mtime, size),错一个字段就会
静默退化成"永远全量"或"脏数据复用"。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from migloop.adapters import codex


def _rec(idx_ts: int, rtype: str, payload: dict) -> str:
    return json.dumps({"timestamp": f"2026-08-21T01:00:{idx_ts:02d}.000Z",
                       "type": rtype, "payload": payload})


def _mk_rollout(root: Path, upto_output: bool = True) -> Path:
    """session_meta + 一次 exec 调用(+ 可选的 output) + token_count。"""
    tid = "cafe0000-0000-7000-8000-00000000c0de"
    p = root / f"rollout-2026-08-21T01-00-00-{tid}.jsonl"
    lines = [
        _rec(0, "session_meta", {"id": tid, "timestamp": "2026-08-21T01:00:00.000Z",
                                 "cwd": str(root)}),
        _rec(1, "turn_context", {"model": "gpt-5"}),
        _rec(2, "response_item", {"type": "function_call", "name": "exec",
                                  "call_id": "c1",
                                  "arguments": json.dumps({"cmd": ["bash", "-lc", "cat a.txt"]})}),
    ]
    if upto_output:
        lines.append(_rec(3, "response_item", {"type": "function_call_output",
                                               "call_id": "c1",
                                               "output": "hello-a\nline-two"}))
        lines.append(_rec(4, "event_msg", {"type": "token_count", "info": {
            "total_token_usage": {"output_tokens": 42}}}))
        lines.append(_rec(5, "event_msg", {"type": "task_complete"}))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _tree_item(p: Path, parent: str | None = None) -> dict:
    """构造 discover_rollout_tree 的一条 —— 直接喂 _child_product。"""
    meta = codex.session_summary(str(p)) or {}
    return {"path": str(p), "meta": meta, "parent": parent,
            "agent_path": "/root/w1", "nickname": "Tester",
            "agent_role": None, "depth": 1}


def _key(product: dict) -> str:
    e = product["entry"]
    return json.dumps({
        "id": product["id"], "billing": product["billing"],
        "tool_uses": e["tool_uses"], "tool_counts": e["tool_counts"],
        "output_tokens": e["output_tokens"], "status": e["status"],
        "start_ts": e["start_ts"], "end_ts": e["end_ts"], "model": e["model"],
    }, sort_keys=True, default=str)


def test_warm_hit_matches_cold(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, "_CHILD_CACHE", {})
    p = _mk_rollout(tmp_path)
    item = _tree_item(p)
    cold = codex._child_product(item)
    assert codex._CHILD_CACHE, "冷解析后必须入缓存"
    warm = codex._child_product(item)
    assert _key(cold) == _key(warm)


def test_file_change_invalidates(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, "_CHILD_CACHE", {})
    p = _mk_rollout(tmp_path)
    item = _tree_item(p)
    first = codex._child_product(item)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(_rec(6, "response_item", {"type": "function_call", "name": "exec",
                                           "call_id": "c2",
                                           "arguments": json.dumps({"cmd": ["bash", "-lc", "ls"]})}) + "\n")
    os.utime(p, (time.time() + 2, time.time() + 2))
    second = codex._child_product(item)
    assert second["entry"]["tool_uses"] > first["entry"]["tool_uses"], "文件变了必须重解"


def test_cache_not_polluted_by_downstream(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, "_CHILD_CACHE", {})
    p = _mk_rollout(tmp_path)
    item = _tree_item(p)
    first = codex._child_product(item)
    # 下游会往 entry 回填阶段/派发点 —— 不得漏回缓存
    first["entry"]["stage"] = "a2h-execute"
    first["entry"]["seg"] = 42
    first["entry"]["tuid"] = "polluted"
    second = codex._child_product(item)
    assert second["entry"]["stage"] is None
    assert second["entry"]["seg"] is None
    assert second["entry"]["tuid"] is None
