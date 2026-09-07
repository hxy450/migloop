```
文件: entry/src/main/ets/pages/SplashPage.ets  修复方: visual-fixer 修复 round-1 / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v53
修复改了什么: 在 `onRoute()` 首行插入 `this.setSystemBarsVisible(true)` + 4 行注释（共 5 行，纯新增），把"离开开屏页时还原系统状态栏/导航条"的动作从 `aboutToDisappear` 挪到真正的"跳走"这一拍。
修复的依据: 修因单 spec/fix/round-1/ui/ALIGN_PSplashActivity_extra_element_status-bar.md@v1（fixer-r1 v22 #23428 读入）；源码依据是同一版窗口内 grep 到的 themes.xml:17-20 `Theme.SeceretBox.Launch` → `android:windowFullscreen=true`（#23467）与 AndroidManifest.xml:99（#23464）——全屏态只属于 SplashActivity；挂载点依据是本页 v52:165-169 已写明的平台差异（Navigation 宿主压入子页不会触发页面级隐藏/销毁回调）。
被改代码的来源: 纯新增（blame v53 changed=True：替换 0 行）。但它纠正的是 fixer-r1 自己 14 秒前在同一版窗口用 python heredoc 写下的代码（#23474：加 `import window`、`aboutToAppear` 末尾 `setSystemBarsVisible(false)`、`aboutToDisappear` 里 `setSystemBarsVisible(true)` 及该私有方法本体）——那笔写是脚本黑盒、账本未立版。生成期（v2 起）根本没有任何"隐藏/还原状态栏"代码，故不存在更早的写者。
生成时为什么没做好: 漏读——生成链路的转换环 conv-splash v1 的读取集里没有 AndroidManifest.xml / themes.xml（派发词只给了 `needs_immersive_safearea=true` 的四层沉浸式指令），主题级的 `windowFullscreen` 从未进入上下文，沉浸式四层只做"背景穿透系统栏"（v53:518-520）而不隐藏系统栏。
是否必要: 必要——若只留 `aboutToDisappear` 里的还原，SplashPage 作为 Navigation 宿主压入 GuidePage/HomePage 时不销毁、回调不触发，全屏态会泄漏到后续所有页面。
证据(每条带坐标):
  1. diff SplashPage.ets@v53 + action(fixer-r1,#23476) Edit 原文：`onRoute` 首行插 `this.setSystemBarsVisible(true)` 与 4 行注释；blame(v53, changed=True) 报"替换/删除 0 行，新增 5 行"。
  2. action(fixer-r1,#23474) 原文：同一版窗口先跑 python heredoc 落盘 `setSystemBarsVisible(false)`（aboutToAppear）+ `(true)`（aboutToDisappear）+ `window.getLastWindow().setWindowSystemBarEnable` 方法体；该写未立版（file 原子只把 #23238/#23348 列为"方向不明"，复原全文里查不到该方法、`onRoute` 在复原文本是 339 行而 grep 实盘是 382 行）。
  3. action(fixer-r1,#23467) grep 原文：themes.xml:17 `Theme.SeceretBox.Launch` → :20 `android:windowFullscreen=true`，:18 cutout shortEdges；action(#23464) 见 AndroidManifest.xml:99 SplashActivity。
  4. agent(fixer-r1) v22 (#23428) 读入 spec/fix/round-1/ui/ALIGN_PSplashActivity_extra_element_status-bar.md@v1 —— 修因单（"开屏页多出状态栏"）。
  5. blame SplashPage.ets@v53:165-169 → group2b-closer@v52 已就地写明"`pushPathByName` 压入子页并不会让本入口页收到 `onPageHide`"，与 v53 注释里"aboutToDisappear 压根不会触发"是同一事实。
  6. agent(conv-splash, 全生命周期) v1 读取集（#9904–#9957）：activity_splash.xml / SplashActivity.kt / bg_launch.xml / splash_progressbar.xml / arkts-immersive-safearea SKILL.md —— **无** AndroidManifest.xml、**无** themes.xml。
  7. file(themes.xml)@v1 下游读者仅 5 个：ref-doc-analyzer v1 / 主会话·9b3105a2 v12（1-40行）/ conv-webview v1 / conv-shortcut v1 / fixer-r1 v25 —— SplashPage 这条链上的 conv-splash、slice11-startup、group2b-closer 一个都不在。
无法确认的部分: ALIGN_PSplashActivity_extra_element_status-bar.md@v1 是外部输入且读取时无全文快照，内容无法复原，"修因具体判据/截图证据"只能由 slug 与读记录推断；#23474 那笔脚本写未立版，v53 的账本复原全文与实盘不一致（缺 `setSystemBarsVisible` 方法体、行号少 43 行），故 v53 全文以复原为准会失真；主会话·9b3105a2 v12 只读了 themes.xml 的 1-40 行，是否把 `windowFullscreen` 传给过任何转换 agent，账本中无法确认。
置信: 高——修复的 Edit 原文、被它纠正的脚本原文、以及作为依据的 themes.xml grep 原文三份实录都直接拿到了；生成侧的漏读由 conv-splash 完整读取集与 themes.xml 读者名单双向对上。唯一未闭合的是修因单正文不可复原。
```