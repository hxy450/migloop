"""MigLoop 两原子 MCP 服务 —— 调查 agent 的工具面。

人在返修链页上点的每一步,对应这里的一次工具调用:同一份账本、同一套原子,
文本渲染给模型。启动(stdio):

    python -m migloop.mcp_server

在 Claude Code 里注册:``claude mcp add migloop -- python -m migloop.mcp_server``(需要 ``mcp`` 包)。
所有工具都要 sid(会话 id 或其 8 位前缀);账本按 sid 的池子(同工程兄弟会话)整包缓存。
"""

from __future__ import annotations

from typing import Any

from migloop import atoms, atoms_text
from migloop import via as via_mod

from migloop.guidance import GUIDE, guide_text

def _rt() -> Any:
    from migloop import service
    return service.McpBackend()


def build_server(backend: Any | None = None) -> Any:
    """backend 提供三个 async 方法:get_ledger(sid) / get_session_cwd(sid) / get_fixchain(sid)。
    默认用 service.McpBackend(与 ``migloop serve`` 共用账本缓存);别的宿主注入自己的服务层。"""
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    import inspect

    # Queries do not modify source transcripts/project files or contact external services.
    # Navigation state and caches are local bookkeeping, not edits to the evidence.
    readonly = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    srv = FastMCP("migloop-atoms",
                  # Codex prepends these instructions to every deferred tool description.
                  # Repeating another tool's name here makes description-based discovery ambiguous.
                  instructions="MigLoop 只读返修调查工具。节点为版本文件与版本 agent;"
                               "索引与模型主张不等于已经核实的原文事实。")
    # These tools return rendered text, not a second structured data interface.
    # New FastMCP versions otherwise emit the SAME string in content AND
    # structuredContent.result. A client forwarding the envelope pays twice.
    # Older SDKs without structured output keep their native text-only contract.
    text_options: dict[str, Any] = {"annotations": readonly}
    if "structured_output" in inspect.signature(srv.tool).parameters:
        text_options["structured_output"] = False
    # 一个服务器实例承载一次调查;同一本账的 sid 前缀/全号/路径共用状态。
    # 新实例、或同一 raw sid 解析到另一账本时不会继承旧节点。
    via_states: dict[str, via_mod.ViaState] = {}

    def via_state(ledger: atoms.Ledger) -> via_mod.ViaState:
        return via_states.setdefault(atoms.ledger_identity(ledger), via_mod.ViaState())

    def _be() -> Any:
        return backend if backend is not None else _rt()

    async def _ctx(sid: str) -> tuple[Any, str]:
        rt = _be()
        return await rt.get_ledger(sid), await rt.get_session_cwd(sid)

    @srv.tool(**text_options)
    def guide(topic: str = "core") -> str:
        """首次读 core；按需 evidence/search/investigation/navigation/verdict/full。提交前读 verdict。"""
        return guide_text(topic=topic)

    @srv.tool(**text_options)
    async def sessions(sid: str, file: str | None = None) -> str:
        """返修链/实际版本/修复候选清单及账本身份。sid 为会话号或 8 位前缀；调查单文件时传 file，省略则总览。"""
        rt = _be()
        payload = await rt.get_fixchain(sid)
        cwd = await rt.get_session_cwd(sid)
        ledger = await rt.get_ledger(sid)
        from . import atom_queries
        return atom_queries.render_text(ledger, cwd, "sessions", {"file": file}, chains=payload)

    @srv.tool(**text_options)
    async def index(sid: str, kind: str | None = None, query: str | None = None,
                    limit: int = 0) -> str:
        """账本目录。kind=agent/ets/spec/src/other/scan(扫描缺口)/time(全池时段)，query 子串过滤；无过滤默认前80条，有过滤最多300，limit 可指定。"""
        ledger, cwd = await _ctx(sid)
        from . import atom_queries
        return atom_queries.render_text(ledger, cwd, "index", dict(kind=kind, query=query, limit=limit))

    @srv.tool(**text_options)
    async def file(sid: str, path: str, v: int, content: bool = False,
                   diff: bool = False, start: int | None = None, n: int | None = None,
                   readers: bool = False, v_from: int | None = None, v_to: int | None = None,
                   diff_chars: int | None = None, m_from: int = 1, m_n: int = 0, m_all: bool = False, via: str = "") -> str:
        """打开 file@v：≤v 写者脊柱与证据标签。v/via 必填；via 照抄已打开节点或 search 精确凭据，首次可 sessions。
        content=True+start/n 展开复原行；diff=True 看该版，v_from/v_to 展开锚点内区间(每页40版)。
        readers 展开读者；词法候选默认只计数，m_n=40/m_from 翻页、m_all 铺只读提及，均非确定读写。"""
        ledger, cwd = await _ctx(sid)
        st = via_state(ledger)
        node, target_error = via_mod.target(ledger, "file", path, v)
        err = via_mod.check(ledger, st, via, node)
        if err:
            return err
        if target_error or node is None:
            return target_error or "⛔ 目标文件无法核验,未打开。"
        from . import atom_queries
        out = atom_queries.render_text(ledger, cwd, "file", dict(path=node[1], v=v, content=content, diff=diff,
            start=start, n=n, readers=readers, v_from=v_from, v_to=v_to,
            diff_chars=diff_chars, m_from=m_from, m_n=m_n, m_all=m_all))
        if via_mod.returned_node(ledger, "file", out) != node:
            return "⛔ 文件返回的版本与目标不一致,未打开。\n" + out
        st.open(node)
        return out

    @srv.tool(**text_options)
    async def agent(sid: str, id: str, v: int, since: int | None = None,
                    reads: bool | None = None, seen: bool = False, until: int | None = None, via: str = "") -> str:
        """打开 agent@v 的累计输入/效应索引(不是全文)。v/via 必填，同 file 导航规则。
        since 只看(since,v]，主会话宜缩窗口；早期输入索引可另开，不能据窗口断言没读。
        reads 默认自动折叠大代理，True 显式展开、False 只计数；seen 展开已见片段。
        until=#调用号按发起时刻截已返回输入，未完成读取不算当时已知；原文用 action。"""
        ledger, cwd = await _ctx(sid)
        st = via_state(ledger)
        node, target_error = via_mod.target(ledger, "agent", id, v)
        err = via_mod.check(ledger, st, via, node)
        if err:
            return err
        if target_error or node is None:
            return target_error or "⛔ 目标 agent 无法核验,未打开。"
        from . import atom_queries
        out = atom_queries.render_text(ledger, cwd, "agent", dict(id=node[1], v=v, since=since, reads=reads,
                                                                seen=seen, until=until))
        if via_mod.returned_node(ledger, "agent", out) != node:
            return "⛔ agent 返回的版本与目标不一致,未打开。\n" + out
        st.open(node)
        return out

    @srv.tool(**text_options)
    async def blame(sid: str, path: str, v: int | None = None, start: int | None = None,
                    n: int | None = None, changed: bool = False) -> str:
        """逐行来源；start/n 选行。changed=True 查修复版替换/删除的前版行及引入者。
        无法归属时 recovery 给可核历史全文/补丁/输入入口，不将快照作者冒充未知行作者。"""
        ledger, cwd = await _ctx(sid)
        from . import atom_queries
        return atom_queries.render_text(ledger, cwd, "blame", dict(path=path, v=v, start=start, n=n, changed=changed))

    @srv.tool(**text_options)
    async def diff(sid: str, path: str, v: int) -> str:
        """第 v 版的 diff；保留原生补丁或复原差分的来源与未知边界，不打开节点。"""
        ledger, cwd = await _ctx(sid)
        from . import atom_queries
        return atom_queries.render_text(ledger, cwd, "diff", dict(path=path, v=v))

    @srv.tool(**text_options)
    async def search(sid: str, q: str = "", agent: str | None = None, v: int | None = None,
                     since: int | None = None, file: str | None = None, after: bool = False,
                     since_ts: str | None = None, until_ts: str | None = None, kind: str | None = None) -> str:
        """字面子串(不区分大小写，不支持正则/OR)。agent+v/since 查该代理输入效应；file+v 查文件生命周期内容。
        全池必须 until_ts，可加 since_ts；kind=write 查写能力候选。after=True 才列锚点后结果。
        返回范围/缺口；零命中不证明不存在。hits 中精确 via 凭据可独立打开命中节点，不证明历史读写。"""
        ledger, cwd = await _ctx(sid)
        args = dict(q=q, agent=agent, v=v, since=since, file=file, after=after,
                    since_ts=since_ts, until_ts=until_ts, kind=kind)
        hits: list[dict[str, Any]] = []
        from . import atom_queries
        out = atom_queries.render_text(ledger, cwd, "search", args, navigation_hits=hits)
        return via_mod.search_return(ledger, via_state(ledger), args, out, hits)

    @srv.tool(**text_options)
    async def action(sid: str, id: str, seq: int, max_chars: int = 20000, offset: int = 0, find: str = "",
                     part: str | None = None, m_n: int = 0, m_from: int = 1) -> str:
        """展开某代理 #seq 原始调用。part=input/output 选择原文侧，find/offset 仅在选中侧定位；Write 正文/命令用 input。
        max_chars 控制原文窗口，审计指针另列；词法导航默认仅计数，m_n/m_from 按需翻页。不开节点。"""
        ledger, _cwd = await _ctx(sid)
        from . import atom_queries
        return atom_queries.render_text(ledger, _cwd, "action", dict(id=id, seq=seq, max_chars=max_chars,
            offset=offset, find=find, part=part, m_n=m_n, m_from=m_from))

    @srv.tool(**text_options)
    async def check(sid: str, draft: str, file: str | None = None) -> str:
        """核完整 YAML/JSON 草稿(≤120000字符)：身份/节点/引用/显式边/覆盖/basis，不核原因真假、不打开节点。
        file 为对账目标；反馈最多40项并标省略数。改稿须再查，mechanical_clear 不代表语义正确。"""
        from . import atom_queries
        ledger, _cwd = await _ctx(sid)
        payload = await _be().get_fixchain(sid)
        return atom_queries.render_text(ledger, _cwd, "check", dict(draft=draft, file=file), chains=payload)

    return srv


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
