"""One fresh Sol task using a frozen four-skill bundle and unedited triage issue.

No answer-bearing prompt, parent conversation, second model, or automatic retry.
The model may revise its own drafts after the skill's mechanical feedback.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
PYTHON = Path("C:/Users/hongy/projects/migbot-elite/.venv/Scripts/python.exe")
MODEL = "gpt-5.6-sol"
EFFORT = "high"
NAMES = ("migloop-repair-triage", "migloop-build-cards", "migloop-memory-maintain", "migloop-memory-recall")


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


RAW = module(REPO / "docs/experiments/file-first-10/run_raw10.py", "card_trial_raw")
RAW.MODEL, RAW.EFFORT = MODEL, EFFORT
native_command = RAW.command


def card_command(workspace, config):
    command = native_command(workspace, config)
    command[command.index("--sandbox") + 1] = "workspace-write"
    return command


RAW.command = card_command


def inventory(root):
    return {str(p.relative_to(root)).replace("\\", "/"): RAW.sha(p)
            for p in sorted(Path(root).rglob("*")) if p.is_file()
            and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def prepare(out, tasks, title):
    import yaml
    if out.exists():
        raise FileExistsError(out)
    originals = yaml.safe_load(tasks.read_text(encoding="utf-8"))
    matches = [i for i in originals["issues"] if i["title"] == title]
    if len(matches) != 1:
        raise ValueError("Select one existing issue by exact title")
    pool = Path(originals["scope"]["materials"][0])
    out.mkdir(parents=True)
    copied_pool = out / "materials"
    shutil.copytree(pool, copied_pool)
    if inventory(pool) != inventory(copied_pool):
        raise ValueError("Copied transcript pool differs")
    workspace = out / "workspace"
    workspace.mkdir()
    for name in NAMES:
        shutil.copytree(REPO / "skills" / name, workspace / "skills" / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    code = workspace / "runtime/src/migloop"
    code.mkdir(parents=True)
    shutil.copy2(REPO / "src/migloop/__init__.py", code / "__init__.py")
    shutil.copytree(REPO / "src/migloop/inquiry", code / "inquiry",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    sys.path.insert(0, str(workspace / "skills/migloop-memory-maintain/scripts"))
    from memorylib.cases import dispatch
    from memorylib.provenance import collect
    runtime = {"python": str(PYTHON), "code_root": str(code.parent),
               "index_path": str(workspace / "index.sqlite")}
    scope = {**originals["scope"], "materials": [str(copied_pool)]}
    selected = {"schema": originals["schema"], "scope": scope, "issues": matches}
    RAW.save(out / "task.json", selected)
    RAW.save(out / "server-metadata.json", {"analysis": {"models": [MODEL]}})
    RAW.save(out / "provenance.json", collect(copied_pool, out / "server-metadata.json"))
    dispatch(out / "task.json", out / "provenance.json", out / "dispatch")
    dispatched = RAW.read(out / "dispatch/jobs.json")["jobs"][0]
    job = RAW.read(dispatched["job"])
    job["provenance_path"] = str(out / "dispatch/provenance.json")
    job["runtime"] = runtime
    RAW.save(workspace / "job.json", job)
    command = [str(PYTHON), "-I", "-B", "-X", "utf8", "-c",
               f"import sys;sys.path.insert(0,{str(code.parent)!r});from migloop.inquiry.__main__ import main;main()",
               "--db", runtime["index_path"], "import", "--pool", str(copied_pool)]
    imported = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=180, check=True)
    RAW.save(out / "import.json", json.loads(imported.stdout))
    skill = workspace / "skills/migloop-build-cards/SKILL.md"
    prompt = f"使用 {skill.as_posix()}。\n转录：{copied_pool.as_posix()}；本次任务：当前目录 job.json。\n"
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    config = RAW.settings(RAW.host_skills())
    RAW.save(out / "settings.json", config)
    command = card_command(workspace, config)
    RAW.save(out / "manifest.json", {
        "schema": "migloop-four-skill-trial/1", "model": MODEL, "effort": EFFORT,
        "fresh_thread": True, "fork": False, "automatic_retry": False,
        "raw_investigation": True, "mcp_servers": [], "mechanical_feedback": "pack --db",
        "source_tasks": str(tasks), "source_tasks_sha256": RAW.sha(tasks), "issue_title": title,
        "issue_unchanged": matches[0] == job["issue"], "selection": "one existing task selected before model run; not a benchmark score",
        "workspace": str(workspace), "pool": str(copied_pool),
        "frozen": {"materials": inventory(copied_pool), "workspace/skills": inventory(workspace / "skills"),
                   "workspace/runtime/src": inventory(code.parent)},
        "files": {str(p.relative_to(out)): RAW.sha(p) for p in (out / "prompt.md", out / "settings.json", workspace / "job.json", out / "dispatch/provenance.json")},
        "dependencies": {str(p): RAW.sha(p) for p in (Path(__file__), REPO / "docs/experiments/file-first-10/run_raw10.py", RAW.OLD_RUNNER, Path(command[0]))},
        "timeout_seconds": 1800,
    })
    print(json.dumps({"prepared": str(out), "model": MODEL, "effort": EFFORT, "issue": title, "prompt": prompt}, ensure_ascii=False), flush=True)


def verify(out):
    manifest = RAW.read(out / "manifest.json")
    for path, expected in manifest["frozen"].items():
        if inventory(out / path) != expected:
            raise ValueError("Frozen artifact changed: " + path)
    for path, expected in manifest["files"].items():
        if RAW.sha(out / path) != expected:
            raise ValueError("Frozen artifact changed: " + path)
    for path, expected in manifest["dependencies"].items():
        if RAW.sha(path) != expected:
            raise ValueError("Execution dependency changed: " + path)
    return manifest


def run(out):
    manifest = verify(out)
    metrics = RAW.launch(Path(manifest["workspace"]), out / "run",
                         (out / "prompt.md").read_text(encoding="utf-8"),
                         RAW.read(out / "settings.json"), manifest["timeout_seconds"])
    verify(out)
    RAW.save(out / "post-run-integrity.json", {"frozen_inputs_unchanged": True})
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "verify"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--title")
    args = parser.parse_args()
    out = args.out.resolve()
    if args.mode == "prepare":
        prepare(out, args.tasks.resolve(), args.title)
    elif args.mode == "run":
        run(out)
    else:
        verify(out)
        print("verified")
