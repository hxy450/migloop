"""One time-range contract for UI JSON and investigator text, including empty chains."""
import asyncio

import pytest

from migloop import atoms, atoms_text, service, time_scope
from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call


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


def test_search_tail_does_not_advertise_an_uncreated_agent_version(tmp_path):
    ledger = _example(tmp_path)
    result = atoms_text.render_search(ledger, "later", agent=MAIN_ID, after=True)
    assert "没有形成 v2" in result and "不能用作节点坐标" in result
    assert "喂 v2" not in result


def test_http_and_text_cutoff_do_not_leak_late_read_body(monkeypatch):
    from tests.test_atom_scope import AID, fixture

    ledger, _ = fixture()
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    args = {"id": AID, "v": 3, "until": 3, "seen": True}
    data = service.atom_json("unused", "agent", args)
    text = service.atom_text("unused", "agent", args)
    assert data["reads"] == [] and data["children"] == []
    assert [r["v"] for r in data["writes"]] == [1]
    assert "SECRET_RETURN" not in str(data) + text
    assert "FUTURE_SUMMARY" not in str(data) + text
    assert "截止时未确认可用的读取 1 条" in text
    assert "尚未返回" in text and "窗口外索引项另计" in text
    with pytest.raises(ValueError):
        service.atom_json("unused", "agent", {**args, "until": 999})
    assert service.atom_text("unused", "agent", {**args, "until": 999}).startswith("⛔")


def test_invalid_cutoff_mcp_does_not_register_a_successful_open():
    pytest.importorskip("mcp")
    from migloop import mcp_server
    from tests.test_atom_scope import AID, fixture

    ledger, _ = fixture()

    class Backend:
        async def get_ledger(self, sid):
            return ledger

        async def get_session_cwd(self, sid):
            return "/proj"

    async def query():
        server = mcp_server.build_server(Backend())
        args = {"sid": "unused", "id": AID, "v": 3, "via": "sessions", "seen": True}
        bad = await server.call_tool("agent", {**args, "until": 999})
        good = await server.call_tool("agent", {**args, "until": 3})
        return bad[0].text, good[0].text

    bad, good = asyncio.run(query())
    assert bad.startswith("⛔")
    assert good.startswith("# agent") and "SECRET_RETURN" not in good


def test_tail_file_reader_is_not_an_existing_agent_version(tmp_path, monkeypatch):
    ledger = _ledger(tmp_path, [
        *_call("2026-01-01T00:00:00Z", "write", "Write", {"file_path": "/proj/A.ets", "content": "a\n"}, "ok"),
        *_read_call("2026-01-01T00:00:05Z", "read", "/proj/A.ets", "a\n")])
    payload = atoms.file_atom(ledger, "A.ets", 1)
    reader = payload["readers"][0]
    assert reader["at"] == reader["feeding_slot"] == 2
    assert reader["after_last_effect"] is True and reader["agent_v"] is None
    assert reader["seq"] is not None
    text = atoms_text.render_file(ledger, "A.ets", 1, readers=True)
    assert "收尾后" in text and "未形成版本" in text
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    for tool, args in (("agent", {"id": MAIN_ID, "v": 2}), ("file", {"path": "A.ets", "v": 2})):
        with pytest.raises(ValueError, match="版本不存在"):
            service.atom_json("unused", tool, args)
        assert service.atom_text("unused", tool, args).startswith("⛔")
