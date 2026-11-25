"""管线走完后的续轮不算进最后一个阶段(移植自 hmigbot-plus 72c56b60、cd6d3d4e)。

只在管线的终点阶段(a2h-retrospect)之后切:单 skill 的能力会话(视觉对比等)只在第一轮盖
skill 归属戳,后续 loop 轮仍在做该 skill 的活(2026-09-23 DiceRoller 视觉对比实测:后续轮
64 次工具调用、visual-fixer / visual-fixer-reviewer 等 6 个子代理,1h18m),不能切成续轮。

阶段按 attributionSkill 切,末段原先一直延到会话最后一条记录。2026-09-21 DiceRoller 实测:
a2h-retrospect 实际 10:20–10:25,之后 loop 又续了 9 轮(每轮一条 DEFERRED 门禁提示、worker
几秒回一句「按 DEFERRED 完成」,记录全无 attributionSkill),Retrospect 被算成 13m30s,
这 9 轮的评审与评估也被标成「Retrospect」。管线中途的续跑轮仍归原阶段,不受影响。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from migloop.adapters import claude as adapter

if TYPE_CHECKING:
    from pathlib import Path

SID = "2e4bd65a-7a58-46da-b9b9-de1e989325e3"


def _ts(minute: int, second: int = 0) -> str:
    return f"2026-09-21T17:{minute:02d}:{second:02d}.000Z"


def _prompt(minute: int, text: str) -> dict:
    return {"type": "user", "timestamp": _ts(minute), "sessionId": SID, "cwd": "/w/h", "promptSource": "sdk",
            "message": {"role": "user", "content": text}}


def _said(minute: int, second: int, text: str, skill: str | None) -> dict:
    rec = {"type": "assistant", "timestamp": _ts(minute, second), "message": {
        "model": "glm-5.3", "id": f"m{minute}-{second}", "usage": {"output_tokens": 5},
        "content": [{"type": "text", "text": text}]}}
    if skill:
        rec["attributionSkill"] = skill
    return rec


def _extract(tmp_path: Path, recs: list[dict]) -> dict:
    path = tmp_path / f"{SID}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    return adapter.extract(str(path))


def test_rounds_after_the_last_stage_get_their_own_segment(tmp_path: Path) -> None:
    trace = _extract(tmp_path, [
        _prompt(0, "运行 /a2h-run"),
        _said(9, 0, "verify", "a2h-verify"), _said(20, 0, "verify done", "a2h-verify"),
        _said(21, 0, "retrospect", "a2h-retrospect"), _said(25, 47, "全流程完成", "a2h-retrospect"),
        _prompt(26, "以下验证项因设备条件尚未实测,请确认验证环境就绪后继续"), _said(27, 54, "按 DEFERRED 完成", None),
        _prompt(34, "以下验证项因设备条件尚未实测,请确认验证环境就绪后继续"), _said(34, 7, "按 DEFERRED 完成", None),
    ])

    stages = {s["label"]: s for s in trace["stages"]}
    assert list(stages)[-2:] == ["Retrospect", adapter.TRAILING_ROUNDS_LABEL]
    assert stages["Retrospect"]["end_ts"] == _ts(25, 47)
    trailing = stages[adapter.TRAILING_ROUNDS_LABEL]
    assert (trailing["start_ts"], trailing["end_ts"]) == (_ts(26), _ts(34, 7))


def test_a_resume_round_that_keeps_working_in_a_stage_stays_in_that_stage(tmp_path: Path) -> None:
    trace = _extract(tmp_path, [
        _prompt(0, "运行 /a2h-run"),
        _said(9, 0, "execute", "a2h-execute"),
        _prompt(10, "reviewer:继续补齐"), _said(11, 0, "继续 execute", "a2h-execute"),
        _said(20, 0, "verify", "a2h-verify"),
    ])

    assert [s["label"] for s in trace["stages"] if s["stage"] != "setup"] == ["Execute", "Verify"]


def test_trailing_rounds_mid_pipeline_without_attribution_are_not_split_off(tmp_path: Path) -> None:
    """只切「最后一个管线阶段之后」的续轮;中途没盖归属戳的续轮照旧留在所在阶段。"""
    trace = _extract(tmp_path, [
        _prompt(0, "运行 /a2h-run"),
        _said(9, 0, "execute", "a2h-execute"),
        _prompt(10, "reviewer:继续"), _said(11, 0, "继续", None),
        _said(20, 0, "verify", "a2h-verify"),
    ])

    assert [s["label"] for s in trace["stages"] if s["stage"] != "setup"] == ["Execute", "Verify"]


def test_later_rounds_of_a_single_skill_session_stay_in_that_skill(tmp_path: Path) -> None:
    trace = _extract(tmp_path, [
        _prompt(0, "调用 arkts-visual-verify skill"),
        _said(1, 0, "visual verify", "arkts-visual-verify"), _said(17, 0, "第一轮完成", "arkts-visual-verify"),
        _prompt(20, "reviewer:继续修复视觉差异"), _said(21, 0, "派 visual-fixer 修复", None),
        _prompt(40, "reviewer:继续"), _said(59, 0, "修复完成", None),
    ])

    stages = [s for s in trace["stages"] if s["stage"] != "setup"]
    assert [s["label"] for s in stages] == ["Visual Verify"]
    assert stages[0]["end_ts"] == _ts(59)
