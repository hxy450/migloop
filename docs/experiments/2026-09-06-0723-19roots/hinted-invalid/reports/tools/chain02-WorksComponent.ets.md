```
文件: entry/src/main/ets/components/WorksComponent.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v12
修复改了什么: 把作品项点击的 `pushPathByName('PPTFilePage', params)` 改成 `'PptFilePage'`(2 行被替换、新增 4 行),同时订正上方那句写错的行内注释并补了一段"路由名是小写 pt、写成安卓类名会走不到任何 navDestination 分支"的警示注释。
修复的依据: 单 `spec/fix/round-1/feat/PPTFilePage_01_works_item_route_name_mismatch.md@v1`(§3/§5:pageMap 只注册 'PptFilePage',全仓 push 名字直方图里 'PPTFilePage' 是唯一没注册的)+ 主会话派发词 P0 第 1 条点名此单;fixer 落盘前自己 sed 打印过 WorksComponent 578-595 与 SplashPage 375-385(agent v16 #23243)对过真值。
被改代码的来源: conv-worksfrag(a2h-activity-converter,agent-aconv-worksfrag-83d07f1d60db1b6b)@v1 写的。它按安卓锚点 `WorksFragment.kt:265 → PPTFilePage.previewPPTFile(...)` 直接把安卓类名当路由名用,手里没有 pageMap 真值。
生成时为什么没做好: 漏读 —— conv-worksfrag@v1 的读取集里没有 pageMap 真值锚点 `SplashPage.ets`(修复方读了),而它读全了的 `PptFilePage.ets@v5` 尾注只写"入口页 pageMap 路由注册用"、没写路由名;同批参照的 `TemplatePreviewPage.ets@v5` 尾注写了路由名,所以隔壁收藏项那行名字反而是对的。
是否必要: 必要,路由名未注册时 `pushPathByName` 走不到任何 pageMap 分支,作品 Tab 点作品静默无跳转(单 §3 + SplashPage 375-385 实录)。
证据(每条带坐标):
  1. diff WorksComponent.ets@v12(fixer-r1 v16,#23246 T+80:51):`'PPTFilePage'` → `'PptFilePage'`,注释同步订正并加警示两行。
  2. blame WorksComponent.ets@v12 changed:被替换 2 行(v11 的 583 注释 / 586 push)原作者均为 conv-worksfrag@v1。
  3. 单 `PPTFilePage_01_works_item_route_name_mismatch.md@v1`(vv-static-B v7 写,T+77:55)§3 指出注释「pageMap 路由名 'PPTFilePage'」与 SplashPage.ets:381 矛盾、是笔误来源;fixer-r1 v16 #23240 读了它。
  4. fixer-r1 v16 #23243 原文:SplashPage pageMap 分支 `else if (name === 'PptFilePage')`,与 WorksComponent 推的名字并排打印。
  5. 真值早于生成:batch2-closer(agent-abatch2-closer-0cd2cc98e7736f2f,v14 T+14:43)收尾报告 `pagemap_routes_added: ['LoginPage','MemberCenterPage','PptFilePage']`;SplashPage.ets@v52:383 blame 亦归它 —— 比 conv-worksfrag 写 v1 的 T+18:27 早约 4 小时。
  6. conv-worksfrag v1 读取集(#10811–#10879)无 SplashPage.ets;#10841 原文显示 PptFilePage.ets@v5:99-103 只写「入口页 pageMap 路由注册用」,不含路由名字面量。
  7. 对照组:#10875 原文 TemplatePreviewPage.ets@v5 尾注明写「pageMap 中登记的路由名应为 'PPTTemplatePreviewPage'」→ 同函数隔壁收藏项跳转名字写对了。
  8. 同一次 #10875 读到的 TemplatePreviewPage.ets@v5 里 FWD-REF P-S18-004 注释写的正是 `pushPathByName('PPTFilePage', ...)`(错名);单里当参照的正确行 TemplatePreviewPage.ets:255 是 slice18-pptgen@v6 解 FWD-REF 后才写的(blame @v8)—— 生成当时没有正确样例可抄,只有带错字面量的注释。
无法确认的部分: conv-worksfrag v1 的「收件 1 条」未展开,是否含路由命名指令不明;SplashPage 注册那一笔的具体写入动作号未展开(只凭 batch2-closer 收尾报告与 blame 定的写者与时段);WorksComponent.ets 在 fixer-r1 v26 #23492(T+81:19)还被一次「脚本字面量方向不明」碰过,该次是否再动本行未确认。
置信: 高 —— 改动、依据单、真值锚点、原作者读取集(缺 SplashPage)与同批对照组四条链都有原文坐标,唯一的推断只在"参照物注释污染"这一条动机上。
```