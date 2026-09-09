"""Known file operations do not certify complete effects of a compound shell call."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from migloop import atoms, atoms_collect


BODY = "from pathlib import Path\nPath('/proj/SplashPage.ets').write_text('changed')\n"
WRITE_AND_RUN = "cat > /tmp/patch_mask.py <<'PY'\n" + BODY + "PY\npython3 /tmp/patch_mask.py"


def file_ops(command: str, scripts: dict[str, Any] | None = None) -> tuple[list[Any], dict[str, Any]]:
    return atoms_collect._file_ops("Bash", {"command": command}, "", None, "/proj",
                                   {} if scripts is None else scripts, ts="2026-01-01T00:00:00Z")


def test_script_write_and_unparsed_execution_effects_coexist() -> None:
    parsed, capable, _, _, hints = atoms_collect._shell_analyze(WRITE_AND_RUN, "/proj", {}, success=True)
    assert capable and hints["unknown_scripts"] == ["/tmp/patch_mask.py"]
    assert [(op.op, op.path, op.content) for op in parsed] == [("write", "/tmp/patch_mask.py", BODY)]
    ops, detail = file_ops(WRITE_AND_RUN)
    assert [(op.op, op.path, op.content) for op in ops] == [("write", "/tmp/patch_mask.py", BODY)]
    assert detail["unknown_scripts"] == ["/tmp/patch_mask.py"]
    assert "脚本执行效应未解析" in detail["unresolved"]
    assert detail["write_capable"] is True and not detail.get("touched")


def test_known_read_does_not_hide_unknown_external_script() -> None:
    ops, detail = file_ops("cat /proj/input.md; python3 /tmp/external.py")
    assert [(op.op, op.path) for op in ops] == [("read", "/proj/input.md")]
    assert detail["unknown_scripts"] == ["/tmp/external.py"]
    assert "脚本执行效应未解析" in detail["unresolved"]


def test_unknown_script_without_other_operations_still_reports_uncertainty() -> None:
    ops, detail = file_ops("python3 /tmp/external.py")
    assert ops == [] and detail["unknown_scripts"] == ["/tmp/external.py"]
    assert "脚本执行效应未解析" in detail["unresolved"]


def test_unknown_script_does_not_replace_other_unresolved_command_reason() -> None:
    ops, detail = file_ops("cat $UNRESOLVED_FILE; python3 /tmp/external.py")
    assert ops == [] and "变量路径" in detail["unresolved"]
    assert "脚本执行效应未解析" in detail["unresolved"]


def test_known_script_execution_remains_resolved() -> None:
    ops, detail = file_ops("python3 /tmp/known.py", {"/tmp/known.py": "open('/proj/output.md','w').write('ok')\n"})
    assert [(op.op, op.path, op.content) for op in ops] == [("write", "/proj/output.md", "ok")]
    assert not detail.get("unresolved") and not detail.get("unknown_scripts")


@pytest.mark.parametrize("command,expected", [
    ("cat /proj/input.md", [("read", "/proj/input.md")]),
    ("cat > /tmp/patch_mask.py <<'PY'\n" + BODY + "PY", [("write", "/tmp/patch_mask.py")]),
    ("pwd", []),
])
def test_commands_without_unparsed_script_execution_are_unchanged(command: str, expected: list[tuple[str, str]]) -> None:
    ops, detail = file_ops(command)
    assert [(op.op, op.path) for op in ops] == expected
    assert not detail.get("unresolved") and not detail.get("unknown_scripts")


def test_collection_keeps_uncertainty_without_inventing_target_writer_or_version(tmp_path: Path) -> None:
    root = tmp_path / "11111111-2222-3333-4444-555555555555.jsonl"
    records = [
        {"timestamp": "2026-01-01T00:00:00Z", "cwd": "/proj", "type": "assistant", "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": "write-then-run", "name": "Bash",
                                                "input": {"command": WRITE_AND_RUN}}]}},
        {"timestamp": "2026-01-01T00:00:01Z", "cwd": "/proj", "type": "user", "message": {
            "role": "user", "content": [{"type": "tool_result", "tool_use_id": "write-then-run",
                                           "content": [{"type": "text", "text": "ok"}], "is_error": False}]}},
    ]
    root.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    ledger = atoms.build_ledger(atoms_collect.collect_cc(str(root), seq=[0]))
    actions = [act for agent in ledger.agents.values() for act in agent.actions if act.tool == "Bash"]
    assert len(actions) == 1 and "脚本执行效应未解析" in actions[0].detail["unresolved"]
    assert [(ref.op, ref.path) for ref in actions[0].files] == [("write", "/tmp/patch_mask.py")]
    assert set(ledger.stories) == {"/tmp/patch_mask.py"}
    assert [version.content for version in ledger.stories["/tmp/patch_mask.py"].versions] == [BODY]


def codex_wrapper(*commands: str) -> str:
    return "\n".join("text(await tools.exec_command(" + json.dumps({"cmd": command, "workdir": "/proj"}) + "));"
                     for command in commands)


def codex_ops(js: str, scripts: dict[str, Any] | None = None) -> tuple[list[Any], dict[str, Any], bool]:
    output = "Script completed\nOutput:\n" + json.dumps({"exit_code": 0, "output": ""})
    return atoms_collect._codex_exec_ops(js, output, "/proj", {} if scripts is None else scripts)


def test_codex_known_script_write_and_unknown_execution_match_cc_semantics() -> None:
    ops, detail, ok = codex_ops(codex_wrapper(WRITE_AND_RUN))
    cc_ops, cc_detail = file_ops(WRITE_AND_RUN)
    assert ok and [(op.op, op.path, op.content) for op in ops] == [(op.op, op.path, op.content) for op in cc_ops]
    assert detail["unknown_scripts"] == cc_detail["unknown_scripts"] == ["/tmp/patch_mask.py"]
    assert detail["unresolved"] == cc_detail["unresolved"]
    assert not any(op.path.endswith(".ets") for op in ops)


def test_codex_multiple_shell_calls_keep_known_effects_and_all_unknown_scripts() -> None:
    js = codex_wrapper("cat /proj/input.md", "python3 /tmp/external.py", "python3 /tmp/other.py", "python3 /tmp/external.py")
    ops, detail, ok = codex_ops(js)
    assert ok and [(op.op, op.path) for op in ops] == [("read", "/proj/input.md")]
    assert detail["unknown_scripts"] == ["/tmp/external.py", "/tmp/other.py"]
    assert detail["unresolved"].count("脚本执行效应未解析") == 1


def test_codex_script_only_unknown_and_other_unresolved_reason_both_survive() -> None:
    ops, detail, ok = codex_ops(codex_wrapper("cat $UNRESOLVED_FILE; python3 /tmp/external.py"))
    assert ok and ops == [] and detail["unknown_scripts"] == ["/tmp/external.py"]
    assert "变量路径" in detail["unresolved"] and "脚本执行效应未解析" in detail["unresolved"]


def test_codex_known_script_execution_remains_resolved() -> None:
    scripts = {"/tmp/known.py": "open('/proj/output.md','w').write('ok')\n"}
    ops, detail, ok = codex_ops(codex_wrapper("python3 /tmp/known.py"), scripts)
    assert ok and [(op.op, op.path, op.content) for op in ops] == [("write", "/proj/output.md", "ok")]
    assert not detail.get("unknown_scripts") and not detail.get("unresolved")


@pytest.mark.parametrize("js", [
    'text("The transcript mentions python3 /tmp/external.py but this is not a shell call");',
    codex_wrapper("echo 'python3 /tmp/external.py'"),
    codex_wrapper("cat /tmp/external.py"),
])
def test_codex_script_mentions_are_not_inferred_execution(js: str) -> None:
    ops, detail, ok = codex_ops(js)
    assert ok and not detail.get("unknown_scripts") and not detail.get("unresolved")
    assert not any(op.op != "read" for op in ops)


def test_codex_collection_preserves_unknown_effect_without_target_version(tmp_path: Path) -> None:
    session_id = "11111111-2222-3333-4444-555555555555"
    root = tmp_path / f"rollout-{session_id}.jsonl"
    records = [
        {"timestamp": "2026-01-01T00:00:00Z", "type": "session_meta", "payload": {
            "id": session_id, "session_id": session_id, "cwd": "/proj", "source": "cli"}},
        {"timestamp": "2026-01-01T00:00:01Z", "type": "response_item", "payload": {
            "type": "custom_tool_call", "id": "call-item", "call_id": "wrapper-real-call", "name": "exec",
            "input": codex_wrapper(WRITE_AND_RUN)}},
        {"timestamp": "2026-01-01T00:00:02Z", "type": "response_item", "payload": {
            "type": "custom_tool_call_output", "id": "result-item", "call_id": "wrapper-real-call",
            "output": "Script completed\nOutput:\n" + json.dumps({"exit_code": 0, "output": ""})}},
    ]
    root.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    ledger = atoms.build_ledger(atoms_collect.collect_codex(str(root), seq=[0], sessions_root=str(tmp_path)))
    actions = [act for agent in ledger.agents.values() for act in agent.actions if act.tool == "exec"]
    assert len(actions) == 1 and actions[0].ok and actions[0].tuid == "wrapper-real-call"
    assert actions[0].detail["unknown_scripts"] == ["/tmp/patch_mask.py"]
    assert "脚本执行效应未解析" in actions[0].detail["unresolved"]
    assert [(ref.op, ref.path) for ref in actions[0].files] == [("write", "/tmp/patch_mask.py")]
    assert [version.content for version in ledger.stories["/tmp/patch_mask.py"].versions] == [BODY]
    assert not any(story.versions for path, story in ledger.stories.items() if path != "/tmp/patch_mask.py")
