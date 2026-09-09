"""A frozen investigation has one explicitly configured observation book."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from migloop import atoms, service


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
    for name in ("_TRACE_CACHE", "_LEDGER_CACHE", "_FIXCHAIN_CACHE", "_ROOT_SIGNATURE_CACHE"):
        monkeypatch.setattr(service, name, {})


def anchored(monkeypatch, pool: Path, anchor: Path, roots: list[Path]) -> None:
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    monkeypatch.setenv("MIGLOOP_FROZEN_ANCHOR", str(anchor))
    monkeypatch.setenv("MIGLOOP_FROZEN_ROOTS", json.dumps([str(path) for path in roots]))


def test_explicit_parent_child_cwds_are_aliases_for_one_anchor_ledger(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z", cwd="/project")
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z", cwd="/project/app")
    anchored(monkeypatch, pool, anchor, [anchor, early])

    scope = service.observation_scope(str(early))
    assert scope["requested_root"] == str(early)
    assert scope["anchor"] == str(anchor)
    assert scope["roots"] == [str(early), str(anchor)]
    assert scope["mode"] == "frozen_anchor"
    assert scope["roots_source"] == "explicit_configuration"
    assert [row["cwd"] for row in scope["root_details"]] == ["/project", "/project/app"]
    assert service.locate_session(early.name) == str(anchor)
    first = service.session_ledger(str(early))
    second = service.session_ledger(str(anchor))
    assert first is second and atoms.ledger_identity(first) == atoms.ledger_identity(second)
    assert list(service._LEDGER_CACHE) == [str(anchor)]
    assert service.session_cwd(str(early)) == service.session_cwd(str(anchor)) == "/project/app"
    assert service.prior_roots("claude", str(early), "/ignored") == [str(early)]
    assert service.later_roots("claude", str(early), "/ignored") == []


def test_no_anchor_preserves_dynamic_root_scopes(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z")
    late = root(pool, "late2222", "2026-01-01T01:00:00Z")
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(pool))
    assert service.locate_session(early.name) == str(early)
    assert service.observation_scope(str(early))["mode"] == "frozen_dynamic"
    assert atoms.ledger_identity(service.session_ledger(str(early))) != atoms.ledger_identity(service.session_ledger(str(late)))


def test_frozen_anchor_does_not_guess_timezone_for_naive_timestamps(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00")
    anchored(monkeypatch, pool, anchor, [anchor])
    with pytest.raises(service.SessionLookupError, match="缺时区"):
        service.session_ledger(str(anchor))


def test_only_explicit_roots_are_admitted_and_request_must_be_an_alias(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z")
    foreign = root(pool, "foreign1", "2026-01-01T00:10:00Z", cwd="/other")
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    anchored(monkeypatch, pool, anchor, [early, anchor])

    scope = service.observation_scope(str(anchor))
    assert scope["roots"] == [str(early), str(anchor)]
    ledger = service.session_ledger(str(anchor))
    assert str(foreign) not in ledger.tag_paths.values()
    with pytest.raises(service.SessionLookupError, match="调用者指定"):
        service.observation_scope(str(foreign))


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


def test_stage_report_and_fixchain_high_level_views_use_anchor(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z")
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    marks = {"marks": [{"stage": "a2h-init", "ts": "2025-12-31T23:00:00Z"},
                       {"stage": "a2h-execute", "ts": "2026-01-01T00:30:00Z"},
                       {"stage": "a2h-verify", "ts": "2026-01-01T00:45:00Z"}]}
    (pool / "stage-marks.json").write_text(json.dumps(marks), encoding="utf-8")
    anchored(monkeypatch, pool, anchor, [early, anchor])

    assert service.run_stage_intervals(str(early), "/wrong") == service.run_stage_intervals(str(anchor), "/project")
    early_payload = service.fixchain_payload(str(early))
    anchor_payload = service.fixchain_payload(str(anchor))
    assert {k: v for k, v in early_payload.items() if k != "observation_scope"} == \
           {k: v for k, v in anchor_payload.items() if k != "observation_scope"}
    assert early_payload["observation_scope"]["requested_root"] == str(early)
    assert anchor_payload["observation_scope"]["requested_root"] == str(anchor)
    assert "observation_scope" not in service._FIXCHAIN_CACHE[str(anchor)][1]
    early_payload["observation_scope"]["roots"].clear()
    assert service.fixchain_payload(str(anchor))["observation_scope"]["roots"] == [str(early), str(anchor)]
    early_report = service.report_trace(str(early), static=True, with_chains=False)
    anchor_report = service.report_trace(str(anchor), static=True, with_chains=False)
    assert {k: v for k, v in early_report.items() if k != "observation_scope"} == \
           {k: v for k, v in anchor_report.items() if k != "observation_scope"}
    assert early_report["observation_scope"]["requested_root"] == str(early)
    assert "cross_hint" not in early_report["audit"]
    light = service.fixchain_light(str(early))
    assert light["sid8"] == service.fixchain_light(str(anchor))["sid8"]
    assert light["fixes"] == [] and light["fixers"] == []
    assert light["observation_scope"]["requested_root"] == str(early)


def test_fixchain_cache_tracks_rebuilt_ledger_not_only_root_files(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    marks = pool / "stage-marks.json"
    marks.write_text(json.dumps({"marks": [{"stage": "a2h-execute", "ts": "2026-01-01T00:00:00Z"}]}), encoding="utf-8")
    anchored(monkeypatch, pool, anchor, [anchor])
    service.fixchain_payload(str(anchor))
    first = service._FIXCHAIN_CACHE[str(anchor)][1]
    marks.write_text(json.dumps({"marks": [{"stage": "a2h-execute", "ts": "2026-01-01T00:30:00Z"}]}), encoding="utf-8")
    service.fixchain_payload(str(anchor))
    assert service._FIXCHAIN_CACHE[str(anchor)][1] is not first


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


def test_anchor_keeps_existing_identity_guard_independent(tmp_path, monkeypatch):
    from migloop import via
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z")
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    anchored(monkeypatch, pool, anchor, [early, anchor])
    ledger = service.session_ledger(str(early))
    current = atoms.ledger_identity(ledger)
    good = {"tool": "sessions", "has_result": True, "is_error": False,
            "text": f"账本身份: {current}\n# chains", "call_id": "c1", "item_id": None,
            "result_line": 2, "provenance": {"format": "test"}}
    bad = {**good, "call_id": "c2", "text": "账本身份: forged-ledger\n# chains"}
    assert via.trace_identity(ledger, [good], {})["bound"] is True
    assert via.trace_identity(ledger, [good, bad], {})["bound"] is False
