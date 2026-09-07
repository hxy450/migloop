```
文件: entry/src/main/module.json5  修复方: visual-fixer 修复 round-1 fixer-r1(agent-a68daf720e780b4c2)  修复版本: v5
修复改了什么: 在 abilities[] 追加 WXEntryAbility / WXPayEntryAbility 两个 UIAbility 声明(srcEntry 指向同轮新建的 ets/wxapi/*.ets,launchType=singleton、exported=true),skills 有意留空;纯新增 38 行,未改动 v4 任何一行。
修复的依据: vv-static-B 产的两张 P1 单 WXCallbackActivity_01_no_wxentry_callback_ability.md@v1(:55「abilities[] 只有 EntryAbility 与 EntryBackupAbility,没有 WXEntryAbility」、:63 源码缺口、§5 处方逐条)与同根的 BaseWXPayEntryActivity_01;主会话 ff019d8a@v74 的派发词又点名「module.json5 补 WXEntryAbility/WXPayEntryAbility 这一半现在就能做」。
被改代码的来源: 纯新增(blame v5 changed=True:替换 0 行/新增 38 行)。前一版 module.json5@v4 的写者 group1b-closer v4(#12169)没写,是因为它的派发词(主会话 9b3105a2@v199 步骤 1b)对 module.json5 的授权只有 Slice 7 的深链 skills 一项,它读的也只是 app/ 与 push/ 的 AndroidManifest(#12156),微信锚点在 pay/src/main/AndroidManifest.xml:13/38,不在其 slice 与读取集内。
生成时为什么没做好: 断在转换器的派发词一环 —— 主会话 9b3105a2@v121 给 conv-wxcallback 的指令把「WXEntryActivity 注册」和 IWXAPI/handleIntent 一起判成「华为侧无等价,属三方 SDK」并要求打占位、且「不写共享文件」,于是宿主 Ability 声明(实为纯 ArkTS 接线)被折进 SDK 阻塞占位,再没有任何收尾方把它认领回来。
是否必要: 必要,单标 is_migration_bug=true/P1,发起侧 F003ViewModel.ets:344 已注册监听而回流侧零宿主,是真缺失;但它是半修 —— skills 留空、SDK 未入仓,回跳链仍不通。
证据(每条带坐标):
  1. entry/src/main/module.json5@v5 ← fixer-r1 v28 (#23554),diff 仅新增两段 abilities;blame(v5, changed=True)=替换 0 行、新增 38 行。
  2. fixer-r1 v26 读 spec/fix/round-1/feat/WXCallbackActivity_01_*.md@v1 与 BaseWXPayEntryActivity_01_*.md@v1 (#23519、#23533),读 module.json5@v4[1-60行] (#23536),随后写 WXEntryAbility.ets@v1 (#23547)、WXPayEntryAbility.ets@v1 (#23550),最后写 module.json5@v5。
  3. 单 @v1 第 29-30 行 disposition: manual_review / disposition_reason「宿主 Ability 注册是纯 ArkTS 接线、现在就能做;want→resp 解析依赖 SDK 入仓(D-013)」,与修复版注释的 D-013 挂起说明一致。
  4. conv-wxcallback(agent-aconv-wxcallback-3f5b8f543d8ac407)派发词第 2 条把「IWXAPI/handleIntent/WXEntryActivity 注册」整体归为三方 SDK 占位,末行「不编译、不写共享文件」;其收尾登记 P-S2-012 kind=thirdparty-sdk,trigger=微信登录 SDK 入仓(含 WXEntryAbility 注册)。
  5. conv-wxpayentry(agent-aconv-wxpayentry-b19fa344fcafd4d8)派发词同样「不写共享文件」,只留 P-S7-012 forward-ref(resolve_by=Slice 7 Step 3d),同样没有 module.json5 出口。
  6. group1b-closer v4 收尾报告 wired_shared_files 明写 module.json5 只追加了 startapp 深链 skills「既有 home skill 未动」;它还把 P-S7-001..013 的 resolve_by 从 Slice 7 订正到 Slice 8,而 module.json5 全生命周期只有 5 版,Slice 2/8 侧无人写过它。
无法确认的部分: (a) Slice 2 / Slice 8 的收尾方派发词里是否本来就该含 module.json5 注册 —— 只证到它们没写过该文件,没逐个读其派发词;(b) module.json5@v3(T+26:52,68 行)标「实录外修改」,写者与动机不在账内;(c) 修复版 WX*Ability 的 skills 留空是否满足微信鸿蒙版 SDK 回跳契约,账本里没有该 SDK 文档,无从核对。
置信: 高。修复方的读取集、依据单、上游派发词三处首尾相连且都在实录里可逐条定位;唯一外推是 (a) 的责任归属,已单列。
```