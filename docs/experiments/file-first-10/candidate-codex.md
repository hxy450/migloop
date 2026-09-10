# Codex：以实际被修文件为入口的候选核验

结论：当前两份 root rollout 严格支持 **2 个 execute 结束后确实写入的产品源码/配置文件**：`entry/src/main/ets/pages/LaunchAgreementDialog.ets`、`build-profile.json5`。本次不以 fixer/reviewer 报告补成第三个。仅更新新实验档案，不改旧实验结果。

## 来源、口径与结束边界

原始文件均来自 `C:/Users/hongy/OneDrive/Documents/xwechat_files/wxid_1d7icrbx732s22_2384/msg/file/2026-08/`，全文件 SHA-256 已复算一致：

| 下文代号 | 完整 source basename | SHA-256 | 物理行数 |
|---|---|---|---:|
| A | `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `9dc4529045f70a6d493fe2ae05d215fac4990e6dcbafc59dce20d69ac2de8679` | 8117 |
| B | `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `a97f9363d03178ef394c593b9274b1b954574b093172e5cfb072712ce1540460` | 7916 |

本次读取旧 `codex-reference.md/.json` 仅用于导航，所有新结论返回原始日志核验；未读被测新模型答案作为真值，未执行日志中的历史命令，未调用付费实验，未修改产品代码。

生成结束原文为 **A:7686**（`event_msg/agent_message`，`2026-08-16T23:49:46.898Z`）及其重复消息 **A:7687**（`response_item/message`，`2026-08-16T23:49:46.899Z`），均无 tool call_id：

> 迁移执行已完成，使用的是刚迁入的 MigBot skills/agents 版本。
>
> `a2h-execute` 已完成；尚未启动下一阶段 `a2h-verify`。

该消息同时报告 10/10 功能、205/205 AC、unsigned HAP，以及第三方 SDK、PPT renderer、设备运行仍待验证。这是明确的阶段结束声明，不是“业务全部实测成功”。A 文件名日期不能代表其中每个 turn 的日期；Launch 修补发生于 08-17 UTC。

全池截止为 B:7916 最后 raw record，`2026-08-22T15:24:43.116Z`。A 最后 assistant 为 A:8115，`2026-08-17T03:12:10.312Z`；B 最后产品交付消息为 B:7884，`2026-08-22T05:26:53.728Z`；B 真正最后 assistant 为 B:7914，`2026-08-22T15:24:42.229Z`，内容仅提供 session 日志路径。这些时点与 execute 结束边界各有不同用途。

因此，若旧归类把 Launch 的这次补丁视为生成内改动，**应在新评测中纠正为 post-execute repair**。它与 A:3037 的 GuideDifficulty1 空回调纠错不同，后者确实早于边界。证据 B1/B2 的行哈希与每条证据的完整 basename、行、call_id、时间、摘录均在 [candidate-codex.json](candidate-codex.json)。

## 全量修改账与取样资格

从两份 root rollout 的原生 `tools.apply_patch` 调用扫描，得到 118 次调用，其中 6 次结果明确失败；独立扫描得到 113 个成功 `patch_apply_end` 事件。外层 `call_*` 只与同 ID 的 `custom_tool_call_output` 配对；事件使用另一个 `exec-*` call_id。下表与 inventory 中 call/event 的联系仅为同路径与时间窗口的候选关联；两个入选文件另外核对了补丁文本一致，仍**不是 ID 已证实的嵌套归属**。尤其外层 `{}` 不证明 write 成功。实际写入事实来自每个事件自身的 `success/changes/unified_diff`，无需依赖外层关联。3 处首次 outer yield 后才出现事件，也不因位置次序判成失败。

全部 **144 个 source/path 组合**及操作定位列在 [codex-native-write-inventory.md](codex-native-write-inventory.md)，完整时间、调用结果和线程元数据在 [codex-native-write-inventory.json](codex-native-write-inventory.json)。其中 77 个 source/path 组合有结束边界后的操作；大部分是工具链和报告。

以下是全池全部直接产品 native 写入，不限于旧题：

