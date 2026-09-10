import asyncio

import pytest

from migloop import atom_queries, mcp_server, probe, time_receipts
from tests.test_temporal import corpus, ts


def test_receipt_binds_query_bytes_body_and_does_not_create_edge(tmp_path):
    ledger, agent, _ = corpus(tmp_path)
    args = {"id": agent, "at": ts(10), "view": "records"}
    text = atom_queries.render_text(ledger, "", "agent", args)
    receipt = time_receipts.parse(ledger, "agent", args, text)
    assert receipt and receipt["node"]["at"].startswith("2026-09-10T10:10")
    assert len(receipt["records"]) == 3 and receipt["relation"] is None
    assert time_receipts.parse(ledger, "agent", {**args, "at": ts(9)}, text) is None
    assert time_receipts.parse(ledger, "agent", args, text.replace("LONGTAIL", "FORGED")) is None
    assert time_receipts.parse(ledger, "file", args, text) is None


def test_projection_is_trace_not_inferred_history(tmp_path):
    ledger, agent, _ = corpus(tmp_path)
    calls = []
    for tool, args in [("agent", {"id": agent, "at": ts(10)}),
                       ("file", {"path": "unrelated-spec.md", "at": ts(10)})]:
        calls.append({"tool": tool, "input": args, "has_result": True,
                      "text": atom_queries.render_text(ledger, "", tool, args)})
    trace = time_receipts.project(ledger, calls)
    assert len(trace["steps"]) == 2 and trace["edges"] == []
    assert all(row["status"] == "recorded_response" and row["relation"] is None for row in trace["steps"])
    assert probe._step_node(ledger, "agent", calls[0]["input"]) is None
    calls[1]["provenance"] = {"origin_unverified": True}
    assert time_receipts.project(ledger, calls)["steps"][1]["node"] is None


def test_mcp_time_entry_does_not_require_via_and_matches_http(tmp_path):
    pytest.importorskip("mcp")
    ledger, agent, _ = corpus(tmp_path)

    class Backend:
        async def get_ledger(self, sid):
            return ledger

        async def get_session_cwd(self, sid):
            return "/p"

    server = mcp_server.build_server(Backend())

    async def run():
        for name, args in [("agent", {"id": agent, "at": ts(10)}),
                           ("file", {"path": "/p/A.ets", "at": ts(10)}),
                           ("search", {"agent": agent, "q": "needle", "at": ts(10)})]:
            blocks = await server.call_tool(name, {"sid": "test", **args})
            text = "".join(b.text for b in blocks)
            assert text == atom_queries.render_text(ledger, "/p", name, args)
            assert time_receipts.parse(ledger, name, args, text)
        blocks = await server.call_tool("agent", {"sid": "test", "id": agent})
        assert time_receipts.parse(ledger, "agent", {"id": agent}, blocks[0].text)
        guide = await server.call_tool("guide", {})
        assert "自由时间调查" in guide[0].text and "migloop-verdict/3" in guide[0].text

    asyncio.run(run())
