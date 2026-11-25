"""codex 会话的风险点审计 —— 与 CC 会话同一套规则要同样生效(移植自 hmigbot-plus 53c5524d)。

实录(2026-08-31,rollout …da58f87e5737,codex CLI 0.147.0):原始 rollout 里 hvigor
出现 591 次、hdc 284 次、6 条命令非零退出,审计却报「执行阶段未见构建」(error)、
「验证阶段未见模拟器」(warn),脚本失败一条没报。三处原因都在这里钉住:

1. 0.147 起 shell 工具是直接的 ``exec_command`` 调用(参数 ``cmd``),适配器只给
   ``exec`` 包装里的嵌套调用出 shell 行,直接调用的摘要是空串;
2. 输出里的退出码写法是 ``Process exited with code N``,失败判定只认 ``exit code: N``;
3. 审计规则只认 CC 的工具名 ``Bash``。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from migloop.adapters import codex
from migloop.audit import build_audit

if TYPE_CHECKING:
    from pathlib import Path

TID = "01a0583c-5443-7693-8088-da58f87e5737"


def _rec(minute: int, rtype: str, payload: dict) -> str:
    return json.dumps({"timestamp": f"2026-08-31T07:{minute:02d}:00.000Z",
                       "type": rtype, "payload": payload})


def _cmd(minute: int, cid: str, cmd: str, code: int = 0, out: str = "") -> list[str]:
    output = f"Chunk ID: af329d\nWall time: 12.5 seconds\nProcess exited with code {code}\nOutput:\n{out}"
    return [
        _rec(minute, "response_item", {"type": "function_call", "name": "exec_command",
                                       "call_id": cid, "arguments": json.dumps({"cmd": cmd})}),
        _rec(minute, "response_item", {"type": "function_call_output", "call_id": cid,
                                       "output": output}),
    ]


def _rollout(tmp_path: Path, *, build: bool = True, device: bool = True) -> str:
    cwd = str(tmp_path / "harmony")
    lines = [
        _rec(0, "session_meta", {"id": TID, "timestamp": "2026-08-31T07:00:00.000Z",
                                 "cwd": cwd, "cli_version": "0.147.0"}),
        _rec(0, "turn_context", {"model": "gpt-5"}),
    ]
    lines += _cmd(1, "c1", f"cat {cwd}/.agents/skills/a2h-execute/SKILL.md")
    lines += _cmd(5, "c2", f"cd {cwd} && ls entry/src/main/ets")
    if build:
        lines += _cmd(10, "c3", f"cd {cwd} && hvigorw assembleHap --no-daemon")
    lines += _cmd(12, "c4", f"cd {cwd} && python3 tools/lint.py", code=1, out="boom")
    lines += _cmd(20, "c5", f"cat {cwd}/.agents/skills/a2h-verify/SKILL.md")
    if device:
        lines += _cmd(25, "c6", "hdc install entry-default-signed.hap")
        lines += _cmd(26, "c7", "hdc shell aa start -a EntryAbility -b com.x")
        lines += _cmd(27, "c8", "hdc shell snapshot_display -f /data/local/tmp/a.jpeg")
    lines += _cmd(40, "c9", "echo done")
    lines.append(_rec(41, "event_msg", {"type": "task_complete"}))
    path = tmp_path / "sessions" / f"rollout-2026-08-31T07-00-00-{TID}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _trace(tmp_path: Path, **kw: bool) -> dict:
    return codex.extract(_rollout(tmp_path, **kw), sessions_root=str(tmp_path / "sessions"))


def test_direct_exec_command_becomes_a_shell_row(tmp_path: Path) -> None:
    trace = _trace(tmp_path)
    build = next(t for t in trace["tools"] if t["tuid"] == "c3")
    assert "hvigorw assembleHap" in build["brief"]
    assert build["name"] == "PowerShell", "与 exec 包装里抽出的 shell 行同名,下游只认一种"
    assert build["stage"] == "a2h-execute"
    assert build["dur_ms"] == 12500, "「Wall time: 12.5 seconds」带冒号也要认"


def test_nonzero_process_exit_marks_the_row_failed(tmp_path: Path) -> None:
    trace = _trace(tmp_path)
    by = {t["tuid"]: t["ok"] for t in trace["tools"]}
    assert by["c4"] is False
    assert by["c3"] is True


def test_audit_sees_codex_build_device_and_script_failures(tmp_path: Path) -> None:
    rules = {f["rule"]: f for f in build_audit(_trace(tmp_path))["findings"]}
    assert "execute-no-build" not in rules
    assert "verify-no-emulator" not in rules
    assert "verify-no-install" not in rules
    assert "verify-no-screenshot" not in rules
    assert "1 次失败" in rules["script-fail"]["detail"]
    assert rules["script-fail"]["anchor"]["stage"] == "a2h-execute"


def test_audit_still_flags_codex_sessions_that_really_skipped_them(tmp_path: Path) -> None:
    rules = {f["rule"] for f in build_audit(_trace(tmp_path, build=False, device=False))["findings"]}
    assert "execute-no-build" in rules
    assert "verify-no-emulator" in rules
