"""Progressively disclosed guidance shared by MCP and HTTP."""

from __future__ import annotations

GUIDE = """\
# MigLoop 两原子归因指南

你在分析一次 Android→HarmonyOS 自动迁移的完整实录。实录已被整理成一本账,账上只有两种原子:

- **版本文件** file(path, v):文件的第 v 版。工具给你 ≤v 的全部写者(每版是哪个 agent 在它自己的
  第几版写的、diff、来路)、读了这一版的 agent(下游)、以及这一版的复原全文(复原不了会说明原因)。
- **版本 agent** agent(id, v):一个 agent 的第 v 版 = 它做出第 v 个对外效应(写文件 / 删文件 /
  派发子 agent / 发消息)之后的状态。工具给你派发它的人与派发词全文、收件箱、≤v 的全部读取
  (每条绑定读到的是文件第几版)、产出、收尾输出。**v 之后不能算该次写入时已有的输入,本窗口已截掉。**
  后续修复、反证和验证仍可调查:另选后置 agent 版本/时间窗口,不要把“当前窗口没返回”说成“后来没有验证”。

两原子互相以 (path, v) / (agent id, v) 引用。人和你走的是同一张图。

## 标签的含义(标签是证据,不是裁决)
- ▲旧版 a/b:读的时候绑到第 a 版,但这条读喂养的那笔写发生时文件已是第 b 版 —— "读旧版"候选
- 行段 (x-y行):记录显示读了这些行;是否全文以 full / seen / 内容未知标签为准,没标范围不自动等于全文
- 同 agent 也写过:这个 agent 生命周期中也写过同一路径;只说明路径重合,不证明读写顺序或这次读取的目的
- 依赖读:cp 源 / < 输入,内容没进上下文
- 脚本读 / 脚本落盘:仅受支持的脚本语义与执行证据可入账;单凭路径字面量只是提及,控制流/执行未知是候选
- 外部输入:第一次出现就是被读,没人写过(安卓源码、spec 参考、模板)—— 树的叶子
- 实录外修改:内容变了但没有记录在案的写(脚本动态目标 / 构建工具 / 人手)
- 版本就近绑定(不确定):读发生在文件状态未知时,版本号是就近猜的
- 读取窗口与写入重叠:保留返回原文,但无法确定快照属于哪一版;返回时间只证明此时可用,不证明此时才取样
- 消息主张:父转录收到的子代理/reviewer 报告可以核回原文,不替代缺失的子转录、实际补丁或行为验证

## 原文入口与已知边界
file 原子末尾的「碰过它、方向不明的调用」与 sessions 末尾的「修复期被脚本碰过、方向不明的工程文件」:脚本里出现了
这个路径但账本判不出是读是写(既读又写 / 数据表),不立版本、不猜方向,只给动作号 —— action(id, n) 展开原文自己判。
被修的真文件可能只在这里露面(0723 修复真正改错值的 F012ViewModel.ets 就是修复方用 python heredoc 改的)。
file 原子末尾还有「提到它的命令」:命令行 / heredoc 体 / 跑的脚本正文 / 工具输出里出现这个路径的每一条命令,不论账本有没有解出读写
(这是词法候选索引,不是全转录完备证明)。版本查询默认 m_n=0 只列计数与展开查法;需查看时显式 m_n=40。
已入账的折成计数;没记到的按分档逐条列 —— 改动类(cp / sed -i / git checkout /
脚本运行 / 重定向目标)、正文提到(heredoc、脚本正文)、输出里(git status、构建报错点名)、其他;只读检查(cat / grep / wc / ls)
默认折叠,m_all=1 铺;一页 40 条,m_from 翻页。每条标它落在哪一版的窗口。版本行上「窗口内提及 N 条」指向这一节;
「窗口内有写能力的命令 N 条(全池)」给的是 search(q='', kind=write, since_ts, until_ts) 的查法 —— 内容未知 / 实录外修改
的版本,谁可能改的先按时间圈这些候选,再 action 打开判。agent 槽里解不出效应的命令直接带「可能碰了 X@v」;
从一条命令进来只想看它之前的输入,用 agent(id, v, until=#n)。
agent 工具给的每条动作/读取后面的 (#n) 是动作号;action(id, n) 返回那次工具调用的完整原始输入与输出
(命令原文、grep 命中、cat 出来的全文、Read 到的内容)。摘要看不清时直接展开,不要猜。
推荐直接 action(ref="#转录标识:n@L行[/块]") 照抄完整引用，无需另猜 agent id；ref 与 id/seq 二选一。
转录标识不是 agent id，确需 id 时复制输出的 id= 字段。action 默认同时给输入和输出，短调用无需分两次；只有按侧定位或翻页时才选 part。
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
窗口的“早期输入索引”只提示被省略的已有记录,不证明相关性;按需展开。reads 默认自动折叠大 agent 的读清单,
reads=True 显式铺开索引,seen=True 再展开看见的片段,原始全文仍从 action 获取。

## search:带起点的按词查找
`search(sid, q, agent=id或名字, v=, since=)` 只在这个 agent 喂养第 v 版及之前的记录里找:派发词、读到的内容、写入内容、
命令与结果、它自己说的话、收件、注入的技能。命中按种类分组,每条带 (#n@L行)、喂哪一版、下一跳(file / diff / action)。
锚点之后的命中只计数,不混进因果;范围内零命中只能支持“在这个范围里未检索到”。派发者后来说的话用 since_ts / until_ts
(文件时间线上两个版本的时刻)做区间。`search(sid, q, file=path, v=)` 查这个词第一次出现在第几版、谁写的,以及哪些
读者的读结果里命中过。提到过一个词不等于在这条链的上游;检索得到的新线索可以调查,但不能把探索跳转直接写成因果边。
每次 search 的输出第二行是「范围」:agent 模式只含这个 agent 的记录,file 模式只含该文件已知内容。**零命中只能按那一行的范围写**。
要写「生成期没人见过 X」这种否定,用 `search(sid, q, until_ts=生成写入的时刻)` 全池查:范围 = 那一刻之前所有 agent 的记录 +
所有文件的已知内容(内容未知的版本数会写出来),结果自带范围行,报告里把它抄上。全池查也可发现候选来源,
有命中后核对语义、时刻和实际传递关系;无关命中不强迫继续走,零命中不证明需求不存在。
报告里引用坐标整体照抄工具给的 (#转录标识:n@L行):标识在前,是坐标的一部分,截掉就核不回去;#n 是本次建账的动作号,
账本重建后会变,标识 + 行不变,核验按它。截短的引用按无效算。

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
   (search(q=文件名, agent=主会话, v=))、占位登记里有没有它(search(q=, file=placeholder-registry.md));三问全否只支持已查范围未发现指派。
   修复轮没动的文件(sessions 里没有它的链)不等于修复侧没看到它:缺陷单可能点了它却把落点路由到别的文件。
   用 search(q=文件名, since_ts=修复开始时刻, until_ts=结束) 全池查修复期谁提到过它,再 file(那张单, content=1) 看正文。
2. diff(path, v_fix) 看修复到底改了什么;blame(path, v_fix, changed=True) 直接列出修复版替换/删除的
   那些行及其引入者(owner@since_v)—— 不必对整个文件做 blame。某一行是谁写的用 blame(path, v, start=行号, n=1)。
   file(path, v) 是这一版的视图:脊柱截到 ≤v(要看全部版本就开最后一版);file(path, v, diff=1) 或 diff(path, v) 看某一版改动;
   file(path, v, diff=1, v_from=, v_to=) 区间每版完整 diff,一页 40 版 —— 问「一个文件为什么被改了几十次」才用它。
3. agent(owner_id, since_v) 看引入者写那一版时手里有什么:派发词、读过哪些 spec/源码(版本、
   行段、是否旧版)、收件箱有没有改指令。对比修复方 agent 的读取集,找"该读没读"。
4. 顺着 file(读到的 spec@v) 往上游走,直到找到最早出问题的环节。

## 结论要求
正式产出用下面的结构化结论,无需再逐环写一份同义散文。可加不超过一小段的中文摘要。
nodes 只收该项问题段与判定所必需的证据边界;正常上游一句即可。其余查过的节点会自动由调用轨迹展示,
不必为了画图把所有查询再写成结论,也不必为每个修复前后坐标重读一遍全文。索引打开与正文查看是不同范围,据实记录。
每条缺陷分别解释生成行为、当时适用的要求、后续修改和依据;一个节点只总结它在这条缺陷中的具体作用。
以修复前相关代码的引入者为上溯起点,不要只找文件最初创建者;整页重写可能改变责任和实际输入,用 blame(changed=True) 核对。
标“进入·错”之前,必须实际打开与该缺陷有关的输入原文/片段及生成实现,证明要求在当时适用且未满足;
不要求把所有上游全文读完,也不能因只打开文件索引就声称核完输入。
输入里未找到要求时,先在生成写入之前的时间范围搜索相关表述与同义概念;有相关命中则核对来源/传递,
没有则写“已知范围未检索到”,披露未知内容和搜索范围,不要推出“池子里不存在该需求”。
追到后来首次观测到该要求时,区分后续新增要求、测试插桩/质量门禁扩展、已有要求漏传、证据不足。
后续新增不自动是生成 agent 的错误;每份输入也不是天然都应包含这项要求,不得把输入全标成缺。
找到局部错误且依据充分可以停止该支上溯;无法确认则保留边界。批量生成/池外仅是边界,不是正确性证明。
引用更多、打开更深不等于更准确。优先覆盖实际修复事项,明确未解释项,不为凑链而加节点或归罪。
reviewer 的 wrong_edit/PASS 只证明它作过该判断;没有对应实现/运行证据就用“无法确认”。报告文件不会因为写着错误判词就成为故障进入点。
先用正向证据说明要求何时被派发、实际改了什么。已查明后续新增要求且没有更早适用依据时,可以写“未确认早期义务”并停止该支;
不必为了认证不存在而反复枚举关键词。标题优先写可观测变化,例如“测试阶段加入参数桥”,不把检索边界藏在“非生成遗漏”这类绝对标题后。
纯新增代码不证明没有行为回归;端点文本无差异也不证明期间没有写入或修改后还原。没有相应测试证据时,不要写“不影响原有逻辑”。
没有展开后续读者/构建者的记录时,只能写“尚未核验”,不能写“不存在后置验证”;概括时也不要把“我没读到”改成“没有”。
凡是写「没有 / 零命中 / 从没读过 / 无人」,后面必须跟工具输出的「范围」行(哪些 agent、哪些文件、到哪一刻、内容未知几版);
没有全池 until_ts 查询撑腰的,只能写成「X 在这个范围内未检索到」。
出现「提及索引不完备」时,先 index(kind=scan) 查缺口,再 action(part=input/output, offset=…/find=…) 看原文。
即使全池零命中也不证明没人见过:查询范围、未知内容、加密/缺失记录和扫描缺口都必须披露。
条件/失败调用的路径是候选,不代表实际写过或读到过;候选写后的观测重锚不证明发生了实录外修改。
账本未复原出文件版本不等于原文没有效应证据:展开候选的命令/脚本、执行结果及可用的前后内容,
分别说明能确认的目标、分支和值与仍未知的归属/版本。成功状态本身也不证明所有分支执行或行为修好。
批量汇总的总数不证明每个目标采用相同值;核对分支、例外、已存在而跳过的站点,不要把中间态当最终态。
边界:账本里只有**被读过**的安卓源码,从没人读过的文件不存在;标签是线索,盲写/脚本落盘的
版本内容可能未知,如实说"无法确认"。

## 位置与来处(via):记录你声明的探索路线
节点只有两种,都带版本:file(path, v) 打开的 file@vN,agent(id, v) 打开的 agent@vK。v 必填 —— 被修文件的版本号看 sessions 摘要,
写者的版本号看文件脊柱那一行(`v8 ← fix-errobserver v1` 就是 agent(fix-errobserver, v=1)),文件的版本号看 agent 时间线里的读写行。
- file / agent 是移动:必须带 via=你现在站的节点,逐字等于你打开过的某个节点:`file:<路径>@vN` / `agent:<id>@vK`,后面可以跟几个字
  说凭哪一行(例:`file:entry/…/EntryAbility.ets@v8 写者`)。不带版本、没打开过、版本对不上,调用都不执行,会回给你已打开的列表。
- 第一次 file / agent 写 via=sessions(从返修链摘要进被修文件或修复方),之后不能再用。目标没有文件版本时,
  可从 index/search 找到真实 agent@v,首次用 via=task 或搜索凭据进入;不为进入页面而捏造文件版本。
- blame / diff / action / search 不移动、不开节点、不带 via。search 是调查事件,不是第三种原子。
  search 返回末尾 hits 中的 via=search:<凭据>:<命中号> 可直接打开该命中的精确 kind/key/v,无需强挂已打开节点。
  凭据必须照抄本次真实返回,不能自造 search# 或换目标/版本;旧搜索无凭据仍可阅读,不能直接充当 via。
  命中只证明限定范围内发现了文本,不证明历史 agent 读过、版本确定或存在因果关系。
- 页面保留每次访问与 via 转移,包括重复回访和自环;实体可以合并显示,步骤不能省略。账本关系另行核验。
  via 是你明确声明的导航来源,不是系统推测你的私有思路。失败/未完成/返回坐标不符的调用不算成功打开。
  v 是实际查询锚点;区间 diff 的 v_from/v_to 只能在该锚点内,不能靠窗口偷偷换版本。

## 结构化结论(正式产出,页面靠它给节点着色、展示原因和证据)
另起一个 ```yaml 围栏块,严格按这个格式(未知键、词表外的词、缺版本号都载入失败):
reason / boundary / notes 等自由文本必须用 YAML 块字符串 `|-` 换行缩进,不能把反引号开头的代码或含冒号文本直接放在冒号后;坐标和 evidence 用引号包围。
```yaml
schema: migloop-verdict/1
ledger: <照抄 sessions 输出首行「账本身份:」后面那一串>
root: file:<被修文件的账本路径>@v<最终版本(账本里最后一版)>
defects:
  - id: A                                   # 一条缺陷一项;几条不相干的缺陷分开列,可共享节点
    title: <简短中文问题短语>
    repair: {before: file:<路径>@v<修复前版本>, after: file:<路径>@v<修复后版本>, evidence: ["#标识:n@L行"]}
    entry: [agent:<账本 id>@v<K>]           # 故障进入点;可以不止一个,查不出就留空列表
    boundary: |-
      <停在哪、为什么:池外输入 / 批量生成 / 停止追溯;不停可省>
    nodes:                                  # 展示顺序;相邻两项不代表因果
      - node: file:<账本路径>@v<N>            # 或 agent:<账本 id>@v<K>;坐标照抄工具输出,版本必填
        role: 正常                            # 正常 / 带病传递 / 进入·错 / 进入·缺 / 无法确认
        reason: |-
          <一到三句>
        evidence: ["#标识:n@L行", "file:<路径>@v<N>"]
        # 标红时填写 basis；正常/无法确认无需强填，不为凑字段编造依据。
        basis:
          expected: |-
            <当时适用的要求或应保持的行为>
          expected_evidence: ["#标识:n@L行"]
          actual: |-
            <此节点实际输出与要求的具体差异，不是仅说它参与了修复>
          actual_evidence: ["#标识:n@L行"]
          counterevidence: |-
            <核过哪些反证；是否只是发现/正确修复；仍有哪些未知>
    edges:                                  # 可省;每条对应账本里的一条 写 / 读 / 派发 边;拿不准写 候选 或 省略
      - {from: agent:<id>@v<K>, to: file:<路径>@v<N>, relation: 写}
coverage:                                   # sessions(file=目标) 清单的每个版本与候选各一项,不能用区间冒充逐项覆盖
  - node: file:<路径>@v<N>
    status: explained                       # explained / unresolved / out_of_scope / not_repair
    defects: [A]                            # 对应上面的缺陷 id;未确认或不算修复时可为空
    reason: |-
      <此版本具体改了什么、归到哪项或为什么尚不能解释>
    evidence: ["#标识:n@L行"]
  - candidate: candidate:<清单里的20位摘要>   # 与 node 二选一;候选不是文件版本,不可自造版本/作者
    status: unresolved                      # 本题未调查=out_of_scope;已核非修复=not_repair;确认修复=explained
    defects: []
    reason: |-
      <核过哪些原文、真实目标/效应是什么或仍缺什么证据>
    evidence: ["#标识:n@L行"]
notes: |-
  <可选备注>
```
角色的意思:正常 = 对本项有依据地提供正确输入、发现问题或正确修复(reason 简述依据;没查过的上游不用列);带病传递 = 保留了上游缺陷并传给下游(说保留了什么、
怎么传的;不等于失职,失职要另有证据);进入·错 = 此节点产生或重新引入错误输出(说当时正确输入/要求与错误输出的落差，不是只描述做了什么);
进入·缺 = 输入里本来就没有;无法确认 = 内容未知或证据不够 —— 不为了把进入点推给下游而宣布上游正常。
角色必须与 reason 一致:后续新增能力的扩展对象不自动是“带病传递”,不要标红后再用文字说它其实没有已确认缺陷。
“正常”只针对本项已核对的输入/义务,不是整个节点功能已验证;尚无法判定该项义务或输入是否正确时用“无法确认”。
文件坐标用 file() / sessions 打印的路径,agent 坐标用 agent() / index 打印的 id(主会话是 __main__:<会话号前 8 位>);
修复后的版本放 repair.after，可在 nodes 以正常/无法确认说明验证边界，不能就同一缺陷标带病;修复后是否仍有其他问题另起一条缺陷或写在 notes。
ledger 必须照抄本次 sessions 的身份。身份缺失/冲突时历史主张保留,但不能重新绑定到当前账本的同号版本。
evidence 有效仅表示能定位;节点的 reason 仍是你的主张。无法核实就写无法确认,不能自报“已机检”替代验证。
输出前核自洽:entry 只列“进入·错/进入·缺”的故障引入节点，不是问题的发现点或正确修复点；修复者若制造新错误可成为那条新缺陷的进入点。没有确证进入点用 []。
repair.before/after 必须是本项实际变化的可核版本,不能借相邻版本当时间窗口,不能 before=after;缺版本就省略对应字段或整个 repair。
coverage 仅保证清单逐项有交代,unresolved 不等于已查清;不能为了交齐把所有候选直接宣称无关或已修复。
coverage 只抄 sessions 清单真实条目;没有对应清单就用 [],将未知放 nodes/notes,不得自造 candidate 或把别的报告文件版本当目标修复清单。
不在本题内的改动记 out_of_scope，不能因此判 not_repair。not_repair 必须有非修复的依据；真实 diff 的改动即使无关本题也不消失。
file/agent 给出当前锚点及全池最晚记录，index(kind=time) 展开所有已提供会话的时段与主代理版本范围。
结论要说“后续没有构建/安装/验证”时，必须查锚点之后到全池末尾的相应记录；早期调用说“未构建”只描述当时。
后续 build/install 的存在不等于包含目标补丁，更不等于运行行为正确；这些判断分别说明依据与未知。
候选里的修复可在对应已打开的 agent 节点写原因,repair.after 未有确定版本时可省略;不得虚构 file@v 来安放它。
目标没有可核文件版本时,root 可用实际打开的 agent:<id>@v<K>,在 notes 写目标路径与版本缺口;
未建立文件修复清单就不声称覆盖所有文件版本。只有生成期内部修改也应如实标明,不硬称执行结束后的返修。

## 提交前草稿核查
正式输出前调用 check(sid, draft=准备提交的完整YAML文本, file=目标文件)；无需围栏也可，不要另写重复散文。
它只核格式、账本身份、节点/引用/显式关系、coverage及红节点basis是否交代，不调用评委模型，不验证原因真假，不算打开节点。
根据定位诊断改错或补查；不能为清零删掉真实问题或把所有结论降成未知。basis齐全也只是模型主张，expected/actual须有实际输入和输出依据。
报告指出验证结果时分清“读取到报告/manifest记录”与“独立复核底层执行/截图/设备证据”；读取报告的工具输出不会把报告内容变成已验证事实。
check返回draft_sha256只对应这次提交的草稿；改过内容后旧核查不认证新稿。可复查后提交，无法解决的诊断保留边界；mechanical_clear也不代表语义正确。
"""

