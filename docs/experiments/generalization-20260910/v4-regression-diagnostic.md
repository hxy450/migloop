# 旧十文件 tools-v3 → tools-v4：只读回归诊断

2026-09-10。结论：本轮能确认的是**少数局部论证丢失、调查预算重新分配、以及交付后仍会发生的遗漏/错归**，不能确认某个 v4 实现改动造成了退步。优先应隔离验证“续查是否完成”和“已读变化是否逐项进入结论”，而不是继续无差别增加返回量。

本审阅只读取旧十文件的已完成报告、既有裁决、汇总 metrics、query-trace 与保存的模型侧 transcript；没有冷建 ledger、运行模型、执行历史命令或改动运行时/候选/参考/评分。未使用新十三文件参考。下面的原池定位均沿用既有证据裁决，本轮没有重新读取原池；模型实际收到的文字另按已保存外层返回抽查。

## 1. 下降在哪里，不在哪里

同一冻结 core（SHA256 `0d48f30f9e501eedd55b87e086590c72e8b7fb8096a939f56842b71703426497`），Luna medium、每文件两重复、共二十跑。`C/P/M/W` 分别为 correct/partial/missing/wrong；partial 不算 correct。以下是描述性配对，十个文件才是十个不同样本，不能把两重复视作二十个独立文件。

| 指标 | v3 | v4 |
| --- | ---: | ---: |
| 文件等权正确覆盖 | 75.67% | 67.00% |
| 核心 C/P/M/W（56 unit） | 35/11/9/1 | 30/14/10/2 |
| 支持主张/事实主张 | 66/79（83.54%） | 55/67（82.09%） |
| major / 整文件通过 | 4 / 8 | 3 / 9 |
| input + output tokens（input 含 cache） | 9,388,415 | 9,400,393 |
| 非缓存 input tokens | 1,911,904 | 1,984,047 |
| 已录制批内 ok/error/deferred | 407/45/20 | 476/24/8 |
| 严格文稿 schema 通过 | 13/20 | 11/20 |

来源：[v3 汇总](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-scores-v3.json)、[v4 汇总](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-scores-v4.json)、[v3 交付审计](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v3-delivery-audit.json)、[v4 交付审计](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-delivery-audit-v4.json)。schema/引用机检不计入语义 correct；更多 ok 不表示完整原文已读，也不表示因果判断正确。

五个 C 的丢失，完整解释了宏平均的 −8.67 个百分点；没有其它 C 增减抵消：

| case / rep | 丢失的核心 | 转移 | 宏平均贡献 | 本跑 total tokens：v3 → v4 |
| --- | --- | --- | ---: | ---: |
| F10-01 / 1 | repair-compile | C → P | −0.833pp | 817,343 → 382,224 |
| F10-01 / 2 | repair-compile | C → P | −0.833pp | 473,612 → 219,982 |
| F10-02 / 1 | progress | C → M | −1.000pp | 559,669 → 391,008 |
| F10-03 / 1 | test-integration | C → P | −1.000pp | 671,504 → 461,609 |
| F10-09 / 2 | hit-test | C → P | −5.000pp | 350,603 → 447,424 |

F10-09 是单 unit 文件，一次 C→P 就占总降幅约 57.7%；不能把这个加权结果说成十文件全面恶化。另有 F10-03/rep2 logging 从 P→W，不改变 correct 分子，但新增了实质错归。F10-10 两重复核心均保持 C，major 从 2 降至 0；这解释了“覆盖下降而 major 减少、file-pass 增加”并不矛盾。

五个失去 C 的 run 合计 token 从 2,872,731 降至 1,902,247（−33.78%）；其余十五跑从 6,515,684 增至 7,498,146（+15.08%），抵消后总量仅 +0.128%。因此“总 token 一样”并不等于每题调查深度、独特证据量或上下文组成一样。五跑非缓存 input 也从 526,444 降至 442,578，但不能据此推定 token 越多必然越正确：F10-09/rep2 恰是 token 增加而 C→P 的反例。

## 2. 四个可隔离的机制候选

