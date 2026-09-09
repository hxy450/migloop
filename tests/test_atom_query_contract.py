"""One request contract for HTTP and MCP; projections do not grant navigation."""
import asyncio
import json

import pytest

from migloop import atom_queries, atoms_text, mcp_server, service, via
from tests.test_draft_check import data
from tests.test_verdict import _pool
from tests.test_atom_scope import AID, action, fixture, ref


@pytest.mark.parametrize("value", [False, 0, "0", "false", "False", " FALSE ", ""])
def test_explicit_false_is_not_a_truthy_string(value):
    assert atom_queries.parameters("file", {"path": "A.ets", "content": value})["content"] is False
    assert service._flag({"content": value}, "content", "1") is False


@pytest.mark.parametrize("value", [True, 1, "1", "true", "True", " TRUE "])
def test_boolean_inputs_are_normalized_once(value):
    assert atom_queries.parameters("file", {"path": "A.ets", "content": value})["content"] is True


@pytest.mark.parametrize("value", [True, False, 1.5, [], {}, "1.0", "nan"])
def test_version_cannot_be_coerced_from_boolean_or_float(value):
    with pytest.raises(ValueError, match="整数"):
        atom_queries.parameters("file", {"path": "A.ets", "v": value})


def test_aliases_are_explicit_and_conflicting_targets_fail():
    assert atom_queries.parameters("search", {"path": "A.ets", "file": None})["file"] == "A.ets"
    assert atom_queries.parameters("sessions", {"path": "A.ets"})["file"] == "A.ets"
    with pytest.raises(ValueError, match="冲突"):
        atom_queries.parameters("search", {"path": "A.ets", "file": "B.ets"})
    with pytest.raises(ValueError, match="未知查询参数"):
        atom_queries.parameters("agent", {"id": "agent-c", "untill": 12})


def test_json_file_is_compact_by_default_and_expansion_is_explicit(tmp_path):
    ledger = _pool(tmp_path)
    compact = atom_queries.json_data(ledger, "file", {"path": "A.ets", "v": 2})
    expanded = atom_queries.json_data(ledger, "file", {"path": "A.ets", "v": 2, "content": True})
    assert compact["path"] == expanded["path"] and compact["v"] == expanded["v"]
    assert compact["time_scope"] == expanded["time_scope"]
    assert compact.get("content") is None
    assert expanded.get("content") is not None


@pytest.mark.parametrize("tool,args", [
    ("file", {"path": "A.ets", "v": 2, "content": True, "start": 100, "n": 1}),
    ("file", {"path": "A.ets", "v": 2, "diff": True, "v_from": 3, "v_to": 9}),
    ("agent", {"id": "agent-c", "v": 1, "reads": False}),
    ("action", {"id": "agent-c", "seq": 1, "part": "input", "offset": 99999, "max_chars": 10}),
    ("index", {"query": "A.ets", "limit": 1}),
])
def test_json_never_silently_ignores_text_disclosure_parameters(tmp_path, tool, args):
    with pytest.raises(ValueError, match="JSON 投影不支持"):
        atom_queries.json_data(_pool(tmp_path), tool, args)


def test_json_blame_changed_has_the_same_actual_scope_as_text(tmp_path):
    ledger = _pool(tmp_path)
    got = atom_queries.json_data(ledger, "blame", {"path": "A.ets", "v": 2, "changed": True})
    assert got["changed"] is True and got["prev_v"] == 1


def test_action_zero_budget_is_not_silently_replaced_by_twenty_thousand(tmp_path):
    ledger = _pool(tmp_path)
    seq = ledger.agents["agent-c"].actions[-1].seq
    text = atom_queries.render_text(ledger, "/proj", "action", {"id": "agent-c", "seq": seq, "max_chars": 0})
    assert text == "max_chars 必须大于 0"


