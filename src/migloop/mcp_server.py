"""MigLoop 两原子 MCP 服务 —— 调查 agent 的工具面。

人在返修链页上点的每一步,对应这里的一次工具调用:同一份账本、同一套原子,
文本渲染给模型。启动(stdio):

    python -m migloop.mcp_server

在 Claude Code 里注册:``claude mcp add migloop -- python -m migloop.mcp_server``(需要 ``mcp`` 包)。
所有工具都要 sid(会话 id 或其 8 位前缀);账本按 sid 的池子(同工程兄弟会话)整包缓存。
"""

from __future__ import annotations

from typing import Any

from migloop import atoms_text

GUIDE = """\
# MigLoop 两原子归因指南

你在分析一次 Android→HarmonyOS 自动迁移的完整实录。实录已被整理成一本账,账上只有两种原子:

- **版本文件** file(path, v):文件的第 v 版。工具给你 ≤v 的全部写者(每版是哪个 agent 在它自己的
  第几版写的、diff、来路)、读了这一版的 agent(下游)、以及这一版的复原全文(复原不了会说明原因)。
- **版本 agent** agent(id, v):一个 agent 的第 v 版 = 它做出第 v 个对外效应(写文件 / 删文件 /
  派发子 agent / 发消息)之后的状态。工具给你派发它的人与派发词全文、收件箱、≤v 的全部读取
  (每条绑定读到的是文件第几版)、产出、收尾输出。**v 之后的活动与第 v 版的归因无因果,已截掉。**

两原子互相以 (path, v) / (agent id, v) 引用。人和你走的是同一张图。

## 标签的含义(标签是证据,不是裁决)
- ▲旧版 a/b:读的时候绑到第 a 版,但这条读喂养的那笔写发生时文件已是第 b 版 —— "读旧版"候选
- 行段 (x-y行):只读了这几行 —— "源码没读全"的原始证据;没标的是全文读
- 写前读:读自己也写过的文件(Edit 前必 Read / 写后自查),程序性动作,归因时打折
- 依赖读:cp 源 / < 输入,内容没进上下文
- 脚本读 / 脚本落盘:从脚本字面量推断的读写,置信低于 Read/Write 工具
- 外部输入:第一次出现就是被读,没人写过(安卓源码、spec 参考、模板)—— 树的叶子
- 实录外修改:内容变了但没有记录在案的写(脚本动态目标 / 构建工具 / 人手)
- 版本就近绑定(不确定):读发生在文件状态未知时,版本号是就近猜的

## 信息不会丢
file 原子末尾的「碰过它、方向不明的调用」与 sessions 末尾的「修复期被脚本碰过、方向不明的工程文件」:脚本里出现了
这个路径但账本判不出是读是写(既读又写 / 数据表),不立版本、不猜方向,只给动作号 —— action(id, n) 展开原文自己判。
被修的真文件可能只在这里露面(0723 修复真正改错值的 F012ViewModel.ets 就是修复方用 python heredoc 改的)。
file 原子末尾还有「提到它的命令」:命令行 / heredoc 体 / 跑的脚本正文里出现这个路径的每一条命令,不论账本有没有解出读写
(等于原始转录按文件名 grep 的结果),每条标明账本记到了什么(写@v / 读 / 碰过 / 没记到)。版本内容未知、实录外修改、
脚本黑盒,先看这一节里「没记到」的那几条,按动作号 action 展开命令原文自己判。
agent 工具给的每条动作/读取后面的 (#n) 是动作号;action(id, n) 返回那次工具调用的完整原始输入与输出
(命令原文、grep 命中、cat 出来的全文、Read 到的内容)。摘要看不清时直接展开,不要猜。
几万字的 think / 结果超过 max_chars 会截断并说明剩余多少:offset= 从第几字继续,find= 跳到关键词前
—— 找决策句用它,别拿 search 撞。子 agent 的收尾全文在父会话那条派发调用的结果里(收尾行给了坐标)。
读记录下的"看见 615: …"是从 stdout 对账出来的行:agent 在那次调用里确实看到了这一行。
摘要只给前 3 行和全部行号,原文用 action(id, n) 拉 —— 两者是同一份信息,摘要只负责让你知道该展开哪次。
读不一定是全文:每条读带范围标签([570-625行] / 看见的行 / 依赖读=内容没进上下文)。核一条读有两条路:
action(id, n) 是模型当时眼睛里看到的原始输出;file(path, v, content=True, start=570, n=56) 是账本复原的
第 v 版里那一段。两者对不上就是线索(实录外改动、就近绑定的版本)。
**主会话动辄几百次调用,整个生命周期一次查会撑爆上下文**:查主会话一律带窗口
agent(id, v, since=v-1),只看喂养第 v 版的输入;子 agent 通常几十次调用,整段给 —— 它早期版本读的
spec 常常就是后来写错的根源,别只看写那一版的窗口。主会话一版之内也可能读几十个不相干的文件:问「它写这份
spec 时凭什么」用 search(q, agent=主会话, v=那一版) 按词切,不要用窗口硬看。

## search:带起点的按词查找
`search(sid, q, agent=id或名字, v=, since=)` 只在这个 agent 喂养第 v 版及之前的记录里找:派发词、读到的内容、写入内容、
命令与结果、它自己说的话、收件、注入的技能。命中按种类分组,每条带 (#n@L行)、喂哪一版、下一跳(file / diff / action)。
锚点之后的命中只计数,不混进因果;范围内零命中是可引用的否定证据。派发者后来说的话用 since_ts / until_ts
(文件时间线上两个版本的时刻)做区间。`search(sid, q, file=path, v=)` 查这个词第一次出现在第几版、谁写的,以及哪些
读者的读结果里命中过。找上游只能带起点:提到过一个词不等于在这条链的上游,每一跳都要有账本里的边。
每次 search 的输出第二行是「范围」:agent 模式只含这个 agent 的记录,file 模式只含该文件已知内容。**零命中只能按那一行的范围写**。
要写「生成期没人见过 X」这种否定,用 `search(sid, q, until_ts=生成写入的时刻)` 全池查:范围 = 那一刻之前所有 agent 的记录 +
所有文件的已知内容(内容未知的版本数会写出来),结果自带范围行,报告里把它抄上。全池查只用来核否定,不用来找上游。
报告里引用坐标写成 #n@L行(动作号加转录行号),不带工具也能回查。

「上游 N/M 跳」(index / file / agent / sessions 都印):从这个节点往上游到池外最多经过几次 agent↔文件转换(派发也算一跳),
建账时算好的。N 按累计读(agent 写之前读过的一切都算它的输入,主会话跑了几百轮就是几百跳,量的是管线深度),M 只按最近一轮
窗口里读的。挑「链最长」的案例、估一根要追多深,看这两个数。

## 建议的调查路径
1. sessions(sid, file=目标文件) 看那条返修链:被修文件、修复方(按先后分段,各段文件版本与时刻)、被修行数与
   ★ 原作者、修因。查一条链就带 file;不带 file 是全部链的总览。链根只认工程根目录下的代码与配置
   (.ets/.ts/.js/.json5/.cpp/.h 与 resources/** 下的 .json;spec/docs/构建产物/测试目录不算),三种:
   rework(生成过又被改,问为什么被改)/ created(修复期新建,问为什么生成期没有它)/
   template(模板或外部原样留到修复期才改,问为什么生成期没改它)。
   created 链先问三件事:baseline 里有没有这一页(index(query=, kind=spec))、有没有派发词把它列为输出
   (search(q=文件名, agent=主会话, v=))、占位登记里有没有它(search(q=, file=placeholder-registry.md));三问全否 = 无人被指派。
   修复轮没动的文件(sessions 里没有它的链)不等于修复侧没看到它:缺陷单可能点了它却把落点路由到别的文件。
   用 search(q=文件名, since_ts=修复开始时刻, until_ts=结束) 全池查修复期谁提到过它,再 file(那张单, content=1) 看正文。
2. diff(path, v_fix) 看修复到底改了什么;blame(path, v_fix, changed=True) 直接列出修复版替换/删除的
   那些行及其引入者(owner@since_v)—— 不必对整个文件做 blame。某一行是谁写的用 blame(path, v, start=行号, n=1)。
   file 三种口径:file(path) 索引;file(path, v, diff=1) 或 diff(path, v) 看某一版;file(path, diff=1) 不带 v 每版完整 diff,
   一页 40 版、v_from/v_to 翻页 —— 问「一个文件为什么被改了几十次」才用它。
3. agent(owner_id, since_v) 看引入者写那一版时手里有什么:派发词、读过哪些 spec/源码(版本、
   行段、是否旧版)、收件箱有没有改指令。对比修复方 agent 的读取集,找"该读没读"。
4. 顺着 file(读到的 spec@v) 往上游走,直到找到最早出问题的环节。

## 结论要求
报告写成整条链:每环「谁、凭什么(坐标)、判定」,判定只有三种 —— 传递 / 错 / 缺(传递=照上游做的;错=有好的输入没用或
用错;缺=输入里本来就没有)。追到池外输入、批量生成的脚本或技能定义为止,停在中间要说明为什么;指出故障进入点(第一个
「错」或「缺」所在的环),以及修复侧比生成侧多看到了什么(类型:真机 dump / 截图 / 编译输出 / 接口探测 / 授权口径 / 晚出生的
现成件)。「错」的细分仍用这六类词:spec 写错 / 读了旧版 / 漏读(相对修复方的读取集)/ 转换错(读全了仍写错)/
closer 或后续写者破坏 / 源码没读全。每条证据带 `path@v` 或 `agent v` 引用。
凡是写「没有 / 零命中 / 从没读过 / 无人」,后面必须跟工具输出的「范围」行(哪些 agent、哪些文件、到哪一刻、内容未知几版);
没有全池 until_ts 查询撑腰的,只能写成「X 在这个范围内没见过」。
边界:账本里只有**被读过**的安卓源码,从没人读过的文件不存在;标签是线索,盲写/脚本落盘的
版本内容可能未知,如实说"无法确认"。
"""


