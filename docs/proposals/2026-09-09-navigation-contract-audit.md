# 调查导航与读写证据图契约审查

基线：`6ffb74c`，2026-09-09。最初只读审查 UI / MCP / via / probe 及关系判定调用链；审查阶段未改生产代码、运行模型或改写旧 run。使用代码探索技能列出 GitNexus 仓库后确认 migloop 未索引，本次直接读源码，没有建立新索引。以下区分“已经实现的行为”“当前风险”和“建议契约”；后续获准的第一阶段实现单列于末尾。

## 结论

不应把“检测器没有找到关系”变成调查访问的拒绝条件，也不应把“调查员能从此处打开彼处”变成读写关系。访问许可、调查来处、关系主张、原文定位、关系方向必须独立。

保留两个原子：真实存在的 `file(path, v)` 与 `agent(id, v)`。搜索、动作原文、草稿核查和派发事件不是第三种原子。主图画读写证据，时间线保留全部查询导航；纯搜索、无关探索、分页与同节点回访不产生主图节点间关系线。

## 已核实的代码路径

| 路径 | 当前实际行为 | 风险与边界 |
| --- | --- | --- |
| `via.py:249–278`；`mcp_server.py:315–326,343–352` | 普通 via 只查 source 是否在 `opened`；destination 只在搜索凭据分支参与比较。MCP 另验真实目的版本和返回头。 | 这是来源/访问校验，不是读写认证。不能把允许访问当“存在关系”；也不建议在这里新增“无账本边就拒绝”。 |
| `via.py:211–233`；MCP file/agent 参数 | via 的尾随说明原样保存，但解析只取首个坐标；没有独立的关系种类、方向、原文证据或多跳路径字段。 | “因为这里读/写了那里”的模型主张无法独立留档，更无法与纯探索区分。不能从尾随散文猜关系。 |
| `probe.py:1030–1095` | 两个方向分别 `check_edge`，按 true/unknown/false 取最优一条；输出 `causal_from/to`。 | 保留了一个关系方向，但不能表达同一对节点同时有多种关系；可能选择的并不是调查员所声称的那种关系。 |
| `fixchain.html:1977–1983,2293–2338` | 转移复制 query from/to，没有复制 causal 端点；所有转移按 query from/to 画箭头。 | 从 agent 回查输入文件时，蓝色“读”箭头仍是 agent→file；它不是数据方向 file→agent。仅加 tooltip 不能消除主图关系歧义。 |
| `verdict.py:502–542`；`probe.py:1075–1095`；UI `relation_status===unknown` | `_candidate` 接受任意词法 mention，含 `cls=out`，归为 unknown；UI 与真正不确定读取共用候选连线样式。 | “只在文字中提到路径”不是 uncertain read/write。原始出处虽可查，仍不能升级为可能执行了读写的主图边。 |
| `probe.py:1233–1253`；`fixchain.html:2298–2311` | search 转移 `from=None`，UI 创建几何虚拟起点并画箭头；同节点查询也产生 route，自环实际绘制。 | 搜索命中可以成为导航事件，不应在读写主图引入一条关系线；同节点翻页也不是自身读写边。 |
| `probe.py:785–809`；UI `ledgerNeighbors` | “未查上游”只枚举确定读取与派发；不确定读取/依赖等在其它渲染入口采用不同规则。 | “0 未查上游”不能表示没有未核的关系线索。关系发现、关系分级与展开规则分散，容易出现导航可行但主图/计数遗漏。 |
| `atoms.py:283–318` → `verdict.py:_rel_dispatch` → `probe.py:_relation_check` | `_link_dispatches` 可按 prompt 全文、前 120 字或 id 前缀的首个候选 adopt；父/版本字段随后被当作 true 派发关系使用，未保留匹配强弱。 | 派发关系也要保留原始记录/推配来源，尤其不能把推配的 parent 字段统称确定事实。组织/派发关系应独立于读写层。 |
| `probe.py:_trajectory_ledger` 的版本连接与 BFS | 老格式在已显示版本之间补 `前一版`，可能携带 skipped>0；首访 parent 或 BFS parent 同时承担布局。 | 在场 v1→v5 并不等于真实相邻版本。布局 parent、压缩历史与读写关系不能共用一条语义边。 |

### 无文件写入的最小复现

用内存 `Ledger`：外部文件 `/proj/input.md@1`，agent-r 的 Read 喂养其 v1，另一个效应使 v1 实际存在。

