"""codex 阶段切分:有 mark-stage 只按 mark 切,spec 期间提前读下游 SKILL.md 不是进入下游阶段。

移植自 hmigbot-plus tests/web/test_insight1_codex_audit.py 后半(82395e6e)。

实录(2026-09-19,rollout 01a0b85d…,Cofi):主线派出 spec 子代理后在 wait_agent 的间隙
读了 a2h-plan / a2h-execute / a2h-verify 的 SKILL.md,读完继续等。适配器把每次读都当成
进入阶段,90 秒去噪拦不住(两段各持续 17、28 分钟),报告成了 Spec → Execute → Verify →
Plan → Execute·2。真实顺序由 `a2h mark-stage <阶段>` 钉死:spec 07:27 才标记完成。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from migloop.adapters import codex

if TYPE_CHECKING:
    from pathlib import Path

TID = "01a0583c-5443-7693-8088-da58f87e5737"


def _rec(minute: int, rtype: str, payload: dict) -> str:
    return json.dumps({"timestamp": f"2026-08-31T07:{minute:02d}:00.000Z",
                       "type": rtype, "payload": payload})


def _cmd(minute: int, cid: str, cmd: str) -> list[str]:
    output = "Chunk ID: af329d\nWall time: 12.5 seconds\nProcess exited with code 0\nOutput:\n"
    return [
        _rec(minute, "response_item", {"type": "function_call", "name": "exec_command",
                                       "call_id": cid, "arguments": json.dumps({"cmd": cmd})}),
        _rec(minute, "response_item", {"type": "function_call_output", "call_id": cid,
                                       "output": output}),
    ]


def _stage_rollout(tmp_path: Path, steps: list[tuple[int, str]]) -> str:
    cwd = str(tmp_path / "harmony")
    lines = [_rec(0, "session_meta", {"id": TID, "timestamp": "2026-08-31T07:00:00.000Z",
                                      "cwd": cwd, "cli_version": "0.147.0"}),
             _rec(0, "turn_context", {"model": "glm-5.3"})]
    for n, (minute, cmd) in enumerate(steps):
        lines += _cmd(minute, f"s{n}", cmd)
    path = tmp_path / "sessions" / f"rollout-2026-08-31T07-00-00-{TID}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _stages(tmp_path: Path, steps: list[tuple[int, str]]) -> list[str]:
    trace = codex.extract(_stage_rollout(tmp_path, steps), sessions_root=str(tmp_path / "sessions"))
    return [s["stage"] for s in trace["stages"] if s["stage"] != "setup"]


def _read(skill: str) -> str:
    return f"cat .agents/skills/{skill}/SKILL.md"


def test_reading_downstream_skills_before_the_stage_is_marked_is_not_a_transition(
        tmp_path: Path) -> None:
    assert _stages(tmp_path, [
        (1, _read("a2h-spec")),
        (11, _read("a2h-plan")), (11, _read("a2h-execute")),          # 等子代理时提前读
        (28, _read("a2h-verify")),
        (55, ".migbot/bin/a2h mark-stage a2h-spec"),
        (56, _read("a2h-plan")),
        (58, ".migbot/bin/a2h mark-stage a2h-plan"),
        (59, _read("a2h-execute")),
    ]) == ["a2h-spec", "a2h-plan", "a2h-execute"]


def test_rework_inside_a_marked_stage_is_not_cut(tmp_path: Path) -> None:
    """有 mark 只按 mark 切:verify 不过回去返工的那段仍在 verify 的 mark 之内,不另切。"""
    assert _stages(tmp_path, [
        (1, _read("a2h-execute")),
        (20, ".migbot/bin/a2h mark-stage a2h-execute"),
        (21, _read("a2h-verify")),
        (30, _read("a2h-execute")),                                    # verify 不过,回去返工
        (45, _read("a2h-verify")),
        (50, ".migbot/bin/a2h mark-stage a2h-verify"),
    ]) == ["a2h-execute", "a2h-verify"]


def test_sessions_without_mark_stage_keep_the_old_behaviour(tmp_path: Path) -> None:
    assert _stages(tmp_path, [
        (1, _read("a2h-spec")), (20, _read("a2h-plan")), (40, _read("a2h-execute")), (50, "echo done"),
    ]) == ["a2h-spec", "a2h-plan", "a2h-execute"]


def test_looking_back_at_an_earlier_skill_does_not_unlock_reading_ahead(tmp_path: Path) -> None:
    """实录(44ac246f):plan 进行中回头翻了 spec,同一条命令顺带读了 verify —— plan 的水位还在后面。

    migloop 把一条命令里同时读几个阶段 skill 当作准备、不当切换(elite 会切回 spec 再回 plan),
    这里只钉住共同的结论:verify 不会因为这次顺带的读冒出来。"""
    assert _stages(tmp_path, [
        (1, _read("a2h-spec")),
        (20, ".migbot/bin/a2h mark-stage a2h-spec"),
        (21, _read("a2h-plan")),
        (24, _read("a2h-spec") + "; " + _read("a2h-verify")),
        (27, _read("a2h-plan")),
        (40, ".migbot/bin/a2h mark-stage a2h-plan"),
        (41, _read("a2h-execute")),
    ]) == ["a2h-spec", "a2h-plan", "a2h-execute"]


def test_single_read_ahead_while_plan_is_open_is_ignored(tmp_path: Path) -> None:
    """单独一条命令提前读 verify(plan 的水位还在后面、之后回到 execute)不切阶段。"""
    assert _stages(tmp_path, [
        (1, _read("a2h-plan")),
        (10, _read("a2h-verify")),
        (20, ".migbot/bin/a2h mark-stage a2h-plan"),
        (21, _read("a2h-execute")),
    ]) == ["a2h-plan", "a2h-execute"]


def test_batched_marks_only_close_the_first_stage(tmp_path: Path) -> None:
    """mark 攒到最后一起打:mark 是权威,后两个阶段长度为零,不再按 skill 信号补回来。"""
    assert _stages(tmp_path, [
        (1, _read("a2h-spec")), (20, _read("a2h-plan")), (40, _read("a2h-execute")),
        (59, ".migbot/bin/a2h mark-stage a2h-spec; .migbot/bin/a2h mark-stage a2h-plan; "
             ".migbot/bin/a2h mark-stage a2h-execute"),
    ]) == ["a2h-spec"]


def test_tail_after_a_late_mark_is_named_by_the_next_unmarked_skill(tmp_path: Path) -> None:
    """spec 的水位迟打(plan 已经开工):mark 之前的 plan 读取不切;mark 之后读到 execute,
    尾段按它命名并标缺结束标记。"""
    trace = codex.extract(_stage_rollout(tmp_path, [
        (1, _read("a2h-spec")), (20, _read("a2h-plan")),
        (25, ".migbot/bin/a2h mark-stage a2h-spec"),
        (40, _read("a2h-execute")),
    ]), sessions_root=str(tmp_path / "sessions"))
    tail = trace["stages"][-1]
    assert [s["stage"] for s in trace["stages"] if s["stage"] != "setup"] == ["a2h-spec", "a2h-execute"]
    assert tail["missing_end_mark"] and tail["label"] == "Execute（缺结束标记）"
