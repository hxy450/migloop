"""Nested native sources must invalidate the same ledger used by MCP and UI.

Before the shared discovery fix, nested append/add/remove changed neither
pool_key nor a warm session_ledger. No historical command is executed here.
"""
import json
from pathlib import Path

import pytest

from migloop import service, transcript_store
from tests.test_temporal_atom import call, message, result


def save_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def session(tmp_path, monkeypatch):
    for name in ("MIGLOOP_FROZEN_POOL", "MIGLOOP_FROZEN_ANCHOR", "MIGLOOP_FROZEN_ROOTS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(service, "_LEDGER_CACHE", {})
    monkeypatch.setattr(service, "extract_trace", lambda path: {"meta": {"session_format": "claude", "cwd": "/project"}})
    monkeypatch.setattr(service, "prior_roots", lambda *args: [])
    monkeypatch.setattr(service, "run_stage_intervals", lambda *args: [])
    main = save_rows(tmp_path / "1234abcd-root.jsonl", [message(0, "main")])
    child = save_rows(tmp_path / main.stem / "subagents/workflows/wf-1/node-1/agent-child.jsonl",
                      [message(1, "child")])
    return main, child


def test_pool_key_covers_nested_sources_and_non_transcript_sidecars(session):
    main, child = session
    key = service.pool_key([str(main)])
    assert {Path(item[0]) for item in key} == {main, child}
    child.with_suffix(".json").write_text('{"sidecar": true}', encoding="utf-8")
    assert service.pool_key([str(main)]) != key


@pytest.mark.parametrize("change", ["append", "add", "remove"])
def test_nested_mutation_invalidates_warm_ledger(session, change):
    main, child = session
    before_key = service.pool_key([str(main)])
    before = service.session_ledger(str(main))
    if change == "append":
        with child.open("a", encoding="utf-8") as out:
            out.write(json.dumps(message(2, "a later and longer message")) + "\n")
    elif change == "add":
        save_rows(child.with_name("agent-new.jsonl"), [message(3, "new child")])
    else:
        child.unlink()  # A fixture-owned file, not real source material.
    assert service.pool_key([str(main)]) != before_key
    after = service.session_ledger(str(main))
    assert after is not before
    observed = {Path(path) for path in transcript_store.sources(after)}
    assert (child in observed) is (change != "remove")
    if change == "add":
        assert child.with_name("agent-new.jsonl") in observed


def test_nested_write_and_raw_source_share_live_service_ledger(session):
    main, child = session
    save_rows(child, [message(1, "task"), call(2, "w1", "Write", file_path="/project/A.ets", content="hello"),
                      result(3, "w1")])
    ledger = service.session_ledger(str(main))
    assert {Path(path) for path in transcript_store.sources(ledger)} == {main, child}
    assert "/project/A.ets" in ledger.stories
    assert "agent-child" in ledger.agents
    assert service.session_ledger(str(main)) is ledger
