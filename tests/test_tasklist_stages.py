"""无管线 skill 会话的阶段切分:按会话自己登记的任务清单切(移植自 hmigbot-plus fe468482)。

DT / 视觉等能力会话不调 a2h-* 管线 skill,adapter 只给一段无名 Session
(2026-09-10 DT verify 实测:7 个 TaskCreate、13 个 TaskUpdate、5 个 Agent 全塞在
一段里)。这些会话自己用 TaskCreate 登记了步骤、用 TaskUpdate 开工/收工,
阶段就从这份清单里来,不做任何按名字的能力识别。
"""

from __future__ import annotations

import json
from pathlib import Path

from migloop.adapters import claude as adapter

SID = "012f584d-9fc8-4272-805f-d431f51ed758"


def _ts(minute: int, second: int = 0) -> str:
    return f"2026-09-10T02:{minute:02d}:{second:02d}.000Z"


def _user(ts: str, text: str, cwd: str) -> dict:
    return {"type": "user", "timestamp": ts, "cwd": cwd, "sessionId": SID,
            "message": {"content": text}}


def _tool(ts: str, mid: str, name: str, inp: dict, attribution: str | None = None) -> dict:
    rec = {"type": "assistant", "timestamp": ts, "message": {
        "model": "claude-opus-5", "id": mid, "usage": {"output_tokens": 10},
        "content": [{"type": "tool_use", "id": f"tu-{mid}", "name": name, "input": inp}]}}
    if attribution:
        rec["attributionSkill"] = attribution
    return rec


def _result(ts: str, mid: str, text: str) -> dict:
    return {"type": "user", "timestamp": ts, "message": {"content": [
        {"type": "tool_result", "tool_use_id": f"tu-{mid}", "content": text}]}}


def _create(ts: str, mid: str, n: int, subject: str) -> list[dict]:
    return [_tool(ts, mid, "TaskCreate", {"subject": subject, "description": "…"}),
            _result(ts, mid, f"Task #{n} created successfully: {subject}")]


def _update(ts: str, mid: str, n: int, status: str) -> list[dict]:
    return [_tool(ts, mid, "TaskUpdate", {"taskId": str(n), "status": status}),
            _result(ts, mid, f"Updated task #{n} status")]


def _write(path: Path, recs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


def _dt_like(tmp_path: Path, *, pipeline: bool = False) -> str:
    cwd = str(tmp_path / "harmony")
    attr = "a2h-execute" if pipeline else None
    recs = [_user(_ts(45), "调用 arkts-dt-verifier skill,对本工程执行 TDD 验证", cwd),
            _tool(_ts(45, 25), "sk", "Skill", {"skill": "arkts-dt-verifier"}, attr),
            _result(_ts(45, 26), "sk", "Launching skill")]
    recs += _create(_ts(47, 9), "c1", 1, "Step 1: 派发单元测试 Agent")
    recs += _create(_ts(47, 10), "c2", 2, "Step 2a+2b 并发:测试数据 + ID 注入")
    recs += _create(_ts(47, 11), "c3", 3, "Step 3: 派发 UI 测试 Agent")
    # 1 与 2 紧挨着开工(并发派发),中间没有别的工具调用 → 并成一段
    recs += _update(_ts(48, 12), "u1", 1, "in_progress")
    recs += _update(_ts(48, 13), "u2", 2, "in_progress")
    recs.append(_tool(_ts(49, 33), "a1", "Agent",
                      {"subagent_type": "general-purpose", "description": "Step 1 单元测试生成",
                       "prompt": "…"}, attr))
    recs.append(_result(_ts(58), "a1", "done"))
    recs += _update(_ts(59, 9), "u3", 1, "completed")
    recs += _update(_ts(59, 9), "u4", 2, "completed")
    recs += _update(_ts(59, 10), "u5", 3, "in_progress")
    recs.append(_tool(_ts(59, 30), "b1", "Bash", {"command": "hvigorw assembleHap"}, attr))
    recs.append(_result(_ts(59, 50), "b1", "BUILD SUCCESSFUL"))
    recs += _update(_ts(59, 55), "u6", 3, "completed")
    # 收工后再开一个不在清单里的任务(没有 TaskCreate 回执)
    recs += _update(_ts(59, 58), "u7", 9, "in_progress")
    path = tmp_path / "projects" / "slug" / f"{SID}.jsonl"
    _write(path, recs)
    return str(path)


def test_task_list_splits_generic_session_into_stages(tmp_path: Path) -> None:
    trace = adapter.extract(_dt_like(tmp_path))
    stages = trace["stages"]
    assert [s["label"] for s in stages] == [
        "Setup",
        "Step 1: 派发单元测试 Agent + Step 2a+2b 并发:测试数据 + ID 注入",
        "Step 3: 派发 UI 测试 Agent",
        "task #9",
    ]
    assert all(s["stage"].startswith("task:") for s in stages[1:])
    # 工具归属跟着阶段走:Agent 派发落在 Step 1+2 段,编译落在 Step 3 段
    by_name = {t["name"]: t["stage"] for t in trace["tools"] if t["name"] in ("Agent", "Bash")}
    assert by_name["Agent"] == stages[1]["stage"]
    assert by_name["Bash"] == stages[2]["stage"]
    assert stages[1]["agent_count"] == 0 or stages[1]["tool_counts"].get("Agent") == 1


def test_pipeline_session_with_task_list_keeps_pipeline_stages(tmp_path: Path) -> None:
    """管线会话本来就用任务清单管子任务(主会话 TaskUpdate #21 实测),阶段仍按
    管线 skill 切,任务清单不插手。"""
    trace = adapter.extract(_dt_like(tmp_path, pipeline=True))
    keys = [s["stage"] for s in trace["stages"]]
    assert "a2h-execute" in keys
    assert not any(k.startswith("task:") for k in keys)


def test_session_without_task_list_stays_single_stage(tmp_path: Path) -> None:
    """ECAT 判别器/生成器会话:没有任务清单、没有归属戳 → 仍是一段 session,
    ecat.annotate 的 ECAT 标签覆盖照常生效。"""
    cwd = str(tmp_path / "harmony")
    recs = [_user(_ts(1), "You are the Discriminator", cwd),
            _tool(_ts(2), "a1", "Agent", {"subagent_type": "entropy-judge", "description": "j",
                                          "prompt": "…"}),
            _result(_ts(3), "a1", "ok")]
    path = tmp_path / "projects" / "slug" / f"{SID}.jsonl"
    _write(path, recs)
    stages = adapter.extract(str(path))["stages"]
    assert [(s["stage"], s["label"]) for s in stages] == [("session", "Session")]


def test_single_stage_labelled_by_harness_attribution(tmp_path: Path) -> None:
    """没有任务清单但 harness 给记录盖了统一的 skill 归属戳:整段仍是 session,
    标签用那个戳(会话自己的信息),不再是无名 Session。"""
    cwd = str(tmp_path / "harmony")
    recs = [_user(_ts(1), "跑 hitest", cwd),
            _tool(_ts(2), "b1", "Bash", {"command": "hdc list targets"}, "arkts-scenario-runner"),
            _result(_ts(3), "b1", "ok")]
    path = tmp_path / "projects" / "slug" / f"{SID}.jsonl"
    _write(path, recs)
    stages = adapter.extract(str(path))["stages"]
    assert [(s["stage"], s["label"]) for s in stages] == [("session", "arkts-scenario-runner")]