### A. 尚有可执行续查入口，就以“当前未知”结束了局部调查

**可证差异。** F10-01 的两个 v4 报告都找到去 `private` 的实际修改，却没有完成触发链。rep1 明说“已交付证据没有展示具体编译错误、调用方或测试结果”“为何必须公开”的机制未解释（[报告 L189](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-01/rep1/report.md:189)）；rep2 说“不能确认它是必要修复”（[L159](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-01/rep2/report.md:159)）。v3/rep2 则明确引用私有方法类外访问错误并解释返修新方案造成的回归（[L139](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v3/runs/F10-01/rep2/report.md:139)）。评分不要求复述 `ProductItemCard` 名称或完整编译日志；差别是 v4 明确保留了核心机制未知，不是少了一个辅助术语。

v4/rep1 最后一次 [query-trace](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-01/rep1/query-trace.json) step17/item1 搜索 compiler，状态 ok 但 `budget_adjusted=true`，只选中 L1/L2/L3 的 240 字符预览，明确 `offset=3, remaining=10`。后面没有续查；外层 [transcript L73](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-01/rep1/transcript.jsonl:73) 虽有截断警告，仍保留这段 total=13/limit=3/remaining=10/next_offset=3。v3/rep2 step19/item1 已定位 compiler L24/L26/L27 的错误预览。不能把“未打开”解释为历史日志不存在。

F10-02/rep1 也是实际证据路径变化：v3 外层 [transcript L62](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v3/runs/F10-02/rep1/transcript.jsonl:62) 仍可见脚本中 `strokeWidth=4vp`、显式 13vp 与 `style` 的修复段；v4 既有审计未见 L346 完整展开，本轮扫描其模型可见外层返回也没有 `strokeWidth` 字面命中。v4 结尾讨论的是业务“进度条缺失”finding，不是已有组件绘制厚度修复（[L150](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-02/rep1/report.md:150)）。这是未完成覆盖，不额外升级成无任何 Progress 修改的错误断言。

**候选机制/未知。** 调查可能过早以“列出变化 + 标 unknown”收尾，尤其当一个操作含多个修改、错误日志与目标写入分处不同记录时。当前能证明停点与证据差异，不能证明长 preview 导致停点，也不能保证继续翻一页就一定正确。

**隔离实验。** 固定工具版本、预算和公开任务，仅加入不带答案的收尾检查：“对已经发现但原因未知的变化，记录仍未完成的分页/原文入口；若继续查阅，优先完成其中一个有界入口，再决定是否未知。”对照组保持原流程。观察待解释变化的实际续查率、新增独特正文范围、局部 C/P 转移、额外 token；不能把穷尽不透明脚本作为必需条件，也不能强迫未知作者变确定作者。

### B. 已送达的变化没有逐项进入解释，同类修改只写了代表项

**可证差异。** F10-03/rep1 的 v4 不只是“没收到 export”：step8/item0 和 step16/item0 均记录 `#81e0a463:1272@L3231` 的 225 字符 derived diff。更重要的是，后者对应外层 [transcript L62](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-03/rep1/transcript.jsonl:62) **没有截断警告**，实际文字包含 `class Dice`→`export class Dice`，以及“仅为 arkxtest 单测可见性放宽”“不抽独立文件”，`diff_chars=225, truncated=false`。这里验证的是送达的派生差分，不冒充原始请求/成功回执全文已展开。

v3 同跑明确解释 export 与三个 UI ID 两条测试接线（[报告 L83](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v3/runs/F10-03/rep1/report.md:83)）；v4 只解释三个 ID（[L79](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-03/rep1/report.md:79)），其后还把同一批注释清理分成两个 finding。因而这里有直接的“已交付内容 → 最终覆盖遗漏”，不能归咎于该 diff 被预算挡住。

**候选机制/未知。** 从变化清单压缩成少数主题时，容易以一个代表修改覆盖整类，遗漏同类的独立修复分支。重复取得同一 diff 没有解决它；尚不能分清是注意力分配、写报告时丢失，还是模型误以为测试接线只需代表项。

