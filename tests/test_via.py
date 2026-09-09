"""via 校验:打开了什么,只能从什么跳。"""
from __future__ import annotations

from typing import Any

from migloop import atoms, via
from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call, _rec


def _pool(tmp_path: Any) -> atoms.Ledger:
    conv = [_rec("2026-01-01T00:00:00Z", "user", "转换 A"),
            *_read_call("2026-01-01T00:00:10Z", "c1", "/proj/spec/pages/A.md", "spec\n"),
            *_call("2026-01-01T00:00:20Z", "c2", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets")]
    fix = [_rec("2026-01-01T02:00:00Z", "user", "修 A"),
           *_read_call("2026-01-01T02:00:10Z", "f1", "/proj/entry/A.ets", "a\n"),
           *_call("2026-01-01T02:00:20Z", "f2", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-a", "prompt": "转换 A"}, "done",
                   toolUseResult={"agentId": "c"}),
            *_call("2026-01-01T02:00:00Z", "m2", "Agent", {"name": "fixer", "prompt": "修 A"}, "done",
                   toolUseResult={"agentId": "f"})]
    return _ledger(tmp_path, main, {"agent-c": conv, "agent-f": fix})


def test_first_move_only_from_sessions_then_only_from_opened_nodes(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    st = via.ViaState()
    assert "缺失" in str(via.check(led, st, ""))
    assert via.check(led, st, "sessions") is None                       # 第一跳
    st.open(("file", "/proj/entry/A.ets", 2))                           # file(A.ets, v=2)
    assert "只能用于第一次" in str(via.check(led, st, "sessions"))
    assert "要带版本" in str(via.check(led, st, "file:entry/A.ets"))     # via 不带版本一律拒
    assert via.check(led, st, "file:entry/A.ets@v2 写者行") is None       # 逐字对上
    assert via.check(led, st, "file:A.ets@v2") is None                   # 文件名也解析到同一个键
    assert "版本对不上" in str(via.check(led, st, "file:entry/A.ets@v1 写者"))   # 打开的是 v2,不是 v1
    st.open(("file", "/proj/entry/A.ets", 1))
    assert via.check(led, st, "file:entry/A.ets@v1 写者") is None
    assert "解析不了" in str(via.check(led, st, "凭感觉"))
    assert "解析不了" in str(via.check(led, st, "file:nope.ets@v1"))
    assert "不是已打开" in str(via.check(led, st, "agent:conv-a@v1"))
    st.open(("agent", "agent-c", 1))
    assert via.check(led, st, "agent:conv-a@v1 读取") is None           # 名字解析到 id
    assert via.check(led, st, "agent:agent-c@v1") is None
    assert via.check(led, st, f"agent:{MAIN_ID}") is not None            # 主会话没打开
    assert via.describe(led, st) == "file:A.ets@v2、file:A.ets@v1、agent:conv-a@v1"


def test_parse_resolves_main_session_and_keeps_version_as_written(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    p = via.parse(led, f"agent:{MAIN_ID}@v2 派发")
    assert p["ok"] and p["key"] == MAIN_ID and p["v"] == 2
    p = via.parse(led, "agent:__main__:abcd")
    assert p["key"] == MAIN_ID and p["v"] is None and not p["ok"]        # 没带版本:能解析到键,但不算合法来处
    assert via.parse(led, "task:被修文件")["first"]
    assert not via.parse(led, "search:x")["first"] and not via.parse(led, "search:x")["ok"]


def test_mcp_tools_enforce_via(tmp_path: Any) -> None:
    """服务端:file / agent 的 via 不对就不执行;blame / diff / action 没有 via 参数。"""
    import asyncio

    import pytest
    pytest.importorskip("mcp")
    from migloop import mcp_server

    led = _pool(tmp_path)

    class Backend:
        async def get_ledger(self, sid: str) -> Any:
            return led

        async def get_session_cwd(self, sid: str) -> str:
            return "/proj"

        async def get_fixchain(self, sid: str) -> dict[str, Any]:
            return {"chains": [], "touched": []}

    srv = mcp_server.build_server(Backend())
    tools = {t.name: t for t in asyncio.run(srv.list_tools())}
    assert "via" in tools["file"].inputSchema["properties"] and "via" in tools["agent"].inputSchema["properties"]
    assert "v" in tools["file"].inputSchema["required"] and "v" in tools["agent"].inputSchema["required"]   # 版本必填
    for name in ("blame", "diff", "action", "search"):
        assert "via" not in tools[name].inputSchema["properties"], name

    async def call(name: str, **kw: Any) -> str:
        res = await srv.call_tool(name, kw)
        parts = res[0] if isinstance(res, tuple) else res
        return "".join(getattr(p, "text", "") for p in parts)

    async def run() -> None:
        out = await call("file", sid="s1", path="A.ets", v=2)
        assert "via 缺失" in out
        out = await call("file", sid="s1", path="A.ets", v=2, via="sessions")
        assert "写者脊柱" in out or "文件" in out
        out = await call("agent", sid="s1", id="conv-a", v=1, via="file:entry/A.ets@v1")
        assert "版本对不上" in out                                       # 打开的是 v2
        out = await call("agent", sid="s1", id="conv-a", v=1, via="file:entry/A.ets@v2 写者")
        assert "agent-c" in out or "conv-a" in out
        out = await call("file", sid="s1", path="spec/pages/A.md", v=1, via="sessions")
        assert "只能用于第一次" in out
        out = await call("file", sid="s1", path="spec/pages/A.md", v=1, via="agent:conv-a@v1 读取")
        assert "A.md" in out
        # 另一个 sid 是另一条路线,状态分开
        out = await call("file", sid="s2", path="A.ets", v=2, via="file:entry/A.ets@v2")
        assert "不是已打开" in out

    asyncio.run(run())
    assert mcp_server.via_state("s1").opened == [("file", "/proj/entry/A.ets", 2), ("agent", "agent-c", 1),
                                                 ("file", "/proj/spec/pages/A.md", 1)]
