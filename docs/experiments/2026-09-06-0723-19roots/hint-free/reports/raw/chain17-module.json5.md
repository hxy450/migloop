```
文件: entry/src/main/module.json5  修复方: fixer-r1(agentType=visual-fixer, agentId=a68daf720e780b4c2)  修改时间: 2026-07-26T21:27:59.817Z（uuid 58d50d64-3820-4b89-bc48-2ed5c0501186）

修复改了什么: 在 `abilities[]` 末尾（EntryAbility 之后、extensionAbilities 之前）纯新增两条 UIAbility 声明 `WXEntryAbility` / `WXPayEntryAbility`（srcEntry 指向新建的 ./ets/wxapi/*.ets，launchType=singleton、exported=true），并附大段注释说明 skills 有意留空、待微信鸿蒙版 SDK 入仓再补。配套在 :557/:561 新建了两个 Ability 源文件。

修复的依据: 修复轮 finding 单 `feat/WXCallbackActivity_01_no_wxentry_callback_ability.md`（+ 同根的 `BaseWXPayEntryActivity_01_no_wxpay_callback_ability.md`），severity P1 / kind=IMPL_MISSING / disposition=manual_review，判据是 Android 锚点 `pay/src/main/AndroidManifest.xml:13`（WXCallbackActivity）+ `:38`（activity-alias → `${applicationId}.wxapi.WXEntryActivity`），以及鸿蒙侧自述契约 `F003ViewModel.ets:351`「回调经 WXEntryAbility → WxCallbackHandler.onResp → 本 VM 监听器回流」；单里 §3 实测 `handleWant/onResp` 全仓零调用点。fixer 的任务书又点名放行了这一半：「`module.json5` 补 `WXEntryAbility`/`WXPayEntryAbility` 声明这一半**现在就能做**；want→resp 解析依赖微信鸿蒙版 SDK 入仓（D-013），那部分保持挂起」。

被改代码的来源: 纯新增，未删改任何既有条目。原 `abilities[]`（EntryAbility + EntryBackupAbility）是 DevEco 工程模板脚手架——生成轮全程没有任何 agent 对 module.json5 执行过 Write，只有两次 Edit，且都不碰 abilities 成员（abase3-network 加 metadata/requestPermissions；agroup1b-closer 给 EntryAbility 补推送深链 skills）。前一版的写者（conv-wxcallback）为什么没写：它的任务书把输出限定为单文件 `entry/src/main/ets/components/WxCallbackHandler.ets`，并明写「微信 SDK 具体接入（IWXAPI/handleIntent/**WXEntryActivity 注册**）→ 华为侧无等价，属三方 SDK：用 PLACEHOLDER」，末尾还有硬约束「不编译、**不写共享文件**」——module.json5 正是共享文件。

生成时为什么没做好: 生成链路的**任务分派环**（team-lead 给 conv-wxcallback 的 page spec）把「WXEntryActivity 注册」整体误归为三方 SDK 占位项（登记为 P-S2-012 kind=thirdparty-sdk），而它其实可拆成两半——manifest→module.json5 的 Ability 注册是纯 ArkTS 接线、有等价物；只有 handleIntent 解析才真依赖 SDK——加上同一份任务书禁止该 agent 写共享文件，导致这一半既没人做也没人认领。

是否必要: 必要 —— 没有宿主 Ability，微信回跳在鸿蒙侧无落点，发起侧 `setAuthListener` 已实装却永远收不到 code，属半条链的真实迁移缺陷（is_migration_bug: true）。

证据(每条带位置):
  1. 修复动作：`ff019d8a-.../subagents/agent-a68daf720e780b4c2.jsonl:565`（Edit module.json5，2026-07-26T21:27:59.817Z）；同 agent `:557`/`:561` Write `ets/wxapi/WXEntryAbility.ets` / `WXPayEntryAbility.ets`。meta：`agent-a68daf720e780b4c2.meta.json` = visual-fixer / "fixer-r1"。
  2. 修复依据（上游单）：`ff019d8a-.../subagents/agent-afcfbf677a4e5864a.jsonl:175`（Write 该 .md，2026-07-26T18:01:07.439Z）与 `:173`（支付那张，18:00:21.750Z）；作者 meta = general-purpose / "vv-static-B"（B系列静态验收），source: visual-verify。
  3. fixer 的授权口径：`agent-a68daf720e780b4c2.jsonl:1`（2026-07-26T20:33:34.783Z）「需要判断的 … `module.json5` 补 … 这一半现在就能做」。
  4. 生成轮误判点：`9b3105a2-.../subagents/agent-aconv-wxcallback-3f5b8f543d8ac407.jsonl:1`（2026-07-24T04:57:48.654Z）任务书第 2 条 +「不写共享文件」；其产物注释复读同一结论于 `:70`/`:71`，收尾报告在 `:131` 登记 `P-S2-012 … kind=thirdparty-sdk`。
  5. 契约的另一半确实已落盘：`agent-aslice2-auth-ac8d92aebe3693fc.jsonl:331-332` 写入 F003ViewModel 注释「回调经 WXEntryAbility → WxCallbackHandler.onResp → 本 VM 的监听器回流」——即生成轮自己承诺了一个从未产出的宿主。
  6. 生成轮 module.json5 仅有的两次改动与 abilities 无关：`agent-abase3-network-f9a03317492be8c4.jsonl:210`（2026-07-24T10:00:10.306Z，metadata+requestPermissions）、`agent-agroup1b-closer-3fdb5cb0c394f474.jsonl:112`（2026-07-24T15:02:15.198Z，EntryAbility skills 深链）。
  7. skills 留空是显式决策非遗漏：fixer 的 §6 追加文本 `agent-a68daf720e780b4c2.jsonl:610`「回跳的 scheme / bundle 校验契约必须以微信鸿蒙版 SDK 官方文档为准 … 照抄或臆造会导致 Want 被错误路由（甚至抢走深链）」，挂起项对齐 D-013 / P-S2-012 / P-S8-034。

无法确认的部分: ①「原 abilities[] 来自 DevEco 模板」是反证（生成轮无任何 Write module.json5、只有两次不碰 abilities 的 Edit），转录里没有直接创建该文件的记录；②这次改动未编译未复测（任务书明令「不重编、不复测」），build-verify-r1(af0e3d2ae54dbf769) 的编译结论我未逐条核对，故新 Ability 是否通过 hvigor 校验无法确认；③单里 spec_oracle 自标 UNRESOLVED（inject_spec_oracle.sh 不存在），判据是 Android 锚点 + 自述注释而非独立 oracle。

置信: 高 —— 修复动作、上游 finding、授权口径、生成轮的误判语句四段全部有唯一且互相咬合的转录位置，且修复轮对 module.json5 的写操作全仓只有这一次；仅编译验证与文件初始来源留有上述缺口。
```