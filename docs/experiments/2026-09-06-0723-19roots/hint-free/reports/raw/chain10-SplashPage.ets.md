```
文件: entry/src/main/ets/pages/SplashPage.ets  修复方: visual-fixer「fixer-r1」(agent-a68daf720e780b4c2, agentType=visual-fixer, spawnDepth=1)  修改时间: 2026-07-26T21:20:10Z(隐藏/helper) 与 21:20:24Z(onRoute 还原)
修复改了什么: 给开屏页补真正的「全屏」——import 补 `window`、新增 `setSystemBarsVisible()`(`win.setWindowSystemBarEnable([])` / `['status','navigation']`)，`aboutToAppear` 末尾隐藏系统栏，`onRoute()` 首行还原、`aboutToDisappear` 兜底还原。
修复的依据: 单 `spec/fix/round-1/ui/ALIGN_PSplashActivity_extra_element_status-bar.md` §3+§5：鸿蒙截图顶部多一条状态栏、dump 里有 `WindowScene [0,0][1216,126]` 且 root 从 y=127 起；加上修复方自己回源取证 `AndroidManifest.xml:102` 给 SplashActivity 单独指定 `@style/Theme.SeceretBox.Launch`、`themes.xml:17-23` 含 `android:windowFullscreen=true`，且全工程只有开屏页用该主题(agent-a68daf720e780b4c2.jsonl:477/479)。
被改代码的来源: 属「纯新增 + 推翻旧沉浸方案」。旧方案由生成轮 `entry-setup`(sonnet, customAgentType=a2h-migration-worker)在 2026-07-24T02:27:37 写 EntryAbility 的 Layer 1(`setWindowLayoutFullScreen(true)` + 透明系统栏)、02:32:52 写 SplashPage 根 Navigation 的 Layer 2(`expandSafeArea`)，依据是 team-lead 任务书末句「沉浸式 Layer 1 + Layer 2 可一并按 arkts-immersive-safearea 装配」。它没写隐藏，因为该四层模板做的是「背景穿透系统栏」，压根不含 `setWindowSystemBarEnable([])`。
生成时为什么没做好: 断在页面规格这一环——`spec/baseline/ui/page_0001_SplashActivity.md` 的沉浸式一节只写 `needs_immersive_safearea = true（基于 page_type = full_screen_page 自动判定）→ converter 按 arkts-immersive-safearea 四层架构实施（spec 不列 API 以避免与 skill 漂移）`，用页型启发式代替了 Activity 主题真值，`windowFullscreen=true` 虽被 ref-doc-analyzer 抓到却没进任何页面级要求。
是否必要: 必要——安卓侧确为主题级全屏、`expandSafeArea` 不隐藏系统栏，二者不可互替；只是还原点覆盖不全(见下)。
证据(每条带位置):
  1. 修复动作本体：agent-a68daf720e780b4c2.jsonl:485(Bash python 补 import/`setSystemBarsVisible`/`aboutToAppear` 隐藏/`aboutToDisappear` 还原, ts=2026-07-26T21:20:10.255Z) 与 :488(Edit `onRoute` 首行插 `this.setSystemBarsVisible(true)`, uuid=4f6ad3c2-d145-4f70-9b9b-0a16f359b0c5, ts=21:20:24.982Z)。
  2. 修复依据单原文：agent-a68daf720e780b4c2.jsonl:439，含 §4「SplashPage.ets:505-516 只做了 expandSafeArea 沉浸(Layer 2)，未做状态栏隐藏」与 §5 两步处方(隐藏 + 离开时还原)。
  3. 单的作者与取证强度：visual-verify 子 agent `vv-t1-A01`(agent-aa2d7cdfd6a5cf89f, ts=2026-07-26T15:52:44.043Z, :235)写 manifest，SplashActivity similarity=0.73 / status=fail / verify_confidence=high，fix_files 列出该单。
  4. 旧沉浸方案出处：agent-aentry-setup-07108f5df45c357c.jsonl:70(EntryAbility「沉浸式 Layer 1」, 02:27:37.706Z) 与 :123(SplashPage「沉浸式 Layer 2 ... expandSafeArea」, 02:32:52.166Z)；meta.json 显示 model=sonnet。
  5. 上游指令：同文件 :1(2026-07-24T02:24:52.099Z) team-lead 任务书末条「沉浸式 Layer 1(EntryAbility setWindowLayoutFullScreen)+ Layer 2(入口页根 Navigation expandSafeArea)可一并按 arkts-immersive-safearea 装配（Batch 1 converter 把这两层延迟给了入口壳）」——全篇未提 SplashActivity 主题。
  6. 页面规格的启发式判定：agent-aconv-splash-9d5902d803bbcde6.jsonl:9 读入 `spec/baseline/ui/page_0001_SplashActivity.md`，§沉浸式 = 「needs_immersive_safearea = true（基于 page_type = full_screen_page 自动判定）→ 按四层架构实施（spec 不列 API）」。
  7. 真值确实被采集过但没下发：`android:windowFullscreen=true` 在生成轮仅出现于 9b3105a2-…jsonl:404 与 agent-aref-doc-analyzer-d4e8fbf7e1d0dbac.jsonl:128/175(主题继承类图)，conv-splash 与 entry-setup 的转录里 0 命中。
  8. 修复方自评已入单：agent-a68daf720e780b4c2.jsonl:615「### round-1 attempt by visual-fixer」，写明「expandSafeArea 让背景穿透系统栏，不会隐藏它 —— 两者不可互相替代」，:616 确认 append 成功；:628 终报 51/51 处理、47 改 2 新、未编译未复测(任务书 :1「不重编、不复测」)。
无法确认的部分: (a) 修复未经编译与复测，实际像素效果未验证——本目录无 round-2 verifier 转录；(b) 还原点只挂在 `onRoute` 与 `aboutToDisappear`，开屏页的另两个出口(点隐私弹窗里的协议链接跳 WebViewPage、拒绝后退出应用)是否也需还原，转录里没有讨论，我无法从 JSONL 判断是否留下「状态栏一直隐藏」的残留态；(c) `spec/baseline/ui/page_0001_SplashActivity.md` 里 `page_type=full_screen_page` 这一字段本身由哪个 agent、按什么规则赋值，未在本次追查中定位到写入点。
置信: 高 —— 修改点、驱动单、单的作者、旧代码作者与其上游指令四链均有原始转录逐条对上；仅收尾覆盖面与规格字段来源两处留白，不影响主结论。
```