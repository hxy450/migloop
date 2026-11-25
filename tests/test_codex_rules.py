"""Codex 按统一口径:注入清单之外 / 改过源码的 skill 读取不算调用、人工与程序下发、里层工具数、停摆。"""

from __future__ import annotations

import json
from pathlib import Path

from migloop.adapters import codex

TID = "01a19167-0000-7000-8000-000000000001"


def _rec(minute: int, rtype: str, payload: dict) -> str:
    return json.dumps({"timestamp": f"2026-10-31T10:{minute:02d}:00.000Z", "type": rtype, "payload": payload})


def _user(minute: int, *texts: str) -> str:
    return _rec(minute, "response_item", {"type": "message", "role": "user",
                                          "content": [{"type": "input_text", "text": t} for t in texts]})


def _exec(minute: int, cid: str, code: str, out: str = "Script completed\nexit_code: 0") -> list[str]:
    return [_rec(minute, "response_item", {"type": "custom_tool_call", "name": "exec", "call_id": cid, "input": code}),
            _rec(minute, "response_item", {"type": "custom_tool_call_output", "call_id": cid, "output": out})]


def _write(tmp_path: Path, lines: list[str], source: str = "vscode") -> str:
    head = [_rec(0, "session_meta", {"id": TID, "session_id": TID, "cwd": str(tmp_path / "w"), "source": source,
                                     "originator": "Codex Desktop", "timestamp": "2026-10-31T10:00:00.000Z"}),
            _rec(0, "turn_context", {"model": "gpt-6.1-sol"}),
            _rec(0, "response_item", {"type": "message", "role": "developer", "content": [{"type": "input_text", "text":
                 "## Skills\n- a2h-spec: spec (file: r9/a2h-spec/SKILL.md)\n- a2h-plan: plan (file: r9/a2h-plan/SKILL.md)"}]})]
    path = tmp_path / "sessions" / f"rollout-2026-10-31T10-00-00-{TID}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(head + lines) + "\n", encoding="utf-8")
    return str(path)


def test_prompt_kinds_and_skill_mentions(tmp_path: Path) -> None:
    trace = codex.extract(_write(tmp_path, [
        _user(1, "# AGENTS.md instructions for /w", "<environment_context><cwd>/w</cwd></environment_context>"),
        _user(1, "[$a2h-spec](/w/.agents/skills/a2h-spec/SKILL.md) "),
        _user(1, "<skill>\n<name>a2h-spec</name>\n<path>/w/.agents/skills/a2h-spec/SKILL.md</path>"),
        _user(3, '<send_user_message_question_reply> [{"answer": "yes"}]'),
        _user(5, "<heartbeat>\n<automation_id>x</automation_id>"),
        _user(9, "<external_codex_apps_open_page>{}</external_codex_apps_open_page>"),
        _user(9, "不迁移 wearos"),
    ]), sessions_root=str(tmp_path / "sessions"))
    kinds = [(p["kind"], p["text"][:12]) for p in trace["prompts"]]
    assert kinds == [("human", "[$a2h-spec]("), ("human", "<send_user_m"), ("program", "<heartbeat> "),
                     ("human", "不迁移 wearos")]
    assert (trace["totals"]["user_prompts"], trace["totals"]["program_prompts"]) == (3, 1)
    # 点 skill 是阶段信号;没有 mark 时最后一个 skill 信号之后的人工输入开后续轮
    assert [s["stage"] for s in trace["stages"]][-2:] == ["a2h-spec", "follow-up"]
    assert codex._driver_session({"source": "exec"}) and not codex._driver_session({"source": "vscode"})


def test_skill_read_outside_injected_list_or_edited_is_not_an_invocation(tmp_path: Path) -> None:
    listed = {"a2h-spec": "r9/a2h-spec/SKILL.md"}
    assert codex._skill_read_counts("a2h-spec", ".agents/skills/a2h-spec/SKILL.md", listed, set(), "/w")
    assert not codex._skill_read_counts("a2h-execute", "~/.claude/skills/a2h-execute/SKILL.md", listed, set(), "/w")
    assert not codex._skill_read_counts("a2h-spec", ".agents/skills/a2h-spec/SKILL.md", listed, {"a2h-spec"}, "/w")
    absolute = {"a2h-spec": "/home/u/.codex/skills/a2h-spec/SKILL.md"}
    assert not codex._skill_read_counts("a2h-spec", "/home/u/.claude/skills/a2h-spec/SKILL.md", absolute, set(), "/w")
    # 开发会话:读的是没注入的 skill 源码 → 整段一个 Session
    trace = codex.extract(_write(tmp_path, [
        _user(1, "look at the skill"),
        *_exec(2, "c1", 'await tools.exec_command({cmd:"cat ~/.claude/skills/a2h-execute/SKILL.md"})'),
        *_exec(9, "c2", 'await tools.exec_command({cmd:"cat ~/.claude/skills/a2h-verify/SKILL.md"})'),
        *_exec(20, "c3", 'await tools.exec_command({cmd:"echo done"})'),
    ]), sessions_root=str(tmp_path / "sessions"))
    assert [s["stage"] for s in trace["stages"]] == ["session"]


