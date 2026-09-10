# 渐进披露文本原型：Dice changes / Member file

这是可审阅的离线原型，**不接生产、不替换 JSON/UI、不调用模型**。与无损 YAML 方案不同，本版明确不默认交付一些字段、其它目标的关系明细、部分重复定位器预览；另有一份 3-row 演示。没有“同事实无损压缩 57%”的主张。

先看两个真实文件：本地 EVAL 的 `tools-v3-progressive-text-20260910-1/render-3/dice-changes.txt` 与 `member-file-three.txt`。不裁记录的对照是 `member-file-all-selected.txt`。`*.audit.json` 有逐字段遗漏清单、实际显示片段范围及完整可执行查询，不会附到模型正文里。

## 默认保留什么

1. 页头给完整 ledger 和一个 scope 对象：对象、at、since_ts 各定义一次。范围含端点；since=null 是无下界。没有 scope-ID 字典、YAML 锚点或隐藏会话游标。
2. 修改/关联余项分区；保持确定/candidate/unknown/lexical 状态，作者状态与来源主体分开。调用返回、success、唯一配对、外层/原生主体与效应认证分开，不能把 returned_success 写成目标写入已确认。
3. 已选中 `native_io` 中的真实输入/返回片段、实际显示长度、来源 ref、pointer、source/line/time、表示内范围、截断与后续 offset。所有 raw refs 原样输出，不缩写。
4. 原始 file 记录的预览、真实关联类型和**目标**关系；其它目标关系默认只显示数量与状态分布。`returned` 注释不提升为目标 writer。
5. selected 数、默认显示数、未交付数、记录总数及不跳过未显示项的 next；覆盖来源数、扫描完备与因果完备分开。gaps、未知时间、失败/异常、不支持执行、未交付标记和既有边界说明保留；不把空字段说成全历史不存在。
6. 原生正文导航明确标为“正文交付 0 字符”；保留其 ref/pointer/记录时刻/完整或部分范围声明、调用状态与 author/current_state 未认证标记，给出展开和后续导航。

不默认显示：重复事件 ID/schema、旧版本/legacy 定位、重复 field-access 技术对象、某些原始查询表示、排序实现字段、其它路径的关系明细；Dice 另有 16 段定位器 preview 可能不同于下列 native_io 预览，**明确未交付**，不能说“只是重复字段”而冒充已读。每个遗漏 JSON leaf 都记录 pointer、原因和值 SHA-256。

新出现的 schema 不会宽松套此模板，原型只接受 `migloop-time-changes/1` 与 `migloop-time-view/1`。这仍不是覆盖未来所有 schema 字段的生产实现。

## 页头 scope 与真实可执行性

正文每条子命令均标“加页头scope”，只显示 tool/args；调用者把页头可见对象加为 query.scope。这不是独立可粘贴命令，正文明确说明了组合规则，不假装接口具有隐式当前 scope。

独立前置请求须在子层显示完整独立 scope（特别是 `since_ts:null`），不能沿用页头 since。所有组合后的完整 query 保存于 audit 的 `queries_displayed`。来源字符串始终完整可见，无需新 MCP 调用来解析别名。

2026-09-10 做了两条真实只读抽查，`render-3/query-smoke.json`：

- Member 主记录续读：scope/对象/at/since 全等，offset=3 返回 3 行，next_offset=6；没有直接跳到原 selected 的 offset=100。
- Member 一个 Write 正文入口：完整组合 query 成功按精确 pointer 展开，offset=0，实际 12,000 字符，next_offset=12,000。这次验证读取不追加到默认演示，也不倒算为演示已读正文。精确 locator 只留本地 EVAL 的 smoke 记录。

抽查仅验证这两个入口，不承诺所有分页均已遍历。另有 8 项构造检查：未知作者与成功回执/效应分离、前置 since=null、原文片段起点、未显示技术字段不进正文、gaps 不丢、遗漏清单、原 query 没给偏移时不猜偏移。显示片段的实际输出字符区间与文本 SHA 对照全部校验。

## 两个真实例子与成本

最终数字以 `render-3/measurements.json` 为准。单位是 Unicode 字符，不是 token；当前只实现正文呈现与本地审计，**还没有生产 compact receipt，因此不称为完整 wire 成本**。

| 示例 | 原 selected JSON 正文 | 渐进正文 | 行数 | 默认实际预览片段 | 默认显示主记录 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dice changes，offset 0 / limit 1 | 52,389 | 17,696 | 283 | 18 段，3,883 字符 | 1/1，另 8 个选中关联余项 |
| Member file，默认 3-row 演示 | 653,654 | 5,918 | 92 | 3 段，720 字符 | 3/100，97 未交付 |
| Member file，不裁 100 条 selected | 653,654 | 104,420 | 2,243 | 100 段，24,000 字符 | 100/100 |

