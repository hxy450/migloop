"""Formal cards keep one lossless graph and bind every external dependency."""
import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_memory_bundle import prepared, memory_with
from test_card_storage import legacy_card
from memorylib.case_format import (content, claims, context, finalize, shared_objects,
                                   write_shared, _merge_graph)
from memorylib.card_contract import require_valid_card
from memorylib.common import fingerprint, load, write_new
from memorylib.registry import Memory, revision_of, validate_case
from memorylib.card_storage import compact_card, compact_store


def test_formal_pack_keeps_exact_authoring_but_no_copies(prepared):
    card = prepared["card"]
    assert card["schema"] == "migloop-case/3"
    assert not set(card) & {"draft", "claims", "graph_evidence", "validation", "environment", "provenance", "targets"}
    assert content(card) == prepared["draft"]
    assert claims(card)["diagnosis"]["text"] == card["summary"]
    metadata = context(card, shared_objects(card, prepared["root"] / "sessions"))
    assert metadata["scope"] == load(prepared["job"])["scope"]
    assert metadata["provenance"]["sources"]["agent.jsonl"]
    require_valid_card(card)
    assert finalize(card) == card


@pytest.mark.parametrize("part", ["prose", "check", "operation", "reference", "context"])
def test_formal_revision_binds_body_graph_receipt_and_dependencies(prepared, part):
    card = copy.deepcopy(prepared["card"])
    if part == "prose":
        card["summary"] += " altered"
    elif part == "check":
        card["check"]["path_status"] = "needs_path"
    elif part == "operation":
        card["graphs"][0]["edges"][0]["operations"][0]["at"] = "2026-01-01T00:00:01Z"
    elif part == "reference":
        card["references"][0] = "fake:999"
    else:
        card["context"]["scope"] = "f" * 64
    assert revision_of(card) != prepared["card"]["revision"]
    with pytest.raises(ValueError, match="revision hash"):
        validate_case(card)


def test_rehashed_graph_without_matching_check_fails(prepared):
    card = copy.deepcopy(prepared["card"])
    card["graphs"][0]["edges"][0]["operations"] = []
    card["revision"] = revision_of(card)
    with pytest.raises(ValueError, match="receipt"):
        require_valid_card(card)


@pytest.mark.parametrize("mutation", ["missing", "changed", "traversal"])
def test_context_cannot_be_missing_mutated_or_escape_directory(prepared, mutation):
    memory = Memory(prepared["root"] / "other-store")
    memory.init()
    card = copy.deepcopy(prepared["card"])
    directory = prepared["root"] / "sessions"
    path = directory / (card["context"]["scope"] + ".json")
    if mutation == "missing":
        path.unlink()
    elif mutation == "changed":
        path.write_text('{}', encoding="utf-8")
    else:
        card["context"]["scope"] = "../scope"
        card["revision"] = revision_of(card)
        prepared["card_path"].write_text(__import__('json').dumps(card), encoding="utf-8")
    before = memory.current()
    with pytest.raises(ValueError):
        memory.ingest([prepared["card_path"]])
    assert memory.current() == before


def test_multiple_operations_extra_versions_and_same_line_sources_survive():
    t = "2026-01-01T00:00:02Z"
    graph = {"target": {"key": "/app/Page.ets", "at": t},
             "nodes": [{"key": "agent-aa.jsonl", "at": t, "reason": "drift", "problem": True}],
             "edges": [{"from": 1, "to": "target", "force": True, "reason": "script writes twice",
                        "evidence": [{"source": "first.jsonl", "line": 3}, {"source": "second.jsonl", "line": 3}]}]}
    nodes = [{"id": "root", "kind": "file", "key": "/app/Page.ets", "at": t},
             {"id": "extra", "kind": "file", "key": "/app/Other.ets", "at": t},
             {"id": "agent", "kind": "agent", "key": "s:aa", "at": t}]
    operations = [{"from": "agent", "to": target, "relation": "write", "source": "model_review",
                   "strength": "candidate", "at": t, "evidence": [ref]}
                  for target, ref in [("root", "first:3:hash"), ("root", "second:3:hash"), ("extra", "third:3:hash")]]
    refs = []
    merged = _merge_graph(graph, {"nodes": nodes, "edges": operations}, refs, {})
    assert len(merged["nodes"]) == 2 and merged["nodes"][-1]["derived"]
    assert len(merged["edges"][0]["operations"]) == 2
    assert merged["edges"][-1]["derived"] and merged["edges"][0]["force"]
    assert {r["source"] for r in refs if isinstance(r, dict)} == {"first.jsonl", "second.jsonl"}
    shell = {"schema": "migloop-case/3", "references": refs, "graphs": [merged]}
    assert content(shell)["graphs"] == [graph]
    assert [refs[r] for e in merged["edges"] for op in e["operations"] for r in op["evidence"]] == ["first:3:hash", "second:3:hash", "third:3:hash"]


def test_shared_publish_is_atomic_with_parallel_writers(prepared):
    objects = shared_objects(prepared["card"], prepared["root"] / "sessions")
    out = prepared["root"] / "parallel-context"
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: write_shared(out, objects), range(24)))
    assert shared_objects(prepared["card"], out) == objects
    assert len(list(out.iterdir())) == len(objects)


def test_migration_preserves_claims_status_versions_and_history(prepared):
    old = legacy_card(prepared, complete=True)
    old_path = prepared["root"] / "legacy-card.json"
    write_new(old_path, old)
    prepared = {**prepared, "card": old, "card_path": old_path}
    memory = memory_with(prepared)
    before = memory.current()
    migrated_path = prepared["root"] / "new-store"
    compact_store(memory, migrated_path)
    migrated = Memory(migrated_path)
    assert len(list((migrated_path / "snapshots").glob('*.json'))) == len(list((memory.root / "snapshots").glob('*.json')))
    after = migrated.current()
    assert memory.current() == before
    assert content(migrated.case(old["id"])) == old["draft"]
    assert claims(migrated.case(old["id"])) == old["claims"]
    old_lesson, new_lesson = copy.deepcopy(before["lessons"]), copy.deepcopy(after["lessons"])
    for lessons in (old_lesson, new_lesson):
        for lesson in lessons.values():
            for ref in lesson["evidence"]:
                ref.pop("revision")
    assert old_lesson == new_lesson
    assert not {"observed", "migration", "analysis"} & after["cases"][old["id"]].keys()


def test_failed_legacy_cannot_be_promoted_by_format_conversion(prepared):
    old = legacy_card(prepared)
    with pytest.raises(ValueError, match="validation summary"):
        finalize(old)
