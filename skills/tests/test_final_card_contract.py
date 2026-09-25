"""Only a template-valid, checked attribution becomes a memory source."""
import copy
import json

import pytest

from test_memory_bundle import prepared, memory_with, make_lesson
from memorylib.cases import pack
from memorylib.card_contract import require_valid_card
from memorylib.common import load, write_new
from memorylib.registry import Memory, revision_of


@pytest.mark.parametrize("field", ["title", "when", "description", "summary", "recommendations", "graphs"])
def test_template_required_fields_fail_without_publishing(prepared, field):
    draft = copy.deepcopy(prepared["draft"])
    del draft[field]
    path, out = prepared["root"] / "missing-field.yaml", prepared["root"] / "invalid.json"
    write_new(path, draft)
    with pytest.raises(ValueError, match=field):
        pack(prepared["job"], path, out)
    assert not out.exists() and not out.with_suffix(".views").exists()


@pytest.mark.parametrize("field", ["recommendations", "graphs"])
def test_empty_required_lists_do_not_become_cards(prepared, field):
    draft = copy.deepcopy(prepared["draft"])
    draft[field] = []
    path, out = prepared["root"] / "empty.json", prepared["root"] / "empty-card.json"
    write_new(path, draft)
    with pytest.raises(ValueError):
        pack(prepared["job"], path, out)
    assert not out.exists()


def test_context_only_tree_is_not_an_attribution_card(prepared):
    from migloop.inquiry.card import delivery_status

    assert delivery_status({"mechanical_status": "valid", "tree": {
        "paths": [], "context_paths": [{"status": "native"}]}})["status"] == "draft"
    draft = copy.deepcopy(prepared["draft"])
    draft["graphs"][0]["nodes"][0].pop("problem")
    path, out = prepared["root"] / "context.json", prepared["root"] / "context-card.json"
    write_new(path, draft)
    with pytest.raises(ValueError, match="problem: true"):
        pack(prepared["job"], path, out)
    assert not out.exists()


def test_free_prose_does_not_create_spelling_dependent_checks(prepared):
    draft = copy.deepcopy(prepared["draft"])
    draft["summary"] = "Free prose mentions e-deadbeef and transcript.jsonl:L999; not structured edge evidence."
    graph = draft["graphs"][0]
    graph["nodes"][0]["reason"] = "同义改写、伪代码 `x = y`、e-deadbeef；这些文字不是结构化关系坐标。"
    path, out = prepared["root"] / "prose.json", prepared["root"] / "prose-card.json"
    write_new(path, draft)
    result = pack(prepared["job"], path, out)
    assert result["status"] == "valid"
    assert load(out)["draft"] == draft
    # The synthetic history has no repair call. Its original write is enough.
    assert len(load(out)["graph_evidence"][0]["edges"]) == 1


@pytest.mark.parametrize("failure", ["not_run", "needs_revision", "needs_path", "changed_graph", "missing_graph_check"])
def test_failed_or_stale_card_cannot_enter_memory(prepared, failure):
    card = copy.deepcopy(prepared["card"])
    validation = card["validation"]
    if failure == "not_run":
        validation.update(graph_check="not_run", mode="draft_only")
    elif failure == "needs_revision":
        validation["graph_checks"][0]["receipt"]["mechanical_status"] = "needs_revision"
    elif failure == "needs_path":
        validation["graph_checks"][0]["receipt"]["path_status"] = "needs_path"
    elif failure == "changed_graph":
        card["draft"]["graphs"][0]["nodes"][0]["at"] = "2026-01-01T00:00:01Z"
    else:
        validation["graph_checks"] = []
    card["revision"] = revision_of(card)
    path = prepared["root"] / "invalid-source.json"
    write_new(path, card)
    memory = Memory(prepared["root"] / "empty-store")
    memory.init()
    before = memory.current()
    with pytest.raises(ValueError):
        memory.ingest([path])
    assert memory.current() == before and not (memory.root / "cases").exists()


def test_old_failed_source_remains_readable_but_cannot_support_new_lesson(prepared):
    memory = memory_with(prepared)
    state = memory.current()
    card = memory.case(prepared["card"]["id"])
    # Simulate an old store, not an import escape hatch in the implementation.
    card["validation"]["graph_checks"][0]["receipt"]["path_status"] = "needs_path"
    path = memory.root / "cases" / card["id"] / (card["revision"] + ".json")
    path.write_text(json.dumps(card), encoding="utf-8")
    assert memory.case(card["id"])["draft"] == card["draft"]
    with pytest.raises(ValueError, match="Graph 1"):
        memory.apply({"base_revision": state["revision"], "upsert": [make_lesson(card)]})
    assert memory.current() == state


def test_valid_final_card_flows_directly_to_published_lesson(prepared):
    require_valid_card(prepared["card"])
    lesson = make_lesson(prepared["card"])
    lesson.pop("status")
    memory = memory_with(prepared, [lesson])
    assert memory.current()["lessons"]["lesson-text"]["status"] == "active"
    assert memory.case(prepared["card"]["id"])["validation"]["status"] == "valid"
