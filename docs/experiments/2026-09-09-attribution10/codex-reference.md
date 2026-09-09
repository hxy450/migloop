# AIPPT_830_test：4 条难归因返修参照（Codex rollout）

## 范围与证据口径

本参照只读取以下两份原始 Codex rollout，不读取后续 GPT-5.5 调查报告，也不执行转录中的历史命令：

- `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl`  
  SHA-256：`9DC4529045F70A6D493FE2AE05D215FAC4990E6DCBAFC59DCE20D69AC2DE8679`
- `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl`  
  SHA-256：`A97F9363D03178EF394C593B9274B1B954574B093172E5CFB072712CE1540460`

下文的“物理行”是一条 JSONL 记录的 1-based 行号。行哈希定义为：该物理行去除换行终止符后，按 UTF-8 编码计算 SHA-256。`agent_message` 没有 shell `call_id` 时明确记为“无”；它能证明主会话收到该子代理报告，不能补出未嵌入 rollout 的子代理内部调用。`source_tool_output` 表示 shell/read 命令送回的输出；`actual_patch` 只在 rollout 本身展示了补丁及成功回执时使用。文件名或 SBS/JPEG 路径只证明路径被记录；除非转录另有图像工具回传，本参照不把它当作评审者实际看过像素。`BUILD SUCCESSFUL` 只证明编译出包，不证明对应页面状态或行为已修复。

本参照称 `rollout-2026-08-16…` 为“迁移 R1 rollout”，称 `rollout-2026-08-21…` 为“visual-verify rollout”。每条证据的完整 basename、单行 SHA-256 与 tier 见同目录 `codex-reference.json`；JSON 已由 `extract_codex_reference.py --validate-reference` 对两份原始文件逐条复算。

---

## C1 — GuideDifficulty1 默认事件：这次改动关闭了什么门，又改变了什么语义？

> 类型：生成内纠错 / 静态门禁边界题；不是 execute 完成后的返修。

**中性问题**：`entry/src/main/ets/pages/GuideDifficulty1Component.ets` 的默认 `@Event onAnswer` 从 `() => {}` 改为 `(): void => { return }`。这次修改能归因为什么，机械验收与运行语义应如何区分？

### 成立事实

1. 当时转换规则明确把“空回调”列为非法占位/骨架，要求 fail；该规则关注代码形态及登记纪律，不等同于用户行为验收。
2. Batch 1 closer 实际返回 `BLOCKED`，唯一列出的非法项就是该文件 line 3 的未登记空回调 `() => {}`；本轮没有 build。
3. 主会话随后读取源码，实际得到 line 3 原值 `@Event ... = () => {}`。
4. 主会话 commentary 说会把它改成“必须由父组件传入的事件接口”，但实际 patch 只把表达式体改成带显式 `return` 的块体默认函数；patch 回执成功。
5. 重跑 closer 后返回 PASS、`illegal_placeholders: []`，仍没有 build。由前后文本可直接判断：该修改关闭了当前静态扫描的“空回调形态”门；两版**默认函数本身**都不产生业务副作用，实际 patch 并没有强制父组件传参。这不证明父调用方没有另传真实回调，也不证明实际选择功能缺失。

### 近因推断

直接近因是 closer 的空回调形态规则，而不是编译器错误或设备行为失败。修改与规则匹配使静态门通过，但它更接近对扫描模式的形态规避；是否设计上允许 no-op 默认事件，需要 ArkUI `@Event` 约束和父调用点进一步裁决。

### 仍未知

- 父 `GuidePage` 是否总会传真实 `onAnswer`，根 rollout 的这组锚点没有展示调用点。
- `@Event` 是否允许无默认值、怎样才能真正“必须传入”，本段没有平台声明证据。
- 此改动后的 build 和点击行为没有在 Batch 1 重扫中验证。

### 必须拒绝的错误说法

- “这是编译错误修复。”
- “补丁已经把 `onAnswer` 改成必须由父组件传入。”
- “`return` 使默认回调获得了新的业务行为。”
- “closer PASS 证明用户选择事件可以正常推进。”

### 原始锚点

