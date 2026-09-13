"""Freeze one existing case and run Luna with a deployed skill and a short task.

The case file contains scope only. No experiment answers enter the workspace.
Reuse the existing native launcher/auditor; do not rewrite any frozen old run.
"""

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
spec = importlib.util.spec_from_file_location("skill_case_iteration", HERE / "iterate.py")
iteration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iteration)
BASE = iteration.BASE


def prepare(out, case_id):
    if out.exists():
        raise FileExistsError(out)
    old = BASE.RAW.verify_manifest(iteration.BASELINE)
    case = next(c for c in old["cases"] if c["id"] == case_id)
    task = (iteration.BASELINE / case["prompt"]).read_text(encoding="utf-8")
    case = {**case, "generation_end": re.search(r"生成结束：([^，\s]+)", task)[1],
            "observation_end": re.search(r"观察截止：([^，\s]+)", task)[1]}
    out.mkdir(parents=True)
    package = out / "code/src/migloop"
    package.mkdir(parents=True)
    shutil.copy2(REPO / "src/migloop/__init__.py", package / "__init__.py")
    shutil.copytree(REPO / "src/migloop/inquiry", package / "inquiry",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    workspace = out / "workspace"
    skill = workspace / ".agents/skills/migloop-investigate"
    skill.parent.mkdir(parents=True)
    shutil.copytree(REPO / "docs/skills/migloop-investigate", skill)
    db = out / "index.sqlite"
    job = {"file": case["file"], "generation_end": case["generation_end"],
           "observation_end": case["observation_end"], "pool": case["pool"],
           "runtime": {"python": str(BASE.DEFAULT_PYTHON), "code_root": str(out / "code/src"),
                       "index_path": str(db)}}
    BASE.save(workspace / "investigation.json", job)
    cmd = iteration.command(out, db)
    imported = subprocess.run(cmd + ["import", "--pool", case["pool"]], check=True,
                              capture_output=True, text=True, encoding="utf-8", timeout=180)
    import_info = json.loads(imported.stdout)
    print(json.dumps(import_info), flush=True)
    config = {**BASE.read(iteration.BASELINE / "runtime-settings.json"),
              "model_reasoning_effort": "high",
              "mcp_servers": {"inquiry": {"command": cmd[0], "args": cmd[1:] + ["mcp"],
                              "required": True, "startup_timeout_sec": 45, "tool_timeout_sec": 120}}}
    # Keep host-skill suppression and all prior isolation flags. Explicit file
    # invocation remains available even if discovery is suppressed by this CLI.
    prompt = "使用 $migloop-investigate，为 investigation.json 指定的被修文件制作并审核一张可载入的返修情景卡。"
    BASE.RAW.command(workspace, config)  # validate CLI/settings without a model call
    BASE.save(out / "settings.json", config)
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    shutil.copy2(__file__, out / "driver.py")
    shutil.copy2(HERE / "luna-audit.py", out / "luna-audit.py")
    BASE.save(out / "manifest.json", {"schema": "skill-case/1", "case": case,
        "code_root": str(out / "code/src"), "index_path": str(db), "workspace": str(workspace),
        "model": "gpt-5.6-luna", "effort": "high", "timeout_seconds": 1800,
        "import_seconds": import_info["seconds"], "automatic_retry": False, "manual_report_repair": False,
        "code_inventory": BASE.tree_manifest(package), "pool_inventory": BASE.tree_manifest(case["pool"]),
        "workspace_inventory": BASE.tree_manifest(workspace), "skill_inventory": BASE.tree_manifest(skill),
        "prompt_sha256": BASE.sha(out / "prompt.md"), "settings_sha256": BASE.sha(out / "settings.json"),
        "driver_sha256": BASE.sha(out / "driver.py"), "audit_sha256": BASE.sha(out / "luna-audit.py"),
        "instruction_delivery": "explicit skill path in short task; no inline skill/GUIDE/task rubric; unchanged MCP initialization instructions",
        "comparison_limit": "Existing ten-file development set, original source pools and time bounds. Skill/card workflow and UI detail presentation changed; not a blind holdout, skill-only causal ablation or fresh raw comparison."})
    print(json.dumps({"prepared": str(out), "model_calls": 0, "task_chars": len(prompt)}), flush=True)


def verify(out):
    m = BASE.read(out / "manifest.json")
    for key, path in (("code_inventory", out / "code/src/migloop"),
                      ("pool_inventory", Path(m["case"]["pool"])),
                      ("workspace_inventory", Path(m["workspace"]))):
        if BASE.tree_manifest(path) != m[key]:
            raise ValueError("Frozen inventory changed: " + key)
    for key, path in (("prompt_sha256", "prompt.md"), ("settings_sha256", "settings.json"),
                      ("driver_sha256", "driver.py"), ("audit_sha256", "luna-audit.py")):
        if BASE.sha(out / path) != m[key]:
            raise ValueError("Frozen artifact changed: " + path)
    return m


def audit_skill_delivery(out):
    """Authenticate full UTF-8 instructions in the recorded native delivery."""
    m = verify(out)
    run_dir = out / "runs/inquiry/rep1"
    skill = Path(m["workspace"]) / ".agents/skills/migloop-investigate"
    spec = importlib.util.spec_from_file_location("skill_delivery_views", out / "luna-audit.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    normalize = lambda t: t.replace("\r\n", "\n").strip()
    expected = {name: normalize((skill / name).read_text(encoding="utf-8"))
                for name in ("SKILL.md", "references/mcp.md")}
    matches = {name: [] for name in expected}
    for line, raw in enumerate((run_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        record = json.loads(raw)
        p = record.get("payload") or {}
        if record.get("type") != "response_item":
            continue
        kind = p.get("type")
        if kind == "message" and p.get("role") == "user":
            body = p.get("content") or []
            text = body if isinstance(body, str) else "\n".join(b.get("text", "") for b in body)
            candidates = [("native_skill", text)] if "<skill>" in text else []
        elif kind in ("function_call_output", "custom_tool_call_output"):
            candidates = list(reader.views(p.get("output")))
        else:
            candidates = []
        for name, text in expected.items():
            for location, body in candidates:
                if text in normalize(body):
                    matches[name].append({"line": line, "channel": location})
                    break
    result = {"model_calls": 0, "matches": matches,
              "full_instruction_delivery": all(matches.values()),
              "native_skill_injected": any(m["channel"] == "native_skill" for m in matches["SKILL.md"]),
              "instruction_hashes": {name: BASE.sha(skill / name) for name in expected},
              "limit": "Verifies complete recorded UTF-8 presentation, not reading attention, compliance or causal correctness."}
    BASE.save(run_dir / "skill-delivery.json", result)
    return result


def run(out):
    m = verify(out)
    BASE.RAW.EFFORT = m["effort"]
    assert BASE.RAW.MODEL == m["model"] == "gpt-5.6-luna"
    metrics = BASE.RAW.launch(m["workspace"], out / "runs/inquiry/rep1",
                             (out / "prompt.md").read_text(encoding="utf-8"),
                             BASE.read(out / "settings.json"), m["timeout_seconds"])
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    audited = subprocess.run([str(BASE.DEFAULT_PYTHON), "-B", "-X", "utf8", str(out / "luna-audit.py"), str(out)],
                             capture_output=True, text=True, encoding="utf-8", timeout=180)
    (out / "audit.stdout.txt").write_text(audited.stdout, encoding="utf-8")
    (out / "audit.stderr.txt").write_text(audited.stderr, encoding="utf-8")
    verify(out)
    print(json.dumps(audit_skill_delivery(out), ensure_ascii=False), flush=True)
    print(json.dumps({"audit_exit_code": audited.returncode, "audit": audited.stdout,
                      "stderr": audited.stderr}, ensure_ascii=False), flush=True)
    run_dir = out / "runs/inquiry/rep1"
    if (run_dir / "verdict.json").is_file():
        graph = BASE.read(run_dir / "verdict.json")
        report_id = graph.get("report_id") if isinstance(graph, dict) else None
        if report_id:
            checked = subprocess.run([str(BASE.DEFAULT_PYTHON), "-B", "-X", "utf8",
                str(Path(m["workspace"]) / ".agents/skills/migloop-investigate/scripts/check_card.py"),
                "--task", str(Path(m["workspace"]) / "investigation.json"), "--report", report_id],
                capture_output=True, text=True, encoding="utf-8", timeout=180)
            BASE.save(run_dir / "card-audit.json", json.loads(checked.stdout))
            print(json.dumps({"card_audit_exit_code": checked.returncode, "report_id": report_id}), flush=True)


def prepare_suite(out):
    """Same ten frozen targets, separate databases so cases cannot read other reports."""
    if out.exists():
        raise FileExistsError(out)
    cases = BASE.RAW.verify_manifest(iteration.BASELINE)["cases"]
    if len(cases) != 10:
        raise ValueError("Expected the existing ten-file benchmark")
    out.mkdir(parents=True)
    for case in cases:
        prepare(out / case["id"], case["id"])
    BASE.save(out / "suite.json", {"cases": [c["id"] for c in cases], "workers": 2,
        "model": "gpt-5.6-luna", "effort": "high", "repetitions": 1,
        "automatic_retry": False, "raw_rerun": False})


def run_suite(out):
    """Two processes maximum; preserve every failure and never replace a result."""
    suite = BASE.read(out / "suite.json")
    for case in suite["cases"]:
        verify(out / case)
        if (out / case / "runs/inquiry/rep1").exists():
            raise FileExistsError("Suite already started: " + case)

    def worker(case):
        print(json.dumps({"started": case}), flush=True)
        result = subprocess.run([str(BASE.DEFAULT_PYTHON), "-B", "-X", "utf8",
            str(__file__), "run", "--out", str(out / case)], capture_output=True,
            text=True, encoding="utf-8")
        (out / case / "worker.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (out / case / "worker.stderr.txt").write_text(result.stderr, encoding="utf-8")
        run_dir = out / case / "runs/inquiry/rep1"
        metrics = BASE.read(run_dir / "metrics.json") if (run_dir / "metrics.json").is_file() else {}
        card = BASE.read(run_dir / "card-audit.json") if (run_dir / "card-audit.json").is_file() else {}
        return {"case": case, "worker_exit_code": result.returncode, "status": metrics.get("status"),
                "seconds": metrics.get("elapsed_seconds"), "card_status": card.get("status"),
                "report_id": card.get("report_id")}

    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = [executor.submit(worker, case) for case in suite["cases"]]
        for future in as_completed(pending):
            results.append(future.result())
            BASE.save(out / "suite-results.json", results)
            print(json.dumps(results[-1]), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("prepare", "run", "verify", "delivery", "prepare-suite", "run-suite"))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--case", default="F10-06")
    args = ap.parse_args()
    target = args.out.resolve()
    if args.mode == "prepare-suite":
        prepare_suite(target)
    elif args.mode == "run-suite":
        run_suite(target)
    elif args.mode == "prepare":
        prepare(target, args.case)
    elif args.mode == "run":
        run(target)
    elif args.mode == "delivery":
        print(json.dumps(audit_skill_delivery(target), ensure_ascii=False))
    else:
        verify(target)
        print("verified")
