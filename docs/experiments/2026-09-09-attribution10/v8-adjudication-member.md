# V8 Member rep1：引用接口可用，但没有转化为上游调查

固定六事实为 **4 supported、2 partial**；S3 缺 H5 既有透明例外，S4 仍缺“Slice8 写前已读正确 Kotlin”。另有尾后动作倒挂末版的重大标注错误。此次不能称为完整语义成功。

冻结源 `b540cb2`，实际 GPT-5.5 / medium / native，2026-09-09 19:31:06 UTC 完成。同一 `reference-v1/legacy-reference.json`、同题、同原始 Member 池；不以新工具正文/机械检查为真值。只读源材料和本次已保存结果，没有改源、冻结报告、参考或调用模型。逐项原句、完整定位及元数据见 [JSON](v8-adjudication-member.json)。

## 固定事实逐项裁决

| 原事实 | 状态 | 本次报告与原始证据 |
|---|---|---|
| S3.f1 三处为 AppLoad、PayAgreement、RenewRule | supported | 正文逐名列 206/704/728 三站点。原始 fixer L80/L81 支持。 |
| S3.f2 跳过已有 mask，AppLoad 透明，其余缺失项 Palette | supported | 脚本前缺失扫描、分支和值正确；coverage 明称“真实执行”。原始 L103 先 write 后 report.append，同 ID L104 成功输出目标 3 sites。 |
| S3.f3 3 sites 是总数；H5 已透明且被跳过 | partial | 明确 1 透明＋2 Palette，不误称 3 深色。但只写“4 controller、已有 1 mask”，全文含 coverage 都没有 H5 名称/既有透明说明；L74 grep 被列未调查。V7 两稿曾在 coverage 点名，这次不能同样算完整。 |
| S4.f1 Slice8 写前读到正确 Kotlin，却重写为非滚动整串 30vp | partial | 正确 id 出现在红节点，但未打开该 agent、原始 Write、v7 正文或早期 Kotlin Read。报告承认“未展开 v7 原文”。没有建立本题关键输入→错误写入关系。 |
| S4.f2 先 ForEach 片段，后固定 priceDigits/priceSuffix 双 Span | supported | 分散在 PRICE、COMPILE 与 notes 中，仍按完整提交计入；两阶段、30/16和保留动画分支均正确。原始 fixer L528/L529、L592/L593。 |
| S4.f3 fixer 引入 private helper，builder 两次 Edit 后构建成功 | supported | actor-level 过程与实际构建回执正确，未把 builder 当错误来源，也未把构建通过当视觉复验。精确版本错挂另列，不用它抹掉确实答对的过程事实。 |

原始池为 `.../attribution10/formal-v1/member-center/pool`。关键来源：

- `9b3105a2.../subagents/agent-aslice8-pay-80bbb1f44b77da0f.jsonl:L21/L24`：07-24 15:33:49 发起、15:33:51 返回 Kotlin；代码 276–282 行以 replaceSpan 只放大数字到 30。
- 同转录 L264/L265：16:04:37 成功整文件 Write，非滚动 priceText 仍为单 Text 30vp；这是 file v7 的真实写者 agent@v12，且正文包含已有 H5 透明。
- `ff019.../subagents/agent-a68daf720e780b4c2.jsonl:L592/L593`：07-26 21:30:17 二次价格脚本加入 private static priceDigits/priceSuffix；发生在 40 个正式效应之后，没有 agent@v41。
- `ff019.../subagents/agent-af0e3d2ae54dbf769.jsonl:L23/L24、L32–35、L36/L37`：private 错误、两次成功 Edit、原生第二次构建 EXIT=0 / BUILD SUCCESSFUL。

这些是固定原始证据，不把“没看够”变成客观不存在，也不因为模型更保守就加分。

## action(ref) 和真实 id 的实际效果

18 次 action 全用 `ref=#完整引用`，18 次均返回成功，没有猜 action owner id 的失败。这是观察到的接口功能改进；不能把全部 token 差异都归因于它。

正确 Slice8 id 与续查入口确实送达，但没有被跟进：

| 实际事件 | 保存位置 | 后续行为 |
|---|---|---|
| maskColor search 返回 file v7，并带真实 `agent-aslice8-pay-80bbb1f44b77da0f` | 第 8 次调用；transcript L63 | 未打开 v7。 |
| blame(v16, changed=true) 返回未知与 recovery | 第 11 次；L67 | 明列 v7、native Write 原文引用、真实 writer id、累计 agent 查询，仍未打开。 |
| file v16 脊柱再列同一真实 id | 第 12 次；L78 | 最终结论使用这个 id，但没有访问该 agent。 |
| 唯一 agent 调用请求 fixer@v33 | 第 28 次；L144 | via 指向尚未打开的 agent 自己，被拒；之后没有重试。 |

