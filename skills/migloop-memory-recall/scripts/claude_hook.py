"""Project-local Claude Code write checkpoint. Standard library, no inquiry kernel.

The checkpoint observes entry reads, not understanding/adoption. It never grants
tool permissions. Shell detection is conservative, not a complete effect parser.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import uuid


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def mark(folder, name, event):
    try:
        save(folder / (name + ".json"), event, exclusive=True)
        return True
    except FileExistsError:
        return False


def may_write(tool, params):
    if tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        return True
    if tool not in {"Bash", "PowerShell"}:
        return False
    command = params.get("command", "")
    # Redirections, common file mutations, and embedded scripting. Reads such as
    # cat/rg/git diff do not trigger. Arbitrary MCP/server-side writes are outside
    # this adapter's scope; a hook is a reminder, not a filesystem security gate.
    if re.search(r"(?<![<>])>{1,2}(?![>&])|\b(sed|perl)\s+[^\n]*-[a-z]*i\b", command):
        return True
    if re.search(r"(?:^|[;&|\n]\s*|\s)(?:cp|mv|rm|mkdir|touch|tee|install|apply_patch|"
                 r"Set-Content|Add-Content|Out-File|New-Item|Copy-Item|Move-Item|Remove-Item)\b", command, re.I):
        return True
    if re.search(r"\bgit\s+(?:apply|checkout|restore|reset|clean|switch|merge|rebase|cherry-pick)\b", command):
        return True
    script = re.search(r"\b(?:python[\d.]*|node|ruby|perl|bash|sh|pwsh|powershell)(?:\.exe)?\b", command, re.I)
    if script and not re.fullmatch(r"[\s\S]*?(?:--version|-V|--help)\s*", command):
        return True
    return False


def deny(message):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
            "permissionDecision": "deny", "permissionDecisionReason": message}}


def handle(config, payload):
    if not config.get("enabled", True):
        return {}
    event_name = payload.get("hook_event_name")
    tool, params = payload.get("tool_name", ""), payload.get("tool_input", {})
    write = may_write(tool, params)
    if event_name == "PreToolUse" and not write:
        return {}
    if event_name not in {"PreToolUse", "PostToolUse"}:
        return {}
    session = payload.get("session_id")
    if not session:
        raise ValueError("Hook input missing session_id")
    # agent_id is present on current Claude subagent tool hooks. Do not use
    # transcript_path as an actor ID: some versions pass the parent's path.
    actor = payload.get("agent_id") or "__main__"
    folder = Path(config["runtime"]) / digest(session) / digest(actor)
    entry, skill = Path(config["entry"]).resolve(), Path(config["skill"]).resolve()
    record = {"at": time.time(), "session_id": session, "agent_id": actor,
              "agent_type": payload.get("agent_type"), "tool": tool,
              "tool_use_id": payload.get("tool_use_id"), "memory_revision": config["memory_revision"]}
    if event_name == "PostToolUse":
        if tool == "Read":
            raw_path = params.get("file_path")
            if not raw_path or payload.get("is_error"):
                return {}
            response = payload.get("tool_response", {})
            if isinstance(response, dict) and response.get("is_error"):
                return {}
            path = Path(raw_path).resolve()
            if path != skill and not path.is_relative_to(entry.parent):
                return {}
            record.update(event="read", path=str(path), offset=params.get("offset"), limit=params.get("limit"))
            # Entry/skill are short: require a full Read to release the write.
            complete = params.get("offset", 1) in (None, 1) and not params.get("limit")
            if complete and path == entry:
                mark(folder, "entry-read", record)
            if complete and path == skill:
                mark(folder, "skill-read", record)
            save(folder / "reads" / (str(time.time_ns()) + "-" + uuid.uuid4().hex[:8] + ".json"), record)
        elif write and (folder / "notified.json").exists():
            mark(folder, "first-write-completed", dict(record, event="write_completed"))
        return {}

    if not entry.is_file() or not skill.is_file():
        mark(folder, "unavailable", dict(record, event="memory_unavailable"))
        return deny(f"迁移经验入口不可读，请检查 {entry} 和 {skill}。尚未执行本次修改；"
                    "若维护者决定停用召回，可将 .claude/migloop-memory.json 的 enabled 改为 false。")
    if (folder / "entry-read.json").exists() and (folder / "skill-read.json").exists():
        mark(folder, "resumed", dict(record, event="resume_normal_permissions"))
        return {}  # No allow: preserve all existing permission checks.
    first = mark(folder, "notified", dict(record, event="write_paused"))
    prefix = "首次修改前的经验检查" if first else "经验入口尚未读全，本次修改仍未执行"
    return deny(f"{prefix}（不是用户拒绝，无需询问用户）。请用 Read 完整读取召回说明 {skill} "
                f"和经验入口 {entry}，按当前已理解的任务选择相关分支与经验，随后自行重试原修改。"
                "这适用于当前代理，无需让主代理代读。只查相关内容，足够即可继续；"
                "不要遍历全库、展开历史卡片或另写报告。没有相关经验也可以继续。"
                "在原任务结果中简记采用的经验 ID/版本及影响；入口读取只表示提醒已收到，不代表建议已被验证。")


def install(project, memory, python):
    project, memory = Path(project).resolve(), Path(memory).resolve()
    if not project.is_dir():
        raise ValueError("Project directory does not exist")
    manifest = load(memory / "manifest.json")
    if manifest["card_links"] != "references_only":
        raise ValueError("Export a portable reading package without --link-cards first")
    for relative, expected in manifest["files"].items():
        path = (memory / relative).resolve()
        if not path.is_relative_to(memory) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Memory manifest mismatch: " + relative)
    claude = project / ".claude"
    source_skill = Path(__file__).resolve().parents[1]
    installed_skill = claude / "skills/migloop-memory-recall"
    installed_script = claude / "hooks/migloop_memory.py"
    config_path = claude / "migloop-memory.json"
    settings_path = claude / "settings.local.json"
    settings = load(settings_path) if settings_path.exists() else {}
    if settings.get("disableAllHooks"):
        raise ValueError("Local settings disableAllHooks=true; not overriding existing policy")
    # Deliberately first-install only. Updates must preserve state and prior
    # versions explicitly; do not silently overwrite another installation.
    for path in (installed_skill, installed_script, config_path):
        if path.exists():
            raise ValueError("Already installed: " + str(path))
    hooks = settings.setdefault("hooks", {})
    for event in ("PreToolUse", "PostToolUse"):
        if not isinstance(hooks.setdefault(event, []), list):
            raise ValueError("Invalid existing hooks: " + event)
    command = (f'"{Path(python).resolve().as_posix()}" -B -X utf8 '
               f'"{installed_script.as_posix()}" run --config "{config_path.as_posix()}"')
    for event, matcher in (("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell"),
                           ("PostToolUse", "Read|Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell")):
        hooks[event].append({"matcher": matcher, "hooks": [{"type": "command", "command": command, "timeout": 5}]})
    backup = None
    if settings_path.exists():
        backup = claude / ("settings.local.before-migloop-" + uuid.uuid4().hex[:8] + ".json")
        shutil.copy2(settings_path, backup)
    installed_skill.mkdir(parents=True)
    shutil.copy2(source_skill / "SKILL.md", installed_skill / "SKILL.md")
    shutil.copytree(source_skill / "references", installed_skill / "references")
    installed_script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(__file__, installed_script)
    save(config_path, {"schema": "migloop-claude-checkpoint/1", "enabled": True,
                      "entry": str(memory / "index.md"), "skill": str(installed_skill / "SKILL.md"),
                      "runtime": str(claude / "migloop-runtime"),
                      "memory_revision": manifest["memory_revision"]}, exclusive=True)
    # Settings last: no live hook points at half-installed files.
    save(settings_path, settings)
    return {"settings": str(settings_path), "config": str(config_path), "entry": str(memory / "index.md"),
            "settings_backup": str(backup) if backup else None}


def main():
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--config", required=True)
    setup = commands.add_parser("install")
    setup.add_argument("--project", required=True)
    setup.add_argument("--memory", required=True)
    setup.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    if args.command == "install":
        result = install(args.project, args.memory, args.python)
    else:
        payload = json.load(sys.stdin)
        try:
            result = handle(load(args.config), payload)
        except (ValueError, OSError, KeyError) as error:
            if payload.get("hook_event_name") == "PreToolUse":
                result = deny(f"经验检查配置/状态错误：{error}。修改尚未执行，请修复 .claude/migloop-memory.json。")
            else:
                result = {"systemMessage": "经验阅读记录失败：" + str(error)}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
