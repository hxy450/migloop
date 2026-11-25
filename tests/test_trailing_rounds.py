"""后续轮(stage_signals 第 2 条)与人工 / 程序下发(第 4 条)在 Claude adapter 上的落地。

最后一个管线阶段结束后,从第一条**人工输入**起单独成「后续轮」,不算进最后一个阶段;
SDK / 驱动程序下发的指令(promptSource=sdk,如 loop 的 DEFERRED 门禁回合)不是人工,
不开后续轮。管线中途的人工输入不切。
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


def _prompt(minute: int, text: str, source: str | None = "typed") -> dict:
    rec = {"type": "user", "timestamp": _ts(minute), "sessionId": SID, "cwd": "/w/h",
           "message": {"role": "user", "content": text}}
    if source:
        rec["promptSource"] = source
    return rec


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


def test_human_input_after_the_last_stage_opens_trailing_rounds(tmp_path: Path) -> None:
    trace = _extract(tmp_path, [
        _prompt(0, "运行 /a2h-run"),
        _said(1, 0, "execute", "a2h-execute"), _said(20, 0, "execute done", "a2h-execute"),
        _prompt(26, "帮我看看各阶段耗时"), _said(27, 54, "好的", None),
        _prompt(34, "再导出一份"), _said(34, 7, "导出了", None),
    ])
    stages = {s["label"]: s for s in trace["stages"]}
    assert list(stages)[-2:] == ["Execute", adapter.TRAILING_ROUNDS_LABEL]
    assert stages["Execute"]["end_ts"] == _ts(20)
    trailing = stages[adapter.TRAILING_ROUNDS_LABEL]
    assert (trailing["start_ts"], trailing["end_ts"]) == (_ts(26), _ts(34, 7))
    assert trace["totals"]["user_prompts"] == 3 and trace["totals"]["program_prompts"] == 0


def test_program_issued_rounds_after_the_pipeline_stay_in_the_last_stage(tmp_path: Path) -> None:
    """loop 驱动下发的 DEFERRED 门禁回合是程序下发,不是人工,不开后续轮(2026-11-24 口径)。"""
    trace = _extract(tmp_path, [
        _prompt(0, "运行 /a2h-run", source="sdk"),
        _said(9, 0, "verify", "a2h-verify"), _said(20, 0, "verify done", "a2h-verify"),
        _prompt(26, "以下验证项因设备条件尚未实测,请确认验证环境就绪后继续", source="sdk"),
        _said(27, 54, "按 DEFERRED 完成", None),
    ])
    assert [s["label"] for s in trace["stages"] if s["stage"] != "setup"] == ["Verify"]
    assert trace["totals"]["user_prompts"] == 0 and trace["totals"]["program_prompts"] == 2
    assert {p["kind"] for p in trace["prompts"]} == {"program"}


def test_human_input_mid_pipeline_is_not_split_off(tmp_path: Path) -> None:
    trace = _extract(tmp_path, [
        _prompt(0, "运行 /a2h-run"),
        _said(9, 0, "execute", "a2h-execute"),
        _prompt(10, "继续"), _said(11, 0, "继续 execute", None),
        _said(20, 0, "verify", "a2h-verify"), _said(25, 0, "verify done", "a2h-verify"),
    ])
    assert [s["label"] for s in trace["stages"] if s["stage"] != "setup"] == ["Execute", "Verify"]


def test_old_transcripts_without_prompt_source_are_judged_by_content(tmp_path: Path) -> None:
    """老版本没有 promptSource:人打的文字与斜杠命令算人工,本地命令回显 / 通知不算。"""
    trace = _extract(tmp_path, [
        _prompt(0, "<command-message>a2h-run</command-message>\n<command-name>/a2h-run</command-name>", source=None),
        _prompt(1, "<local-command-stdout>Bye!</local-command-stdout>", source=None),
        _prompt(2, "<task-notification><task-id>x</task-id></task-notification>", source=None),
        _prompt(3, "帮我启动下鸿蒙应用", source=None),
        _said(4, 0, "ok", None),
    ])
    assert [(p["kind"], p["text"]) for p in trace["prompts"]] == [
        ("human", "/a2h-run"), ("human", "帮我启动下鸿蒙应用")]
