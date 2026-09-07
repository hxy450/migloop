```
文件: entry/src/main/ets/pages/SplashPage.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v53
修复改了什么: 给开屏页补了「系统栏显隐」这一整套原本不存在的行为——先由脚本 #23474 加 `import { window }`、`aboutToAppear` 里 `setSystemBarsVisible(false)`、`aboutToDisappear` 里 `true` 以及 `setSystemBarsVisible()` 方法本体（`window.getLastWindow().setWindowSystemBarEnable`）；账本立版的 v53(#23476) 是最后 5 行:在 `onRoute()` 开头再补一次 `this.setSystemBarsVisible(true)`,理由是本页是 Navigation 宿主、压子页时 `aboutToDisappear` 根本不触发。
修复的依据: 安卓侧 `themes.xml:17-22` 的 `Theme.SeceretBox.Launch` 带 `windowFullscreen=true`、且 `AndroidManifest.xml:99-102` 只把这个主题给了 SplashActivity(fixer-r1 v25 #23467/#23464);单子 `spec/fix/round-1/ui/ALIGN_PSplashActivity_extra_element_status-bar.md@v1`(fixer-r1 v22 读于 T+81:13);还原点选 `onRoute` 的依据是它自己 grep 出的 SplashPage@v52:166-167(#23469)。
被改代码的来源: 纯新增(blame v53 changed:替换 0 行 / 新增 5 行)。前一版写者是 group2b-closer v5(SplashPage@v52,#13174),它恰恰写下了 v52:160-177 那段「⚠ 平台差异(就地标注,不修):pushPathByName 压子页不会让本入口页收到 onPageHide」——它识别了同一个生命周期缺口,但派发词把它限定在 Slice 13 广告 F016,而广告链在 `canShowSplashAd()` 恒 false 下不可达,故判定「运行期无可观测影响」而只留注释;当时文件里根本没有系统栏控制(#23469 grep `window\.` 零命中),它没有第二个受害者可考虑。
生成时为什么没做好: 漏读——转换方 conv-splash v1(写 SplashPage@v2)的输入集里只有 activity_splash.xml / SplashActivity.kt / view.xml / meta.json / arkts-immersive-safearea SKILL,从没读过 AndroidManifest.xml 或 themes.xml,Activity 主题的 `windowFullscreen` 从未进入转换链路,被 meta.json `needs_immersive_safearea=true` 触发的「沉浸式四层」替代了,而那套只让背景穿透系统栏、并不隐藏它。
是否必要: 必要——v53 这 5 行防的是修复方自己在同一拍引入的回归:隐藏已加而唯一还原点 `aboutToDisappear` 在宿主页不触发,不补就会把状态栏永久藏到 Guide/Home 页。
证据(每条带坐标):
  1. `themes.xml@v1:17-22` — `Theme.SeceretBox.Launch` 含 `windowFullscreen=true`(fixer-r1 #23467 原文)。
  2. `AndroidManifest.xml@v1:99-102` — 该主题只挂 SplashActivity(fixer-r1 #23464 原文)。
  3. `SplashPage.ets@v52:166-167` — group2b-closer@v52 写下「onPageHide/压子页不触发…就地标注,不修」;其收尾报告亦列为「一处需要下游知晓的平台差异(已就地标注,未修)」(group2b-closer v5)。
  4. `blame SplashPage.ets@v53 changed=True` — 替换 0 行、新增 5 行,无原作者。
  5. `agent conv-splash v1` 读取集(#9915/#9917/#9909/#9925 等)不含 themes.xml / AndroidManifest.xml;派发词只给「沉浸式:needs_immersive_safearea=true → arkts-immersive-safearea 四层」。
  6. `themes.xml@v1` 下游读者共 5 个(ref-doc-analyzer v1、主会话·9b3105a2 v12 读 1-40 行、conv-webview v1、conv-shortcut v1、fixer-r1 v25)——信息 T+0:33 就在链路里,却没进到开屏页转换。
  7. fixer-r1 #23474 脚本原文含 `setSystemBarsVisible` 方法本体与注释「expandSafeArea(Layer 2) 只让背景穿透系统栏,并不隐藏它 —— 两者不可互相替代」,直接对应第 5 条的替代物。
无法确认的部分: ①单子 `ALIGN_PSplashActivity_extra_element_status-bar.md@v1` 是外部输入且「无法复原」,它给的判据(截图差异/oracle 强度)看不到;②修复注释断言「GuideActivity / HomeActivity 走基础主题、状态栏可见」——账本里没有任何一次读取覆盖这两个 Activity 的 manifest 主题行,该前提未取证;③#23474 是脚本落盘、账本只记成读(未立版本),故 v53 的账本 diff 只含 onRoute 那 5 行,`setSystemBarsVisible` 方法体与 `aboutToAppear` 的 `false` 调用是从动作原文而非版本内容确认的,账本复原的 v53 全文可能与磁盘不一致。
置信: 高——改了什么、凭什么改、前一版写者为何没写、生成链哪一环漏读,四条都各有工具坐标直接落地;扣分只在单子原文不可复原与脚本写未立版本这两处已标注的边界。
```