| basename:物理行 | call_id | 短摘录 | 支持/反证 |
|---|---|---|---|
| `rollout-2026-08-16…jsonl:224` | `call_l2FJxo9zP3XjiBLPDHKO0HsI` | 规则：`empty callbacks ... are forbidden` | `source_tool_output`，当时可见规则 |
| `rollout-2026-08-16…jsonl:3029` | 无（closer `agent_message`） | `status: BLOCKED`；line 3 未登记 `() => {}`；`build_run:false` | 阶段报告，证明门禁判定 |
| `rollout-2026-08-16…jsonl:3031` | 无（commentary） | 声称将改为“必须由父组件传入” | 模型意图，不等于实际 patch |
| `rollout-2026-08-16…jsonl:3034` | `call_cITFznZwW17SBIwTS2wQhbj0` | source line 3：`= () => {}` | `source_tool_output`，实际修前源码 |
| `rollout-2026-08-16…jsonl:3037-3038` | `call_S2DOREu8NlaqtS123olwx41i` | `() => {}` → `(): void => { return }`；更新成功 | `actual_patch` + 成功回执 |
| `rollout-2026-08-16…jsonl:3065` | 无（closer `agent_message`） | `status: PASS`；`illegal_placeholders: []`；`build_run:false` | 证明静态门关闭，不证明功能 |

---

## C2 — Works 生成入库：门面替换的解释和有效性有什么证据、边界？

**中性问题**：`entry/src/main/ets/viewmodels/PptGenerationViewModel.ets` 改为经 `entry/src/main/ets/services/WorksService.ets#saveGeneratedWork()` 入库。现有证据能否判断它改变了哪些行为，以及是否触及“作品未呈现”的原因？

### 成立事实

1. 返修前的执行期**摘要主张**：F005/F006 只有一个 post-insert `WorksLibraryUpdated(CREATED)` publisher，即 `PptRecordRepository`；同一摘要还称 `WorksService.saveGeneratedWork` 的重复 publisher 已被删除。该行是命令读回的历史摘要，不是相关类的源码正文。
2. Round 2 finding 是“已生成作品未在鸿蒙列表呈现”。同轮 Works canonical 截图又被记录为系统联系人污染，因此 UI 侧页面判定处于 BLOCKED；这不能反过来定位成入库 API 缺失。
3. fixer 报告把生成完成链改经 `WorksService`，声称根因是“生成与作品页分叉成两个业务门面”。
4. reviewer 报告称其检查修改前代码后发现：原 `PptRecordRepository.insert()` 已使用同一 `PptCreateDao.getInstance()`，成功后也发布同名 `WorksLibraryUpdated(CREATED)`，于是判断替换门面没有改变持久化和事件语义。根 rollout 没有同时展示两条方法的完整源码，故“所有行为等价”仍是 reviewer 结论，不是本参照可独立复算的事实；同 DAO 与同事件也不足以排除事务、错误处理、时序或附加副作用差异。
5. 后置 build 成功；没有证据表明生成动作实际到达入库、目标数据库存在记录，或 Works 初始化/加载断点已消失。

### 近因推断

现有证据只够说根因未定。fixer 将近因归为业务门面分叉；reviewer 将两条链描述为同 DAO/同事件并质疑其有效性。缺少实际源码正文和有效 Works 页面复测，不能裁定门面完全等价；调用是否到达、事务/错误处理、目标记录、查询初始化和刷新接收仍都是候选。

### 仍未知

- Round 2 canonical 被系统联系人污染，缺少有效 Works 页面复测。
- rollout 未包含子代理完整 diff；可确认主会话收到并持久化了 attempt/reviewer 结果，但不能从根转录独立还原每一行源改动。
- 真实断点可能在调用到达、事务、查询或页面加载，现有证据不能唯一裁决。

### 必须拒绝的错误说法

- “作品未呈现是因为原代码没有 DAO insert 或 CREATED 事件。”
- “接入 `WorksService.saveGeneratedWork()` 已修复作品列表。”
- “build 通过证明数据库写入和列表刷新通过。”
- “同 DAO 且发布同名事件已经证明两个门面的全部行为等价。”

### 原始锚点

