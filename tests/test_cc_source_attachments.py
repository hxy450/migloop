"""Every archived attachment is raw material, not an inferred actor or action."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from migloop import atoms, atoms_collect, cc_sources, investigation, service, transcript_store as store
from tests.test_cc_source_discovery import SID, dump


def make_pool(tmp_path: Path) -> tuple[str, list[Path]]:
    root = dump(tmp_path / f"{SID}.jsonl")
    files = {
        "workflows/wf-one.json": '{\n  "label": "attachment needle /project/A.ets"\n}\n',
        "tool-results/result-one.txt": "heading\nattachment needle /project/A.ets\nlast line\n",
        "workflows/scripts/task.js": "// attachment needle /project/A.ets\nconst value = 1;\n",
        "subagents/workflows/wf-one/agent-child.meta.json": '{"description":"attachment needle"}\n',
        "other/unknown.data": "attachment needle\n",
    }
    paths = []
    for relative, text in files.items():
        path = tmp_path / SID / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return root, paths


def build(root: str) -> atoms.Ledger:
    discovered = cc_sources.discover([root])
    agents = atoms_collect.collect_cc_pool([root], [0], sources=discovered)
    return atoms.build_ledger(agents, auxiliary_sources=discovered.auxiliary_sources,
                             source_metadata=discovered.source_metadata)


def test_all_attachments_are_discovered_without_actor_inference(tmp_path: Path) -> None:
    root, paths = make_pool(tmp_path)
    sources = cc_sources.discover([root])
    assert {os.path.normpath(p) for p in sources.auxiliary_sources} == {str(p) for p in paths}
    assert sources.actor_transcripts == (root,)
    assert {os.path.normpath(p) for p in cc_sources.all_source_paths(root)} == {root, *(str(p) for p in paths)}
    assert cc_sources.subagent_paths(root) == []
    ledger = build(root)
    assert set(ledger.agents) == {"__main__:11111111"}
    assert ledger.stories == {}
    registry = store.sources(ledger)
    assert len(registry) == 6
    assert all(registry[os.path.normcase(str(p))] == set() for p in paths)


def test_multiline_attachments_are_searchable_and_expand_exact_physical_lines(tmp_path: Path) -> None:
    root, paths = make_pool(tmp_path)
    ledger = build(root)
    data = investigation.query(ledger, "search", {"q": "attachment needle", "at": "latest", "include_undated": True})
    assert data["rows"] == []
    hits = data["undated"]["rows"]
    assert len(hits) == 5
    assert all(hit["agents"] == [] and hit["annotations"] == [] and hit["ts"] is None for hit in hits)
    expected = {path.name: path.read_text(encoding="utf-8").splitlines() for path in paths}
    for hit in hits:
        record = store.resolve(ledger, hit["ref"])
        assert record.raw == expected[hit["source"]][hit["line"] - 1]
        result = investigation.query(ledger, "record", {"ref": hit["ref"], "at": "latest", "include_undated": True})
        assert result["text"] == record.raw
        assert result["ts"] is None


def test_binary_attachment_remains_registered_and_reports_decode_gap(tmp_path: Path) -> None:
    root, _ = make_pool(tmp_path)
    binary = tmp_path / SID / "tool-results/opaque.bin"
    binary.write_bytes(b"\xff\x00attachment needle\n")
    ledger = build(root)
    assert os.path.normcase(str(binary)) in store.sources(ledger)
    data = investigation.query(ledger, "search", {"q": "attachment needle", "at": "latest", "include_undated": True})
    assert any("opaque.bin" in gap["source"] for gap in data["gaps"])
    assert ledger.stories == {}


def test_attachments_never_enter_actor_script_prescan_or_walk(tmp_path: Path, monkeypatch: Any) -> None:
    root, _ = make_pool(tmp_path)
    child = dump(tmp_path / SID / "subagents/workflows/wf-one/agent-child.jsonl")
    prescanned, walked = [], []

    def prescan(paths: list[str]) -> Any:
        prescanned.extend(paths)
        return atoms_collect.ScriptTable()

    def walk(path: str, identity: str, session: str, *args: Any) -> Any:
        walked.append(path)
        return atoms.AgentRec(identity, session, sources=[path])

    monkeypatch.setattr(atoms_collect, "_prescan_scripts", prescan)
    monkeypatch.setattr(atoms_collect, "_walk", walk)
    discovered = cc_sources.discover([root])
    atoms_collect.collect_cc_pool([root], [0], sources=discovered)
    assert prescanned == walked
    assert [os.path.normpath(p) for p in walked] == [root, child]
    assert len(discovered.auxiliary_sources) == 5


@pytest.mark.parametrize("change", ["append", "add", "remove"])
def test_attachment_changes_invalidate_warm_service_ledger(tmp_path: Path, monkeypatch: Any, change: str) -> None:
    root, attachments = make_pool(tmp_path)
    for name in ("MIGLOOP_FROZEN_POOL", "MIGLOOP_FROZEN_ANCHOR", "MIGLOOP_FROZEN_ROOTS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(service, "_LEDGER_CACHE", {})
    monkeypatch.setattr(service, "extract_trace", lambda path: {"meta": {"session_format": "claude", "cwd": "/project"}})
    monkeypatch.setattr(service, "prior_roots", lambda *args: [])
    monkeypatch.setattr(service, "run_stage_intervals", lambda *args: [])
    before_key = service.pool_key([root])
    before = service.session_ledger(root)
    target = attachments[1]
    if change == "append":
        target.write_text(target.read_text(encoding="utf-8") + "new line\n", encoding="utf-8")
    elif change == "add":
        target = target.with_name("new-attachment.txt")
        target.write_text("a newly archived line\n", encoding="utf-8")
    else:
        target.unlink()  # Only this test's fixture file.
    assert service.pool_key([root]) != before_key
    after = service.session_ledger(root)
    assert after is not before
    assert (os.path.normcase(str(target)) in store.sources(after)) == (change != "remove")


def test_json_attachment_timestamp_is_data_not_historical_record_time(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    path = tmp_path / SID / "workflow.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"timestamp": "2026-01-01T00:00:00Z", "label": "attachment needle"}) + "\n", encoding="utf-8")
    ledger = build(root)
    row = store.read_record(str(path), 1)
    assert row.ts is None
    assert store.resolve(ledger, row.ref).ts is None
    data = investigation.query(ledger, "search", {"q": "attachment needle", "at": "latest", "include_undated": True})
    assert data["rows"] == [] and len(data["undated"]["rows"]) == 1
