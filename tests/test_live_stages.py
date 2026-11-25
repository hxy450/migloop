"""live 与离线同一套阶段口径:斜杠命令 / 归属戳 / 显式 Skill 都是信号,不足 90 秒不切,
管线阶段里的 Workflow(含 scriptPath 形式)不换外层阶段,管线之后的人工输入进后续轮。"""

from __future__ import annotations

import json
from pathlib import Path

from migloop.live.monitor import IncrementalSessionMonitor, _workflow_name

SID = "11112222-0000-4000-8000-000000000001"


def _ts(m: int, s: int = 0) -> str:
    return f"2026-11-24T10:{m:02d}:{s:02d}.000Z"


def _rec(m: int, rtype: str, content, attr: str | None = None, **kw) -> dict:
    rec = {"type": rtype, "timestamp": _ts(m), "sessionId": SID, "cwd": "/w/h",
           "message": {"role": rtype, "content": content, **({"id": f"m{m}"} if rtype == "assistant" else {})}, **kw}
    if attr:
        rec["attributionSkill"] = attr
    return rec


def _tool(m: int, tid: str, name: str, inp: dict, attr: str | None = None) -> dict:
    return _rec(m, "assistant", [{"type": "tool_use", "id": tid, "name": name, "input": inp}], attr)


def _poll(tmp_path: Path, rows: list[dict]) -> dict:
    p = tmp_path / f"{SID}.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    mon = IncrementalSessionMonitor(str(p), cache_dir=str(tmp_path / "cache"), reset_cache=True)
    mon.poll_once()
    return mon.snapshot()


def test_live_uses_command_names_and_ignores_short_switches(tmp_path: Path) -> None:
    snap = _poll(tmp_path, [
        _rec(0, "user", "<command-message>a2h-spec</command-message>\n<command-name>/a2h-spec</command-name>",
             promptSource="typed"),
        _rec(3, "assistant", [{"type": "text", "text": "spec"}], "a2h-spec-zh"),
        _rec(10, "assistant", [{"type": "text", "text": "peek plan"}], "a2h-plan"),     # 只停 30 秒
        _rec(10, "assistant", [{"type": "text", "text": "x"}]),
        _rec(11, "assistant", [{"type": "text", "text": "back"}], "a2h-spec"),
        _rec(20, "assistant", [{"type": "text", "text": "still spec"}], "a2h-spec"),
    ])
    assert snap["current_stage"] == "a2h-spec"
    assert snap["user_prompts"] == 1
    assert not any(e["text"] == "进入 a2h-plan" for e in snap["events"])


def test_live_workflow_inside_pipeline_keeps_outer_stage_and_human_input_opens_trailing(tmp_path: Path) -> None:
    snap = _poll(tmp_path, [
        _rec(0, "user", "go", promptSource="sdk"),
        _tool(1, "s1", "Skill", {"skill": "migbot:a2h-execute"}),
        _rec(5, "assistant", [{"type": "text", "text": "exec"}], "a2h-execute"),
        _tool(6, "w1", "Workflow", {"scriptPath": "C:/p/.claude/workflows/scripts/impl-units-wf_1a2b.js"}, "a2h-execute"),
        _rec(9, "assistant", [{"type": "text", "text": "exec"}], "a2h-execute"),
    ])
    assert (snap["current_stage"], snap["current_workflow"]) == ("a2h-execute", "impl-units")
    assert (snap["user_prompts"], snap["program_prompts"]) == (0, 1)
    snap = _poll(tmp_path, [
        _tool(1, "s1", "Skill", {"skill": "a2h-execute"}),
        _rec(5, "assistant", [{"type": "text", "text": "exec"}], "a2h-execute"),
        _rec(9, "user", "做完了吗", promptSource="typed"),
        _rec(10, "assistant", [{"type": "text", "text": "done"}]),
    ])
    assert snap["current_stage"] == "follow-up"
    # 「继续」类人工输入不开后续轮
    snap = _poll(tmp_path, [
        _tool(1, "s1", "Skill", {"skill": "a2h-execute"}),
        _rec(5, "assistant", [{"type": "text", "text": "exec"}], "a2h-execute"),
        _rec(9, "user", "继续，resume agent", promptSource="typed"),
        _rec(10, "assistant", [{"type": "text", "text": "ok"}]),
    ])
    assert snap["current_stage"] == "a2h-execute"


