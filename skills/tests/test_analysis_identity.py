import copy
import json

import pytest

from test_memory_bundle import make_lesson, memory_with, prepared
from memorylib.analysis import from_host, record_analysis
from memorylib.common import write_new
from memorylib.case_format import finalize, content, claims
from memorylib.registry import Memory, revision_of


def test_host_identity_is_optional_and_material_scoped(tmp_path, monkeypatch):
    monkeypatch.delenv("MIGLOOP_ANALYSIS_CONTEXT", raising=False)
    meta = {"materials": str(tmp_path / "pool")}
    assert from_host(meta) == {}
    context = {"schema": "migloop-analysis-runtime/1", "materials": meta["materials"],
               "analysis": {"models": ["analyst-model"], "platforms": ["claude-code"],
                            "root_session_ids": ["analysis-session"]}}
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(context), encoding="utf-8")
    monkeypatch.setenv("MIGLOOP_ANALYSIS_CONTEXT", str(path))
    assert from_host(meta) == context["analysis"]
    with pytest.raises(ValueError, match="another material pool"):
        from_host({"materials": str(tmp_path / "other")})


def test_annotation_preserves_authored_card_lessons_and_status(prepared):
    card = finalize(prepared["card"])
    card["metadata"]["analysis"] = {"platforms": ["claude-code"]}
    card["revision"] = revision_of(card)
    path = prepared["root"] / "lean.json"
    write_new(path, card)
    memory = Memory(prepared["root"] / "annotated-store")
    memory.init()
    memory.ingest([path])
    memory.apply({"base_revision": memory.current()["revision"],
                  "upsert": [make_lesson(card)], "topic_descriptions": {"ui": "UI", "ui/text": "Text"}})
    original = memory.current()
    records = {card["id"]: {"models": ["observed-analyst"], "root_session_ids": ["root-analysis"]}}
    result = record_analysis(memory, records, original["revision"])
    current = memory.current()
    updated = memory.case(card["id"])
    assert result["annotated"] == 1
    assert content(updated) == content(card) and claims(updated) == claims(card)
    assert updated["metadata"]["migration"] == card["metadata"]["migration"]
    lesson = current["lessons"]["lesson-text"]
    expected = copy.deepcopy(original["lessons"]["lesson-text"])
    for ref in expected["evidence"]:
        ref["revision"] = updated["revision"]
    assert lesson == expected  # Including unchanged version and publication status.
    again = record_analysis(memory, records, current["revision"])
    assert again["annotated"] == 0 and again["revision"] == current["revision"]
    with pytest.raises(ValueError, match="Conflicting"):
        record_analysis(memory, {card["id"]: {"models": ["other-model"]}}, current["revision"])
    assert memory.current() == current


def test_annotation_rejects_non_analysis_fields_without_changes(prepared):
    memory = memory_with(prepared)
    before = memory.current()
    with pytest.raises(ValueError, match="only"):
        record_analysis(memory, {prepared["card"]["id"]: {"models": ["x"], "summary": "changed"}}, before["revision"])
    assert memory.current() == before


def test_pack_adds_observed_host_model_without_changing_frozen_provenance(prepared, monkeypatch):
    from memorylib.cases import pack
    root = prepared["root"]
    job_path = prepared["job"]
    from memorylib.common import load
    job = load(job_path)
    provenance_path = job_path.parent / job["provenance_path"]
    original = provenance_path.read_bytes()
    metadata = load(provenance_path)
    context = {"schema": "migloop-analysis-runtime/1", "materials": metadata["materials"],
               "analysis": {"models": ["actual-host-model"], "platforms": ["claude-code"],
                            "root_session_ids": ["actual-analysis-session"]}}
    runtime = root / "analysis-runtime.json"
    runtime.write_text(json.dumps(context), encoding="utf-8")
    monkeypatch.setenv("MIGLOOP_ANALYSIS_CONTEXT", str(runtime))
    output = root / "case-with-analysis.json"
    assert pack(job_path, root / "draft.json", output)["status"] == "valid"
    card = load(output)
    assert card["metadata"]["analysis"] == context["analysis"]
    assert "actual-host-model" not in card["metadata"]["observed_in_materials"]["models"]
    assert provenance_path.read_bytes() == original