| basename:物理行 | call_id | 短摘录 | 支持/反证 |
|---|---|---|---|
| `rollout-2026-08-21…jsonl:4934` | `call_nfwjmlicObG8LyPwc3f5ZPgb` | `exactly one post-insert ... publisher: PptRecordRepository`；`duplicate CREATED publisher removed` | `source_tool_output` 读回执行摘要；支持该历史主张，不是源码正文 |
| `rollout-2026-08-21…jsonl:7574` | `call_rHkspr6Fzhub0xEU83VOrdsF` | `BLOCKED_PWorksFragment ... canonical 误采集系统联系人`；`WorksFragment_generated_work_missing` | 区分无效 UI 身份与功能 finding |
| `rollout-2026-08-21…jsonl:7683` | `call_BYzt9sjwzhzxLipXgCsr6q4Y` | `生成完成统一走 WorksService 入库并发布 CREATED 事件` | 支持 fixer 的修改主张，不认证有效性 |
| `rollout-2026-08-21…jsonl:7680` | 无（reviewer `agent_message`） | 原 repository `已使用同一 DAO` 且 `已发布 ... CREATED`；替换“未改变实际持久化与事件行为” | reviewer 主张；根 rollout 缺源码，不能独立裁决 |
| `rollout-2026-08-21…jsonl:7686-7687` | `call_XHYFotPT6f6XWmbIyXSilnMV` | reviewer 的 Works `wrong_edit` 被写回 summary | `actual_patch` 仅修改 summary；不证明 reviewer 语义正确 |
| `rollout-2026-08-21…jsonl:7825-7826` | 无（最终消息） | “Works 等价门面替换没有触及真实根因” | 支持调用结束时仍未闭环 |

---

## C3 — GuideInit 瞬态页：多轮修法的解释和有效性有什么证据、边界？

**中性问题**：`entry/src/main/ets/pages/GuidePage.ets` 中 GuideInit loading/progress 经历了 Monitor/visibility 与独立挂载两种修法。两种解释分别有什么直接证据，现有材料能否判定真实根因或修复结果？

### 成立事实

1. 初始阶段同时具备 GuideInit 的静态三源入口：spec 明确列 Android Kotlin、`fragment_guide_init.xml`、synthesized view snapshot，并描述 Lottie/加载倒计时用途。初始 `GuideInitComponent` 报告称实现 5110ms progress flow 与 panorama auto-scroll；父 `GuidePage` 报告称 six-step Swiper 与 exact progress states 已实现。后来的缺失不能简单归成“生成时完全没有该要求”。
2. Round 0/1 两条工单一直明确标为 `low_confidence` / `transient_capture_debt`：介绍气泡和加载进度“未稳定截获”，不是高置信已证明代码不存在。
3. Round 1 fixer 新增 `progressPercent Monitor` 和 active visibility；reviewer **主张**既有 active Monitor 已处理激活、根节点默认可见，且 progressPercent 原已被 Text/Progress 响应式消费，因此两条均判 `wrong_edit`。根 rollout 没有相关源码正文，不能独立验证 reviewer 的所有前提。
4. Round 2 改变方向：将第六步移出缓存 Swiper，在 `currentStep===5` 时独立挂载并传 `active/progress`；摘要将近因写为“缓存子树首次 inactive 构建后未按当前 Param 重新生产节点”。这是比继续叠 Monitor 更具体的挂载生命周期假设。
5. 但两单仍保留 `manual_review`，最终报告明确说 GuideInit 仍有两项低置信人工复核债，且 need-info 仍要求 fresh capture。构建成功不能关闭它们。

### 近因推断

两轮形成互相竞争的代码假设：Round 1 指向 Monitor/visibility，Round 2 指向缓存 Swiper 的挂载/参数刷新。Round 2 解释更具体且方向不同，但这只是 fixer 摘要里的假设；没有实际 patch 正文与 fresh capture，不能把“缺挂载”提升为已证近因或把 reviewer 的 Round 1 判断当金标。

### 仍未知

- Round 2 独立挂载是否在正确瞬态窗口显示机器人、气泡和进度，没有新鲜截图/时间同步证据。
- 两条最初是低置信 capture debt；可能混有采样时序问题，不能全部归责代码。
- 初始 converter/worker 的完整子会话不在这两份根 rollout 中；只可使用根收到的报告和工具输出，不能宣称穷尽它读过的所有输入。

### 必须拒绝的错误说法

