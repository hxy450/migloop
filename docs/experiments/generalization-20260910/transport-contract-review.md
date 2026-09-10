# 通用交付合同审查：先压缩封装，再约束完整传输

审查时间：2026-09-10。审查起点 HEAD `04745b24ab737e57dd342193b3fcd1e5bde62810`；工作区已有 service/deveco 用户改动，本 agent 未修改。未运行模型、真实池冷查询、历史命令或旧 runner。使用 gitnexus-impact-analysis 的调用者/兼容风险检查思路；GitNexus 没有 migloop 索引，因此以源码和现有测试对账，未新建索引。后经父端授权，仅新增纯 `batch_wire.py` 与专用合成测试；运行时/receipt集成由父端另行负责。

结论：优先落**方案一：无别名、仅减冗余外层的版本化 wire codec**，随后另接完整工具文本总预算。不要只在 `data` 内继续削正文，也不要将服务端保留的完整材料当成模型交付。方案二是同一选中数据生成可读文本、用显式正文区间清单描述交付；它更易读，但迁移范围更大。首落 codec 已实现，尚不负责预算裁剪或回执认证。

## 现状与预算缺口

`investigation.batch` 先独立查询，按成功项均分 `max_chars`，再回流余量；`delivery_budget.fit` 只裁已排序前缀、原文字符前缀或可恢复注释。这个顺序和不改匹配范围的语义应保留。当前明确声明 `budget_scope=serialized_data_only`，封装另计，并非总输出承诺。

- 同一项的 scope 出现在 `item.scope`、`item.data.scope`、`item.delivery.scope`，并可再次出现在数据里的查询与外层 `continuations` 中。
- 原始定位可能同时出现在结果行、嵌套 query、数据内部 receipt、`item.delivery.records`、continuations 中；请求 `item.args` 还完整回显路径、搜索词和 refs。
- `render_batch` 最后才序列化整个 envelope，再加 receipt。因此目前只减少行/正文的预算操作，不约束这些大块封装。
- MCP 已设 `structured_output=False`，避免 `content` 和 `structuredContent.result` 重复同一文本。这条已解决的防线不能在新方案中倒退。
- scalar `expand.max_chars` 是**每条原文/字段**预算，最多24个引用，不是调用总预算；scalar `render_query` 没有统一总量 fit。新策略若只改 batch，scalar 仍可大量返回。

纯合成测量：9项 search，每项相同长文件 scope、4条真实形态的短 preview、`total=40`、保留未知计数；替换 query/ledger identity，不读取任何池。调用当前 `batch/render_batch(max_chars=16000)`：

| 项目 | 字符数 |
|---|---:|
| 实际所有 `item.data` | 12,762 |
| 完整 batch JSON 正文 | 34,098 |
| 正文中 data 外部分 | 21,336 |
| marker + receipt | 268 |

9项均 `ok`，完整 JSON 是 data 的2.672倍。这是合同层面的合成反例，不是实际池收益或模型效果测量。

## 调用消费者与不可暗改的合同

以下行号以审查时工作区为准。

