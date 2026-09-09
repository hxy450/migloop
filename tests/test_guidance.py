import asyncio

import pytest

from migloop import guidance, mcp_server, service


def test_short_entry_defers_schema_without_deleting_original_reference(monkeypatch):
    monkeypatch.setenv("MIGLOOP_VERDICT_VERSION", "1")
    core = guidance.guide_text("document")
    assert len(core) < len(guidance.GUIDE) * 0.25
    assert 'guide(topic="verdict")' in core
    assert "basis:" not in core
    assert guidance.guide_text("document", "full") == guidance.GUIDE
    topics = [guidance.guide_text("document", topic)
              for topic in guidance._TOPIC_HEADINGS]
    for block in guidance.GUIDE.split("\n## ")[1:]:
        assert sum(block.rstrip() in text for text in topics) == 1
    assert "basis:" in guidance.guide_text("document", "verdict")
    assert "schema: migloop-verdict-ref/1" in guidance.guide_text("reference", "verdict")


@pytest.mark.parametrize("topic", guidance.TOPICS)
@pytest.mark.parametrize("mode", ["document", "reference"])
def test_each_topic_matches_mcp_and_http_without_a_ledger(topic, mode, monkeypatch):
    monkeypatch.setenv("MIGLOOP_FINAL_MODE", mode)
    expected = guidance.guide_text(topic=topic)
    assert service.atom_text("unused", "guide", {"topic": topic}) == expected
    pytest.importorskip("mcp")
    blocks = asyncio.run(mcp_server.build_server().call_tool("guide", {"topic": topic}))
    assert len(blocks) == 1 and blocks[0].text == expected


@pytest.mark.parametrize("topic", ["typo", "", None, False, 1, [], {}])
def test_bad_topic_is_rejected_not_silently_full(topic):
    with pytest.raises(ValueError, match="guide topic"):
        guidance.guide_text("document", topic)
    with pytest.raises(ValueError, match="guide topic"):
        service.atom_text("unused", "guide", {"topic": topic})


def test_http_guide_rejects_ignored_parameters():
    with pytest.raises(ValueError, match="unsupported guide parameters"):
        service.atom_text("unused", "guide", {"topci": "verdict"})


def test_short_entry_keeps_nonnegotiable_evidence_and_time_boundaries():
    core = guidance.CORE
    for phrase in ("不能互换", "就近绑定/重叠/依赖读", "不创建历史读写边", "until_ts",
                   "不代替原生执行或设备复核", "不把历史快照作者当未知行作者",
                   "Write 正文或命令要 part=input", "not_repair 须有非修复依据"):
        assert phrase in core


def test_v2_is_explicit_and_preserves_v1_guide_as_a_legacy_mode(monkeypatch):
    monkeypatch.delenv("MIGLOOP_VERDICT_VERSION", raising=False)
    core = guidance.guide_text("document")
    assert "migloop-verdict/2" in core and "event_claims" in core
    assert "schema: migloop-verdict/2" in guidance.guide_text("document", "verdict")
    assert "schema: migloop-verdict/1" not in guidance.guide_text("document", "full")
    assert "schema: migloop-verdict-ref/1" in guidance.guide_text("reference", "verdict")
    monkeypatch.setenv("MIGLOOP_VERDICT_VERSION", "1")
    assert guidance.guide_text("document", "full") == guidance.GUIDE
