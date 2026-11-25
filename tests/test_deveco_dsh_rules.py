"""DevEco / dsh 按统一口径:管线 skill 切段、管线里的 Workflow 是子段而管线外的按实际结束收尾、
请求数按 assistant 消息行、缓存写入归 cw5、注入文本不算人工输入、重放的消息只记一次。"""

from __future__ import annotations

import json
from pathlib import Path

from migloop.adapters import deveco, dsh

T0 = 1788348600000          # 毫秒


def _msg(mid, role, minute, parts, **info):
    base = {"id": mid, "role": role, "time": {"created": T0 + minute * 60000, "completed": T0 + minute * 60000 + 1000}}
    base.update(info)
    return {"info": base, "parts": parts}


def _tool(name, inp, start_min, end_min, output="ok", status="completed"):
    return {"type": "tool", "tool": name, "callID": "c-%s-%s" % (name, start_min),
            "state": {"status": status, "input": inp, "output": output,
                      "time": {"start": T0 + start_min * 60000, "end": T0 + end_min * 60000}}}


def _tokens(out=10, reasoning=5, write=0):
    return {"input": 100, "output": out, "reasoning": reasoning, "cache": {"read": 50, "write": write}}


def test_deveco_workflows_requests_and_prompts() -> None:
    data = {"info": {"id": "ses_x", "directory": "/w", "model": {"id": "glm-5.3-flash"}}, "messages": [
        _msg("m0", "user", 0, [{"type": "text", "text": "用户执行 `/a2h`"}]),
        _msg("m1", "assistant", 1, [_tool("workflow", {"runName": "probe"}, 1, 2)], tokens=_tokens(write=7)),
        _msg("m2", "assistant", 30, [_tool("skill", {"name": "a2h-execute"}, 30, 30)], tokens=_tokens()),
        _msg("m3", "assistant", 31, [_tool("workflow", {"runName": "wave_1"}, 31, 50)], tokens=_tokens()),
        _msg("m4", "user", 51, [{"type": "text", "text": "<task id=\"t\" state=\"completed\">", "synthetic": True}]),
        _msg("m5", "assistant", 52, [], error={"name": "MessageAbortedError"}),
        _msg("m6", "user", 53, [{"type": "text", "text": "继续"}]),
        _msg("m7", "assistant", 60, [{"type": "text", "text": "done"}], tokens=_tokens()),
    ]}
    trace = deveco._parse(data, storage_root="/nonexistent", child_documents=[])
    stages = [(s["stage"], s["start_ts"][11:16], s["end_ts"][11:16]) for s in trace["stages"]]
    # 管线外的 probe 是顶层段,段尾取它实际结束(2 分);execute 里的 wave_1 是子段
    assert [s[0] for s in stages] == ["setup", "wf:probe", "a2h-execute"]
    assert stages[1][2] == "11:32"
    (child,) = trace["stages"][-1]["children"]
    assert (child["stage"], child["end_ts"][11:16]) == ("wf:wave_1", "12:20")
    bill = trace["billing"]["glm-5.3-flash"]
    # 4 条正常回复 + 1 条中断的回复 = 5 次请求;缓存写入归 cw5;out 含 reasoning、reasoning 另列
    assert (bill["req"], bill["cw5"], bill["cw1h"], bill["out"], bill["reasoning"]) == (5, 7, 0, 60, 20)
    # synthetic 的任务通知不是人工输入;「继续」不开后续轮
    assert [p["text"] for p in trace["prompts"]] == ["用户执行 `/a2h`", "继续"]
    assert trace["totals"]["user_prompts"] == 2


def test_deveco_empty_child_session_is_listed_not_billed() -> None:
    child = {"info": {"id": "ses_c", "title": "[Tasks] probe [failed]", "model": {"id": "model"},
                      "time": {"created": T0 + 60000, "updated": T0 + 60000}}, "messages": []}
    data = {"info": {"id": "ses_x", "directory": "/w", "model": {"id": "glm-5.3-flash"}}, "messages": [
        _msg("m0", "user", 0, [{"type": "text", "text": "go"}]),
        _msg("m1", "assistant", 1, [{"type": "text", "text": "ok"}], tokens=_tokens()),
    ]}
    trace = deveco._parse(data, storage_root="/nonexistent", child_documents=[child])
    assert set(trace["billing"]) == {"glm-5.3-flash"}
    assert trace["totals"]["empty_child_sessions"] == [{"id": "subagent:ses_c", "title": "[Tasks] probe [failed]"}]


def _dsh_log(tmp_path: Path, events: list) -> str:
    p = tmp_path / "proj" / "s1" / "session.v4.jsonl"
    p.parent.mkdir(parents=True)
    rows = [{"type": "session", "version": 4, "id": "s1", "cwd": "/w", "createdAt": 1794566300000}] + events
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(p)