| 入口/消费者 | 当前依赖 | 改 wire 时必须处理 |
|---|---|---|
| `mcp_server.py:269` / `atom_queries.render_text:284` | batch→`render_batch`；changes/expand/events→`render_query`；其余 scalar time→可读 renderer + time receipt | 保留一个文本副本；新增格式要显式版本/投影选择，不混入旧 receipt 声称兼容 |
| `investigation.batch:286` / `delivery_budget.fit:327` | 返回 canonical items/data/delivery/continuations；data-only字符预算 | 不以减少正文掩盖 envelope 超量；总量必须在最终投影后计量 |
| `render_batch:354` / `render_query:362` / `parse_receipt:397` | 单个 JSON 正文、ledger、请求hash、整段正文hash；parser 对正文 `json.loads` | 不能把同 schema 正文改成表引用或 prose 后让旧 parser 猜解 |
| `time_receipts.py:23,52,72` | 参数默认值归一；可读文本固定行前缀提取实际 preview refs；raw_count/hash一致 | 文本 renderer 改前缀会破坏旧解析；导航行不能套用原文 preview 行前缀 |
| `probe.py:438,477,610,631,781` | provider/ID/完整配对认证；双表示只按明确 ID 合并；文本块不递归解 JSON；中间截断只认证可见边界 | 不用旁路完整 runtime body 替换模型实际截断文本；新 codec 必须在原文/提供者认证之后解码 |
| `investigation.project_trace:423` | 完整 native 回执通过后，batch直接复制 item（只去 data）；scalar由 `_delivery` 计算交付 | wire省略或别名化 delivery 时须由已认证可见正文重算；不能照搬原查询未交付数据 |
| `via.trace_identity:33` | batch/changes/expand 的 `parse_receipt` 提供账本身份，独立于模型 YAML | 新 receipt 若未接入，可能所有图都变 identity-unbound；不能只修 UI 忽略此调用者 |
| `time_probe.probe_payload:37` | query_trace、论证图、报告原文认证是三条独立路径 | 查询序列始终 `edges=[]`；图来自经认证文稿+账本，不从查询顺序补边 |
| `service.atom_json:829` / `serve.py:64,112` | HTTP JSON直接调用 `atom_queries.json_data`，不是解析MCP文本；POST只读；HTTP JSON序列化本身也增加封装 | 同选中数据/裁剪范围必须一致；不得HTTP偷偷送更多正文给模型交付记账；旧HTTP不能直接收到未解码表 |
| `fixchain.html:1491–1618` | fullscope对象、`data.items[].data`、时间原子sections、query/next_query、raw_index/body_sources | 新表需统一decode适配层；裸offset不是通用continuation；不能替默认scope/latest补齐 |
| `fixchain.html:1834` | trace steps/items/delivery、真实状态；只有已认证 `data_schema=time-view/1` 才重放旧 `view=records` | 缺旧schema不能猜；重查仍标“当前实现、不保证原次交付相同”，不得修改PROBE原轨迹或图 |
| 旧 `run_tools10.py:328` | 从native calls保存 `project_trace`；冻结包拥有自身源码 | 不修改旧runner/包/保存结果；新解码只供新版本或兼容读取，不补造旧交付 |

特别注意：`time_receipts.digest(text)` 是对**排序compact JSON序列化后的字符串值**做 SHA256，不是直接 `sha256(text.encode())`；`render_batch` 的正文虽为JSON字符串，receipt依然沿用此算法。若新协议采用直接字节hash，必须版本化，不能悄悄统一旧算法。

原始 raw ref 是 `source basename hash + 1-based line + 原始行文本hash`（`transcript_store.py:28,87`）；字段展开另外有 JSON Pointer、representation、字符偏移与 field hash。首版不引入响应短ID，不让模型学习alias，也不引入跨响应隐式状态。

旧兼容还有两个明确分支：time receipt 的未提供 view 与显式 view 不同；较早无 annotation cursor 默认项的hash仍可核。investigation scalar changes 的旧 receipt 没有 `related_offset/related_limit` 默认项，parser仅在原请求未提供时按旧形状验证。旧正文必须直接核原始hash，禁止重查当前默认视图后生成“等价”回执。

## 方案一（已选首落点）：只减可机械还原的冗余外层

保留 query、fit 和 canonical batch 数据模型。新 `migloop-batch-wire/1` 只包裹 `batch`、顶层ledger、原requests hash和显式 `omitted` 清单；`batch.items`仍直接含 tool/status/data，原文与内部元数据完整保留，无scope表、ref表或alias。顶层ledger必须与batch.ledger逐字一致，继续满足现有说明的账本身份读取方式。模型仍照抄原来的完整scope/ref/continuation对象。

