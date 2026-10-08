"""File disclosure and publication contracts; no model/migration accuracy claims."""
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

from test_memory_bundle import SCRIPTS, make_lesson, memory_with, prepared
from memorylib.case_format import claim_map
from memorylib.common import load
from memorylib.publication import export_memory, _support_counts, _support_line
from memorylib.registry import STAGES

LESSON = "topics/ui/text/lesson-text.lesson.md"


def _links(path):
    return [(path.parent / unquote(target)).resolve()
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8"))]


def _catalog(output):
    return [json.loads(line) for line in (output / "catalog.jsonl").read_text(encoding="utf-8").splitlines()]


def test_root_offers_domains_stages_and_structured_entries(prepared):
    memory = memory_with(prepared, [make_lesson(prepared["card"], description="分段内容输入")])
    original = memory.current()
    output = prepared["root"] / "reading"
    result = export_memory(memory, output)
    lesson = output / LESSON
    assert _links(output / "index.md") == [output / "topics/ui/index.md",
                                           *[output / f"by-stage/{s}.md" for s in STAGES]]
    assert _links(output / "topics/ui/index.md") == [output / "index.md", output / "topics/ui/text/index.md"]
    assert _links(output / "topics/ui/text/index.md") == [output / "topics/ui/index.md", lesson]
    root_text = (output / "index.md").read_text(encoding="utf-8")
    assert "catalog.jsonl" in root_text and "signals.json" in root_text and "（1 条）" in root_text
    assert "富文本" not in root_text and "分段内容输入" not in root_text
    index_text = (output / "topics/ui/text/index.md").read_text(encoding="utf-8")
    assert "富文本分段样式逐段保留" in index_text and "阶段：execute" in index_text and "StyledString" in index_text
    # The index line is the summary; conditions and bodies stay in the lesson file.
    assert "分段内容输入" not in index_text and "Avoid losing segment style" not in index_text
    body = lesson.read_text(encoding="utf-8")
    for value in ("Avoid losing segment style", "保留数字和后缀的独立字号", "Compare each segment", "全串相同样式",
                  "分段内容输入", "概要：富文本分段样式逐段保留", "`StyledString`"):
        assert value in body
    assert output / "topics/ui/text/index.md" in _links(lesson)
    assert result["lessons"] == 1 and result["topics"] == 2 and result["domains"] == 1
    assert memory.current() == original and result["store_changed"] is False
    manifest = load(output / "manifest.json")
    assert manifest["schema"] == "migloop-memory-files/2"
    for relative, digest in manifest["files"].items():
        assert hashlib.sha256((output / relative).read_bytes()).hexdigest() == digest
    assert set(manifest["files"]) >= {"index.md", "catalog.jsonl", "signals.json", LESSON, "topics/ui/text/index.md",
                                      *[f"by-stage/{s}.md" for s in STAGES]}
    entry = manifest["lessons"]["lesson-text"]
    assert entry["evidence"] == original["lessons"]["lesson-text"]["evidence"]
    assert entry["path"] == LESSON and entry["topic"] == "ui/text" and entry["stage"] == ["execute"]
    assert entry["summary"] == "富文本分段样式逐段保留" and entry["signals"][0] == "StyledString"


def test_catalog_signals_and_stage_views_are_derived_from_lesson_fields(prepared):
    card = prepared["card"]
    lessons = [make_lesson(card),
               make_lesson(card, "lesson-layout", topic=["ui", "layout"], stage=["spec", "repair"],
                           summary="布局边距按父尺寸推导", signals=["layoutWeight", "Span"])]
    memory = memory_with(prepared, lessons)
    memory.apply({"base_revision": memory.current()["revision"], "upsert": [],
                  "topic_descriptions": {"ui/layout": "尺寸与位置"}})
    output = prepared["root"] / "reading"
    result = export_memory(memory, output)
    rows = _catalog(output)
    assert [row["id"] for row in rows] == ["lesson-layout", "lesson-text"]  # topic order, then id
    layout = rows[0]
    assert layout == {"id": "lesson-layout", "summary": "布局边距按父尺寸推导", "topic": "ui/layout",
                      "stage": ["spec", "repair"], "signals": ["layoutWeight", "Span"], "title": "富文本 text segments",
                      "cards": 1, "apps": 0, "path": "topics/ui/layout/lesson-layout.lesson.md"}
    signals = load(output / "signals.json")
    assert signals["Span"] == ["lesson-layout", "lesson-text"] and signals["layoutWeight"] == ["lesson-layout"]
    spec = (output / "by-stage/spec.md").read_text(encoding="utf-8")
    implement = (output / "by-stage/execute.md").read_text(encoding="utf-8")
    verify = (output / "by-stage/verify.md").read_text(encoding="utf-8")
    assert "布局边距按父尺寸推导" in spec and "富文本分段样式逐段保留" not in spec
    assert "富文本分段样式逐段保留" in implement and "布局边距按父尺寸推导" not in implement
    assert "lesson" not in verify.split("返回根索引")[1]
    assert output / "topics/ui/layout/lesson-layout.lesson.md" in _links(output / "by-stage/spec.md")
    assert result["stages"] == {"spec": 1, "plan": 0, "execute": 1, "verify": 0, "repair": 1, "converge": 0}
    assert result["signals"] == 4


def test_related_lessons_come_from_shared_cards_not_authoring(prepared):
    card = prepared["card"]
    memory = memory_with(prepared, [make_lesson(card), make_lesson(card, "lesson-second", summary="第二条同源经验")])
    output = prepared["root"] / "reading"
    export_memory(memory, output)
    body = (output / LESSON).read_text(encoding="utf-8")
    assert "## 同源经验" in body and "第二条同源经验" in body and "共享 1 张卡" in body
    assert output / "topics/ui/text/lesson-second.lesson.md" in _links(output / LESSON)
    assert "related" not in memory.current()["lessons"]["lesson-text"]


@pytest.mark.parametrize("link_cards", [False, True])
def test_shared_guidance_is_at_root_without_dropping_lesson_data(prepared, link_cards):
    lessons = [make_lesson(prepared["card"], description="Known input condition"),
               make_lesson(prepared["card"], "lesson-second", check=[], requires=["lesson-text"])]
    memory = memory_with(prepared, lessons)
    original = memory.current()
    output = prepared["root"] / "reading"
    export_memory(memory, output, link_cards=link_cards)
    root = (output / "index.md").read_text(encoding="utf-8")
    guidance = root.split("## 阅读约定\n\n", 1)[1].strip().splitlines()
    guidance = [line for line in guidance if line.strip()]
    assert len(guidance) == 3
    assert ("unknown" in guidance[0]) == link_cards
    assert "可选检查" in guidance[1]
    assert "原有必需测试" in guidance[2]
    for path in output.rglob("*.md"):
        if path != output / "index.md":
            assert not any(line in path.read_text(encoding="utf-8") for line in guidance)
    for lesson in lessons:
        path = output / "topics/ui/text" / (lesson["id"] + ".lesson.md")
        body = path.read_text(encoding="utf-8")
        for value in [lesson["title"], lesson["when"], lesson["why"],
                      *lesson["unless"], *lesson["how"], *lesson["check"]]:
            assert value in body
        assert ("## 可选检查" in body) == bool(lesson["check"])
        for ref in lesson["evidence"]:
            assert all(ref[key] in body for key in ("case", "claim", "revision")) == link_cards
        assert all(target.is_file() for target in _links(path))
    assert lessons[0]["description"] in (output / LESSON).read_text(encoding="utf-8")
    assert output / LESSON in _links(output / "topics/ui/text/lesson-second.lesson.md")
    assert memory.current() == original


def test_local_card_links_resolve_to_exact_revision_and_no_cards_are_copied(prepared):
    memory = memory_with(prepared)
    output = prepared["root"] / "阅读 包" / "v1"
    result = export_memory(memory, output, link_cards=True)
    source = memory.root / "cases" / prepared["card"]["id"] / (prepared["card"]["revision"] + ".json")
    assert source in _links(output / LESSON)
    for path in output.rglob("*.md"):
        assert all(target.is_file() for target in _links(path))
    assert sorted(output.rglob("*.json")) == [output / "manifest.json", output / "signals.json"]
    assert result["card_links"] == "local"


def test_application_package_is_portable_without_store_or_card_content(prepared):
    memory = memory_with(prepared)
    output = prepared["root"] / "application"
    export_memory(memory, output)
    copied = prepared["root"] / "copied"
    shutil.copytree(output, copied)
    for path in copied.rglob("*.md"):
        assert all(target.is_file() and target.is_relative_to(copied) for target in _links(path))
        body = path.read_text(encoding="utf-8")
        assert "Test diagnosis" not in body and "recorded-generation-model" not in body
    body = (copied / LESSON).read_text(encoding="utf-8")
    assert prepared["card"]["revision"] not in body
    assert "## 来源" not in body
    assert load(copied / "manifest.json")["lessons"]["lesson-text"]["evidence"]
    assert load(copied / "manifest.json")["card_links"] == "references_only"


def test_support_deduplicates_claims_and_same_app_across_migrations():
    lesson = {"evidence": [
        {"case": "a", "revision": "r1", "claim": "diagnosis"},
        {"case": "a", "revision": "r1", "claim": "rec-0123456789"},
        {"case": "b", "revision": "r2", "claim": "diagnosis"},
        {"case": "c", "revision": "r3", "claim": "diagnosis"}]}
    counts = _support_counts(lesson, {
        ("a", "r1"): {"server_session_id": "run-1", "project": "DemoApp"},
        ("b", "r2"): {"server_session_id": "run-1", "project": " demoapp "},
        ("c", "r3"): {"server_session_id": "run-2", "project": "DemoApp"}})
    assert counts == {"cards": 3, "migrations": 2, "applications": 1,
                      "missing_migration_cards": 0, "missing_application_cards": 0}
    assert _support_line(counts) == "来源支持：3 张卡 · 2 次迁移 · 1 个应用"


def test_support_does_not_infer_migrations_from_agents_or_material_versions():
    lesson = {"evidence": [{"case": "a", "revision": "r", "claim": "diagnosis"},
                           {"case": "b", "revision": "r", "claim": "diagnosis"}]}
    records = {("a", "r"): {"id": "migration-1", "project": "A"},
               ("b", "r"): {"root_session_ids": ["root", "child"], "source_set_id": "pool"}}
    counts = _support_counts(lesson, records)
    assert counts == {"cards": 2, "migrations": 1, "applications": 1,
                      "missing_migration_cards": 1, "missing_application_cards": 1}
    assert "部分未记录" in _support_line(counts)
    records[("a", "r")] = {}
    assert _support_line(_support_counts(lesson, records)) == "来源支持：2 张卡 · 迁移数未记录 · 应用数未记录"


@pytest.mark.parametrize("link_cards", [False, True])
def test_support_line_is_derived_without_changing_knowledge_or_index(prepared, link_cards):
    card = prepared["card"]
    lesson = make_lesson(card)
    lesson["evidence"].append({**lesson["evidence"][0], "claim": claim_map(card)["recommendation:1"]})
    memory = memory_with(prepared, [lesson])
    before = memory.current()
    output = prepared["root"] / "support-reading"
    export_memory(memory, output, link_cards=link_cards)
    body = (output / LESSON).read_text(encoding="utf-8")
    assert body.count("来源支持：") == 1
    assert "来源支持：1 张卡 · 1 次迁移 · 应用数未记录" in body
    assert ("## 来源（按需复核）" in body) == link_cards
    assert "来源支持：" not in (output / "topics/ui/text/index.md").read_text(encoding="utf-8")
    assert "不是正确概率或成功复用次数" in (output / "index.md").read_text(encoding="utf-8")
    assert _catalog(output)[0]["cards"] == 1
    assert memory.current() == before


@pytest.mark.parametrize("entries, code", [(3, "sparse_topic"), (4, None), (9, None), (10, "crowded_topic")])
def test_leaf_size_hints_are_nonblocking_within_the_contract(prepared, entries, code):
    lessons = [make_lesson(prepared["card"], f"lesson-{i}") for i in range(entries)]
    memory = memory_with(prepared, lessons)
    before = memory.current()
    result = export_memory(memory, prepared["root"] / "reading")
    assert [w["code"] for w in result["warnings"]] == ([code] if code else [])
    if code:
        assert result["warnings"][0]["topic"] == "ui/text" and result["warnings"][0]["entries"] == entries
    assert memory.current() == before


def test_structure_contract_rejects_crowded_leaf_and_lessons_above_leaves(prepared):
    card = prepared["card"]
    base = memory_with(prepared)
    old = base.current()
    crowded = [make_lesson(card, f"lesson-{i}") for i in range(13)]
    with pytest.raises(ValueError, match="14 lessons exceed 12"):  # 13 new plus the existing lesson-text
        base.apply({"base_revision": old["revision"], "upsert": crowded})
    with pytest.raises(ValueError, match="holds lessons and subtopics"):
        base.apply({"base_revision": old["revision"], "upsert": [make_lesson(card, "lesson-child", topic=["ui", "text", "child"])],
                    "topic_descriptions": {"ui/text/child": "子机制"}})
    with pytest.raises(ValueError, match="2–3 path segments"):
        base.apply({"base_revision": old["revision"], "upsert": [make_lesson(card, "lesson-domain", topic=["ui"])]})
    with pytest.raises(ValueError, match="exceeds 60 characters"):
        base.apply({"base_revision": old["revision"], "upsert": [], "topic_descriptions": {"ui/text": "长" * 61}})
    assert base.current() == old
    # Retired lessons no longer count against the leaf; the contract is about what readers see.
    base.apply({"base_revision": old["revision"], "upsert": crowded[:11]})
    base.apply({"base_revision": base.current()["revision"], "retire": [{"id": "lesson-text", "reason": "fixture"}],
                "upsert": [make_lesson(card, "lesson-12")]})
    assert export_memory(base, prepared["root"] / "reading")["lessons"] == 12


@pytest.mark.parametrize("field, value, message", [
    ("stage", [], "lesson.stage"), ("stage", ["build"], "lesson.stage"), ("stage", ["spec", "spec"], "lesson.stage"),
    ("summary", "x" * 31, "lesson.summary"), ("summary", " ", "lesson.summary"),
    ("signals", [], "lesson.signals"), ("signals", ["a", "a"], "lesson.signals"), ("signals", [" bindSheet"], "lesson.signals"),
    ("signals", ["bindSheet", "import"], "plain words"), ("signals", ["title"], "plain words")])
def test_retrieval_fields_are_validated_before_publishing(prepared, field, value, message):
    memory = memory_with(prepared)
    original = memory.current()
    with pytest.raises(ValueError, match=message):
        memory.apply({"base_revision": original["revision"], "upsert": [make_lesson(prepared["card"], **{field: value})]})
    assert memory.current() == original


def test_lessons_without_retrieval_fields_cannot_be_exported(prepared, monkeypatch):
    memory = memory_with(prepared)
    state = memory.current()
    for key in ("stage", "summary", "signals"):
        state["lessons"]["lesson-text"].pop(key)
    monkeypatch.setattr(memory, "current", lambda: state)
    with pytest.raises(ValueError, match="retrieval fields"):
        export_memory(memory, prepared["root"] / "reading")


def test_requires_links_cross_topics_and_identity_survives_move(prepared):
    card = prepared["card"]
    memory = memory_with(prepared, [make_lesson(card),
                                    make_lesson(card, "lesson-ui", topic=["ui", "layout"], requires=["lesson-text"])])
    memory.apply({"base_revision": memory.current()["revision"], "upsert": [], "topic_descriptions": {"ui/layout": "尺寸与位置"}})
    first = prepared["root"] / "v1"
    export_memory(memory, first)
    assert first / LESSON in _links(first / "topics/ui/layout/lesson-ui.lesson.md")
    proposal = {"base_revision": memory.current()["revision"], "upsert": [
        make_lesson(card, topic=["ui", "layout"], title="Changed title"),
        make_lesson(card, "lesson-ui", topic=["ui", "layout"], requires=["lesson-text"])]}
    memory.apply(proposal)
    second = prepared["root"] / "v2"
    export_memory(memory, second)
    manifest = load(second / "manifest.json")
    # The file follows its topic folder; the ID, evidence and catalog row stay the same identity.
    assert manifest["lessons"]["lesson-text"]["path"] == "topics/ui/layout/lesson-text.lesson.md"
    assert manifest["lessons"]["lesson-text"]["topic"] == "ui/layout"
    assert manifest["lessons"]["lesson-text"]["evidence"] == load(first / "manifest.json")["lessons"]["lesson-text"]["evidence"]
    assert not (second / "topics/ui/text").exists() and (second / "topics/ui/layout/index.md").is_file()
    assert (second / "topics/ui/layout/lesson-ui.lesson.md").is_file()
    assert first.joinpath(LESSON).is_file()


def test_migrate_rebinds_positional_claims_to_stable_ids(prepared):
    card = prepared["card"]
    memory = memory_with(prepared)
    stable = claim_map(card)["recommendation:1"]
    assert stable.startswith("rec-") and memory.current()["cases"][card["id"]]["claims"] == ["diagnosis", stable]
    # A pre-migration snapshot: positional names everywhere.
    state = memory.current()
    state["schema"] = "migloop-memory/1"
    state["cases"][card["id"]]["claims"] = ["diagnosis", "recommendation:1"]
    state["lessons"]["lesson-text"]["evidence"].append({"case": card["id"], "claim": "recommendation:1", "revision": card["revision"]})
    with memory.lock():
        memory._publish(state, ["fixture: positional claims"])
    result = memory.migrate(memory.current()["revision"])
    assert result["changes"] == [{"migrated": "migloop-memory/2", "cases_with_stable_claims": 1, "claim_bindings_rebound": 1}]
    current = memory.current()
    assert current["schema"] == "migloop-memory/2"
    assert current["cases"][card["id"]]["claims"] == ["diagnosis", stable]
    assert [ref["claim"] for ref in current["lessons"]["lesson-text"]["evidence"]] == ["diagnosis", stable]
    assert memory.case(card["id"])["revision"] == card["revision"]  # cards are untouched
    assert export_memory(memory, prepared["root"] / "reading")["lessons"] == 1
    again = memory.migrate(memory.current()["revision"])
    assert again["changes"][0]["claim_bindings_rebound"] == 0


def test_withdrawal_suppresses_new_release_not_old_snapshot(prepared):
    card = prepared["card"]
    memory = memory_with(prepared, [make_lesson(card), make_lesson(card, "candidate-only", status="candidate"),
                                    make_lesson(card, "consumer", requires=["lesson-text"])])
    first = prepared["root"] / "v1"
    assert export_memory(memory, first)["lessons"] == 2
    assert not list(first.rglob("candidate-only.lesson.md"))
    memory.withdraw(card["id"], "test withdrawal", memory.current()["revision"], "diagnosis")
    second = prepared["root"] / "v2"
    assert export_memory(memory, second)["lessons"] == 0
    assert not list(second.rglob("*.lesson.md"))
    assert first.joinpath(LESSON).is_file()


def test_missing_topic_description_fails_without_guessing_or_publishing(prepared):
    memory = memory_with(prepared, [make_lesson(prepared["card"], topic=["ui", "new-topic"])])
    output = prepared["root"] / "reading"
    with pytest.raises(ValueError, match="Missing topic description: ui/new-topic"):
        export_memory(memory, output)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_existing_output_is_preserved(prepared, kind):
    memory = memory_with(prepared)
    output = prepared["root"] / "reading"
    if kind == "directory":
        output.mkdir()
        sentinel = output / "user.txt"
    else:
        sentinel = output
    sentinel.write_text("user content", encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        export_memory(memory, output)
    assert sentinel.read_text(encoding="utf-8") == "user content"


@pytest.mark.parametrize("where", ["store", "child", "parent"])
def test_export_cannot_overlap_store(prepared, where):
    memory = memory_with(prepared)
    output = {"store": memory.root, "child": memory.root / "reading", "parent": memory.root.parent}[where]
    previous = memory.current()
    with pytest.raises(ValueError, match="overlap"):
        export_memory(memory, output)
    assert memory.current() == previous


def test_failed_generation_never_publishes_partial_directory(prepared, monkeypatch):
    memory = memory_with(prepared)
    original = Path.write_text
    def fail_manifest(path, *args, **kwargs):
        if path.name == "manifest.json":
            raise OSError("simulated disk error")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", fail_manifest)
    output = prepared["root"] / "reading"
    with pytest.raises(OSError, match="disk error"):
        export_memory(memory, output)
    assert not output.exists()
    assert not list(output.parent.glob(".memory-export-*"))
    assert not (memory.root / ".publish.lock").exists()


def test_damaged_card_rejects_export_even_without_card_links(prepared):
    memory = memory_with(prepared)
    card = copy.deepcopy(prepared["card"])
    card["summary"] = "modified without revision"
    path = memory.root / "cases" / card["id"] / (card["revision"] + ".json")
    path.write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(ValueError, match="revision hash"):
        export_memory(memory, prepared["root"] / "reading")


@pytest.mark.parametrize("fault", ["withdrawn", "dependency"])
def test_inconsistent_active_record_cannot_be_published(prepared, monkeypatch, fault):
    memory = memory_with(prepared)
    state = memory.current()
    if fault == "withdrawn":
        state["cases"][prepared["card"]["id"]]["withdrawn_claims"] = ["diagnosis"]
    else:
        state["lessons"]["lesson-text"]["requires"] = ["unavailable"]
    monkeypatch.setattr(memory, "current", lambda: state)
    with pytest.raises(ValueError, match="withdrawn|unpublished dependency"):
        export_memory(memory, prepared["root"] / "reading")


def test_legacy_description_is_not_invented_and_long_body_is_complete(prepared):
    long_text = "完整正文" * 10000
    memory = memory_with(prepared, [make_lesson(prepared["card"], why=long_text)])
    output = prepared["root"] / "reading"
    export_memory(memory, output)
    assert long_text in (output / LESSON).read_text(encoding="utf-8")
    assert "description" not in memory.current()["lessons"]["lesson-text"]


def test_export_cli_works_outside_repository(prepared):
    memory = memory_with(prepared)
    output = prepared["root"] / "cli-reading"
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "memory.py"),
                             "export", "--store", str(memory.root), "--out", str(output)],
                            cwd=prepared["root"], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert Path(json.loads(result.stdout)["entry"]) == output / "index.md"
