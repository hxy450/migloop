```
文件: entry/src/main/module.json5  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v5
修复改了什么: 在 `abilities[]` 末尾纯新增 38 行——注册 `WXEntryAbility` / `WXPayEntryAbility` 两个 wxapi 宿主 Ability(srcEntry 指向新建的 ./ets/wxapi/*.ets,launchType=singleton、exported=true),并有意留空 `skills` 待微信鸿蒙版 SDK 文档确认。
修复的依据: 派发词点名「标 disposition: manual_review 的(微信双回调 Ability):module.json5 补 WXEntryAbility/WXPayEntryAbility 这一半现在就能做,want→resp 解析依赖 D-013 保持挂起」(fixer-r1 派发指令),对应两张 finding 单 spec/fix/round-1/feat/WXCallbackActivity_01_no_wxentry_callback_ability.md@v1 与同根的 BaseWXPayEntryActivity_01(fixer-r1 v26 于 T+81:21/81:23 读过),单里 §4 源码缺口写明「module.json5:33 abilities[] 缺 WXEntryAbility」。
被改代码的来源: 纯新增(sessions 行级归属:纯新增 38 行),没有改掉任何人写的行。前一版写者 group1b-closer v4(module.json5@v4)只按 F014 推送深链给 EntryAbility 补了 startapp:// 的 skills/uris;再前一版 base3-network v22(@v2)的职责被派发词限定为「明文 HTTP cleartext + INTERNET 权限,这一项你负责改 module.json5」,两者都不负责 wxapi 宿主。真正的"应写者"是 slice2-auth:它在 F003ViewModel.ets:351(slice2-auth@v13)写下「回调经 WXEntryAbility → WxCallbackHandler.onResp」的契约,却把它整体挂在 :345 的 `PLACEHOLDER: P-S2-012 kind=thirdparty-sdk`(slice2-auth@v1)下,当成"等 SDK 入仓"而没落地。
生成时为什么没做好: 环节在 activity-converter 的派发口径——conv-wxcallback 派发词把「IWXAPI/handleIntent/**WXEntryActivity 注册**」整包判为三方 SDK 占位并硬性规定「不写共享文件」,把"纯 ArkTS 就能做的宿主注册"和"必须等 SDK 的 want 解析"混进同一个 P-S2-012(支付侧同构:conv-wxpayentry → P-S7-012/后编号 P-S8-034),下游 slice2-auth / 各 closer 沿用该占位,module.json5 的 abilities[] 就没人认领。
是否必要: 必要,回流侧宿主缺席使 handleWant/onResp 全仓零调用点、微信授权 code 永远回不来(finding §3),补声明是接通半条链的前提;但 skills 留空意味着此版仍只能被显式 startAbility 拉起,不构成完整回跳。
证据(每条带坐标):
  1. diff module.json5@v5 — 纯增两个 ability 条目 + 注释自述「skills 有意留空(D-013 挂起),SDK 入仓时按文档补并同步 P-S2-012 / P-S8-034」。
  2. fixer-r1 派发指令(agent v28 窗口)「需要判断的」一节 — 明确授权补这两条声明、其余挂起;收尾输出「47 modified + 2 new」与新建的两个 Ability 文件对应。
  3. fixer-r1 v27 写 entry/src/main/ets/wxapi/WXPayEntryAbility.ets@v1 (#23550 T+81:24) → v28 写 module.json5@v5 (#23554),写前读 module.json5@v4 [60-110行]。
  4. finding spec/fix/round-1/feat/WXCallbackActivity_01_...md@v1(vv-static-B v10 #26454 写)第 55/63 行:abilities[] 只有 EntryAbility(:33) 与 EntryBackupAbility(:75);disposition: manual_review,理由「宿主 Ability 注册是纯 ArkTS、现在就能做」。
  5. module.json5 写者脊柱:v2 ← base3-network v22(#2643),其派发词硬约束 #9 只要求放开 cleartext;v4 ← group1b-closer v4(#12169),diff 只加推送深链 skills —— 两版都没碰 abilities[]。
  6. conv-wxcallback 派发指令第 2 条 + 【返回报告】末句:「WXEntryActivity 注册 → 属三方 SDK,用 PLACEHOLDER/FWD-REF」「不编译、不写共享文件」;其收尾登记 P-S2-012(thirdparty-sdk, WxCallbackHandler.ets:255, 含"WXEntryAbility 注册")。conv-wxpayentry 同构,登记 P-S7-012(forward-ref)。
  7. blame F003ViewModel.ets@v17 340-354 行:slice2-auth@v13 写下 :351 的 WXEntryAbility 契约、:344 的 setAuthListener,回流侧仍压在 :345 的 P-S2-012 占位下。
无法确认的部分: module.json5@v2(base3-network)与 @v3(实录外修改,T+26:52,68 行)两版内容账本判为"内容未知/无记录写者",无法直接核对它们是否触碰过 abilities[](仅能从 base3-network 自述与 v5 时的实际内容反推);P-S2-012 / P-S8-034 在 placeholder-registry 中的最终状态未直接查证,只有 fixer 在 v5 注释里的自述;主会话是否曾另派 agent 认领 wxapi 宿主,未逐一排查全部 closer。
置信: 高 —— 修复依据(派发词+finding单)、被改位置(纯新增)、前两版写者的职责边界、以及占位口径的源头(conv-wxcallback 派发词 → P-S2-012 → slice2-auth:345/351)全部有直接坐标;仅 v2/v3 内容未知,但 finding@v1 在修复前实测 abilities[] 仍只有两个模板 Ability,不影响结论。
```