| 字段 | 省略条件 | 不可省的情况 |
|---|---|---|
| `item.args` | 与同 `item_index` 原始request的args精确JSON类型/值相同 | 规范化后不同、显式false/null与0/缺省不同；不能凭Python宽松相等省略 |
| `item.scope` | `data.scope`确实存在，且精确相同 | deferred/error没有data；跨scope或显式值差异 |
| `item.delivery` | 支持的data schema可按**固定wire-v1算法**从可见data推出，且与原delivery精确相同 | 未知schema/无法解释形态、额外unknown字段、任何值或类型差异 |
| `attention` | 与保留的每项status/error完全重建一致 | 额外注释、显式null、自定义内容；不得吞不一致 |

以下原样保留：全部 `data`（包括scope、raw refs、field hash、preview/text、gap/unknown、内部receipt、next_query）、tool/status/error、budget_adjusted、original_data_chars、delivery_summary、所有continuations和未交付refs。尤其continuations不能仅从剩余data重建：被裁掉的另一侧、未交付ref、独立related/undated页和派生diff重查信息可能已不在data里。

decoder只按显式省略标记恢复。没有标记的缺字段不猜补；重复/越界/bool索引、重复省略名、同字段又省略又显式给出、不同原requests、未知codec均拒绝。未知item.data schema仍可原样往返，只是不省其delivery。JSON文本入口拒重复key、非JSON类型、NaN/Infinity、循环、超深/超节点/超字符内容；不递归解析raw string中的JSON或YAML。

固定delivery提取版本很重要：不能未来升级 `investigation._delivery` 后，让旧wire在重放时凭空多出“已读”。wire-v1独立固定小提取函数，明确区分raw字段段、raw段、preview、派生diff/line；纯导航不产生正文记录。只为已支持schema省字段，不用新版本默认值填补旧语义。

同一个9项合成对象，单纯删这些外层得到18,432字符；**实际新codec连版本wrapper、requests hash、omitted清单及顶层ledger共19,114字符，比34,098减少43.94%**。12,762字符的data和9条continuations一字未裁，同JSON树往返成立。这里不含尚由父端集成的新receipt。这验证可达封装收益，不宣称已经增加原始材料交付量或提升模型表现。

迁移仍涉及 `parse_receipt`、`project_trace`、`via.trace_identity`，不能只换renderer。父端已选新 `MIGLOOP_BATCH_WIRE_RECEIPT` 分支，绑定实际wire body、原request（含预算）与还原canonical三hash；只有完整新文本含receipt比旧格式短时才使用，否则保留旧格式。旧marker和旧parser不动；先完成native来源/完整交付核验，再decode。codec内 `request_sha256`只是自一致性，不是数字签名或原文真实性证明，篡改正文必须由外层receipt+原生调用认证拒绝。重新序列化canonical可改变对象键顺序，不能用它替代旧原始文本hash。

HTTP可先继续返回canonical JSON，MCP新wire的decode必须等于同一次选择后的HTTP数据；选中数据共用内核，不为两端重查不同页。UI与trace仍消费还原后的canonical结构，可避免模型学习新alias和UI各自解析深层表。旧HTTP/MCP字节相等回归保留旧协议分支，新协议另测解码同树。

**下一步才是总预算**：当前codec没有截断职责，`max_chars`仍不能改口成已限制整个输出。后续在最终wire+receipt层核算，以已选择数据公平裁前缀/回流容量；大到连最低状态和续取也放不下时明确拒绝，不产生非法JSON。预算单位须注明Unicode字符/UTF-8字节/工具文本长度，不宣传成token硬上限。不要同时改变查询范围、schema默认值与原文长度。

## 方案二：共享选中数据，独立可读正文与显式交付清单

