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
from memorylib.common import load
from memorylib.publication import export_memory


def _links(path):
    return [(path.parent / unquote(target)).resolve()
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8"))]


def test_indexes_disclose_only_direct_children_and_preview(prepared):
    memory = memory_with(prepared, [make_lesson(prepared["card"], description="分段内容输入")])
    original = memory.current()
    output = prepared["root"] / "reading"
    result = export_memory(memory, output)
    lesson = output / "ui/text/lesson-text.lesson.md"
    assert _links(output / "index.md") == [output / "ui/index.md"]
    assert _links(output / "ui/index.md") == [output / "index.md", output / "ui/text/index.md"]
    assert _links(output / "ui/text/index.md") == [output / "ui/index.md", lesson]
    root_text = (output / "index.md").read_text(encoding="utf-8")
    index_text = (output / "ui/text/index.md").read_text(encoding="utf-8")
    assert "富文本" not in root_text
    assert "分段内容输入" in index_text and "全串相同样式" in index_text
    assert "Avoid losing segment style" not in index_text
    body = lesson.read_text(encoding="utf-8")
    for value in ("Avoid losing segment style", "保留数字和后缀的独立字号", "Compare each segment", "全串相同样式"):
        assert value in body
    assert result["lessons"] == 1 and result["topics"] == 2
    assert memory.current() == original and result["store_changed"] is False
    manifest = load(output / "manifest.json")
    for relative, digest in manifest["files"].items():
        assert hashlib.sha256((output / relative).read_bytes()).hexdigest() == digest
    assert manifest["lessons"]["lesson-text"]["evidence"] == original["lessons"]["lesson-text"]["evidence"]


def test_direct_lessons_and_subtopics_can_coexist(prepared):
    memory = memory_with(prepared, [make_lesson(prepared["card"]),
                                    make_lesson(prepared["card"], "lesson-ui", topic=["ui"])])
    output = prepared["root"] / "reading"
    export_memory(memory, output)
    links = _links(output / "ui/index.md")
    assert output / "ui/text/index.md" in links
    assert output / "ui/lesson-ui.lesson.md" in links
    assert output / "ui/text/lesson-text.lesson.md" not in links


def test_local_card_links_resolve_to_exact_revision_and_no_cards_are_copied(prepared):
    memory = memory_with(prepared)
    output = prepared["root"] / "阅读 包" / "v1"
    result = export_memory(memory, output, link_cards=True)
    source = memory.root / "cases" / prepared["card"]["id"] / (prepared["card"]["revision"] + ".json")
    assert source in _links(output / "ui/text/lesson-text.lesson.md")
    for path in output.rglob("*.md"):
        assert all(target.is_file() for target in _links(path))
    assert list(output.rglob("*.json")) == [output / "manifest.json"]
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
    assert prepared["card"]["revision"] in (copied / "ui/text/lesson-text.lesson.md").read_text(encoding="utf-8")
    assert load(copied / "manifest.json")["card_links"] == "references_only"


def test_requires_links_cross_topics_and_stable_identity_after_move(prepared):
    card = prepared["card"]
    memory = memory_with(prepared, [make_lesson(card),
                                    make_lesson(card, "lesson-ui", topic=["ui"], requires=["lesson-text"])])
    first = prepared["root"] / "v1"
    export_memory(memory, first)
    assert first / "ui/text/lesson-text.lesson.md" in _links(first / "ui/lesson-ui.lesson.md")
    proposal = {"base_revision": memory.current()["revision"], "upsert": [
        make_lesson(card, topic=["ui", "layout"], title="Changed title"),
        make_lesson(card, "lesson-ui", topic=["ui"], requires=["lesson-text"])],
        "topic_descriptions": {"ui/layout": "尺寸与位置"}}
    memory.apply(proposal)
    second = prepared["root"] / "v2"
    export_memory(memory, second)
    manifest = load(second / "manifest.json")
    assert manifest["lessons"]["lesson-text"]["path"] == "ui/layout/lesson-text.lesson.md"
    assert not (second / "ui/text").exists()
    assert first.joinpath("ui/text/lesson-text.lesson.md").is_file()


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
    assert first.joinpath("ui/text/lesson-text.lesson.md").is_file()


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
    card["draft"]["summary"] = "modified without revision"
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
    assert long_text in (output / "ui/text/lesson-text.lesson.md").read_text(encoding="utf-8")
    assert "description" not in memory.current()["lessons"]["lesson-text"]


def test_export_cli_works_outside_repository(prepared):
    memory = memory_with(prepared)
    output = prepared["root"] / "cli-reading"
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "memory.py"),
                             "export", "--store", str(memory.root), "--out", str(output)],
                            cwd=prepared["root"], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert Path(json.loads(result.stdout)["entry"]) == output / "index.md"
