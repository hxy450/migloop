"""Frozen file-first raw baseline. No production imports, retries or model fallback.

smoke uses an empty workspace. run requires a frozen manifest and passing smoke.
Only the parent harness writes artifacts outside the read-only investigator pool.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OLD_RUNNER = HERE.parent / "2026-09-09-fidelity-cost/run_pair.py"
MODEL, EFFORT = "gpt-5.6-luna", "medium"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, data):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def now():
    return datetime.now(timezone.utc).isoformat()


def parser():
    spec = importlib.util.spec_from_file_location("raw10_native_parser", OLD_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def host_skills():
    # Per-run overrides, never change global Codex settings or delete skills.
    roots = [Path.home() / ".agents/skills", Path.home() / ".codex/skills",
             Path.home() / ".codex/plugins/cache"]
    return sorted({str(p.resolve()) for root in roots if root.exists() for p in root.rglob("SKILL.md")})


def settings(skills):
    config = {"model_reasoning_effort": EFFORT, "web_search": "disabled",
              "mcp_servers": {}, "project_doc_max_bytes": 0,
              "skills.config": [{"path": str(Path(p)), "enabled": False} for p in skills]
                  + [{"path": str(Path(p).parent), "enabled": False} for p in skills]}
    if os.name == "nt":
        config["windows.sandbox"] = "elevated"
    for name in ("plugins", "browser_use", "computer_use", "image_generation", "memories",
                 "hooks", "apps", "multi_agent", "code_mode", "skill_search"):
        config["features." + name] = False
    config.update({"features.code_mode_host": True, "features.shell_tool": True,
                   "features.skip_host_skill_discovery": True})
    return config


def command(pool, config):
    engine = parser()
    exe = shutil.which("codex")
    if not exe:
        raise RuntimeError("Codex CLI is unavailable; no fallback")
    if os.name == "nt" and Path(exe).suffix.lower() in (".cmd", ".bat", ".ps1"):
        # npm's cmd shim has an 8191-character limit; native Windows supports
        # the larger argument vector needed for per-run skill overrides.
        package = Path(exe).parent / "node_modules/@openai/codex"
        native = list(package.glob("node_modules/@openai/codex-win32-*/vendor/*/bin/codex.exe"))
        if len(native) != 1:
            raise RuntimeError("Native CLI resolution ambiguous; do not silently change launcher")
        exe = str(native[0])
    cmd = [exe, "-a", "never", "exec", "--ignore-user-config", "--ignore-rules",
           "--skip-git-repo-check", "--sandbox", "read-only", "--json", "-m", MODEL]
    for key, value in config.items():
        if key.startswith("features."):
            cmd.extend(["--enable" if value else "--disable", key.split(".", 1)[1]])
        else:
            cmd.extend(["-c", key + "=" + engine.toml_value(value)])
    cmd.extend(["-C", str(pool), "-"])
    if os.name == "nt" and len(subprocess.list2cmdline(cmd)) > 30000:
        raise ValueError("Command would exceed Windows command-line limit")
    return cmd


def instruction_audit(transcript):
    messages, skill_catalogs = [], []
    for number, line in enumerate(Path(transcript).read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        p = row.get("payload") or {}
        if row.get("type") == "response_item" and p.get("type") == "message" and p.get("role") in ("developer", "system"):
            body = p.get("content")
            text = body if isinstance(body, str) else "\n".join(x.get("text", "") for x in body or [] if isinstance(x, dict))
            record = {"line": number, "role": p["role"], "sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "chars": len(text)}
            messages.append(record)
            if "### Available skills" in text or "## Available skills" in text:
                skill_catalogs.append({**record, "text": text})
    return {"instruction_messages": messages, "host_skill_catalogs": skill_catalogs,
            "host_skill_catalog_absent": not skill_catalogs,
            "limit": "Instruction inspection, not proof of OS-level read isolation or all tool-policy compliance"}


def launch(pool, out, prompt, config, timeout):
    out = Path(out).resolve()
    if out.exists() or out.is_relative_to(Path(pool).resolve()):
        raise ValueError("Run directory must be new and outside the source pool")
    out.mkdir(parents=True)
    cmd = command(pool, config)
    save(out / "command.json", {"argv": cmd, "cwd": str(pool), "settings": config})
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    engine = parser()
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    # Do not point the raw investigator at a current source checkout via env.
    for key in tuple(env):
        if key == "PYTHONPATH" or key.startswith("MIGLOOP_"):
            env.pop(key)
    started, proc = time.perf_counter(), None
    metrics = {"model_requested": MODEL, "effort_requested": EFFORT, "started_at": now(),
               "status": "starting", "timeout_seconds": timeout, "automatic_retry": False,
               "token_or_dollar_cap": None, "wall_limit_enforced": True, "turn_hint_enforced": False}
    save(out / "started.json", metrics)
    with (out / "events.jsonl").open("wb") as stdout, (out / "stderr.txt").open("wb") as stderr:
        try:
            kw = {"cwd": str(pool), "env": env, "stdin": subprocess.PIPE, "stdout": stdout, "stderr": stderr}
            if os.name == "nt":
                kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            else:
                kw["start_new_session"] = True
            proc = subprocess.Popen(cmd, **kw)
            proc.communicate(input=prompt.encode("utf-8"), timeout=timeout)
            metrics["status"] = "completed" if proc.returncode == 0 else "cli_error"
        except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            metrics.update(status="timeout" if isinstance(error, subprocess.TimeoutExpired) else "launch_error",
                           error=repr(error))
            if proc is not None:
                engine.stop_process(proc)
    result = engine.parse_codex_events(out / "events.jsonl")
    save(out / "result.json", result)
    original = engine.find_codex_transcript(result.get("thread_id"))
    native = None
    if original:
        shutil.copy2(original, out / "transcript.jsonl")
        native = engine.parse_codex_transcript(out / "transcript.jsonl")
        save(out / "instruction-audit.json", instruction_audit(out / "transcript.jsonl"))
    report = result.get("response_text")
    if isinstance(report, str):
        (out / "report.md").write_text(report, encoding="utf-8")
    metrics.update(engine.actual_codex_context(result, native))
    metrics.update(ended_at=now(), elapsed_seconds=time.perf_counter()-started,
                   usage=result.get("usage"), recording_complete=native is not None,
                   session_id=result.get("thread_id"), transcript_sha256=sha(out/"transcript.jsonl") if native else None,
                   final_status=result.get("final_status"), events_malformed=result.get("malformed_lines"),
                   report_present=isinstance(report, str) and bool(report.strip()),
                   host_skill_catalog_absent=read(out/"instruction-audit.json")["host_skill_catalog_absent"] if native else None)
    if metrics["status"] == "completed" and result.get("final_status") != "completed":
        metrics["status"] = "incomplete"
    save(out / "metrics.json", metrics)
    return metrics


def smoke(out):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    empty = out / "empty-pool"
    empty.mkdir()
    config = settings(host_skills())
    save(out / "runtime-settings.json", config)
    prompt = ("这是只读实验环境检查，不是会话调查。只执行一次 Get-ChildItem -Force -LiteralPath . 列出当前空目录，"
              "不要读取目录外内容，不用技能，不访问网络。成功后仅回复 RAW10_SMOKE_OK；若失败就如实说明，不重试。")
    metrics = launch(empty, out / "run", prompt, config, 180)
    calls = read(out / "run/result.json").get("calls", {}).get("seq", [])
    command_ok = (len(calls) == 1 and calls[0].get("tool") == "command_execution"
                  and calls[0].get("exit_code") == 0 and calls[0].get("status") == "returned"
                  and "get-childitem -force -literalpath ." in str(calls[0].get("input", "")).lower())
    passed = (metrics["status"] == "completed" and metrics["actual_models"] == [MODEL]
              and metrics["actual_effort"] == EFFORT and metrics["recording_complete"]
              and metrics["host_skill_catalog_absent"] is True and command_ok
              and (out / "run/report.md").read_text(encoding="utf-8").strip() == "RAW10_SMOKE_OK")
    save(out / "smoke.json", {"passed": passed, "command_executed": command_ok, "settings_sha256": sha(out/"runtime-settings.json"),
                               "metrics": metrics, "runner_sha256": sha(Path(__file__)), "parser_sha256": sha(OLD_RUNNER)})
    return {"smoke": str(out), "passed": passed, **metrics}


def verify_manifest(base):
    manifest = read(base / "manifest.json")
    if manifest.get("status") != "frozen_ready_for_raw":
        raise ValueError("Reference and rubric must be frozen before investigation")
    for item in manifest["artifacts"]:
        if sha(base/item["path"]) != item["sha256"]:
            raise ValueError("Frozen artifact drift: " + item["path"])
    for item in manifest["source_files"]:
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("Frozen source drift")
    if sha(Path(__file__)) != manifest["runner_sha256"] or sha(OLD_RUNNER) != manifest["parser_sha256"]:
        raise ValueError("Frozen runner drift")
    if not read(Path(manifest["smoke"]) / "smoke.json")["passed"]:
        raise ValueError("Environment smoke did not pass")
    if sha(base/"runtime-settings.json") != manifest["runtime_settings_sha256"]:
        raise ValueError("Runtime settings changed")
    if manifest["runtime_settings_sha256"] != sha(Path(manifest["smoke"])/"runtime-settings.json"):
        raise ValueError("Settings differ from inspected smoke")
    return manifest


def run_queue(base):
    base = Path(base).resolve()
    manifest = verify_manifest(base)
    config = read(base / "runtime-settings.json")
    jobs = [(case, rep) for rep in (1, 2) for case in manifest["cases"]]
    for case, rep in jobs:
        if (base/"runs"/case["id"]/f"rep{rep}").exists():
            raise FileExistsError("Existing run; no automatic overwrite or retry")
    stopped = False
    with (base / "queue.jsonl").open("x", encoding="utf-8", buffering=1) as journal:
        def emit(value):
            line = json.dumps({"time": now(), **value}, ensure_ascii=False)
            journal.write(line + "\n")
            print(line, flush=True)
        emit({"event": "start", "jobs": len(jobs), "concurrency": 2})
        with ThreadPoolExecutor(max_workers=2) as executor:
            pending = {}
            while jobs or pending:
                while jobs and len(pending) < 2 and not stopped:
                    case, rep = jobs.pop(0)
                    out = base/"runs"/case["id"]/f"rep{rep}"
                    emit({"event": "launch", "case": case["id"], "rep": rep})
                    task = executor.submit(launch, case["pool"], out,
                        (base/case["prompt"]).read_text(encoding="utf-8"), config, manifest["timeout_seconds"])
                    pending[task] = (case["id"], rep)
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for task in done:
                    case, rep = pending.pop(task)
                    try:
                        metric = task.result()
                    except Exception as error:
                        metric = {"status": "harness_error", "error": repr(error)}
                    emit({"event": "finish", "case": case, "rep": rep, **metric})
                    if (metric.get("status") not in ("completed", "timeout", "incomplete")
                        or metric.get("actual_models") != [MODEL] or metric.get("actual_effort") != EFFORT
                        or not metric.get("recording_complete") or not metric.get("host_skill_catalog_absent")):
                        stopped = True
                        emit({"event": "stop_scheduling", "reason": "infrastructure_or_identity_or_instruction_failure", "unstarted": len(jobs)})
            verify_manifest(base)
            emit({"event": "end", "status": "stopped" if stopped else "finished", "unstarted": len(jobs)})
    return {"base": str(base), "status": "stopped" if stopped else "finished"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("smoke", "run"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(smoke(args.out) if args.mode == "smoke" else run_queue(args.out), ensure_ascii=False))