仍由一个 canonical selection/fit 产生结果；MCP只返回一次可读文本，HTTP返回同一选中数据。文本先列状态、范围表、计数/缺口和续取，再列编号原文块；每块绑定 ref/pointer、representation、原字符offset、实际交付字符数、next_offset。新 receipt验证实际可见文本，显式span清单仅描述已出现的原文块。

这不是 `content + structuredContent` 双发，也不是把完整正文存在服务端sidecar后声称模型已读。HTTP更丰富的展示、hash清单、折叠原文入口都不能代替MCP文本交付事实。可为人工UI加载更多数据，但必须标独立查看，不写入模型trace。

优点：模型默认读到正文而不是多层JSON；不必理解大量响应别名。风险：文本正文/清单/HTTP数据成为三者一致性合同；需要新严格parser验证每个span实际存在、无重复覆盖/越界、保留换行/转义、外部文本不能伪造区块头。当前time receipt只会按行正则取ref，不记录精确extent，不能承担这个新协议。`probe._tool_output` 也不可对JSON样原文做语义重排。

仅适合愿意维护一个受版本控制、可机械解析的文本编码时选用；不要为每个tool各造独立随意格式。总预算仍须在最终正文+清单+receipt上执行。与方案一二选一为主，避免两个新wire长期并存。

## 两种方案共同的不可退让边界

- 新协议认证三层分开：native provider+call/result来源；请求/实际返回bytes自一致；源ref/时间/关系事实。hash不是签名，返回可定位不是模型采用，更不是因果成立。
- 全文、字段前缀、preview、派生diff/line、纯导航必须区别。字符offset按其representation，不把preview位置或diff行页当原始JSON字符偏移；空串/只locator不得升级已读。
- `total`/匹配范围/未知与gap计数不变。日期未知独立页，related页使用related_offset，操作候选不升级confirmed或writer。来源过期/未完成/失败状态不因压缩消失。
- 候选关联、原生确认效应、作者未认证、状态传播未证之间的区别保留。节省字段可共享枚举/声明，但不改默认truth值。
- continuation必须完整继承目标及上下界，并表明对应主rows、related、undated、annotation/relation、字段字符还是派生diff重查。`next_offset=0`是有效入口；actual_limit=0不允许发下次limit=0。缺continuation格式不得猜offset工具语义。
- UI独立record/展开/下一页继续走POSTbatch，只更新独立结果容器；查询步骤之间、模型论证节点之间均不自动补边。

## 必须保留/增加的回归反例

| 反例 | 期望与现有测试锚点 |
|---|---|
| 9项长scope/refs，data未超预算但封装超出两倍；一项大diff先返回 | 新总预算包含表/receipt；每项有公平正文机会或明确未交付，不按重要性排序。`test_investigation.py:185`、`test_delivery_budget.py:68` |
| scalar expand 24refs、其中第一条超长，另外仅result在范围内 | 每ref部分交付/拒绝/续取准确；不能将未交付refs记读，不能泄漏另侧。`test_investigation.py:27,143`、`test_delivery_budget.py:133,155` |
| 纯导航ref和长度50000、没有任何preview/text | 交付raw段为空，折叠/展开入口不是阅读。`test_body_sources.py:86`、`test_temporal_atom_delivery.py:56`、`test_annotation_delivery_v3.py:132` |
| old receipt无view/无annotation默认/旧changes默认；显式records、不同cursor或since | 原旧hash仍成功，不重查当前数据；显式不同参数失败。`test_time_atom_transport_audit.py:106`、`test_investigation.py:202` |
| 非migloop提供者复制合法receipt、同ID冲突参数/结果、只有stdout完成、缺发起时间 | 不认证trace或身份，codec不提供新信任。`test_codex_probe.py:213,259,491,505,513` |
| native full runtime返回存在，模型实际正文中段被截；伪造truncationmarker | 只保留实际visible片段，不用完整旁路正文补齐receipt。`test_codex_probe.py:388,415,437` |
| 原始正文含JSON键content/result/error、receiptmarker、像ref行的内容 | 不递归解包/丢字段，不让原文伪造清单；quoted text不改变hash。`test_probe_json_text.py:22,33,38`、`test_time_atom_transport_audit.py:194` |
| raw+field同ref，中文/emoji/CRLF/JSON转义，不同pointer | 原raw hash不改；field hash、offset、长度按明确representation，不能合并为同一正文覆盖。`test_delivery_budget.py:113`、`test_investigation.py:143` |
| 独立related/undated页、零交付、最后一页被裁、只有大gap元数据 | 各页精确续取、不吞gap、不误宣告穷尽。`test_delivery_budget.py:195,274,300,315,326` |
| 新wire省略标记缺失/重复/越界/bool索引/同字段双给、原request不匹配 | 拒绝不一致还原；不从缺字段或查询顺序补数据。`test_batch_wire.py` 的结构/请求篡改回归 |
| HTTP/MCP请求相同，UI点record/下一页，再重放旧无schema记录 | 两端共享选中数据；UI图/真实trace深拷贝前后相等；无schema不猜旧view。`test_time_atom_transport_audit.py:51,130,244,264,290` |
| 未知query schema或未知receipt版本超预算 | 不按rows名字猜语义；原样可容纳则标未知，不能容纳则明确defer/拒绝且给重试，不伪造原文认证。`test_delivery_budget.py:204,219` |

