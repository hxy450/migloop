# V3 Member rep2：预先计划的重复裁决，不替换 rep1

审计时间：2026-09-09 14:39 UTC。只读 `formal-v3/member-center/runs/tools/rep2`、同一冻结参考及原始池；另用该 run 自己的 frozen source `18b8f7f` 做位置/边核验，并先确认账本身份严格相等。没有调用模型、修改源码、重绑或写回运行产物。[结构化数据](v3-repeat-adjudication-legacy.json)，[保留的 rep1 裁决](v3-adjudication-legacy.md)。所有相对路径均以 `C:/Users/hongy/projects/_migloop-eval-20260909/attribution10` 为根。

结论：rep2 的 S4 核心归因恢复，S3 不再把正确执行者当错误入口，题外 coverage 也修正。但 S3 仍过度降级成功执行证据、漏 H5；S4 有一处“首次出现”的范围扩大。因此核心回答明显好于 rep1，完整标注仍有边界问题。同 source / 同题 / 同池出现两种归因结果，应报告为运行级不稳定，而不是用 rep2 覆盖 rep1 或宣称新方案已稳定有效。

## 重复条件与结果并列

[预先记录计划](v3-repeat-plan.md) 明确只追加一次、不给答案反馈、保留两次结果。计划文件 SHA `8983c4bed391975398a27f2df44f7eed7058a06ef331f19a77eb77453676157b`；本机 LastWriteTimeUtc 为 14:29:22，早于 rep2 的 14:29:23.446855 开始时刻。这是本次可见计划记录，不是额外模型输入。

两次均为 source `18b8f7f`、gpt-5.5 / medium / native MCP；common-task SHA `e60ad7491cd5991a948f8c7128432feca230a59bee208640ca5b90a44d68dec1`，pool digest `a78b1373045f7558d6da3b76123e30d032635a2a0b4cdd665e7f80c0bdf8b337`，完整 prompt SHA 也相同。账本均为 `atoms-2026-09-09-observation4:146:bc4e9e2dd01e9ff0d0a1de37`。独立查询路线会产生不同后续上下文；这里不声称每个输入 token 或随机种子都相同。

| 核验维度 | rep1 | rep2 |
|---|---|---|
| S3 一透明两暗色 | 映射正确 | 映射正确；执行仍被写成“尝试/声称” |
| S3 故障入口 | 正确 patch 的 fixer 被标进入错 | entry=[]，不再错误归罪 |
| H5 已透明、被跳过 | 漏 | 仍漏 |
| S4 Slice8 已读源码→错误重写 | 未查 Slice8 输入，丢失近因 | 实际打开 Read 和 Write，恢复核心证据 |
| S4 private / builder 角色 | builder 错误发现者被标进入错 | 最终 helper 引入者为 fixer@v53，builder 正常 |
| S4 v45 | 错误标签但理由仅说修字号 | 正常，理由限于修字号；不认证全体新增代码无错 |
| v13 banner coverage | explained+[S4]，错借同动作归因 | out_of_scope，保留分母 |
| schema / coverage complete | true / 22/22 | true / 22/22 |

## Rep2 的 S4 恢复有直接查询证据

调用号按 frozen `probe._transcript_calls` 的 primary transcript 顺序，L 为 rep2 `transcript.jsonl` 物理行。

rep2 #27 按旧价格表达式搜到 v7；#29（L186）实际打开 v7 价格片段；#32（L205）打开 Slice8@v13 的历史输入/动作；#34（`call_kvrj0mE5NZcpOReVOxE364LT`，L219）展开 Slice8 `#20509` 的原始 Read，包含 Kotlin `showNowPrice.replaceSpan(Regex("\\d+")) { AbsoluteSizeSpan(30,true) }`。#35（`call_b7asjKploky3kcr6wETfQKjG`，L226）展开 `#20723` Write 的实际单 Text 30vp 代码。不是凭 search 命中伪造历史读取。

原始 Slice8 JSONL L24 返回源码的时刻为 2026-07-24T15:33:51.671Z，L264 Write 为 16:04:37.440Z，方向成立。两轮价格修改、final private helper、private access 编译错、两次去 private、build2 `EXIT=0` / `BUILD SUCCESSFUL` 也都有已打开的 action 原文。没有把构建通过当成修后视觉已验证，S4 的有限核心回答可判通过。

v45 的“正常”在其 reason 仅描述按数字/非数字修正字号这一作用时可接受；不应扩张成它所有新增代码已证明无错。首次修复 v12 本来已经含 private splitPriceRuns/isDigitRun，最终编译所报名称则是 v16 的 priceDigits/priceSuffix。可以把这次实际编译失败追到最终 helper 引入点，不能改写成整个 private 模式直到 v16 才首次出现；本次未证明中间态曾构建失败。

