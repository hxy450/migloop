```
文件: entry/src/main/ets/wxapi/WXEntryAbility.ets  修复方: fixer-r1 / visual-fixer(agentId a68daf720e780b4c2)  修改时间: 2026-07-26T21:26:56.736Z(建文件) + 21:27:59.817Z(module.json5 注册)

修复改了什么: 纯新增一个 UIAbility 宿主——onCreate/onNewWant 都把 want 交 WxCallbackHandler.getInstance().handleIntent(want) 分发、分发后 terminateSelf 自关闭（对位源码 finish()）；同时在 module.json5 的 abilities[] 注册 WXEntryAbility（launchType=singleton、exported=true，skills 有意留空）。

修复的依据: 两条。①单 spec/fix/round-1/feat/WXCallbackActivity_01_no_wxentry_callback_ability.md（P1、kind=IMPL_MISSING、disposition=manual_review），§5 直接给出"新建 ets/wxapi/WXEntryAbility.ets + 在 module.json5 注册"的修法；判据是 Android 锚点 pay/src/main/AndroidManifest.xml:13/38 的 activity + alias（${applicationId}.wxapi.WXEntryActivity 约定入口）与鸿蒙侧自述契约 F003ViewModel.ets:351。②主会话派单时显式授权这半边："module.json5 补 WXEntryAbility/WXPayEntryAbility 声明这一半现在就能做；want→resp 解析依赖微信鸿蒙版 SDK 入仓（D-013），那部分保持挂起"。

被改代码的来源: 纯新增，此前该文件与该 abilities 条目都不存在。前一版的写者是生成轮 conv-wxcallback（agent-aconv-wxcallback-3f5b8f543d8ac407），它的派单书把产出**限定为单一文件** entry/src/main/ets/components/WxCallbackHandler.ets，并明令"微信 SDK 具体接入（IWXAPI/handleIntent/WXEntryActivity 注册）→ 华为侧无等价，属三方 SDK：用 // PLACEHOLDER 标占位"。它照办了：把"WXEntryAbility 注册"整体打进占位 P-S2-012（trigger=微信登录 SDK 入仓），只在注释里承诺宿主存在（handler 的 onFinish 钩子注释"宿主微信入口 UIAbility（WXEntryAbility）自行终止"）。Slice 2（aslice2-auth）后来只偿还了 FWD-REF P-S2-013（发起侧 setAuthListener），P-S2-012 按"等 SDK"规则保留，宿主始终没人写。

生成时为什么没做好: 生成轮派单书的"三方 SDK 占位"分类过宽——把纯 ArkTS 能做的宿主 Ability + module.json5 注册和真正依赖 SDK 的 want→resp 解析捆在同一个占位 P-S2-012 里，占位一挂就整段免做，且切片单文件产出边界让没人对 module.json5 负责。

是否必要: 必要（但不充分）——半条链是实证的（回流侧零调用点），宿主这一半确实只能由本轮补；但 handleIntent 仍是 P-S2-012 占位、skills 留空，回跳尚不能真正落地，本轮只是把契约补齐、让 handler 的 finish 路径可被验证。

证据(每条带位置):
  1. 新建动作与全文：ff019d8a-.../subagents/agent-a68daf720e780b4c2.jsonl:557（Write toolu_01AKvyiY2VwoW6mzsNVzSbAm，2026-07-26T21:26:56.736Z）；:558 结果 "File created successfully at .../wxapi/WXEntryAbility.ets"（确证是新增而非改写）。
  2. module.json5 注册：同文件 :565（Edit toolu_018TphB7YWDmYrBMnC3RMBFr，21:27:59.817Z），注释自述"skills 有意留空（D-013 挂起项）…不能照抄 EntryAbility 的 skills、更不能臆造"。
  3. 修复依据的单：ff019d8a-.../subagents/agent-afcfbf677a4e5864a.jsonl:175（vv-static-B 写单，2026-07-26T18:01:07.439Z），evidence 列 module.json5:33、WxCallbackHandler.ets:253/257、F003ViewModel.ets:344/351、AndroidManifest.xml:13。
  4. 缺席的实证：同文件 :72-73（17:46:42），grep module.json5 abilities 只有 EntryAbility(:33) / EntryBackupAbility(:75)，find '*WX*' 只命中两个 handler，无 wxapi 目录。
  5. 派单授权：主会话 ff019d8a-5172-4cdd-8ce3-77a21682c1b6.jsonl:1712（2026-07-26T20:33:31.393Z）Agent 调用 prompt 中"微信双回调 Ability…现在就能做…那部分保持挂起"。
  6. 生成轮的口径：9b3105a2-.../subagents/agent-aconv-wxcallback-3f5b8f543d8ac407.jsonl:1（派单书：【输出】仅 WxCallbackHandler.ets；"WXEntryActivity 注册"归三方 SDK 占位），:131（2026-07-24T05:11:51.861Z 占位表：P-S2-012 @ WxCallbackHandler.ets:255 handleIntent()，trigger 明写含"WXEntryAbility 注册"）。
  7. 单里建议调 handleWant，fixer 实际写的是 handleIntent（真实方法名，见证据 6 的占位表）——说明 fixer 读了源文件而非照抄单；编译验证 agent-af0e3d2ae54dbf769.jsonl:54（21:47:53）BUILD_STATUS: PASS，并确认新增的 wxapi 两文件"经 module.json5 声明入口，确已参与编译"，本文件零报错。

无法确认的部分: ①skills 留空时微信回跳能否真正把 want 投递到该 Ability——微信鸿蒙版 SDK 的 scheme/校验契约不在任何转录里，转录中也无人验证。②dispatch() 里 onFinish 回调与末尾无条件各调一次 terminateSelf 是否会重复终止，无运行时证据（本轮明令"不重编不复测"，编译验证仅静态过 pass）。③生成轮那份派单书由谁/依据哪条规则写成"WXEntryActivity 注册=三方 SDK"，其上游规则文本未在转录中出现。

置信: 高——新增动作、写入全文、驱动它的单、派单授权、生成轮的占位口径五处原始记录齐备且互相印证；仅运行时行为与 SDK 契约无从核。
```