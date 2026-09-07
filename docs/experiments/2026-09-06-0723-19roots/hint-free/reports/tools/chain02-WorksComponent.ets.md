```
文件: entry/src/main/ets/components/WorksComponent.ets  修复方: visual-fixer 修复 round-1 / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v12
修复改了什么: 把作品项点击的 `pushPathByName('PPTFilePage', params)` 改成 `pushPathByName('PptFilePage', params)`(替换 2 行、新增 4 行),并订正行内注释、补两行「路由名不是 Android 类名」的警示。
修复的依据: 单子 spec/fix/round-1/feat/PPTFilePage_01_works_item_route_name_mismatch.md@v1(P0,vv-static-B v7 写于 T+77:55)在 #23240 被读;fixer 又在 #23243 亲自读 SplashPage.ets@v52[375-385行] 核对注册名,blame 显示 :382 `} else if (name === 'PptFilePage') {`(batch2-closer@v14 写)——push 的名字在 pageMap 里根本不存在,点击走不到任何 navDestination 分支。
被改代码的来源: conv-worksfrag(agent-aconv-worksfrag-83d07f1d60db1b6b)在自己 v1 写 WorksComponent.ets@v1 时写下(#10881 T+18:27),v1→v11 十版无人动过;它的依据是 Android 侧类名 `PPTFilePage`(读了 PPTFilePage.kt@v2 #10875,又读了 PptFilePage.ets@v5 头部溯源注释「Android 类: …page.PPTFilePage」),把类名当成了路由名。
生成时为什么没做好: 漏读 —— conv-worksfrag v1 的读取集里没有 SplashPage.ets(全工程唯一登记 pageMap 路由名的地方),它读的 main_pages.json@v10 只有 `pages/SplashPage` 一条、给不出路由名,派发词也只强制它先读 WorksPage.ets 与 HomeTabComponent.ets,没把 pageMap 指为路由名真值源。
是否必要: 必要,路由名未注册即死路由,作品Tab点作品静默无跳转,且改动只动调用方、不动 pageMap(避免打断已用 'PptFilePage' 的深链)。
证据(每条带坐标):
  1. diff WorksComponent.ets@v12:`'PPTFilePage'`→`'PptFilePage'` + 注释订正 + 2 行警示(fixer-r1 v16 #23246 T+80:51)。
  2. blame WorksComponent.ets@v12 changed=True:被替换的 v11:583/586 两行,owner 均为 conv-worksfrag@v1。
  3. conv-worksfrag v1 时间线(#10812–#10879):读了 WorksFragment.kt / PPTFilePage.kt(#10875) / PptFilePage.ets@v5 / main_pages.json@v10,**无 SplashPage.ets**。
  4. main_pages.json@v10 全文只有 `"pages/SplashPage"` —— 路由名不在这里。
  5. SplashPage.ets@v52 blame :382 `name === 'PptFilePage'`,batch2-closer@v14 于 07-24T02:41 写下,早于 WorksComponent.ets@v1(T+18:27)。
  6. PptFilePage.ets@v5 头部溯源写的是 Android 类 `PPTFilePage`,通篇不含 pageMap 路由名 —— conv-worksfrag 读到的这份文件本身给不出正确名字。
  7. 单子 §3/§4(md@v1:52-55,61-63)指明 :586 的名字与 :584 注释互为矛盾来源,并要求「不要反过来改 pageMap」(§5:66),fixer 的改法与之一致。
无法确认的部分: 单子引的对照样例 `TemplatePreviewPage.ets:255` 用的是正确名字,但我在 TemplatePreviewPage.ets@v5(conv-worksfrag 当时读到的版本,读了 1-100/300-345/命中 37 行)的 148-264 行里没看到该 pushPathByName,无法确认生成时这个正确样例是否已存在、是否落在它读过的行段内;另外 fixer-r1 v26 #23492(T+81:19)用脚本又改过 WorksComponent.ets 一次(标题栏返回图标尺寸),账本未立版本,与本次路由名修复无关但内容未被完整记录。
置信: 高,修复动作、依据单据、真值锚点(SplashPage:382)与原作者的读取集缺口都各有工具坐标直接支撑,唯一空白是旁证样例的时点。
```