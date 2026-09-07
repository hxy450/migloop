```
文件: entry/src/main/ets/wxapi/WXEntryAbility.ets  修复方: fixer-r1 / visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v1(修复期新建,71 行,#23547 @T+81:24)
修复改了什么: 新建微信授权/分享回跳的宿主 UIAbility —— onCreate/onNewWant 都走 dispatch(want):取 WxCallbackHandler 单例、挂 onFinish=terminateSelf、调 handler.handleIntent(want) 并吞异常,末尾再无条件 terminateSelf 兜底;同一 agent 的 v28 在 module.json5@v5 注册了该 Ability(skills 有意留空)。
修复的依据: spec/fix/round-1/feat/WXCallbackActivity_01_no_wxentry_callback_ability.md@v1 的 §3「handleWant/onResp 全仓零调用点、module.json5 abilities[] 无 WXEntryAbility」与 §5 处方 1/2/4(新建 Ability + 注册 + 未入仓期自关闭兜底);fixer-r1 v26 两次读该单(#23519、#23533),并读 WxCallbackHandler.ets@v15 225-275 行(#23540)确认真实入口名。
被改代码的来源: 纯新增,无生成侧版本。前一版写者是 conv-wxcallback(a2h-activity-converter)v1(#11118 T+17:03):其派发词把【输出】限死为单文件 entry/src/main/ets/components/WxCallbackHandler.ets,并规定「微信 SDK 具体接入(IWXAPI/handleIntent/WXEntryActivity 注册)→ 华为侧无等价,属三方 SDK,用 PLACEHOLDER/FWD-REF」且「不写共享文件」,于是宿主 Ability 被登记成占位 P-S2-012 而不是产物;下游也无人认领 —— group1-closer v27(Slice 2 owner)只解除注入侧 P-S2-013,group1b-closer v4 写 module.json5@v4 时的范围是 slice 6/7 深链 skills。
生成时为什么没做好: 出在 a2h-execute 的派发/任务切分这一环 —— 转换器派发词把「WXEntryActivity 注册」定性为三方 SDK 依赖(P-S2-012)、输出只准一个 handler 文件,纯 ArkTS 就能做的宿主 Ability 因此掉出产物清单,不是读旧版或转换错。
是否必要: 必要,回流侧无宿主 Ability 时 F003ViewModel 注册的 authListener 永远收不到回调(单 §3/§4),这半条链只能靠新建 Ability + module.json5 注册补上。
证据(每条带坐标):
  1. sessions(WXEntryAbility.ets):生成期未产出 · 修复期新建,修复方 fixer-r1 文件 v1 @T+81:24 —— 链根类型 created。
  2. file WXEntryAbility.ets@v1 写者脊柱:v1 ← fixer-r1 v26(#23547),内容含 onCreate/onNewWant → dispatch → handleIntent + 双重 terminateSelf。
  3. 单 WXCallbackActivity_01_...md@v1(vv-static-B v10 于 T+77:58 创建)§3/§4/§5:module.json5:33 缺条目、handleWant 零调用点、F003ViewModel.ets:344/351 半条链;fixer-r1 v26 读到 (#23519/#23533)。
  4. action(fixer-r1,#23540):sed 225-275 行看到 WxCallbackHandler@v15 的真实入口是 handleIntent(want),handleWant 是 WxPayEntryHandler 的名字 —— 修复方按源码取名,没照抄单里 §5.1 的 handleWant。
  5. agent conv-wxcallback v1 派发词全文:【输出】=WxCallbackHandler.ets、「WXEntryActivity 注册…属三方 SDK,用 PLACEHOLDER」、「不写共享文件」;其产物 WxCallbackHandler.ets@v15 注释(见 #23540)自述 onFinish「交宿主微信入口 UIAbility(WXEntryAbility,SDK 门面)自行终止」。
  6. agent group1-closer v27 收尾:resolved_fwd_refs 含 P-S2-013 不含 P-S2-012;派发词 cross_slice_edits 只列 MineComponent/network 两处,无宿主 Ability。agent group1b-closer v4:module.json5@v4 仅追加深链 skills(范围 slice 6/7)。
  7. diff module.json5@v5(fixer-r1 v28,#23554):补 WXEntryAbility/WXPayEntryAbility 两条 abilities,注释写明 skills 留空待微信鸿蒙版 SDK 文档(D-013)。
无法确认的部分: skills 留空时微信能否真把回跳投递到本 Ability —— 账本内无 SDK 文档证据,fixer 自己也把 skills 声明列为挂起项;handleIntent 仍是 P-S2-012 占位(只打日志),端到端 code→token 是否通无法确认;下游只有 build-verify-r1 v6 的「依赖读」,编译/验证结论不在实录中。
置信: 中,修复内容、依据单、转换器派发词三处都是直证,但我未核 feature-plan 是否在别处派过「宿主 Ability」任务,该项只由两个 closer 的派发词间接排除。
```