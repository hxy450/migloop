```
文件: entry/src/main/ets/wxapi/WXEntryAbility.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v1(creation,72 行,fixer-r1 v26 #23547)
修复改了什么: 新建微信授权/分享回调宿主 UIAbility——onCreate/onNewWant 都走 dispatch(want),取 WxCallbackHandler 单例、挂 onFinish=terminateSelf、调 handleIntent(want) 并吞异常,末尾无条件 terminateSelf 兜底;同一 agent 的 v28 把它连同 WXPayEntryAbility 写进 module.json5@v5(skills 有意留空)。
修复的依据: 单 spec/fix/round-1/feat/WXCallbackActivity_01_no_wxentry_callback_ability.md@v1 的 §3「module.json5 只有 EntryAbility,handleWant/onResp 全仓零调用点」+ §5 建议 1/4(新建 wxapi/WXEntryAbility.ets、分发后自关闭、SDK 未入仓期必须兜底自关);派发词「需要判断的」一节明确授权:module.json5 补 WXEntryAbility/WXPayEntryAbility 声明「现在就能做」,skills 待 SDK 文档。落笔前读了 WxCallbackHandler.ets@v15 225-275 行(#23540)确认 handleIntent/onFinish 的真实签名。
被改代码的来源: 纯新增,生成期无任何版本(sessions:生成期未产出)。前一版写者是 conv-wxcallback(a2h-activity-converter,派发自 主会话·9b3105a2@v121):它的派发词把输出钉死为 entry/src/main/ets/components/WxCallbackHandler.ets、并规定「WXEntryActivity 注册 → 华为侧无等价,属三方 SDK,打 PLACEHOLDER」「不写共享文件」,所以它只产出 handler(WxCallbackHandler.ets@v1 #11118),把 finish() 做成 onFinish 钩子「交宿主微信入口 UIAbility 终止」,宿主本身登记为占位 P-S2-012 留给 SDK 入仓;接棒的 slice2-auth 也只接了发起侧。
生成时为什么没做好: 卡在派发/切分这一环——conv-wxcallback 的派发词把「宿主 Ability 注册」(纯 ArkTS 接线)与「want→resp 解析」(真三方 SDK)捆进同一个 P-S2-012 占位,能做的那一半也随 SDK 一起被挂起,且输出目录限死在 components/、禁改 module.json5,于是没有任何 agent 认领宿主。
是否必要: 必要,不补宿主则微信回跳无落地 Ability、F003ViewModel 注册的 authListener 永远收不到回调(半条链),且本次改动不依赖 SDK。
证据(每条带坐标):
  1. entry/src/main/ets/wxapi/WXEntryAbility.ets@v1 写者脊柱:唯一一版 ← fixer-r1 v26 #23547 @T+81:24,creation;sessions 该链根 = created(生成期未产出)。
  2. 单 WXCallbackActivity_01_no_wxentry_callback_ability.md@v1(vv-static-B v10 #26454 写)§3/§4:module.json5:33 abilities[] 无 WXEntryAbility、handleWant/onResp 零调用点;§5.1/§5.4 即本次改法。fixer-r1 v26 两次读该单(#23519、#23533)。
  3. fixer-r1 派发词(主会话 ff019d8a@v74)「需要判断的」:module.json5 补两个 Ability 声明「现在就能做」,skills 须查 SDK 文档——对应 module.json5@v5 diff 里 skills 留空的注释。
  4. conv-wxcallback 派发词全文:【输出】components/WxCallbackHandler.ets;第 2 条「IWXAPI/handleIntent/WXEntryActivity 注册 → 华为侧无等价…用 PLACEHOLDER」;结尾「不写共享文件」。
  5. conv-wxcallback 收尾报告:P-S2-012 登记于 WxCallbackHandler.ets:255,trigger 文字里就含「WXEntryAbility 注册」;`Activity.finish()` → onFinish 钩子「交宿主微信入口 UIAbility 终止」。#23540 读到的第 230 行原文同款自述。
  6. blame F003ViewModel.ets@v17:344/351 行 ← slice2-auth@v13——只做 setAuthListener 注入,注释承诺「回调经 WXEntryAbility 回流」,而该 Ability 直到 T+81:24 才存在。
无法确认的部分: spec/placeholder-registry.md@v57 因盲写断点内容无法复原,P-S2-012 在生成期收尾时的状态(是否被标为未解、是否有人被指派补宿主)无法确认;skills 留空后微信真实回跳能否被系统投递到本 Ability,账本内无判据(依赖微信鸿蒙版 SDK 文档,D-013 挂起);handleIntent 目前仍是只打日志的占位,故本次修复只补齐宿主一半,code→token 是否能通无法确认。
置信: 高,新建/派发词/占位登记/下游注册四处坐标互相印证且都是原文级证据;仅 placeholder 登记表的终态因盲写不可复原。
```