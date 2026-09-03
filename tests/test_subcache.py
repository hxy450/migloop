"""子代理解析产物缓存 —— 增量 extract 的行为契约。

钉三条:命中结果与冷解析一致;文件变化即失效;缓存不被消费方污染。
签名是 (jsonl mtime/size, meta mtime/size, cwd),错一个字段都会静默
退化成"永远全量"或"脏数据复用"。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from migloop.adapters import claude as cc


def _mk_session(root: Path, sub_tool_calls: int = 2) -> Path:
    """最小 CC 会话:主线派发一个子代理,子代理若干工具调用。"""
    sid = "cafe0000-0000-4000-8000-000000000001"
    main = root / f"{sid}.jsonl"
    ts = "2026-08-20T01:00:{s:02d}.000Z"
    recs = [
        {"type": "user", "timestamp": ts.format(s=0), "cwd": str(root),
         "sessionId": sid, "message": {"content": "start"}},
        {"type": "assistant", "timestamp": ts.format(s=1), "message": {
            "model": "claude-opus-5", "id": "m1",
            "usage": {"output_tokens": 10},
            "content": [{"type": "tool_use", "id": "tu1", "name": "Task",
                          "input": {"prompt": "convert page"}}]}},
    ]
    main.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")

    sub = root / sid / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-x1.meta.json").write_text(json.dumps({
        "agentType": "a2h-migration-worker", "description": "conv-P1",
        "toolUseId": "tu1"}), encoding="utf-8")
    srecs = [{"type": "user", "timestamp": ts.format(s=2),
              "message": {"content": "do the work"}}]
    for i in range(sub_tool_calls):
        srecs.append({"type": "assistant", "timestamp": ts.format(s=3 + i), "message": {
            "model": "claude-opus-5", "id": f"s{i}",
            "usage": {"output_tokens": 5},
            "content": [{"type": "tool_use", "id": f"su{i}", "name": "Read",
                          "input": {"file_path": f"C:/src/F{i}.java"}}]}})
    srecs.append({"type": "assistant", "timestamp": ts.format(s=30), "message": {
        "model": "claude-opus-5", "id": "se", "stop_reason": "end_turn",
        "usage": {"output_tokens": 5}, "content": [{"type": "text", "text": "done"}]}})
    (sub / "agent-x1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in srecs) + "\n", encoding="utf-8")
    return main


def _agent(trace: dict) -> dict:
    assert len(trace["agents"]) == 1
    return trace["agents"][0]


def test_warm_hit_matches_cold_parse(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    main = _mk_session(tmp_path)
    cold = cc.extract(str(main))
    assert cc._SUB_CACHE, "冷解析后必须入缓存"
    warm = cc.extract(str(main))
    a1, a2 = _agent(cold), _agent(warm)
    for k in ("type", "tool_uses", "tool_counts", "status", "output_tokens",
              "prompt_excerpt", "start_ts", "end_ts"):
        assert a1[k] == a2[k], k


def test_subagent_file_change_invalidates(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    main = _mk_session(tmp_path, sub_tool_calls=2)
    first = cc.extract(str(main))
    assert _agent(first)["tool_uses"] == 2

    jl = tmp_path / "cafe0000-0000-4000-8000-000000000001" / "subagents" / "agent-x1.jsonl"
    extra = {"type": "assistant", "timestamp": "2026-08-20T01:00:40.000Z", "message": {
        "model": "claude-opus-5", "id": "s9", "usage": {"output_tokens": 5},
        "content": [{"type": "tool_use", "id": "su9", "name": "Read",
                      "input": {"file_path": "C:/src/F9.java"}}]}}
    prev = jl.stat().st_mtime_ns
    with open(jl, "a", encoding="utf-8") as f:
        f.write(json.dumps(extra) + "\n")
    if jl.stat().st_mtime_ns == prev:  # 粗粒度文件系统兜底
        os.utime(jl, (time.time() + 2, time.time() + 2))

    second = cc.extract(str(main))
    assert _agent(second)["tool_uses"] == 3, "文件变化必须失效重解析"


def test_cache_not_polluted_by_downstream_mutation(tmp_path, monkeypatch):
    """extract 尾部会剥离 _prompt 并回填 stage —— 缓存条目必须与消费方隔离。"""
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    main = _mk_session(tmp_path)
    first = cc.extract(str(main))
    # 消费方肆意改动第一次结果
    _agent(first)["tool_counts"]["Read"] = 999
    _agent(first)["status"] = "vandalized"
    warm = cc.extract(str(main))
    assert _agent(warm)["tool_counts"]["Read"] != 999
    assert _agent(warm)["status"] != "vandalized"
    # 缓存条目自身也不该带下游剥离/回填的痕迹污染后续消费
    (_sig, cached) = next(iter(cc._SUB_CACHE.values()))
    assert "_prompt" in cached, "缓存的是剥离前的纯解析产物"
