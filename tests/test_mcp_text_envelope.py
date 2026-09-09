"""The same evidence must not be sent twice as text plus a structured scalar wrapper."""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")
from mcp.types import CallToolResult

from migloop import atoms_text, mcp_server
from tests.test_atoms import MAIN_ID, _call, _ledger


def test_all_nine_queries_advertise_text_only_without_a_duplicate_output_schema():
    server = mcp_server.build_server()
    tools = asyncio.run(server.list_tools())
    assert len(tools) == 9
    assert all(t.outputSchema is None for t in tools)


def test_guide_envelope_contains_exactly_one_copy_of_the_guide():
    blocks = asyncio.run(mcp_server.build_server().call_tool("guide", {}))
    assert isinstance(blocks, list) and len(blocks) == 1
    assert blocks[0].type == "text" and blocks[0].text == mcp_server.GUIDE
    serialized = CallToolResult(content=blocks).model_dump_json(exclude_none=True)
    assert "structuredContent" not in serialized
    assert serialized.count("MigLoop 两原子归因指南") == 1


def test_raw_action_body_and_pagination_are_unchanged_by_envelope_deduplication(tmp_path):
    marker = "EXACT_RAW_EVIDENCE_KEEP_ONCE"
    led = _ledger(tmp_path, [*_call("2026-01-01T00:00:00Z", "w", "Write", {
        "file_path": "/proj/A.ets", "content": "prefix " * 1000 + marker + " tail " * 1000})])
    seq = led.agents[MAIN_ID].actions[0].seq

    class Backend:
        async def get_ledger(self, sid):
            return led

        async def get_session_cwd(self, sid):
            return "/proj"

    server = mcp_server.build_server(Backend())
    args = dict(sid="synthetic", id=MAIN_ID, seq=seq, part="input", find=marker, max_chars=512, m_n=0)
    blocks = asyncio.run(server.call_tool("action", args))
    expected = atoms_text.render_action(led, MAIN_ID, seq, part="input", find=marker, max_chars=512, m_n=0)
    assert isinstance(blocks, list) and len(blocks) == 1 and blocks[0].text == expected
    serialized = CallToolResult(content=blocks).model_dump_json(exclude_none=True)
    assert serialized.count(marker) == 1 and "structuredContent" not in serialized
    assert "offset=" in expected and "事件 id" in expected