- “GuideInit 要求是视觉验证阶段才新增的，初始生成者没有输入。”
- “Round 1 增加 Monitor 修复了进度链。”
- “Round 2 因 build 成功或记录了 SBS 文件名，所以已视觉闭环。”

### 原始锚点

| basename:物理行 | call_id | 短摘录 | 支持/反证 |
|---|---|---|---|
| `rollout-2026-08-16…jsonl:2013` | `call_b5NIkmLWkXtjLgHjdKGnc9WQ` | GuideInit Kotlin/layout/snapshot；“展示引导加载动画并倒计时进入首页” | 支持初始阶段已有要求与源入口 |
| `rollout-2026-08-16…jsonl:2336` | 无（`agent_message`） | 父 `GuidePage`：`six-step non-swipe Swiper, exact progress states` | 支持父级初始实现自述；不是运行验证 |
| `rollout-2026-08-16…jsonl:2781` | 无（`agent_message`） | `GuideInitComponent`：`5110ms progress flow ... implemented` | 支持子组件初始实现自述；不是设备验证 |
| `rollout-2026-08-21…jsonl:5879` | `call_8PsHI1kc3azM3FxOJBhI8I0j` | 两单 `confidence: low_confidence` | 支持最初证据不确定性 |
| `rollout-2026-08-21…jsonl:6957` | 无（reviewer `agent_message`） | Monitor 未建立新渲染链；progress 已响应式消费；两条 `wrong_edit` | reviewer 主张；不是本参照独立源码判定 |
| `rollout-2026-08-21…jsonl:7683` | `call_BYzt9sjwzhzxLipXgCsr6q4Y` | `currentStep===5` 独立挂载；“缓存子树首次 inactive 构建” | 支持 Round 2 新近因假设 |
| `rollout-2026-08-21…jsonl:7653` | 无（fixer `agent_message`） | need-info 含 `GuideInit fresh capture` | fixer 报告明确保留复测债；不是设备工具输出 |
| `rollout-2026-08-21…jsonl:7825-7826` | 无（最终消息） | `GuideInit 仍有两项低置信人工复核债` | 证明调用结束时未关闭 |

---

## C4 — LaunchAgreementDialog 点击失效：代码近因与验证边界是什么？

> 上下文：此案完整发生在迁移 R1 rollout（`rollout-2026-08-16…`）末段，不是 08-21 visual-verify rollout 的 reviewer 裁决。

**中性问题**：`entry/src/main/ets/pages/LaunchAgreementDialog.ets` 将外层 Stack 的可见态从 `HitTestMode.Block` 改为 `HitTestMode.Default`。这段修改的代码近因证据有多强，现有 rollout 又实际验证到了哪一层？

### 成立事实

1. 主会话通过源码读取实际看到：弹窗声明 `onAccept/onReject/onReadAgreement/onCloseAgreement`，外层 Stack 在可见时使用 `HitTestMode.Block`。
2. 主会话读取了本机 HarmonyOS SDK 声明；可见摘录明确说明 `HitTestMode.Default` 允许节点及其子节点响应触摸、同时阻挡 sibling。诊断消息进一步把 `Block` 解释为阻断子节点，但当前引用片段没有完整展示 `Block` 枚举正文，因此该半句仍有少量摘录边界。
3. rollout 展示了实际 patch：唯一代码变化是可见态 `HitTestMode.Block → HitTestMode.Default`；紧接的 `patch_apply_end` 返回成功。之后源码读回 line 109 也确认新值已落盘。
4. 本次修复会话没有得到新 HAP：最终消息明确说 CLI 编译被缺失的 `.migbot/config.json` 阻断，当时现有 HAP 仍是修复前版本。08-21 visual-verify rollout 后来另有一次 `BUILD SUCCESSFUL` 和安装成功，但该记录没有给 C4 源码 hash、补丁血缘或四类点击结果，不能仅凭时间后置把它当作本补丁的行为验证。
5. 因此“代码里存在会影响命中路由的设置”与“补丁已落盘”有直接证据；“同意、不同意、协议链接四类交互都已恢复”只有助手推断，没有修后构建、安装或点击回放支持。

### 近因推断

`HitTestMode.Block` 是很强的代码级近因候选：它位于覆盖全屏的外层 Stack，四类交互都是其子节点，且 SDK hit-test 语义与症状方向一致。相较前三题，它有实际 source、SDK 摘录、patch 和 source readback 的闭环；但仍应称“代码级近因”，不能升级为设备行为已验证根因。

