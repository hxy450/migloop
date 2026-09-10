"""CC source coverage and identity boundaries; all transcript bodies are synthetic."""
from __future__ import annotations

import glob
import json
import os
import shutil
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from migloop import atoms, atoms_collect, cc_sources, raw_events, transcript_store


SID = "11111111-2222-3333-4444-555555555555"
SID2 = "22222222-2222-3333-4444-555555555555"


def dump(path: Path, records: list[dict[str, Any]] | None = None) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if records is None:
        records = [{"type": "assistant", "message": {"role": "assistant", "content": []}}]
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return str(path)


def call(tool: str, inp: dict[str, Any], *, minute: int = 0) -> list[dict[str, Any]]:
    return [
        {"timestamp": f"2026-01-01T00:{minute:02d}:00Z", "cwd": "/proj", "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": "call-1", "name": tool,
                                                "input": inp}]}},
        {"timestamp": f"2026-01-01T00:{minute:02d}:01Z", "cwd": "/proj", "message": {
            "role": "user", "content": [{"type": "tool_result", "tool_use_id": "call-1",
                                           "content": "ok", "is_error": False}]}},
    ]


def test_nested_unknown_transcript_is_in_raw_registry(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    child = dump(tmp_path / SID / "subagents/workflows/wf-1/agent-child.jsonl", [
        {"timestamp": "2026-01-01T00:00:00Z", "type": "assistant", "message": {
            "role": "assistant", "content": [{"type": "unfamiliar", "opaque": "synthetic record"}]}},
    ])
    ledger = atoms.build_ledger(atoms_collect.collect_cc(root, [0]))
    assert set(ledger.agents) == {"__main__:11111111", "agent-child"}
    assert set(transcript_store.sources(ledger)) == {
        os.path.normcase(os.path.abspath(root)), os.path.normcase(os.path.abspath(child)),
    }
    assert ledger.agents["agent-child"].actions == []


@pytest.mark.parametrize("pool", [False, True])
def test_nested_scripts_are_prescanned_before_collect(tmp_path: Path, pool: bool) -> None:
    root = dump(tmp_path / f"{SID}.jsonl", call("Bash", {"command": "python3 /proj/make.py"}, minute=1))
    dump(tmp_path / SID / "subagents/workflows/wf-1/agent-script.jsonl", call("Write", {
        "file_path": "/proj/make.py", "content": "open('/proj/output.md', 'w').write('synthetic')\n",
    }))
    if pool:
        other = dump(tmp_path / f"{SID2}.jsonl")
        agents = atoms_collect.collect_cc_pool([other, root], [0])
    else:
        agents = atoms_collect.collect_cc(root, [0])
    action, = agents["__main__:11111111"].actions
    assert any(f.path == "/proj/output.md" and f.op == "write" for f in action.files)
    assert not action.detail.get("unknown_scripts")


@pytest.mark.parametrize("cross_root", [False, True])
def test_duplicate_agent_stem_rejects_before_prescan_or_walk(tmp_path: Path, monkeypatch: Any,
                                                          cross_root: bool) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    dump(tmp_path / SID / "subagents/agent-same.jsonl")
    if cross_root:
        other = dump(tmp_path / f"{SID2}.jsonl")
        dump(tmp_path / SID2 / "subagents/agent-same.jsonl")
        roots = [root, other]
    else:
        dump(tmp_path / SID / "subagents/workflows/wf-1/agent-same.jsonl")
        roots = [root]
    monkeypatch.setattr(atoms_collect, "_prescan_scripts", lambda *a: pytest.fail("prescan ran before validation"))
    monkeypatch.setattr(atoms_collect, "_walk", lambda *a: pytest.fail("walk ran before validation"))
    seq = [7]
    with pytest.raises(ValueError, match="ambiguous.*agent-same"):
        atoms_collect.collect_cc_pool(roots, seq)
    assert seq == [7]


def test_same_root_short_id_rejects_instead_of_overwriting(tmp_path: Path) -> None:
    one = dump(tmp_path / f"{SID}.jsonl")
    two = dump(tmp_path / "11111111-9999-9999-9999-999999999999.jsonl")
    with pytest.raises(ValueError, match="ambiguous.*__main__:11111111"):
        atoms_collect.collect_cc_pool([one, two], [0])


def test_directory_nesting_never_creates_parent_or_dispatch(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    dump(tmp_path / SID / "subagents/agent-parent.jsonl")
    dump(tmp_path / SID / "subagents/agent-parent/subagents/agent-child.jsonl")
    ledger = atoms.build_ledger(atoms_collect.collect_cc(root, [0]))
    assert set(ledger.agents) == {"__main__:11111111", "agent-parent", "agent-child"}
    assert all(a.parent is None for a in ledger.agents.values())
    assert all(not a.actions for a in ledger.agents.values())


def test_flat_order_ids_sources_and_stage_fallback_stay_compatible(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl", call("Read", {"file_path": "/proj/input.md"}))
    z = dump(tmp_path / SID / "subagents/agent-z.jsonl", call("Read", {"file_path": "/proj/z.md"}))
    a = dump(tmp_path / SID / "subagents/agent-a.jsonl", call("Read", {"file_path": "/proj/a.md"}))
    stages = [{"stage": "a2h-execute", "start_ts": "2026-01-01T00:00:00Z",
               "end_ts": "2026-01-01T00:05:00Z"}]
    agents = atoms_collect.collect_cc(root, [0], stage_intervals=stages)
    assert list(agents) == ["__main__:11111111", "agent-a", "agent-z"]
    legacy_paths = [root, *sorted(glob.glob(os.path.splitext(root)[0] + "/subagents/*.jsonl"))]
    assert [agent.sources for agent in agents.values()] == [[path] for path in legacy_paths]
    assert [agent.session for agent in agents.values()] == ["11111111"] * 3
    assert agents["__main__:11111111"].actions[0].stage == "a2h-execute"
    assert agents["agent-a"].actions[0].stage is None


def test_prescan_and_walk_share_exact_discovery_snapshot(tmp_path: Path, monkeypatch: Any) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    a = dump(tmp_path / SID / "subagents/agent-a.jsonl")
    z = dump(tmp_path / SID / "subagents/workflows/wf-1/agent-z.jsonl")
    prescanned: list[str] = []
    walked: list[str] = []

    def prescan(paths: list[str]) -> Any:
        prescanned.extend(paths)
        # Discovery must not be re-run between the prescan and actual walk.
        dump(tmp_path / SID / "subagents/agent-created-later.jsonl")
        return atoms_collect.ScriptTable()

    def walk(path: str, agent: str, session: str, *args: Any) -> Any:
        walked.append(path)
        return atoms.AgentRec(agent, session, sources=[path])

    monkeypatch.setattr(atoms_collect, "_prescan_scripts", prescan)
    monkeypatch.setattr(atoms_collect, "_walk", walk)
    atoms_collect.collect_cc_pool([root], [0])
    assert prescanned == walked
    assert [os.path.normpath(path) for path in walked] == [root, a, z]


def build(roots: list[str]) -> atoms.Ledger:
    sources = cc_sources.discover(roots)
    agents = atoms_collect.collect_cc_pool(roots, [0], sources=sources)
    return atoms.build_ledger(agents, auxiliary_sources=sources.auxiliary_sources,
                             source_metadata=sources.source_metadata)


def test_discovery_covers_only_own_subtree_and_keeps_all_jsonls(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    a = dump(tmp_path / SID / "subagents/agent-a.jsonl")
    b = dump(tmp_path / SID / "subagents/workflows/wf-1/agent-b.jsonl")
    journal = dump(tmp_path / SID / "subagents/workflows/wf-1/journal.jsonl", [{
        "type": "started", "key": "synthetic", "agentId": "agent-b",
    }])
    dump(tmp_path / SID / "workflows/outside-subagents.jsonl")
    dump(tmp_path / "unrelated.jsonl")
    (tmp_path / SID / "subagents/agent-a.meta.json").write_text("{}", encoding="utf-8")
    got = cc_sources.subagent_paths(root)
    assert [os.path.normpath(p) for p in got] == sorted([a, b, journal])


def test_journals_and_unknown_nested_records_remain_unowned_raw_sources(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    actor = dump(tmp_path / SID / "subagents/workflows/wf-1/arbitrary-native-name.jsonl")
    journals = [dump(tmp_path / SID / f"subagents/workflows/wf-{i}/journal.jsonl", [
        {"type": "started", "key": "task", "agentId": "not-a-dispatch-edge"},
        {"type": "result", "key": "task", "result": {"opaque": "synthetic"}},
    ]) for i in (1, 2)]
    unknown = dump(tmp_path / SID / "subagents/workflows/wf-2/agent-unknown.jsonl", [
        {"type": "new-protocol", "opaque": "not enough to identify an actor"},
    ])
    discovered = cc_sources.discover([root])
    assert {os.path.normpath(p) for p in discovered.actor_transcripts} == {root, actor}
    assert {os.path.normpath(p) for p in discovered.auxiliary_sources} == {*journals, unknown}
    ledger = build([root])
    assert set(ledger.agents) == {"__main__:11111111", "arbitrary-native-name"}
    assert all(a.parent is None for a in ledger.agents.values())
    assert all(not a.actions for a in ledger.agents.values())
    registry = transcript_store.sources(ledger)
    assert len(registry) == 5
    assert all(registry[os.path.normcase(p)] == set() for p in [*journals, unknown])
    assert all(os.path.normcase(p) not in transcript_store.sources(ledger, "__main__:11111111")
               for p in journals)
    inventory = raw_events.inventory(ledger)
    assert inventory["source_count"] == 5
    assert inventory["events"] == []


def test_flat_nonstandard_empty_unknown_legacy_sources_are_not_reclassified_by_name(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    dump(tmp_path / SID / "subagents/agent-s.jsonl")
    dump(tmp_path / SID / "subagents/legacy-name.jsonl", [])
    dump(tmp_path / SID / "subagents/unknown.jsonl", [{"unknown": True}])
    dump(tmp_path / SID / "subagents/not-named-journal.jsonl", [{"type": "started", "key": "task"}])
    discovered = cc_sources.discover([root])
    assert {Path(p).name for p in discovered.auxiliary_sources} == {"not-named-journal.jsonl"}
    assert set(atoms_collect.collect_cc(root, [0], sources=discovered)) == {
        "__main__:11111111", "agent-s", "legacy-name", "unknown",
    }


def test_unknown_empty_or_malformed_nested_sources_never_create_actors(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    empty = Path(dump(tmp_path / SID / "subagents/workflows/empty.jsonl", []))
    broken = Path(dump(tmp_path / SID / "subagents/workflows/broken.jsonl", []))
    broken.write_bytes(b'{"unrecognized":true}\nnot-json\n\xff\n')
    discovered = cc_sources.discover([root])
    assert {os.path.normpath(p) for p in discovered.auxiliary_sources} == {str(empty), str(broken)}
    assert set(atoms_collect.collect_cc(root, [0], sources=discovered)) == {"__main__:11111111"}


def test_cross_root_same_journal_name_does_not_merge_or_become_actor(tmp_path: Path) -> None:
    roots = [dump(tmp_path / f"{sid}.jsonl") for sid in (SID, SID2)]
    for sid in (SID, SID2):
        dump(tmp_path / sid / "subagents/workflows/wf-1/journal.jsonl", [{"type": "started", "key": "task"}])
    ledger = build(roots)
    assert len(ledger.auxiliary_sources) == 2
    assert len(ledger.source_stats) == 4
    assert set(ledger.agents) == {"__main__:11111111", "__main__:22222222"}


def test_auxiliary_identity_covers_logical_path_content_and_stats_without_pool_path(tmp_path: Path) -> None:
    first = tmp_path / "pool-one"
    root = dump(first / f"{SID}.jsonl")
    journal1 = dump(first / SID / "subagents/workflows/wf-1/journal.jsonl", [{"type": "started", "key": "same"}])
    journal2 = dump(first / SID / "subagents/workflows/wf-2/journal.jsonl", [{"type": "started", "key": "same"}])
    ledger = build([root])
    assert len(ledger.auxiliary_sources) == 2 and len(ledger.source_stats) == 3
    initial = atoms.ledger_identity(ledger)
    one_only = atoms.build_ledger({}, auxiliary_sources=[journal1], source_metadata=ledger.source_metadata)
    other_only = atoms.build_ledger({}, auxiliary_sources=[journal2], source_metadata=ledger.source_metadata)
    assert atoms.ledger_identity(one_only) != atoms.ledger_identity(other_only)
    reverse = atoms.build_ledger(ledger.agents, auxiliary_sources=reversed(ledger.auxiliary_sources),
                                 source_metadata=ledger.source_metadata)
    assert atoms.ledger_identity(reverse) == initial
    shutil.copytree(first, tmp_path / "pool-two")
    moved = build([str(tmp_path / "pool-two" / f"{SID}.jsonl")])
    assert atoms.ledger_identity(moved) == initial
    Path(journal2).write_text('{"type":"started","key":"changed"}\n', encoding="utf-8")
    assert atoms.ledger_identity(ledger) == initial  # The old in-memory ledger stays frozen.
    assert atoms.ledger_identity(build([root])) != initial


def test_repeated_root_is_deduplicated_but_wrong_discovery_is_rejected(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl", call("Read", {"file_path": "/proj/input.md"}))
    other = dump(tmp_path / f"{SID2}.jsonl")
    sources = cc_sources.discover([root, root])
    assert sources.roots == (root,)
    seq = [0]
    agents = atoms_collect.collect_cc_pool([root, root], seq, sources=sources)
    assert len(agents) == 1 and len(agents["__main__:11111111"].actions) == 1
    with pytest.raises(ValueError, match="do not match"):
        atoms_collect.collect_cc_pool([other], [0], sources=sources)


@pytest.mark.parametrize("location", ["root", "subagents", "directory", "file", "broken", "cycle"])
def test_links_are_explicitly_rejected_and_never_followed(tmp_path: Path, location: str) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    child = Path(dump(tmp_path / SID / "subagents/workflows/agent-child.jsonl"))
    outside = Path(dump(tmp_path / "outside/agent-other.jsonl"))
    try:
        if location == "root":
            link = tmp_path / f"{SID2}.jsonl"
            link.symlink_to(root)
            root = str(link)
        elif location == "subagents":
            root = dump(tmp_path / f"{SID2}.jsonl")
            link = tmp_path / SID2 / "subagents"
            link.parent.mkdir()
            link.symlink_to(child.parent, target_is_directory=True)
        elif location in ("directory", "cycle"):
            target = outside.parent if location == "directory" else child.parent
            (child.parent / "linked-directory").symlink_to(target, target_is_directory=True)
        else:
            target = outside if location == "file" else tmp_path / "missing.jsonl"
            (child.parent / "agent-link.jsonl").symlink_to(target)
    except OSError as error:
        pytest.skip(f"Host cannot create symbolic links: {error}")
    with pytest.raises(ValueError, match="link/reparse"):
        cc_sources.subagent_paths(root)


def test_windows_reparse_flag_is_rejected_even_without_symlink_mode() -> None:
    info = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
    with pytest.raises(ValueError, match="link/reparse"):
        cc_sources._check_entry("synthetic-junction", info)


def test_builder_fingerprint_covers_discovery_and_raw_source_semantics() -> None:
    # Source-only inspection, not changing installed runtime files in this test.
    import inspect
    source = inspect.getsource(atoms._builder_fingerprint)
    assert '"cc_sources.py"' in source and '"transcript_store.py"' in source
