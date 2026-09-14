"""Fork a frozen raw answer into equal-budget raw/inquiry claim reviews.

Reuses the original launcher, native recorder and isolation settings unchanged.
Each arm runs in its own process; no global monkeypatch races or model retries.
"""

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("paired_iteration", HERE / "iterate.py")
iteration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iteration)
BASE, RAW = iteration.BASE, iteration.BASE.RAW
REPO = HERE.parents[2]
RAW_HIGH = iteration.BASELINE.parent / "raw-high-i20-match-20260912"
CASES = ("F10-06", "F10-09")
ALL_CASES = tuple(f"F10-{number:02d}" for number in range(1, 11))
ARMS = ("raw", "inquiry")


def fork_command(command, session_id):
    UUID(session_id)
    if command[-1] != "-" or "resume" in command or "fork" in command:
        raise ValueError("Expected ordinary stdin exec, never --last")
    return command[:-1] + ["fork", session_id, "-"]


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]


def messages(records):
    return [r["payload"] for r in records if r.get("type") == "response_item"]


def last_usage(records):
    values = [r.get("payload", {}).get("info", {}).get("total_token_usage")
              for r in records if r.get("payload", {}).get("type") == "token_count"
              and isinstance(r.get("payload", {}).get("info"), dict)]
    return next((v for v in reversed(values) if v), None)


def review_usage(parent, child, prompt):
    """Prove inherited vs reset counters from first new provider usage, not size."""
    def is_prompt(record):
        p = record.get("payload", {})
        return (record.get("type") == "response_item" and p.get("role") == "user"
                and any(c.get("text") == prompt for c in p.get("content", []) if isinstance(c, dict)))

    start = next((i for i, r in enumerate(child) if is_prompt(r)), None)
    if start is None:
        raise ValueError("Fork review prompt missing from native history")
    initial, final = last_usage(parent), last_usage(child)
    if not initial or not final:
        raise ValueError("Native usage missing")
    keys = ("input_tokens", "cached_input_tokens", "output_tokens")
    mode = None
    for record in child[start + 1:]:
        info = record.get("payload", {}).get("info")
        if not isinstance(info, dict):
            continue
        total, last = info.get("total_token_usage"), info.get("last_token_usage")
        if not total or not last or all(total.get(k, 0) == initial.get(k, 0) for k in keys):
            continue
        if all(total.get(k, 0) == initial.get(k, 0) + last.get(k, 0) for k in keys):
            mode = "inherited"
        elif all(total.get(k, 0) == last.get(k, 0) for k in keys):
            mode = "reset"
        break
    if mode is None:
        raise ValueError("Cannot prove fork counter semantics; do not publish incremental cost")
    delta = {k: final.get(k, 0) - (initial.get(k, 0) if mode == "inherited" else 0) for k in keys}
    if any(v < 0 for v in delta.values()) or delta["cached_input_tokens"] > delta["input_tokens"]:
        raise ValueError("Invalid incremental usage")
    return {"counter_mode": mode, "initial": initial, "final": final,
            "incremental": delta, "incremental_total": delta["input_tokens"] + delta["output_tokens"],
            "incremental_uncached_input": delta["input_tokens"] - delta["cached_input_tokens"]}


