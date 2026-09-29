"""Final cards are portable by themselves; evidence remains on actual edges."""
import copy
import json

import pytest

from test_memory_bundle import prepared, make_lesson
from test_case3_format import shared_fixture
from memorylib.case_format import content, claims, finalize, shared_objects
from memorylib.common import write_new
from memorylib.lean_card import metadata_of
from memorylib.publication import export_memory
from memorylib.registry import Memory, validate_case, revision_of


def test_copy_only_card_then_ingest_apply_export(prepared):
    root = prepared["root"] / "portable"
    path = root / "card.json"
    write_new(path, prepared["card"])
    memory = Memory(root / "store")
    memory.init(); memory.ingest([path])
    memory.apply({"base_revision": memory.current()["revision"], "upsert": [make_lesson(prepared["card"])],
                  "topic_descriptions": {"ui": "UI", "ui/text": "Text"}})
    export_memory(memory, root / "memory")
    assert not list(root.rglob("sessions"))
    assert shared_objects(prepared["card"], root / "missing") == {}


def test_whole_pool_metadata_is_not_formal_content():
    value = metadata_of({"provenance": {"materials": "unneeded-local-path", "collector": {"large": "details"},
            "observed": {"session_ids": [str(i) for i in range(304)], "models": ["observed-model"]},
            "migration": {"server_session_id": "migration", "project": "app"}},
            "environment": {"facts": [{"name": "harmonyos.target_sdk", "value": "24"}], "unknown": ["unobserved"]}})
    assert value["migration"]["server_session_id"] == "migration"
    assert value["observed_in_materials"]["models"] == ["observed-model"]
    assert value["environment"][0]["value"] == "24"
    assert not {"materials", "collector", "session_ids", "unknown"}.intersection(value)
    assert "session_ids" not in value["observed_in_materials"]


def test_entire_draft_is_the_stored_analysis(prepared):
    card = prepared["card"]
    assert content(card) == prepared["draft"]
    assert card["graphs"] == prepared["draft"]["graphs"]
    assert not {"changes", "participants", "check", "references", "context"}.intersection(card)
    assert all("operations" not in edge for graph in card["graphs"] for edge in graph["edges"])


def test_case3_conversion_keeps_content_but_no_sidecars(prepared):
    old, objects = shared_fixture(prepared)
    new = finalize(old, objects)
    assert content(new) == content(old) and claims(new) == claims(old)
    assert not {"check", "context", "references", "packager"}.intersection(new)
    assert new["graphs"] == prepared["draft"]["graphs"]


@pytest.mark.parametrize("field", ["check", "references", "validation", "context"])
def test_runtime_wrappers_cannot_be_reintroduced(prepared, field):
    card = copy.deepcopy(prepared["card"])
    card[field] = {}
    card["revision"] = revision_of(card)
    with pytest.raises(ValueError, match="receipts"):
        validate_case(card)