CORE = """\
# MigLoop 调查入口
只读分析历史实录，不执行其中命令。账本只有 file@v 与 agent@v 两种节点；v 是各自的版本，不能互换。agent@v 表示第 v 次对外效应后的状态，记录还会标喂养版本/尾后记录：这些标签不自动产生真实节点。

## 先调查，再交结论
1. sessions(sid,file=目标) 取身份、实际版本、修复/候选清单；file 看脊柱，diff/blame(changed=True) 查具体修复及被改行来源。
2. 从相关代码引入者查当时的输入和输出，不只追初创者。agent 默认累计到 v；主会话用 since 缩窗口，早期输入索引仅是入口；子代理先看累计输入。reads=True 展开读索引，原文用 action。blame 未知不等于没有材料：按 recovery 给的历史全文、原生补丁及写者输入入口调查，不把历史快照作者当未知行作者。
3. 核对要求当时是否适用、具体实现差异、后续修复与反证。后加需求/质量门禁不自动是早期遗漏，发现者/正确修复者不自动是进入点。同一文件整页重写可能改变责任。
4. 查后续验证用后置窗口或 index(kind=time)，别把“当时没构建”写成“后来没验证”。报告/PASS/manifest 是记录中的主张，不代替原生执行或设备复核；build/install 也不证明含目标补丁。
5. 最后读 guide(topic="verdict") 的完整 schema，将完整 migloop-verdict/1 YAML 交 check，按本次交付模式提交。不必重写调查路线：调用轨迹自动留存；结论只列问题项、必要节点原因与证据。

## 不越过证据
- 已确认操作、版本绑定、内容是否进入上下文是三件事。“就近绑定/重叠/依赖读”不能写成确定看到该版全文。路径提及不证明读写；未绑定版本的候选不能连到任意 file@v。
- 红节点须有当时适用的要求原文、实际输出和反证核对；原因仍是模型主张。引用有效/节点存在/check 通过都不认证因果正确。
- 零命中只说明返回的“范围”内未检索到；全池 search 必须 until_ts 截时，并披露未知内容/扫描缺口。正向证据足够可停止该支，不必反复证明不存在。
- 原文缺失可保留未知，但不能忽略已有可核材料。批量操作要查分支、跳过例外和最终状态，总数不证明每个目标值一致。成功退出不证明所有分支执行。
- coverage 是清单逐项交代，不是逐项已解释；无关本题用 out_of_scope，not_repair 须有非修复依据。

## 导航与展开
file/agent 必填真实 v 和 via：照抄已成功打开的 file:<路径>@vN / agent:<id>@vK；首次可 via=sessions，无文件版本可由真实 agent 进入。search 的精确 hits 凭据可独立进入发现的节点。via 记录导航，不创建历史读写边；无关系的查阅也保留为查阅。
action/diff/blame/search 不移动；action 优先 ref=照抄完整原文引用（与id/seq二选一），转录标识不是agentID，agent查询复制 id= 字段。
action 默认同时给输入和输出，短调用无需拆两次；find/offset 仅作用于所选 part，Write 正文或命令要 part=input，返回原文用 part=output。不要对输出搜写入正文。
默认只给索引/计数，content、reads、seen、m_n、分页按需展开；摘要不是全文。已打开的同一来源上的独立查询可以并行，但不能抢先使用尚未返回的 via/坐标。
详细帮助按需 guide(topic=...)：evidence 证据与原文边界；search 查询范围；investigation 归因准则；navigation 路线；verdict 完整结论/check；full 全部原指南。
"""

