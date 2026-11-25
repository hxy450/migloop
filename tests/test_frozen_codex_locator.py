"""The UUID serialized into a Codex page must resolve within its frozen root pool.

Locator half only; the page / API round-trip case moved with the repair chain to
fuxi-ailabs/a2h-memory fixchain/.
"""
from __future__ import annotations

import pytest

from migloop import service
from tests.cc_transcript import _write_jsonl
from tests.test_frozen_pool import fail_discovery

# Same rollout names as tests/test_transcript_tags.py (moved to a2h-memory with the ledger tests).
NAMES = ["rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl",
         "rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl"]

IDS = ["01a009fe-68e3-7f42-b76b-5e863c555976", "01a021e5-c150-7b12-a610-d40c07816b98"]


def roots(tmp_path, count=2):
    """Write the root rollouts only; no ledger is built here."""
    for name, sid in zip(NAMES[:count], IDS):
        records = [{"timestamp": "2026-08-16T17:54:23Z", "type": "session_meta", "payload": {"id": sid, "cwd": "/proj"}},
                   {"timestamp": "2026-08-16T17:54:24Z", "type": "response_item", "payload": {
                       "type": "message", "id": "msg-" + sid, "role": "user", "content": [{"type": "input_text", "text": "instruction"}]}},
                   {"timestamp": "2026-08-16T17:54:25Z", "type": "response_item", "payload": {
                       "type": "function_call", "call_id": "call-" + sid, "name": "exec_command", "arguments": '{"cmd":"echo observed"}'}},
                   {"timestamp": "2026-08-16T17:54:26Z", "type": "response_item", "payload": {
                       "type": "function_call_output", "call_id": "call-" + sid, "output": "observed"}}]
        _write_jsonl(str(tmp_path / name), records)


@pytest.fixture
def pool(tmp_path, monkeypatch):
    frozen = tmp_path / "pool"
    roots(frozen)
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(frozen))
    monkeypatch.setattr(service.adapters, "discover", fail_discovery)
    monkeypatch.setattr(service, "_TRACE_CACHE", {})
    return frozen


def test_frozen_codex_uuid_and_prefixes_match_actual_filename_suffixes(pool):
    for name, sid in zip(NAMES, IDS):
        path = str(pool / name)
        assert service.locate_session(sid) == path
        assert service.locate_session(sid[:8]) == path
        assert service.locate_session(sid.upper()) == path
        assert service.locate_session(name[:-6]) == path
        assert service.locate_session(path) == path
    with pytest.raises(service.SessionLookupError, match="歧义"):
        service.locate_session("01a0")


def test_meta_fallback_never_searches_external_or_subagent_files(pool, tmp_path):
    sid = "11111111-2222-3333-4444-555555555555"
    record = {"type": "session_meta", "payload": {"id": sid, "cwd": "/proj"}}
    _write_jsonl(str(tmp_path / "external.jsonl"), [record])
    _write_jsonl(str(pool / NAMES[0][:-6] / "subagents" / "rollout-child.jsonl"), [record])
    with pytest.raises(service.SessionLookupError, match="找不到"):
        service.locate_session(sid)
    _write_jsonl(str(pool / "rollout-nonstandard-name.jsonl"), [record])
    assert service.locate_session(sid) == str(pool / "rollout-nonstandard-name.jsonl")
    _write_jsonl(str(pool / "rollout-another-name.jsonl"), [record])
    with pytest.raises(service.SessionLookupError, match="歧义"):
        service.locate_session(sid)
