"""Experiment plumbing only; no model calls or changes to frozen benchmarks."""

import importlib.util
from pathlib import Path

import pytest

DRIVER = (
    Path(__file__).parents[1] / "docs/experiments/inquiry-20260911/run_two_stage.py"
)
spec = importlib.util.spec_from_file_location("two_stage_test", DRIVER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_resume_preserves_options_and_requires_explicit_uuid():
    command = [
        "codex",
        "-a",
        "never",
        "exec",
        "--json",
        "--sandbox",
        "read-only",
        "-C",
        "workspace",
        "-",
    ]
    identity = "11111111-1111-4111-8111-111111111111"
    resumed = runner.resume_command(command, identity)
    assert resumed == command[:-1] + ["resume", identity, "-"]
    assert command[-1] == "-" and "resume" not in command
    with pytest.raises(ValueError):
        runner.resume_command(command, "--last")


def test_identity_failure_cannot_silently_continue():
    valid = {
        "status": "completed",
        "actual_models": ["gpt-5.6-luna"],
        "actual_effort": "high",
        "recording_complete": True,
        "host_skill_catalog_absent": True,
        "report_present": True,
    }
    runner.require_identity(valid)
    for key, value in (
        ("status", "timeout"),
        ("actual_models", ["another-model"]),
        ("actual_effort", "medium"),
        ("recording_complete", False),
    ):
        with pytest.raises(ValueError):
            runner.require_identity({**valid, key: value})


def test_first_report_seal_rejects_later_rewrite(tmp_path):
    package, pool, skill, workspace = [
        tmp_path / name
        for name in ("code/src/migloop", "pool", "staged-skill", "workspace")
    ]
    for path in (package, pool, skill, workspace, tmp_path / "runs/free/rep1"):
        path.mkdir(parents=True)
    (tmp_path / "driver.py").write_bytes(DRIVER.read_bytes())
    cli = tmp_path / "cli-marker"
    cli.write_text("not executed", encoding="utf-8")
    report = tmp_path / "runs/free/rep1/report.md"
    report.write_text("frozen first report", encoding="utf-8")
    save = runner.BASE.save
    inventory = runner.BASE.tree_manifest
    save(
        tmp_path / "manifest.json",
        {
            "code_inventory": inventory(package),
            "pool_inventory": inventory(pool),
            "case": {"pool": str(pool)},
            "staged_skill_inventory": inventory(skill),
            "workspace": str(workspace),
            "files": {"driver.py": runner.BASE.sha(DRIVER)},
            "cli": str(cli),
            "cli_sha256": runner.BASE.sha(cli),
        },
    )
    save(tmp_path / "phase2-seal.json", {"workspace_inventory": inventory(workspace)})
    save(
        tmp_path / "phase1-seal.json",
        {"artifacts": {"report.md": runner.BASE.sha(report)}},
    )
    runner.verify(tmp_path, phase2=True)
    report.write_text("silently replaced", encoding="utf-8")
    with pytest.raises(ValueError, match="first-stage"):
        runner.verify(tmp_path, phase2=True)


def test_two_stage_skill_contains_no_case_specific_answer_terms():
    skill = (DRIVER.parent / "two-stage-card-skill.md").read_text(encoding="utf-8")
    for term in ("Dice", "Roll", "ROLL", "hilog", "AC14", "textAllCaps"):
        assert term not in skill
    assert "initial-report.md" in skill
    # This checks disclosure boundaries, not skill quality or model compliance.