| 文件 | 调用 / 独立成功事件 / 外层结果（候选关联） | 外层 call_id | UTC 时间（调用） | 资格 |
|---|---|---|---|---|
| `entry/src/main/ets/pages/GuideDifficulty1Component.ets` | A:3037 → 3038 → 3039 | `call_S2DOREu8NlaqtS123olwx41i` | 2026-08-16T18:03:10.855Z | 生成内，排除 |
| `entry/src/main/ets/pages/MainPage.ets`（新增）；`entry/src/main/resources/base/profile/main_pages.json`；`entry/src/main/ets/entryability/EntryAbility.ets`；`entry/src/main/ets/pages/Index.ets`（删除） | A:4356 → 4357 → 4358 | `call_1P0Hw8iHj4f8Nn4HH3UFX9ZX` | 2026-08-16T19:33:12.999Z | 生成内入口装配，排除 |
| `entry/src/main/ets/pages/WXCallbackPage.ets`；`entry/src/main/ets/pages/BaseWXPayEntryPage.ets` | A:4386 → 4387 → 4388 | `call_v0kC135m7IqJafP1QEFE1JGL` | 2026-08-16T19:34:22.031Z | 生成内，排除 |
| `entry/src/main/ets/pages/LaunchAgreementDialog.ets` | A:8066 → 8067 → 8068 | `call_sOYpciVhfgk1glebywbIbHAY` | 2026-08-17T03:11:06.675Z | 可纳入 |
| `build-profile.json5` | B:4943 → 4944 → 4945 | `call_bLvRxsabKt5jwrDAGfcDP0LK` | 2026-08-21T11:15:04.158Z | 可纳入（工程配置） |

## 候选 1：LaunchAgreementDialog.ets

审阅端关注点（不进入调查员问题）：该文件在 execute 完成后被改了什么，修改前事件链、生成输入和 SDK 摘录分别支持什么近因；原始 rollout 是否证明用户点击已恢复？

**生成侧可见信息。** A:5527（L1）是主会话读取到的 F001 spec：AC02 要求同意后先写值 1；AC03/04 要求二次拒绝；AC05 要求两个协议链接。这说明生成阶段已有这些行为要求。A:5640（L2）读取了 `slice-01-source-notes.md`，描述 Android `onClick` 的两阶段拒绝与 `openWebPage`。它是源理解报告，不能当 Kotlin 正文或子代理完整读入清单。

A:5717（L3，2026-08-16T20:52:57.556Z）的真实 sender 为 **`/root/close_batch_02`**，此时被复用于 Stage 3 Group 1 / Slice 1 / F001，报告 `CREATED ... LaunchAgreementDialog.ets`、`BUILD: NOT_RUN`。不能根据 agent 名字把它继续认作仅执行 Batch 2 closer，也不能虚构 `/root/slice_01` 身份。创建补丁不在根转录里，最初写入 Block 的具体操作者/时刻、是否在后续 closer 中引入，均未知。

**触发与假设变化。** A:7997（L4，2026-08-17T03:09:20.059Z）用户原话：“卡在这个页面了，点击同意也没反应，你能帮我修复一下吗”。它证明用户报告的症状，不是本次审计独立设备重现。A:8000（L5）最初猜测事件未接到启动协调器；A:8027/8037（L6/L7）读到实际源码后出现直接反证：按钮有 `.onClick((): void => this.onAccept())`，父 `SplashPage` 也实际传了 `onAccept: (): void => this.onPrivacyResult(true)`。因此不能仅凭默认 `@Event` no-op 就断言父回调未接线。

同一 A:8027 显示可见外层 Stack 的 `.hitTestBehavior(this.visible ? HitTestMode.Block : HitTestMode.None)`，并有接受、拒绝、协议链接、关闭协议回调。A:8048（L8）SDK 摘录完整显示 Default 允许自身与子节点响应；紧接注释写有阻断 child 的语义，但截取在 Block 枚举标识之前结束。A:8055（L9）主会话据此改判外层 hit-test 为近因。这是很强的代码级候选；审计保留 SDK 截取边界，不把模型诊断句当独立运行事实。

**实际写入。** A:8066（L10）仅改一行：

```diff
-    .hitTestBehavior(this.visible ? HitTestMode.Block : HitTestMode.None)
+    .hitTestBehavior(this.visible ? HitTestMode.Default : HitTestMode.None)
```

A:8067（L11，2026-08-17T03:11:06.817Z）的独立事件 call_id 为 `exec-4ef57557-1919-4ec6-b81e-4b4d9d8c112a`，`success:true`，含该文件 unified_diff 和成功 stdout；这条事件本身足以证明对应写入。A:8068（L12）是外层 `call_sOYpciVhfgk1glebywbIbHAY` 的空结果，不单独证明写入，也不证明事件属于该 outer call。A:8110（L14，2026-08-17T03:12:02.536Z，`call_qMphaUcIWYqr2IY7APprp85k`）读回源 line 109 已为 Default。直接落盘事实依赖 L11 与 L14，邻近调用文本只作佐证。

