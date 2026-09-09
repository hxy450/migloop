"""Offline tests for the paired runner; subprocesses are mocked, never paid models."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest


RUNNER = Path(__file__).parents[1] / "docs/experiments/2026-09-09-fidelity-cost/run_pair.py"
spec = importlib.util.spec_from_file_location("pair_harness", RUNNER)
assert spec and spec.loader
pair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pair)


@pytest.fixture
def frozen_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "source"
    (source / "src/migloop").mkdir(parents=True)
    (source / "src/migloop/service.py").write_text("# frozen source\n", encoding="utf-8")
    original = tmp_path / "original"
    original.mkdir()
    prior = original / "prior-session.jsonl"
    current = original / "current-session.jsonl"
    prior.write_text('{"timestamp":"2026-01-01"}\n', encoding="utf-8")
    current.write_text('{"timestamp":"2026-01-02"}\n', encoding="utf-8")
    sub = original / "current-session/subagents"
    sub.mkdir(parents=True)
    (sub / "agent-a.jsonl").write_text('{"message":"原始内容"}\n', encoding="utf-8")
    (original / "stage-marks.json").write_text('{"marks":[]}\n', encoding="utf-8")
    service = SimpleNamespace(locate_session=lambda sid: str(current),
                              extract_trace=lambda root: {"meta": {"session_format": "claude", "cwd": "/original/project"}},
                              prior_roots=lambda fmt, root, cwd: [str(prior)], session_ledger=lambda root: object())
    atoms = SimpleNamespace(ledger_identity=lambda ledger: "test-ledger")
    verdict = SimpleNamespace(load_block=lambda text: {"found": False, "data": None, "errors": [], "raw": None})
    monkeypatch.setattr(pair, "load_modules", lambda src: (service, atoms, verdict))
    return pair.prepare("current", "entry/A.ets", "case-one", tmp_path / "store", source, "frozen-code-1")


def test_prepare_copies_same_pool_preserves_content_and_writes_manifests(frozen_case: Path) -> None:
    case = pair.read_json(frozen_case / "case.json")
    pool = Path(case["pool"])
    assert sorted(p.relative_to(pool).as_posix() for p in pool.rglob("*") if p.is_file()) == [
        "current-session.jsonl", "current-session/subagents/agent-a.jsonl", "prior-session.jsonl", "stage-marks.json"]
    manifest = pair.read_json(frozen_case / "pool-manifest.json")
    assert len(manifest["entries"]) == 4
    assert all(pair.sha256(pool / entry["path"]) == entry["sha256"] for entry in manifest["entries"])
    assert case["current_root"] == str(pool / "current-session.jsonl")
    assert all(Path(root).is_relative_to(pool) for root in case["roots"])
    assert all(pair.check_frozen(frozen_case, case)[key] for key in ("pool_unchanged", "source_unchanged", "task_unchanged"))


def test_prepare_never_overwrites_case_or_accepts_path_escape(frozen_case: Path) -> None:
    case = pair.read_json(frozen_case / "case.json")
    with pytest.raises(FileExistsError):
        pair.prepare("current", "A.ets", frozen_case.name, frozen_case.parent, Path(case["source"]), "new-code")
    with pytest.raises(ValueError, match="single safe"):
        pair.prepare("current", "A.ets", "../escape", frozen_case.parent, Path(case["source"]), "new-code")


def new_source(tmp_path: Path) -> Path:
    source = tmp_path / "new-source"
    (source / "src/migloop").mkdir(parents=True)
    (source / "src/migloop/service.py").write_text("# optimized frozen source\n", encoding="utf-8")
    return source


def test_common_task_explicitly_allows_all_in_pool_roots_for_both_arms(frozen_case: Path) -> None:
    case = pair.read_json(frozen_case / "case.json")
    for arm in ("tools", "raw"):
        text = pair.build_prompt(frozen_case, case, arm)
        assert "- prior-session.jsonl" in text and "- current-session.jsonl" in text
        assert "两组都允许检索、打开池内全部会话" in text
        assert "全部 subagents 子目录" in text and "调查起点，不是范围边界" in text
        assert "不访问池外原工程、其他会话" not in text


def test_harness_coverage_is_separate_from_schema_and_respects_actual_trace(frozen_case: Path, monkeypatch):
    from migloop import atoms, probe, verdict
    from tests.test_repair_coverage import PATH, declaration, splash_ledger
    ledger, chains = splash_ledger()
    case = pair.read_json(frozen_case / "case.json")
    case["file"] = PATH
    # Feature-detection fixture, not imported code; actual modules below are injected.
    (Path(case["source"]) / "src/migloop/coverage.py").write_text("# supported", encoding="utf-8")
    service = SimpleNamespace(session_ledger=lambda root: ledger, fixchain_payload=lambda root: {"chains": chains})
    monkeypatch.setattr(pair, "load_modules", lambda src: (service, atoms, verdict))
    data = {"schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger), "defects": [],
            "coverage": [declaration(v, status="unresolved", defects=[]) for v in (52, 53, 54)]}
    response = {"response_text": "```json\n" + json.dumps(data) + "\n```"}
    got = pair.collect_verdict(case, response, "tools")
    assert not got["errors"] and got["coverage"]["complete"] is True
    assert got["coverage"]["counts"]["unresolved"] == 3 and got["coverage"]["semantic_checked"] is False
    trace = [{"tool": "sessions", "has_result": True, "is_error": False, "text": "账本身份: historical-ledger"}]
    monkeypatch.setattr(probe, "_transcript_calls", lambda folder: trace)
    old = pair.collect_verdict(case, response, "tools", frozen_case)
    assert not old["errors"] and old["coverage"]["complete"] is False
    assert old["trace_identity"]["bound"] is False


def test_task_refresh_is_explicit_new_case_and_never_mutates_parent(frozen_case: Path, tmp_path: Path) -> None:
    original = pair.read_json(frozen_case / "case.json")
    # Simulate a recorded older, ambiguous prompt. This synthetic fixture is not a real run.
    task = frozen_case / "common-task.md"
    task.write_text("older scope wording", encoding="utf-8")
    original["common_task_sha256"] = pair.sha256(task)
    pair.write_json(frozen_case / "case.json", original)
    before = pair.inventory(frozen_case)
    new = pair.variant(frozen_case, new_source(tmp_path), tmp_path / "v2", "new-code", refresh_task=True)
    doc = pair.read_json(new / "case.json")
    assert doc["task_revision"] == "pool-scope/2" and doc["pool"] == original["pool"]
    assert doc["common_task_sha256"] != original["common_task_sha256"]
    assert doc["parent_case"]["common_task_sha256"] == original["common_task_sha256"]
    assert pair.inventory(frozen_case) == before
    assert pair.check_frozen(new, doc)["task_unchanged"] is True


def test_variant_reuses_absolute_pool_and_exact_task_without_copying_runs(frozen_case: Path, tmp_path: Path) -> None:
    original = pair.read_json(frozen_case / "case.json")
    task = frozen_case / "common-task.md"
    task.write_bytes(task.read_bytes() + "\r\n逐字保留\r\n".encode())
    original["common_task_sha256"] = pair.sha256(task)
    pair.write_json(frozen_case / "case.json", original)
    old_run = frozen_case / "runs/raw/rep1"
    old_run.mkdir(parents=True)
    (old_run / "metrics.json").write_text('{"historical":true}', encoding="utf-8")
    before = pair.inventory(frozen_case)
    pool_stats = {p: (p.stat().st_mode, p.stat().st_mtime_ns) for p in Path(original["pool"]).rglob("*")}
    source = new_source(tmp_path)
    destination = pair.variant(frozen_case, source, tmp_path / "variant-store", "new-code")
    assert destination == tmp_path / "variant-store" / original["case"]
    assert not (destination / "pool").exists() and not (destination / "runs").exists()
    updated = pair.read_json(destination / "case.json")
    changed = {key for key in updated if updated[key] != original.get(key)}
    assert changed == {"source", "source_code_id", "source_digest", "parent_case"}
    assert updated["source"] == str(source) and updated["source_code_id"] == "new-code"
    assert updated["parent_case"] == {"case_dir": str(frozen_case), "case_sha256": pair.sha256(frozen_case / "case.json")}
    assert (destination / "common-task.md").read_bytes() == task.read_bytes()
    assert (destination / "pool-manifest.json").read_bytes() == (frozen_case / "pool-manifest.json").read_bytes()
    assert pair.read_json(destination / "source-manifest.json") == pair.inventory(source / "src/migloop")
    for arm in ("raw", "tools"):
        assert pair.build_prompt(destination, updated, arm) == pair.build_prompt(frozen_case, original, arm)
        argv, _ = pair.build_codex_command(updated, arm, destination / "run", "model", "medium", "codex")
        assert argv[argv.index("-C") + 1] == original["pool"]
    assert all(pair.check_frozen(destination, updated)[key] for key in ("pool_unchanged", "source_unchanged", "task_unchanged"))
    assert pair.inventory(frozen_case) == before
    assert {p: (p.stat().st_mode, p.stat().st_mtime_ns) for p in pool_stats} == pool_stats
    with pytest.raises(FileExistsError):
        pair.variant(frozen_case, source, destination.parent, "another-code")


@pytest.mark.parametrize("target", ["pool/current-session.jsonl", "common-task.md", "source"])
def test_variant_rejects_changed_parent_before_writing(frozen_case: Path, tmp_path: Path, target: str) -> None:
    original = pair.read_json(frozen_case / "case.json")
    path = Path(original["source"]) / "src/migloop/service.py" if target == "source" else frozen_case / target
    path.chmod(path.stat().st_mode | stat.S_IWUSR)
    path.write_text("changed", encoding="utf-8")
    store = tmp_path / "variant-store"
    with pytest.raises(RuntimeError, match="Frozen parent"):
        pair.variant(frozen_case, new_source(tmp_path), store, "new-code")
    assert not store.exists()


def test_variant_rejects_protected_destination_and_invalid_source(frozen_case: Path, tmp_path: Path) -> None:
    original = pair.read_json(frozen_case / "case.json")
    source = new_source(tmp_path)
    for store in (frozen_case / "nested", Path(original["pool"]), Path(original["source"]), source):
        with pytest.raises(ValueError, match="outside"):
            pair.variant(frozen_case, source, store, "new-code")
        assert not (store / original["case"]).exists()
    with pytest.raises(ValueError, match="Frozen source"):
        pair.variant(frozen_case, tmp_path / "missing-source", tmp_path / "variant-store", "new-code")
    assert not (tmp_path / "variant-store").exists()


def test_variant_cli_is_offline(frozen_case: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    source = new_source(tmp_path)
    monkeypatch.setattr(pair, "load_modules", lambda *args: pytest.fail("Variant must not load source or locate live data"))
    monkeypatch.setattr(pair.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Variant must not start a model"))
    store = tmp_path / "new-store"
    assert pair.main(["variant", "--case-dir", str(frozen_case), "--source", str(source), "--store", str(store), "--code-id", "new-code"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["case_dir"] == str(store / frozen_case.name)
    assert result["case"]["pool"] == str(frozen_case / "pool")


def test_common_task_is_identical_and_only_arm_instructions_differ(frozen_case: Path) -> None:
    case = pair.read_json(frozen_case / "case.json")
    common = (frozen_case / "common-task.md").read_text(encoding="utf-8")
    raw = pair.build_prompt(frozen_case, case, "raw")
    tools = pair.build_prompt(frozen_case, case, "tools")
    assert raw.startswith(common + "\n") and tools.startswith(common + "\n")
    assert "GUIDE" not in raw and "当前 GUIDE" in tools
    assert "只读 shell" in raw and "Read/Grep/Glob/Bash" not in raw
    assert "reason/evidence/notes" in tools and "不另写重复的完整散文报告" in tools
    assert "name 精确匹配 mcp__migloop__guide" in tools and "不按 description 搜索 guide" in tools
    assert "在共同任务要求的报告之后" not in tools
    assert "零命中" in common and "不认证" in common and "禁止照着执行" in common
    assert "source_code_id" not in raw and "PROTOCOL.md" not in raw


def test_cli_isolates_available_tools_and_preserves_interpreter(frozen_case: Path) -> None:
    case = pair.read_json(frozen_case / "case.json")
    for arm in ("raw", "tools"):
        command, mcp = pair.build_command(case, arm, frozen_case / "run", "test-session", "explicit-model", "high", 45, 5, "claude.exe")
        assert all(flag in command for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-chrome"))
        assert not any("skip-permissions" in arg or arg == "--bare" for arg in command)
        assert command[command.index("--tools") + 1] == ("" if arm == "tools" else "Read,Grep,Glob,Bash")
        assert command[command.index("--model") + 1] == "explicit-model"
        if arm == "tools":
            tool = mcp["mcpServers"]["migloop"]
            assert tool["command"] == sys.executable
            assert tool["env"]["PYTHONPATH"] == str(Path(case["source"]) / "src")
            assert "--add-dir" not in command
        else:
            assert mcp == {"mcpServers": {}}
            assert command[command.index("--add-dir") + 1] == case["pool"]


def test_tokens_count_output_once_and_keep_unknowns() -> None:
    usage = pair.usage_fields({"input_tokens": 5, "cache_creation_input_tokens": 7, "cache_read_input_tokens": 11,
                               "output_tokens": 19, "thinking_tokens": 13})
    assert usage["input_total"] == 23
    assert usage["output"] == 19 and usage["thinking_reported"] == 13
    missing = pair.usage_fields({"input_tokens": 5})
    assert missing["cache_read"] is None and missing["input_total"] is None and missing["output"] is None
    assert pair.usage_fields(None)["input_uncached"] is None
    assert pair.usage_fields({"inputTokens": 2, "cacheCreationInputTokens": 0, "cacheReadInputTokens": 3})["input_total"] == 5


def write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")


def test_transcript_correlates_ids_preserves_pending_rejection_and_replay(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    def use(tid: str, via: str = "sessions") -> dict[str, Any]:
        return {"type": "tool_use", "id": tid, "name": "mcp__migloop__file", "input": {"path": "A.ets", "v": 1, "via": via}}
    def result(tid: str, text: str) -> dict[str, Any]:
        return {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}
    assistant = {"type": "assistant", "message": {"id": "msg1", "usage": {"input_tokens": 2, "cache_creation_input_tokens": 0,
                   "cache_read_input_tokens": 3, "output_tokens": 4}, "content": [use("t1"), use("t2")]}}
    write_records(transcript, [assistant, assistant,
        {"type": "user", "message": {"content": [result("t1", "# A.ets @v1")]}},
        {"type": "assistant", "message": {"id": "msg2", "content": [use("t3", "file:A.ets@v1"), use("t4")]}},
        {"type": "user", "message": {"content": [result("t3", "# A.ets @v1"), result("t4", '{"result":"⛔ refused"}'), result("ghost", "x")]}},
        {"type": "user", "message": {"content": [result("t1", "# A.ets @v1")]}}])
    out = pair.parse_transcript(transcript)
    assert out["tool_calls"] == 4 and out["usage"]["input_total"] == 5 and out["usage"]["output"] == 4
    assert [row["status"] for row in out["seq"]] == ["returned", "pending", "returned", "rejected"]
    first = out["seq"][0]
    assert first["tool_use_id"] == "t1" and first["use_line"] == 1 and first["result_line"] == 3
    assert first["replay_use_lines"] == [2] and first["duplicate_result_lines"] == [6]
    assert out["seq"][1]["chars"] is None and out["tool_chars"] is None and out["tool_chars_observed"] > 0
    assert out["pending_calls"] == 1 and out["rejected_calls"] == 1 and out["revisited_nodes"] == 1
    assert out["unmatched_result_ids"] == ["ghost"]


def fake_process(monkeypatch: pytest.MonkeyPatch, output: dict[str, Any] | str, exc: BaseException | None = None) -> list[Any]:
    calls = []
    class Process:
        returncode = None
        pid = 123
        def __init__(self, command: list[str], **kwargs: Any) -> None:
            calls.append((command, kwargs))
            self.kwargs = kwargs
        def communicate(self, input: bytes, timeout: float) -> None:
            self.kwargs["stdout"].write((json.dumps(output) if isinstance(output, dict) else output).encode())
            self.kwargs["stderr"].write(b"diagnostic stderr")
            if exc:
                raise exc
            self.returncode = 0
    monkeypatch.setattr(pair.subprocess, "Popen", Process)
    monkeypatch.setattr(pair, "stop_process", lambda proc: setattr(proc, "returncode", -9))
    monkeypatch.setattr(pair, "find_transcript", lambda session_id: None)
    return calls


def test_run_archives_exact_configuration_cost_and_unknown_transcript(frozen_case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_process(monkeypatch, {"result": "实际报告", "total_cost_usd": 1.23456789, "num_turns": 3,
                        "usage": {"input_tokens": 1, "cache_creation_input_tokens": 2, "cache_read_input_tokens": 3, "output_tokens": 4},
                        "modelUsage": {"actual-concrete-model": {"costUSD": 1.23456789}}})
    metrics = pair.run_one(frozen_case, "raw", 1, model="requested-model", backend="claude")
    run = frozen_case / "runs/raw/rep1"
    assert metrics["status"] == "completed" and metrics["cost_usd_total"] == 1.23456789
    assert metrics["actual_models"] == ["actual-concrete-model"] and metrics["usage"]["input_total"] == 6
    assert metrics["transcript"] is None and metrics["recording_complete"] is False
    assert not (run / "transcript.jsonl").exists()
    assert all((run / name).exists() for name in ("prompt.md", "mcp.json", "command.json", "config.json", "result.json", "stderr.txt", "metrics.json", "verdict.json"))
    assert calls[0][1]["cwd"] == str(run) and metrics["wall_s"] >= 0
    assert len(calls) == 1 and "--resume" not in calls[0][0]
    with pytest.raises(FileExistsError):
        pair.run_one(frozen_case, "raw", 1, model="requested-model", backend="claude")
    assert len(calls) == 1


@pytest.mark.parametrize("exc,status", [(KeyboardInterrupt(), "interrupted"),
                                       (subprocess.TimeoutExpired("fake", 1), "timeout")])
def test_interruption_and_timeout_keep_artifacts_without_retry(frozen_case: Path, monkeypatch: pytest.MonkeyPatch,
                                                            exc: BaseException, status: str) -> None:
    calls = fake_process(monkeypatch, "", exc)
    metrics = pair.run_one(frozen_case, "tools", 1, model="model", backend="claude")
    run = frozen_case / "runs/tools/rep1"
    assert metrics["status"] == status and metrics["cost_usd"] is None and metrics["usage"]["output"] is None
    assert metrics["returncode"] == -9 and len(calls) == 1
    assert pair.read_json(run / "metrics.json")["status"] == status
    assert (run / "stderr.txt").read_text() == "diagnostic stderr"
    assert metrics["verdict_ok"] is False and "Required YAML" in metrics["verdict_errors"][0]


def test_invalid_json_is_not_reported_as_completed(frozen_case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_process(monkeypatch, "not JSON")
    metrics = pair.run_one(frozen_case, "raw", 1, model="model", backend="claude")
    assert metrics["status"] == "result_error" and metrics["cost_usd"] is None


def test_frozen_data_change_blocks_before_model_launch(frozen_case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_process(monkeypatch, {})
    target = frozen_case / "pool/current-session.jsonl"
    target.chmod(target.stat().st_mode | stat.S_IWUSR)
    target.write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Frozen"):
        pair.run_one(frozen_case, "raw", 1, model="model", backend="claude")
    assert not calls and not (frozen_case / "runs/raw/rep1").exists()


def test_backend_and_model_are_never_implicitly_selected(frozen_case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_process(monkeypatch, {})
    with pytest.raises(ValueError, match="explicit"):
        pair.run_one(frozen_case, "raw", 1, model=None)
    assert not calls


def test_codex_configuration_uses_readonly_sandbox_and_one_mcp(frozen_case: Path) -> None:
    case = pair.read_json(frozen_case / "case.json")
    for arm in ("raw", "tools"):
        command, config = pair.build_codex_command(case, arm, frozen_case / "run", "gpt-5.6-sol", "medium", "codex.exe")
        assert command[:6] == ["codex.exe", "-a", "never", "exec", "--ignore-user-config", "--ignore-rules"]
        assert command[command.index("--sandbox") + 1] == "read-only"
        assert command[command.index("-C") + 1] == case["pool"]
        assert command[command.index("-m") + 1] == "gpt-5.6-sol"
        assert not any("auth" in arg or "bypass" in arg for arg in command)
        assert config["settings"]["features.shell_tool"] is (arm == "raw")
        assert config["settings"]["features.multi_agent"] is False and config["settings"]["web_search"] == "disabled"
        if os.name == "nt":
            assert config["settings"]["windows.sandbox"] == "elevated"
            assert 'windows.sandbox="elevated"' in command
        else:
            assert "windows.sandbox" not in config["settings"]
        disabled = {command[i + 1] for i, arg in enumerate(command[:-1]) if arg == "--disable"}
        enabled = {command[i + 1] for i, arg in enumerate(command[:-1]) if arg == "--enable"}
        common_disabled = {"plugins", "browser_use", "computer_use", "image_generation", "memories", "hooks", "apps", "multi_agent", "code_mode"}
        assert disabled == common_disabled | ({"shell_tool"} if arm == "tools" else set())
        assert enabled == {"skip_host_skill_discovery", "code_mode_host"} | ({"shell_tool"} if arm == "raw" else set())
        if arm == "tools":
            server = config["mcp_servers"]["migloop"]
            assert server["command"] == sys.executable and server["cwd"] == case["source"]
            assert server["env"]["MIGLOOP_FROZEN_POOL"] == case["pool"] and server["required"] is True
        else:
            assert config["mcp_servers"] == {}


def codex_events() -> list[dict[str, Any]]:
    item = {"id": "item_1", "type": "mcp_tool_call", "server": "migloop", "tool": "file",
            "arguments": {"path": "A.ets", "v": 1, "sid": "snapshot-root"}}
    return [{"type": "thread.started", "thread_id": "12345678-1234-1234-1234-123456789abc"},
            {"type": "turn.started"},
            {"type": "item.started", "item": item},
            {"type": "item.completed", "item": {**item, "status": "completed", "result": {"content": [{"type": "text", "text": "⛔ via rejected"}]}}},
            {"type": "item.started", "item": {"id": "item_2", "type": "command_execution", "command": "read-only parse"}},
            {"type": "item.completed", "item": {"id": "item_3", "type": "agent_message", "text": "原生报告"}},
            {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 20}}]


def test_codex_events_keep_native_token_semantics_and_pending_calls(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    write_records(events, codex_events())
    result = pair.parse_codex_events(events)
    assert result["backend"] == "codex" and result["response_text"] == "原生报告"
    assert result["usage"]["input_total"] == 100 and result["usage"]["input_uncached"] == 60
    assert result["usage"]["cache_read"] == 40 and result["usage"]["cache_creation"] is None
    assert result["usage"]["output"] == 20 and result["actual_models"] is None
    calls = result["calls"]
    assert calls["tool_calls"] == 2 and calls["seq"][0]["use_line"] == 3 and calls["seq"][0]["result_line"] == 4
    assert calls["seq"][0]["input"]["sid"] == "snapshot-root"
    assert calls["rejected_calls"] == 1 and calls["pending_calls"] == 1 and calls["tool_chars"] is None


def test_codex_run_keeps_native_events_and_does_not_invent_cost_limits(frozen_case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events = "\n".join(json.dumps(event, ensure_ascii=False) for event in codex_events()) + "\n"
    calls = fake_process(monkeypatch, events)
    monkeypatch.setattr(pair, "find_codex_transcript", lambda thread_id: None)
    metrics = pair.run_one(frozen_case, "tools", 1)
    run = frozen_case / "runs/tools/rep1"
    assert metrics["backend"] == "codex" and metrics["model_requested"] == "gpt-5.6-sol"
    assert metrics["effort"] == "medium" and len(calls) == 1
    assert metrics["status"] == "completed" and metrics["cost_usd_total"] is None
    assert metrics["usage"]["input_total"] == 100 and metrics["usage"]["output"] == 20
    assert metrics["actual_models"] is None and metrics["model_usage"] is None
    assert metrics["dollar_limit_enforced"] is False and metrics["turn_limit_enforced"] is False
    assert metrics["native_events"]["pending_calls"] == 1 and metrics["transcript"] is None
    assert (run / "events.jsonl").read_text(encoding="utf-8") == events
    assert pair.read_json(run / "result.json")["schema"] == "migloop-codex-result/1"


def test_codex_rollout_uses_real_call_ids_and_is_copied(frozen_case: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rollout = tmp_path / "investigator.jsonl"
    write_records(rollout, [
        {"type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "medium"}},
        {"type": "response_item", "payload": {"type": "function_call", "call_id": "call_actual", "name": "mcp__migloop__file", "arguments": '{"path":"A.ets","v":1}'}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "call_actual", "output": '{"result":"A.ets @v1"}'}},
        {"type": "response_item", "payload": {"type": "function_call", "call_id": "call_pending", "name": "exec_command", "arguments": '{"cmd":"read-only command"}'}}])
    parsed = pair.parse_codex_transcript(rollout)
    assert parsed["backend"] == "codex" and parsed["models_reported_by_context"] == ["gpt-5.6-sol"]
    assert parsed["seq"][0]["tool_use_id"] == "call_actual" and parsed["seq"][0]["use_line"] == 2
    assert parsed["seq"][0]["result_line"] == 3 and parsed["seq"][0]["chars"] == len("A.ets @v1")
    assert parsed["pending_calls"] == 1 and parsed["tool_chars"] is None
    fake_process(monkeypatch, "\n".join(json.dumps(e, ensure_ascii=False) for e in codex_events()) + "\n")
    monkeypatch.setattr(pair, "find_codex_transcript", lambda thread_id: rollout)
    metrics = pair.run_one(frozen_case, "raw", 1)
    copy = frozen_case / "runs/raw/rep1/transcript.jsonl"
    assert copy.read_bytes() == rollout.read_bytes() and metrics["recording_complete"] is True
    assert metrics["transcript"]["seq"][0]["call_id"] == "call_actual"
    assert metrics["models_reported_by_context"] == ["gpt-5.6-sol"]
    assert metrics["actual_models"] == ["gpt-5.6-sol"] and metrics["actual_model_source"] == "transcript.turn_context"
    assert metrics["actual_effort"] == "medium" and metrics["actual_effort_source"] == "transcript.turn_context"
    assert metrics["native_events"]["seq"][0]["item_id"] == "item_1"
    assert metrics["native_events"]["seq"][0]["tool_use_id"] is None


def test_harness_identity_is_computed_in_snapshot_environment(frozen_case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = pair.read_json(frozen_case / "case.json")
    observed = []
    service = SimpleNamespace(session_ledger=lambda root: observed.append((root, os.environ.get("MIGLOOP_FROZEN_POOL"))))
    monkeypatch.setattr(pair, "load_modules", lambda src: (service, SimpleNamespace(ledger_identity=lambda _: "snapshot-id"), object()))
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", "previous-value")
    result = pair.collect_verdict(case, {}, "raw")
    assert observed == [(case["current_root"], case["pool"])] and result["harness_identity"] == "snapshot-id"
    assert os.environ["MIGLOOP_FROZEN_POOL"] == "previous-value"


def test_observed_codex_cache_write_and_reasoning_are_not_added_again(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_records(path, [{"type": "turn.started"}, {"type": "turn.completed", "usage": {
        "input_tokens": 10419, "cached_input_tokens": 10240, "cache_write_input_tokens": 0,
        "output_tokens": 12, "reasoning_output_tokens": 0}}])
    usage = pair.parse_codex_events(path)["usage"]
    assert usage["input_total"] == 10419 and usage["input_uncached"] == 179
    assert usage["cache_read"] == 10240 and usage["cache_creation"] == 0
    assert usage["output"] == 12 and usage["thinking_reported"] == 0
    write_records(path, [{"type": "turn.completed", "usage": {
        "input_tokens": 100, "cached_input_tokens": 40, "cache_write_input_tokens": 11,
        "output_tokens": 20, "reasoning_output_tokens": 9}}])
    usage = pair.parse_codex_events(path)["usage"]
    assert usage["input_total"] == 100 and usage["cache_creation"] == 11
    assert usage["output"] == 20 and usage["thinking_reported"] == 9


@pytest.mark.parametrize("tool_transport", ["code-host", "native"])
def test_guide_smoke_is_separate_and_never_builds_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool_transport: str) -> None:
    source = tmp_path / "source"
    (source / "src/migloop").mkdir(parents=True)
    (source / "src/migloop/mcp_server.py").write_text("# source\n", encoding="utf-8")
    store = tmp_path / "smoke-new"
    item = {"id": "guide_item", "type": "mcp_tool_call", "server": "migloop", "tool": "guide", "arguments": {}}
    events = [{"type": "thread.started", "thread_id": "12345678-1234-1234-1234-123456789abc"},
              {"type": "turn.started"}, {"type": "item.started", "item": item},
              {"type": "item.completed", "item": {**item, "result": {"content": [{"type": "text", "text": "GUIDE"}]}, "status": "completed"}},
              {"type": "item.completed", "item": {"id": "answer", "type": "agent_message", "text": "SOL_MCP_SMOKE_OK"}},
              {"type": "turn.completed", "usage": {"input_tokens": 10419, "cached_input_tokens": 10240, "cache_write_input_tokens": 0,
                                                    "output_tokens": 12, "reasoning_output_tokens": 0}}]
    calls = fake_process(monkeypatch, "\n".join(json.dumps(row) for row in events) + "\n")
    rollout = tmp_path / "actual-rollout.jsonl"
    model = "gpt-5.5" if tool_transport == "native" else "gpt-5.6-sol"
    write_records(rollout, [{"type": "turn_context", "payload": {"model": model, "effort": "medium"}},
                            {"type": "response_item", "payload": {"type": "function_call", "call_id": "real_guide", "name": "mcp__migloop__guide", "arguments": "{}"}},
                            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "real_guide", "output": "GUIDE"}}])
    monkeypatch.setattr(pair, "find_codex_transcript", lambda thread_id: rollout)
    monkeypatch.setattr(pair, "collect_verdict", lambda *args: pytest.fail("Smoke must not build a ledger or verdict"))
    monkeypatch.setattr(pair, "load_modules", lambda *args: pytest.fail("Smoke must not import the data service"))
    metrics = pair.run_smoke(source, store, model=model, tool_transport=tool_transport)
    assert len(calls) == 1 and metrics["smoke_passed"] is True and metrics["connection_verified"] is True
    assert metrics["include_in_pairs"] is False and metrics["experiment_kind"] == "connectivity_smoke"
    assert metrics["actual_models"] == [model] and metrics["actual_effort"] == "medium"
    assert metrics["tool_transport"] == pair.read_json(store / "config.json")["tool_transport"] == tool_transport
    assert metrics["cost_usd"] is None and metrics["usage"]["input_total"] == 10419
    assert (store / "transcript.jsonl").read_bytes() == rollout.read_bytes()
    assert list((store / "empty-pool").iterdir()) == []
    assert not (store / "case.json").exists() and not (store / "verdict.json").exists()
    assert "不传 sid" in (store / "prompt.md").read_text(encoding="utf-8")
    assert ("code-mode" in (store / "prompt.md").read_text(encoding="utf-8")) is (tool_transport == "code-host")
    with pytest.raises(FileExistsError):
        pair.run_smoke(source, store)
    assert len(calls) == 1


def test_native_transport_keeps_mcp_and_sandbox_without_forcing_code_host(frozen_case: Path) -> None:
    case = pair.read_json(frozen_case / "case.json")
    command, config = pair.build_codex_command(case, "tools", frozen_case / "run", "gpt-5.5", "medium", "codex.exe", "native")
    enabled = {command[i + 1] for i, word in enumerate(command[:-1]) if word == "--enable"}
    disabled = {command[i + 1] for i, word in enumerate(command[:-1]) if word == "--disable"}
    assert {"code_mode", "code_mode_host", "shell_tool"} <= disabled
    assert enabled == {"skip_host_skill_discovery"}
    assert command[command.index("-m") + 1] == "gpt-5.5"
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("-a") + 1] == "never"
    assert set(config["mcp_servers"]) == {"migloop"} and config["mcp_servers"]["migloop"]["required"] is True
    prompt = pair.build_prompt(frozen_case, case, "tools", tool_transport="native")
    assert "mcp__migloop__guide" in prompt and "code-mode" not in prompt and "tools.mcp__" not in prompt
    assert "当前 GUIDE 要求的 migloop-verdict YAML" in prompt and "reason/evidence/notes" in prompt
    default_command, default_config = pair.build_codex_command(case, "tools", frozen_case / "run", "model", "medium", "codex.exe")
    assert default_config["tool_transport"] == "code-host"
    assert default_config["settings"]["features.code_mode_host"] is True


def test_invalid_transport_is_rejected_before_artifacts_or_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    (source / "src/migloop").mkdir(parents=True)
    (source / "src/migloop/mcp_server.py").write_text("# source\n", encoding="utf-8")
    monkeypatch.setattr(pair.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("must not launch"))
    with pytest.raises(ValueError, match="tool_transport"):
        pair.run_smoke(source, tmp_path / "invalid", tool_transport="guessed")
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize("command", ["smoke", "run"])
def test_cli_forwards_explicit_native_transport(command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    received = []
    def fake(*args: Any, **kwargs: Any) -> dict[str, Any]:
        received.append((args, kwargs))
        return {"status": "completed"}
    monkeypatch.setattr(pair, "run_smoke" if command == "smoke" else "run_one", fake)
    paths = (["--source", str(tmp_path), "--store", str(tmp_path / "smoke")]
             if command == "smoke" else ["--case-dir", str(tmp_path), "--arm", "tools", "--rep", "1"])
    assert pair.main([command, *paths, "--model", "gpt-5.5", "--tool-transport", "native"]) == 0
    assert received[0][0][-1] == "native" and "gpt-5.5" in received[0][0]


def test_host_rollout_preserves_failed_mcp_leaf_and_counts_wrappers_separately(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    failed = {"type": "event_msg", "timestamp": "2026-09-09T06:04:29.167Z", "payload": {
        "type": "item_completed", "started_at_ms": 1788933869166, "completed_at_ms": 1788933869167,
        "item": {"type": "McpToolCall", "id": "exec-native-guide", "server": "migloop", "tool": "guide", "arguments": {},
                 "status": "failed", "error": {"message": "MCP tool call requires approval, but approval policy is never"},
                 "duration": {"secs": 0, "nanos": 0}}}}
    write_records(transcript, [
        {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "call_discover", "name": "exec", "input": "ALL_TOOLS.filter(...)"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "call_discover", "output": [{"type": "input_text", "text": "catalog"}]}},
        {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "call_wrapper", "name": "exec", "input": "await tools.mcp__migloop__guide({})"}},
        failed,
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "call_wrapper", "output": "approval error"}},
        failed])
    parsed = pair.parse_codex_transcript(transcript)
    assert parsed["tool_calls"] == 1 and parsed["failed_calls"] == 1 and parsed["pending_calls"] == 0
    assert parsed["wrapper_count"] == 2 and parsed["mcp_item_calls"] == 1
    assert parsed["wrapper_tool_chars"] == len("catalog") + len("approval error")
    leaf = parsed["seq"][0]
    assert leaf["tool"] == "guide" and leaf["server"] == "migloop" and leaf["status"] == "error"
    assert leaf["source_id"] == "exec-native-guide" and leaf["source_id_type"] == "codex_mcp_item_id"
    assert leaf["call_id"] is None and leaf["tool_use_id"] is None
    assert leaf["use_line"] is None and leaf["result_line"] == 4 and leaf["duplicate_result_lines"] == [6]
    assert leaf["started_at_ms"] == 1788933869166 and leaf["completed_at_ms"] == 1788933869167
    assert leaf["duration"] == {"secs": 0, "nanos": 0}
    assert parsed["tool_chars"] is None and parsed["tool_chars_observed"] == 0
    assert all(c["source_id_type"] == "codex_call_id" and c["is_wrapper"] for c in parsed["wrapper_calls"])


def test_host_rollout_keeps_multiple_leaf_calls_and_pending_native_start(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    def native(ident: str, typ: str, v: int, start: int, end: int | None = None) -> dict[str, Any]:
        item: dict[str, Any] = {"type": "McpToolCall", "id": ident, "server": "migloop", "tool": "file", "arguments": {"path": "A.ets", "v": v}}
        if end is not None:
            item.update(status="completed", result={"content": [{"type": "text", "text": f"A.ets @v{v}"}]})
        return {"type": "event_msg", "payload": {"type": typ, "item": item, "started_at_ms": start, "completed_at_ms": end}}
    write_records(transcript, [
        {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "call_outer", "name": "exec", "input": "Promise.all([...])"}},
        native("exec-a", "item_started", 1, 10), native("exec-b", "item_completed", 2, 12, 15),
        native("exec-a", "item_completed", 1, 10, 20), native("exec-pending", "item_started", 3, 21),
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "call_outer", "output": "wrapper output"}}])
    parsed = pair.parse_codex_transcript(transcript)
    assert [c["source_id"] for c in parsed["seq"]] == ["exec-a", "exec-b", "exec-pending"]
    assert [c["input"]["v"] for c in parsed["seq"]] == [1, 2, 3]
    assert parsed["tool_calls"] == 3 and parsed["wrapper_count"] == 1 and parsed["pending_calls"] == 1
    assert parsed["seq"][0]["use_line"] == 2 and parsed["seq"][0]["result_line"] == 4
    assert parsed["seq"][1]["use_line"] is None and parsed["seq"][1]["started_at_ms"] == 12
    assert parsed["seq"][2]["result_line"] is None and parsed["seq"][2]["chars"] is None
    assert not any("parent_call_id" in c for c in parsed["seq"])


def test_same_explicit_call_id_deduplicates_native_and_response_views(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    write_records(transcript, [
        {"type": "response_item", "payload": {"type": "function_call", "call_id": "call_real", "name": "mcp__migloop__guide", "arguments": "{}"}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "call_real", "output": "GUIDE"}},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "McpToolCall", "id": "call_real",
            "server": "migloop", "tool": "guide", "arguments": {}, "status": "completed", "result": {"content": [{"type": "text", "text": "GUIDE"}]}}}}])
    parsed = pair.parse_codex_transcript(transcript)
    assert parsed["tool_calls"] == 1 and parsed["wrapper_count"] == 0 and parsed["tool_chars"] == len("GUIDE")
    leaf = parsed["seq"][0]
    assert leaf["call_id"] == "call_real" and leaf["response_use_line"] == 1 and leaf["response_result_line"] == 2
    assert leaf["source_id_type"] == "codex_mcp_item_id" and leaf["result_line"] == 3


@pytest.mark.parametrize("case,verified", [("native", True), ("qualified", True), ("unknown", False),
    ("other", False), ("namespace_conflict", False), ("server_conflict", False),
    ("tool_conflict", False), ("args_conflict", False)])
def test_native_mcp_origin_cannot_be_replaced_during_dedup(tmp_path: Path, case: str, verified: bool) -> None:
    path = tmp_path / "origin.jsonl"
    payload = {"type": "function_call", "call_id": "same", "name": "guide", "arguments": "{}"}
    if case != "unknown":
        payload["namespace"] = "mcp__other" if case == "other" else "mcp__migloop"
    if case == "qualified":
        payload.pop("namespace")
        payload["name"] = "mcp__migloop__guide"
    if case == "namespace_conflict":
        payload["name"] = "mcp__other__guide"
    records = [{"type": "response_item", "payload": payload},
               {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "same", "output": "GUIDE"}}]
    if case != "unknown":
        item = {"type": "McpToolCall", "id": "same", "server": "other" if case in ("other", "server_conflict") else "migloop",
                "tool": "file" if case == "tool_conflict" else "guide", "arguments": {"q": "different"} if case == "args_conflict" else {},
                "status": "completed", "result": {"content": [{"type": "text", "text": "GUIDE"}]}}
        records.insert(1, {"type": "event_msg", "payload": {"type": "item_completed", "item": item}})
    write_records(path, records)
    parsed = pair.parse_codex_transcript(path)
    assert parsed["tool_calls"] == 1
    row = parsed["seq"][0]
    assert row["tool_origin"]["verified"] is verified
    if "conflict" in case:
        assert row["tool_origin"]["errors"] and row["status"] == "unverified"
    if case == "unknown":
        assert row["status"] == "unverified"


@pytest.mark.parametrize("representation", ["direct", "runtime", "stdout"])
def test_harness_origin_replay_conflicts_remain_auditable(tmp_path: Path, representation: str) -> None:
    path = tmp_path / "replay-origin.jsonl"
    if representation == "direct":
        rows = [{"type": "response_item", "payload": {"type": "function_call", "call_id": "same",
                 "name": "guide", "namespace": namespace, "arguments": "{}"}}
                for namespace in ("mcp__migloop", "mcp__other")]
        rows.append({"type": "response_item", "payload": {"type": "function_call_output", "call_id": "same", "output": "GUIDE"}})
    else:
        items = [{"type": "mcp_tool_call" if representation == "stdout" else "McpToolCall", "id": "same",
                  "server": server, "tool": "guide", "arguments": {}, "status": "completed",
                  "result": {"content": [{"type": "text", "text": "GUIDE"}]}} for server in ("migloop", "other")]
        rows = ([{"type": "item.started" if i == 0 else "item.completed", "item": item} for i, item in enumerate(items)]
                if representation == "stdout" else [{"type": "event_msg", "payload": {"type": "item_completed", "item": item}} for item in items])
    write_records(path, rows)
    parsed = pair.parse_codex_events(path)["calls"] if representation == "stdout" else pair.parse_codex_transcript(path)
    assert parsed["tool_calls"] == 1
    row = parsed["seq"][0]
    assert row["status"] == "unverified" and not row["tool_origin"]["verified"] and row["tool_origin"]["errors"]


def test_host_command_leaf_preserves_raw_fields_and_does_not_count_wrapper_output(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    command = ["powershell.exe", "-NoProfile", "-Command", "Get-ChildItem -Force -LiteralPath ."]
    item = {"type": "CommandExecution", "id": "exec-native-shell", "process_id": "46152", "command": command,
            "cwd": "file:///C:/snapshot/pool", "parsed_cmd": [{"type": "unknown", "cmd": command[-1]}],
            "source": "unified_exec_startup", "status": "completed", "stdout": "out\n", "stderr": "warn\n",
            "aggregated_output": "out\nwarn\n", "exit_code": 0, "duration": {"secs": 0, "nanos": 8991800},
            "formatted_output": "output wrapper"}
    done = {"timestamp": "2026-09-09T06:25:07.584Z", "type": "event_msg", "payload": {
        "type": "item_completed", "item": item, "started_at_ms": 1788935107575, "completed_at_ms": 1788935107584}}
    write_records(transcript, [
        {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "call_wrapper", "name": "exec", "input": "await tools.exec_command(...)"}},
        done,
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "call_wrapper", "output": "wrapper repeats output"}},
        done])
    parsed = pair.parse_codex_transcript(transcript)
    assert parsed["tool_calls"] == parsed["command_item_calls"] == parsed["wrapper_count"] == 1
    assert parsed["mcp_item_calls"] == 0 and parsed["failed_calls"] == parsed["pending_calls"] == 0
    assert parsed["tool_chars"] == len(item["aggregated_output"])
    assert parsed["wrapper_tool_chars"] == len("wrapper repeats output")
    leaf = parsed["seq"][0]
    assert leaf["source_id"] == leaf["item_id"] == "exec-native-shell"
    assert leaf["source_id_type"] == "codex_command_item_id" and leaf["source_file"] == transcript.name
    assert leaf["call_id"] is None and leaf["tool_use_id"] is None and leaf["is_wrapper"] is False
    assert leaf["tool"] == leaf["tool_name"] == "command_execution" and leaf["input"] == command
    for key in ("command", "cwd", "process_id", "parsed_cmd", "stdout", "stderr", "aggregated_output", "exit_code", "duration", "formatted_output"):
        assert leaf[key] == item[key]
    assert leaf["command_source"] == item["source"] and leaf["native_status"] == "completed"
    assert leaf["use_line"] is None and leaf["source_line"] == leaf["result_line"] == 2
    assert leaf["event_lines"] == [2, 4] and leaf["duplicate_result_lines"] == [4]
    assert leaf["started_at_ms"] == 1788935107575 and leaf["completed_at_ms"] == 1788935107584
    assert leaf["ts"] == done["timestamp"] and "parent_call_id" not in leaf


def test_host_command_events_keep_pending_failures_empty_and_unknown_output(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    def event(ident: str, typ: str = "item_completed", **fields: Any) -> dict[str, Any]:
        return {"type": "event_msg", "payload": {"type": typ, "item": {
            "type": "CommandExecution", "id": ident, "command": ["read-only command"], **fields}}}
    write_records(transcript, [
        event("pending", "item_started", status="in_progress"),
        event("failed", "item_started", status="in_progress"),
        event("empty", status="completed", aggregated_output="", stdout="", stderr="", exit_code=0),
        event("failed", status="completed", stdout="", stderr="process error", exit_code=2),
        event("unknown", status="failed", error={"message": "blocked by policy"}),
        event("declined", status="declined"),
        event("missing", status="completed", exit_code=0),
        event("pending", "item_started", status="in_progress")])
    parsed = pair.parse_codex_transcript(transcript)
    assert parsed["tool_calls"] == parsed["command_item_calls"] == 6
    assert parsed["failed_calls"] == 2 and parsed["rejected_calls"] == 1 and parsed["pending_calls"] == 1
    rows = {call["source_id"]: call for call in parsed["seq"]}
    assert rows["pending"]["use_line"] == 1 and rows["pending"]["replay_use_lines"] == [8]
    assert rows["failed"]["use_line"] == 2 and rows["failed"]["result_line"] == 4
    assert rows["failed"]["chars"] == len("process error") and rows["failed"]["aggregated_output"] is None
    assert rows["empty"]["chars"] == 0 and rows["empty"]["status"] == "returned"
    assert all(rows[key]["chars"] is None for key in ("pending", "unknown", "declined", "missing"))
    assert rows["unknown"]["exit_code"] is None and rows["unknown"]["error"] == {"message": "blocked by policy"}
    assert parsed["tool_chars"] is None and parsed["tool_chars_observed"] == len("process error")


def test_host_command_json_output_is_data_not_an_mcp_result_envelope(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    output = '{"result":"actual file contents"}'
    write_records(transcript, [{"type": "event_msg", "payload": {"type": "item_completed", "item": {
        "type": "CommandExecution", "id": "exec-json", "command": ["read JSON"], "status": "completed",
        "aggregated_output": output, "exit_code": 0}}}])
    parsed = pair.parse_codex_transcript(transcript)
    assert parsed["tool_chars"] == len(output) and parsed["seq"][0]["aggregated_output"] == output


@pytest.mark.parametrize("same_id", [True, False])
def test_host_command_and_direct_call_merge_only_with_explicit_equal_id(tmp_path: Path, same_id: bool) -> None:
    transcript = tmp_path / "transcript.jsonl"
    write_records(transcript, [
        {"type": "response_item", "payload": {"type": "function_call", "call_id": "call_shell", "name": "exec_command", "arguments": '{"cmd":"list"}'}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "call_shell", "output": "listed"}},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "CommandExecution",
            "id": "call_shell" if same_id else "exec-different", "command": ["list"], "status": "completed",
            "aggregated_output": "listed", "exit_code": 0}}}])
    parsed = pair.parse_codex_transcript(transcript)
    assert parsed["tool_calls"] == (1 if same_id else 2) and parsed["command_item_calls"] == 1
    leaf = next(call for call in parsed["seq"] if call["source_id_type"] == "codex_command_item_id")
    assert leaf["call_id"] == ("call_shell" if same_id else None)
    assert leaf["tool_use_id"] == ("call_shell" if same_id else None)
    if same_id:
        assert leaf["response_use_line"] == leaf["use_line"] == 1 and leaf["response_result_line"] == 2
    else:
        assert "response_use_line" not in leaf and leaf["use_line"] is None
    assert leaf["result_line"] == 3


@pytest.mark.parametrize("variant,passed", [("success", True), ("no_execution", False), ("blocked", False),
                                          ("missing_exit", False), ("wrong_command", False)])
def test_raw_smoke_requires_actual_successful_listing_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                          variant: str, passed: bool) -> None:
    source = tmp_path / "source"
    (source / "src/migloop").mkdir(parents=True)
    (source / "src/migloop/mcp_server.py").write_text("# source\n", encoding="utf-8")
    listing = "Get-ChildItem -Force -LiteralPath ." if os.name == "nt" else "ls -a ."
    item = {"id": "shell_item", "type": "command_execution", "command": listing if variant != "wrong_command" else "echo SOL_RAW_SMOKE_OK"}
    events: list[dict[str, Any]] = [{"type": "thread.started", "thread_id": "12345678-1234-1234-1234-123456789abc"}, {"type": "turn.started"}]
    if variant != "no_execution":
        events.extend([{"type": "item.started", "item": item},
                       {"type": "item.completed", "item": {**item, "status": "failed" if variant == "blocked" else "completed",
                            "aggregated_output": "blocked by policy" if variant == "blocked" else "",
                            "exit_code": None if variant == "missing_exit" else 1 if variant == "blocked" else 0}}])
    events.extend([{"type": "item.completed", "item": {"id": "answer", "type": "agent_message", "text": "SOL_RAW_SMOKE_OK"}},
                   {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 3}}])
    launches = fake_process(monkeypatch, "\n".join(json.dumps(row) for row in events) + "\n")
    rollout = tmp_path / "raw-rollout.jsonl"
    write_records(rollout, [{"type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "medium"}}])
    monkeypatch.setattr(pair, "find_codex_transcript", lambda thread_id: rollout)
    monkeypatch.setattr(pair, "collect_verdict", lambda *args: pytest.fail("raw smoke must not build ledger/verdict"))
    store = tmp_path / "raw-smoke"
    result = pair.run_smoke(source, store, arm="raw")
    assert result["smoke_passed"] is passed and result["connection_verified"] is passed
    assert result["sentinel_verified"] is True
    assert result["status"] == ("completed" if passed else "smoke_failed")
    assert result["include_in_pairs"] is False and result["arm"] == "raw"
    assert len(launches) == 1
    config = pair.read_json(store / "mcp.json")
    assert config["mcp_servers"] == {} and config["settings"]["features.shell_tool"] is True
    command = pair.read_json(store / "command.json")["argv"]
    assert command[command.index("-C") + 1] == str(store / "empty-pool")
    assert "SOL_RAW_SMOKE_OK" in (store / "prompt.md").read_text(encoding="utf-8")
    assert (store / "transcript.jsonl").read_bytes() == rollout.read_bytes()
