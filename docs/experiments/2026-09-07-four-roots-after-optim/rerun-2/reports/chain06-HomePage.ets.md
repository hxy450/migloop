```
文件: entry/src/main/ets/pages/HomePage.ets  修复方: visual-fixer 修复 round-1 / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v28-v29
修复改了什么: 只改注释——把第 461 行行尾与文件头第 11 行的「底栏深色背景 #202022」改成「白色 #FFFFFF（对位 activity_home.xml:21 ll_bottom_tab @color/white）」；真正的值改动在同一 agent 的 v1：color.json@v3 把 color_home_tab_bg 由 #ff202022 改成 #ffFFFFFF。
修复的依据: 单据 SYSTEMIC_home-tab-bar-dark-background.md@v2 —— P0、android_anchor = activity_home.xml:21 `ll_bottom_tab android:background="@color/white"`、安卓实测截图基线、§4 点名 HomePage.ets:461 与 color.json:180、§5 第 2 条明确要求「更正 461 行尾注释，避免误导后续轮次」；fixer 读该单(#24961)、读 sbs 对比图(#24967/#24968)后动手。
被改代码的来源: conv-home(agent-aconv-home-2cc89a9fca55ecb2) v1 在 HomePage.ets@v1 (#8865@L68) 写下这两行注释。依据是它收到的派发词原文「底部导航深色背景 $r('app.color.color_home_tab_bg')(#202022)」+ grep 到 resource-mapping.md:93 `color_home_tab_bg | #ff202022`(#8863)；它读了 activity_home.xml@v1(#8819) 并明确察觉冲突，却裁定「resource-mapping 权威」(#8864@L67)。v11 之后该行经多次 closer 重排、v23 有实录外修改，故 blame 显示「断点后归属未知」。
生成时为什么没做好: 转换错——派发环把「安卓 colors.xml 里存在名为 color_home_tab_bg 的深色」误当成「底栏实际背景」，conv-home 读全了源布局仍按派发词/资源映射表覆盖了 `@color/white` 这一真实证据。
是否必要: 可免 —— HomePage.ets 这两版是零行为影响的注释同步，真正修好 4 页的是 color.json@v3；但单据 §5.2 明确要求，且不改就留下与代码相反的误导注释。
证据(每条带坐标):
  1. 修复内容：diff HomePage.ets@v28 / @v29 仅注释行；diff color.json@v3 `#ff202022`→`#ffFFFFFF`(fixer-r1 v1 #25002@L54)。
  2. 修复依据：SYSTEMIC_home-tab-bar-dark-background.md@v2 §1 android_anchor activity_home.xml:21 @color/white、§3 实际 #202022、§5 建议改 color.json 并更正 461 行注释；fixer 读它于 #24961@L26。
  3. 原始写者：search(file=HomePage.ets, q=color_home_tab_bg) 首次出现 v1 ← conv-home v1 (#8865@L68, T+14:02)，第 10/117 行即这两行注释。
  4. 写者依据：conv-home 派发词全文含「底部导航深色背景 …(#202022)」(派发自 主会话·9b3105a2 @v85, #1072@L1925)；grep 命中 resource-mapping.md:93 `#ff202022`(#8863@L64)。
  5. 明知冲突仍写错：conv-home #8864@L67 原文「resolves the apparent conflict with the source layout's `@color/white` (the intended runtime design is the dark bar; the resource-mapping is authoritative)」，并把该裁决回写进 page_0009_HomeActivity.md@v3 第 93 行(#8873@L79)。
  6. 源布局确实读过：conv-home v1 读 …/res/layout/activity_home.xml@v1 (#8819@L17，无行段标=全文读)；同时 grep 到 app/res/values/colors.xml:18 `color_home_tab_bg=#202022`(#8826/#8830)。
  7. 「深色」不是从上游读来的：search(agent=主会话·9b3105a2, q=深色, v=85, since=70) 在窗口内仅命中它自己那条派发词，无任何读记录含此词；页面 spec page_0009_HomeActivity.md@v2 也无 202022(search file=…, q=202022 首次出现才在 v3)。
无法确认的部分: resource-mapping.md@v1(stage0-resources v25 #23155@L241, shell 落盘) 内容不可复原，只能由 grep 命中行确认第 93 行是「名→值」映射、无法确认它是否声称底栏用此色；主会话 v70 之前是否从别处取得「深色」说法未查(窗口外)；color.json@v2 里 `#ff202022` 由「实录外修改」引入，写者不明。
置信: 高 —— 修复方、被改行、原写者与其明示的裁决理由都有直接工具坐标且互相印证；仅链条最上游的 resource-mapping.md 原文缺失一环。
```