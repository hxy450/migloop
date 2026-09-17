"""Product skill belongs only to the tools arm; no model calls in these tests."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "docs/experiments/inquiry-20260911/run_skill_case.py"
    spec = importlib.util.spec_from_file_location("product_pair_test", source)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    baseline, pool, repo = [tmp_path / p for p in ("baseline", "pool", "repo")]
    for folder in (baseline, pool, repo / "src/migloop/inquiry", repo / "docs/skills/migloop-investigate"):
        folder.mkdir(parents=True)
    (pool / "session.jsonl").write_text('{}\n', encoding="utf-8")
    (repo / "src/migloop/__init__.py").write_text('', encoding="utf-8")
    (repo / "docs/skills/migloop-investigate/SKILL.md").write_text('product instructions', encoding="utf-8")
    (baseline / "task.md").write_text('生成结束：2026-01-01T01:00:00Z，观察截止：2026-01-02T01:00:00Z', encoding="utf-8")
    (baseline / "runtime-settings.json").write_text('{}', encoding="utf-8")
    monkeypatch.setattr(runner, "REPO", repo)
    monkeypatch.setattr(runner.iteration, "BASELINE", baseline)
    monkeypatch.setattr(runner.BASE.RAW, "verify_manifest", lambda _: {"cases": [
        {"id": "F10-01", "file": "pages/Page.ets", "pool": str(pool), "prompt": "task.md"}]})
    monkeypatch.setattr(runner.BASE.RAW, "host_skills", lambda: [])
    binary = tmp_path / "fake-codex.exe"
    binary.write_bytes(b"test executable identity only")
    monkeypatch.setattr(runner.BASE.RAW, "command", lambda *_: [str(binary), "-"])
    monkeypatch.setattr(runner.subprocess, "run", lambda *_a, **_k: SimpleNamespace(stdout='{"seconds": 0.1}'))
    return runner, tmp_path / "pair"


def test_raw_has_only_scope_and_one_sentence_without_product_instructions(prepared):
    runner, out = prepared
    runner.prepare(out, "F10-01", raw_control=True)
    manifest = runner.verify(out)
    raw = out / "raw-workspace"
    assert [p.name for p in raw.iterdir()] == ["investigation.json"]
    raw_job = runner.BASE.read(raw / "investigation.json")
    tool_job = runner.BASE.read(out / "workspace/investigation.json")
    assert set(raw_job) == {"file", "pool", "generation_end", "observation_end"}
    assert raw_job == {k: tool_job[k] for k in raw_job}
    prompt = (out / "raw-prompt.md").read_text(encoding="utf-8")
    assert prompt == runner.RAW_TASK and len(prompt) < 150 and prompt.count("。") == 1
    assert all(s not in prompt for s in ("skill", "inquiry", "复核", "节点", "spec", "Span"))
    assert (out / "prompt.md").read_text(encoding="utf-8").startswith(prompt)
    assert (out / "workspace/.agents/skills/migloop-investigate/SKILL.md").is_file()
    raw_config = runner.BASE.read(out / "raw-settings.json")
    tool_config = runner.BASE.read(out / "settings.json")
    assert raw_config["mcp_servers"] == {} and set(tool_config["mcp_servers"]) == {"inquiry"}
    assert {**tool_config, "mcp_servers": {}} == raw_config
    assert raw_config["model_reasoning_effort"] == "high"
    assert manifest["raw_control"]["fresh_threads"] and not manifest["raw_control"]["extra_review"]
    assert manifest["timeout_seconds"] == 1800 and not manifest["automatic_retry"]


@pytest.mark.parametrize("filename", ["SKILL.md", "initial-report.md", "query-reference.md"])
def test_raw_workspace_cannot_gain_hints_after_freeze(prepared, filename):
    runner, out = prepared
    runner.prepare(out, "F10-01", raw_control=True)
    (out / "raw-workspace" / filename).write_text("unexpected hint", encoding="utf-8")
    with pytest.raises(ValueError, match="Raw control workspace changed"):
        runner.verify(out)


def test_raw_run_reuses_recorder_once_without_fork_or_extra_turn(prepared, monkeypatch):
    runner, out = prepared
    runner.prepare(out, "F10-01", raw_control=True)
    calls = []
    monkeypatch.setattr(runner.BASE.RAW, "launch", lambda *a: calls.append(a) or {"status": "completed"})
    runner.run_raw(out)
    assert len(calls) == 1
    workspace, destination, prompt, config, timeout = calls[0]
    assert Path(workspace) == out / "raw-workspace"
    assert destination == out / "runs/raw/rep1"
    assert prompt == runner.RAW_TASK and config["mcp_servers"] == {} and timeout == 1800


def test_legacy_skill_preparation_does_not_silently_gain_raw_control(prepared):
    runner, out = prepared
    runner.prepare(out, "F10-01")
    assert "raw_control" not in runner.verify(out)
    assert not (out / "raw-workspace").exists()
    with pytest.raises(ValueError, match="explicit product pair"):
        runner.run_raw(out)


def test_changed_execution_dependency_blocks_run(prepared):
    runner, out = prepared
    runner.prepare(out, "F10-01", raw_control=True)
    manifest = runner.BASE.read(out / "manifest.json")
    dependency = out / "dependency.py"
    dependency.write_text("before", encoding="utf-8")
    manifest["dependencies"][str(dependency)] = runner.BASE.sha(dependency)
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    dependency.write_text("after", encoding="utf-8")
    with pytest.raises(ValueError, match="execution dependency changed"):
        runner.verify(out)


def test_mcp_only_mode_keeps_product_skill_and_original_task_without_extra_raw_run(prepared):
    runner, out = prepared
    runner.prepare(out, "F10-01", investigation_mode="mcp")
    manifest = runner.verify(out)
    assert manifest["investigation_mode"] == "mcp"
    assert "raw_control" not in manifest and not (out / "raw-workspace").exists()
    prompt = (out / "prompt.md").read_text(encoding="utf-8")
    assert prompt.startswith(runner.RAW_TASK)
    assert "调查原始转录只使用 inquiry MCP" in prompt
    assert (out / "workspace/.agents/skills/migloop-investigate/SKILL.md").read_text(encoding="utf-8") == "product instructions"
    assert runner.BASE.read(out / "settings.json")["model_reasoning_effort"] == "high"
    assert len(manifest["executables"]) == 2
    binary = next(Path(p) for p in manifest["executables"] if p.endswith("fake-codex.exe"))
    binary.write_bytes(b"changed executable")
    with pytest.raises(ValueError, match="execution dependency changed"):
        runner.verify(out)
