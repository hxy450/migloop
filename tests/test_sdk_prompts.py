"""报告的提示词:SDK 起的会话同样要看得到(移植自 hmigbot-plus 72c56b60)。

HMBot 的会话(主迁移、托管 reviewer、ECAT、视觉对比 / 开发者测试)全经 SDK 起,
Claude Code 在 transcript 里记 ``promptSource: "sdk"``;只认 ``"typed"`` 时这些会话
的提示词一条都不进报告(2026-09-22 DiceRoller 实测:主迁移 10 条、reviewer 1 条、
ECAT generator 10 条,报告里全是 0)。抽屉标题是「全文」,正文不能在 400 字处截断。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from migloop.adapters import claude as claude_adapter
from migloop.adapters import codex as codex_adapter

if TYPE_CHECKING:
    from pathlib import Path

SID = "b17e11ab-fad4-4829-8bba-ff32fde5d6e5"
LONG = "# Core task\nYou are the Discriminator in the ECAT adversarial loop (iteration 1). " + "x" * 3000


def _write(path: Path, recs: list[dict]) -> str:
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    return str(path)


def _user(minute: int, content: object, source: str | None) -> dict:
    rec: dict = {"type": "user", "timestamp": f"2026-09-21T10:{minute:02d}:00.000Z", "cwd": "/w/harmony",
                 "sessionId": SID, "entrypoint": "sdk-py", "message": {"role": "user", "content": content}}
    if source is not None:
        rec["promptSource"] = source
    return rec


def _assistant(minute: int) -> dict:
    return {"type": "assistant", "timestamp": f"2026-09-21T10:{minute:02d}:30.000Z", "message": {
        "model": "glm-5.3", "id": f"m{minute}", "usage": {"output_tokens": 5},
        "content": [{"type": "text", "text": "ok"}]}}


def test_sdk_prompts_reach_the_report_in_full(tmp_path: Path) -> None:
    path = _write(tmp_path / f"{SID}.jsonl", [
        _user(0, LONG, "sdk"), _assistant(0),
        _user(1, [{"type": "tool_result", "tool_use_id": "t1", "content": "done"}], None),
        _user(2, "reviewer 反馈:继续补齐 11 处阻塞项", "sdk"), _assistant(2),
    ])

    prompts = claude_adapter.extract(path)["prompts"]

    assert [p["text"][:40] for p in prompts] == [
        " ".join(LONG.split())[:40], "reviewer 反馈:继续补齐 11 处阻塞项"]
    assert prompts[0]["text"] == " ".join(LONG.split()), "抽屉里的「全文」不能截在 400 字"


def test_typed_prompts_still_count(tmp_path: Path) -> None:
    path = _write(tmp_path / f"{SID}.jsonl", [_user(0, "帮我看看构建报错", "typed"), _assistant(0)])

    assert [p["text"] for p in claude_adapter.extract(path)["prompts"]] == ["帮我看看构建报错"]


def test_codex_prompt_text_is_kept_in_full(tmp_path: Path) -> None:
    tid = "01a0c5fe-0414-7d90-a009-c210df253cab"
    recs = [
        {"timestamp": "2026-09-21T10:00:00.000Z", "type": "session_meta",
         "payload": {"id": tid, "cwd": "/w/harmony", "cli_version": "0.147.0",
                     "timestamp": "2026-09-21T10:00:00.000Z"}},
        {"timestamp": "2026-09-21T10:00:00.000Z", "type": "turn_context", "payload": {"model": "glm-5.3"}},
        {"timestamp": "2026-09-21T10:00:01.000Z", "type": "event_msg",
         "payload": {"type": "user_message", "message": LONG}},
        {"timestamp": "2026-09-21T10:00:02.000Z", "type": "event_msg", "payload": {"type": "task_complete"}},
    ]
    path = _write(tmp_path / f"rollout-2026-09-21T10-00-00-{tid}.jsonl", recs)

    prompts = codex_adapter.extract(path)["prompts"]

    assert [p["text"] for p in prompts] == [" ".join(LONG.split())]
