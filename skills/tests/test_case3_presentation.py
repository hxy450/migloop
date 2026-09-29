"""Serialization order is a reader contract, independent of semantic revision."""
import copy
import json

from test_memory_bundle import prepared
from memorylib.case_format import content, finalize, presentation
from memorylib.common import fingerprint
from memorylib.registry import revision_of, validate_case


def test_pack_puts_authored_content_before_technical_context(prepared):
    card = json.loads(prepared["card_path"].read_text(encoding="utf-8"))
    assert list(card) == [
        "schema", "id", "created_at", "migration_key",
        "title", "when", "description", "summary",
        "recommendations", "changes", "participants", "graphs", "unknown",
        "job", "identity_basis", "context", "references", "packager", "check", "revision",
    ]
    assert content(card) == prepared["draft"]


def test_existing_card_reordering_preserves_revision_and_nested_serialization(prepared):
    card = dict(reversed(list(prepared["card"].items())))
    nested = json.dumps(card["graphs"], ensure_ascii=False)
    value = finalize(card)
    assert list(value) != list(card)
    assert value == card
    assert revision_of(value) == card["revision"]
    assert fingerprint(value) == fingerprint(card)
    assert json.dumps(value["graphs"], ensure_ascii=False) == nested
    assert list(finalize(value)) == list(value)
    validate_case(value)


def test_optional_fields_and_extensions_are_not_lost_or_added(prepared):
    card = copy.deepcopy(prepared["card"])
    card["unresolved_targets"] = [{"key": "/app/Other.ets", "reason": "No attribution asserted"}]
    card["extension"] = {"z": [3, 1, 2], "a": "retained"}
    card.pop("unknown")
    before = copy.deepcopy(card)
    value = presentation(card)
    assert value == before and card == before
    assert "unknown" not in value
    assert list(value).index("graphs") < list(value).index("unresolved_targets") < list(value).index("context")
    assert json.dumps(value["extension"]) == json.dumps(before["extension"])
