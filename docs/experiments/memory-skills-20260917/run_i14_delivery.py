"""Current unmodified inquiry + i14 investigation/implicit-edge delivery skill.

Fresh Luna/high. Original file-level task, no triaged issue or answer-bearing
prompt. Reuses the native CLI recorder, not the newer card pack workflow.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

import yaml

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("card_trial_common", HERE / "run_card.py")
BASE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BASE)
RAW = BASE.RAW
RAW.MODEL, RAW.EFFORT = "gpt-5.6-luna", "high"
RAW.command = BASE.native_command  # original read-only shell; MCP saves reports
SKILL = "migloop-inquiry-i14"


def prepare(out, historical_case):
    if out.exists():
        raise FileExistsError(out)
    old = RAW.read(historical_case / "manifest.json")
    case = old["case"]
    out.mkdir(parents=True)
    workspace = out / "workspace"
    workspace.mkdir()
    pool = out / "materials"
    shutil.copytree(case["pool"], pool)
    if BASE.inventory(pool) != BASE.inventory(Path(case["pool"])):
        raise ValueError("Raw pool copy differs")
    shutil.copytree(BASE.REPO / "skills" / SKILL, workspace / "skills" / SKILL)
    package = out / "code/src/migloop"
    package.mkdir(parents=True)
    shutil.copy2(BASE.REPO / "src/migloop/__init__.py", package / "__init__.py")
    shutil.copytree(BASE.REPO / "src/migloop/inquiry", package / "inquiry",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    job = {"target": case["file"], "materials": str(pool),
           "generation_end": case["generation_end"], "observation_end": case["observation_end"]}
    RAW.save(workspace / "job.json", job)
    args = ["-I", "-B", "-X", "utf8", "-c",
            f"import sys;sys.path.insert(0,{str(package.parent)!r});from migloop.inquiry.__main__ import main;main()",
            "--db", str(out / "index.sqlite")]
    imported = subprocess.run([str(BASE.PYTHON), *args, "import", "--pool", str(pool)],
                              capture_output=True, text=True, encoding="utf-8", check=True, timeout=180)
    RAW.save(out / "import.json", json.loads(imported.stdout))
    config = RAW.settings(RAW.host_skills())
    config["mcp_servers"] = {"inquiry": {"command": str(BASE.PYTHON), "args": [*args, "mcp"],
        "required": True, "startup_timeout_sec": 45, "tool_timeout_sec": 120}}
    RAW.save(out / "settings.json", config)
    prompt = (f"按 UTF-8 读取并使用 {(workspace / 'skills' / SKILL / 'SKILL.md').as_posix()}。\n"
              f"转录：{pool.as_posix()}；任务：当前目录 job.json。\n")
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    command = RAW.command(workspace, config)
    RAW.save(out / "manifest.json", {
        "schema": "migloop-i14-delivery-trial/1", "case": case, "workspace": str(workspace),
        "historical_case": str(historical_case), "code_root": str(package.parent),
        "index_path": str(out / "index.sqlite"), "model": RAW.MODEL, "effort": RAW.EFFORT,
        "fresh_thread": True, "fork": False, "automatic_retry": False, "timeout_seconds": 1800,
        "mcp_guide": "current unchanged", "delivery": "inquiry/1; omit edges; MCP submit only",
        "repository_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BASE.REPO, text=True).strip(),
        "frozen": {"materials": BASE.inventory(pool), "workspace/skills": BASE.inventory(workspace / "skills"),
                   "code/src": BASE.inventory(package.parent)},
        "files": {str(p.relative_to(out)): RAW.sha(p) for p in (out / "prompt.md", out / "settings.json", workspace / "job.json")},
        "dependencies": {str(p): RAW.sha(p) for p in (Path(__file__), HERE / "run_card.py",
            BASE.REPO / "docs/experiments/file-first-10/run_raw10.py", RAW.OLD_RUNNER, Path(command[0]))},
        "historical_inputs": {str(historical_case / name): RAW.sha(historical_case / name) for name in ("manifest.json", "prompt.md")},
        "environment": subprocess.check_output([str(BASE.PYTHON), "-m", "pip", "freeze"], text=True, encoding="utf-8").splitlines(),
        "caveat": "One nonconcurrent file-level rerun. Core unchanged; skill packaging and legacy delivery tested together. No claim of isolated causal superiority."
    })
    BASE.verify(out)
    print(json.dumps({"prepared": str(out), "job": job, "prompt": prompt}, ensure_ascii=False), flush=True)


def capture(out):
    """Export exact model submissions without repairing them or invoking a model."""
    run = out / "run"
    events = [json.loads(line) for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    submitted = [e["item"].get("arguments", {}) for e in events if e.get("type") == "item.completed"
                 and e.get("item", {}).get("tool") == "submit"]
    final = (run / "report.md").read_text(encoding="utf-8") if (run / "report.md").exists() else ""
    db = sqlite3.connect((out / "index.sqlite").as_uri() + "?mode=ro", uri=True)
    reports = db.execute("SELECT id,request,data FROM runs WHERE kind='report' ORDER BY rowid").fetchall()
    db.close()
    saved, selected = [], []
    for number, (identity, source, data) in enumerate(reports, 1):
        graph = json.loads(data)
        original = yaml.safe_load(source)
        stem = f"submission-{number}"
        with (run / (stem + ".yaml")).open("x", encoding="utf-8", newline="") as handle:
            handle.write(source)
        RAW.save(run / (stem + ".json"), graph)
        bound = any(s.get("document") == source or
                    (isinstance(s.get("card"), dict) and original == s["card"])
                    for s in submitted)
        source_hash = RAW.sha(run / (stem + ".yaml"))
        saved.append({"report_id": identity, "source_sha256": source_hash, "native_submission_bound": bound,
                      "mechanical_status": graph.get("mechanical_status"), "path_status": graph.get("path_status"),
                      "model_omitted_edges": all("edges" not in f for f in original.get("findings", []))})
        if identity in final and source_hash in final and bound:
            selected.append((stem, saved[-1]))
    if len(selected) == 1:
        stem, result = selected[0]
        shutil.copy2(run / (stem + ".yaml"), run / "verdict.yaml")
        shutil.copy2(run / (stem + ".json"), run / "verdict.json")
    else:
        result = {"error": "Final report/hash did not uniquely select a native submission"}
    RAW.save(run / "submission-audit.json", {"reports": saved, "selected": result,
        "model_calls": 0, "format_repair": False, "semantic_verified": False})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify", "run", "capture"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--historical-case", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.mode == "prepare":
        if not args.historical_case:
            parser.error("prepare requires --historical-case")
        prepare(out, args.historical_case.resolve())
    elif args.mode == "capture":
        print(json.dumps(capture(out), ensure_ascii=False))
    else:
        manifest = BASE.verify(out)
        if args.mode == "run":
            metrics = RAW.launch(Path(manifest["workspace"]), out / "run", (out / "prompt.md").read_text(encoding="utf-8"),
                                 RAW.read(out / "settings.json"), manifest["timeout_seconds"])
            BASE.verify(out)
            RAW.save(out / "post-run-integrity.json", {"frozen_inputs_unchanged": True})
            print(json.dumps({"metrics": metrics, "submission": capture(out)}, ensure_ascii=False, indent=2), flush=True)
        else:
            print("verified")
