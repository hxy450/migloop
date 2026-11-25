"""A frozen investigation has one explicitly configured observation book.

Observation-scope validation only; the anchored ledger / fix-chain cases moved with the repair chain
to fuxi-ailabs/a2h-memory fixchain/."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from migloop import service


def root(pool: Path, name: str, ts: str, *, cwd: str | None = "/project") -> Path:
    pool.mkdir(parents=True, exist_ok=True)
    path = pool / f"{name}.jsonl"
    record = {"timestamp": ts, "type": "user", "message": {"role": "user", "content": "task"}}
    if cwd is not None:
        record["cwd"] = cwd
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for name in ("MIGLOOP_FROZEN_POOL", "MIGLOOP_FROZEN_ANCHOR", "MIGLOOP_FROZEN_ROOTS"):
        monkeypatch.delenv(name, raising=False)
    for name in ("_TRACE_CACHE", "_ROOT_SIGNATURE_CACHE"):
        monkeypatch.setattr(service, name, {})


def anchored(monkeypatch, pool: Path, anchor: Path, roots: list[Path]) -> None:
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    monkeypatch.setenv("MIGLOOP_FROZEN_ANCHOR", str(anchor))
    monkeypatch.setenv("MIGLOOP_FROZEN_ROOTS", json.dumps([str(path) for path in roots]))


@pytest.mark.parametrize("missing", ["anchor", "roots"])
def test_anchor_and_roots_must_be_configured_together(tmp_path, monkeypatch, missing):
    pool = tmp_path / "pool"
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    if missing == "anchor":
        monkeypatch.setenv("MIGLOOP_FROZEN_ROOTS", json.dumps([str(anchor)]))
    else:
        monkeypatch.setenv("MIGLOOP_FROZEN_ANCHOR", str(anchor))
    with pytest.raises(service.SessionLookupError, match="同时配置"):
        service.observation_scope(str(anchor))


def test_explicit_scope_validation_is_fail_closed(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z")
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    later = root(pool, "later333", "2026-01-01T02:00:00Z")
    codex = pool / "codex444.jsonl"
    codex.write_text(json.dumps({"timestamp": "2026-01-01T00:30:00Z", "type": "session_meta",
                                 "payload": {"id": "01a00000-0000-0000-0000-000000000001", "cwd": "/project"}}) + "\n",
                     encoding="utf-8")
    anchored(monkeypatch, pool, anchor, [early, anchor])

    cases = [
        ("not-json", "JSON 数组"),
        ("[]", "非空"),
        (json.dumps([str(early), str(early), str(anchor)]), "重复"),
        (json.dumps([str(early)]), "必须包含"),
        (json.dumps([str(early), str(anchor), str(later)]), "晚于 anchor"),
        (json.dumps([str(early), str(codex), str(anchor)]), "不同的会话格式"),
    ]
    for configured, message in cases:
        monkeypatch.setenv("MIGLOOP_FROZEN_ROOTS", configured)
        with pytest.raises(service.SessionLookupError, match=message):
            service.observation_scope(str(anchor))


def test_root_times_are_compared_as_utc_and_invalid_times_are_rejected(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T01:30:00+02:00")  # 2025-12-31 23:30Z
    anchor = root(pool, "anchor22", "2026-01-01T00:00:00Z")
    later = root(pool, "later333", "2026-01-01T00:30:00-01:00")   # 2026-01-01 01:30Z
    invalid = root(pool, "invalid4", "not-a-time")
    anchored(monkeypatch, pool, anchor, [anchor, early])
    assert service.observation_scope(str(anchor))["roots"] == [str(early), str(anchor)]
    monkeypatch.setenv("MIGLOOP_FROZEN_ROOTS", json.dumps([str(anchor), str(later)]))
    with pytest.raises(service.SessionLookupError, match="晚于 anchor"):
        service.observation_scope(str(anchor))
    monkeypatch.setenv("MIGLOOP_FROZEN_ROOTS", json.dumps([str(anchor), str(invalid)]))
    with pytest.raises(service.SessionLookupError, match="可排序"):
        service.observation_scope(str(anchor))


def test_anchor_requires_pool_and_all_paths_stay_inside_it(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    outside = root(tmp_path / "outside", "outside1", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("MIGLOOP_FROZEN_ANCHOR", str(anchor))
    monkeypatch.setenv("MIGLOOP_FROZEN_ROOTS", json.dumps([str(anchor)]))
    with pytest.raises(service.SessionLookupError, match="只能与"):
        service.observation_scope(str(anchor))
    with pytest.raises(service.SessionLookupError, match="只能与"):
        service.locate_session(str(anchor))
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    monkeypatch.setenv("MIGLOOP_FROZEN_ROOTS", json.dumps([str(outside), str(anchor)]))
    with pytest.raises(service.SessionLookupError, match="越出"):
        service.observation_scope(str(anchor))


def test_signature_uses_first_record_cache_not_full_trace(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z")
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    anchored(monkeypatch, pool, anchor, [early, anchor])
    calls = 0
    original = service.adapters.detect

    def counted(path):
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(service.adapters, "detect", counted)
    service.observation_scope(str(early))
    first = calls
    service.observation_scope(str(early))
    assert first == 2 and calls == first


def test_signature_cache_is_bounded(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z")
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    anchored(monkeypatch, pool, anchor, [early, anchor])
    monkeypatch.setattr(service, "_ROOT_SIGNATURE_CACHE_MAX", 1)
    service.observation_scope(str(anchor))
    assert len(service._ROOT_SIGNATURE_CACHE) == 1

