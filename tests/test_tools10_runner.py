"""Offline tools-arm contracts. Paid/model launch is always stubbed here."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


HERE = Path(__file__).resolve().parents[1] / "docs/experiments/file-first-10"
SPEC = importlib.util.spec_from_file_location("run_tools10_offline_tests", HERE / "run_tools10.py")
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)


@pytest.fixture
def paired(tmp_path, monkeypatch):
    base = tmp_path / "raw"
    base.mkdir()
    (base / "tasks").mkdir()
    source = tmp_path / "source"
    (source / "src/migloop/assets").mkdir(parents=True)
    (source / "src/migloop/__init__.py").write_text("# frozen package\n", encoding="utf-8")
    (source / "src/migloop/assets/help.txt").write_text("neutral help", encoding="utf-8")
    source_files, pools = [], []
    for index, (total, jsonls) in enumerate(((290, 146), (144, 80), (2, 2))):
        pool = tmp_path / f"pool{index}" / "pool"
        (pool / "root-early/subagents").mkdir(parents=True)
        for number in range(jsonls):
            path = pool / ("root-early.jsonl" if number == 0 else "root-late.jsonl" if number == 1
                           else f"root-early/subagents/agent-{number:04d}.jsonl")
            path.write_text(json.dumps({"timestamp": f"2026-01-0{1 if number != 1 else 2}T00:00:00Z",
                "cwd": "/project", "type": "user", "message": {"role": "user", "content": "original task"}}) + "\n",
                encoding="utf-8")
            source_files.append({"path": str(path), "sha256": run.sha(path)})
        for number in range(total - jsonls):
            (pool / f"meta-{number}.json").write_text("{}\n", encoding="utf-8")
        manifest = run.tree_manifest(pool)
        run.save(pool.parent / "pool-manifest.json", {**manifest, "origins": [{"original": "/unavailable/ignored"}]})
        pools.append(pool)
    cases = []
    for number in range(10):
        name = f"F10-{number + 1:02d}"
        text = (f"调查文件：entry/File{number}.ets\r\n生成结束：2026-01-01T00:00:00Z，原始记录：root-early.jsonl:1\r\n"
                "观察截止：2026-01-03T00:00:00Z，原始记录：root-late.jsonl:1\r\n"
                "中性原始问题。不要求 YAML；本轮使用只读 shell。\r\n")
        path = base / f"tasks/{name}.md"
        path.write_bytes(text.encode("utf-8"))
        cases.append({"id": name, "file": f"entry/File{number}.ets", "pool": str(pools[number % 3]),
                      "prompt": f"tasks/{name}.md", "exposure": "fixture"})
    raw = {"status": "frozen_ready_for_raw", "model": run.MODEL, "effort": run.EFFORT,
           "repetitions": 2, "concurrency": 2, "timeout_seconds": 1800, "cases": cases, "source_files": source_files}
    run.save(base / "manifest.json", raw)
    run.save(base / "runtime-settings.json", run.RAW.settings(["/disabled/SKILL.md"]))
    monkeypatch.setattr(run.RAW, "verify_manifest", lambda path: run.read(Path(path) / "manifest.json"))
    return {"base": base, "source": source, "python": Path(sys.executable), "raw": raw,
            "out": tmp_path / "tools", "pools": pools}


def prepare(fixture):
    return run.prepare(fixture["out"], fixture["base"], source=fixture["source"], python=fixture["python"])


def mark_smoke(fixture):
    manifest = run.read(fixture["out"] / "manifest.json")
    run.save(fixture["out"] / "mcp-smoke.json", {"passed": True, "code_digest": manifest["code_digest"],
        "tools_manifest_sha256": run.sha(fixture["out"] / "manifest.json"), "pools": [
            {"pool": pool["pool"], "passed": True, "batch_content_verified": True, "registry": {"matches": True}}
            for pool in manifest["pools"]]})


def test_prepare_copies_exact_raw_tasks_full_code_and_complete_pool_bytes(paired):
    before = run.sha(paired["base"] / "manifest.json")
    summary = prepare(paired)
    assert summary["pool_files"] == 436 and summary["model_started"] is False
    manifest = run.verify(paired["out"])
    assert (manifest["model"], manifest["effort"], manifest["repetitions"], manifest["concurrency"],
            manifest["timeout_seconds"]) == ("gpt-5.6-luna", "medium", 2, 2, 1800)
    assert len(manifest["cases"]) == 10
    for case in manifest["cases"]:
        original = Path(case["raw_prompt"]).read_bytes()
        final = (paired["out"] / case["prompt"]).read_bytes()
        assert final.startswith(original) and case["raw_prompt_sha256"] == run.sha(case["raw_prompt"])
        assert b"migloop-verdict/3" in final and b"migloop-verdict-ref" in final
    assert (paired["out"] / "code/src/migloop/assets/help.txt").read_text() == "neutral help"
    assert not (paired["out"] / "private").exists()
    assert run.sha(paired["base"] / "manifest.json") == before


def test_only_shell_and_mcp_settings_differ_from_frozen_raw(paired):
    prepare(paired)
    manifest = run.read(paired["out"] / "manifest.json")
    config = run.read(paired["out"] / manifest["cases"][0]["settings"])
    raw = run.read(paired["base"] / "runtime-settings.json")
    assert config["features.shell_tool"] is False
    server = config["mcp_servers"]["migloop"]
    assert server["enabled_tools"] == list(run.ENABLED_TOOLS)
    assert server["required"] is True and server["args"][:2] == ["-I", "-B"]
    assert server["args"][2:4] == ["-X", "utf8"]
    assert (paired["out"] / "code/src").as_posix() in server["args"][-1]
    assert str(paired["source"]) not in server["args"][-1]
    assert server["env"]["MIGLOOP_FINAL_MODE"] == "document"
    assert len(json.loads(server["env"]["MIGLOOP_FROZEN_ROOTS"])) == 2
    config.update({"features.shell_tool": True, "mcp_servers": {}})
    assert config == raw


@pytest.mark.parametrize("change", ["sidecar", "extra", "jsonl", "pyc"])
def test_complete_old_pool_manifest_rejects_drift_not_just_jsonl(paired, change):
    pool = paired["pools"][0]
    path = pool / {"sidecar": "meta-0.json", "extra": "unexpected.txt", "jsonl": "root-early.jsonl", "pyc": "extra.pyc"}[change]
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest drift"):
        prepare(paired)
    assert not paired["out"].exists()


def test_freeze_refuses_unexpected_model_budget_and_existing_output(paired):
    paired["raw"]["timeout_seconds"] = 1801
    (paired["base"] / "manifest.json").write_text(json.dumps(paired["raw"]), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        prepare(paired)
    paired["raw"]["timeout_seconds"] = 1800
    (paired["base"] / "manifest.json").write_text(json.dumps(paired["raw"]), encoding="utf-8")
    paired["out"].mkdir()
    with pytest.raises(ValueError, match="new and separate"):
        prepare(paired)


def test_runtime_is_frozen_not_live_but_frozen_edits_are_rejected(paired):
    prepare(paired)
    (paired["source"] / "src/migloop/__init__.py").write_text("later working edit", encoding="utf-8")
    assert run.verify(paired["out"])
    (paired["out"] / "code/src/migloop/extra.py").write_text("unfrozen", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory drift"):
        run.verify(paired["out"])


def test_source_change_during_copy_never_creates_runnable_manifest(paired, monkeypatch):
    original = run.shutil.copytree

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        (paired["source"] / "src/migloop/__init__.py").write_text("race", encoding="utf-8")
        return result

    monkeypatch.setattr(run.shutil, "copytree", changed)
    with pytest.raises(ValueError, match="during freeze"):
        prepare(paired)
    assert not (paired["out"] / "manifest.json").exists()


def test_raw_manifest_and_frozen_settings_are_still_authenticated(paired):
    prepare(paired)
    (paired["base"] / "manifest.json").write_text(json.dumps({**paired["raw"], "extra": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="Raw baseline manifest drift"):
        run.verify(paired["out"])


@pytest.mark.parametrize("field,value", [("timeout_seconds", 3600), ("format_repair", True)])
def test_verify_rejects_changed_runtime_policy(paired, field, value):
    prepare(paired)
    path = paired["out"] / "manifest.json"
    data = run.read(path)
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Paired runtime condition drift"):
        run.verify(paired["out"])


def test_launcher_is_raw_once_no_format_repair_and_cost_includes_final(paired, monkeypatch):
    prepare(paired)
    manifest = run.read(paired["out"] / "manifest.json")
    calls = []

    def launch(pool, out, prompt, config, timeout):
        calls.append((pool, prompt, config, timeout))
        out.mkdir(parents=True)
        (out / "report.md").write_text("真实但不合格式的最终回答", encoding="utf-8")
        metric = {"status": "completed", "elapsed_seconds": 12, "usage": {"output": 99},
                  "actual_models": [run.MODEL], "actual_effort": run.EFFORT,
                  "recording_complete": True, "host_skill_catalog_absent": True}
        run.save(out / "metrics.json", metric)
        return metric

    def check(out, manifest, case, directory):
        run.save(directory / "verdict.json", {"errors": ["missing verdict block"], "format_repair": False})
        return {"status": "completed", "elapsed_seconds": 2, "model_calls": 0}

    monkeypatch.setattr(run.RAW, "launch", launch)
    monkeypatch.setattr(run, "postprocess", check)
    metric = run.launch_case(paired["out"], manifest, manifest["cases"][0], 1)
    assert len(calls) == 1 and calls[0][-1] == 1800
    assert metric["usage"]["output"] == 99 and metric["structured_output_cost_included"]
    assert metric["format_repair"] is False and metric["postprocess"]["model_calls"] == 0
    directory = paired["out"] / "runs/F10-01/rep1"
    assert (directory / "raw-launch-metrics.json").exists()
    assert (directory / "report.md").read_text(encoding="utf-8") == "真实但不合格式的最终回答"
    assert run.read(directory / "verdict.json")["errors"]


def test_postprocessor_is_isolated_frozen_code_and_never_model_launcher(paired, monkeypatch):
    prepare(paired)
    manifest = run.read(paired["out"] / "manifest.json")
    case = manifest["cases"][0]
    directory = paired["out"] / "runs/F10-01/rep1"
    directory.mkdir(parents=True)
    captured = []

    def execute(cmd, **kwargs):
        captured.append((cmd, kwargs))
        assert cmd[1:5] == ["-I", "-B", "-X", "utf8"] and cmd[5] == "-c"
        assert str(paired["out"] / "code/src") in cmd
        assert kwargs["env"]["MIGLOOP_FROZEN_POOL"] == case["pool"]
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(run.subprocess, "run", execute)
    monkeypatch.setattr(run.RAW, "launch", lambda *a, **k: pytest.fail("No model in postprocess"))
    result = run.postprocess(paired["out"], manifest, case, directory)
    assert len(captured) == 1 and result["status"] == "error" and result["model_calls"] == 0
    assert run.read(directory / "verdict.json")["data"] is None


def test_queue_refuses_existing_runs_before_launch(paired, monkeypatch):
    prepare(paired)
    (paired["out"] / "runs/F10-01/rep1").mkdir(parents=True)
    monkeypatch.setattr(run, "launch_case", lambda *a, **k: pytest.fail("No retry"))
    with pytest.raises(FileExistsError, match="no overwrite"):
        run.run_queue(paired["out"])


def test_queue_uses_two_repetitions_and_preserves_raw_order(paired, monkeypatch):
    prepare(paired)
    mark_smoke(paired)
    seen = []

    def launch(out, manifest, case, rep):
        seen.append((case["id"], rep))
        return {"status": "completed", "actual_models": [run.MODEL], "actual_effort": run.EFFORT,
                "recording_complete": True, "host_skill_catalog_absent": True,
                "postprocess": {"status": "completed"}}

    monkeypatch.setattr(run, "launch_case", launch)
    assert run.run_queue(paired["out"])["status"] == "finished"
    assert len(seen) == 20 and set(seen) == {(c["id"], r) for c in paired["raw"]["cases"] for r in (1, 2)}
    rows = [json.loads(line) for line in (paired["out"] / "queue.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["concurrency"] == 2
    assert [(r["case"], r["rep"]) for r in rows if r["event"] == "launch"] == \
           [(c["id"], r) for r in (1, 2) for c in paired["raw"]["cases"]]


def test_prepare_verify_never_resolve_codex_or_launch_models(paired, monkeypatch):
    monkeypatch.setattr(run.RAW, "launch", lambda *a, **k: pytest.fail("No paid launch"))
    monkeypatch.setattr(run.RAW, "command", lambda *a, **k: pytest.fail("No Codex command during prepare"))
    assert prepare(paired)["model_started"] is False
    assert run.verify(paired["out"])


def test_untimed_root_header_does_not_replace_first_valid_timestamp(tmp_path):
    path = tmp_path / "root.jsonl"
    rows = [{"type": "last-prompt"}, {"timestamp": "invalid"}, {"timestamp": "2026-01-01T00:00:00"},
            {"timestamp": "2026-01-01T08:00:00+08:00"}]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    result = run._root_start(path)
    assert result["line"] == 4 and result["normalized_time"] == "2026-01-01T00:00:00+00:00"
    path.write_text('{"type":"last-prompt"}', encoding="utf-8")
    with pytest.raises(ValueError, match="no valid explicit timestamp"):
        run._root_start(path)


@pytest.mark.parametrize("status", ["error", "deferred", "ok"])
def test_smoke_requires_actual_ok_item_correct_scope_and_receipt(status):
    scope = {"kind": "file", "key": "/p/A.ets", "at": "2026-01-01T00:00:00.000000Z", "since_ts": None, "id": "scope:sample"}
    registry = {"scope": scope, "ledger": "ledger:test", "expected_count": 146}
    request = {"sid": "s", "requests": [{"tool": "file", "args": {"path": "A.ets", "at": scope["at"]}}], "max_chars": 12000}
    data = {"schema": "migloop-investigation-batch/1", "ledger": registry["ledger"], "items": [
        {"tool": "file", "status": status, "scope": scope, "data": {"schema": "migloop-time-view/1", "scope": scope, "source_count": 146}}]}
    def encoded(body_data):
        body = json.dumps(body_data, ensure_ascii=False)
        def digest(value):
            return run.hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        receipt = {"schema": "migloop-investigation-receipt/1", "ledger": registry["ledger"],
                   "body_sha256": digest(body), "request_sha256": digest({k: v for k, v in request.items() if k != "sid"})}
        return body + "\nMIGLOOP_INVESTIGATION_RECEIPT " + json.dumps(receipt)
    assert run._batch_smoke_check(encoded(data), request, registry) is (status == "ok")
    data["items"][0]["scope"] = {**scope, "at": "2026-01-02T00:00:00Z"}
    assert not run._batch_smoke_check(encoded(data), request, registry)


def test_paid_queue_requires_three_pool_smoke(paired, monkeypatch):
    prepare(paired)
    monkeypatch.setattr(run, "launch_case", lambda *a, **k: pytest.fail("No launch before smoke"))
    with pytest.raises(ValueError, match="three-pool MCP smoke"):
        run.run_queue(paired["out"])


def test_development_smoke_snapshot_cannot_start_model_queue(paired, monkeypatch):
    result = run.prepare(paired["out"], paired["base"], source=paired["source"], python=paired["python"], dev_smoke=True)
    assert result["status"] == "frozen_dev_smoke_only"
    assert run.verify(paired["out"])
    monkeypatch.setattr(run, "launch_case", lambda *a, **k: pytest.fail("No paid launch"))
    with pytest.raises(ValueError, match="Development smoke snapshot"):
        run.run_queue(paired["out"])
