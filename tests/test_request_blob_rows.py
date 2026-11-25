"""Claude Code ≥2.1.322 的 api-request-blob 行不是对话记录。

夹具 tests/fixtures/cc-request-blob:主线 2 次真实工具调用(Agent、Read),子代理 2 次
(Write、Edit);每次请求后 harness 把请求体里的消息再落一行 api-request-blob,content 里
的 tool_use / tool_result 与真实行同 id。按对话读的入口都只能数到真实的那几次。
"""

from __future__ import annotations

import os
import shutil

from migloop import atoms_collect, filestory_collect
from migloop.adapters import claude as cc
from migloop.cc_records import is_request_replay
from migloop.inquiry.source_adapters import adapter_for, parts
from migloop.live.monitor import IncrementalSessionMonitor

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cc-request-blob")
SID = "b10b0000-0000-4000-8000-000000000001"


def _copy(tmp_path) -> str:
    dst = tmp_path / "proj"
    shutil.copytree(FIXTURE, dst)
    return str(dst / f"{SID}.jsonl")


def test_fixture_really_carries_blob_rows():
    with open(os.path.join(FIXTURE, f"{SID}.jsonl"), encoding="utf-8") as fh:
        assert sum('"api-request-blob"' in line for line in fh) == 5
    assert all(not is_request_replay(r) for r in cc.load_main_session(os.path.join(FIXTURE, f"{SID}.jsonl")))


def test_extract_counts_only_conversation_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    trace = cc.extract(_copy(tmp_path))
    assert trace["totals"]["tool_calls"] == 2
    assert trace["totals"]["agent_calls"] == 1
    assert [t["name"] for t in trace["tools"]] == ["Agent", "Read"]
    assert all(t["ok"] is True for t in trace["tools"])
    assert len(trace["audit_tools"]) == 2
    (agent,) = trace["agents"]
    assert agent["tool_uses"] == 2
    assert agent["tool_counts"] == {"Write": 1, "Edit": 1}
    assert agent["status"] != "unknown" and not agent.get("aborted")
    # 用量本来就不受影响(blob 行没有 usage):主线 3 次请求 + 子代理 3 次
    assert trace["billing"]["deepseek-flash"]["req"] == 6
    ets = [f for f in trace["lineage"]["files"] if str(f.get("path", "")).endswith("Index.ets")]
    assert ets and ets[0]["writes"] == 2


def test_collectors_skip_blob_rows(tmp_path):
    main = _copy(tmp_path)
    agents = atoms_collect.collect_cc(main, [0])
    sub = next(a for k, a in agents.items() if not k.startswith("__main__"))
    tuids = [act.tuid for act in sub.actions if act.tuid]
    assert sorted(tuids) == ["tuE", "tuW"]
    main_rec = next(a for k, a in agents.items() if k.startswith("__main__"))
    assert sorted(act.tuid for act in main_rec.actions if act.tuid) == ["tuA", "tuR"]

    jl = os.path.join(os.path.dirname(main), SID, "subagents", "agent-s1.jsonl")
    writes = [e for e in filestory_collect._collect_one(jl, "agent-s1", [0]) if e.kind != "read"]
    assert len(writes) == 2


def test_live_monitor_skips_blob_rows(tmp_path):
    main = _copy(tmp_path)
    mon = IncrementalSessionMonitor(main, cache_dir=str(tmp_path / "cache"), poll_interval=0.05,
                                    checkpoint_interval=0.01, reset_cache=True)
    mon.poll_once()
    snap = mon.snapshot()
    assert snap["tool_calls"] == 4          # 主线 2 + 子代理 2
    assert snap["tool_counts"] == {"Agent": 1, "Read": 1, "Write": 1, "Edit": 1}


def test_raw_index_does_not_pair_blob_calls():
    blob = {"type": "api-request-blob", "sessionId": SID, "hash": "h",
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "tuR", "name": "Read",
                                                          "input": {"file_path": "x"}}]}}
    assert is_request_replay(blob)
    assert adapter_for(blob) is None
    assert list(parts(blob)) == []
