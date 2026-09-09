"""冻结实验只消费临时池;所有路径和转录均由测试构造,不扫描真实用户数据。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from migloop import atoms_collect, service


@pytest.fixture(autouse=True)
def isolated(monkeypatch: Any) -> None:
    monkeypatch.delenv("MIGLOOP_FROZEN_POOL", raising=False)
    for name in ("_TRACE_CACHE", "_LEDGER_CACHE", "_FIXCHAIN_CACHE"):
        monkeypatch.setattr(service, name, {})


def root(pool: Path, name: str = "abcdef12-main", ts: str = "2026-01-01T00:10:00Z", cwd: str = "/frozen/project") -> Path:
    pool.mkdir(parents=True, exist_ok=True)
    path = pool / (name + ".jsonl")
    path.write_text(json.dumps({"timestamp": ts, "type": "user", "cwd": cwd,
                                "message": {"role": "user", "content": "synthetic task"}}) + "\n", encoding="utf-8")
    return path


def fail_discovery(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("Frozen mode must not discover the global user pool")


def redirect_realpath(monkeypatch: Any, link: Path, destination: Path) -> None:
    """模拟Windows junction/symlink解析,不依赖测试机的符号链接创建权限。"""
    original = os.path.realpath
    source = os.path.normcase(os.path.abspath(link))

    def resolve(path: Any, *args: Any, **kwargs: Any) -> str:
        if os.path.normcase(os.path.abspath(path)) == source:
            return str(destination)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(service.os.path, "realpath", resolve)


def test_frozen_resolves_only_root_paths_and_unique_prefixes(tmp_path: Path, monkeypatch: Any) -> None:
    pool = tmp_path / "pool"
    first = root(pool)
    other = root(pool, "other123-main")
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    monkeypatch.setattr(service.adapters, "discover", fail_discovery)
    assert service.locate_session(str(first)) == str(first)
    assert service.locate_session(first.name) == str(first)
    assert service.locate_session("abcdef12", {"claude": str(tmp_path / "live")}) == str(first)
    assert service.locate_session("other123") == str(other)
    for value in ("", "unknown", "frozen/project"):
        with pytest.raises(service.SessionLookupError):
            service.locate_session(value)
    root(pool, "abcdef12-second")
    with pytest.raises(service.SessionLookupError, match="歧义"):
        service.locate_session("abcdef12")


def test_frozen_rejects_outside_paths_sibling_prefixes_and_subagent_roots(tmp_path: Path, monkeypatch: Any) -> None:
    pool = tmp_path / "pool"
    first = root(pool)
    outside = root(tmp_path / "pool-other")
    child = root(pool / first.stem / "subagents", "agent-child")
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    monkeypatch.setattr(service.adapters, "discover", fail_discovery)
    for value in (str(outside), "../pool-other/" + outside.name, str(child),
                  first.stem + "/subagents/" + child.name, str(pool)):
        with pytest.raises(service.SessionLookupError):
            service.locate_session(value)
    with pytest.raises(service.SessionLookupError, match="越出"):
        service.session_ledger(str(outside))


def test_frozen_root_rejects_symlink_resolution_outside_pool(tmp_path: Path, monkeypatch: Any) -> None:
    pool = tmp_path / "pool"
    link = root(pool, "link")
    outside = root(tmp_path / "outside", "target")
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    redirect_realpath(monkeypatch, link, outside)
    with pytest.raises(service.SessionLookupError, match="越出"):
        service.locate_session("link.jsonl")


def test_frozen_rejects_escaped_subagent_before_collect_or_extract(tmp_path: Path, monkeypatch: Any) -> None:
    pool = tmp_path / "pool"
    main = root(pool)
    child = root(pool / main.stem / "subagents", "agent-child")
    outside = root(tmp_path / "outside", "target")
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    redirect_realpath(monkeypatch, child, outside)
    monkeypatch.setattr(service.atoms_collect, "collect_cc_pool", fail_discovery)
    monkeypatch.setattr(service.adapters, "detect", fail_discovery)
    for operation in (lambda: service._collect("claude", [str(main)]),
                      lambda: service.extract_trace(str(main)), lambda: service.pool_key([str(main)])):
        with pytest.raises(service.SessionLookupError, match="越出"):
            operation()


def test_frozen_prior_and_later_roots_never_search_live_cwd(tmp_path: Path, monkeypatch: Any) -> None:
    pool = tmp_path / "pool"
    first = root(pool, "first123", "2026-01-01T00:01:00Z")
    second = root(pool, "second12", "2026-01-01T00:05:00Z")
    current = root(pool)
    later = root(pool, "later123", "2026-01-01T00:20:00Z")
    root(tmp_path / "live", "external", "2026-01-01T00:09:00Z")
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    for name in ("find_prior_claude_roots", "find_later_claude_roots", "find_prior_codex_roots", "find_later_codex_roots"):
        monkeypatch.setattr(service.crosschain, name, fail_discovery)
    for fmt in ("claude", "codex"):
        assert service.prior_roots(fmt, str(current), str(tmp_path / "live")) == [str(second), str(first)]
        assert service.later_roots(fmt, str(current), str(tmp_path / "live")) == [str(later)]


def test_frozen_stage_marks_only_come_from_the_pool(tmp_path: Path, monkeypatch: Any) -> None:
    pool = tmp_path / "pool"
    live = tmp_path / "live"
    main = root(pool, cwd=str(live))
    marks = {"marks": [{"stage": "a2h-init", "ts": "2026-01-01T00:00:00Z"},
                       {"stage": "a2h-execute", "ts": "2026-01-01T01:00:00Z"},
                       {"stage": "a2h-verify", "ts": "2026-01-01T02:00:00Z"}]}
    live_marks = live / ".migbot/metrics/run/facts/stage-marks.json"
    live_marks.parent.mkdir(parents=True)
    live_marks.write_text(json.dumps(marks), encoding="utf-8")
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    assert service.run_stage_intervals(str(main), str(live)) == []
    (pool / "stage-marks.json").write_text(json.dumps(marks), encoding="utf-8")
    intervals = service.run_stage_intervals(str(main), str(live))
    assert atoms_collect.fix_boundary(intervals).startswith("2026-01-01T01:00:00")
    redirect_realpath(monkeypatch, pool / "stage-marks.json", live_marks)
    with pytest.raises(service.SessionLookupError, match="越出"):
        service.run_stage_intervals(str(main), str(live))


def test_frozen_cc_collection_keeps_all_sources_in_pool(tmp_path: Path, monkeypatch: Any) -> None:
    pool = tmp_path / "pool"
    main = root(pool)
    child = root(pool / main.stem / "subagents", "agent-child")
    old = root(pool, "older123", "2026-01-01T00:01:00Z")
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    ledger = service._collect("claude", [str(old), str(main)])
    assert "agent-child" in ledger.agents and "__main__:older123" in ledger.agents
    assert {os.path.normpath(p) for p in ledger.tag_paths.values()} == {str(old), str(main), str(child)}


def test_frozen_codex_passes_explicit_scan_root_to_extract_and_collect(tmp_path: Path, monkeypatch: Any) -> None:
    pool = tmp_path / "pool"
    main = root(pool)
    seen: list[tuple[str, str | None]] = []

    def extract(path: str, sessions_root: str | None = None) -> dict[str, Any]:
        seen.append(("extract", sessions_root))
        return {"meta": {"session_format": "codex"}}

    def collect(path: str, seq: list[int], sessions_root: str | None = None) -> dict[str, Any]:
        seen.append(("collect", sessions_root))
        return {}

    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    monkeypatch.setattr(service.adapters, "detect", lambda path: SimpleNamespace(FORMAT="codex", extract=extract))
    monkeypatch.setattr(service.atoms_collect, "collect_codex", collect)
    service.extract_trace(str(main))
    service._collect("codex", [str(main)])
    assert seen == [("extract", str(pool)), ("collect", str(pool))]


def test_frozen_trace_cache_does_not_reuse_nonfrozen_product(tmp_path: Path, monkeypatch: Any) -> None:
    pool = tmp_path / "pool"
    main = root(pool)
    modes: list[bool] = []

    def extract(path: str) -> dict[str, Any]:
        mode = bool(os.environ.get("MIGLOOP_FROZEN_POOL"))
        modes.append(mode)
        return {"frozen": mode}

    monkeypatch.setattr(service.adapters, "detect", lambda path: SimpleNamespace(FORMAT="claude", extract=extract))
    assert service.extract_trace(str(main))["frozen"] is False
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    assert service.extract_trace(str(main))["frozen"] is True
    assert modes == [False, True]


def test_nonfrozen_lookup_and_prior_discovery_remain_unchanged(tmp_path: Path, monkeypatch: Any) -> None:
    local = root(tmp_path / "normal")
    row = SimpleNamespace(session_id="id-123", project="test-project", path=str(local))
    monkeypatch.setattr(service.adapters, "discover", lambda roots: iter([row]))
    assert service.locate_session("test-project") == str(local)
    assert service.locate_session("id-") == str(local)
    monkeypatch.setattr(service.crosschain, "find_prior_claude_roots", lambda path, limit: ["unchanged"])
    assert service.prior_roots("claude", str(local), "/live") == ["unchanged"]
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(tmp_path / "missing"))
    with pytest.raises(service.SessionLookupError, match="目录不存在"):
        service.locate_session("id-")


def test_frozen_adapter_skips_all_live_source_probes(tmp_path: Path, monkeypatch: Any) -> None:
    from migloop.adapters import claude
    pool = tmp_path / "pool"
    root(pool)
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    with monkeypatch.context() as guarded:
        guarded.setattr("builtins.open", fail_discovery)
        guarded.setattr(claude.os.path, "isfile", fail_discovery)
        guarded.setattr(claude.os.path, "isdir", fail_discovery)
        guarded.setattr(claude.os, "walk", fail_discovery)
        assert claude._resolve_source_path("Source.java", [str(tmp_path)]) is None
        assert claude._script_probed_paths("Bash", {"command": "cat Source.java"}, str(tmp_path)) == []
        assert claude._infer_visible_source_lines("Bash", {"command": "cat Source.java"}, "class Source {}", str(tmp_path)) == []
        assert claude._find_gradle_root([str(tmp_path / "Source.java")]) is None
        assert claude._scan_android_total(str(tmp_path)) is None
        assert claude._live_source_line_count(str(tmp_path / "Source.java")) == 0


def test_frozen_extract_retains_recorded_reads_without_opening_live_sources(tmp_path: Path, monkeypatch: Any) -> None:
    import builtins
    from migloop.adapters import claude
    from tests.test_atoms import _call, _read_call, _rec, _write_jsonl
    pool = tmp_path / "pool"
    live = tmp_path / "live"
    source = live / "app/src/main/java/Source.java"
    source.parent.mkdir(parents=True)
    source.write_text("class DifferentLiveSource {}\n", encoding="utf-8")
    (live / "settings.gradle").write_text("rootProject.name = 'live'", encoding="utf-8")
    main = pool / "abcdef12-main.jsonl"
    records = [_rec("2026-01-01T00:00:00Z", "user", "read source"),
               *_read_call("2026-01-01T00:00:10Z", "read1", str(source), "class RecordedSource {}\n"),
               *_call("2026-01-01T00:00:20Z", "bash1", "Bash", {"command": "cat " + source.as_posix()},
                      "class RecordedSource {}\n")]
    for record in records:
        record["cwd"] = str(live)
    _write_jsonl(str(main), records)
    original_open = builtins.open

    def pool_only(path: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(path, (str, os.PathLike)) and Path(path).resolve().is_relative_to(live):
            raise AssertionError(f"Live source was opened in frozen mode: {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    monkeypatch.setattr(builtins, "open", pool_only)
    trace = claude.extract(str(main))
    recorded_read = next(t for t in trace["tools"] if t["name"] == "Read")
    assert recorded_read["rlines"] == 2 and recorded_read["rtotal"] == 2
    assert trace["lineage"]["android_total"] is None


def test_frozen_subagent_cache_cannot_reuse_live_enriched_entry(tmp_path: Path, monkeypatch: Any) -> None:
    import builtins
    from migloop.adapters import claude
    from tests.test_atoms import _call, _rec, _write_jsonl
    pool = tmp_path / "pool"
    live = tmp_path / "live"
    source = live / "app/src/main/java/Source.java"
    source.parent.mkdir(parents=True)
    source.write_text("class Source {\n    int count = 1;\n}\n", encoding="utf-8")
    main = root(pool, cwd=str(live))
    child = pool / main.stem / "subagents/agent-child.jsonl"
    child_meta = child.with_suffix(".meta.json")
    records = [_rec("2026-01-01T00:00:00Z", "user", "inspect source"),
               *_call("2026-01-01T00:00:10Z", "bash1", "Bash", {"command": "cat " + source.as_posix()},
                      "class Source {\n    int count = 1;\n}\n")]
    for record in records:
        record["cwd"] = str(live)
    _write_jsonl(str(child), records)
    child_meta.write_text(json.dumps({"agentType": "general-purpose", "description": "inspect"}), encoding="utf-8")
    monkeypatch.setattr(claude, "_SUB_CACHE", {})
    claude.extract(str(main))
    assert claude._SUB_CACHE
    cached = next(iter(claude._SUB_CACHE.values()))
    normal_signature = cached[0]
    cached[1]["live_cache_sentinel"] = True
    original_open = builtins.open

    def pool_only(path: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(path, (str, os.PathLike)) and Path(path).resolve().is_relative_to(live):
            raise AssertionError(f"Live source was opened in frozen mode: {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    monkeypatch.setattr(builtins, "open", pool_only)
    frozen = claude.extract(str(main))
    assert frozen["agents"] and all("live_cache_sentinel" not in agent for agent in frozen["agents"])
    assert next(iter(claude._SUB_CACHE.values()))[0] != normal_signature
