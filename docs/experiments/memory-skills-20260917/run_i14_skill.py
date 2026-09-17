"""Fresh Luna/high + MCP trial; preserve old hashed harness and all old runs.

Preparation reuses the four-skill job/import machinery, then freezes the selected
comparison skill and MCP settings before any model runs. No answers in the prompt.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("frozen_card_trial", HERE / "run_card.py")
BASE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BASE)
BASE.MODEL = BASE.RAW.MODEL = "gpt-5.6-luna"
BASE.EFFORT = BASE.RAW.EFFORT = "high"
SKILL = "migloop-build-cards-i14"


def prepare(out, tasks, title):
    BASE.prepare(out, tasks, title)
    workspace = out / "workspace"
    shutil.copytree(BASE.REPO / "skills" / SKILL, workspace / "skills" / SKILL,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    runtime = BASE.RAW.read(workspace / "job.json")["runtime"]
    prompt = (f"使用 {(workspace / 'skills' / SKILL / 'SKILL.md').as_posix()}。\n"
              f"转录：{(out / 'materials').as_posix()}；本次任务：当前目录 job.json。\n")
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    config = BASE.RAW.read(out / "settings.json")
    config["mcp_servers"] = {"inquiry": {
        "command": runtime["python"],
        "args": ["-I", "-B", "-X", "utf8", "-c",
                 f"import sys;sys.path.insert(0,{runtime['code_root']!r});from migloop.inquiry.__main__ import main;main()",
                 "--db", runtime["index_path"], "mcp"],
        "required": True, "startup_timeout_sec": 45, "tool_timeout_sec": 120,
    }}
    (out / "settings.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = BASE.RAW.read(out / "manifest.json")
    manifest.update(schema="migloop-i14-skill-trial/1", mcp_servers=["inquiry"],
                    comparison_skill=SKILL, preparation_complete=True,
                    limitation="New skill + enabled MCP + Luna vs earlier Sol/raw runs; not an isolated code or skill ablation")
    manifest["frozen"]["workspace/skills"] = BASE.inventory(workspace / "skills")
    manifest["files"] = {p: BASE.RAW.sha(out / p) for p in manifest["files"]}
    manifest["dependencies"][str(Path(__file__))] = BASE.RAW.sha(__file__)
    manifest["repository_head"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=BASE.REPO, text=True).strip()
    manifest["environment"] = subprocess.check_output(
        [str(BASE.PYTHON), "-m", "pip", "freeze"], text=True, encoding="utf-8").splitlines()
    # Only preparation updates these files. run/verify never overwrite inputs.
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    BASE.verify(out)
    print(json.dumps({"ready": str(out), "model": BASE.MODEL, "effort": BASE.EFFORT,
                      "mcp": True, "prompt": prompt}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "verify"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--title")
    args = parser.parse_args()
    if args.mode == "prepare":
        if not args.tasks or not args.title:
            parser.error("prepare requires --tasks and --title")
        prepare(args.out.resolve(), args.tasks.resolve(), args.title)
    elif args.mode == "run":
        BASE.run(args.out.resolve())
    else:
        BASE.verify(args.out.resolve())
        print("verified")
