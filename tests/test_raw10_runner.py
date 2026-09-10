"""Offline baseline gates. No model calls or real source-pool changes."""
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "docs/experiments/file-first-10"


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE/(name+".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


run = module("run_raw10")
prepare = module("prepare_raw10")


def test_exact_ten_files_and_all_core_units():
    units = prepare.validate_contract(prepare.read(HERE/"selection.json"), prepare.read(HERE/"reference-units.json"), prepare.read(HERE/"scoring-core.json"))
    assert len(units) == 28


def test_contract_rejects_missing_case_and_duplicate_file():
    selection, reference, core = [prepare.read(HERE/x) for x in ("selection.json", "reference-units.json", "scoring-core.json")]
    reference["cases"].pop()
    with pytest.raises(ValueError, match="mismatch"):
        prepare.validate_contract(selection, reference, core)
    selection["cases"][-1] = selection["cases"][0]
    with pytest.raises(ValueError, match="distinct"):
        prepare.validate_contract(selection, reference, core)


def test_core_unit_cannot_silently_disappear():
    selection, reference, core = [prepare.read(HERE/x) for x in ("selection.json", "reference-units.json", "scoring-core.json")]
    core["units"].pop(next(iter(core["units"])))
    with pytest.raises(ValueError, match="match reference"):
        prepare.validate_contract(selection, reference, core)


def test_no_seeded_defect_questions_in_public_template():
    template = (HERE/"task-template.md").read_text(encoding="utf-8")
    assert "{target_file}" in template
    for word in ("AC14", "4dp", "priceDigits", "setDebug", "D-010", "HitTestMode", "signingConfig", "F10-"):
        assert word not in template


def test_artifacts_never_overwritten(tmp_path):
    p = tmp_path/"result.json"
    run.save(p, {"initial": True})
    with pytest.raises(FileExistsError):
        run.save(p, {"initial": False})
    assert run.read(p) == {"initial": True}


def test_skill_disable_is_per_run_and_shell_enabled():
    config = run.settings(["C:/test/skills/one/SKILL.md"])
    assert config["features.shell_tool"]
    assert config["features.multi_agent"] is False
    assert config["features.plugins"] is False
    assert config["web_search"] == "disabled"
    assert config["mcp_servers"] == {}
    assert len(config["skills.config"]) == 2
    assert all(x["enabled"] is False for x in config["skills.config"])


def test_instruction_audit_checks_developer_catalog_not_quoted_history(tmp_path):
    p = tmp_path/"transcript.jsonl"
    records = [{"type":"response_item", "payload":{"type":"message","role": role,
        "content":[{"type":"input_text","text":"### Available skills\n- example"}]}} for role in ("user", "assistant")]
    p.write_text("\n".join(json.dumps(x) for x in records), encoding="utf-8")
    assert run.instruction_audit(p)["host_skill_catalog_absent"]
    records.append({"type":"response_item", "payload":{"type":"message","role":"developer",
        "content":[{"type":"input_text","text":"### Available skills\n- example"}]}})
    p.write_text("\n".join(json.dumps(x) for x in records), encoding="utf-8")
    assert not run.instruction_audit(p)["host_skill_catalog_absent"]


def test_refuse_unfrozen_baseline(tmp_path):
    run.save(tmp_path/"manifest.json", {"status":"draft"})
    with pytest.raises(ValueError, match="frozen"):
        run.verify_manifest(tmp_path)


def test_sentinel_alone_cannot_pass_smoke(tmp_path):
    (tmp_path/"run").mkdir()
    run.save(tmp_path/"runtime-settings.json", {})
    run.save(tmp_path/"smoke.json", {"passed":True, "settings_sha256":run.sha(tmp_path/"runtime-settings.json"),
        "metrics":{"actual_models":["gpt-5.6-luna"],"actual_effort":"medium","recording_complete":True,"host_skill_catalog_absent":True}})
    run.save(tmp_path/"run/result.json", {"calls":{"seq":[]}})
    with pytest.raises(ValueError, match="actual successful command"):
        prepare.validate_smoke(tmp_path)