def _rt() -> Any:
    from migloop import service
    return service.McpBackend()


def build_server(backend: Any | None = None) -> Any:
    """backend 提供三个 async 方法:get_ledger(sid) / get_session_cwd(sid) / get_fixchain(sid)。
    默认用 service.McpBackend(与 ``migloop serve`` 共用账本缓存);别的宿主注入自己的服务层。"""
    from mcp.server.fastmcp import FastMCP

    srv = FastMCP("migloop-atoms",
                  instructions="MigLoop 两原子(版本文件 × 版本 agent)归因工具。先调 guide 读指南,"
                               "再从 sessions(sid) 的返修链出发。")

    def _be() -> Any:
        return backend if backend is not None else _rt()

    async def _ctx(sid: str) -> tuple[Any, str]:
        rt = _be()
        return await rt.get_ledger(sid), await rt.get_session_cwd(sid)

    @srv.tool()
    def guide() -> str:
        """两原子模型、标签含义、建议的调查路径与结论要求。第一次用之前先读。"""
        return GUIDE

    @srv.tool()
    async def sessions(sid: str, file: str | None = None) -> str:
        """返修链总览:被修文件 × 修复方、被修行数与 ★ 原作者、修因、跨会话接力。sid = 会话 id 或 8 位前缀。
        file 给了(文件名 / 相对路径)只回那条链 —— 查一条链就带 file,别把全部链拉回来。"""
        rt = _be()
        payload = await rt.get_fixchain(sid)
        cwd = await rt.get_session_cwd(sid)
        return atoms_text.render_chains(payload, root=cwd, file=file)

    @srv.tool()
    async def index(sid: str, kind: str | None = None, query: str | None = None,
                    limit: int = 0) -> str:
        """账本目录:agent 与文件各一行。kind = agent | ets | spec | src | other(空=全部);query 子串过滤。
        不带 query 只给前 80 条(大会话有两百多个 agent,整张表就是三万字),带 query 给到 300。"""
        ledger, cwd = await _ctx(sid)
        return atoms_text.render_index(ledger, kind, query, root=cwd, limit=limit or (300 if query else 80))

    @srv.tool()
    async def file(sid: str, path: str, v: int | None = None, content: bool = False,
                   diff: bool = False, start: int | None = None, n: int | None = None,
                   readers: bool = False, v_from: int | None = None, v_to: int | None = None,
                   diff_chars: int | None = None) -> str:
        """版本文件原子:≤v 的写者脊柱(写者 agent 版本/来路)、读了这一版的 agent、复原全文。
        path 可给文件名、相对路径或绝对路径;v 空 = 最新版;content=True 给全文(start/n 裁行窗口)。
        三种口径:不带 diff = 索引;diff=True 带 v = 只看第 v 版的 diff;diff=True 不带 v = 每版完整 diff,一页 40 版,
        v_from / v_to 翻页(创建版只给行数;diff_chars 只在你明确给时才截)。"""
        ledger, cwd = await _ctx(sid)
        return atoms_text.render_file(ledger, path, v, root=cwd, content=content, diff=diff,
                                      start=start, n=n, readers=readers, v_from=v_from, v_to=v_to,
                                      diff_chars=diff_chars)

    @srv.tool()
    async def agent(sid: str, id: str, v: int | None = None, since: int | None = None,
                    reads: bool = True, seen: bool = False) -> str:
        """版本 agent 原子(索引):身份、派发者与派发词全文、收件箱一行一条、≤v 逐版的效应与输入
        (读按调用合行,绑文件版本,▲旧版/行段/命中行号/写前读等标)、它中途说的话一行一条、收尾输出。
        每条记录带 (#n@L行):action(id, n) 展开原文。id 可带或不带 agent- 前缀,名字唯一也认;
        v 空 = 整个生命周期;since 给了只看 (since, v] 这段版本 —— 主会话动辄几百次调用,查它必须带窗口。
        seen=True 把命中读看见的原文行铺出来;reads=False 只给每版读的条数。"""
        ledger, cwd = await _ctx(sid)
        return atoms_text.render_agent(ledger, id, v, root=cwd, since=since, reads=reads, seen=seen)

    @srv.tool()
    async def blame(sid: str, path: str, v: int | None = None, start: int | None = None,
                    n: int | None = None, changed: bool = False) -> str:
        """逐行归属:文件@v 每一行是谁在哪一版写的(确定性逐行签名)。start/n 裁窗口,汇总按全文。
        changed=True 把 v 当修复版:只给它替换/删除掉的前一版那些行及其引入者(owner@since_v)和新增行数
        —— 定位被修行的来源用这个,不必整文件 blame。"""
        ledger, cwd = await _ctx(sid)
        return atoms_text.render_blame(ledger, path, v, start, n, root=cwd, changed=changed)

    @srv.tool()
    async def diff(sid: str, path: str, v: int) -> str:
        """某一版的 unified diff(相对前一已知版)。"""
        ledger, cwd = await _ctx(sid)
        return atoms_text.render_diff(ledger, path, v, root=cwd)

    @srv.tool()
    async def search(sid: str, q: str, agent: str | None = None, v: int | None = None,
                     since: int | None = None, file: str | None = None, after: bool = False,
                     since_ts: str | None = None, until_ts: str | None = None) -> str:
        """带起点的按词查找。agent=(id 或名字)+ v / since:只看它喂养第 v 版及之前的记录(派发词、读到的内容、
        写入、命令与结果、自述、收件、注入技能),命中按种类分组、带 (#n@L行) 与下一跳;锚点之后的只计数(after=True 才列)。
        since_ts / until_ts:按时间区间查派发者(用文件时间线上两个版本的时刻)。file=(+ v):这个词首次出现在第几版、
        谁写的,哪些读者的读结果命中过。不带 agent / file 时必须带 until_ts:全池查那一刻之前所有 agent 的记录与
        所有文件的已知内容,只用来核否定(「生成期没人见过 X」),结果自带范围行。每次输出第二行都是「范围」,零命中只能按它写。"""
        ledger, cwd = await _ctx(sid)
        return atoms_text.render_search(ledger, q, agent=agent, v=v, since=since, file=file, after=after,
                                        since_ts=since_ts, until_ts=until_ts, root=cwd)

    @srv.tool()
    async def action(sid: str, id: str, seq: int, max_chars: int = 20000, offset: int = 0, find: str = "") -> str:
        """展开 agent 某一次工具调用的完整原始输入与输出(agent 工具时间线里的 #n 就是 seq)。
        账本是实录的索引,任何摘要不够看时用它拿原文,信息不会丢。输出超过 max_chars 会截断并说明剩余多少:
        offset= 从第几字继续,find= 直接跳到关键词前(长 think 里找决策句用它,别拿 search 撞)。"""
        ledger, _cwd = await _ctx(sid)
        return atoms_text.render_action(ledger, id, seq, max_chars=max_chars, offset=offset, find=find)

    return srv


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
