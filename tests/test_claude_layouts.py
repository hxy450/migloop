"""Claude adapter:下载包平铺布局的子代理、fork 前缀跨文件去重计费、管线阶段里的 Workflow 子段。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from migloop.adapters import claude as cc

SID = "9a45ec91-0000-4000-8000-000000000001"


def _ts(m: int, s: int = 0) -> str:
    return f"2026-11-04T07:{m:02d}:{s:02d}.000Z"


def _w(path: Path, recs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")


def _asst(m: int, mid: str, blocks: list[dict], out: int = 10, attr: str | None = None, **kw) -> dict:
    rec = {"type": "assistant", "timestamp": _ts(m), "sessionId": SID, "cwd": "/w/h",
           "message": {"id": mid, "model": "glm-5.3", "role": "assistant", "content": blocks,
                       "usage": {"input_tokens": 1, "output_tokens": out}}, **kw}
    if attr:
        rec["attributionSkill"] = attr
    return rec


def _user(m: int, blocks, **kw) -> dict:
    return {"type": "user", "timestamp": _ts(m), "sessionId": SID, "cwd": "/w/h",
            "message": {"role": "user", "content": blocks}, **kw}


def test_flat_download_layout_links_agents_through_dispatch_receipts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    d = tmp_path / "epoch-0" / "sessions"
    agent_use = {"type": "tool_use", "id": "call_1", "name": "Agent",
                 "input": {"subagent_type": "android-analyzer", "description": "分析安卓工程", "prompt": "go"}}
    _w(d / f"main-{SID}.jsonl", [
        _user(0, "/a2h-run"),
        _asst(1, "m1", [agent_use], attr="a2h-spec"),
        _user(2, [{"type": "tool_result", "tool_use_id": "call_1", "content": "Async agent launched"}],
              toolUseResult={"isAsync": True, "status": "async_launched", "agentId": "a01ce41"},
              attributionSkill="a2h-spec"),
        _asst(9, "m2", [{"type": "text", "text": "done"}], attr="a2h-spec"),
    ])
    _w(d / "agent-a01ce41.jsonl", [
        {"type": "user", "timestamp": _ts(2), "sessionId": SID, "agentId": "a01ce41", "isSidechain": True,
         "message": {"role": "user", "content": "go"}},
        {"type": "assistant", "timestamp": _ts(5), "sessionId": SID, "agentId": "a01ce41", "isSidechain": True,
         "message": {"id": "s1", "model": "glm-5.3", "role": "assistant", "stop_reason": "end_turn",
                     "content": [{"type": "text", "text": "ok"}], "usage": {"output_tokens": 7}}},
    ])
    _w(d / "agent-unrelated.jsonl", [{"type": "user", "timestamp": _ts(3), "sessionId": "other",
                                      "message": {"role": "user", "content": "x"}}])
    trace = cc.extract(str(d / f"main-{SID}.jsonl"))
    (agent,) = trace["agents"]
    assert (agent["agent_id"], agent["type"], agent["desc"], agent["tuid"]) == (
        "a01ce41", "android-analyzer", "分析安卓工程", "call_1")
    assert agent["stage"] == "a2h-spec" and agent["output_tokens"] == 7


def test_fork_prefix_copied_into_subagent_is_billed_once(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    task = {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"description": "fork", "prompt": "p"}}
    _w(tmp_path / f"{SID}.jsonl", [_user(0, "go", promptSource="typed"), _asst(1, "m1", [task], out=100),
                                   _user(2, [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}])])
    sub = tmp_path / SID / "subagents"
    (sub).mkdir(parents=True)
    (sub / "agent-f1.meta.json").write_text(json.dumps({"agentType": "fork", "toolUseId": "t1"}), encoding="utf-8")
    _w(sub / "agent-f1.jsonl", [
        _asst(1, "m1", [task], out=100),                       # 抄进来的父会话前缀(同 message.id)
        _asst(3, "f2", [{"type": "text", "text": "fork work"}], out=30, stop_reason="end_turn"),
    ])
    trace = cc.extract(str(tmp_path / f"{SID}.jsonl"))
    assert trace["billing"]["glm-5.3"]["req"] == 2
    assert trace["billing"]["glm-5.3"]["out"] == 130
    assert trace["agents"][0]["output_tokens"] == 30
    again = cc.extract(str(tmp_path / f"{SID}.jsonl"))         # 缓存命中也要记账
    assert again["billing"] == trace["billing"]


def test_workflow_launched_inside_a_pipeline_stage_is_its_child(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    wf_use = {"type": "tool_use", "id": "w1", "name": "Workflow", "input": {"scriptPath": "impl.js"}}
    _w(tmp_path / f"{SID}.jsonl", [
        _user(0, "go", promptSource="typed"),
        _asst(1, "m1", [{"type": "text", "text": "execute"}], attr="a2h-execute"),
        _asst(2, "m2", [wf_use], attr="a2h-execute"),
        _user(3, [{"type": "tool_result", "tool_use_id": "w1", "content": "Task ID: wtask1"}], attributionSkill="a2h-execute"),
        _asst(20, "m3", [{"type": "text", "text": "wf done, continue"}], attr="a2h-execute"),
        _asst(30, "m4", [{"type": "text", "text": "done"}], attr="a2h-execute"),
    ])
    start_ms = int(datetime.fromisoformat("2026-11-04T07:02:00+00:00").timestamp() * 1000)
    wdir = tmp_path / SID / "workflows"
    wdir.mkdir(parents=True)
    (wdir / "wf_r1.json").write_text(json.dumps({
        "runId": "wf_r1", "taskId": "wtask1", "workflowName": "impl", "startTime": start_ms, "durationMs": 10 * 60_000,
        "workflowProgress": [{"type": "workflow_agent", "agentId": "wa1", "label": "unit-1", "state": "done"}]}),
        encoding="utf-8")
    wa = tmp_path / SID / "subagents" / "workflows" / "wf_r1"
    wa.mkdir(parents=True)
    (wa / "agent-wa1.meta.json").write_text(json.dumps({"agentType": "workflow"}), encoding="utf-8")
    _w(wa / "agent-wa1.jsonl", [_asst(4, "x1", [{"type": "text", "text": "unit"}], out=5)])
    trace = cc.extract(str(tmp_path / f"{SID}.jsonl"))
    execute = next(s for s in trace["stages"] if s["stage"] == "a2h-execute")
    assert execute["end_ts"] == _ts(30), "Workflow 不另起顶层段,外层阶段照常延续"
    (child,) = execute["children"]
    assert (child["stage"], child["start_ts"], child["end_ts"]) == ("wf:impl", _ts(2), "2026-11-04T07:12:00.000Z")
    assert child["agent_count"] == 1
    (agent,) = trace["agents"]
    assert (agent["stage"], agent["seg"], agent["subseg"]) == ("a2h-execute", execute["id"], child["id"])


def test_marks_from_executed_calls_and_resumed_agent_is_not_busy_overnight(tmp_path: Path, monkeypatch) -> None:
    """mark 只认回执真跑成了的调用;子代理按自己转录的停摆规则切忙碌窗口(续跑跨过的空档不算忙)。"""
    monkeypatch.setattr(cc, "_SUB_CACHE", {})

    def bash(m, tid, cmd, attr=None):
        return _asst(m, "b" + tid, [{"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": cmd}}], attr=attr)

    def res(m, tid, text, err=False, **kw):
        return _user(m, [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": err}], **kw)

    task = {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"description": "worker", "prompt": "p"}}
    _w(tmp_path / f"{SID}.jsonl", [
        _user(0, "<command-name>/a2h-init</command-name>", promptSource="typed"),
        bash(2, "k1", ".migbot/bin/a2h mark-stage a2h-init && validate"),
        res(2, "k1", "Exit code 1\nmark-stage ok\nvalidate: no device", err=True),
        _asst(3, "m3", [task], attr="a2h-execute"),
        res(3, "t1", "Async agent launched", toolUseResult={"status": "async_launched", "agentId": "w1"}),
        bash(4, "k2", "echo later: .migbot/bin/a2h mark-stage a2h-execute"),
        res(4, "k2", "The user doesn't want to proceed with this tool use.", err=True),
        _asst(50, "m5", [{"type": "text", "text": "done"}], attr="a2h-execute"),
    ])
    sub = tmp_path / SID / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-w1.meta.json").write_text(json.dumps({"agentType": "worker", "toolUseId": "t1"}), encoding="utf-8")
    def stop(rec, reason):
        rec["message"]["stop_reason"] = reason
        return rec

    _w(sub / "agent-w1.jsonl", [
        _user(3, "p"),
        stop(_asst(5, "s1", [{"type": "text", "text": "429"}], out=1, isApiErrorMessage=True), "stop_sequence"),
        _user(45, "resume"),                                   # 40 分钟后被续跑
        stop(_asst(50, "s2", [{"type": "text", "text": "ok"}], out=1), "end_turn"),
    ])
    trace = cc.extract(str(tmp_path / f"{SID}.jsonl"))
    stages = [(s["stage"], s.get("missing_end_mark", False)) for s in trace["stages"]]
    # init 的 mark 回执报错但回显了 mark-stage → 算;被拒的 execute mark 不算 → execute 缺结束标记
    assert stages == [("a2h-init", False), ("a2h-execute", True)]
    assert trace["stages"][1]["label"] == "Execute（缺结束标记）"
    (agent,) = trace["agents"]
    assert agent["busy"] == [[_ts(3), _ts(5)], [_ts(45), _ts(50)]]
