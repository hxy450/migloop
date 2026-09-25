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


def test_stored_receipt_mutation_cannot_support_new_lesson(prepared):
    memory = memory_with(prepared)
    state = memory.current()
    card = memory.case(prepared["card"]["id"])
    # A stored outcome cannot be edited independently of the hashed summary.
    card["validation"]["graph_checks"][0]["receipt"]["path_status"] = "needs_path"
    path = memory.root / "cases" / card["id"] / (card["revision"] + ".json")
    path.write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(ValueError, match="validation summary"):
        memory.case(card["id"])
    with pytest.raises(ValueError, match="validation summary"):
        memory.apply({"base_revision": state["revision"], "upsert": [make_lesson(card)]})
    assert memory.current() == state


def test_valid_final_card_flows_directly_to_published_lesson(prepared):
    require_valid_card(prepared["card"])
    lesson = make_lesson(prepared["card"])
    lesson.pop("status")
    memory = memory_with(prepared, [lesson])
    assert memory.current()["lessons"]["lesson-text"]["status"] == "active"
    assert memory.case(prepared["card"]["id"])["validation"]["status"] == "valid"


@pytest.mark.parametrize("field,value", [("graph", 2), ("draft_sha256", "f" * 64),
                                       ("mechanical_status", "needs_revision"), ("path_status", "needs_path")])
def test_editing_bound_receipt_fields_is_rejected_before_ingest(prepared, field, value):
    from memorylib.registry import validate_case

    card = copy.deepcopy(prepared["card"])
    check = card["validation"]["graph_checks"][0]
    (check if field in ("graph", "draft_sha256") else check["receipt"])[field] = value
    # The unchanged top-level binding keeps the old revision, but cannot match
    # the edited receipt. Both validation and admission must reject it.
    assert revision_of(card) == prepared["card"]["revision"]
    with pytest.raises(ValueError, match="validation summary"):
        validate_case(card)
    path = prepared["root"] / "edited-receipt.json"
    write_new(path, card)
    memory = Memory(prepared["root"] / "receipt-store")
    memory.init()
    before = memory.current()
    with pytest.raises(ValueError, match="validation summary"):
        memory.ingest([path])
    assert memory.current() == before


def test_failed_to_complete_edit_reproduces_and_closes_the_reported_bypass(prepared):
    from memorylib.card_contract import validation_digest
    from memorylib.registry import validate_case

    card = copy.deepcopy(prepared["card"])
    receipt = card["validation"]["graph_checks"][0]["receipt"]
    receipt["path_status"] = "needs_path"
    card["validation_sha256"] = validation_digest(card["validation"])
    card["revision"] = revision_of(card)
    validate_case(card)
    receipt["path_status"] = "complete"
    path = prepared["root"] / "forged-completion.json"
    write_new(path, card)
    memory = Memory(prepared["root"] / "no-bypass")
    memory.init()
    with pytest.raises(ValueError, match="validation summary"):
        memory.ingest([path])
    # Updating the binding alone also breaks the card's existing revision.
    card["validation_sha256"] = validation_digest(card["validation"])
    with pytest.raises(ValueError, match="revision hash"):
        validate_case(card)


def test_legacy_card_read_compatible_but_receipt_edit_cannot_grant_admission(prepared):
    from memorylib.registry import validate_case

    card = copy.deepcopy(prepared["card"])
    card.pop("validation_sha256")
    card["validation"]["graph_checks"][0]["receipt"]["path_status"] = "needs_path"
    card["revision"] = revision_of(card)
    validate_case(card)  # Old hash stays readable; no silent migration.
    card["validation"]["graph_checks"][0]["receipt"]["path_status"] = "complete"
    validate_case(card)
    with pytest.raises(ValueError, match="revision-bound validation summary"):
        require_valid_card(card)


def test_repack_run_metadata_does_not_change_revision(prepared):
    from memorylib.registry import validate_case

    card = copy.deepcopy(prepared["card"])
    card["validation"]["graph_checks"][0]["receipt"]["report_id"] = "another-run"
    card["validation"]["kernel_sha256"] = "another-kernel-fingerprint"
    validate_case(card)
    assert revision_of(card) == prepared["card"]["revision"]
    packed = pack(prepared["job"], prepared["root"] / "draft.json", prepared["root"] / "repacked.json")
    assert packed["revision"] == prepared["card"]["revision"]
