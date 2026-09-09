# V7 legacy raw 基线裁决（Dice / Splash 各两次，定稿）

本版包含 `formal-v7/dice-entry/runs/raw/rep1`、`rep2` 与 `formal-v7/splash/runs/raw/rep1`、`rep2`。实际模型均为 GPT-5.5 / medium；首轮 Dice 于 2026-09-09 19:02:41 UTC 完成，Splash 于 19:11:31 UTC 完成。Dice rep2 于 19:26:37 UTC、Splash rep2 于 19:34:03 UTC 完成，各自独立裁决见末节。不以某次代替重复试验，不以工具组报告或 holdout 为原始真值。

使用冻结 `reference-v1/legacy-reference.json` 的旧 protocol 核心问题和原始 facts 数组。核心回答与全量回答分开；不要求逐字复述每条 Read/每个术语，不因 raw 没有 YAML、basis 或结构化 coverage 扣分，也不强求题外所有文件修复。细项状态是定位缺口的量尺，不冒充整体准确率。原句、原始位置、引用核对与补充证据 SHA 见 [JSON](v7-baseline-legacy.json)。

## rep1 结论

| 组/题 | 核心回答 | 原始 facts 细项 | 全量边界 |
|---|---|---|---|
| Dice D1 测试桥 | partial | 2 supported、1 partial | 后置测试桥的原因/实施正确；初生成输入链没有还原，后置验证通道状态不完整。 |
| Dice D2 异常观察者 | supported | 3 supported | 明确 ECAT 派发、SDK 适配、代码变更、构建/WARN及未触发回调的边界；不因没逐字列三次 Edit 扣分。 |
| Splash S1 返回处理 | partial | 2 supported、1 contradicted、1 omitted | 初版实现与 Slice11 错误解释找到，但删除作者错归、后置构建漏掉。 |
| Splash S2 系统栏 | partial | 2 supported、1 partial | 已有要求未充分传递及后置修复方向正确，漏掉主题在生成前已进入主会话的具体证据。 |

因此，Dice 的 5/6 完整 facts、Splash 的 4/7 完整 facts 都不等于整份报告准确率或整体成功。Splash 错作者属于实质归因错误，不能被其他事实命中掩盖；Dice 的更多未知也不自动比完整追到后置证据更正确。

## Dice：桥的阶段解释正确，初生成输入与后续通道少查了一段

