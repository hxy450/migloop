"""One raw investigation, then resume its exact thread for evidence-tree review.

No production edits, gold-fed messages, replacement runs or hand-repaired cards.
Reuse the frozen launcher/recorder; only its per-process command adapter adds resume.
"""

import argparse
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
spec = importlib.util.spec_from_file_location(
    "two_stage_iteration", HERE / "iterate.py"
)
iteration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iteration)
BASE, RAW = iteration.BASE, iteration.BASE.RAW
RAW_HIGH = iteration.BASELINE.parent / "raw-high-i20-match-20260912"


def resume_command(command, session_id):
    UUID(session_id)  # Never --last: another user's session may have run meanwhile.
    if command[-1] != "-" or "resume" in command:
        raise ValueError("Expected an ordinary stdin exec command")
    return command[:-1] + ["resume", session_id, "-"]


def prepare(out):
    if out.exists():
        raise FileExistsError(out)
    baseline = RAW.verify_manifest(iteration.BASELINE)
    case = next(c for c in baseline["cases"] if c["id"] == "F10-03")
    out.mkdir(parents=True)
    package = out / "code/src/migloop"
    package.mkdir(parents=True)
    shutil.copy2(REPO / "src/migloop/__init__.py", package / "__init__.py")
    shutil.copytree(
        REPO / "src/migloop/inquiry",
        package / "inquiry",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    workspace = out / "workspace"
    workspace.mkdir()
    staged_skill = out / "staged-skill"
    shutil.copytree(REPO / "docs/skills/migloop-investigate", staged_skill)
    shutil.copy2(HERE / "two-stage-card-skill.md", staged_skill / "SKILL.md")
    job = {
        "file": case["file"],
        "generation_end": "2026-09-03T16:46:30.036Z",
        "observation_end": "2026-09-03T22:09:07.188Z",
        "pool": case["pool"],
        "runtime": {
            "python": str(BASE.DEFAULT_PYTHON),
            "code_root": str(out / "code/src"),
            "index_path": str(out / "index.sqlite"),
        },
    }
    BASE.save(workspace / "investigation.json", job)
    cmd = iteration.command(out, out / "index.sqlite")
    imported = subprocess.run(
        cmd + ["import", "--pool", case["pool"]],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    first = BASE.read(RAW_HIGH / "runtime-settings.json")
    assert not first["mcp_servers"] and first["model_reasoning_effort"] == "high"
    second = {
        **first,
        "mcp_servers": {
            "inquiry": {
                "command": cmd[0],
                "args": cmd[1:] + ["mcp"],
                "required": True,
                "startup_timeout_sec": 45,
                "tool_timeout_sec": 120,
            }
        },
    }
    for name, config in (
        ("phase1-settings.json", first),
        ("phase2-settings.json", second),
    ):
        BASE.save(out / name, config)
    shutil.copy2(RAW_HIGH / "tasks/F10-03.md", out / "phase1-prompt.md")
    prompt = (
        f"工作目录为 {workspace}。使用 $migloop-build-card（{workspace / '.agents/skills/migloop-build-card/SKILL.md'}），"
        "对你刚完成且已冻结在 initial-report.md 的调查进行构树与证据复核，"
        "保存 investigation.json 指定文件的可载入卡片。原稿不是标准答案；"
        "只有实际证据支持才改变判断，并按技能说明记录复核变更。"
    )
    (out / "phase2-prompt.md").write_text(prompt, encoding="utf-8")
    shutil.copy2(__file__, out / "driver.py")
    shutil.copy2(HERE / "luna-audit.py", out / "luna-audit.py")
    cli = RAW.command(workspace, first)[0]
    BASE.save(
        out / "manifest.json",
        {
            "schema": "inquiry-two-stage/1",
            "case": case,
            "model": "gpt-5.6-luna",
            "effort": "high",
            "created": RAW.now(),
            "product_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=REPO,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "workspace": str(workspace),
            "code_root": str(out / "code/src"),
            "index_path": str(out / "index.sqlite"),
            "code_inventory": BASE.tree_manifest(package),
            "pool_inventory": BASE.tree_manifest(case["pool"]),
            "phase1_workspace_inventory": BASE.tree_manifest(workspace),
            "staged_skill_inventory": BASE.tree_manifest(staged_skill),
            "files": {
                name: BASE.sha(out / name)
                for name in (
                    "phase1-settings.json",
                    "phase2-settings.json",
                    "phase1-prompt.md",
                    "phase2-prompt.md",
                    "driver.py",
                    "luna-audit.py",
                )
            },
            "cli": cli,
            "cli_sha256": BASE.sha(cli),
            "import": json.loads(imported.stdout),
            "timeouts": {"phase1": 1800, "phase2": 1200},
            "automatic_retry": False,
            "manual_report_repair": False,
            "baseline_replacement": False,
            "limits": "One exposed development case; extra time and review instructions are treatment differences. Not a causal ablation of mechanical checks alone.",
        },
    )
    print(json.dumps({"prepared": str(out), "model_calls": 0}), flush=True)


def verify(out, phase2=False):
    m = BASE.read(out / "manifest.json")
    for key, path in (
        ("code_inventory", out / "code/src/migloop"),
        ("pool_inventory", Path(m["case"]["pool"])),
        ("staged_skill_inventory", out / "staged-skill"),
    ):
        if BASE.tree_manifest(path) != m[key]:
            raise ValueError("Frozen inventory changed: " + key)
    for name, digest in m["files"].items():
        if BASE.sha(out / name) != digest:
            raise ValueError("Frozen file changed: " + name)
    if (
        BASE.sha(__file__) != m["files"]["driver.py"]
        or BASE.sha(m["cli"]) != m["cli_sha256"]
    ):
        raise ValueError("Driver or CLI changed")
    expected = (
        BASE.read(out / "phase2-seal.json")["workspace_inventory"]
        if phase2
        else m["phase1_workspace_inventory"]
    )
    if BASE.tree_manifest(m["workspace"]) != expected:
        raise ValueError("Investigator workspace changed")
    if phase2:
        seal = BASE.read(out / "phase1-seal.json")
        for name, digest in seal["artifacts"].items():
            if BASE.sha(out / "runs/free/rep1" / name) != digest:
                raise ValueError("Frozen first-stage artifact changed")
    return m


def require_identity(metric):
    if not (
        metric["status"] == "completed"
        and metric["actual_models"] == ["gpt-5.6-luna"]
        and metric["actual_effort"] == "high"
        and metric["recording_complete"]
        and metric["host_skill_catalog_absent"]
        and metric["report_present"]
    ):
        raise ValueError(
            "Investigator failed completion/identity/recording checks; do not replace run"
        )


def run(out):
    m = verify(out)
    RAW.EFFORT = "high"
    workspace = Path(m["workspace"])
    first_dir, second_dir = out / "runs/free/rep1", out / "runs/inquiry/rep1"
    print(json.dumps({"phase": "free_investigation", "started": RAW.now()}), flush=True)
    first = RAW.launch(
        Path(m["case"]["pool"]),
        first_dir,
        (out / "phase1-prompt.md").read_text(encoding="utf-8"),
        BASE.read(out / "phase1-settings.json"),
        m["timeouts"]["phase1"],
    )
    require_identity(first)
    verify(out)
    BASE.save(
        out / "phase1-seal.json",
        {
            "session_id": first["session_id"],
            "sealed_at": RAW.now(),
            "artifacts": {
                name: BASE.sha(first_dir / name)
                for name in (
                    "report.md",
                    "transcript.jsonl",
                    "events.jsonl",
                    "metrics.json",
                )
            },
        },
    )
    print(
        json.dumps(
            {
                "phase": "first_report_frozen",
                "session_id": first["session_id"],
                "seconds": first["elapsed_seconds"],
                "report_sha256": BASE.sha(first_dir / "report.md"),
            }
        ),
        flush=True,
    )
    shutil.copy2(first_dir / "report.md", workspace / "initial-report.md")
    skill = workspace / ".agents/skills/migloop-build-card"
    skill.parent.mkdir(parents=True)
    shutil.copytree(out / "staged-skill", skill)
    BASE.save(
        out / "phase2-seal.json",
        {
            "session_id": first["session_id"],
            "activated_at": RAW.now(),
            "workspace_inventory": BASE.tree_manifest(workspace),
        },
    )
    verify(out, phase2=True)
    original_command = RAW.command

    def resumed(pool, config):
        return resume_command(original_command(pool, config), first["session_id"])

    print(json.dumps({"phase": "resume_for_tree", "started": RAW.now()}), flush=True)
    with patch.object(RAW, "command", resumed):
        second = RAW.launch(
            workspace,
            second_dir,
            (out / "phase2-prompt.md").read_text(encoding="utf-8"),
            BASE.read(out / "phase2-settings.json"),
            m["timeouts"]["phase2"],
        )
    require_identity(second)
    verify(out, phase2=True)
    prefix = (first_dir / "transcript.jsonl").read_bytes()
    joined = (second_dir / "transcript.jsonl").read_bytes()
    continuity = {
        "same_session": first["session_id"] == second["session_id"],
        "first_transcript_is_exact_prefix": joined.startswith(prefix),
        "first_transcript_bytes": len(prefix),
        "full_transcript_bytes": len(joined),
    }
    BASE.save(out / "continuity.json", continuity)
    if not all(
        continuity[k] for k in ("same_session", "first_transcript_is_exact_prefix")
    ):
        raise ValueError("Resume did not preserve the exact first-stage transcript")
    audit = subprocess.run(
        [
            str(BASE.DEFAULT_PYTHON),
            "-B",
            "-X",
            "utf8",
            str(out / "luna-audit.py"),
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    (out / "audit.stdout.txt").write_text(audit.stdout, encoding="utf-8")
    (out / "audit.stderr.txt").write_text(audit.stderr, encoding="utf-8")
    if audit.returncode:
        raise ValueError("Native delivery audit failed; preserve artifacts")
    delivery = BASE.read(second_dir / "delivery-audit.json")
    checked = subprocess.run(
        [
            str(BASE.DEFAULT_PYTHON),
            "-B",
            "-X",
            "utf8",
            str(skill / "scripts/check_card.py"),
            "--task",
            str(workspace / "investigation.json"),
            "--report",
            delivery["report_id"],
            "--full",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    BASE.save(second_dir / "card-audit.json", json.loads(checked.stdout))
    print(
        json.dumps(
            {
                "completed": True,
                "same_session": True,
                "report_id": delivery["report_id"],
                "phase1_seconds": first["elapsed_seconds"],
                "phase2_seconds": second["elapsed_seconds"],
                "card_exit": checked.returncode,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "verify"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    target = args.out.resolve()
    if args.mode == "prepare":
        prepare(target)
    elif args.mode == "run":
        run(target)
    else:
        verify(target, phase2=(target / "phase2-seal.json").exists())
        print(json.dumps({"verified": True, "model_calls": 0}))