因此本次有 **1 次 blame recovery 返回，0 次跟进其 v7/实际 writer/早期输入入口**；agent 调用 1 次但成功 0 次。另两次 file 自指 via 在未打开任何节点时被拒。action 查看原文不等于自动打开其作者节点，不能把这三次拒绝伪记为调查访问。

recovery 的警告原文为“最近全文写者不是被替换行作者，不自动归责”。它还列了 edit-miss 首断点、8 个中间正式版本、1 个显式效应候选、64 个未核提及及补丁原文。报告却说明“本进入点基于 sessions 脊柱和修复前读取输出”。这表现为使用索引与后置观察替代具体上游核查，而非成功完成恢复调查。原始 v7 实际确有错误代码，不代表这种证据用法已经证明了该精确版本与当时输入。

3 次 until_ts search 全用于 07-26 后续证据；没有生成前输入窗口核查。没有 seq-only until。

## 边界 warning 有送达，但没有修正核心错绑

第一份 check（第 37 次，L202）为 **3 errors + 2 warnings**：

- builder@v4 越界；
- fixer@v41 的 entry/node 越界；
- 同节点角色冲突；
- Slice8@v12 的 actual 引用是 07-26 后置读取。

两次 check 之间没有新证据调用。最终稿将 v4 改 v3、v41 改 v40，删除重复角色项，仍保留红节点。它不是简单“删红清零”，但也不是证据补足：

> “这里用 fixer-r1@v40 表示该候选写之前的最后可导航 agent 状态，具体进入动作以 evidence 的 #15731 为准。”

这段主动披露了替代做法，**披露不使替代成为合法的精确事件归属**。上一状态不是尾后错误进入动作；不能为了获得有效坐标将事件移到末版。

最后 check（第 38 次，L211）仍是 **needs_review，0 errors + 4 warnings**，不是 mechanical_clear。其中明确返回：

> “同一 agent 的证据事件在节点 v40 窗口之后（喂养槽 41），没有对应正式效应版本；不重绑到末版，也不制造新版本。”

其他三条是后置实际证据提示。它们只陈述时间/窗口，不自动判断因果错；但最终报告没有解决明确的窗口不一致。未发现检查自动改角色、造新版本或声称语义认证。

S4_PRICE 的实际证据仍是后来 fixer 的 L516。它可以证明当时读到单 Text 30vp，不独自证明两天前 Slice8 的输入或跨 edit-miss 的完整状态。真实早期 Kotlin 与原生 v7 Write 都可用却未查询，所以“没进一步追溯 Android 原工程”不能替代本池内已提供输入的核查。

## 完整标注：有改善，不能掩盖剩余错误

正向变化：

- S3 不再编造正式 mask repair before/after 对。
- v10、v13、v14 和图片脚本正确列 out_of_scope，不说这些真实改动是 not_repair。
- L501 正确作为价格 finding，不再称题外 banner 报告。
- L615 明确未调查是允许的，没有将它虚称纯 CTA 或无关；但其中源码比例纠正仍没补进核心调查。

结构上 38/38：7 正式版本＋31 候选，17 explained、21 out_of_scope、missing=0、not_repair=0。它们不是 38 次真实修复，更不表示每条归因已证真。

本次没有使用 builder 的不确定 v14 Read 去伪造 v14 私有 helper 快照（V7 rep2 的错误）；但换成了明确的尾后动作→agent@v40 错绑。因此不宜只看少了某个旧错误便宣布整体提高。

## 成本与结论边界

| 指标 | V8 rep1 |
|---|---:|
| Input（已含 cached） | 762,351 |
| 其中 cached | 672,768 |
| Output（已含 reasoning） | 18,782 |
| Input + Output | 781,133 |
| 工具调用 / 返回字符 | 38 / 123,739 |
| 模型运行 / 端到端秒 | 525.383 / 539.277 |

相对 V7 Member 两次均值 1,349,627，总 token 观察值减少 **42.1%**；运行时间相对均值 431.298 秒增加 **21.8%**。只有一个 V8 样本、且包含多项接口改动，不能据此宣称稳定收益或单个机制的因果效果。V7 两稿各 5 supported＋1 partial，本次 4＋2，核心事实没有更好；“省 token＋提高原始事实准确率＋UI 忠实”联合验收仍未证明。

最终保存稿 matched，仅说明与检查过的正文一致。verdict.yaml SHA256 为 `a2eacaa702e45d5ce94e7d29c6d879729b3a500dc6b61fdcb0c2ff8b2f37d7c6`；canonical document SHA 为 `d3eff5c2ef999c6f2b7978fc0b6d1c974d0bf8d5b927150aa6b67e646329935c`。不能把 `verdict_ok=true`、matched 或可定位红节点当作语义通过，也不能把出现在结论中的 Slice8 节点当成实际已访问。

