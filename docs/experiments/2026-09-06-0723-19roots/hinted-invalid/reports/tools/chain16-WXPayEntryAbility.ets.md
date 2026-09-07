```
文件: entry/src/main/ets/wxapi/WXPayEntryAbility.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v1
修复改了什么: 新建微信支付回跳宿主 UIAbility(72 行):onCreate/onNewWant 都把 want 转给 WxPayEntryHandler.getInstance().handleWant(),并把 finishCallback 注入为 context.terminateSelf();同一批还给 handler 补了 getInstance()(#23549),并在 module.json5@v5 注册了 WXPayEntryAbility(#23554)。
修复的依据: finding spec/fix/round-1/feat/BaseWXPayEntryActivity_01_no_wxpay_callback_ability.md@v1(vv-static-B v9 #26452)——§4 列出 module.json5:33 缺 ability、handleWant 零调用点、finishCallback 无注入方,§5.1/5.2 的处方逐条对应本文件写法;fixer-r1 v26 两次读该单(#23519/#23533),主会话派发词也明确「WXEntryAbility/WXPayEntryAbility 声明这一半现在就能做」。
被改代码的来源: 纯新增。前一版写者是 conv-wxpayentry v1(#11236,写 WxPayEntryHandler.ets@v1):它的派发词【输出】只有 handler 一个文件,SDK 与结果回传按规则走 FWD-REF(P-S7-012/013 resolve_by=Slice 7/8),宿主 Ability 被显式推给支付切片(handler 头 :19-20 自述「由支付切片产出」,被 finding §2 引用),所以它没写、也不该写。
生成时为什么没做好: 交接落空在计划一环——feature-plan.md@v16:572-606 的 Slice 8 integration_points/wires/modifies_files 里根本没有 wxapi/Ability/module.json5,而 slice8-pay 派发词又把 module.json5/Ability 类共享文件列为「禁碰,移交 group-closer」,converter FWD-REF 出去的这一半无人承接。
是否必要: 必要,finding is_migration_bug=true / P1,handler 全仓零引用、abilities[] 无该项(finding §3),不补则支付结果永远回不来;但只补齐了宿主一半,skills 与 want→resp 解析仍挂起。
证据(每条带坐标):
  1. WXPayEntryAbility.ets@v1 由 fixer-r1 v27 creation(#23550 T+81:24);配套 module.json5@v5 ← fixer-r1 v28(#23554)新增 WXPayEntryAbility 声明,注释写明「skills 有意留空(D-013),按 SDK 文档补」。
  2. 修复依据单 BaseWXPayEntryActivity_01_no_wxpay_callback_ability.md@v1:§5.1 要求「新建 wxapi/WXPayEntryAbility.ets…finishCallback 注入 terminateSelf…参考 WxCallbackHandler.getInstance()」——落盘文件 :54-64 与 #23549 的 getInstance 补丁逐条对上。
  3. 该单 §3:grep 全仓 WxPayEntryHandler 排除自身命中 0;module.json5 abilities[] 只有 EntryAbility(:33)/EntryBackupAbility —— 缺口成立,disposition=manual_review。
  4. 生成侧源头 conv-wxpayentry 派发词:【输出】entry/src/main/ets/components/WxPayEntryHandler.ets(单文件),SDK/回传走 FWD-REF resolve_by=Slice 7/8;其 v3 收尾登记 P-S7-012/013,未产 Ability。
  5. feature-plan.md@v16:600-606(slice8-pay v1 #20202 读到的原文)Slice 8 modifies_files 六个 page/dialog,无 module.json5、无 wxapi;slice8-pay 派发词「禁碰 EntryAbility.ets/他切片文件 —— 移交 group-closer」。
  6. slice_08_handoff.md@v2:125(group2-closer v75 #13116):「WXPayEntryHandler 无宿主 UIAbility」登记为 deferred_item,owner=arkts-payment、status=open,闭环条件正是纯接线;index(kind=agent, query=pay) 全库只有 conv-payagree/conv-h5pay/conv-wxpayentry/slice8-pay,没有 arkts-payment 这个后续 agent,该项无人认领直到 round-1。
无法确认的部分: ① skills 留空时微信回跳能否真正拉起该 Ability——fixer 自己判定需 SDK 文档并把这半挂起,账本无验证记录;② 修复后的编译/运行结果:仅 build-verify-r1 v6 对 WXPayEntryAbility.ets@v1 有一条「依赖读」(T+81:44),结论未入账;③ feature-plan.md@v16 全文「无法复原」,Slice 8 之外是否另有条目安排宿主 Ability,只能凭 #20202 的 520-649 段判断。
置信: 高——修复方读取集、finding 原文、handoff deferred_item、plan 原文四条独立坐标互相印证,唯一未取证的是修复后的运行效果。
```