```
文件: entry/src/main/ets/pages/HomePage.ets  修复方: visual-fixer 修复 round-1 / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v28-v29
修复改了什么: 只订正两处注释——行尾 `.barBackgroundColor($r('app.color.color_home_tab_bg'))` 的「深色底栏 #202022」和文件头注释「底栏深色背景 #202022」，改成「白色底栏 #FFFFFF（activity_home.xml:21 ll_bottom_tab @color/white）」；真正生效的值改动在同一 agent 的 color.json@v3（#ff202022→#ffFFFFFF）。
修复的依据: spec/fix/round-1/ui/_systemic/SYSTEMIC_home-tab-bar-dark-background.md@v2（P0，fixer-r1 v1 全文读 #24961）——§1 android_anchor「activity_home.xml:21 ll_bottom_tab android:background="@color/white"」+ 安卓/鸿蒙 sbs 实测截图，§4 点名 HomePage.ets:461 与 color.json:180-181，§5.2 明确要求「更正 HomePage.ets:461 行尾注释，避免误导后续轮次」；派发词也把它列为 3 条 SYSTEMIC 之一（affects 4 单）。
被改代码的来源: conv-home(a2h-activity-converter, agent-aconv-home-2cc89a9fca55ecb2) v1 在 HomePage.ets@v1(T+14:02) 原样写下，此后 27 版逐字未动。它的依据是两条：(a) 派发它的 主会话·9b3105a2 @v85 派发词已写死「底部导航深色背景 $r('app.color.color_home_tab_bg')(#202022)」；(b) resource-mapping.md:93 的资源值表 `color_home_tab_bg | #ff202022`。它自己也读到了 activity_home.xml@v1 里 ll_bottom_tab 是 @color/white，在收尾输出里把这称为「底栏配色冲突裁决」并判 resource-mapping 权威。
生成时为什么没做好: 转换错——conv-home 把「资源字典里存在一个叫 tab_bg 的深色 token」当成了「底栏用这个 token」的判据，压过了它已经读到的布局真值属性；错误口径在上游派发词里已被预置（主会话 v15 #249 只读了 colors.xml 的色值定义，没核布局引用）。
是否必要: 必要（非功能性）——两行 diff 不改运行时，但旧注释正是那条错误裁决的载体，已被下游 4 个 agent 读到过，留着会继续误导后续轮次，且单 §5.2 明确要求订正。
证据(每条带坐标):
  1. diff(HomePage.ets@v28) / diff(@v29)：两版全部改动都是注释文本；实际值改动在 diff(color.json@v3) ← fixer-r1 v1。
  2. SYSTEMIC_home-tab-bar-dark-background.md@v2 §1/§2/§4/§5：anchor = activity_home.xml:21 @color/white，指名 HomePage.ets:461 + color.json:180-181，并要求订正注释。
  3. search(file=HomePage.ets, q=202022)：「深色底栏 #202022」首次出现于 v1 ← conv-home v1 (#8865)，v1→v27 逐字未变；v28/v29 各消去一行。
  4. conv-home v1 派发词全文（派发自 主会话·9b3105a2 @v85，action #1072）：「底部导航深色背景 $r('app.color.color_home_tab_bg')(#202022)，选中 #5B3CFF / 未选中 #D1D5EB」——错误结论在生成前就已下发。
  5. conv-home v1 读 activity_home.xml@v1 (#8819) 与 action(#8830)：它主动 grep「color_home_tab_bg 在哪被引用」，全仓 XML 唯一命中是 colors.xml:18 的定义本身（无任何布局引用），它看到了这个结果仍选深色。
  6. action(#8863/#8864) + conv-home 收尾输出：以 resource-mapping.md:93 的值表作「权威」推翻布局真值，并把该裁决写进 page_0009_HomeActivity.md@v3:93（search(file=page_0009_HomeActivity.md) 显示 v1/v2 的页面 spec 里根本没有 color_home_tab_bg——不是 spec 写错，是转换环节自造的裁决）。
  7. fixer-r1 v2/v3 写前读 HomePage.ets@v27 [440-479行] (#25004) 与 @v28 [1-30行] (#25008)，改动范围与所读一致。
无法确认的部分: HomePage.ets@v23 是「实录外修改」断点（07-24T20:07），blame(v28/v29, changed=True) 因此把被改行标为「归属未知(断点后)」——归到 conv-home v1 是靠 search 的逐版文本同一性推出的，不是逐行签名。vv-static-B v6 #28377(T+77:54) 对 HomePage.ets 的那次脚本调用方向不明，未展开核实是否写入；resource-mapping.md:93 本身只是资源名→值的字典行，它是否在别处宣称「底栏用深色」我未逐行核过全文。
置信: 高——修复动作、修复依据单、原写者身份与其当时的读取集（含那次证否性的 grep）和派发词全文都有直接坐标，唯一的弱点是断点导致的逐行签名缺失，但文本同一性证据足够替代。
```