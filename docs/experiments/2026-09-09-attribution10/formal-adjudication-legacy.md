# Formal v1：legacy 六题逐项裁决

审计时间：2026-09-09 12:53 UTC。三个 tools/rep1 均已结束；本页只读复核冻结材料，没有调用模型、重跑历史命令或修改 frozen source / pool / run / reference。参照 `reference-v1/legacy-reference.json`，不是把参考答案当成独立因果真值；关键争点已回到原始事件核对。机器可读数据见 [formal-adjudication-legacy.json](formal-adjudication-legacy.json)。

实验根目录为 `C:/Users/hongy/projects/_migloop-eval-20260909/attribution10`；下文 `formal-v1/<case>/...` 和 `reference-v1/...` 均相对此目录。本文“调用 #N”按冻结 `probe._transcript_calls` 的 primary transcript 顺序计数；`L` 是该 run 的 `transcript.jsonl` 物理行，历史事件另列原始 pool 路径和行号。

## 结论速览

| 题 | 核心事实 | 归因 / 责任边界 | 验证层次与缺项 |
|---|---|---|---|
| D1 测试参数桥 | 通过：后续测试阶段明确要求并加入，未倒灌为初版明确遗漏 | 通过：输入关键词零命中只作为有限范围旁证；没有强造故障 entry | 10/10、onNewWant×3 来自已打开的历史生成总结；AppStorage 不可直观测边界正确。“证明”宜改为“历史报告记载” |
| D2 异常观察者 | 通过：ECAT 派发、SDK 读取、三次 Edit、两个构建目标 | 通过：不把后置框架要求强归责初版 | 编译成功有原始结果；明确不等于 observer 回调触发。漏报 may-throw WARN 属小缺项，不是把 0 ERROR 误当 0 WARN |
| S3 mask | 通过核心：三处总数＝AppLoad 透明＋两个普通弹窗暗色 | 未证明最初责任；正常 fixer 被放进 entry 不自洽 | 不能证明三处设备复验，报告正确保留。repair v9→v10 只是时间窗，不是 mask 版本锚点；H5 已透明、被跳过未明确补齐 |
| S4 价格 | 修复事实通过：中间 ForEach→最终两个 Span；private helper→编译错→去 private→成功 | 部分：漏掉最近 Slice8 整文件重写及其已读 Kotlin 输入；正常 builder 被列 entry 等角色不自洽 | 正确区分编译与视觉 / 全价格格式验证 |
| S1 返回键 | 大部分通过：初版已有拦截，entry-setup 删除，D-020 / Slice11 错误解释，后置修复 | 部分：尚未追 D-020 制定者；删除点被标“带病传递”没有区分该动作自身新引入的变化 | “可用的回调”超出静态写入证据；遗漏另一 builder 的成功构建，但未明确声称整个池没有构建；修后设备行为仍未知 |
| S2 系统栏 | 大部分通过：早期主题事实存在；后置隐藏 / 恢复实现正确 | 部分：有限关键词零命中被写成“实际只获得 / 未传给”，过强；主题传递链未复原 | repair.before=v57 已包含此次 window import，不是整轮修复前态。没有独立修后设备验证 |

Splash 的 YAML 在第 116 行以未引用反引号开头，机械解析失败；因此该 run 的 schema=false、coverage accounted=0/24 必须原样保留。人工能读到六题相关文字和覆盖行，不等于修好了该产物或机器接受了它。Member / Dice 的 schema 与 coverage complete 也不认证语义归因正确。

## Member：事实找到，坏行来处没有追到最近重写

S3 的 [报告](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/member-center/runs/tools/rep1/result.json) 准确区分了 AppLoadDialog→`Color.Transparent`、PayAgreementDialog / RenewRuleDialog→`Palette.DIALOG_MASK`（`#8C000000`）。调用 #7（`call_KEaI9q1J4XnmHceRUdZDpGSF`，L56）返回脚本原文；原始 fixer L103 确实先跳过已有 mask，再按 AppLoad 分支选值。原始扫描 L81 和 Slice8 L264 可核三个缺项及已透明的 H5。报告未把 3 sites 当三个深色弹窗，且承认只部分读回、没有三处设备闭环。

但 `repair.before=@v9 / after=@v10` 并非这个脚本的文件状态差异：正式 v10 对应 fixer L436 的底部 CTA width / margin 调整（`#23849`），报告自己的 coverage 也把 v10 写作题外布局变更。两端节点存在，所以不是“编造节点”；错误在把邻近版本时间窗装进修复语义锚点。报告已主动披露此限制，应保留这份诚实，同时把该修复锚到真实 candidate / action，不能仍宣称该版本区间就是 mask 修复。S3 entry 仅含 role=正常 的 fixer@v5，也未给出它作为故障进入点的证据。

