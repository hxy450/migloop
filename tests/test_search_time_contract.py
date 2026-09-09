"""New requests share precise time rules; authenticated old receipts remain history."""
import asyncio
import hashlib
import json

import pytest

from migloop import atom_queries, atoms, atoms_text, mcp_server, service, via
from tests.test_multi_search import _ledger, _call, MAIN_ID


@pytest.mark.parametrize("query", [{"q": "alpha"}, {"q_any": ["alpha", "beta"]}])
@pytest.mark.parametrize("stamp", ["latest", "zzz", "2026-01-01", "2026-01-01T00:00:00", ""])
def test_all_new_search_requests_reject_non_orderable_cutoffs(query, stamp):
    with pytest.raises(ValueError, match="ISO"):
        atom_queries.parameters("search", {**query, "until_ts": stamp})


def test_timezone_order_not_lexical_order_and_equal_bounds_allowed():
    good = {"q": "x", "since_ts": "2026-01-01T08:00:00+08:00", "until_ts": "2026-01-01T00:00:00Z"}
    assert atom_queries.parameters("search", good)["since_ts"] == good["since_ts"]
    with pytest.raises(ValueError, match="不能晚于"):
        atom_queries.parameters("search", {**good, "since_ts": "2026-01-01T08:00:01+08:00"})


@pytest.mark.parametrize("query", [{"q": "alpha"}, {"q_any": ["alpha", "beta"]}])
@pytest.mark.parametrize("scope", [
    {"file": "A.ets", "until_ts": "2026-01-01T00:00:00Z"},
    {"file": "A.ets", "after": True}, {"agent": "a", "file": "A.ets"},
    {"kind": "write", "agent": "a"}, {"kind": "write", "after": True},
    {"v": 2, "until_ts": "2026-01-01T00:00:00Z"},
    {"agent": "a", "v": 2, "until_ts": "2026-01-01T00:00:00Z"},
    {"agent": "a", "since": 0, "until_ts": "2026-01-01T00:00:00Z"},
])
def test_new_queries_never_silently_ignore_unimplemented_scope_combinations(query, scope):
    with pytest.raises(ValueError):
        atom_queries.parameters("search", {**query, **scope})


def test_unknown_result_time_is_a_gap_in_both_single_and_or_search(tmp_path):
    records = _call("2026-01-01T00:00:01Z", "slow", "Bash", {"command": "echo alpha"}, out="beta")
    records[-1].pop("timestamp")
    ledger = _ledger(tmp_path, records)
    ledger.agents[MAIN_ID].actions[0].done_ts = None
    cutoff = "2026-01-01T00:00:05Z"
    single = atoms.search_agent(ledger, MAIN_ID, "beta", until_ts=cutoff)
    multi = atoms.search_agent(ledger, MAIN_ID, "", q_any=["alpha", "beta"], until_ts=cutoff)
    assert single["hits"] == [] and single["unknown_times"] == multi["unknown_times"] == 1
    assert [h["field"] for h in multi["hits"]] == ["input"]
    text = atom_queries.render_text(ledger, "/proj", "search", {"q": "beta", "agent": MAIN_ID, "until_ts": cutoff})
    assert "时间未知 1 个字段未纳入窗口" in text
    assert "未知返回时刻不借用调用时刻" in text


def test_single_search_counts_unknown_versions_even_after_first_hit(tmp_path):
    records = _call("2026-01-01T00:00:01Z", "w1", "Write", {"file_path": "/proj/A.ets", "content": "alpha"})
    records += _call("2026-01-01T00:00:02Z", "w2", "Write", {"file_path": "/proj/A.ets", "content": "alpha"})
    records += _call("2026-01-01T00:00:03Z", "w3", "Write", {"file_path": "/proj/A.ets", "content": "beta"})
    ledger = _ledger(tmp_path, records)
    versions = ledger.stories["/proj/A.ets"].versions
    versions[1].content = versions[1].partial = None
    versions[2].ts = "2026-01-01T00:00:03"  # timezone unknown
    cutoff = "2026-01-01T00:01:00Z"
    result = atoms.search_pool(ledger, "alpha", cutoff)
    assert len(result["files"]) == 1 and result["files"][0]["v"] == 1
    assert result["unknown_versions"] == result["unknown_times"] == 1
    text = atoms_text.render_search(ledger, "alpha", until_ts=cutoff)
    assert "时间未知 1 个字段/版本未纳入窗口" in text


def test_old_receipt_with_bad_time_remains_exact_history_not_new_query():
    args = {"q": "alpha", "until_ts": "zzz"}
    body = "old search output with invalid scope"
    row = {"schema": "migloop-search/1", "id": "a" * 24, "ledger": "old-ledger",
           "args": via.search_args(args), "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "hits": []}
    text = body + "\n" + via.SEARCH_RECEIPT + json.dumps(row)
    assert via.search_receipt(text, args) == row
    with pytest.raises(ValueError):
        atom_queries.parameters("search", args)


def test_old_or_receipt_is_not_rejudged_by_new_scope_policy():
    args = {"q_any": ["alpha", "beta"], "v": 3, "until_ts": "2026-01-01T00:00:00Z"}
    body = "old OR ignored the pool version; this authenticates bytes, not scope quality"
    row = {"schema": "migloop-search/2", "id": "b" * 24, "ledger": "old-ledger",
           "args": via.search_args(args, historical=True),
           "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "hits": []}
    text = body + "\n" + via.SEARCH_RECEIPT + json.dumps(row)
    assert via.search_receipt(text, args) == row
    with pytest.raises(ValueError):
        via.search_args(args)


@pytest.mark.parametrize("query", [{"q": "alpha"}, {"q_any": ["alpha", "beta"]}])
def test_redundant_after_in_time_mode_is_explained_without_widening_cutoff(tmp_path, query):
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:02Z", "w", "Write",
        {"file_path": "/proj/A.ets", "content": "alpha beta"}))
    args = {**query, "until_ts": "2026-01-01T00:00:01Z", "after": True}
    text = atom_queries.render_text(ledger, "/proj", "search", args)
    assert "after=True 不扩大时间范围" in text
    assert "/proj/A.ets@v1" not in text


def test_native_and_http_reject_invalid_scope_before_any_search(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:01Z", "w", "Write",
        {"file_path": "/proj/A.ets", "content": "alpha"}))
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid range must not perform a search")
    monkeypatch.setattr(atoms, "search_pool", forbidden)
    class Backend:
        async def get_ledger(self, sid): return ledger
        async def get_session_cwd(self, sid): return "/proj"
    args = {"q": "alpha", "until_ts": "zzz"}
    with pytest.raises(ValueError, match="ISO"):
        service.atom_text("unused", "search", args)
    from mcp.server.fastmcp.exceptions import ToolError
    with pytest.raises(ToolError, match="ISO"):
        asyncio.run(mcp_server.build_server(Backend()).call_tool("search", {"sid": "s", **args}))
