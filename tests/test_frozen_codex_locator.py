"""The UUID serialized into a Codex page must resolve within its frozen root pool."""
from __future__ import annotations

import json
import threading

import pytest

from migloop import service, serve
from tests.test_atoms import _write_jsonl
from tests.test_frozen_pool import fail_discovery
from tests.test_service_serve import _get
from tests.test_transcript_tags import IDS, NAMES, roots


@pytest.fixture
def pool(tmp_path, monkeypatch):
    frozen = tmp_path / "pool"
    roots(frozen)
    monkeypatch.setenv("MIGLOOP_FROZEN_POOL", str(frozen))
    monkeypatch.setattr(service.adapters, "discover", fail_discovery)
    for name in ("_TRACE_CACHE", "_LEDGER_CACHE", "_FIXCHAIN_CACHE"):
        monkeypatch.setattr(service, name, {})
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


def test_page_canonical_sid_roundtrips_all_frozen_api_routes(pool, monkeypatch):
    path = str(pool / NAMES[1])
    sid = service.fixchain_light(path)["sid"]
    assert sid == IDS[1] and service.locate_session(sid) == path
    monkeypatch.setattr(service, "probe_payload", lambda resolved, run: {"resolved": resolved, "run": run})
    server = serve.make_server(sid, "127.0.0.1", 0, {})
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body, _ = _get(base, "/api/insight1/fixchain/" + sid)
        assert status == 200 and f'"sid": "{sid}"' in body.decode("utf-8")
        for prefix in ("/api/insight1/fixchain-data/", "/api/insight1/atom/"):
            status, body, _ = _get(base, prefix + sid + ("/index" if "atom" in prefix else ""))
            assert status == 200 and isinstance(json.loads(body), dict)
        status, body, _ = _get(base, "/api/insight1/probe/" + sid + "?run=fixture")
        assert status == 200 and json.loads(body) == {"resolved": path, "run": "fixture"}
    finally:
        server.shutdown()
        server.server_close()