```text
_relation_check(agent-r@1, input.md@1):
  query direction = agent-r@1 -> input.md@1
  relation_status = true, relation_kind = 读
  causal_from = file:/proj/input.md@1
  causal_to   = agent:agent-r@1

把 ref.certain 改为 False：_upstream_neighbors(agent-r@1) = []。
移除 ref，仅保留 cls=out 的 Mention：
  relation_status = unknown, relation_kind = 候选
  relation_label = 候选·仅词法提及, causal_from = None。

via.check 对已打开 agent-r@1 返回允许，不要求 source/destination 有读写边。
via.parse("agent:agent-r@v1 read evidence=#source:3@L4")
  仅解析 agent-r@v1；尾随 read/evidence 不是结构化关系主张。
```

现有 `tests/test_trajectory.py:206` 明确把同节点自环纳入 transitions；其 `test_route_keeps_read_uncertainty_and_candidate_evidence` 同时接受 certain / uncertain / dependency / conditional / overlap / mention，证明这些是当前有意兼容的旧合同，不应悄悄篡改历史记录来迁就新图。

## 建议的独立字段契约

下面是概念契约，实际 MCP 参数命名由统一 query 层收敛。保留旧 `via` 原文，不让解析器从自然语言补事实。

| 字段 | 唯一含义 | 不得推导的结论 |
| --- | --- | --- |
| `source` | 本次调查从哪个已返回的节点访问、搜索事件、动作上下文或任务入口发起；附来源调用/原文定位 | 不等于历史数据生产者，不一定是最近一次打开的节点 |
| `destination` | 本次请求及实际返回的精确两原子坐标；两者分别保存 | 请求了不等于打开了，原文提及不等于版本已存在 |
| `navigation_direction` | 调查 source→destination | 不等于数据流方向 |
| `relation.kind` | read / write / dependency / dispatch / mention / none；缺失就未知，不从“跳过来”补 | mention 不是 uncertain read；dispatch 不是文件输入 |
| `relation.from/to` | 关系自身的语义方向 | 不按浏览顺序反向，不用布局 parent 代替 |
| `source_of_claim` | ledger observation / explicit ledger candidate / model / legacy unknown | 模型给了证据，不自动改成 ledger confirmed |
| `evidence` | 实际动作 ID、源路径、物理行、input/output 字段与时间/范围；是否可定位另计 | 能找到该行，不证明该行支持关系断言 |
| `verification` | 端点绑定、原文定位、关系分类/确认分别给状态 | checked/ok 不能同时代表“来源合法、内容看过、读写属实、因果正确” |

模型补充读写建议至少带明确 kind、关系端点、原文证据与简短理由，保存为 `source_of_claim=model`、`semantic_checked=false`。检测器未命中时仍可继续读取和调查；原文无法定位时保留未核主张及诊断，不阻断其它访问，也不创建确认边。已有真实节点可以作为候选视图锚点，但必须单独标明版本绑定是否确认；不能为了可跳而造 file@v0、尾槽 agent@vN 或未存在版本。

身份不匹配、越界/歧义目标、未返回内容等安全边界不因“允许补充主张”而取消。确定性来源应来自原始调用与账本，不来自模型 YAML 的自报 checks。检索/文本未命中只表示给定范围未找到，不构成“关系不存在”的证明；建议把 `not_found` 与可明确反驳具体主张的 `contradicted` 分开。

### 方向与图层

| 情形 | 调查时间线 | 读写主图 | 其它层 |
| --- | --- | --- | --- |
| agent 查询其输入文件 | 记录 agent→file 请求及返回 | read 数据方向 file→agent | 原文和具体读范围可展开 |
| file 查询其写者 | 记录 file→agent 请求及返回 | write 数据方向 agent→file | 不把回查箭头当写方向 |
| 同节点分页/重复打开 | 每次步骤、窗口、截断和返回状态均保留 | 不增自环、不增实体 | 访问次数/页段可展开 |
| 同文件/agent 的不同版本 | 记录实际两个版本与访问次序 | 无独立读写证据则无边 | 版本历史层可展示差异，非读写关系 |
| 纯搜索命中、纯 mention、无关探索 | 保存搜索凭据、命中号、来源及步骤 | 可保留真实目标节点为独立位置；不画节点间导航线 | 查询/搜索侧栏显示来路 |
| 跨多跳跳转 | 一次请求仍只是一条访问事件 | 只有逐跳独立证据才可显示逐跳关系；不补直接捷径 | 未打开的中间节点只能标“未访问”，不伪造步骤 |
| 真实或声明的派发 | 保留派发原始事件、声明者与定位 | 不混入读写线 | 独立组织/控制关系层；模型声明、推配、原始记录分级 |

