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
    assert hook.handle(setup, event()) == {}
    assert not list(Path(setup["runtime"]).rglob("notified.json"))


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
    assert hook.handle(setup, event()) == {}


def test_missing_entry_clear_error_and_disabled_recovery(setup):
    Path(setup["entry"]).unlink()
    assert "入口不可读" in hook.handle(setup, event())["hookSpecificOutput"]["permissionDecisionReason"]
    setup["enabled"] = False
    assert hook.handle(setup, event()) == {}


@pytest.mark.parametrize("command", ["cat spec.md", "rg safearea spec", "git diff --stat", "python --version", "pwd", "Get-Content file.txt"])
def test_read_only_shell_not_paused(command):
    assert not hook.may_write("Bash", {"command": command})


@pytest.mark.parametrize("command", ["python patch.py", "python -c \"open('a','w').write('x')\"", "cat > a <<'EOF'\nx\nEOF", "sed -i 's/a/b/' f", "cp a b", "cd src && mv a b", "Set-Content f x", "git apply changes.patch", "node fix.js"])
def test_common_shell_modifications(command):
    assert hook.may_write("Bash", {"command": command})


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