## 已实现的纯模块交接

新增 `src/migloop/batch_wire.py` 与 `tests/test_batch_wire.py`，无新依赖、I/O、查询、状态或字符串裁剪：

```python
pack(canonical_batch, requests, *, max_chars=8_000_000, max_depth=64, max_nodes=200_000) -> dict
unpack(wire_dict_or_json_text, requests, *, max_chars=8_000_000, max_depth=64, max_nodes=200_000) -> dict
```

limits是codec资源安全上限，不是query/token交付预算。`unpack(str)`自行拒重复JSON键；`unpack(dict)`只能验证已安全解析的树，无法追溯上游parser已丢弃的重复键。正文被改但结构仍自洽时，codec不假装能认证其来源；测试明确要求调用者另外核回执和native原文。

正式venv验证：60项新codec测试，加既有 investigation/time_receipts/time_probe 共 **105 passed in 1.82s**。覆盖真实小合成canonical batch、不重查、固定delivery八种schema、partial/deferred、错误request、unknown schema、跨scope差异、顶层ledger严格一致、Unicode/null/bool、重复key与结构篡改、资源上限。没有跑真实池或模型。

父端已接入新receipt/入口/identity；下一阶段总预算仍与本纯codec分开。UI仍只消费统一还原数据，不自行造事实，不重写旧实验产物，也不以本轮新模型跑分证明收益。

## 接口集成后的独立收尾

详见 [batch-wire-interface-audit.md](batch-wire-interface-audit.md)。新增12项真实MCP/HTTP与原生回执格式测试，覆盖1000/6000/100000 data预算下的canonical同树、partial/deferred/error、真实配对/假provider/pending，以及三hash和安全包装边界。

审查曾复现 `project_trace` 可拆受支持的单键result包装、`via.trace_identity` 却不拆而误判unbound。父端复用同一安全 `_unwrap_result` 后，wire/legacy两个回归均通过；带额外字段或非字符串嵌套result仍不被宽松拆解。所有新测试已无xfail，旧失败事实保留在测试说明。

最终相关联合 **174 passed、2 skipped，5.10s**；skip是既有可选browser项目，不表示本次已做Chrome视觉验收。旧v3一份已冻结原生录制的4条batch回执在当前parser全部有效，32个不同交付raw refs中顺序抽8项回原池核行hash均一致；没有重建旧ledger、改ID、读holdout报告或调用模型。当前未发现尚未处理的新marker遗漏、错误正文交付认证或哈希绕过；这不把源码可达性/交付认证扩为模型归因正确性。
