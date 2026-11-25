"""没有 mark、也没跑过管线 skill 的会话整段一个 Session(stage_signals 第 1 条,2026-11-24 口径)。

此前按会话自己的任务清单(TaskCreate / TaskUpdate)切段(hmigbot-plus fe468482);用户定的统一
口径改为整段一个 Session,任务清单不再切段。管线会话照常按管线 skill 切。
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


def _write(path: Path, recs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


def _dt_like(tmp_path: Path, *, pipeline: bool = False) -> str:
    cwd = str(tmp_path / "harmony")
    attr = "a2h-execute" if pipeline else None
    recs = [_user(_ts(45), "调用 arkts-dt-verifier skill,对本工程执行 TDD 验证", cwd),
            _tool(_ts(45, 25), "sk", "Skill", {"skill": "arkts-dt-verifier"}, attr),
            _result(_ts(45, 26), "sk", "Launching skill")]
    recs += [_tool(_ts(47, 9), "c1", "TaskCreate", {"subject": "Step 1"}, attr),
             _result(_ts(47, 9), "c1", "Task #1 created successfully: Step 1"),
             _tool(_ts(48, 12), "u1", "TaskUpdate", {"taskId": "1", "status": "in_progress"}, attr),
             _tool(_ts(49, 33), "a1", "Agent", {"subagent_type": "general-purpose", "description": "Step 1",
                                                "prompt": "…"}, attr),
             _result(_ts(58), "a1", "done"),
             _tool(_ts(59, 30), "b1", "Bash", {"command": "hvigorw assembleHap"}, attr),
             _result(_ts(59, 50), "b1", "BUILD SUCCESSFUL")]
    path = tmp_path / "projects" / "slug" / f"{SID}.jsonl"
    _write(path, recs)
    return str(path)


def test_task_list_no_longer_splits_a_session_without_pipeline(tmp_path: Path) -> None:
    stages = adapter.extract(_dt_like(tmp_path))["stages"]
    assert [s["stage"] for s in stages] == ["session"]


def test_pipeline_session_with_task_list_keeps_pipeline_stages(tmp_path: Path) -> None:
    keys = [s["stage"] for s in adapter.extract(_dt_like(tmp_path, pipeline=True))["stages"]]
    assert "a2h-execute" in keys and not any(k.startswith("task:") for k in keys)


def test_single_stage_labelled_by_harness_attribution(tmp_path: Path) -> None:
    """没有管线信号但 harness 给记录盖了统一的 skill 归属戳:整段仍是 session,标签用那个戳。"""
    cwd = str(tmp_path / "harmony")
    recs = [_user(_ts(1), "跑 hitest", cwd),
            _tool(_ts(2), "b1", "Bash", {"command": "hdc list targets"}, "arkts-scenario-runner"),
            _result(_ts(3), "b1", "ok")]
    path = tmp_path / "projects" / "slug" / f"{SID}.jsonl"
    _write(path, recs)
    stages = adapter.extract(str(path))["stages"]
    assert [(s["stage"], s["label"]) for s in stages] == [("session", "arkts-scenario-runner")]