**隔离实验。** 不新增原始材料，固定这类已完成调查的实际可见证据包，仅对比自由总结与“逐个已见实质变化映射到 finding/明确未知/非修复，再写总结”的通用写作检查。分组单位是已见变化，不是 gold unit，也不给文件专用关键词。测新增覆盖与虚假归因是否同时变化；不能通过复制所有 diff 冒充原因已解释。此实验优先级高于单纯加大返回量。

### C. 把局部报告推广到整个阶段，或把后修状态回投初始状态

**可证差异。** F10-09/rep2 的 v3 读到了直接修复说明和生成收尾：step8/item1/step14/item0 含 A8114；step14/item0 含 A7687。外层 [transcript L60](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v3/runs/F10-09/rep2/transcript.jsonl:60) 虽整体截断，这两个短正文均在保留前缀中：Block 阻断子按钮，以及 FV-2 真实编译 `1 → 0`、unsigned HAP、未开始 a2h-verify。v3 正文相应区分编译通过与交互未验证。

v4 同跑 19 个批内项全部 ok，却沿另一条路径完整展开 A5717、A2607/A3906 等 worker 的 NOT_RUN 报告、以及更晚 B6090 汇总；未见 A8114/A7687 的完整送达。最终先把局部原因留为“点击被拦截”或“点击穿透”无法区分（[报告 L20](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-09/rep2/report.md:20)），随后无条件说“生成阶段没有构建或设备复测记录；因此能定位‘验证覆盖不足’这一局部环节”（[L87](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-09/rep2/report.md:87)）。局部 hit-test 因果未完成对应 C→P；全阶段无构建的错误前提另计 major，不是同一个评分项。

既有[裁决](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-adjudication-v4/F10-09/rep2.json)保存的反证是 A6120（`2026-08-16T21:28:08.140Z`，实际 BUILD SUCCESSFUL/exit0）和 A7687（`23:49:46.899Z`，生成收尾）；NOT_RUN 只对特定 worker/批次成立。没有本次重跑、不知道某触摸行为是否修好，都不能推出历史全阶段没构建。

另一个交付后反例是 F10-03/rep2：v4 [报告 L183](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-03/rep2/report.md:183) 明说“初始文件确实包含 console.error 及 Android/Kotlin/Material 等注释溯源”。但初版全文已在 step18、未截断外层 [transcript L69](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v4/runs/F10-03/rep2/transcript.jsonl:69) 送达。既有[裁决](C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-adjudication-v4/F10-03/rep2.json)定位初版 `agent-a349784d2663f1f0a.jsonl` L75/76（15:52）没有 console；`agent-a4874344c8fb6228d.jsonl` L68/69（18:29）才新增，晚期再换 hilog。初版有注释，不使“初版也有 console”成立。

**候选机制/未知。** 一个主题下的不同 actor/阶段/证据强度在写作时被合并成单一历史故事。该失误在旧版本也出现；本次不证明 v4 更容易犯，尤其总 major 反而减少。正确边界也不是“凡没有机器认证作者一律不能解释”：原作者未知允许通过，代码级近因不必等待设备重测才可解释。

**隔离实验。** 固定同一可见证据包，增加通用事实前提审计：每个“初始/生成期/全部/没有”断言列所覆盖的时间、主体、证据类型和反证，区分 worker 报告、原始命令输出、观察快照与直接修改；不修改工具关系认证，不由查询顺序造边。检查 major/普通错误能否下降，同时监控是否因过度谨慎将已有局部因果一律降为 unknown。实验不提供特定反证行号或答案。

### D. data 预算改善尚未等于模型端完整交付；外层截断仍是候选干扰

**可证现象。** 对两版四十份保存的 `transcript.jsonl` 做一次轻量扫描：仅计 `response_item` 下 `custom_tool_call_output/function_call_output` 的 output 文本块，以 `Warning: truncated output` 开头的外层返回，v3 为 **90/177**，v4 为 **89/182**。一条输出只计一次；不计内部 `event_msg` 的完整缓存，也不把此分母称为 MCP 次数/批内项数。因而批内 deferred 从 20 降至 8，不代表模型端外层截断已经消失。