def test_inner_tool_count_expands_for_of_over_array_literals() -> None:
    code = ('for (const u of ["a","b","c"]) {\n text(await tools.exec_command({cmd:`x ${u}`}));\n}\n'
            'const r = await tools.write_stdin({});\nfor (const f of files) { await tools.view_image({path:f}); }')
    assert codex._inner_tool_count(code) == 3 + 1 + 1
    assert codex._inner_tool_count('for (const a of [1,2]) for (const b of [1,2,3]) await tools.x({});') == 6
    assert codex._call_tool_count({"name": "exec", "ptype": "function_call", "raw": "{}"}) == 1


def test_marks_inner_counts_and_stalls(tmp_path: Path) -> None:
    trace = codex.extract(_write(tmp_path, [
        _user(1, "/a2h-spec go"),
        *_exec(2, "c1", 'for (const x of ["a","b"]) await tools.exec_command({cmd:"cat r9/skills/a2h-spec/SKILL.md"});'),
        *_exec(10, "c2", 'await tools.exec_command({cmd:".migbot/bin/a2h mark-stage a2h-spec"})'),
        *_exec(11, "c3", 'await tools.exec_command({cmd:".migbot/bin/a2h mark-stage a2h-plan"})',
               out="Script failed\nexit code: 1"),                          # 没跑成,不算
        _rec(12, "event_msg", {"type": "task_complete"}),
        _rec(40, "event_msg", {"type": "task_started"}),
        _user(41, "还在吗"),                                              # 输入比 task_started 晚落盘
        *_exec(42, "c4", 'await tools.exec_command({cmd:"ls"})'),
    ]), sessions_root=str(tmp_path / "sessions"))
    stages = [(s["stage"], s.get("missing_end_mark", False)) for s in trace["stages"]]
    assert stages == [("setup", False), ("a2h-spec", False), ("unmarked", True)]
    assert trace["stages"][-1]["label"] == "未标记（a2h-spec 之后）"
    t = trace["totals"]
    assert (t["tool_calls"], t["tool_calls_outer"]) == (5, 4)
    # 12 分到 40 分回合关闭等人:28 分钟不算活跃
    assert t["active_ms"] == t["duration_ms"] - 28 * 60_000 and t["user_wait_ms"] == 28 * 60_000


def test_spawn_matches_transcript_by_returned_agent_path_and_failed_spawn_is_not_counted(tmp_path: Path) -> None:
    def call(minute: int, cid: str, task: str) -> str:
        return _rec(minute, "response_item", {"type": "function_call", "name": "spawn_agent", "call_id": cid,
                                              "arguments": json.dumps({"task_name": task, "agent_type": "worker",
                                                                       "message": "do " + task})})

    def out(minute: int, cid: str, text: str) -> str:
        return _rec(minute, "response_item", {"type": "function_call_output", "call_id": cid, "output": text})

    main = _write(tmp_path, [_user(1, "go"), call(2, "c1", "a"), out(2, "c1", '{"task_name":"/root/a"}'),
                             call(3, "c2", "b"), out(3, "c2", '{"isError": true, "message": "no slot"}')])
    child = tmp_path / "sessions" / "rollout-child.jsonl"
    meta = {"id": "child-1", "session_id": TID, "cwd": str(tmp_path / "w"), "timestamp": "2026-10-31T10:02:00.000Z",
            "source": {"subagent": {"thread_spawn": {"parent_thread_id": TID, "depth": 1, "agent_path": "/root/a",
                                                     "agent_role": "worker"}}}, "thread_source": "subagent"}
    child.write_text("\n".join([_rec(2, "session_meta", meta), _rec(2, "turn_context", {"model": "gpt-6.1-sol"}),
                                _rec(4, "response_item", {"type": "message", "role": "assistant",
                                                          "content": [{"type": "output_text", "text": "done"}]})]) + "\n",
                     encoding="utf-8")
    trace = codex.extract(main, sessions_root=str(tmp_path / "sessions"))
    assert (trace["totals"]["agent_calls"], trace["totals"]["subagent_transcripts"]) == (1, 1)   # 报错的派发不算
    (agent,) = trace["agents"]
    assert (agent["tuid"], agent["dispatch_ts"]) == ("c1", "2026-10-31T10:02:00.000Z")
    assert agent["prompt_excerpt"] == "do a"                                                       # 派发原话
