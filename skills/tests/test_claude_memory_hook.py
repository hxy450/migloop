"""Checkpoint identity, resume and installation; no semantic recall claims."""
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "migloop-memory-recall/scripts/claude_hook.py"
spec = importlib.util.spec_from_file_location("claude_memory_hook", SCRIPT)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


@pytest.fixture
def setup(tmp_path):
    entry, skill = tmp_path / "memory/index.md", tmp_path / "SKILL.md"
    entry.parent.mkdir()
    entry.write_text("# memory", encoding="utf-8")
    skill.write_text("# recall", encoding="utf-8")
    return {"entry": str(entry), "skill": str(skill), "runtime": str(tmp_path / "runtime"),
            "memory_revision": "rev1", "enabled": True}


def event(tool="Write", actor="a", name="PreToolUse", **params):
    return {"hook_event_name": name, "session_id": "session1", "agent_id": actor,
            "tool_name": tool, "tool_input": params}


def read_entry(config, actor="a"):
    for key in ("entry", "skill"):
        hook.handle(config, event("Read", actor, "PostToolUse", file_path=config[key]))


def test_deny_then_read_then_resume_without_granting_permissions(setup):
    assert hook.handle(setup, event())["hookSpecificOutput"]["permissionDecision"] == "deny"
    read_entry(setup)
    assert hook.handle(setup, event()) == {}
    assert hook.handle(setup, event("Edit")) == {}
    assert len(list(Path(setup["runtime"]).rglob("notified.json"))) == 1


def test_reads_can_precede_first_write(setup):
    read_entry(setup)
    result = hook.handle(setup, event())
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "无需重复读取" in result["hookSpecificOutput"]["permissionDecisionReason"]
    assert hook.handle(setup, event()) == {}
    assert len(list(Path(setup["runtime"]).rglob("notified.json"))) == 1


def test_actor_and_session_isolation_including_main(setup):
    read_entry(setup)
    for actor in ("b", None):
        assert hook.handle(setup, event(actor=actor))["hookSpecificOutput"]["permissionDecision"] == "deny"
    next_session = event()
    next_session["session_id"] = "session2"
    assert hook.handle(setup, next_session)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_partial_or_failed_read_does_not_unlock(setup):
    for key in ("entry", "skill"):
        hook.handle(setup, event("Read", name="PostToolUse", file_path=setup[key], limit=1))
    assert "hookSpecificOutput" in hook.handle(setup, event())
    failed = event("Read", name="PostToolUse", file_path=setup["entry"])
    failed["tool_response"] = {"is_error": True}
    hook.handle(setup, failed)
    assert not list(Path(setup["runtime"]).rglob("entry-read.json"))


def test_parallel_reads_no_lost_state(setup):
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: read_entry(setup), range(12)))
    assert "hookSpecificOutput" in hook.handle(setup, event())
    assert hook.handle(setup, event()) == {}


def test_missing_entry_clear_error_and_disabled_recovery(setup):
    Path(setup["entry"]).unlink()
    assert "入口不可读" in hook.handle(setup, event())["hookSpecificOutput"]["permissionDecisionReason"]
    setup["enabled"] = False
    assert hook.handle(setup, event()) == {}


@pytest.mark.parametrize("command", ["cat spec.md", "rg safearea spec", "git diff --stat", "python --version", "pwd", "Get-Content file.txt"])
def test_read_only_shell_not_paused(command):
    assert not hook.may_write("Bash", {"command": command})


@pytest.mark.parametrize("command", ["cat > a <<'EOF'\nx\nEOF", "sed -i 's/a/b/' f", "cp a b", "cd src && mv a b", "Set-Content f x", "cat f | tee output.txt", "apply_patch <<'PATCH'\nx\nPATCH"])
def test_common_shell_modifications(command):
    assert hook.may_write("Bash", {"command": command})


STARTUP_CHECKS = [
    r'ls "C:\Users\hongy\projects\transfer-app-jetnews925" 2>/dev/null && echo "---SPEC DIR---" && ls "C:\Users\hongy\projects\transfer-app-jetnews925\spec" 2>/dev/null || echo "no spec dir"',
    r'ls "C:\Users\hongy\projects\transfer-app-jetnews925" 2>/dev/null; echo "---SPEC---"; ls "C:\Users\hongy\projects\transfer-app-jetnews925\spec" 2>/dev/null || echo "no spec dir"; echo "---FINDINGS---"; cat "C:\Users\hongy\projects\transfer-app-jetnews925\spec\.a2h\open-findings.json" 2>/dev/null || echo "no open-findings.json (first round)"',
]


@pytest.mark.parametrize("command", STARTUP_CHECKS + [
    "ls missing 2> /dev/null", "cat spec.md >/dev/null 2>&1",
    'cat spec.md 2>>"/dev/null"', "ls missing 2> '/dev/null'",
    "ls missing &>/dev/null", "ls missing 2>&1",
    'rg "->" entry', 'echo "literal > output.txt"', "echo 'literal >> output.txt'",
])
def test_discard_redirects_and_quoted_text_are_not_project_writes(command):
    assert not hook.may_write("Bash", {"command": command})


