```
文件: entry/src/main/ets/components/WorksComponent.ets  修复方: visual-fixer / fixer-r1(agent-a68daf720e780b4c2)  修改时间: 2026-07-26T20:54:51.158Z
修复改了什么: 把作品项点击的路由名从 `pushPathByName('PPTFilePage', params)` 改为 `pushPathByName('PptFilePage', params)`（一个字母 case），并订正上方那行「pageMap 路由名 'PPTFilePage'」的错误注释、追加一条警示说明。
修复的依据: 直接照单执行 finding `PPTFilePage_01_works_item_route_name_mismatch`（fixer 主 prompt 把它列为 P0 第 1 条，agent-a68daf720e780b4c2.jsonl:1；20:54:32 读了该 md 全文，:241）；并且改前自己用 `sed` 复核了真值锚点——SplashPage.ets 的 pageMap 分支确为 `} else if (name === 'PptFilePage') {`（:242 发起 / :243 结果，20:54:38）。
被改代码的来源: conv-worksfrag（a2h-activity-converter，agent-aconv-worksfrag-83d07f1d60db1b6b.jsonl:78，2026-07-24T06:30:51.557Z）整文件 Write 时写下的，依据是 Android 侧 `WorksFragment.kt:265 PPTFilePage.previewPPTFile(...)` 的类名 + `TemplatePreviewPage.ets:333` 一行**注释**里的 `pushPathByName('PPTFilePage', ...)`；它写的「pageMap 路由名 'PPTFilePage'」是无据推断——真正的注册名 `'PptFilePage'` 早在 2026-07-24T02:39:56.487Z 就由 abatch2-closer 落进 SplashPage 了（agent-abatch2-closer-0cd2cc98e7736f2f.jsonl:72），比它早近 4 小时。
生成时为什么没做好: 转换环（conv-worksfrag）查证路由名的那条 grep 本身是坏的——只 grep 了 `pushPathByName(...)` 调用点（结果全是注释）、pageMap 那半句用了 `-l` 只列文件名且被 `head` 截断，SplashPage 根本没出现在输出里，于是它拿 Android 类名当路由名写死。
是否必要: 必要，路由名不匹配时 `navDestination(pageMap)` 走不到任何分支，作品 Tab 点击静默无跳转，且该入口在 Android 侧是活的（HomeActivity 常驻 Tab2）。
证据(每条带位置):
  1. 修复动作：agent-a68daf720e780b4c2.jsonl:244（uuid f7a25bb0-…，2026-07-26T20:54:51.158Z）Edit，`'PPTFilePage'` → `'PptFilePage'` + 注释订正。
  2. 修复前自证：同文件 :242/:243（20:54:38），sed 出 SplashPage pageMap 分支 `name === 'PptFilePage'`。
  3. finding 出处：agent-afcfbf677a4e5864a.jsonl:169（vv-static-B「B系列静态验收」，2026-07-26T17:58:36.348Z）Write 该 md，`source: visual-verify / severity: P0`，evidence 列 WorksComponent.ets:586 vs SplashPage.ets:381 vs 正确的 TemplatePreviewPage.ets:255。
  4. 错误代码作者与依据：agent-aconv-worksfrag-83d07f1d60db1b6b.jsonl:78（2026-07-24T06:30:51.557Z）Write，含注释「目标页 pages/PptFilePage.ets 已存在（pageMap 路由名 'PPTFilePage'）」。
  5. 坏的查证环：同文件 :63/:64（06:25:38–39），grep 只命中 TemplatePreviewPage.ets:333、SplashPage.ets:114 两行注释；`grep -rln "pageMap..." pages/*.ets | head` 输出到 RefundProgressPage 即被截断，SplashPage 未进视野。
  6. 正确注册名早已存在：agent-abatch2-closer-0cd2cc98e7736f2f.jsonl:72（2026-07-24T02:39:56.487Z）Edit SplashPage 注册 `name === 'PptFilePage'`。
  7. 二次错失：F009 属主 slice20-works 在 agent-aslice20-works-2651c58894fb3cf9.jsonl:77/:78（2026-07-24T20:44:32）grep「who pushes PPTFilePage」，`WorksComponent.ets:396` 那行原样打在屏幕上，但它只查了"谁在推"没查"注册了什么"，随即转去核对入参形状（:80/:81）。
无法确认的部分: 修复后是否在 round-2 复验中被标记 fixed（未追到复验记录）；fixer 新增注释里「PushDetailRouter 的深链表也注册 'PptFilePage'」一句来自 finding 的修复建议原文（:241），fixer 本人未独立打开 PushDetailRouter.ets:206 核对。
置信: 高——改动、改前复核、finding 原文、错误代码的 Write 与其查证 grep 的完整输出、正确注册的时间戳，六个环节都有逐行转录直接落位，无需推断。
```