### 仍未知

- 修改后的 HAP 是否可编译、能否安装以及四类点击是否逐一成功。
- 08-21 的成功构建是否包含完全相同的 C4 源状态；现有记录缺少 source→artifact 对账。
- `HitTestMode.Block` 的完整 SDK 枚举说明没有完整出现在所引摘录；若要形式证明 Block 的精确语义，还需完整枚举正文。
- 是否还有透明覆盖层、事件回调或状态机问题与 hit-test 问题并存。

### 必须拒绝的错误说法

- “这次只是模型自述，没有实际源码或 patch 证据。”
- “四类点击已经在设备上回归通过。”
- “现有 HAP 包含该修复。”
- “缺 `.migbot/config.json` 说明代码 patch 没有落盘。”
- “全池后来完全没有成功构建。”

### 原始锚点

| basename:物理行 | call_id | 短摘录 | 支持/反证 |
|---|---|---|---|
| `rollout-2026-08-16…jsonl:8027` | `call_7fkY9pgpk0sNPDyhCFcX0npm` | source output：四个 Event 声明；外层 Stack 后续可见 | `source_tool_output`，实际源码读取 |
| `rollout-2026-08-16…jsonl:8048` | `call_P25PVpQdj6880uvIX5rXeevD` | SDK：Default 下 node 与 child 响应、sibling 被阻挡 | `source_tool_output`，平台声明摘录 |
| `rollout-2026-08-16…jsonl:8055` | 无（commentary） | 将 `Block` 诊断为阻断子节点 | 模型诊断，不是独立工具事实 |
| `rollout-2026-08-16…jsonl:8066-8067` | `call_sOYpciVhfgk1glebywbIbHAY` | `Block → Default`；`Success. Updated` | `actual_patch` + patch 成功回执 |
| `rollout-2026-08-16…jsonl:8110` | `call_qMphaUcIWYqr2IY7APprp85k` | line 109 已为 `HitTestMode.Default`；HAP mtime 仍旧 | `source_tool_output`，落盘读回及旧产物状态 |
| `rollout-2026-08-16…jsonl:8114-8115` | 无（final message） | `.migbot/config.json` 阻断；`现有 HAP 仍是修复前版本` | 明确验证边界；“同时恢复四类交互”仍是未实测推断 |
| `rollout-2026-08-21…jsonl:7694` | `call_dacW1PmSvf6UGEA9wFwJcdnz` | `BUILD SUCCESSFUL`、signed HAP installed | 后来确有构建；缺少与 C4 patch 的 source/artifact 血缘及点击验证 |

---

## 四条题目的共同判分边界

- 能定位持久化 attempt，不等于根因正确；C1/C2 是 fixer 与 reviewer 主张冲突、但缺直接源码/行为裁决的边界题。
- 生成方报告“implemented/PASS”、fixer 报告“modified”、后置 `BUILD SUCCESSFUL` 是三种不同证据层级，均不能替代设备行为复测。
- finding 可能是低置信覆盖债、错误页面身份或污染采集；不能把任何 finding 标题自动当产品真值。
- “最接近的近因”必须与“已验证根因”分开。C3 的 Swiper 缓存挂载仍是未复测假设；C4 虽有更强的 source/SDK/patch/readback 链，也没有修后 HAP 和设备点击闭环。
- 本集合是四条有界参照，不宣称覆盖两份 rollout 的全部返修，也不以缺失的子代理内部转录证明某动作从未发生。

## 淘汰候选

- `GuideStatusComponent.ets` 的 `64→70 / 15→17`：只见 fixer/reviewer 冲突摘要，没有产品源码 patch 与修后测量；reviewer 的 2vp 阈值也没有裁决同时发生的 6vp 行高变化，故不纳入最终四题。
- `MemberCenterActivitiy.ets` 的 HomeVip readiness gate：只见 fixer summary；正确会员页身份、源码 patch 和成功 catalog 行为都缺失，故不纳入最终四题。
- `MainPage.ets` 入口装配：有直接 patch，但发生在生成阶段的一次性入口装配；后续 compile fix 只见摘要，难以构成清晰的后置返修链，故未采用。