原始池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool`。

D1 报告说明桥在 `arkts-ui-verifier` 第 3 步引入，受 `@ComponentV2` 与单页零导航约束，收敛为 EntryAbility 消费 Want token；列出 TestDataSetup、import/常量、onCreate/onNewWant、consumeTestWant 的变化，并正确拒绝把构建或页面落树当 AppStorage 桥键已验证。

缺失的是题目明确问的“生成时已有输入”：
`81e0a463.../subagents/agent-a349784d2663f1f0a.jsonl` 中，页面 Read L51/L52、F001 Read L53/L54、沉浸式 skill Read L57/L58 均在 EntryAbility native Write L71/L72 之前。报告从测试阶段派发开始，引用后续 Edit 的旧 onCreate 虽能说明加桥前局部状态，不能代替这一生成输入链。D1.f1 标 partial；“后置要求不自动等于初生成遗漏”仍 supported。

D2 的 ECAT 派发（`2f01bcdc...jsonl:L100`）、fixer 的 SDK 决定、import/注册/实现三个变更均正确。原始 fixer `agent-a27497cfed8c44856` L23/L24 读取入口，后续 SDK 探测，L41–46 三次成功 Edit；L55/L56 diff 支持最终变化。报告主要引 builder `agent-a635575c78cd15ff6:L82` 终态总结；原始 L48/L52 也有直接成功构建/具体 may-throw WARN 回执，所以不将真实构建结论判错，但保留“总结≠执行回执”的引用强度区别。未宣称 observer 的运行时回调或 crash 回收已测试。

### 额外后置状态审计：canonical DEFERRED 不等于没有等价通道结果

报告末尾写“UI TDD 当前是 DEFERRED”，并停在 `593d4e86...jsonl:L23` 的 round-0 0/10 与 L82 的启动/landmark。canonical arkxtest 仍 DEFERRED、桥键仍未知，这些都成立；不完整之处是没有交代同一转录后面的 round-1。

新增核到的是**原始工具回执，不只是总结主张**：

- `593d4e86-a947-4e62-8027-013014c2bafc.jsonl:L256` Bash 执行 `replay_ui_cases.py`；L260 同 ID `call_1a4f6f34ebd54fabb47c8373` 返回逐例 PASS、`用例 10/10 PASS，HARD 断言 21/21，UNOBSERVABLE 显式留痕 7`、`EXIT=0`，时间 2026-09-03 21:01:35.309 UTC。
- 输出同时明确 `AppStorage['__TEST_MODE__']===true` 为 NOT_ASSERTED，跨进程不可观测。因此 **10/10 不能升级为桥键认证，也不能抹掉 7 项未观测断言或 canonical 通道的阻断**。
- L265→L267 的第二个 Bash 回执列出 14 个 dump、results.json 汇总，以及 onCreate / LoadPage / onNewWant×3 的 hilog。后续 final-summary 的 PASS 是对这些记录的报告，类别应分开。

该记录不在旧 D1 facts/witness 列表中，故作为独立补充，不修改 `reference-v1`、不悄悄加核心分母。未来工具组/raw 组须采用相同后置状态标准。它修正的是验证进度叙述，不推翻“AppStorage 桥键未被直接观测”。

可复核 SHA256（对原始 JSONL 单行去换行；正文为解码后的 `message.content[0].content`）：

| 回执 | 原始记录 SHA256 | 正文 SHA256 |
|---|---|---|
| L260 | `d0bdea3e3501e2137d49a16f818fb36770ef4163c71e90b29e018a0e3a066b2d` | `bb8d9a53c01927641445a511c60e00838367ec0c27a9e09b4ea7db267a0acfae` |
| L267 | `2894f5e5712d2846271d4328082daa0285e23269fb3a7d881309f69ea2b2bc80` | `cf8255f39d135430b3dcabe89594b72b9cf03b28c566f906d640efbe591ebb03` |

## Splash：不能把装配删除与 Slice11 后续决策合成同一作者

原始池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/splash/pool`。

S1 报告正确指出初生成者读到“返回无效”规格，并在 native Write 写入 `.onBackPressed(() => true)`。它也找到 Slice11 的 `isModal:true` 解释、D-020 的页面外壳差异、历史 finding 反驳及 fixer 的 onWillDismiss 修复。这些都保留。报告“方向正确”结合代码与后置验证限定，按已有实现理解，不无依据判成“初版已在设备验证”。

但其首段将“把页面改成根 Navigation”归于 Slice11，漏掉真正删除动作：

- `9b3105a2.../subagents/agent-aentry-setup-07108f5df45c357c.jsonl:L123` 的 Edit old_string 包含 callback，new_string 删去它，改为 Navigation 路由/外壳及“API 不暴露、留给 F001 评估”的注释；L124 明确成功，时间 07-24 02:32:52.249 UTC。
- Slice11 的隐私控制器和 D-020 是之后的接线/决策。责任链应保留 entry-setup 删除与 Slice11 承接，而非合并为一个 Slice11 动作。故 S1.f2 为 contradicted。
- 后置 `ff019.../subagents/agent-af0e3d2ae54dbf769.jsonl:L36/L37` 有真实第二轮 `EXIT=0 / BUILD SUCCESSFUL`；报告没有交代，S1.f4 为 omitted。它没有断言“全池无构建”，不把遗漏升级为相反断言。

S2 正确区分 safearea/透明系统栏与显隐调用，找到后置 theme Read 和入页隐藏/离页恢复。关键缺口是没有找到主会话 **07-23** 的早期 theme 读取：

