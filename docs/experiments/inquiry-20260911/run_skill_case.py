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
RAW_TASK = "请查询 investigation.json 指定的被修文件，查明 execute 阶段结束后为什么需要修复、生成期间为什么没有一次做对，并给出总结和 recommendation。"


def prepare(out, case_id, *, raw_control=False, investigation_mode=None, isolated_inputs=None,
            skill_source=None, skill_name=None):
    if investigation_mode not in (None, "free", "mcp"):
        raise ValueError("investigation_mode must be free or mcp")
    custom_skill = skill_source is not None or skill_name is not None
    skill_name = skill_name or (Path(skill_source).name if skill_source is not None else "migloop-investigate")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", skill_name):
        raise ValueError("skill_name must be a single skill directory name")
    skill_source = Path(skill_source or REPO / "docs/skills" / skill_name).resolve()
    if not (skill_source / "SKILL.md").is_file():
        raise FileNotFoundError(skill_source / "SKILL.md")
    skill_source_inventory = BASE.tree_manifest(skill_source)
    product_mode = raw_control or investigation_mode is not None or custom_skill
    mode = investigation_mode or "free"
    if out.exists():
        raise FileExistsError(out)
    old = BASE.RAW.verify_manifest(iteration.BASELINE)
    case = next(c for c in old["cases"] if c["id"] == case_id)
    task = (iteration.BASELINE / case["prompt"]).read_text(encoding="utf-8")
    case = {**case, "generation_end": re.search(r"生成结束：([^，\s]+)", task)[1],
            "observation_end": re.search(r"观察截止：([^，\s]+)", task)[1]}
    source_pool = Path(case["pool"])
    if isolated_inputs is not None:
        isolated_inputs = Path(isolated_inputs).resolve()
        if isolated_inputs.exists() or out.resolve().is_relative_to(isolated_inputs):
            raise ValueError("Isolated inputs must be new and must not contain experiment outputs")
        isolated_inputs.mkdir(parents=True)
        shutil.copytree(source_pool, isolated_inputs / "mcp/pool")
        if raw_control:
            shutil.copytree(source_pool, isolated_inputs / "raw/pool")
        source_inventory = BASE.tree_manifest(source_pool)
        for arm in ("mcp", "raw") if raw_control else ("mcp",):
            if BASE.tree_manifest(isolated_inputs / arm / "pool") != source_inventory:
                raise ValueError("Independent source copy differs: " + arm)
        case = {**case, "source_pool": str(source_pool), "pool": str(isolated_inputs / "mcp/pool")}
    out.mkdir(parents=True)
    package = out / "code/src/migloop"
    package.mkdir(parents=True)
    shutil.copy2(REPO / "src/migloop/__init__.py", package / "__init__.py")
    shutil.copytree(REPO / "src/migloop/inquiry", package / "inquiry",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    workspace = isolated_inputs / "mcp/workspace" if isolated_inputs is not None else out / "workspace"
    skill = workspace / ".agents/skills" / skill_name
    skill.parent.mkdir(parents=True)
    shutil.copytree(skill_source, skill)
    if BASE.tree_manifest(skill) != skill_source_inventory:
        raise ValueError("Skill source changed during deployment")
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
    defaults = (BASE.RAW.settings(BASE.RAW.host_skills()) if product_mode
                else BASE.read(iteration.BASELINE / "runtime-settings.json"))
    config = {**defaults,
              "model_reasoning_effort": "high",
              "mcp_servers": {"inquiry": {"command": cmd[0], "args": cmd[1:] + ["mcp"],
                              "required": True, "startup_timeout_sec": 45, "tool_timeout_sec": 120}}}
    # Keep host-skill suppression and all prior isolation flags. Explicit file
    # invocation remains available even if discovery is suppressed by this CLI.
    prompt = "使用 $migloop-investigate，为 investigation.json 指定的被修文件制作并审核一张可载入的返修情景卡。"
    if custom_skill:
        prompt = f"使用 ${skill_name}，为 investigation.json 指定的被修文件制作归因卡。"
    elif product_mode:
        prompt = RAW_TASK + "使用 $migloop-investigate 完成调查并交付可加载的情景卡。"
    if product_mode and mode == "mcp":
        prompt += "本次调查原始转录只使用 inquiry MCP；shell 仅用于读取任务和 skill 文件、执行随附审核脚本。"
    control = None
    if raw_control:
        raw_workspace = isolated_inputs / "raw/workspace" if isolated_inputs is not None else out / "raw-workspace"
        raw_workspace.mkdir()
        raw_job = {k: job[k] for k in ("file", "pool", "generation_end", "observation_end")}
        if isolated_inputs is not None:
            raw_job["pool"] = str(isolated_inputs / "raw/pool")
        BASE.save(raw_workspace / "investigation.json", raw_job)
        raw_settings = {**config, "mcp_servers": {}}
        BASE.RAW.command(raw_workspace, raw_settings)
        BASE.save(out / "raw-settings.json", raw_settings)
        raw_prompt = RAW_TASK + ("只依据 investigation.json 指定的原始会话材料调查。" if isolated_inputs is not None else "")
        (out / "raw-prompt.md").write_text(raw_prompt, encoding="utf-8")
        control = {"workspace": str(raw_workspace),
                   "workspace_inventory": BASE.tree_manifest(raw_workspace),
                   "settings_sha256": BASE.sha(out / "raw-settings.json"),
                   "prompt_sha256": BASE.sha(out / "raw-prompt.md"),
                   "fresh_threads": True, "extra_review": False}
    argv = BASE.RAW.command(workspace, config)  # validate CLI/settings without a model call
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
        "skill_name": skill_name, "skill_source": str(skill_source), "skill_path": str(skill),
        "skill_source_inventory": skill_source_inventory,
        "prompt_sha256": BASE.sha(out / "prompt.md"), "settings_sha256": BASE.sha(out / "settings.json"),
        "driver_sha256": BASE.sha(out / "driver.py"), "audit_sha256": BASE.sha(out / "luna-audit.py"),
        "instruction_delivery": "explicit skill path in short task; no inline skill/GUIDE/task rubric; unchanged MCP initialization instructions",
        "comparison_limit": ("Single fresh skill-guided investigation: the first submit already receives the selected skill. "
                             "Its pre/post-feedback comparison is not an unguided raw or between-group baseline. "
                             "Recover every actual submit from native calls, including schema-invalid inputs absent from the report database."
                             if custom_skill and not raw_control else
                             "Fresh plain-task raw versus complete product skill/MCP/card workflow. "
                             "Product-level comparison, not a skill-isolated or checker-only ablation; "
                             "one existing development case per run, no baseline replacement." if product_mode else
                             "Existing ten-file development set, original source pools and time bounds. Skill/card workflow and UI detail presentation changed; not a blind holdout, skill-only causal ablation or fresh raw comparison."),
        **({"raw_control": control} if raw_control else {}),
        **({"investigation_mode": mode,
            "executables": {str(p): BASE.sha(p) for p in (Path(argv[0]), Path(BASE.DEFAULT_PYTHON))},
            "dependencies": {str(p): BASE.sha(p) for p in
                (Path(__file__), Path(iteration.__file__), Path(BASE.__file__),
                 Path(BASE.RAW.__file__), Path(BASE.RAW.OLD_RUNNER))}} if product_mode else {})})
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
    if control := m.get("raw_control"):
        if BASE.tree_manifest(control["workspace"]) != control["workspace_inventory"]:
            raise ValueError("Raw control workspace changed")
        for key, path in (("settings_sha256", "raw-settings.json"), ("prompt_sha256", "raw-prompt.md")):
            if BASE.sha(out / path) != control[key]:
                raise ValueError("Raw control artifact changed: " + path)
    for path, expected in {**m.get("dependencies", {}), **m.get("executables", {})}.items():
        if BASE.sha(path) != expected:
            raise ValueError("Frozen execution dependency changed: " + path)
    return m


