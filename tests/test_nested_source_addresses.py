"""Portable source addresses do not confer actor ownership or a known time."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from migloop import atoms, transcript_store as store


def source(base, workflow="wf-one", text="fact", name="journal.jsonl"):
    path = base / "session-1234/subagents/workflows" / workflow / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "result", "result": text}) + "\n", encoding="utf-8")
    return path


def registry(*paths):
    # Fixture-declared namespace, not production path inference. Real contracts
    # come from the explicitly selected root JSONL in cc_sources.discover.
    metadata = {}
    for path in paths:
        anchors = [i for i, part in enumerate(path.parts) if part in ("session-1234", "root-a", "root-b")]
        if anchors:
            i = anchors[-1]
            name = path.parts[i] + ".jsonl/" + "/".join(path.parts[i + 1:])
            metadata[os.path.normcase(str(path))] = {"logical_name": name, "timestamp_policy": "unknown"}
    return SimpleNamespace(agents={}, auxiliary_sources=[str(p) for p in paths], source_metadata=metadata)


def declared_record(path):
    ledger = registry(path)
    return store.read_record(str(path), 1, source=store.source_spec(ledger, str(path)))


def legacy_ref(path):
    row = store.read_record(str(path), 1)
    key = hashlib.sha256(path.name.encode()).hexdigest()[:20]
    content = hashlib.sha256(row.raw.encode()).hexdigest()[:20]
    return f"raw:{key}:L1:{content}"


def test_nested_same_basename_sources_have_distinct_portable_addresses(tmp_path):
    left = source(tmp_path, "wf-one")
    right = source(tmp_path, "wf-two")
    copied = source(tmp_path / "frozen", "wf-one")
    a, b, c = [declared_record(p) for p in (left, right, copied)]
    assert a.ref != b.ref
    assert a.ref == c.ref
    assert len(a.ref.split(":")[1]) == 40
    assert store.resolve(registry(left, right), a.ref).path == os.path.normcase(str(left))
    assert store.resolve(registry(left, right), b.ref).path == os.path.normcase(str(right))


def test_auxiliary_registry_has_no_actor_even_when_payload_mentions_agent(tmp_path):
    path = source(tmp_path, text="agentId:agent-real")
    owned = source(tmp_path, name="agent-real.jsonl")
    agent = atoms.AgentRec("agent-real", "session", sources=[str(owned)])
    ledger = SimpleNamespace(agents={agent.id: agent}, auxiliary_sources=[str(path)])
    assert store.sources(ledger)[os.path.normcase(str(path))] == set()
    assert set(store.sources(ledger, agent.id)) == {os.path.normcase(str(owned))}
    row = store.resolve(ledger, store.read_record(str(path), 1).ref)
    assert row.ts is None  # Never borrow workflow/root timestamps.


def test_old_unique_basename_reference_round_trips_without_rewriting_it(tmp_path):
    path = source(tmp_path)
    old = legacy_ref(path)
    row = store.resolve(registry(path), old)
    assert row.ref == old
    assert row.address()["ref"] == old
    assert row.raw == store.read_record(str(path), 1).raw


def test_old_ambiguous_basename_reference_remains_ambiguous(tmp_path):
    a, b = source(tmp_path, "one"), source(tmp_path, "two")
    with pytest.raises(ValueError, match="ambiguous"):
        store.resolve(registry(a, b), legacy_ref(a))


def test_portable_duplicate_copy_in_one_registry_is_not_silently_coalesced(tmp_path):
    a, b = source(tmp_path / "one"), source(tmp_path / "two")
    with pytest.raises(ValueError, match="ambiguous"):
        store.resolve(registry(a, b), declared_record(a).ref)


@pytest.mark.parametrize("legacy", [False, True])
def test_both_address_versions_reject_changed_original_content(tmp_path, legacy):
    path = source(tmp_path)
    ref = legacy_ref(path) if legacy else declared_record(path).ref
    source(tmp_path, text="changed longer bytes")
    with pytest.raises(ValueError, match="content changed"):
        store.resolve(registry(path), ref)


def test_non_nested_source_keeps_old_address_and_strict_source_lengths(tmp_path):
    path = tmp_path / "root.jsonl"
    path.write_text('{"timestamp":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")
    ref = legacy_ref(path)
    assert store.read_record(str(path), 1).ref == ref
    assert store.resolve(registry(path), ref).ref == ref
    for length in (0, 19, 21, 39, 41):
        with pytest.raises(ValueError, match="invalid raw"):
            store.resolve(registry(path), "raw:" + "a" * length + ":L1:" + "b" * 20)


def test_nested_subagent_folder_does_not_drop_outer_root_identity(tmp_path):
    a = tmp_path / "root-a/subagents/agent-parent/subagents/journal.jsonl"
    b = tmp_path / "root-b/subagents/agent-parent/subagents/journal.jsonl"
    c = tmp_path / "copied/root-a/subagents/agent-parent/subagents/journal.jsonl"
    for path in (a, b, c):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"type":"result","result":"same bytes"}\n', encoding="utf-8")
    first, second, copied = [declared_record(p) for p in (a, b, c)]
    assert first.ref != second.ref
    assert first.ref == copied.ref
    assert store.resolve(registry(a, b), first.ref).path == os.path.normcase(str(a))


def test_host_folder_named_subagents_is_not_part_of_registered_identity(tmp_path):
    one = source(tmp_path / "subagents/worktree")
    two = source(tmp_path / "copied")
    assert declared_record(one).ref == declared_record(two).ref
    # An ordinary standalone source does not acquire a qualified key merely
    # because its host path contains a directory called subagents.
    assert len(store.read_record(str(one), 1).ref.split(":")[1]) == 20


@pytest.mark.parametrize("name", ["journal.jsonl", "workflow.json", "result.txt"])
def test_attachment_json_timestamp_never_becomes_arrival_evidence(tmp_path, name):
    path = source(tmp_path, name=name)
    path.write_text('{"timestamp":"2026-01-01T00:00:00Z","result":"later saved artifact"}\n', encoding="utf-8")
    ledger = registry(path)
    row = declared_record(path)
    assert row.ts is None
    assert store.resolve(ledger, row.ref).ts is None
    assert store.resolve(ledger, legacy_ref(path)).ts is None