`9b3105a2-85ec-4889-9786-b3c220f06754.jsonl:L404` 在 2026-07-23 12:36:37.214 UTC 已返回 `Theme.SeceretBox.Launch` 的 `android:windowFullscreen=true`，早于初生成 Write。报告只引 fixer 07-26 的 themes 读取，知道“源语义原本存在”，没有证明“生成前主会话已经拥有”。S2.f1 因此 partial，不因结论方向相同就记完整命中。

它没有声称首次出现于 finding，也没有把搜索命中冒充生成者已读或指定某个 skill 为唯一根因；这些边界不应扣错。修后完整设备复验未知仍合理。

## 引用与观察成本

Dice 正文 10 个、Splash 14 个唯一 native call/tool_use ID 均在相应原始池的 canonical tool_use/tool_result 块找到；定位成功不等于原因支持性。完整定位表在 JSON，错作者仍按原始事件裁决。没有要求 raw 提供 YAML。

| rep1 观察值 | Dice | Splash |
|---|---:|---:|
| Input（含 cached） | 1,703,830 | 3,516,725 |
| 其中 cached | 1,464,832 | 3,261,952 |
| Output（含 reasoning） | 9,267 | 16,208 |
| Input + Output | 1,713,097 | 3,532,933 |
| 原生命令调用 | 21 | 31 |
| 返回字符 | 4,313,468 | 6,384,849 |
| 模型运行秒 | 208.537 | 527.107 |
| 端到端秒 | 211.417 | 539.868 |

cached 不另加，reasoning 不另加。返回字符不是精确模型 token 数；这里只报告已保存 metrics 的观察值。各次保留独立裁决，不从单个文件的两个重复声称普遍质量或成本胜负。没有源代码、冻结运行、参考文件修改，没有模型调用。

## Dice rep2 独立裁决

旧核心量尺仍为 **5 supported、1 partial / 6**：D1 核心 partial、D2 supported。不是用 rep2 替换 rep1，也不因为多写未知加分。

- D1 仍从测试阶段的 design/manifest 前置检查开始，没有追原 converter 的 page/F001/immersive Read 与生成 Write。桥的实现与阶段归属正确，这个旧核心缺项保持不变。
- 后置状态比 rep1 完整：明确引用 `332534c3...jsonl:L1` 前置 worker 文本的 round-1 10/10 PASS，同时保留 SMOKE AppStorage 为 UNOBSERVABLE，并称其为来源主张。因此不再笼统停在“当前 DEFERRED”。它没有打开补充的 L260/L267 原生回执，不把这项改善夸成全部运行证据已核；桥键未知仍正确。
- D2 明确核过 SDK d.ts、import/注册/实现及后置静态 crash_risk=0；区分静态降分、编译通过与异常回调实测，核心有原始支持。主要编译引用 `2f01...jsonl:L206` 实际为 queue-operation/enqueue 的 task-notification，内含 builder 总结，不是新的一条 native 构建 stdout；真实原生回执在 builder L48/L52。不能混同类别，也不因此把真实构建事实判假。
- 22 个绝对文件路径＋物理行链接均解析为池内原始 JSON。正文工具 ID 多用省略前缀，不能单靠前缀当唯一 ID；完整文件/行定位仍可复核，raw 不要求结构化引用格式。

| Dice 观察值 | rep1 | rep2 | 均值 |
|---|---:|---:|---:|
| Input + Output | 1,713,097 | 1,114,764 | 1,413,930.5 |
| Input（含 cached） | 1,703,830 | 1,104,559 | 1,404,194.5 |
| 其中 cached | 1,464,832 | 948,736 | 1,206,784 |
| Output（含 reasoning） | 9,267 | 10,205 | 9,736 |
| 命令调用 / 返回字符 | 21 / 4,313,468 | 15 / 3,187,665 | 18 / 3,750,566.5 |
| 模型运行秒 | 208.537 | 223.887 | 216.212 |
| 端到端秒 | 211.417 | 227.003 | 219.210 |

两次核心缺项稳定，后置通道描述不同。这里不由 token 波动推断哪次“更聪明”，也不将单文件两个样本外推为全套准确率或性能胜负。

