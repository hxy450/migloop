"""execute-no-build 认子代理的构建回执(对应 hmigbot-plus a960895d 的意图,代码以 migloop 为主)。

cc 资源包 a2h-execute 把门禁编译全派给 hmos-builder / closer / worker 子代理,主线只有 Agent
派发 + 取果;只扫主线命令的规则会把每条正常 cc 线迁移报成「执行阶段未见构建」(#314)。
migloop 的审计引擎(audit_review + audit_events)本来就把主会话与各子代理的调用回执放在一起
看,这里钉住:子代理跑过且返回的构建清掉这条;都没构建仍出项(info「证据不足」);
派发了名叫 hmos-builder 的代理但没有任何构建回执时不放行 —— 代理名字不是构建证据
(与 elite 按类型名兜底的做法刻意不同)。
"""

from __future__ import annotations

import json
from pathlib import Path

from migloop.adapters import claude as cc
from migloop.audit import build_audit

SID = "cafe0000-0000-4000-8000-0000000000b1"


def _ts(s: int) -> str:
    return f"2026-08-20T01:{s // 60:02d}:{s % 60:02d}.000Z"


def _session(root: Path, sub_calls: list[tuple[str, str, str]], agent_type: str = "a2h-closer") -> str:
    """主线 execute 阶段派发一个子代理、自己不构建;子代理跑给定的 (工具, 命令, 结果)。"""
    main = root / f"{SID}.jsonl"
    recs = [
        {"type": "user", "timestamp": _ts(0), "cwd": str(root), "sessionId": SID,
         "message": {"content": "/a2h-run"}},
        {"type": "assistant", "timestamp": _ts(1), "attributionSkill": "a2h-execute", "message": {
            "model": "claude-opus-5", "id": "m1", "usage": {"output_tokens": 10},
            "content": [{"type": "tool_use", "id": "tu1", "name": "Agent",
                          "input": {"subagent_type": agent_type, "description": "gate build",
                                    "prompt": "build it"}}]}},
        {"type": "user", "timestamp": _ts(90), "attributionSkill": "a2h-execute", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu1", "content": "done"}]}},
        {"type": "assistant", "timestamp": _ts(100), "attributionSkill": "a2h-verify", "message": {
            "model": "claude-opus-5", "id": "m2", "usage": {"output_tokens": 5},
            "content": [{"type": "text", "text": "verify"}]}},
    ]
    main.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    sub = root / SID / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-x1.meta.json").write_text(json.dumps({
        "agentType": agent_type, "description": "gate build", "toolUseId": "tu1"}), encoding="utf-8")
    srecs: list[dict] = [{"type": "user", "timestamp": _ts(2), "message": {"content": "build it"}}]
    for i, (name, cmd, out) in enumerate(sub_calls):
        srecs.append({"type": "assistant", "timestamp": _ts(3 + 2 * i), "message": {
            "model": "claude-opus-5", "id": f"s{i}", "usage": {"output_tokens": 5},
            "content": [{"type": "tool_use", "id": f"su{i}", "name": name, "input": {"command": cmd}}]}})
        srecs.append({"type": "user", "timestamp": _ts(4 + 2 * i), "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"su{i}", "content": out}]}})
    srecs.append({"type": "assistant", "timestamp": _ts(80), "message": {
        "model": "claude-opus-5", "id": "se", "stop_reason": "end_turn",
        "usage": {"output_tokens": 5}, "content": [{"type": "text", "text": "done"}]}})
    (sub / "agent-x1.jsonl").write_text("\n".join(json.dumps(r) for r in srecs) + "\n", encoding="utf-8")
    return str(main)


def _check(trace: dict) -> tuple[set[str], dict]:
    result = build_audit(trace)
    status = next(c for c in result["assessments"] if c["rule"] == "execute-no-build")
    return {f["rule"] for f in result["findings"]}, status


def test_subagent_build_receipt_clears_execute_no_build(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    trace = cc.extract(_session(tmp_path, [
        ("Bash", "cd entry && hvigorw assembleHap --no-daemon", "BUILD SUCCESSFUL in 41s"),
        ("PowerShell", ".\\hvigorw.bat assembleHap", "BUILD SUCCESSFUL"),
        ("Bash", "cat build-log.txt", "ok"),
    ]))
    assert "a2h-execute" in {s["stage"] for s in trace["stages"]}
    assert not any(t["name"] in ("Bash", "PowerShell") for t in trace["tools"]), "主线自己没构建"
    rules, status = _check(trace)
    assert "execute-no-build" not in rules
    assert status["status"] == "observed" and status["observed_calls"] == 2
    assert status["build_success_receipts"] == 2


def test_no_build_anywhere_still_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    trace = cc.extract(_session(tmp_path, [("Bash", "cat build-log.txt", "ok"), ("Bash", "ohpm install", "ok")]))
    rules, status = _check(trace)
    assert "execute-no-build" in rules
    assert status["status"] == "unknown"


def test_builder_agent_name_alone_is_not_build_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    trace = cc.extract(_session(tmp_path, [("Bash", "ls entry", "ok")], agent_type="hmos-builder"))
    rules, _ = _check(trace)
    assert "execute-no-build" in rules
    finding = next(f for f in build_audit(trace)["findings"] if f["rule"] == "execute-no-build")
    assert finding["level"] == "info", "证据不足只提示,不报严重"