REFERENCE_DELIVERY = """

## 本次最终交付模式：显式引用已核草稿
上面的 migloop-verdict/1 仍是完整结论格式，必须作为 check 的 draft 参数提交；调查、理由、证据和覆盖要求全部不变。
最终回复不要再重写一遍完整 YAML，只输出下面的小块（可附一小段摘要），三个值逐字照抄最后一次 check 返回：
```yaml
schema: migloop-verdict-ref/1
ledger: <本次账本身份>
draft_sha256: <最后一次 check 的 draft_sha256>
document_sha256: <同一次 check 的 document_sha256>
```
系统只从本次录制的最后一次真实 check 取回你实际提交过的原文，并核对双哈希；没有对应调用、缺失/截断返回或不匹配就载入失败。
要改任何结论，先将完整新稿再交 check，再引用新的哈希。needs_review 可以提交，未解诊断会保留；不能删真实问题来清零。
这个小块不代替完整草稿，也不证明原因正确。不要自算或猜哈希，不要引用另一次运行。
"""

# The original reference remains available verbatim. Topics are views of it,
# not a second hand-maintained schema or a weaker evidence contract.
_TOPIC_HEADINGS = {
    "evidence": ("标签的含义", "原文入口与已知边界"),
    "search": ("search:",),
    "investigation": ("建议的调查路径", "结论要求"),
    "navigation": ("位置与来处",),
    "verdict": ("结构化结论", "提交前草稿核查"),
}
TOPICS = ("core", *_TOPIC_HEADINGS, "full")


