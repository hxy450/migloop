# DiceRoller：EntryAbility.ets 与 AppScope/app.json5 有界参考

状态：两个文件均有生成后真实修改，可纳入新 10 文件集合；本稿是可复核的开发参考，不是未曝光盲测真值，也不是迁移收益评估。审查对象是整份被修文件，事件数不等于缺陷数。

## 冻结范围与取证方法

- 项目：历史 `.../scratchpad/dice-hmos`，Android 源为 `Android-Beginner-Projects/DiceRoller`。
- 冻结池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool`，80 个 JSONL、17 个根会话。
- 生成根：`81e0a463-c9d3-4a7a-a671-b7f064830af1.jsonl`；边界 `2026-09-03T16:46:30.036Z` L1521，`tool_result.tool_use_id=call_1c3a687dea17483dac9482b0`，摘录 `[a2h-codex] mark-stage: a2h-execute`。
- 截止：`2026-09-03T22:09:07.188Z`；当前根 `49d451b1-f479-4c4e-bb39-9fa0dd06aeb0.jsonl`。下文简写时刻均为 **2026-09-03 UTC**，不是工具输出里的设备本地时间。
- 已阅读旧 `docs/experiments/file-first-luna/review-v2/dice-index.md`。它只用于发现边界与邻接线索；Index.ets 不重复计入本次两个文件。两个候选都应标记 **Dice 项目级开发暴露**。本文重新解析池内原始 `message.content`，按相同 `tool_use.id / tool_result.tool_use_id` 配对，不以旧稿、ledger、memory、评分或后写报告自证改动及初期动机。
- 扫描覆盖池内所有 `Write/Edit` 的目标路径，包括相对路径；两目标未找到 `MultiEdit`。另检索 `Bash` 中直接文件名及复制、写文件、构建等可能影响文件的调用。只读取历史文本；没有执行其中命令，没有调用模型、重新构建或设备测试，没有改生产代码。
- 本地在内存中逐条应用原始 old/new，核对每条 old_string 在当时文本中恰好命中一次，再与晚期原始工具读回比较；只移除 Read 行号前缀并忽略末尾换行。该一致性检查支持“已解释可见净差异”，不证明窗口内没有被撤销的瞬态修改或未展开脚本效应。

## 原始来源索引

表中别名仅缩短后文，完整 basename 与根目录均列在这里。行号均指 JSONL 物理行。

| 别名 | 池内原始 source（完整 basename） |
|---|---|
| G | [81e0a463-c9d3-4a7a-a671-b7f064830af1.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/81e0a463-c9d3-4a7a-a671-b7f064830af1.jsonl) |
| C | [81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a349784d2663f1f0a.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a349784d2663f1f0a.jsonl) |
| I0 | [81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a39c5351955d3cd6b.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a39c5351955d3cd6b.jsonl) |
| T | [81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a711c5d09fb676814.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a711c5d09fb676814.jsonl) |
| U | [81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a52d61ac7ab7033ba.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a52d61ac7ab7033ba.jsonl) |
| E | [2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a27497cfed8c44856.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a27497cfed8c44856.jsonl) |
| I1 | [2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a87804892da9cfc8b.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a87804892da9cfc8b.jsonl) |
| B | [2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a635575c78cd15ff6.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a635575c78cd15ff6.jsonl) |
| D1 | [1f681af9-9dee-4e1c-9e1e-2e6bccf70927.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/1f681af9-9dee-4e1c-9e1e-2e6bccf70927.jsonl) |
| R1 | [70f369a3-58ac-4f4f-b30a-45e8497983b6.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/70f369a3-58ac-4f4f-b30a-45e8497983b6.jsonl) |
| L1 | [a329e202-1d33-49f8-abd9-daa156504a35/subagents/agent-a066f03249327db0d.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/a329e202-1d33-49f8-abd9-daa156504a35/subagents/agent-a066f03249327db0d.jsonl) |
| L2 | [49d451b1-f479-4c4e-bb39-9fa0dd06aeb0/subagents/agent-a0e222c0fcd4973f5.jsonl](C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool/49d451b1-f479-4c4e-bb39-9fa0dd06aeb0/subagents/agent-a0e222c0fcd4973f5.jsonl) |

## 文件一：entry/src/main/ets/entryability/EntryAbility.ets

### 全文件变更清单

初版不是空壳。C L71→72 的整文件 Write 已含 hilog、页面加载及错误日志、生命周期日志、沉浸式窗口设置、系统栏透明配置、安全区测量、windowSizeChange 监听、px→vp 换算与 WindowModel 同步。初版 onCreate 仅记录日志，没有 onNewWant、测试桥、errorManager。下面 6 条是生成边界后的全部已确认原生修改；没有把初版的既有窗口/日志能力算成后修新增。

| 事件 | 原始 source basename / 调用→返回 | call_id | 时间（调用→返回） | 原始改动摘录与范围 |
|---|---|---|---|---|
| E0 初版，边界前 | `agent-a349784d2663f1f0a.jsonl` C L71→72，Write | `call_459071197f484436b71237e5` | 15:51:35.645→15:51:35.656 | 写完整 EntryAbility；`onCreate` 为 `hilog.info(..., 'onCreate')`；`loadContent('pages/Index')`、`setupImmersiveWindow(windowStage)` 已在场。返回 `has been updated successfully`。 |
| E1 测试 import/常量 | `agent-a711c5d09fb676814.jsonl` T L35→36，Edit | `call_003bc0a35ce74684a5296325` | 19:17:13.810→19:17:13.830 | 添加 `import { TestDataSetup } from '../test/TestDataSetup'`；添加 `TEST_MODE_KEY='__TEST_MODE__'`、`TARGET_PAGE_KEY='__TARGET_PAGE__'`、`HOST_PAGE_NAME='Index'` 及测试桥/宿主页注释；保留既有 import、TAG、DOMAIN。 |
| E2 生命周期测试接线 | `agent-a711c5d09fb676814.jsonl` T L37→38，Edit | `call_6c1a4dd0da164350a549d420` | 19:17:21.617→19:17:21.630 | onCreate 新增 `this.consumeTestWant(want)`；新增带 hilog 的 `onNewWant` 并调用同一方法；注释明确 singleton 热路径与测试重入。 |
| E3 测试桥实现 | `agent-a711c5d09fb676814.jsonl` T L39→40，Edit | `call_04086bf7960b46e7b2a00be4` | 19:17:35.691→19:17:35.704 | 在安全区方法前插入 `consumeTestWant`：读 Want 小写参数，写 AppStorage 大写桥键；测试模式调用 `TestDataSetup.injectMockData().catch(...)` 并 hilog；空 target 返回；非空写 target；target 为 Index 时清空 token。注释说明 V2 不用 V1 `@StorageLink+@Watch`、单页无需 push。 |
| E4 异常观察者 import | `agent-a27497cfed8c44856.jsonl` E L41→42，Edit | `call_f031a058037c467fb06fc159` | 21:19:24.777→21:19:25.164 | `UIAbility, AbilityConstant, Want` → `UIAbility, AbilityConstant, Want, errorManager`，来源 `@kit.AbilityKit`。 |
| E5 异常观察者接线 | `agent-a27497cfed8c44856.jsonl` E L43→44，Edit | `call_7013085c03274c8183fdd455` | 21:19:31.929→21:19:31.944 | onCreate 日志后、consumeTestWant 前添加 `this.registerGlobalErrorObserver()` 和新增用途注释。 |
| E6 异常观察者实现 | `agent-a27497cfed8c44856.jsonl` E L45→46，Edit | `call_b6682a6aab774d88b1d1871d` | 21:19:39.888→21:19:40.205 | 类尾添加 JSDoc 与私有方法；显式 `errorManager.ErrorObserver`，实现 `onUnhandledException`、可选 `onException`，hilog 输出 message/name/stack（`stack ?? ''`）；注册 `errorManager.on('error', observer)`。没有添加 appRecovery/hiAppEvent、注销机制或真实崩溃测试。 |

E1—E6 的匹配 result 均明确 `The file .../EntryAbility.ets has been updated successfully`，非只见调用、失败尝试或 agent 自述。相同日志里对其它文件的修改不计入本文件。

### 阶段、输入与初期状态

| 证据定位 | 当时实际交付/观察 | 支持的判断 |
|---|---|---|
| C L1，15:37:36.490，原始派单，无 call_id | MainActivity 唯一 Activity，沉浸式安全区四层架构、骰子功能 AC、V2 页面生成；要求先读 `arkts-immersive-safearea`。 | 生成派单明确页面与窗口契约；这里未交付后来的测试桥或全局异常观察者指令。不能由后修倒推出这两项当时已是生成要求。 |
| C L57→58，`call_1488a6869bea4472921ea35f`，15:39:25.327 调用，Read `arkts-immersive-safearea/SKILL.md`；C L71→72 | 读取安全区材料后写入窗口四层的 Ability 部分；初版保有 `getMainWindow`、设置系统栏等失败分支 hilog。 | EntryAbility 初期重点由显式沉浸式契约解释。没有全局 observer 不等于没有任何异常处理。未穷尽生成者全部隐式系统上下文，因此“此前绝对从未出现这项要求”仍不是可证明结论。 |
| T L1，19:10:08.728，原始派单，无 call_id | `第三步 Agent — UI 测试用例生成（MODE=generate）`；“只做测试代码与测试数据落地”；明确“onCreate/onNewWant 注入”、保留已有沉浸式逻辑、单页 V2 桥收敛至 Ability 侧。 | E1—E3 是新的测试接线任务；不能归成掷骰功能缺失、业务导航丢失或初版 lifecycle 没实现。 |
| T L11→12，`call_769beeda1a324d3d95de7251`，19:10:17.886→19:10:17.962，Read `spec/test/ui-test/design/P0001_MainActivity.md` | 设计 §F 原文：“当前 EntryAbility.onCreate 为空壳（仅 hilog），桥为纯增量注入”；Index 为 `@ComponentV2`；零 push、无 NavDestination；mock 最小集为空；唯一 AppStorage 键是测试桥键，非业务键。 | 直接解释为什么追加 Want/AppStorage 接线、为何不往 Index 套 V1 装饰器。这里“空壳”只修饰 onCreate，不可扩成整个 Ability 无实现。 |
| E L1，21:17:54.685，原始派单，无 call_id | `ECAT iteration 0`，work list 要求全局异常观察者；明确称为 HarmonyOS 框架约束、无 Android 对应物，要求不要按 Android 补业务。 | E4—E6 是后置质量门禁驱动的框架可观测性改动。它是该阶段确实收到的要求；其“无观察者就无 crash 报告”的技术理由仍需另证。 |
| E L31→32，`call_b751d8c3336d470cae38df74`，21:18:26.388→21:18:26.416；E L35→36，`call_e6d56b80320d4677b97b915b`，21:18:35.605→21:18:35.628 | 原派单建议从 `@kit.ArkTS` import；本镜像 ArkTS kit grep 无命中；AbilityKit d.ts 第46行 import、第95行 export 含 errorManager。 | 工作者检查 SDK 后修正了派单给的 import 路径。应归为修复期间核实 API，不能把不存在的初版 bad import 算成一次编译修复。 |
| E L29→30，`call_f3722a2fa80c4d2bbee5b99e`，21:18:25.065→21:18:25.089；E L37→38，`call_e8130043aeef4043aa0e3ff0`，21:18:36.033→21:18:36.200 | d.ts 返回 `on(type: 'error', observer: ErrorObserver): number`；`onUnhandledException(errMsg: string): void`、`onException?(errObject: Error): void`。 | 支持新方法类型和成员的来源，不是推测 SDK 能力。 |

### 验证、反证与脚本边界

| 原始证据 | 实际结果 | 边界 |
|---|---|---|
| U `agent-a52d61ac7ab7033ba.jsonl` L139→140，`call_a308ad2fae7c4c99a119b8ec`，19:28:23.702→19:28:24.213，Bash 读取设备 `/data/log/faultlog/faultlogger/jscrash-com.example.myapplication-20020091-20260904032755972.log` | observer 添加前已返回 `Generated by HiviewDFX@OpenHarmony`、`Load Page Failed: pages/Index`、Stacktrace、HiLog，带 TestAbility/UiTest exporter 上下文。 | 可反驳“未注册该 observer 就任何异常零报告”的无条件表述；这是测试路径崩溃记录，不证明正常生产启动必崩，也不证明与缺 observer 有因果关系。不能将其作为 E4—E6 已解决的故障。 |
| E L55→56，`call_86ef24539b644c61830b5a1a`，21:20:05.427→21:20:05.745，`git diff EntryAbility.ets` | 仅 observer 三组净差异；此前测试桥已在基线。 | 交叉确认 E4—E6；单次 git diff 基线不覆盖 E1—E3，因此不能用它代替全窗口清单。 |
| B L29→30，`call_4ddf55d524fc40a19c0dc42a`，21:23:32.588→21:23:32.839；B L43→44，`call_01dfaa766cce469ca64faf64`，21:23:58.751→21:23:58.793；B L47→48，`call_552108735f094b3f8d8a9e0d`，21:24:08.671→21:24:08.914 | entry build 后台调用返回任务 `btucjteyt`；后续日志读回 `Finished ... CompileArkTS`、`PackageHap`、`BUILD SUCCESSFUL`、`BUILD_EXIT_CODE=0`，产生 unsigned HAP。 | 是同一历史构建链原始返回，支持编译完成；同时有 `app_name conflict`、EntryAbility 多处 WARN（含新注册调用 line140）与无 signingConfig WARN。不能写零 warning、已签名安装或 observer 真机功能验证通过。 |
| B L63→64，`call_09982c7436e5491a84ac4559`，21:25:29.586→21:25:34.704；L67→68，`call_8f969a5b29af41dd9cf09479`，21:25:43.667→21:25:43.751 | `entry@ohosTest` 构建成功，exit0；真实 OhosTestCompileArkTS/PackageHap 和 unsigned 测试 HAP 路径。 | 构建测试包不等于执行其中的 UI 用例。未找到对新 observer 的专门异常注入及 hilog 断言。 |
| L2 `agent-a0e222c0fcd4973f5.jsonl` L8→9，`call_ac3454e853d9404188ea76de`，22:06:32.348→22:06:32.517，Read 全文 | E0 + E1—E6 内存复原与返回全文一致；规范化 SHA256 `ccae34e3df209ac3dd93fbae6b72336c98d1bdf6c7600cd66b10b28f35b1dbbe`。 | 晚期内容核验，不是新执行代码；最后读回至截止的短区间仍只能依据已见调用判断。 |

已见 `touch` 后构建应独立处理：`agent-ac3b22afb4458cd07.jsonl`（生成根 subagents）L15→16，`call_afebad7ee5364ed4b444c0ef`，20:15:05.530→20:15:05.579，返回三源文件的新 mtime（EntryAbility 6115字节）；`593d4e86-a947-4e62-8027-013014c2bafc.jsonl` L465→467，`call_df65c4b5e96d4fb892f971c6`，21:06:18.476→21:06:23.938，返回编译输出与 WARN。两条命令均点名 EntryAbility/Index/WindowModel，意图为强制重编，`touch` 本身改变 mtime，不作为代码修复事件。构建包装器内部动作未穷尽展开；本文件的晚期净文本已由 6 次 Edit 完整解释，不以此声明所有脚本均无副作用。

### 归因与可行机制假设分栏

| 已知为何修改 | 初期为何如此 / 未知 | 反证或不可推断 | 可行机制假设（待实验） |
|---|---|---|---|
| UI verifier 新增专门的测试 Want、桥键、mock hook、冷热入口接线。 | 初期派单是页面迁移及沉浸式窗口；后期设计才明确测试接线。当前证据不支持初版漏遵已有桥接要求。 | 不得叫“缺少掷骰业务初始化”；空 mock 与该应用无外部数据依赖一致；增加 onNewWant 不证明此前业务重入有故障。 | 若测试方式在生成前确定，可生成明确的测试接线契约，注明宿主页、V1/V2、冷/热入口及数据依赖；比较后期追加次数，同时检查是否无端增加测试耦合。 |
| ECAT 后置门禁要求异常观察者与 hilog 可观测性。 | C 初版已有局部错误日志；尚未找到该全局观察者约束作为初版输入的直接证据。 | 原始 jscrash 反例排除“无 observer 就零系统报告”；没有观测到 observer 的真实崩溃测试收益。 | 将观察者要求标为明确的质量基线及适用阶段；核实 SDK export、区分系统 crash 日志与应用定制记录，再用异常注入验证增量价值。 |
| 修复者将建议的 ArkTS import 改用 SDK 已证实的 AbilityKit export。 | 这个错误路径只出现在后置派单建议，未进入初版或已成功写入的 bad code。 | 不应虚构“先引入错误 import、再编译修好”的额外事件。 | 给代码生成任务附可核对的目标 SDK 证据，减少凭文字示例采用不存在 export 的风险。 |

## 文件二：AppScope/app.json5

### 全文件状态与真实变更

此文件适合与 EntryAbility 并列：实际修改只有一个生成后 Edit，却涉及显式的阶段授权改变、来源映射、资源作用域和检测器误报。不能因为编辑次数少就拆成虚构的多个修复轮。

| 事件 | 原始 source basename / 调用→返回 | call_id | 时间（调用→返回） | 完整修改范围 |
|---|---|---|---|---|
| A0 首个已核快照，边界前 | `agent-a39c5351955d3cd6b.jsonl` I0 L33→34，Bash | `call_4d7173d3a6a44651901a7f15` | 15:33:04.075→15:33:04.109 | 完整 app.json5：bundle `com.example.myapplication`、vendor `example`、versionCode `1000000`、versionName `1.0.0`、icon `$media:app_icon`、label `$string:app_name`、min/target API21、debug false。AppScope media 仅 app_icon.png，entry media 已有分层三件套。脚手架最早创建者未在本稿恢复，不作作者断言。 |
| A1 生成期 version 对齐，不算生成后修复 | `agent-a39c5351955d3cd6b.jsonl` I0 L59→60，Edit | `call_9eeac76f5b9a45d6ac08a6ef` | 15:35:18.958→15:35:18.971 | versionCode `1000000→1`；versionName `1.0.0→1.0`。成功返回；其它字段未改。 |
| A2 生成后身份/图标配置修改 | `agent-a87804892da9cfc8b.jsonl` I1 L49→50，Edit | `call_2a22aef71a3641f19092ca7c` | 21:19:08.646→21:19:08.653 | **同一次成功 Edit**：bundleName `com.example.myapplication→com.example.diceroller`；vendor `example→diceroller`；icon `$media:app_icon→$media:layered_image`。old/new 中 versionCode/versionName 不变；label/minAPIVersion/targetAPIVersion/debug 不在编辑块中，也与最终全文一致。 |
| A2 的配套脚本（写相邻资产，不是 app.json5 原生 Edit） | `agent-a87804892da9cfc8b.jsonl` I1 L45→46，Bash | `call_c8f9430feac54929af417cb1` | 21:19:00.755→21:19:00.809 | `cp` entry media 的 background.png、foreground.png、layered_image.json 至 AppScope media；返回三对 md5 相同，分别 `e44e7ecfec99356632c13cd3eaa3e250`（两 PNG）与 `95dbeae27ebea23feffb65c05a3fb1d5`（JSON）。保留 app_icon.png，没有删除旧图，也没有生成/导入新的 Android 图标。 |

生成边界后只找到 A2 这一条 app.json5 原生写入。A0+A1+A2 可复原 L1 L29→30（21:55:06.370→21:55:06.640，`call_9cbbfc27df06477fbacab7fb`）Bash 读回的完整 app.json5；规范化 SHA256 `6d5233bedbba3d8c9e374adae29d668bc9a6a19caa9c8eb9f4955afcd8bd0549`。没有把其它 root 对 ledger/memory/report 的修改误计为 app.json5 改动。

### “为什么最初保留默认身份”的直接证据

| 原始证据 | 当时指令/结果摘录 | 可判定边界 |
|---|---|---|
| I0 L1，15:31:54.536，原始派单，无 call_id | `scope=dev-identity`；“硬边界：**不碰 bundleName / vendor**（部署期 D-009）”；目标是 app_name、版本、图标，非阻断身份任务。 | 这是生成者收到的直接指令，足以说明其保留两字段有明确任务依据。无需把 ledger 后写文字当作初期动机的证明。不能判模型忘改、漏迁或未读身份 skill。 |
| I0 L23→24，`call_d4970dd01f094b548d8da86d`，15:32:21.567→15:32:21.677，Read 身份 skill | 返回原文第30、135—139行：dev-identity “跳过 bundleName/vendor”“保留脚手架占位值，待部署期由 scope=full（或人工）统一落地”。 | 具体任务与当时实际读取的 skill 在这两个字段上相符。其签名风险解释是历史材料的理由；本稿没有独立证明所有 HarmonyOS 工程都必须如此。 |
| I0 L69→70，`call_95105c2b9d7f4c188cf2c2e7`，15:35:39.457→15:35:39.697 | grep 明确看到 `com.example.myapplication`；完整读回仍是该 bundle/vendor，版本已是1/1.0。 | 生成者不是没有看到模板值，而是在明确不改的作用域内保留。不能只看最后 grep 命中就推断其没自检。 |
| G L1572→1574，`call_f7bbca0d43ea414981576de8`，16:48:06.800→16:48:06.879 | CHECK-4 app 身份读取仍为默认 bundle/vendor；module ability icon 指 `layered_image`，entry 三件资产已存在。 | 边界后状态连续；早期验收口径并不等于后来 ECAT 的全身份门禁。 |
| I1 L1，21:17:38.624，原始 ECAT iteration0 派单，无 call_id | work list 要求移除默认 bundle/vendor，补 AppScope 三件资产；明确 bundle→com.example.diceroller；vendor 不得保留 example；复制已有 entry 图标；icon 依 skill 决定。 | 后置阶段改变了需写字段范围，并非同一时间生成者收到“既不准改又必须改”两条指令。直接修改原因可判为后置门禁/身份收尾。 |
| I1 L23→24，`call_6d681c27df894624856a8269`，21:17:56.027→21:17:56.045；L25 skill 正文 21:17:56.043 | Skill 调用未传 scope=dev-identity；skill 默认 full；vendor 机械规则仍是 applicationId 的第二段，示例 `com.example.app→example`。 | 后置 full 身份任务与早期 dev-identity 应分开；vendor 非模板要求与源组织段映射在此教学应用发生冲突。 |

### 图标与 vendor 不应被强行解释为源码真值

图标初期保留 `$media:app_icon` 与 bundle/vendor 的原因证据强度不同：早期任务明确不改后两者，图标则在 dev-identity 目标内；I0 的目录读回表明 AppScope 只有 app_icon，entry 有三件分层资产。当时引用并不悬空。后期 I1 L1 明确沿用既有脚手架图标、复制三件至 AppScope，A2 再切换 icon 引用，因而本次图标改动可以确认是 **资源作用域补齐与指针切换**。仅凭配套 copy 不能宣称 Android 原始 launcher 图标已完成迁移，也不能宣称此前系统无法显示图标。初期为何未把三件复制进 AppScope 的完整权威决策链未独立恢复；本稿保留未知，不用 D-003/后写报告补成确定因果。

vendor 则存在具体的修复取舍。I1 L1 开头说“skill 规则与本 prompt 冲突时以 skill 为准”，正文又要求“不得保留 example”；实际交付的 skill（L25）要求取 applicationId 第二段，对 `com.example.diceroller` 得到 example。I1 L60，21:20:07.963 的最终自述承认改按 prompt 的非模板要求选择 diceroller，并声称“无歧义、不构成违规”。**只接受其作为取舍自述，不能接受无冲突结论**：选择结果由 A2 old/new 直接证明；diceroller 是应用名/尾段取值，不是已证实的真实厂商名，也不与机械第二段规则相符。评测应允许指出修复输入冲突和解释不充分，而不是要求将 vendor 变化统一美化成“忠实源映射”。

### 修后报警、验证与反证

| 原始证据 | 实际结果 | 支持与限制 |
|---|---|---|
| I1 L53→54，`call_6e915aae02594c01bf2f5ec0`，21:19:24.502→21:19:24.694 | JSON parse OK；AppScope media 四个文件；app icon/label 与 layered 内部两资源均解析 `[OK]`；字面 `com.example.myapplication` 的 json5 grep 无命中。 | 静态引用自检通过；此 grep 只搜旧字面值，不代表 ECAT 的更宽规则必通过。 |
| B L29→30、L43→44、L47→48、L63→64（调用 id 与完整时刻见文件一验证表） | app.json5 修改后 entry 与 ohosTest 均构建成功，存在无签名 HAP，WARN 仍在。 | 可以引用历史编译成功；没有证明 bundle 变更后的安装、签名、升级、测试包启动、用户数据连续性或 launcher 像素对齐已验证。 |
| D1 `1f681af9-9dee-4e1c-9e1e-2e6bccf70927.jsonl` L3，21:27:46.820，原始下一轮检测输入，无 call_id | `bundleName=com.example.diceroller`、vendor diceroller、`layered_image_valid=true`；fails 仍含 `bundleName is template default: 'com.example.diceroller'`；两个 PNG 各0.07KB warn。 | 是修后确实继续报警的事实；检测输入自身不是原因证明，也不是另一轮 app.json5 修改。 |
| R1 `70f369a3-58ac-4f4f-b30a-45e8497983b6.jsonl` L73→75，`call_5d7033b366a34cea9fd97315`，21:37:06.842→21:37:06.876 | 原始 Bash grep Android `app/build.gradle:10: applicationId "com.example.diceroller"`，同调用 cat app.json5 与新 bundle 一致。 | 源真值与新 bundle 一致；可反驳“com.example.diceroller 必然是迁移遗留模板”的断言。只证明 bundle，不证明 vendor 来自真实厂商。 |
| R1 L157→159，`call_66591deda54c419daa094142`，21:40:10.179→21:40:10.185，Read `check_app_identity.py` | 工具返回源码第78行：`if not bundle or re.match(r"com\.example\.", bundle):`；第84行拒绝 vendor example；第119行 PNG ≤0.3KB 即警告；第123附近无条件查 AppScope layered 文件。 | 独立的原始检测器源码解释继续报警：规则匹配源工程本身的示例前缀。不得用后写 ledger/memory 代替这条证据，也不能建议为清分数随意造另一个包名。 |
| L1 `agent-a066f03249327db0d.jsonl` L29→30，`call_9cbbfc27df06477fbacab7fb`，21:55:06.370→21:55:06.640 | 再次读回仍为 A2 后全文；与内存复原一致。 | 已核净修改完整；后续登记/说明没有再改此配置。当前截止根 L3 仍带同样 app_identity 检测数据，可视为后续输入快照，不取代文件读回。 |

除上述资产 copy 外，未发现明确直接写 app.json5 的 Bash 文本。历史构建、依赖安装及工具包装器可能写生成物/缓存，其内部文件效应未在本稿逐体展开；全文复原一致缩小了“未解释持久修改”的空间，不证明所有历史脚本无副作用。`app_icon.png` 被保留的事实与三件新增文件并存，不能补写成“旧图标被删除”。

### 归因与可行机制假设分栏

| 已知为何修改 | 初期为何如此 / 未知 | 反证或不可推断 | 可行机制假设（待实验） |
|---|---|---|---|
| ECAT 后置要求清默认 bundle/vendor；A2 执行了身份范围扩展。 | 初期 explicit dev-identity 明确不准改这两字段，且读回自检看到默认值。 | 不能归“生成者没遵循正确身份指令”；后置范围变化不等于初版 Android 功能遗漏。 | 让每个身份字段携带阶段/是否暂缓/何时写入的契约；验证器按当前阶段判断，并把后期扩大范围作为新任务记录。 |
| 后期配置选择了 AppScope layered_image 并先复制所需资产。 | 初期 app_icon 引用有效；初期图标取舍的权威因果链在本稿仍未穷尽。 | 复制的是 entry 既有68字节资产，不是证明已转换 Android launcher；不能把缺 layered 文件等同于旧 icon 引用悬空。 | 检测器先解析实际 icon 引用及资源作用域，再检查必需资产；资源转换报告同时列出源资产、去向及批准复用策略。 |
| vendor 由 example 改成 diceroller，以响应非模板要求。 | 后期 skill 的第二段规则本来会产出 example；工作者报告承认改用 prompt 取舍。 | diceroller 不是已证厂商；原派单内部优先级与非模板要求冲突，修复自述不消除冲突。 | 对示例应用允许显式厂商决策，不把“非 example”当作真实身份；规则冲突要输出具体分歧，而非自动记为忠实源迁移成功。 |
| 修后仍有模板前缀/小图告警；源代码与检测器源码给出竞争解释。 | Android 源 applicationId 正是 com.example.diceroller；修后包名已对齐源。 | 继续报警不证明代码没改或修复失败；H 变化/告警清零都不是迁移收益。 | 将源身份值与模板启发式分开，保留可审计的冲突结果；用源值匹配和发布约束共同决定，不以分数驱动改名。 |

## 用作冻结参考的接受范围

- 文件一应解释测试接线与后置异常观察者两阶段的实质变化，保留完整文件初版窗口实现；6 次原生 Edit 是审阅端覆盖账，模型可合并描述，不要求逐条复述计数、call_id 或本稿行序，也不强制回答“两条业务缺陷”。
- 文件二应解释三字段配置变化及配套资产 copy，可以合并描述而无需复述 A2 编号；版本更新属于生成期；显式 dev-identity 禁改应进入初期归因。只报告模板值没迁或只复述 ECAT 的故障理由均不充分。
- 两文件都允许输出有证据的未知、修复输入冲突、反证与验证不充分；不得要求把原始 agent 自述的技术绝对化措辞照搬为真值。
- 本稿的模型/工具收益是假设：尚未比较任何新模型组，也未运行付费模型或把当前参考作为训练后盲测结果。未来评测须保留项目级开发暴露标记，并避免以本稿中的预设结论代替原始证据检索能力。

## 只读复现

[replay-dice-snapshots.cjs](C:/Users/hongy/projects/migloop/docs/experiments/file-first-10/replay-dice-snapshots.cjs) 只读取冻结池 JSONL，在内存应用 old/new 并与原始晚期全文读回比较，JSON 输出到 stdout；不运行日志里的命令、不写池内文件。调用：`node docs/experiments/file-first-10/replay-dice-snapshots.cjs`（也可把其它冻结池路径作为唯一参数）。它核实文本与事件链，不重新判定本文的原因或收益假设。
