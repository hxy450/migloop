"""Claude Code ≥2.1.322 的 api-request-blob 行不是对话记录。

夹具 tests/fixtures/cc-request-blob:主线 2 次真实工具调用(Agent、Read),子代理 2 次
(Write、Edit);每次请求后 harness 把请求体里的消息再落一行 api-request-blob,content 里
的 tool_use / tool_result 与真实行同 id。按对话读的入口都只能数到真实的那几次。
"""

from __future__ import annotations

import json
import os
import shutil

from migloop.adapters import claude as cc
from migloop.cc_records import is_request_replay
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


def test_live_monitor_skips_blob_rows(tmp_path):
    main = _copy(tmp_path)
    mon = IncrementalSessionMonitor(main, cache_dir=str(tmp_path / "cache"), poll_interval=0.05,
                                    checkpoint_interval=0.01, reset_cache=True)
    mon.poll_once()
    snap = mon.snapshot()
    assert snap["tool_calls"] == 4          # 主线 2 + 子代理 2
    assert snap["tool_counts"] == {"Agent": 1, "Read": 1, "Write": 1, "Edit": 1}


def _stage_session(tmp_path) -> str:
    """管线 spec → plan → execute;请求体快照与一条非对话行带着早先 Skill 调用的副本,
    主线还有一条同 id 的 assistant 重复行(resume 拼接实录形态)。"""
    sid = "b10b0000-0000-4000-8000-0000000000aa"

    def skill(n, kid, name, attr):
        return {"type": "assistant", "uuid": f"a{n}", "timestamp": "2026-11-23T12:%02d:00.000Z" % n,
                "sessionId": sid, "cwd": "C:/fixture/app", "attributionSkill": attr,
                "message": {"id": f"m{n}", "model": "deepseek-flash", "role": "assistant",
                            "usage": {"output_tokens": 1},
                            "content": [{"type": "tool_use", "id": kid, "name": "Skill",
                                         "input": {"skill": name}}]}}

    def result(n, kid, attr):
        return {"type": "user", "uuid": f"u{n}", "timestamp": "2026-11-23T12:%02d:30.000Z" % n,
                "sessionId": sid, "attributionSkill": attr,
                "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": kid,
                                                         "content": "Launching skill"}]}}

    spec_use = skill(1, "k1", "a2h-spec", "a2h-spec")["message"]["content"]
    rows = [
        {"type": "user", "uuid": "u0", "timestamp": "2026-11-23T12:00:00.000Z", "sessionId": sid,
         "cwd": "C:/fixture/app", "promptSource": "typed", "message": {"role": "user", "content": "/a2h-run"}},
        skill(1, "k1", "a2h-spec", "a2h-spec"), result(1, "k1", "a2h-spec"),
        skill(5, "k2", "a2h-plan", "a2h-plan"), result(5, "k2", "a2h-plan"),
        {"type": "api-request-blob", "sessionId": sid, "hash": "h1",
         "message": {"role": "assistant", "content": spec_use}},
        {"type": "progress", "sessionId": sid, "timestamp": "2026-11-23T12:06:00.000Z",
         "message": {"role": "assistant", "content": spec_use}},
        skill(5, "k2", "a2h-plan", "a2h-plan"),            # 同 id 重复行
        skill(9, "k3", "a2h-execute", "a2h-execute"), result(9, "k3", "a2h-execute"),
    ]
    path = tmp_path / f"{sid}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(path)


def test_copies_of_skill_calls_do_not_reopen_stages(tmp_path):
    """副本里的 Skill 调用不能当显式阶段边界(FairEmail 曾被切成 42 段),
    tool_by_id 也不能被副本改指。"""
    trace = cc.extract(_stage_session(tmp_path))
    assert [s["stage"] for s in trace["stages"] if s["stage"] != "setup"] == [
        "a2h-spec", "a2h-plan", "a2h-execute"]
    assert [t["tuid"] for t in trace["tools"]] == ["k1", "k2", "k3"]
    assert all(t["ok"] is True for t in trace["tools"])
    assert sorted(c["call"] for c in trace["audit_tools"]) == ["k1", "k2", "k3"]


def test_live_monitor_counts_each_tool_use_once(tmp_path):
    path = _stage_session(tmp_path)
    mon = IncrementalSessionMonitor(path, cache_dir=str(tmp_path / "cache"), poll_interval=0.05,
                                    checkpoint_interval=0.01, reset_cache=True)
    mon.poll_once()
    snap = mon.snapshot()
    assert snap["tool_calls"] == 3
    assert snap["current_stage"] == "a2h-execute"


def test_request_replay_predicate():
    blob = {"type": "api-request-blob", "sessionId": SID, "hash": "h",
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "tuR", "name": "Read",
                                                          "input": {"file_path": "x"}}]}}
    assert is_request_replay(blob)
    assert not is_request_replay({"type": "assistant", "message": blob["message"]})
    assert not is_request_replay("api-request-blob")