def _reference_topic(topic: str) -> str:
    if topic == "full":
        return GUIDE
    blocks = GUIDE.split("\n## ")[1:]
    selected = [block for block in blocks
                if any(block.startswith(prefix) for prefix in _TOPIC_HEADINGS[topic])]
    if len(selected) != len(_TOPIC_HEADINGS[topic]):
        raise RuntimeError("guide topic headings no longer match the reference")
    return "\n\n".join("## " + block.rstrip() for block in selected) + "\n"


def verdict_version() -> str:
    import os
    version = os.environ.get("MIGLOOP_VERDICT_VERSION", "2")
    if version not in ("1", "2"):
        raise ValueError("MIGLOOP_VERDICT_VERSION must be 1 or 2")
    return version


def guide_text(final_mode: str | None = None, topic: str = "core") -> str:
    """Short default entry; full evidence rules and schema expand on demand."""
    import os
    mode = final_mode if final_mode is not None else os.environ.get("MIGLOOP_FINAL_MODE", "document")
    if mode not in ("document", "reference"):
        raise ValueError("MIGLOOP_FINAL_MODE must be document or reference")
    if not isinstance(topic, str) or topic not in TOPICS:
        raise ValueError("guide topic must be one of: " + ", ".join(TOPICS))
    text = CORE if topic == "core" else _reference_topic(topic)
    version = verdict_version()
    if version == "2":
        from .guidance_v2 import VERDICT, CORE_ADDENDUM
        if topic == "core":
            text = text.replace("migloop-verdict/1", "migloop-verdict/2") + CORE_ADDENDUM
        elif topic == "verdict":
            text = VERDICT
        elif topic == "full":
            text = GUIDE.split("\n## 结构化结论", 1)[0] + "\n\n" + VERDICT
    if topic == "core":
        delivery = ("本次最终交付：document。check 后原样提交完整 YAML；改过须重新 check。"
                    if mode == "document" else
                    "本次最终交付：reference。完整 YAML 仍须交 check；最终只交 migloop-verdict-ref/1，"
                    "照抄最后一次 check 的 ledger、draft_sha256、document_sha256；改稿先重查。"
                    "完整模板见 guide(topic=verdict)。")
        return text + "\n\n" + delivery + "\n"
    if mode == "reference" and topic in ("verdict", "full"):
        text += REFERENCE_DELIVERY.replace("migloop-verdict/1", "migloop-verdict/" + version)
    return text