Member 的 5,918 比 104,420 短，主要包含**少交付 97 条记录**的收益；不能冒充同事实呈现改善。即使不裁行，非目标关系明细仍被渐进披露，所以 653,654 → 104,420 也不属于无损压缩。

Dice 的 18 段 native_io 正文全部原样展示，但另 16 段 pointer 预览没有默认展示。字面预览与所有技术字段并非同树全交付；只显示关键边界和选中事实卡片，省略明细可按当前 query 的 details=true 请求。details=true 仍受真实预算/分页约束，不能保证下一次一口气取全，也不能把原型的 renderer 选择误称为已存在的新生产协议。

### Dice：读者能直接看到什么

默认把修改卡与关联余项分区，保留各自原有 actor/作者未知/目标效应状态。成功返回文字和原文中的失败/未完成提示可以同时存在；呈现层不让一个外层成功状态掩盖正文中的相反信息，也不替历史补结论。实际源文件、refs、原文及每个具体状态只放本地 EVAL 例子，不复制进仓库作为答案提示。

这张“单页”包含 1 个修改和 8 个余项，共 18 段原文，所以即使 scope 只显示一次，也仍有 17.7k 字符 / 283 行。它不算足够短的最终设计；但长处已由重复 scope 字典转成具体事件、片段及明确下一步。是否再减少默认余项正文是另外的交付选择，不能偷偷视作纯元数据优化。

### Member：不把提及记录当初版代码

原查询是 F10-01 rep1 step7 第 3 项：`file`，截止生成结束时刻，limit=100，details=true；实际 total=525。本版 3-row 演示如实先展示原顺序的 3 条记录，目标提及关系不会因同条记录对其它路径写入而升级为目标作者。

正文导航直接给出 kind、source/line、record_ts、完整 raw ref、pointer、chars、body_extent、call_state、author_certified 和 current_state_certified。实际样例只保留于本地 EVAL，不把具体作者、初版位置和原文复制进仓库。

这只是导航元数据，演示没有读到这些全文；只读 smoke 后也没有回填演示。调查者可以使用给出的 expand 参数读取正文，不需要先解释大量无关文件关系。

原 `file` 预览没有给出精确 JSON pointer 或 readable 表示内偏移，本版明确写“原 query 未提供，不猜测”，仅记录准确的**显示文本**字符范围与 raw record ref。不能据此伪造原始字段级 read receipt；需展开记录/正文后取得精确位置。

## 遗漏审计口径

| 示例 | 非默认技术 leaf | 非目标关系 leaf | 未交付记录 leaf | 未交付另一组 preview 定位 leaf |
| --- | ---: | ---: | ---: | ---: |
| Dice | 424 | 0 | 0 | 288 |
| Member 3-row | 286 | 1,086 | 12,777 | 0 |
| Member 100-row | 4,588 | 7,540 | 0 | 0 |

这是 leaf 实例数，不是不同事实数/证据数。边界字段即使属于未显示记录，也可能单独以缺口/异常说明或空实例计数显示，故整条隐藏记录并不等于其每个 leaf 都归同一类。审计记录仅表示哪些字段实例未在默认呈现中显示，不把别处重复出现的等值字段自动当这个实例已读。

本地 audit 约 0.2–2.9 MB，包含完整遗漏表和可执行查询，**不会附回模型**。未来 compact receipt 应只绑定实际正文、已显示片段/ref/范围，不捎带这份完整审计吃回节省；这部分尚未实现，本次不虚报其成本。

## 数据包与边界

- Dice 重用上一无损原型保存的真实 selected，未再次查询 Dice 池；包 SHA `903ad2c9de0b99100ca8213b508a0ac2c091654d16e41d9cccdd7fa0fc2e4610`。
- Member 只读单 query 重放 16.235 秒，包前后 SHA 均 `56fcf7e081abe0cfdc0e9042758b667ae44aa80bfa0be4671f737d69bfdb36ce`；不是与 Dice 同一个全文件包。
- 两份清单实际唯一差异为 `src/migloop/render/templates/fixchain.html`，Python 查询模块相同。后续两条真实抽查 16.483 秒、前后包仍稳定。
- 没有执行池中历史命令；没有付费模型调用；未修改 src、冻结产物、旧报告或评分。

停在可审阅原型，不继续精修。待主代理看真实文本后决定：是否接受页头范围组合，是否改默认余项/记录数量，以及是否另做版本化 renderer/compact receipt 接入。这里的可读性判断仍是 AI 审阅，不是人类或 Luna 的已测收益。

相关实验模块：`progressive_text_prototype.py`、`capture_member_text.py`、`verify_progressive_queries.py`。旧无损版和本版数据都保留，不能交叉引用其收益百分比。