**验证范围。** A:8101（L13，`call_K4votC9ADdWZuKxjzYSHC9lK`）是 `a2h-tool validate` 的 `exit_code:1` / `config.json missing`，发生在真正 assembleHap 前。A:8110 同时读到旧 unsigned HAP 时间为 `2026-08-17 11:05:57 CST`，即 `03:05:57Z`，早于补丁。A:8115（L15）明确说“现有 HAP 仍是修复前版本”。没有当次新构建、新安装和各按钮点击回归。

全池后来并非从未成功构建：B:7694（C11）直接记录 `BUILD SUCCESSFUL` 与 signed HAP 安装。但是 B:6090 还报告 Round 0 再次修改了 LaunchAgreementDialog（其实际 source patch 缺失），原补丁至后置产物的源码血缘更不能只靠时间和相同路径建立。不得声称 C11 已证明 L10 的四类点击通过。

**可判事实/未知。** 可以判定是一次后置真实代码修补，并要求回答区分“最初回调接线猜测被源码反证”“外层命中路由近因”“修补成功”“行为未验证”。不能判定 Block 一定由初始生成者直接引入，不能将初始需求缺失当根因，也不能据现有证据排除其他覆盖层或状态问题共存。

## 候选 2：build-profile.json5

审阅端关注点（不进入调查员问题）：工程已有 signingConfigs 却只能出 unsigned HAP 时，这次后置配置修补与鉴权请求签名缺失有什么关系；哪些结果有直接证据，遗漏来自哪里是否可追溯？

**生成来源界限。** A:120（C1，2026-08-16T11:18:03.875Z，`call_ZCtfL6Tg97dBG0jHXIWkXOCk`）在迁移执行前已列出目标 `build-profile.json5`。两份根转录没有其创建 native patch，因此原作者、模板版本以及哪次写入导致 product 未引用 signingConfig 均未知。不能把“后置被修”自动写成“模型从零生成时漏掉”。

**修前状态与动机。** B:4921（C2，2026-08-21T11:14:26.907Z）`/root/build_auth_fix` 报告 ArkTS 编译 PASS、`FILES_CHANGED: none`，但 unsigned 原因为 `signingConfigs present but no product references it`。B:4930（C3，2026-08-21T11:14:42.786Z，`call_8N7RoqR0XTc63HuR9I41Nq6Z`）实际读取完整配置：`app.products[0]` 的 name 为 default、没有 signingConfig 字段，另有 `app.signingConfigs[].name=default` 及材料配置。这能独立核实配置关系，不依赖 build agent 总结。材料凭据值不抄入本档案。

B:4934（C4，2026-08-21T11:14:48.679Z，`call_nfwjmlicObG8LyPwc3f5ZPgb`）读回 D-019：“开发阶段使用目标工程现有调试签名”，生产材料由发布责任人提供。B:4941（C5）主会话基于这条既有决定，选择补 product 引用。邻近的 B:4848（X1）是 **另一问题**：`MainSigningKeyProvider`、`AipptDevelopmentSecretProvider`、ApiClient 组合根缺失，由 `/root/fix_auth_composition` 报告 BLOCKED 且未修改文件。HAP 签名引用补丁没有创建这些请求鉴权 provider。

**实际写入。** B:4943（C6）在 product name 后添加：

```diff
         "name": "default",
+        "signingConfig": "default",
         "targetSdkVersion": "6.0.2(22)",
```

外层 call_id 为 `call_bLvRxsabKt5jwrDAGfcDP0LK`；B:4944（C7，2026-08-21T11:15:04.181Z）独立 `exec-9c2b0363-9806-4d9a-8733-06f2e3379843` 事件 `success:true`，并列该文件真实 diff，单独证明该修改成功；B:4945（C8）是 outer 的空结果，仅证其结束。两者归属联系仍按候选关联记录。该事件中的 patch 没有增加证书、改变口令、修改 SDK target 或改业务源码。

**验证范围与反证。** B:4966（C9，2026-08-21T11:16:05.982Z）是 `/root/build_auth_fix` 的最终报告：`BUILD_TYPE: signed-hap`、`SignHap` 成功，声明该代理未改签名引用/凭据。这个“未修改”限定在 child agent，不能否认此前 root 的 C6；该条也不是 root-visible 编译器 stdout。B:5017（C10）是主会话的新包安装总结，不能补出子代理设备调用。B:7694（C11）则确有稍后 root 工具输出的构建成功与 signed HAP 安装成功，但不提供原配置 hash/产物 hash，也不证明验证码、登录、会员或 Works 等行为正确。

