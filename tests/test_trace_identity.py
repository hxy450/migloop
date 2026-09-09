"""Query provenance is independent of a model's YAML ledger claim."""
from __future__ import annotations

from typing import Any

import pytest

from migloop import atoms, via

CURRENT = "atoms-snapshot:current"
OLD = "atoms-snapshot:old"


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch) -> Any:
    sentinel = object()

    def identity(value: Any) -> str:
        assert value is sentinel
        return CURRENT

    monkeypatch.setattr(atoms, "ledger_identity", identity)
    return sentinel


def sessions(identity: str = CURRENT, **changes: Any) -> dict[str, Any]:
    return {"tool": "sessions", "has_result": True, "is_error": False,
            "text": f"账本身份: {identity}\n# 返修链(1)\n原始返回内容",
            "call_id": "call-1", "item_id": None, "result_line": 17,
            "provenance": {"format": "codex_rollout", "path": "transcript.jsonl", "pairing": "call_id"},
            **changes}


@pytest.mark.parametrize(("sources", "harness", "bound", "status", "source"), [
    ([CURRENT], None, True, "matched", "sessions"),
    ([CURRENT, CURRENT], CURRENT, True, "matched", "sessions+harness"),
    ([OLD], None, False, "mismatch", "sessions"),
    ([CURRENT, OLD], CURRENT, False, "mismatch", "sessions+harness"),
    ([OLD, CURRENT], None, False, "mismatch", "sessions"),
    ([OLD], CURRENT, False, "mismatch", "sessions+harness"),
    ([CURRENT], OLD, False, "mismatch", "sessions+harness"),
    ([], CURRENT, True, "matched", "harness"),
    ([], OLD, False, "mismatch", "harness"),
    ([], None, None, "legacy", None),
    ([], "", None, "legacy", None),
])
def test_independent_providers(ledger: Any, sources: list[str], harness: Any,
                               bound: bool | None, status: str, source: str | None) -> None:
    result = via.trace_identity(ledger, [sessions(identity) for identity in sources], {"harness_identity": harness})
    assert result["bound"] is bound and result["match"] is bound
    assert (result["status"], result["source"]) == (status, source)
    assert result["source_identities"] == list(dict.fromkeys(sources))
    assert result["current"] == CURRENT and result["harness_identity"] == harness


def test_wrong_model_claim_cannot_override_original_sessions(ledger: Any) -> None:
    metrics = {"ledger": OLD, "data": {"ledger": OLD}, "structured": {"identity": {"bound": False}},
               "harness_identity": CURRENT}
    result = via.trace_identity(ledger, [sessions()], metrics)
    assert result["bound"] is True
    assert result["observations"] == [{"identity": CURRENT, "step": 1, "call_id": "call-1", "item_id": None,
                                        "result_line": 17, "provenance": sessions()["provenance"]}]


def test_model_claim_and_summary_are_not_runtime_identity_sources(ledger: Any) -> None:
    result = via.trace_identity(ledger, None, {"ledger": CURRENT, "data": {"ledger": CURRENT},
                                             "transcript": {"seq": [sessions()]}})
    assert result["bound"] is None and result["status"] == "legacy"


@pytest.mark.parametrize("changes", [
    {"is_error": True}, {"ok": False}, {"has_result": False}, {"has_result": None},
    {"status": "rejected"}, {"parse_error": "invalid arguments"},
    {"provenance": {"format": "codex_exec_events", "complete_pair": False}},
    {"text": f"⛔ 被拒\n账本身份: {CURRENT}"},
])
def test_failed_pending_or_rejected_sessions_are_not_identity_sources(ledger: Any, changes: dict[str, Any]) -> None:
    result = via.trace_identity(ledger, [sessions(**changes)], {})
    assert result["bound"] is None and result["source_identities"] == []
    assert len(result["ignored_sessions"]) == 1
    # A refused old response also cannot invalidate independent, explicit harness provenance.
    assert via.trace_identity(ledger, [sessions(OLD, **changes)], {"harness_identity": CURRENT})["bound"] is True


@pytest.mark.parametrize("text", [
    f"引用: 账本身份: {CURRENT}",
    f"> 账本身份: {CURRENT}",
    f"    账本身份: {CURRENT}",
    f"`账本身份: {CURRENT}`",
    f"```text\n账本身份: {CURRENT}\n```",
    f"# 返修链\n账本身份: {CURRENT}",
    f'{{"text":"账本身份: {CURRENT}"}}',
    f"账本身份: {CURRENT} 后续解释",
    "账本身份:",
])
def test_only_complete_runtime_header_not_quoted_or_embedded_text(ledger: Any, text: str) -> None:
    result = via.trace_identity(ledger, [sessions(text=text)], {})
    assert result["bound"] is None and result["observations"] == []


def test_blank_lines_bom_and_windows_newlines_preserve_exact_header(ledger: Any) -> None:
    call = sessions(tool="mcp__migloop__sessions", text=f"\ufeff\r\n\r\n账本身份: {CURRENT}\r\n# 返修链(0)")
    assert via.trace_identity(ledger, [call], None)["bound"] is True


def test_other_tool_return_cannot_supply_sessions_identity(ledger: Any) -> None:
    assert via.trace_identity(ledger, [sessions(tool="action"), sessions(tool="mcp__other__sessions")], {})["bound"] is None


@pytest.mark.parametrize("value", [False, 0, [], {}, " ", "current identity", CURRENT + "\n"])
def test_explicit_malformed_harness_identity_is_not_silently_ignored(ledger: Any, value: Any) -> None:
    result = via.trace_identity(ledger, [sessions()], {"harness_identity": value})
    assert result["bound"] is False and result["status"] == "mismatch"