def test_large_agent_read_disclosure_is_auto_not_an_unexpandable_override():
    ledger, _ = fixture(done=8)
    ledger.agents[AID].actions.extend(action(10 + v, 31, 32, kind="write", ver=v)
                                      for v in range(4, 28))
    auto = atom_queries.render_text(ledger, "/proj", "agent", {"id": AID, "v": 27})
    expanded = atom_queries.render_text(ledger, "/proj", "agent", {"id": AID, "v": 27, "reads": True})
    assert "读 1 条(reads=True 展开)" in auto
    assert "读 1 条(reads=True 展开)" not in expanded
    assert "A.ets@v1" in expanded
    assert atom_queries.parameters("agent", {"id": AID})["reads"] is None


@pytest.mark.parametrize("done,expected_reads", [(8, 1), (20, 0)])
def test_prior_input_index_obeys_same_completion_boundary_as_visible_window(done, expected_reads):
    ledger, _ = fixture(done=done)
    # Read feeds v1, which is outside (1, 3], but may complete after the cutoff.
    ledger.agents[AID].actions[1].at = 1
    payload = atom_queries.agent_data(ledger, AID, v=3, since=1, until=3)
    scope = payload["input_scope"]
    assert scope["omitted_prior"]["reads"] == expected_reads
    assert len(scope["prior_read_preview"]) == expected_reads
    assert not scope["scope_complete"] and not payload["reads"]
    assert all(row["seq"] > 2 for row in payload["actions"])
    # No early preview exposes late output, or any full prior content at all.
    assert "SECRET_RETURN" not in str(scope)
    text = atoms_text.render_agent(ledger, AID, v=3, since=1, until=3)
    assert ("早期读" in text) is bool(expected_reads)


def test_window_data_matches_legacy_selector_without_reclassifying_prior_inputs(tmp_path):
    from migloop import atoms
    ledger = _pool(tmp_path)
    for since in (0, 1):
        legacy = atoms.agent_atom(ledger, "agent-c", v=1, since=since)
        unified = atom_queries.agent_data(ledger, "agent-c", v=1, since=since)
        for field in ("reads", "writes", "actions", "inbox", "children", "prompt", "result"):
            assert unified[field] == legacy[field], field


@pytest.mark.parametrize("kind,args", [("file", {"path": "A.ets", "v": 2}),
                                      ("agent", {"id": "agent-c", "v": 1})])
def test_scope_only_projects_the_same_metadata_without_bodies(tmp_path, kind, args):
    ledger = _pool(tmp_path)
    payload = atom_queries.json_data(ledger, kind, {**args, "scope_only": True})
    text = atom_queries.render_text(ledger, "/proj", kind, {**args, "scope_only": True})
    assert set(payload) == {"time_scope"}
    assert text == atoms_text.render_time_scope(payload["time_scope"])


def test_all_text_surfaces_share_core_and_search_only_adds_transport_receipt(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    ledger = _pool(tmp_path)
    chains = {"chains": [], "touched": []}
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    monkeypatch.setattr(service, "fixchain_payload", lambda _: chains)

    class Backend:
        async def get_ledger(self, sid): return ledger
        async def get_session_cwd(self, sid): return "/proj"
        async def get_fixchain(self, sid): return chains

    seq = ledger.agents["agent-c"].actions[-1].seq
    cases = [("sessions", {"file": "A.ets"}), ("index", {}),
             ("file", {"path": "A.ets", "v": 2}), ("agent", {"id": "agent-c", "v": 1}),
             ("diff", {"path": "A.ets", "v": 2}), ("blame", {"path": "A.ets", "v": 2}),
             ("action", {"id": "agent-c", "seq": seq, "max_chars": 256}),
             ("search", {"q": "spec", "agent": "agent-c"}),
             ("check", {"draft": json.dumps(data(ledger))})]
    for tool, args in cases:
        server = mcp_server.build_server(Backend())
        request = {"sid": "synthetic", **args}
        if tool in ("file", "agent"):
            request["via"] = "sessions"
        blocks = asyncio.run(server.call_tool(tool, request))
        assert isinstance(blocks, list) and len(blocks) == 1
        text = blocks[0].text
        http = service.atom_text("unused", tool, args)
        if tool == "search":
            receipt = via.search_receipt(text, args)
            assert receipt is not None
            assert text.split("\n搜索导航:", 1)[0] == http
        else:
            assert text == http, tool