S4 正确恢复了修复过程与编译问题，没有把 ForEach 当最终态，也没有把 private helper 问题归给最初 converter。但其上游核查只查初始 conv-member，未查最近的 Slice8：

- 调用 #3（`call_DGlWrFamEB7uy12vIumXCfH7`，L38）已返回完整写者脊柱：`Member@v7 ← slice8-pay@v13`，1194 行全量写，`#20723@L264`。不是返回截断或账本没有这条入口。
- 调用 #20（`call_hlwFy4DyUQQPvUHMMTr0iPke`，L134）给 v11 原生 diff，旧侧为 `Text(this.animatedPrice.length > 0 ? this.animatedPrice : this.item.priceText).fontSize(30)`，但仅有本次 fixer 名，没有旧侧来源提示。之后六次 diff 都停留在 repair 单版，0 次 blame；没有打开 Slice8 agent / action / file@v7。
- 调用 #48–55 查的是初始 conv-member 的 `AbsoluteSizeSpan`、`replaceSpan`、后缀及 Write。最后两个 action 搜索在 v1 原始 Write 中找新版表达式，均无命中后退回分页片段；恢复入口仍在，并非分页丢失。
- 原始 `9b.../subagents/agent-aslice8-pay-80bbb1f44b77da0f.jsonl` L24，2026-07-24T15:33:51.671Z，Read 结果已有 Kotlin `showNowPrice.replaceSpan(Regex("\\d+")) { AbsoluteSizeSpan(30, true) }`；L264，16:04:37.440Z，实际全量 Write 仍统一 `.fontSize(30)`。这支持“最近重写已读源码逻辑却未落实”的近因。中间 v8–v10 内容未知，不能进一步伪称逐行连续性已被证明。

S4 的 entry 还把 role=正常 的 builder@v3 纳入故障进入集合；fixer@v45 被标“带病传递”但理由讲的是修价格，本身未解释传递了何种错误。final fixer 的 private helper 编译责任有证据，与这些角色自洽问题应分开。

## Dice：有界问题回答成立，保留证据等级

[Dice 报告](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/runs/tools/rep1/result.json) 对 D1 / D2 都保留空 entry，没有把后续阶段扩展强造为早期明确违约。生成前池搜索给出了时间、agent/file 数和未知版本排除范围，报告也明确“未检索到”不等于更早所有要求都不存在。

D1 调用 #26（`call_BAYgG7iQb5kGboMYPYdTbBLk`，L147）打开 `spec/verify/ui/round-1/final-summary.md@v1` 的完整 66 行。它是历史 agent 通过 Write 生成的总结（主会话 593d4e86，`#1350@L291`）：记载等价通道 10/10 PASS、onNewWant×3，同时写明 7 个不可观测探针、AppStorage 只能旁证、canonical 通道仍 DEFERRED。当前报告保留了 AppStorage 边界，值得给分；但是并未打开该总结所指的 `results.json`、hilog 或逐项设备命令，因此“后续验证证明……”不应由审计者升级为本次直接核验结果。核心问题不要求穷尽重审所有设备材料，裁决为核心通过、措辞需降为历史报告记载。

D2 调用 #24（`call_k6Bl25eEyXaZd9G6k8KMTsC7`，L133）返回 builder@v2，其中已经有 ohosTest 的原始输出片段 `BUILD SUCCESSFUL` / `BUILD_EXIT_CODE=0`；主构建成功主要通过同次 agent 返回的历史叙述可见。只读复核同 pool builder 原文 L44/L48 确认 default 编译实跑和退出码 0，L64/L68 确认 ohosTest 成功、实跑与 HAP，L52 确认 EntryAbility:140:5 的 may-throw WARN。报告不声称 0 WARN，也明确不证明异常回调 / 日志已运行，故 WARN 漏项不应升级成整个 D2 失败。

43 次 MCP 中 3 次拒绝：两次非首跳 `via=sessions`，一次打开没有已登记版本的 judge@v1。无 action / blame 调用；这些是查询协议成本，不改变已返回证据的真假。

## Splash：方向有证据，不能扩大输入排除与运行时断言

[Splash 原始报告](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/splash/runs/tools/rep1/result.json) 虽 YAML 失败，仍能人工核语义。

S1 找到了关键历史链：初始 Write 含 `.onBackPressed(() => true)`；调用 #53（`call_fhfVi4E7jZMT41f4UhPwWFjA`，L258）直接给 entry-setup@v7 的删除 diff；Slice11 的 D-020 派发、`isModal:true` 解释与后置 `onWillDismiss` / 弹窗复位也有对应返回。静态“存在且意图符合契约”可成立，开头“删掉了可用的回调”则缺初版运行时验证。后置 finding 也是历史证据，不是本次审计亲自设备复验。