@pytest.mark.parametrize("tool,command", [
    ("Bash", "cat spec.md > report.txt 2>/dev/null"),
    ("Bash", "ls missing 2>/dev/null && echo result >> report.txt"),
    ("Bash", "cat spec.md 2>/dev/null > report.txt"),
    ("Bash", 'cat spec.md > "report file.txt"'),
    ("Bash", "cat spec.md >/dev/null.txt"),
    ("Bash", "ls missing 2>/dev/null; cp a b"),
    ("PowerShell", "Get-Content spec.md 2>$null > report.txt"),
    ("PowerShell", "Get-Content spec.md 2>'$null'"),
])
def test_discard_redirect_does_not_hide_a_real_write(tool, command):
    assert hook.may_write(tool, {"command": command})


@pytest.mark.parametrize("command", ["Get-Content missing.txt 2>$null", "Get-ChildItem *> $null"])
def test_powershell_null_discard_is_not_project_write(command):
    assert not hook.may_write("PowerShell", {"command": command})


@pytest.mark.parametrize("tool,command", [
    ("Bash", "python patch.py"), ("Bash", "node fix.js 2>/dev/null"),
    ("Bash", "python -c \"open('a','w').write('x')\""),
    ("Bash", "python export.py --output out.json"),
    ("Bash", "bash script.sh"), ("Bash", "cat patch.py"),
    ("Bash", "ls /opt/node/node.exe"), ("Bash", "mkdir -p src"),
    ("Bash", "touch marker"), ("Bash", "git status"),
    ("Bash", "git apply --check patch.diff"), ("Bash", "cp --help"),
    ("Bash", "echo cp a b"), ("Bash", "rg 'cp|mv|sed -i|>file' ."),
    ("Bash", "echo 'read only'; # cp a b\nls"),
    ("Bash", "cat <<'EOF'\ncp a b\necho x > file\nEOF"),
    ("Bash", "echo 'unterminated > file"),
    ("Bash", "tee /dev/null"), ("Bash", "cat x >/dev/stdout"),
    ("Bash", "sed -n '1,20p' file"), ("Bash", "echo x > $UNKNOWN"),
    ("PowerShell", "Get-Content f 2>$nullFile"),
    ("PowerShell", "Set-Content -Path f -Value x -WhatIf"),
    ("PowerShell", 'Write-Output "Set-Content f x"'),
])
def test_unknown_or_literal_commands_do_not_trigger(tool, command):
    assert not hook.may_write(tool, {"command": command})


@pytest.mark.parametrize("tool,command", [
    ("Bash", "ls 2>/dev/null && cp a b"),
    ("Bash", '"/bin/cp" "a file" "b file"'),
    ("Bash", "cat a | tee -a b"),
    ("Bash", "echo 'cp a b'; sed -i.bak 's/x/y/' file"),
    ("Bash", "python inspect.py > result.json"),
    ("PowerShell", "Get-Content f | Set-Content -Path out.txt"),
    ("PowerShell", "Copy-Item -LiteralPath a -Destination b"),
    ("PowerShell", "Add-Content -Path f -Value x"),
])
def test_explicit_shell_writes_survive_other_read_only_segments(tool, command):
    assert hook.may_write(tool, {"command": command})


@pytest.mark.parametrize("actor,start", [("worker", "SubagentStart"), (None, "UserPromptSubmit")])
def test_two_independent_reminders_with_no_repeat_reads(setup, actor, start):
    result = hook.handle(setup, event(actor=actor, name=start))
    assert result["hookSpecificOutput"]["hookEventName"] == start
    assert "additionalContext" in result["hookSpecificOutput"]
    assert "permissionDecision" not in result["hookSpecificOutput"]
    assert hook.handle(setup, event(actor=actor, name=start)) == {}
    assert not list(Path(setup["runtime"]).rglob("entry-read.json"))
    read_entry(setup, actor)
    reads_before = len(list(Path(setup["runtime"]).rglob("reads/*.json")))
    result = hook.handle(setup, event(actor=actor))
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert hook.handle(setup, event(actor=actor)) == {}
    assert hook.handle(setup, event("Edit", actor)) == {}
    assert len(list(Path(setup["runtime"]).rglob("reads/*.json"))) == reads_before


def test_early_reminder_not_a_fake_read_or_adoption(setup):
    hook.handle(setup, event(name="SubagentStart"))
    for _ in range(2):
        assert "hookSpecificOutput" in hook.handle(setup, event())
    assert not list(Path(setup["runtime"]).rglob("resumed.json"))
    read_entry(setup)
    assert hook.handle(setup, event()) == {}


def test_no_backfilled_start_or_reset_for_existing_actor(setup):
    hook.handle(setup, event())
    read_entry(setup)
    assert hook.handle(setup, event(name="SubagentStart")) == {}
    assert hook.handle(setup, event()) == {}


def test_failed_write_is_not_logged_as_completed(setup):
    hook.handle(setup, event())
    payload = event(name="PostToolUse")
    payload["tool_response"] = {"is_error": True}
    hook.handle(setup, payload)
    assert not list(Path(setup["runtime"]).rglob("first-write-completed.json"))


