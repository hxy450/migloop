"""Known endpoint text is not proof of an opaque operation or of business correctness."""
from __future__ import annotations

from migloop import atoms, atoms_text
from migloop.filestory import FileStory, Version


def _ledger(after: str | None, *, sealed: bool = False, source: str = "opaque") -> atoms.Ledger:
    path = "/proj/A.ets"
    before = Version(1, "2026-01-01T00:00:00Z", 1, "agent-a", "full", "a\nb\n", None, "creation")
    current = Version(2, "2026-01-01T00:01:00Z", 2, "agent-b", source, after, None,
                      "interval" if sealed else "true", sealed=sealed)
    return atoms.Ledger(stories={path: FileStory(path, versions=[before, current])}, agents={})


def test_truly_unknown_content_has_unknown_counts_and_no_certain_zero_text() -> None:
    ledger = _ledger(None)
    payload = atoms.blame(ledger, "A.ets", 2, changed=True)
    assert payload is not None and payload["known"] is False
    assert payload["comparison_basis"] == "unavailable"
    assert payload["added"] is None and payload["removed"] is None and payload["n_lines"] is None
    text = atoms_text.render_blame(ledger, "A.ets", 2, changed=True)
    assert "内容未知" in text and "新增 0 行" not in text


def test_sealed_equal_snapshot_keeps_comparison_fact_and_limits_operation_claims() -> None:
    ledger = _ledger("a\nb\n", sealed=True)
    version = atoms.file_atom(ledger, "A.ets", 2)["versions"][-1]
    assert version["content_known"] is True and version["sealed"] is True and version["diff"] is None
    payload = atoms.blame(ledger, "A.ets", 2, changed=True)
    assert payload is not None and payload["known"] is True
    assert payload["added"] == 0 and payload["removed"] == 0
    assert payload["comparison_basis"] == "observed_endpoints"
    text = atoms_text.render_blame(ledger, "A.ets", 2, changed=True)
    assert "可观测端点" in text and "后续观测封口" in text
    assert "不证明黑盒调用没有改写" in text and "期间经过仍未知" in text
    diff = atoms_text.render_diff(ledger, "A.ets", 2)
    assert "可观测端点文本相同" in diff and "未被全文读到" not in diff
    assert "不证明黑盒调用没有改写" in diff


def test_pure_insertion_counts_do_not_certify_no_business_regression() -> None:
    ledger = _ledger("a\nb\nnew behavior\n", source="full")
    payload = atoms.blame(ledger, "A.ets", 2, changed=True)
    assert payload is not None and payload["known"] is True
    assert payload["added"] == 1 and payload["removed"] == 0
    assert payload["comparison_basis"] == "adjacent_version_text"
    text = atoms_text.render_blame(ledger, "A.ets", 2, changed=True)
    assert "不证明业务行为无回归" in text
    assert "要问 v1 的写者当时为什么没写" not in text


def test_known_unchanged_direct_write_is_not_reported_as_missing_observation() -> None:
    ledger = _ledger("a\nb\n", source="full")
    payload = atoms.blame(ledger, "A.ets", 2, changed=True)
    assert payload is not None and payload["comparison_basis"] == "adjacent_version_text"
    diff = atoms_text.render_diff(ledger, "A.ets", 2)
    assert "可观测端点文本相同" in diff and "覆盖前未被观测" not in diff


def test_known_current_snapshot_does_not_hide_unknown_baseline() -> None:
    ledger = _ledger("a\nb\n", sealed=True)
    ledger.stories["/proj/A.ets"].versions[0].content = None
    diff = atoms_text.render_diff(ledger, "A.ets", 2)
    assert "本版内容可见" in diff and "前一版或本版内容未知" in diff
    assert "端点文本相同" not in diff and "未被全文读到" not in diff