依赖读和未确认采集窗口不能当“模型已获得全文输入”。若主图纳入这类候选，必须保留 dependency / overlapping / conditional 等具体分类，不能只用一个 unknown 遮住不同语义。

## 最小结构重构与第一阶段边界

建议首阶段只增加一个只读 `evidence_graph` 投影，不重命名或覆盖原 trajectory 的 visits/transitions/searches/declared/parent，不改变旧 raw 与 metrics。

1. 默认仅投影**本次已记录转移中实际核出的关系**。不对所有已显示节点做 O(N²) 两两关系搜索，也不递归扩池。不声称“完整账本图”或“全因果图”。
2. 投影边要求两端都是既有真实精确节点，关系 kind 为 read/write、status 为 true/unknown，且有原始动作定位证据。方向用 `causal_from/to`；没有这两个字段不得用 query from/to 猜方向。
3. 排除 self-loop、search、纯 lexical mention、仅查询导航及 dispatch；端点/轨迹身份不绑定或只有无来源的关系摘要不能成为当前读写确认边。被排除的查询和节点仍保留在时间线/独立位置。
4. 对同一方向、同种类/状态/来源的证据边合并重复导航步骤，保留 steps 和全部原文证据。模型补充关系只预留 schema，首阶段不从现有散文抽取或生成。
5. UI 主图消费 evidence_graph；完整访问时间线继续消费旧 visits/transitions/searches。布局父单独处理，不能因为现有 parent 有值就顺手画线。来源数、关系数、访问数、查询数分开计。
6. 旧 run 缺字段时明确“旧记录未提供新图投影/关系方向”，可用新查看器按当前可核事实做独立投影并记录 viewer 身份；不得把新的解释写回旧产物，或把旧 route 默认视为 read/write。无 via 的 ledger 模式也不能把纯版本继承线混入新读写层。

第二阶段再由统一 query/关系注册层承载模型补充、显式路径、dispatch 独立层，并统一候选枚举与计数规则。不要把重构第一步做成收紧检测器准入的开关。

验收重点：逆向浏览仍按数据流画边；同节点翻页保留步骤但无自环；多跳不凭空补直接边；mention 与真正不确定读分离；允许从原文继续调查但不升级模型主张；搜索/dispatch 不进入读写主图；旧原始步骤、时间、来源、身份与拒绝状态不被改写。

## 第一阶段实现与验收补记

主线程确认以上合同后，已实施顶层 `evidence_graph`，schema 为 `migloop-evidence-graph/1`；保留原 trajectory 列表不改。`scope=recorded_transitions`、`complete=false`、`semantic_checked=false`，`model_relations=[]` 仅预留，不从旧报告补造关系。

- 边按 `causal_from/to` 定向，保存 `kind=read/write`、`status=true/unknown`、`source_of_claim=ledger`、全部 `steps/evidence/notes`。原始动作位置要求与当前 ledger 的 aid/seq/source/use_line/result_line/event_id 一致；无位置则不画线。
- `counts` 分别计访问、搜索、转移、投影/未投影转移、确定/候选读写；`source_counts/relation_counts/excluded` 单列原始来源与排除原因。未知身份、明确身份冲突及旧无 via 跑不生成当前读写边。
- 图只画独立投影，首访布局 parent、搜索入口、自环和版本前后不画主图线。全部转移在可点击时间线保留；原生调用、拒绝、分页与部分返回仍在原列表和节点抽屉。手动换根的非调查账本视图未在本阶段重新设计。
- 新 `findings` 只读投影以折叠面板展示文件修复锚点归集，区别“坐标存在”与“模型声明该文件属于此事项”；未绑定事项不以 root 补挂，原因/无效坐标/引用保留，归因对照字段齐全不变成语义通过。
- 新增投影测试先红（旧代码缺 `_evidence_graph`）后绿。probe/native/identity/via/trajectory 相关 170 项通过；浏览器保留旧功能回归并新增投影、方向、导航隔离、身份防线和文件归集检查。真实旧报告/冻结材料未修改，未运行模型。`probe_smoke.cjs` 同时兼容新读写投影和旧查看器的原路线显示，不把两套图含义混为一谈。