def test_dsh_commands_dedupe_and_cache_write(tmp_path: Path) -> None:
    usage = {"inputTokens": 10, "cacheReadTokens": 20, "cacheWriteTokens": 3, "outputTokens": 4}
    user = {"content": [{"type": "text", "text": "hi"}], "source": {"kind": "user"}, "role": "user", "id": "u1"}
    events = [
        {"type": "command/run", "seq": 1, "time": 1794566306959,
         "data": {"commandId": "cmd-1", "name": "migloop", "args": " help", "source": {"kind": "user"}}},
        {"type": "command/done", "seq": 2, "time": 1794566366959, "data": {"commandId": "cmd-1"}},
        {"type": "user/message", "seq": 3, "time": 1794566400000, "data": user},
        {"type": "user/message", "seq": 4, "time": 1794566400001, "data": user},          # inbox 重放
        {"type": "user/message", "seq": 5, "time": 1794566400002,
         "data": {"content": [{"type": "text", "text": "ctx"}], "source": {"kind": "runtime-context"}, "id": "u2"}},
        {"type": "assistant/attempt", "seq": 6, "time": 1794566401000, "data": {}},
        {"type": "assistant/message", "seq": 7, "time": 1794566402000, "data": {"message": {"id": "a1"}, "usage": usage}},
        {"type": "assistant/message", "seq": 8, "time": 1794566402001, "data": {"message": {"id": "a1"}, "usage": usage}},
    ]
    trace = dsh.extract(_dsh_log(tmp_path, events))
    assert [p["text"] for p in trace["prompts"]] == ["/migloop help", "hi"]
    assert trace["totals"]["user_prompts"] == 2
    bill = next(iter(trace["billing"].values()))
    assert (bill["req"], bill["cw5"], bill["cw1h"]) == (1, 3, 0)
    assert [s["stage"] for s in trace["stages"]] == ["session"]
    assert trace["totals"]["active_ms"] >= 60000          # 命令 run → done 在跑


def test_deveco_active_uses_the_stall_rule() -> None:
    """回合以 stop 收尾到下一条消息之间算停,扣掉子会话自己的忙碌窗口;回合中的静默算忙。"""
    child = {"info": {"id": "ses_c", "title": "worker", "model": {"id": "glm-5.3-flash"},
                      "time": {"created": T0 + 10 * 60000, "updated": T0 + 20 * 60000}},
             "messages": [_msg("c1", "assistant", 10, [], tokens=_tokens(), finish="tool-calls"),
                          {"info": {"id": "c2", "role": "assistant", "finish": "stop", "tokens": _tokens(),
                                    "time": {"created": T0 + 19 * 60000, "completed": T0 + 20 * 60000}}, "parts": []}]}
    data = {"info": {"id": "ses_x", "directory": "/w", "model": {"id": "glm-5.3-flash"}}, "messages": [
        _msg("m0", "user", 0, [{"type": "text", "text": "go"}]),
        {"info": {"id": "m1", "role": "assistant", "finish": "stop", "tokens": _tokens(),
                  "time": {"created": T0 + 60000, "completed": T0 + 5 * 60000}}, "parts": []},   # 1–5 分在跑
        _msg("m2", "user", 30, [{"type": "text", "text": "继续"}]),
        {"info": {"id": "m3", "role": "assistant", "finish": "stop", "tokens": _tokens(),
                  "time": {"created": T0 + 30 * 60000, "completed": T0 + 40 * 60000}}, "parts": []},
    ]}
    trace = deveco._parse(data, storage_root="/nonexistent", child_documents=[child])
    # 0–40 分:5→30 分回合关着(25 分),其中 10→20 分子会话在跑 → 停 15 分,活跃 25 分
    assert trace["totals"]["active_ms"] == 25 * 60000


def test_dsh_active_uses_turn_end_to_next_turn(tmp_path: Path) -> None:
    base = 1794566300000
    events = [
        {"type": "turn/start", "seq": 1, "time": base, "data": {"turn": 1}},
        {"type": "turn/end", "seq": 2, "time": base + 5 * 60000, "data": {"reason": {"kind": "completed"}}},
        {"type": "turn/start", "seq": 3, "time": base + 20 * 60000, "data": {"turn": 2}},
        {"type": "turn/end", "seq": 4, "time": base + 25 * 60000, "data": {"reason": {"kind": "completed"}}},
    ]
    trace = dsh.extract(_dsh_log(tmp_path, events))
    # 0–25 分里 5→20 分回合关着:活跃 10 分
    assert (trace["totals"]["duration_ms"], trace["totals"]["active_ms"]) == (25 * 60000, 10 * 60000)


def test_dsh_command_done_outside_a_turn_closes_it(tmp_path: Path) -> None:
    """只敲了斜杠命令、没有模型回合的会话:command/done 到下一条 command/run 之间算停。"""
    base = 1794566300000
    events = [
        {"type": "command/run", "seq": 1, "time": base, "data": {"commandId": "a", "name": "fixchain", "args": " cards"}},
        {"type": "command/done", "seq": 2, "time": base + 123, "data": {"commandId": "a"}},
        {"type": "command/run", "seq": 3, "time": base + 10 * 60000, "data": {"commandId": "b", "name": "fixchain", "args": " status"}},
        {"type": "command/done", "seq": 4, "time": base + 10 * 60000 + 1, "data": {"commandId": "b"}},
    ]
    trace = dsh.extract(_dsh_log(tmp_path, events))
    assert trace["totals"]["active_ms"] == 124