## Splash rep2 独立裁决与联合结果

旧事实量尺为 **4 supported、3 partial / 7**，S1/S2 核心仍均 partial。它找到了主 root L404 的早期 theme 和后置 builder，且不再把 Navigation 删除明确错归 Slice11；但没有找到 entry-setup 具体删除、入页隐藏写入，并新增一条实质错误引用。

| 原事实 | rep2 | 原因 |
|---|---|---|
| S1.f1 初版有返回代码及来源要求 | supported | 点明 converter native Write L71 及对应注释；未把自述当额外验证。 |
| S1.f2 entry-setup 删除，之后 D020 | partial | 识别 batch2 前已有 Navigation，承认移除点未知；原始 entry-setup L123/L124 仍没查到。 |
| S1.f3 isModal 错误解释→finding→onWillDismiss | partial | 前两段正确；onWillDismiss 的唯一具体引用不支持所引文字，见下。 |
| S1.f4 后置 builder 构建通过 | supported | 引 builder L54 总结，原始 L36/L37 回执支持；不要求逐字列回执才能给核心事实分。 |
| S2.f1 生成前主会话已读 windowFullscreen | supported | 这次具体定位 root L404，结合早期规约/源读取说明，不要求复述 UTC 时间才能给分。 |
| S2.f2 概括性输入与传递证据缺口 | supported | meta L16 的 full_screen_page/needs_immersive_safearea/style_sources 与具体主题值分开。 |
| S2.f3 入页隐藏＋离页恢复 | partial | 只定位 L488 恢复；明确说隐藏写点未定位，实际 L485/L486 可查。 |

重大引用问题：报告将 `ff019d8a-5172-4cdd-8ce3-77a21682c1b6.jsonl:L897`、`toolu_01CnpgzerWYWKBoNVRKLskZF` 引为“隐私弹窗控制器新增 onWillDismiss…D-020 只覆盖弹窗之外”。该 ID 与行真实存在，但实际内容是 **07-26 04:46 的 Bash「生成 t1b prompt」**，生成安全复核/接力/提示文件，command 全文没有 onWillDismiss 或 D-020。L898 只是 prompt 生成回执。真实修复是 fixer 子转录 L346/L347，相关说明在 L608。

因此不能因事件 ID/行能定位而认证该引文；也不能因 onWillDismiss 这个结论恰好符合真相就给这一证据链满分。17 个文件＋行定位均有效，这个错引正说明机械定位与原文支持性不同。

| 原始组 | rep1 细项 | rep2 细项 | 两次核心/全量结论 |
|---|---|---|---|
| Dice | 5 supported / 1 partial | 5 supported / 1 partial | D1 均 partial，D2 均 supported；rep2 后置通道叙述更完整，仍缺初生成输入。 |
| Splash | 4 supported / 1 partial / 1 omitted / 1 contradicted | 4 supported / 3 partial | S1/S2 均 partial；rep1 错作者，rep2 错引文；不能择一替换另一份。 |

| Splash 观察值 | rep1 | rep2 | 均值 |
|---|---:|---:|---:|
| Input + Output | 3,532,933 | 3,078,206 | 3,305,569.5 |
| Input（含 cached） | 3,516,725 | 3,063,154 | 3,289,939.5 |
| 其中 cached | 3,261,952 | 2,801,152 | 3,031,552 |
| Output（含 reasoning） | 16,208 | 15,052 | 15,630 |
| 命令调用 / 返回字符 | 31 / 6,384,849 | 26 / 7,735,246 | 28.5 / 7,060,047.5 |
| 模型运行秒 | 527.107 | 442.266 | 484.686 |
| 端到端秒 | 539.868 | 454.322 | 497.095 |

四份合计的 26 条旧事实观察为 18 supported、6 partial、1 omitted、1 contradicted，仅作细项盘点，不称整体准确率。Dice 10/10 等价通道回执仍独立列为补充，不改旧 oracle，也不把它升级为 AppStorage 桥键实测。