**可判事实/未知。** 最直接近因是 product 到已有调试 signingConfig 的引用缺失；“缺生产签名材料”“API signer 缺失”“ArkTS 编译失败”均不足以描述这条补丁。可确认配置成功写入；紧随签名构建成功是 child 报告，稍后另有实际 build/install 输出。遗漏的生成责任仍未知，实际应用业务是否闭环仍未知。

## 排除记录与报告修改清单

三轮 fixer `FILES_MODIFIED` 已从 B:6090、B:6968、B:7683 完整提取到 [codex-reported-source-modifications.json](codex-reported-source-modifications.json)，含完整 basename/行/call_id/时间/hash。它们证明总结被读取，不升级为源文件实际 write。包括 GuidePage、PptGenerationViewModel、GuideInitComponent、GuideStatusComponent、MemberCenterActivitiy、Mine/Recommend/Works 组件、Web 相关服务等，均不能拿列表补足本实验的严格入选数。

- `GuidePage.ets`：B:6957（X2）reviewer 对 Monitor/visibility 的意见，与 B:7683（X6）独立挂载解释竞争；B:7653（X4）仍要求 GuideInit fresh capture。源 patch 缺失；真实时序/渲染根因与结果未知。
- `PptGenerationViewModel.ets`、`WorksService.ets`：B:7683 声称统一入库门面，B:7680（X5）reviewer 声称旧路径已有相同 DAO/事件；B:7574（X3）Works canonical 受联系人污染。没有完整方法源码/diff/有效复测，不得把 reviewer 的 wrong_edit 当行为等价证明。
- `GuideStatusComponent.ets`、`MemberCenterActivitiy.ets`：报告有行高/间距、composition gate 修改，但无 root-visible 源 patch；不纳入。
- `AuthViewModel.ets`、`AuthApi.ets`：B:4874/4875 有修后源码读取，B:4921 有编译报告，根转录缺对应写入调用/结果；不混入 native 实写账。
- A:3037/4356/4386 涉及的 7 个产品文件：真实写入充分，但发生在 execute 内；MainPage 后来的 timestamp touch 也不能算文件内容修补。
- `.agents/skills/**`、`spec/**`、`docs/autofix-log/**`、`build_out.log`：全量 native 账中确有后置修改，属于工具链/验收产物/日志，不是本轮需要的产品源码或产品配置候选。

补查 root 显式 `write_text/.write/cp/mv/rm` 等非 native 命令：B:510、543、584、603、668、688 是 fact tree、registry map 等报告加工；B:1615、3528、3592、3596 是截图/dump/walk-plan 搬运；B:7794、7798 是 finding 路径搬运；B:7870 是清理构建日志。未找到额外直接产品源码/配置写入。这里仅列可见命令目标，未将脚本间接产物或退出码不明项补作已成功 write；不能以此宣称穷尽所有子代理及外部写入。

## 缺失子代理与证据上限

源池只有两个 root session，原始 session id 为 `01a009fe-68e3-7f42-b76b-5e863c555976`、`01a021e5-c150-7b12-a610-d40c07816b98`。两份根日志合计记录 111 个去重的 source/thread 元数据组合，含以下关键子线程；没有这些子线程的独立 rollout 正文。

| 角色与原始路径 | 稳定 thread id | 根日志首次元数据 |
|---|---|---|
| 复用作 Slice 1 生成者 `/root/close_batch_02` | `01a00bef-9cb2-7fe0-a0e8-174e7c99abca` | A:3853 |
| `/root/build_auth_fix` | `01a02404-3599-75f1-8970-bf25edcdec81` | B:4869 |
| `/root/visual_fixer_round_0` | `01a02511-c851-7662-ab84-543e3b5ad374` | B:5948 |
| `/root/visual_fixer_round_1` | `01a0258b-b27e-7d31-9ad8-e725de827251` | B:6816 |
| `/root/visual_fixer_round_2` | `01a025f4-74b1-7953-bcf1-c968ace7defe` | B:7601 |

根会话收到的子代理报告不等于其全部输入、补丁或工具回执。有些派发消息还以不透明字符串记录，不能猜测明文。可把上述 ID 用于请求补充源材料，不能拿根转录缺失证明子代理从未执行动作。本档案以这两个已证实后置写入文件为候选，缺失的生成责任和行为验证保留 unknown。

复核命令：`node docs/experiments/file-first-10/scan_codex_candidates.cjs validate`。结果：两个 source hash/物理行数 PASS，35 条引用的行哈希、时间、call_id、原文片段 PASS，113 个独立 native 事件的身份、文件集合、行哈希及覆盖率 PASS。该检查只读原始日志和本次证据 JSON，不执行历史代码。
