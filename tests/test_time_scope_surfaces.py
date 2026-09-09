"""One time-range contract for UI JSON and investigator text, including empty chains."""
import asyncio

import pytest

from migloop import atoms, atoms_text, service, time_scope
from tests.test_atoms import MAIN_ID, _call, _ledger


def _example(tmp_path):
    return _ledger(tmp_path, [
        *_call("2026-01-01T00:00:00.675Z", "write", "Write",
               {"file_path": "/proj/A.ets", "content": "target\n"}, "ok"),
        *_call("2026-01-02T00:00:00Z", "later", "Bash", {"command": "echo later"}, "later")])


def test_file_agent_http_text_share_exact_anchor(tmp_path, monkeypatch):
    ledger = _example(tmp_path)
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    for kind, args in (("file", {"path": "A.ets", "v": 1}), ("agent", {"id": MAIN_ID, "v": 1})):
        payload = service.atom_json("unused", kind, args)
        scope = payload["time_scope"]
        assert scope == time_scope.for_atom(ledger, kind, payload)
        assert scope["latest_known_pool_time"].startswith("2026-01-02")
        assert scope["anchor"]["time"].startswith("2026-01-01")
        compact = atoms_text.render_time_scope(scope)
        text = service.atom_text("unused", kind, args)
        assert compact in text
        assert service.atom_json("unused", kind, {**args, "scope_only": 1}) == {"time_scope": scope}
        # The real returned-node headers must remain untouched by added metadata.
        assert text.splitlines()[0].startswith("# 文件" if kind == "file" else "# agent")
    assert "later" not in atoms_text.render_time_scope(time_scope.overview(ledger))


def test_sessions_without_chain_and_index_still_expose_pool(tmp_path, monkeypatch):
    ledger = _example(tmp_path)
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    monkeypatch.setattr(service, "fixchain_payload", lambda _: {"chains": []})
    sessions = service.atom_text("unused", "sessions", {"file": "absent.ets"})
    assert "2026-01-02" in sessions and "全池时间边界" in sessions
    index = service.atom_text("unused", "index", {"kind": "time"})
    assert MAIN_ID in index and "2026-01-02" in index
    assert service.atom_json("unused", "index", {"kind": "time"}) == {"time_scope": time_scope.overview(ledger)}


def test_mcp_sessions_and_time_index_equal_http_text(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from migloop import mcp_server

    ledger = _example(tmp_path)

    class Backend:
        async def get_ledger(self, sid):
            return ledger

        async def get_session_cwd(self, sid):
            return "/proj"

        async def get_fixchain(self, sid):
            return {"chains": []}

    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    monkeypatch.setattr(service, "fixchain_payload", lambda _: {"chains": []})
    server = mcp_server.build_server(Backend())
    for tool, args in (("sessions", {"file": "absent.ets"}), ("index", {"kind": "time"})):
        blocks = asyncio.run(server.call_tool(tool, {"sid": "unused", **args}))
        assert len(blocks) == 1 and blocks[0].text == service.atom_text("unused", tool, args)


def test_search_includes_equal_instants_with_mixed_iso_precision_and_offset(tmp_path):
    ledger = _example(tmp_path)
    expected = [("/proj/A.ets", 1)]
    for boundary in ("2026-01-01T00:00:00.675000Z", "2025-12-31T19:00:00.675-05:00"):
        result = atoms.search_pool(ledger, "target", since_ts=boundary, until_ts=boundary)
        assert [(r["path"], r["v"]) for r in result["files"]] == expected
        assert result["agents"]
    early = atoms.search_pool(ledger, "target", until_ts="2026-01-01T00:00:00.674999Z")
    assert early["files"] == [] and early["agents"] == []


def test_search_reports_literal_semantics_without_turning_pipe_into_or(tmp_path):
    ledger = _example(tmp_path)
    for args in ({"agent": MAIN_ID}, {"file": "A.ets"}, {"until_ts": "2026-01-03T00:00:00Z"}):
        result = atoms_text.render_search(ledger, "target|absent", **args)
        assert "字面子串" in result and "不支持正则/OR" in result
        assert "首次出现: v1" not in result
