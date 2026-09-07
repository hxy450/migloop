```
文件: entry/src/main/ets/wxapi/WXPayEntryAbility.ets  修复方: visual-fixer「fixer-r1」(agent-a68daf720e780b4c2)  修复版本: v1(由 fixer-r1 v27 创建,T+81:24)
修复改了什么: 新建微信支付回跳的宿主 UIAbility(73 行):onCreate/onNewWant 把 want 交给 WxPayEntryHandler.getInstance().handleWant(),并把 finishCallback 注入为 context.terminateSelf();同批还给 handler 补了单例入口(#23549)、在 module.json5@v5 注册 WXPayEntryAbility(skills 有意留空)。
修复的依据: 静态验收单 spec/fix/round-1/feat/BaseWXPayEntryActivity_01_no_wxpay_callback_ability.md@v1(P1/IMPL_MISSING),§3 记「WxPayEntryHandler 全仓零引用、module.json5:33 无该 Ability」,§5 给的处方 1/2 与落盘代码逐条对应;fixer-r1 v26 读过该单两次(#23519、#23533),其派发词也点名「module.json5 补 WXEntryAbility/WXPayEntryAbility 这一半现在就能做」。
被改代码的来源: 纯新增,无生成侧版本(sessions:created)。最近的前置写者是 conv-wxpayentry(a2h-activity-converter),它在 T+17:02 写了 WxPayEntryHandler.ets@v1(#11236);其派发词【输出】只列了这一个 handler 文件、并要求 SDK 管道与事件回传走 FWD-REF(P-S7-012/013,resolve_by=支付切片),宿主 Ability 不在它的产出清单里。接棒的 slice8-pay 派发词又把该 handler 标为「已存在勿新建」+ 单写者纪律禁碰共享工程文件,只把 P-S7-012 转登为 P-S8-034(thirdparty-sdk,WxPayEntryHandler.ets:91,仅覆盖 createWXAPI+handleWant)。
生成时为什么没做好: 出在派发切分环——no_ui 回调页被定义成「只产 handler 模块」,宿主 UIAbility + module.json5 注册这一半没进任何 agent 的输出清单,后续切片的禁碰纪律又堵死了补齐路径(不是源码没读:conv-wxpayentry 读了 BaseWXPayEntryActivity.java@v2 全文 #11174)。
是否必要: 必要,回流侧缺宿主时 handleWant/onResp/postPayEvent 零调用点、支付真实成功路径永不触发,补的又是纯 ArkTS 接线、不依赖 SDK 入仓。
证据(每条带坐标):
  1. WXPayEntryAbility.ets@v1 ← fixer-r1 v27 (#23550, T+81:24) creation·73 行;sessions 该链标「生成期未产出·修复期新建」。
  2. 依据单 BaseWXPayEntryActivity_01_no_wxpay_callback_ability.md@v1 ← vv-static-B v9 (#26452);§3「grep -w WxPayEntryHandler 排除自身 0 命中」+「module.json5:33 abilities[] 无 WXPayEntryAbility」。
  3. 配套落地:action(fixer-r1,#23549) 给 WxPayEntryHandler 插入 getInstance() 单例;module.json5@v5 ← fixer-r1 v28 (#23554) 新增 WXEntryAbility/WXPayEntryAbility 两条声明,注释写明 skills 按 D-013 留空。
  4. 上游一:conv-wxpayentry 派发词(主会话 9b3105a2@v122 派发)【输出】= entry/src/main/ets/components/WxPayEntryHandler.ets,SDK 与结果回传走 FWD-REF resolve_by=Slice 7;其收尾登记 P-S7-012/013,无宿主 Ability 项。
  5. 上游二:slice8-pay 派发词(9b3105a2@v200)把 components/WxPayEntryHandler.ets 列入「已存在勿新建」,并「禁碰 placeholder-registry / EntryAbility.ets / 他切片文件——移交 group-closer」;其收尾把该点登记为 P-S8-034(thirdparty-sdk,WxPayEntryHandler.ets:91),trigger 只写 createWXAPI+handleWant。
  6. 缺口被登记但未闭环:finding §3 引 spec/placeholder-registry.md:802 P-S8-034 status=planned「未覆盖宿主 Ability 未注册这一半」+ slice_08_handoff.md:124 status=open owner=arkts-payment。
无法确认的部分: P-S8-034 究竟由哪个 agent 写进 placeholder-registry.md:802 —— 该文件 @v57 内容「无法复原(盲写)」,只能凭 finding 的引用;WxPayEntryHandler.ets@v2 是 07-24T15:37 的「实录外修改」,改了什么未知;修复后是否真能收到微信回跳无证据 —— 派发词明令不重编不复测,下游只有 build-verify-r1 v6 对 WXPayEntryAbility.ets@v1 的一次依赖读,无编译/运行结论,且 skills 仍留空。
置信: 高 —— 修复方、修复版本、依据单、两级上游派发词都有工具坐标可指;仅 registry 原文不可复原与「未复测」两处留白,不影响归因结论。
```