def run_raw(out):
    """Fresh plain-task control, using the same recorder with no follow-up turn."""
    m = verify(out)
    if not m.get("raw_control"):
        raise ValueError("Prepare an explicit product pair before running its raw control")
    BASE.RAW.EFFORT = m["effort"]
    if BASE.RAW.MODEL != m["model"] or m["model"] != "gpt-5.6-luna":
        raise ValueError("Model differs from the frozen comparison")
    metrics = BASE.RAW.launch(m["raw_control"]["workspace"], out / "runs/raw/rep1",
                             (out / "raw-prompt.md").read_text(encoding="utf-8"),
                             BASE.read(out / "raw-settings.json"), m["timeout_seconds"])
    verify(out)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)


def audit_skill_delivery(out):
    """Authenticate full UTF-8 instructions in the recorded native delivery."""
    m = verify(out)
    run_dir = out / "runs/inquiry/rep1"
    skill = Path(m.get("skill_path", Path(m["workspace"]) / ".agents/skills/migloop-investigate"))
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
    result = {"model_calls": 0, "matches": matches, "skill_name": m.get("skill_name", "migloop-investigate"),
              "skill_path": str(skill),
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
                             capture_output=True, text=True, encoding="utf-8", timeout=180, check=False)
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
            skill = Path(m.get("skill_path", Path(m["workspace"]) / ".agents/skills/migloop-investigate"))
            checker = skill / "scripts/check_card.py"
            if not checker.is_file():
                skipped = {"status": "not_run", "report_id": report_id,
                           "reason": "Deployed skill has no optional scripts/check_card.py",
                           "native_delivery_audit_exit_code": audited.returncode,
                           "limit": "Native submission and graph audit retained; optional card-loader script was not executed."}
                BASE.save(run_dir / "card-audit.json", skipped)
                print(json.dumps(skipped), flush=True)
                return
            checked = subprocess.run([str(BASE.DEFAULT_PYTHON), "-B", "-X", "utf8",
                str(checker),
                "--task", str(Path(m["workspace"]) / "investigation.json"), "--report", report_id, "--full"],
                capture_output=True, text=True, encoding="utf-8", timeout=180, check=False)
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
            text=True, encoding="utf-8", check=False)
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
            # This is a progress snapshot, not an immutable experiment artifact.
            # BASE.save deliberately uses exclusive creation for original runs.
            (out / "suite-results.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(results[-1]), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("prepare", "prepare-product-pair", "run", "run-raw", "verify", "delivery", "prepare-suite", "run-suite"))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--case", default="F10-06")
    ap.add_argument("--investigation-mode", choices=("free", "mcp"))
    ap.add_argument("--isolated-inputs", type=Path)
    ap.add_argument("--skill-source", type=Path)
    ap.add_argument("--skill-name")
    args = ap.parse_args()
    target = args.out.resolve()
    if args.mode == "prepare-suite":
        prepare_suite(target)
    elif args.mode == "run-suite":
        run_suite(target)
    elif args.mode in ("prepare", "prepare-product-pair"):
        prepare(target, args.case, raw_control=args.mode == "prepare-product-pair",
                investigation_mode=args.investigation_mode, isolated_inputs=args.isolated_inputs,
                skill_source=args.skill_source, skill_name=args.skill_name)
    elif args.mode == "run":
        run(target)
    elif args.mode == "run-raw":
        run_raw(target)
    elif args.mode == "delivery":
        print(json.dumps(audit_skill_delivery(target), ensure_ascii=False))
    else:
        verify(target)
        print("verified")