def _result(m: int, tid: str, text: str, is_error: bool = False) -> dict:
    return _rec(m, "user", [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": is_error}])


def test_live_marks_close_stages_and_open_after_pipeline(tmp_path: Path) -> None:
    rows = [
        _rec(0, "user", "<command-name>/a2h-init</command-name>", promptSource="typed"),
        _tool(2, "b1", "Bash", {"command": ".migbot/bin/a2h mark-stage a2h-init && validate"}),
        _result(2, "b1", "Exit code 1; mark-stage ok; validate failed", is_error=True),
        _tool(5, "b2", "Bash", {"command": "echo .migbot/bin/a2h mark-stage a2h-plan"}),
        _result(5, "b2", "The user doesn't want to proceed with this tool use.", is_error=True),
    ]
    snap = _poll(tmp_path, rows)
    # init 收尾(回执报错但 mark-stage 回显了);被拒的 plan mark 不算
    assert (snap["current_stage"], snap["marked_stages"]) == ("unmarked", ["a2h-init"])
    rows += [
        _tool(6, "s1", "Skill", {"skill": "a2h-execute"}),
        _rec(7, "user", "做完没", promptSource="typed"),          # 阶段没收尾:不开后续轮
    ]
    snap = _poll(tmp_path, rows)
    assert snap["current_stage"] == "a2h-execute"
    rows += [
        _tool(8, "b3", "Bash", {"command": "a2h-codex mark-stage a2h-execute"}),
        _result(8, "b3", "[a2h-codex] mark-stage: a2h-execute"),
    ]
    assert _poll(tmp_path, rows)["current_stage"] == "after-pipeline"
    rows.append(_rec(12, "user", "继续", promptSource="typed"))
    assert _poll(tmp_path, rows)["current_stage"] == "follow-up"


def test_workflow_name_forms() -> None:
    assert _workflow_name({"script": "export const meta = { name: 'case-selection' }"}) == "case-selection"
    assert _workflow_name({"scriptPath": "a/b/antennapod53-case-selection-wf_121fca26-4ad.js"}) == "antennapod53-case-selection"
    assert _workflow_name({"name": "impl"}) == "impl"
    assert _workflow_name({}) is None


def _stages() -> tuple[dict, "object"]:
    from migloop.stage_signals import LiveStages
    state: dict = {}
    return state, LiveStages(state, lambda *a: None)


def test_live_name_from_signal_moves_to_a_later_unmarked_stage() -> None:
    state, stages = _stages()
    stages.mark("a2h-build", "2026-11-04T07:54:25Z")
    stages.signal("a2h-run", "2026-11-04T07:54:35Z")
    assert state["current_stage"] == "a2h-run"
    stages.signal("a2h-spec", "2026-11-04T07:54:38Z")           # 规范顺序更靠后、还没打 mark
    assert state["current_stage"] == "a2h-spec" and state["stage_history"][-1]["stage"] == "a2h-spec"
    stages.signal("a2h-init", "2026-11-04T08:00:00Z")           # 更靠前的不改
    assert state["current_stage"] == "a2h-spec"


def test_live_human_input_before_execute_does_not_open_follow_up() -> None:
    state, stages = _stages()
    stages.signal("a2h-init", "2026-10-31T10:00:34Z")
    stages.confirm("2026-10-31T10:03:00Z")
    stages.human("yes", "2026-10-31T10:03:19Z")
    assert state["current_stage"] == "a2h-init"
    stages.signal("a2h-execute", "2026-10-31T11:00:00Z")
    stages.confirm("2026-10-31T11:05:00Z")
    stages.human("统计一下用量", "2026-10-31T12:00:00Z")
    assert state["current_stage"] == "follow-up"


def test_live_unmarked_segment_after_an_end_mark_is_renamed_not_split() -> None:
    state, stages = _stages()
    stages.mark("a2h-build", "2026-11-04T07:54:25Z")
    n = len(state["stage_history"])
    assert state["stage_history"][-1]["stage"] == "unmarked"
    stages.signal("a2h-spec", "2026-11-04T07:54:38Z")
    assert len(state["stage_history"]) == n and state["stage_history"][-1]["stage"] == "a2h-spec"
    assert state["stage_history"][-1]["start_ts"] == "2026-11-04T07:54:25Z"   # 段从收尾 mark 起


def test_live_mark_names_the_closed_segment_and_fills_in_a_pending_signal() -> None:
    state, stages = _stages()
    state["tool_calls"] = 2
    stages.signal("a2h-init", "2026-11-04T07:00:00Z")          # 还在 90 秒等待期
    state["tool_calls"] = 5
    stages.mark("a2h-init", "2026-11-04T07:00:40Z")
    hist = state["stage_history"]
    assert [(h["stage"], h["start_ts"], h["tools_at_start"]) for h in hist] == [
        ("a2h-init", "2026-11-04T07:00:00Z", 2), ("unmarked", "2026-11-04T07:00:40Z", 5)]
    stages.signal("a2h-spec", "2026-11-04T07:00:50Z")          # 段内先见下一阶段的信号
    stages.mark("a2h-build", "2026-11-04T07:01:00Z")
    assert [h["stage"] for h in hist] == ["a2h-init", "a2h-build", "unmarked"]   # 被关的段用 mark 的名字


def test_live_segment_counts_are_taken_when_the_signal_is_pending() -> None:
    state, stages = _stages()
    state.update(tool_calls=3, agent_dispatches=1)
    stages.signal("a2h-spec", "2026-11-04T07:00:00Z")
    state.update(tool_calls=9, agent_dispatches=4)                # 90 秒等待期里又跑了工具、派了子代理
    stages.confirm("2026-11-04T07:02:00Z")
    assert (state["stage_history"][-1]["tools_at_start"], state["stage_history"][-1]["agents_at_start"]) == (3, 1)