报告明确停在 D-020 既定派发、不追制定者，属于已披露的上游边界；但验证调查只围绕 finding 名和预期文本搜索，没有查询 builder。冻结 pool `ff.../subagents/agent-af0e3d2ae54dbf769.jsonl` L37，2026-07-26T21:46:28.608Z，有真实 `EXIT=0` / `BUILD SUCCESSFUL`，位于其全池验证搜索时间窗内。应补“后置成功构建，行为闭环仍未知”，不能把没搜到某两个短语当作充分的验证全貌。报告没有直接说“整个池没有构建”，因此裁决为缺项，不指控捏造无构建结论。

S2 的时间方向不是靠参考答案替它补上的：调用 #30（`call_nv6nTnMb9ZNtzJ3D3dzC1rwP`，L161）虽然截止到 Jul26 修复前，但实际返回明确 `windowFullscreen` 的主会话 `#232@L402 T+0:33` 和设计文档 T+0:59；初始生成是 T+14:04。原始主会话 L404 在 2026-07-23T12:36:37.214Z 已返回 Launch theme 的 `windowFullscreen=true`，早于 conv-splash L71 的 2026-07-24T02:07:13.800Z Write。所以“要求早期已存在，不是修复才新增”的事实分应给。

限制在另一方向：生成 agent 的两个关键词零命中，加页面 spec 中 `windowFullscreen` / `状态栏` 零命中，不能穷尽证明“实际只获得沉浸式而没有隐藏系统栏信息”。调用 #50（L245）自己的正文还明确 `page_type=full_screen_page`；spec 存在 full-screen 语义，是否足以落实系统栏行为、具体主题如何传递，仍需核输入和生成链。建议表述“尚未建立明确主题要求到该次生成的传递证据”，而不是把 converter / spec 的缺陷进入角色当作已确定责任。报告自己的 boundary 承认未追 spec 裁剪，但摘要未保持同等谨慎。

S2 修复范围也偏一版：coverage 正确把 v57 归为 window import，但 `repair.before=v57` 已在该轮修复内。若描述 import＋隐藏＋恢复整个修复，应从 v56 起；若只说剩余步骤，必须缩小标题和范围。S1 v51→v56 包含一个已明确 unresolved 的题外进度条 v55，独立 coverage 已披露，不能仅因区间中存在别的改动就把所有锚点一概判假。

## 通用、小范围证据返回建议（本轮不实施）

观察到的 Member 失败更像“最近坏行来处未追”，不是账本漏入口。可评估在 diff 尾部增加有预算的旧侧来源导航：相邻端点已知时复用 `blame(changed=True)`，只列改变行的来源分组、实际 source action 和继续查询命令；未知时明确无逐行归属，并给最近可复原基线 / 中间未知版本作为候选入口。

关键防误导条件：本次离线对冻结 source 的 `blame(Member, v=11, changed=True)` 实测为 `known=false, comparison_basis=unavailable`，因为 v10/v11 都未知。最近可复原的是 v7←Slice8@v13，但不能把跨 v8–v10 断点的候选基线直接叫“坏行作者”。冻结 [atoms.py:905](C:/Users/hongy/projects/_migloop-eval-20260909/source-b197227/src/migloop/atoms.py:905) 已正确拒绝未知端点；[atoms_text.py:796](C:/Users/hongy/projects/_migloop-eval-20260909/source-b197227/src/migloop/atoms_text.py:796) 对已有 diff 只回该 diff，没有这类旧侧提示。保留 fail-closed 和原文恢复入口，不能为导航便利抹掉不确定性。

这里只记录待验证假设，不宣称此改动必然提高归因质量；本轮不改 source 或 GUIDE，不追写旧 run。

## 观察到的开销，不作质量胜负推断

| tools / rep1 | wall 秒 | MCP 调用 / 拒绝 | 返回字符 | input 总量 | 其中 cached | uncached | output |
|---|---:|---:|---:|---:|---:|---:|---:|
| Member | 324.45 | 55 / 0 | 238,198 | 1,723,544 | 1,595,904 | 127,640 | 13,948 |
| Dice | 224.66 | 43 / 3 | 161,618 | 769,067 | 637,952 | 131,115 | 9,932 |
| Splash | 311.79 | 56 / 1 | 240,675 | 1,329,480 | 1,198,080 | 131,400 | 13,206 |

来自各 run 的原始 metrics，原生 leaf 返回字符不重复加 wrapper。cached 已包含在 input，不能相加；output 也不再加 reasoning。美元 cost 为 null，不能臆造账单。三个文件问题数均为 2，但材料规模、查询路线和输出不同；没有本轮配对 baseline，不能据这些单次观察宣称工具组质量 / 成本胜负。

Member coverage=22/22（9 版本＋13 候选），Dice=8/8（7＋1）。Splash 机械 0/24（9＋15）因整块解析失败；人工可见逐项填写不改此机器指标。分母是需要交代的记录，不是 22 / 8 / 24 个已证实修复。