def test_missing_subagent_identity_does_not_mark_main(setup):
    with pytest.raises(ValueError, match="agent_id"):
        hook.handle(setup, event(actor=None, name="SubagentStart"))
    assert not Path(setup["runtime"]).exists()


@pytest.mark.parametrize("command", STARTUP_CHECKS)
@pytest.mark.parametrize("actor", [None, "worker"])
def test_startup_reads_do_not_consume_the_first_write_checkpoint(setup, command, actor):
    assert hook.handle(setup, event("Bash", actor, command=command)) == {}
    assert hook.handle(setup, event("Bash", actor, "PostToolUse", command=command)) == {}
    assert not list(Path(setup["runtime"]).rglob("*.json"))
    assert hook.handle(setup, event("Write", actor))["hookSpecificOutput"]["permissionDecision"] == "deny"
    read_entry(setup, actor)
    assert hook.handle(setup, event("Write", actor)) == {}
    # Even after notification, successful read-only shell calls aren't logged as writes.
    hook.handle(setup, event("Bash", actor, "PostToolUse", command=command))
    assert not list(Path(setup["runtime"]).rglob("first-write-completed.json"))
    hook.handle(setup, event("Edit", actor, "PostToolUse"))
    assert len(list(Path(setup["runtime"]).rglob("first-write-completed.json"))) == 1


def test_install_preserves_existing_settings_and_validates_bundle(tmp_path):
    project, memory = tmp_path / "工程 with space", tmp_path / "reading"
    (project / ".claude").mkdir(parents=True)
    memory.mkdir()
    (memory / "index.md").write_text("memory", encoding="utf-8")
    manifest = {"card_links": "references_only", "memory_revision": "r1",
                "files": {"index.md": hashlib.sha256(b"memory").hexdigest()}}
    hook.save(memory / "manifest.json", manifest)
    settings = {"permissions": {"deny": ["Bash(rm *)"]}, "hooks": {"Stop": [{"hooks": []}]}}
    hook.save(project / ".claude/settings.local.json", settings)
    result = hook.install(project, memory, sys.executable)
    actual = hook.load(result["settings"])
    assert actual["permissions"] == settings["permissions"]
    assert actual["hooks"]["Stop"] == settings["hooks"]["Stop"]
    assert actual["hooks"]["SubagentStart"][0]["matcher"] == "*"
    assert "UserPromptSubmit" in actual["hooks"]
    assert hook.load(result["settings_backup"]) == settings
    assert "allow" not in json.dumps(actual["hooks"])
    with pytest.raises(ValueError, match="Already installed"):
        hook.install(project, memory, sys.executable)


def test_install_rejects_nonportable_or_corrupt_memory(tmp_path):
    memory = tmp_path / "reading"
    memory.mkdir()
    hook.save(memory / "manifest.json", {"card_links": "local"})
    with pytest.raises(ValueError, match="portable"):
        hook.install(tmp_path, memory, sys.executable)
    hook.save(memory / "manifest.json", {"card_links": "references_only", "files": {"../escape": "bad"}})
    with pytest.raises(ValueError, match="mismatch"):
        hook.install(tmp_path, memory, sys.executable)


def test_update_backups_and_keeps_memory_runtime_config_and_foreign_hooks(tmp_path):
    project, memory = tmp_path / "project", tmp_path / "reading"
    project.mkdir()
    memory.mkdir()
    (memory / "index.md").write_text("memory", encoding="utf-8")
    hook.save(memory / "manifest.json", {"card_links": "references_only", "memory_revision": "r1",
              "files": {"index.md": hashlib.sha256(b"memory").hexdigest()}})
    result = hook.install(project, memory, sys.executable)
    config = hook.load(result["config"])
    config["enabled"] = False
    hook.save(Path(result["config"]), config)
    state = Path(config["runtime"]) / "existing.json"
    hook.save(state, {"keep": True})
    settings = hook.load(result["settings"])
    foreign = {"type": "command", "command": "foreign-validator"}
    settings["hooks"]["PreToolUse"][0]["hooks"].append(foreign)
    settings["autoMemoryEnabled"] = False
    hook.save(Path(result["settings"]), settings)
    old_script = (project / ".claude/hooks/migloop_memory.py").read_bytes()
    updated = hook.install(project, memory, sys.executable, update=True)
    backup = Path(updated["settings_backup"])
    assert (backup / "migloop_memory.py").read_bytes() == old_script
    assert hook.load(backup / "settings.local.json") == settings
    assert hook.load(updated["config"]) == config
    assert hook.load(state) == {"keep": True}
    actual = hook.load(updated["settings"])
    assert actual["autoMemoryEnabled"] is False
    handlers = [h for g in actual["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert foreign in handlers
    assert len(handlers) == 2
    for name in ("SubagentStart", "UserPromptSubmit", "PostToolUse"):
        assert sum(len(g["hooks"]) for g in actual["hooks"][name]) == 1
    with pytest.raises(ValueError, match="preserves"):
        hook.save(memory / "manifest.json", {"card_links": "references_only", "memory_revision": "different", "files": {}})
        hook.install(project, memory, sys.executable, update=True)
