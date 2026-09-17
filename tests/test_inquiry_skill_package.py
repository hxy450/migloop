"""Selectable skill packages and native delivery checks; never call a model."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_inquiry_product_pair import prepared


@pytest.fixture
def package(prepared):
    runner, out = prepared
    source = out.parent / "migloop-case-card"
    (source / "references").mkdir(parents=True)
    (source / "SKILL.md").write_text("新卡片技能：先提交原稿，再复核。", encoding="utf-8")
    (source / "references/mcp.md").write_text("本包完整调用约定。", encoding="utf-8")
    return runner, out, source


def native_delivery(run_dir, source):
    run_dir.mkdir(parents=True)
    records = [
        {"type": "response_item", "payload": {"type": "message", "role": "user",
            "content": [{"text": "<skill>\n" + (source / "SKILL.md").read_text(encoding="utf-8") + "\n</skill>"}]}},
        {"type": "response_item", "payload": {"type": "function_call_output",
            "output": json.dumps({"output": (source / "references/mcp.md").read_text(encoding="utf-8")})}},
    ]
    (run_dir / "transcript.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in records), encoding="utf-8")


def test_selected_package_has_short_prompt_and_independent_frozen_input(package):
    runner, out, source = package
    inputs = out.parent / "isolated-inputs"
    runner.prepare(out, "F10-01", skill_source=source, skill_name="migloop-case-card", isolated_inputs=inputs)
    manifest = runner.verify(out)
    deployed = inputs / "mcp/workspace/.agents/skills/migloop-case-card"
    assert manifest["skill_name"] == "migloop-case-card"
    assert Path(manifest["skill_source"]) == source
    assert Path(manifest["skill_path"]) == deployed
    assert manifest["skill_source_inventory"] == manifest["skill_inventory"] == runner.BASE.tree_manifest(source)
    assert set(p.name for p in deployed.parent.iterdir()) == {"migloop-case-card"}
    assert not (deployed / "scripts").exists()
    assert "raw_control" not in manifest
    assert (out / "prompt.md").read_text(encoding="utf-8") == (
        "使用 $migloop-case-card，为 investigation.json 指定的被修文件制作归因卡。")
    assert "not an unguided raw" in manifest["comparison_limit"]
    assert manifest["investigation_mode"] == "free"
    assert len(manifest["executables"]) == 2
    assert runner.BASE.tree_manifest(inputs / "mcp/pool") == runner.BASE.tree_manifest(out.parent / "pool")
    (deployed / "SKILL.md").write_text("changed after freeze", encoding="utf-8")
    with pytest.raises(ValueError, match="workspace_inventory"):
        runner.verify(out)


def test_skill_name_can_be_inferred_from_source_and_delivery_uses_deployed_files(package):
    runner, out, source = package
    runner.prepare(out, "F10-01", skill_source=source)
    manifest = runner.verify(out)
    assert manifest["skill_name"] == source.name
    run_dir = out / "runs/inquiry/rep1"
    native_delivery(run_dir, source)
    result = runner.audit_skill_delivery(out)
    assert result["full_instruction_delivery"] and result["native_skill_injected"]
    assert result["skill_name"] == "migloop-case-card"
    assert Path(result["skill_path"]) == Path(manifest["skill_path"])
    assert result["instruction_hashes"] == {name: runner.BASE.sha(source / name)
        for name in ("SKILL.md", "references/mcp.md")}


def test_explicit_name_resolves_default_skill_source(package):
    runner, out, source = package
    destination = runner.REPO / "docs/skills/migloop-case-card"
    runner.shutil.copytree(source, destination)
    runner.prepare(out, "F10-01", skill_name="migloop-case-card")
    assert Path(runner.verify(out)["skill_source"]) == destination


@pytest.mark.parametrize("name", ["../wrong", "nested/skill", "nested\\skill"])
def test_invalid_skill_names_fail_before_creating_workspace(package, name):
    runner, out, source = package
    with pytest.raises(ValueError, match="single skill directory"):
        runner.prepare(out, "F10-01", skill_source=source, skill_name=name)
    assert not out.exists()


@pytest.mark.parametrize("has_script", [False, True])
def test_run_records_optional_checker_status_and_uses_actual_package(package, monkeypatch, has_script):
    runner, out, source = package
    if has_script:
        (source / "scripts").mkdir()
        (source / "scripts/check_card.py").write_text("# frozen optional checker", encoding="utf-8")
    runner.prepare(out, "F10-01", skill_source=source)
    calls, launches = [], []

    def fake_launch(*args):
        launches.append(args)
        native_delivery(out / "runs/inquiry/rep1", source)
        return {"status": "completed"}

    def fake_subprocess(args, **kwargs):
        calls.append(args)
        if str(out / "luna-audit.py") in args:
            runner.BASE.save(out / "runs/inquiry/rep1/verdict.json", {"report_id": "report-last"})
            return SimpleNamespace(stdout="{}", stderr="", returncode=0)
        return SimpleNamespace(stdout='{"status":"ready_for_review"}', stderr="", returncode=0)

    monkeypatch.setattr(runner.BASE.RAW, "launch", fake_launch)
    monkeypatch.setattr(runner.subprocess, "run", fake_subprocess)
    runner.run(out)
    assert len(launches) == 1
    assert runner.BASE.read(out / "runs/inquiry/rep1/skill-delivery.json")["full_instruction_delivery"]
    card = runner.BASE.read(out / "runs/inquiry/rep1/card-audit.json")
    if has_script:
        assert len(calls) == 2
        assert str(out / "workspace/.agents/skills/migloop-case-card/scripts/check_card.py") in calls[-1]
        assert card["status"] == "ready_for_review"
    else:
        assert len(calls) == 1
        assert card["status"] == "not_run"
        assert card["native_delivery_audit_exit_code"] == 0
        assert "optional" in card["reason"]