实例：F10-01/v4/rep1 step17 内部结果在 transcript L72，外层 L73 已有截断警告；F10-03/v4/rep1 step8 内部 L33，外层 L34 截断，但 step16 后来无截断重交了 export；F10-09/v3/rep2 的外层截断仍保留了能支持核心的前缀。**有警告既不等于全部正文丢失，无警告也不等于证据被正确使用。** 本审阅引用完整送达时另外检查可见正文，没有把原 ref/receipt 清单当正文已读。

**候选机制/未知。** 外层包装、重复定位元数据、批次选择及前缀位置可能改变有效证据密度和续查行为，但这只是可测假说。v4 同时改变缓存、短任务 preview、wire 和回执解码；没有单因素对照，不能说 `preview=4096` 本身导致了 −8.67pp，也不能用某一次 wire 节省字符证明其提高了语义质量。两版外层警告总数接近，更不能用它解释全部下降。

**隔离实验。** 先不调用模型，离线重放相同已保存请求/响应，统计“模型最终可见正文字符、未交付正文、metadata/包装字符、尾部续查入口、端到端截断”，把 `raw_segment`、实际 preview、derived diff、导航指针分开。再单独登记并冻结，在旧开发材料/合成材料中做固定检索脚本的 2×2 对照（短任务 preview 上限 × wire 开关），其它参数和原始证据顺序固定；另设相同证据内容仅改变表示的写作实验，以区分“取得更多证据”和“同证据更易理解”。总传输预算、input/cache/output 和失败全部保留；这不是本轮已经执行的模型实验。

## 3. 优先级与推断边界

最先验证 B 的“已见变化逐项对账”，再验证 A 的“有界续查后才能结束未知”：一个直接针对已交付却遗漏，一个针对有入口未完成，两者都不要求新工具基础设施或把 gold 写进题面。C 用于防止提升覆盖时放大错误归责；D 先做离线字节/正文审计，若做模型对照须另行登记和冻结，不并入正在运行的新13文件队列。

不能从本轮得出的结论：v4 减少了可达真值、4096 preview 必然有害、token 总量不变意味着同证据、更多 ok 必然更好、同一文件两次重复足以证明稳定机制，或某项建议必然恢复 75.67%。模型随机路径、并行负载和多项实现同时变化尚未隔离；已有结果文档也记录了后台 CPU/磁盘工作，故不把耗时变化归因于 codec/缓存。没有因为本诊断调整任何既有分数或推荐升级 v4。

## 审计来源与复核方法

根目录 `EVAL = C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10`。读取 `tools-scores-v3/v4.json` 的逐 run grade/cost，逐项比较 `tools-adjudication-v3/v4/<case>/repN.json`；重点回读五个 C 丢失 run 的报告、保存的 query-trace 与相关外层 tool output，另读 F10-03/rep2 的错归句及实际初版交付。query-trace 的 step/item 与 transcript 物理行分别注明，不把服务端选中数据自动当作模型完整所见；外层警告计数覆盖全部四十个已保存 transcript，仅做字符串和 JSON 读取。

| 已读汇总产物 | SHA256 |
| --- | --- |
| tools-scores-v3.json | `1298ab7c202d9f89264b23a751e66628fe83f93acc6fe194896e7661fcd8bc74` |
| tools-scores-v4.json | `7c321171a5915f00cc7a962c35f1f6323fe65198720a271c8f559c8f038328e4` |
| tools-v3-delivery-audit.json | `4ca578d17ff691a891051c2507f5aa7bc199c5a6e3178435a13d6c5acab112e1` |
| tools-delivery-audit-v4.json | `21806295f19e1e6798aa102488cd2fe24e2e97dfd4090bc34693c00a68008753` |

版本差异范围据[冻结前登记](tools-v4-registration.md)，语义细部据[0723 已有裁决审阅](v4-0723-adjudication.md)与[Codex/Dice 已有裁决审阅](v4-codex-adjudication.md)及各 grade 的逐字 spans。这里是旧开发集的回顾性诊断，不是新增真值审定、留出评测或因果效果实验。
