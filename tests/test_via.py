"""via 校验:打开了什么,只能从什么跳。"""
from __future__ import annotations

from typing import Any

from migloop import atoms, via
from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call, _rec


def test_mcp_queries_advertise_read_only_evidence_access():
    import asyncio
    import pytest
    pytest.importorskip("mcp")
    from migloop.mcp_server import build_server

    tools = asyncio.run(build_server().list_tools())
    assert len(tools) == 10
    for tool in tools:
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False


def _pool(tmp_path: Any, spec: str = "spec\n") -> atoms.Ledger:
    conv = [_rec("2026-01-01T00:00:00Z", "user", "转换 A"),
            *_read_call("2026-01-01T00:00:10Z", "c1", "/proj/spec/pages/A.md", spec),
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


def test_first_self_via_rejection_explains_retry_without_opening_anything(tmp_path):
    led = _pool(tmp_path)
    state = via.ViaState()
    destination = ("file", "/proj/entry/A.ets", 2)
    text = via.check(led, state, "file:entry/A.ets@v2", destination)
    assert text.startswith("⛔") and "改用 via=sessions" in text
    assert "本次未打开目标" in text and state.opened == []
    assert via.check(led, state, "sessions", destination) is None
    assert state.opened == []  # Validation itself never claims a tool returned.


def test_exact_error_choices_are_bounded_but_do_not_remove_opened_nodes(tmp_path):
    led = _pool(tmp_path)
    state = via.ViaState()
    for version in range(1, 13):
        state.open(("file", "/exact/nested/A.ets", version))
    before = list(state.opened)
    text = via.describe(led, state, exact=True, limit=8)
    assert "file:/exact/nested/A.ets@v12" in text and "另有 4 个" in text
    assert "@v1、" not in text
    assert state.opened == before and state.has(before[0])


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
        # 同一本账的 sid 别名共用路线,换参数拼法不能重开 sessions 入口。
        out = await call("file", sid="s2", path="A.ets", v=2, via="file:entry/A.ets@v2")
        assert "# 文件" in out
        out = await call("file", sid="s2", path="A.ets", v=2, via="sessions")
        assert "只能用于第一次" in out

    asyncio.run(run())


def test_target_and_returned_node_require_exact_existing_versions(tmp_path: Any) -> None:
    from migloop import atoms_text
    led = _pool(tmp_path)
    for kind, hint in (("file", "A.ets"), ("agent", "fixer")):
        for v in (None, -1, 0, 999):
            node, error = via.target(led, kind, hint, v)
            assert node is None and error and "目标版本不存在" in error
    assert via.target(led, "file", "missing.ets", 1)[0] is None
    node = via.returned_node(led, "file", atoms_text.render_file(led, "A.ets", 999))
    assert node == ("file", "/proj/entry/A.ets", 2)              # 正文核出实际 v2,不能认请求的 v999
    assert via.returned_node(led, "agent", atoms_text.render_agent(led, "fixer", 999)) == ("agent", "agent-f", 1)
    assert via.returned_node(led, "file", "账本里没有该文件: A.ets") is None


def test_search_receipts_bind_actual_hit_target_instance_and_ledger(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    other = _pool(tmp_path / "other", "different spec")
    state = via.ViaState()
    args = {"q": "spec", "until_ts": "2026-01-01T01:00:00Z"}
    dest = ("file", "/proj/spec/pages/A.md", 1)
    output = via.search_return(led, state, args, "# search\nreal displayed hit", [
        {"kind": dest[0], "key": dest[1], "v": dest[2], "seq": 2, "field": "content"},
        {"kind": "file", "key": "/missing", "v": 1},
        {"kind": "file", "key": dest[1], "v": 99},
        {"kind": "agent", "key": "agent-c", "v": None}])
    receipt = via.search_receipt(output, args)
    assert receipt is not None and len(receipt["hits"]) == 1
    handle = receipt["hits"][0]["via"]
    assert via.check(led, state, handle, dest) is None and not state.opened
    assert via.check(led, state, handle, ("agent", "agent-c", 1)) is not None
    assert via.check(led, state, handle, ("file", dest[1], 2)) is not None
    assert via.check(led, state, handle.rsplit(":", 1)[0] + ":2", dest) is not None
    assert via.check(led, via.ViaState(), handle, dest) is not None
    assert via.check(other, state, handle, dest) is not None
    assert via.search_receipt(output.replace("real displayed", "changed displayed"), args) is None
    assert via.search_receipt(output, {**args, "q": "different"}) is None
    assert via.search_receipt("# historical search without receipt", args) is None
    identity = via.trace_identity(led, [{"tool": "search", "input": args, "has_result": True, "text": output}], {})
    assert identity["bound"] is True and identity["source"] == "search"
    assert via.trace_identity(other, [{"tool": "search", "input": args, "has_result": True, "text": output}], {})["bound"] is False


def test_mcp_search_receipt_opens_only_a_returned_hit_without_a_fake_source_node(tmp_path: Any) -> None:
    import asyncio
    import pytest
    pytest.importorskip("mcp")
    from migloop import mcp_server, probe
    led = _pool(tmp_path, "search navigation needle")

    class Backend:
        async def get_ledger(self, sid: str) -> Any:
            return led

        async def get_session_cwd(self, sid: str) -> str:
            return "/proj"

    srv = mcp_server.build_server(Backend())
    fresh = mcp_server.build_server(Backend())

    async def call(server: Any, tool: str, **args: Any) -> str:
        response = await server.call_tool(tool, {"sid": "s1", **args})
        parts = response[0] if isinstance(response, tuple) else response
        return probe._unwrap_result("".join(getattr(part, "text", "") for part in parts))

    async def run() -> None:
        args = {"q": "navigation needle", "until_ts": "2026-01-01T01:00:00Z"}
        out = await call(srv, "search", **args)
        receipt = via.search_receipt(out, args)
        assert receipt is not None
        hit = next(h for h in receipt["hits"] if h["kind"] == "file")
        assert hit["key"] == "/proj/spec/pages/A.md" and hit["v"] == 1
        assert (await call(srv, "file", path="A.ets", v=1, via=hit["via"])).startswith("⛔")
        assert (await call(fresh, "file", path=hit["key"], v=hit["v"], via=hit["via"])).startswith("⛔")
        opened = await call(srv, "file", path=hit["key"], v=hit["v"], via=hit["via"])
        assert opened.startswith("# 文件")  # 不需要先打开假的父 agent
        assert (await call(srv, "agent", id="conv-a", v=1, via="file:spec/pages/A.md@v1")).startswith("# agent")
        empty = await call(srv, "search", **{**args, "q": "no-such-token"})
        assert via.search_receipt(empty, {**args, "q": "no-such-token"})["hits"] == []

    asyncio.run(run())


def test_mcp_isolates_servers_and_ledgers_and_never_opens_invalid_targets(tmp_path: Any) -> None:
    import asyncio
    import pytest
    pytest.importorskip("mcp")
    from migloop import mcp_server, probe

    first_ledger = _pool(tmp_path / "first")
    second_ledger = _pool(tmp_path / "second", "different spec\n")
    assert atoms.ledger_identity(first_ledger) != atoms.ledger_identity(second_ledger)

    class Backend:
        current = first_ledger

        async def get_ledger(self, sid: str) -> Any:
            return self.current

        async def get_session_cwd(self, sid: str) -> str:
            return "/proj"

    backend = Backend()
    srv = mcp_server.build_server(backend)
    fresh = mcp_server.build_server(backend)

    async def call(server: Any, tool: str, **kw: Any) -> str:
        res = await server.call_tool(tool, {"sid": "same-raw-sid", **kw})
        parts = res[0] if isinstance(res, tuple) else res
        return probe._unwrap_result("".join(getattr(p, "text", "") for p in parts))

    async def run() -> None:
        for tool, args in (("file", {"path": "A.ets"}), ("agent", {"id": "fixer"})):
            for v in (0, 999):
                out = await call(srv, tool, **args, v=v, via="sessions")
                assert out.startswith("⛔") and "目标版本不存在" in out
        out = await call(srv, "file", path="A.ets", v=1, diff=True, v_from=2, v_to=2, via="sessions")
        assert out.startswith("⛔")                              # 区间不许越过锚点,失败不消耗入口
        out = await call(srv, "file", path="A.ets", v=2, diff=True, v_from=1, v_to=2, via="sessions")
        assert "@v2" in out.splitlines()[0] and "每版完整 diff" in out
        out = await call(srv, "agent", id="fixer", v=1, via="file:A.ets@v999")
        assert out.startswith("⛔") and "不是已打开" in out
        out = await call(srv, "agent", id="fixer", v=1, via="file:A.ets@v2")
        assert out.startswith("# agent")
        out = await call(fresh, "file", path="A.ets", v=2, via="sessions")
        assert out.startswith("# 文件")                        # 新服务器实例不继承前一条路线
        backend.current = second_ledger
        out = await call(srv, "agent", id="fixer", v=1, via="file:A.ets@v2")
        assert out.startswith("⛔") and "不是已打开" in out       # raw sid 复用到另一账本也不继承
        out = await call(srv, "file", path="A.ets", v=2, via="sessions")
        assert out.startswith("# 文件")

    asyncio.run(run())