有一项额外过强表述需收窄：boundary 写“单 Text 价格实现首次出现在 v7”。#27 实际只搜一个带 `animatedPrice` 的精确表达式。原始初版 conv-member L61 已有 `Text(this.item.priceText).fontSize(30)`；其 `priceText` 注释当时约定为数字。正确说法是“这条精确表达式最早已知命中 v7，v7 是已查明的最近相关重写”，不是所有单 Text 实现的历史首次，也不能由此反向归罪初始生成者。

## S3：空 entry 正确，执行事实仍不该降成纯主张

rep2 #7（`call_jA8YeaUK14tLQvm1BvuWyzyY`，L60）返回完整 mask 脚本和成功结果：先 `open(path,'w').write(new)`，后加入报告，最终报告精确目标 `3 sites import=+`；前置分类也已打开。它支持记录中的三处实际写入：AppLoadDialog→`Color.Transparent`，PayAgreementDialog / RenewRuleDialog→`Palette.DIALOG_MASK`。不需要先给这个动态脚本造一个正式 file@v，才能承认执行证据。

S3 boundary / notes 却多次称“只能确认脚本声称”“尝试并报告”。这仍把解析器未生成目标版本的问题，扩大成执行事实的证据不足。应区分：成功调用支持三处写入；完整文件快照未复原；独立读回只覆盖 PayAgreement 和 Palette import；修后设备行为未验证。后面两项边界正确，不构成否定前一项的理由。

H5 仍未点明：原始 Slice8 L264 的 h5PayDialog 已设 `Color.Transparent`，脚本有 `if 'maskColor' in block: continue`。因此三处不是四个 controller 全改，也不是三处暗色。rep2 至少没有再把正确脚本执行者标成故障进入点；这是相较 rep1 的实质修正。

## 边、引用和 coverage 分开核

在 rep2 自己的冻结引擎和相同账本身份下，46 次 evidence 引用、28 个唯一引用均可定位（status=ok）。位置可定位不是理由真伪认证。

五条模型显式写边全符合精确版本：Slice8@v13→file@v7；fixer@v45→file@v11；fixer@v53→file@v16；builder@v3→file@v17；builder@v4→file@v18。没有把 builder@v5 的总结节点误写成 v17/v18 的写入时刻。rep1 的两处错 L 后缀在 rep2 没有复现。

冻结 `verdict.build` 还自动给相邻 nodes 补出五条 implicit 关系，均为未核出直接边，包括重复的 S3 agent@v5→自身。这些不是模型显式声称的边：S3 原文 `edges: []`，S4 原文只有上述五条写边。不能把系统相邻项自动核出的 false 算成模型五次伪造关系。

coverage 原样为 22/22（9 版本＋13 候选），11 项 out_of_scope / deferred / unconfirmed，0 not_repair。v10、v13、v14 以及图片候选都正确留在分母而标本题未调查。前置扫描 explained 的 reason 明确它是 S3 输入依据，不是“它执行了修复”；这类标注不应一律判错。未调查的 #23492 留 out_of_scope 是允许边界，无须为了达到清单完整而追完无关信息。

consistency 与 coverage advisory 都为 0；这只表示有限规则未命中，不认证 S3 执行措辞、H5 完整性或“首次出现”的语义。因此完整报告仍是部分通过，不是全面无误。

## until 与后置验证范围

rep2 显式 `until`=0、`until_seq`=0；`until_ts` / `since_ts` 各 1 次。唯一为 #40（`call_Gtb8tpQ5v7d1DlGrRT4dN2iL`，L263）：全池 `product-price-suffix`，从 2026-07-26T21:30:17.239Z 至 21:48:57.218000Z。返回 fixer 写 attempt 脚本的线索，不是早期 Read；没有打开新的运行视觉比对。故“本次范围没有核到行为复验”可以保留，“全池绝无行为验证”则不能由一个关键词成立。

没有观测到显式 seq-only until 缺陷的触发。已核核心 Slice8 Read 返回早于 Write；这不是对全部内部 v 窗口的完备时序认证，也不是对尚在另行修复的引擎问题给出 clean bill。

## 收支观察与稳定性结论

| 指标 | rep1 | rep2 |
|---|---:|---:|
| wall 秒 | 280.17 | 306.46 |
| MCP 调用 / 拒绝 | 60 / 6 | 40 / 4 |
| leaf 返回字符 | 230,543 | 191,833 |
| input 总量 | 876,504 | 1,934,960 |
| 其中 cached | 759,808 | 1,830,400 |
| uncached input | 116,696 | 104,560 |
| output | 11,945 | 10,696 |

rep2 使用一次 file `v_from=10, v_to=18` 汇总 diff，没有六次单独 diff 调用；少 20 次调用、返回字符少 16.8%，但 wall 多 9.4%、累计 input 多 120.8%。cached 已含于 input，reasoning 已含于 output，美元 cost 仍 null，不作账单推估。

两次结果都保留：rep1 的错误归因是失败观察，rep2 的恢复是成功到有限核心的观察。可以说明系统有能力找到这条证据链，但此次两次重复未稳定产出相同质量；不能挑较好一次替换基线，也不能以两次样本估计泛化成功率。
