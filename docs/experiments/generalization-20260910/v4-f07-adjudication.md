# tools-v4 F10-07 补充裁决（Dice EntryAbility）

这是旧开发集的 AI 证据审阅，不是人工/双盲留出评测。它补充 F10-07，不改动五个 0723 文件的既有小计，也不接触新 13 文件参考。没有模型调用、冷建账本、执行历史命令或修改 runtime、冻结 core、模型报告及旧 arm 裁决。

沿用 `baseline-v1/private/scoring-core.json`，SHA-256 `0d48f30f9e501eedd55b87e086590c72e8b7fb8096a939f56842b71703426497`。两跑的 metrics 与 postprocess 均 completed 后才审阅。

| 报告 | 核心 | 去重事实主张 | major | 核心 pass |
|---|---:|---:|---:|---:|
| F10-07 rep1 | 2 correct / 2 | 2 supported / 3 | 0 | 是 |
| F10-07 rep2 | 2 correct / 2 | 2 supported / 2 | 0 | 是 |

两份均正确区分：初版已经有窗口加载、沉浸式和安全区能力；后来 UI 测试设计驱动 Want/AppStorage/mock 冷热入口接线；再后置 ECAT 要求驱动全局异常观察者。没有将后置测试或观测要求无证倒归初期生成违规。更深组织机制明确为假设，不进入事实精确率分母。

## 独立原文边界

原始池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool`。以下是池相对路径；完整逐项时间、call_id、短摘录和正反依据已写在两份 grade 内。

- `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a349784d2663f1f0a.jsonl`：L1 为迁移和沉浸式任务；L47/L48 是真实 EntryAbility Read；L71/L72 是初版完整 Write/成功回执。完整 Write 没有 `TestDataSetup`、`consumeTestWant`、`onNewWant` 或 `errorManager`，但已有 `setupImmersiveWindow`。
- 同 root 的 `agent-a711c5d09fb676814.jsonl`：L1 后置任务要求只追加桥、不动既有逻辑；L11/L12 真正读取 P0001 设计；L35–L40 为三次 Edit/成功回执，增加测试导入和键、冷热接线、Want/AppStorage/mock 与宿主 token 消费。
- `2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a27497cfed8c44856.jsonl`：L1 后置 ECAT 任务；L31/L32 的 ArkTS 查询无匹配不等于 SDK 无 API，L35/L36 实际查得 AbilityKit 导出；L41–L46 为 import、onCreate 注册和两个日志回调的三次 Edit/成功回执。
- 同 root 的 `agent-a635575c78cd15ff6.jsonl`：L44（2026-09-03T21:23:58.793Z）原生 `BUILD SUCCESSFUL in 8 s 185 ms`，L48 有 `BUILD_EXIT_CODE=0`；L64（21:25:34.704Z）另有构建成功，L68 明确 ohosTest CompileArkTS/PackageHap。都在 22:09:07.188Z 观察截止前。

rep1 摘要的“两组修改的编译、运行和测试效果均未被记录验证。”以及 unknown 中“最终 API 具体可编译性没有编译证据”是全池编译证据否定，并非只说本次未重跑。上述真实构建反驳这一个去重主张，计普通 contradicted、major=false。构建成功不证明 UI 用例已经执行、桥可用或观察者捕获/持久化行为正确；这些合理未知不处罚。

rep2 的“EntryAbility 在记录中出现过，但只有路径提及”孤立看有歧义；同 finding 正文明说“一次 Bash”，counterevidence 又限定“同一记录”，对应 L42 的文件列表。因此不扩读为整个生成 actor 从未 Read EntryAbility。另以 L47/L48 保存明确反证边界。rep2 “没有重新编译、运行”及“本次未执行这些验证”是自身操作限制，不当作历史全池无验证。

引用/边认证、schema 与 role 标签仍是独立形式审计；没有因此自动给语义加分或扣 major。未分析 query-trace 的交付完备性，不能把本裁决的历史反证直接称为模型已读后忽略。

## 验证与产物

新文件位于 `C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-adjudication-v4/F10-07/rep1.json` 和 `rep2.json`。原 `score_raw10.validate_grade(base=tools-v4, contract_base=baseline-v1)` 两份通过；全部 decision 的 report_spans 为最终报告逐字片段。另对 4 个原始子源重核 evidence 的行、timestamp、call_id 和字面 excerpt，零错误。

- rep1 报告 SHA-256：`8cb75ffe27498f846f5e9fa2eea4c7a9d4196cc31249aa56f9407f721f961738`；grade SHA-256：`e899efc6a0d3e7324388c725fb7bc8c471adf14ac7fd58356f7a2636910fbc8a`。
- rep2 报告 SHA-256：`0a14336746df89819c32199a95034595538d7d847a5325a84bdf3ebb9ccc6c4b`；grade SHA-256：`eb9333f1a88efc7249819e87929a77e5afabe69d3f20fb2c9b2a9f10ca056be6`。

这些成绩只进入已冻结开发集汇总，不能宣称工具的稳定泛化效果。