def prepare(out, cases=CASES):
    if out.exists():
        raise FileExistsError(out)
    if not cases or len(set(cases)) != len(cases) or set(cases) - set(ALL_CASES):
        raise ValueError("Select distinct files from the existing ten-case benchmark")
    frozen = RAW.verify_manifest(iteration.BASELINE)
    out.mkdir(parents=True)
    package = out / "code/src/migloop"
    package.mkdir(parents=True)
    shutil.copy2(REPO / "src/migloop/__init__.py", package / "__init__.py")
    shutil.copytree(REPO / "src/migloop/inquiry", package / "inquiry",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(__file__, out / "driver.py")
    shutil.copy2(HERE / "paired-review-plan.md", out / "plan.md")
    config = BASE.read(RAW_HIGH / "runtime-settings.json")
    assert config["model_reasoning_effort"] == "high" and not config["mcp_servers"]
    cli = RAW.command(out, config)[0]
    manifest = {"schema": "inquiry-paired-review/1", "created": RAW.now(),
                "model": RAW.MODEL, "effort": "high", "timeout_seconds": 900,
                "automatic_retry": False, "baseline_replacement": False,
                "cli": cli, "cli_sha256": BASE.sha(cli), "cases": {},
                "code_inventory": BASE.tree_manifest(package),
                "driver_sha256": BASE.sha(__file__), "plan_sha256": BASE.sha(out / "plan.md")}
    manifest["dependencies"] = []
    (out / "runner-dependencies").mkdir()
    for source in (HERE / "audit_paired_review.py", HERE / "luna-audit.py", HERE / "iterate.py",
                   Path(BASE.__file__), Path(RAW.__file__), Path(RAW.OLD_RUNNER)):
        archive = Path("runner-dependencies") / source.name
        shutil.copy2(source, out / archive)
        manifest["dependencies"].append({"source": str(source), "archive": str(archive), "sha256": BASE.sha(source)})
    for identity in cases:
        case = next(c for c in frozen["cases"] if c["id"] == identity)
        prior = RAW_HIGH / "runs" / identity / "rep1"
        metric = BASE.read(prior / "metrics.json")
        if metric["actual_models"] != [RAW.MODEL] or metric["actual_effort"] != "high":
            raise ValueError("Original identity differs")
        native = RAW.parser().find_codex_transcript(metric["session_id"])
        if not native or BASE.sha(native) != BASE.sha(prior / "transcript.jsonl"):
            raise ValueError("Stored thread no longer equals frozen raw history")
        task = (RAW_HIGH / "tasks" / (identity + ".md")).read_text(encoding="utf-8")
        job = {"file": case["file"], "pool": case["pool"],
               "generation_end": re.search(r"生成结束：([^，\s]+)", task)[1],
               "observation_end": re.search(r"观察截止：([^，\s]+)", task)[1]}
        folder = out / identity
        folder.mkdir()
        db = folder / "index.sqlite"
        cmd = iteration.command(out, db)
        imported = subprocess.run(cmd + ["import", "--pool", case["pool"]],
                                  check=True, capture_output=True, text=True, encoding="utf-8", timeout=180)
        entry = {"task": job, "original": str(prior), "parent_session": metric["session_id"],
                 "parent_native": str(native), "parent_sha256": BASE.sha(native),
                 "baseline_files": {name: BASE.sha(prior / name) for name in
                                    ("report.md", "transcript.jsonl", "metrics.json", "events.jsonl")},
                 "pool_inventory": BASE.tree_manifest(case["pool"]),
                 "import": json.loads(imported.stdout), "arms": {}}
        for arm in ARMS:
            workspace = folder / arm / "workspace"
            workspace.mkdir(parents=True)
            # Explicit local skill, not an injected host skill catalogue.
            shutil.copy2(HERE / "review-skill/SKILL.md", workspace / "SKILL.md")
            shutil.copy2(prior / "report.md", workspace / "initial-report.md")
            BASE.save(workspace / "investigation.json", job)
            settings = {**config}
            prompt = (f"使用 {workspace / 'SKILL.md'}（UTF-8，须完整读取）复核你刚完成、"
                      f"封存在 {workspace / 'initial-report.md'} 的调查。任务在同目录 investigation.json。"
                      "本轮预算约 15 分钟，只交复核变更与未决项，原稿不重写、不构树。")
            if arm == "inquiry":
                shutil.copy2(HERE / "review-skill/query-reference.md", workspace / "query-reference.md")
                settings["mcp_servers"] = {"inquiry": {"command": cmd[0], "args": cmd[1:] + ["mcp"],
                    "required": True, "startup_timeout_sec": 45, "tool_timeout_sec": 120}}
                prompt += f" 原始读取仍可用，额外的 inquiry 查询说明在 {workspace / 'query-reference.md'}。"
            BASE.save(folder / arm / "settings.json", settings)
            (folder / arm / "prompt.md").write_text(prompt, encoding="utf-8")
            entry["arms"][arm] = {"workspace": str(workspace),
                "inventory": BASE.tree_manifest(workspace),
                "settings_sha256": BASE.sha(folder / arm / "settings.json"),
                "prompt_sha256": BASE.sha(folder / arm / "prompt.md")}
        manifest["cases"][identity] = entry
    BASE.save(out / "manifest.json", manifest)
    print(json.dumps({"prepared": str(out), "cases": list(cases), "model_calls": 0}), flush=True)


def verify(out, require_current_driver=False):
    m = BASE.read(out / "manifest.json")
    if BASE.sha(out / "driver.py") != m["driver_sha256"]:
        raise ValueError("Frozen driver changed")
    if require_current_driver and BASE.sha(__file__) != m["driver_sha256"]:
        raise ValueError("Execution driver differs from frozen run; audit-only access remains possible")
    for dep in m.get("dependencies", []):
        if BASE.sha(out / dep["archive"]) != dep["sha256"]:
            raise ValueError("Frozen dependency archive changed")
        if require_current_driver and BASE.sha(dep["source"]) != dep["sha256"]:
            raise ValueError("Execution dependency differs from frozen run")
    if BASE.sha(m["cli"]) != m["cli_sha256"] or BASE.sha(out / "plan.md") != m["plan_sha256"]:
        raise ValueError("CLI or preregistration changed")
    if BASE.tree_manifest(out / "code/src/migloop") != m["code_inventory"]:
        raise ValueError("Frozen inquiry changed")
    for identity, case in m["cases"].items():
        if BASE.sha(case["parent_native"]) != case["parent_sha256"]:
            raise ValueError("Parent thread changed")
        if BASE.tree_manifest(case["task"]["pool"]) != case["pool_inventory"]:
            raise ValueError("Source pool changed")
        for name, digest in case["baseline_files"].items():
            if BASE.sha(Path(case["original"]) / name) != digest:
                raise ValueError("Frozen raw artifact changed")
        for arm, values in case["arms"].items():
            if BASE.tree_manifest(values["workspace"]) != values["inventory"]:
                raise ValueError("Review workspace changed")
            for name in ("settings", "prompt"):
                suffix = ".json" if name == "settings" else ".md"
                if BASE.sha(out / identity / arm / (name + suffix)) != values[name + "_sha256"]:
                    raise ValueError("Arm instructions changed")
    return m


def run(out, identity, arm):
    m = verify(out, require_current_driver=True)
    case = m["cases"][identity]
    folder = out / identity / arm
    workspace = Path(case["arms"][arm]["workspace"])
    original_command = RAW.command
    prompt = (folder / "prompt.md").read_text(encoding="utf-8")
    RAW.EFFORT = "high"
    print(json.dumps({"started": identity, "arm": arm, "parent": case["parent_session"]}), flush=True)
    with patch.object(RAW, "command", lambda pool, config: fork_command(original_command(pool, config), case["parent_session"])):
        metric = RAW.launch(workspace, folder / "rep1", prompt, BASE.read(folder / "settings.json"), m["timeout_seconds"])
    verify(out, require_current_driver=True)
    audit = {"same_parent": case["parent_session"], "new_session": metric.get("session_id"),
             "completed": metric["status"] == "completed", "errors": []}
    try:
        if not (metric["actual_models"] == [RAW.MODEL] and metric["actual_effort"] == "high"
                and metric["recording_complete"] and metric["host_skill_catalog_absent"]
                and metric["session_id"] != case["parent_session"]):
            raise ValueError("Identity, recording, instructions or fork failed")
        parent = rows(Path(case["original"]) / "transcript.jsonl")
        child = rows(folder / "rep1/transcript.jsonl")
        spec = importlib.util.spec_from_file_location("paired_history", HERE / "audit_paired_review.py")
        history = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(history)
        audit.update(history.history_binding(parent, child, case["parent_session"],
                                             (Path(case["original"]) / "transcript.jsonl").stat().st_size))
        if not audit["native_history_binding_confirmed"]:
            raise ValueError("Fork did not bind the exact immutable original history")
        audit["usage"] = review_usage(parent, child, prompt)
    except (ValueError, KeyError, StopIteration) as error:
        audit["errors"].append(str(error))
    audit["valid_pair_member"] = not audit["errors"] and audit["completed"] and metric.get("report_present")
    BASE.save(folder / "rep1/fork-audit.json", audit)
    print(json.dumps({"finished": identity, "arm": arm, "seconds": metric["elapsed_seconds"],
                      "audit": audit}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "verify"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case", choices=ALL_CASES)
    parser.add_argument("--cases", choices=ALL_CASES, nargs="+", default=CASES, help="prepare only")
    parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    target = args.out.resolve()
    if args.mode == "prepare":
        prepare(target, tuple(args.cases))
    elif args.mode == "verify":
        verify(target)
        print(json.dumps({"verified": True, "model_calls": 0}))
    else:
        if not args.case or not args.arm:
            parser.error("run requires --case and --arm")
        run(target, args.case, args.arm)
