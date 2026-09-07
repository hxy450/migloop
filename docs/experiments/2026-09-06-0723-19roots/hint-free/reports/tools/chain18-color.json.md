```
文件: entry/src/main/resources/base/element/color.json  修复方: visual-fixer 修复 round-1 / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v3
修复改了什么: 把 color_home_tab_bg 的值从 #ff202022 改成 #ffFFFFFF（v2 第 181 行,一行替换),连带订正 HomePage.ets 两处"深色底栏"误导注释;一处改动收敛 4 个 Tab 页的底栏配色单。
修复的依据: spec/fix/round-1/ui/_systemic/SYSTEMIC_home-tab-bar-dark-background.md@v2(P0, is_migration_bug: true),其安卓锚点为 activity_home.xml:21 `ll_bottom_tab android:background="@color/white"`(@v2:41/45),期望白底、实测鸿蒙 #202022(@v2:48);派发词也点名"color.json:180 由 #ff202022 改白"(fixer-r1 v1 派发指令)。
被改代码的来源: 无记录写者 —— color.json@v1 是外部输入(T+13:32)、@v2 是实录外修改(T+15:55,unknown),blame(v3, changed) 对该行给"归属未知(断点后)"。值本身与安卓资源逐值一致(app/src/main/res/values/colors.xml:18 `<color name="color_home_tab_bg">#202022</color>`,conv-home v1 #7592 看见),属资源表 1:1 机械搬运,不是拍脑袋写的。真正把它接到底栏上的是 conv-home v1(写 HomePage.ets@v2, #7623)。
生成时为什么没做好: 转换错(读全了仍写错)—— conv-home v1 已读 activity_home.xml@v1(#7586) 与 colors.xml,却在收尾"底栏配色冲突裁决"里明写"源布局 ll_bottom_tab 是 @color/white,但…采用 color_home_tab_bg",而它的上游派发词(主会话·9b3105a2@v82,#834)本就预先写死"底部导航深色背景 color_home_tab_bg(#202022)";所以坏在 slice 派发词把配色结论前置、converter 又用它压过了布局锚点这一环,color.json 只是被牵连的模板文件(链根 kind=template)。
是否必要: 必要 —— 安卓基线锚点确为白底,且 grep(#23024) 证明该 token 全仓只有 HomePage.ets:461 一个消费者,改值零外溢;唯一副作用是该 token 值自此与安卓 colors.xml:18 不再同值(更彻底的改法是把 :461 改指 white)。
证据(每条带坐标):
  1. color.json@v3 diff:`color_home_tab_bg` `#ff202022`→`#ffFFFFFF`,写者 fixer-r1 v1(#23045 T+80:31);blame(color.json@v3, changed) 只替换 v2 的第 181 行。
  2. 修因单 SYSTEMIC_home-tab-bar-dark-background.md@v2:41「android_anchor: activity_home.xml:21 ll_bottom_tab android:background="@color/white"」、:54「color.json:180-181 应为白」;fixer-r1 v1 读了它(#22994)。
  3. conv-home v1 派发词(主会话·9b3105a2@v82,#834)已含「底部导航深色背景 $r('app.color.color_home_tab_bg')(#202022)」——错误结论在派发时已成立。
  4. conv-home v1 读了 activity_home.xml@v1(#7586)和 app/colors.xml@v1(#7592,看见 18 行 `#202022`),收尾自述"源布局是 @color/white…采用 color_home_tab_bg,与你的指令一致"——漏读不成立,是有意覆盖。
  5. color.json 写者脊柱:v1 外部输入 / v2 实录外修改,生成侧无记录写者;stage0-resources #21366(T+13:43)只是核对"color.json 99 条 OK",是资源搬运的产物。
  6. fixer-r1 #23024 grep 结果:该 token 仅 color.json:180 定义 + HomePage.ets:11(注释)/:461(唯一使用点)。
  7. HomePage.ets@v28 第 461 行 blame 为「归属未知(断点后)」,文件在 07-24T20:07 有 outband-change 断点(slice17-home 脚本写 #17764),故行级签名断在这里。
无法确认的部分: (a) 派发词里 #202022 这个结论的上游出处 —— 主会话 v82 窗口只有派发动作、无读记录,页面 spec page_0009_HomeActivity.md@v2 前 60 行也没提配色;conv-home 声称的"resource-mapping.md 也锚定深色"在它的读取集里没有对应读记录,其自查 grep(#7622)还失败了,该引用无法核实。(b) color.json@v1/@v2 由谁、用什么脚本落盘 —— 账本记为外部输入 + 实录外修改,只能从值一致性推断是 colors.xml 的机械转换。(c) HomePage.ets:461 的行级作者被断点截断,只能靠 conv-home v1 的产出与收尾报告认定。
置信: 中 —— 从修复版 diff 到修因单、到 converter 的"明知 @color/white 仍覆盖"的自述,每步都有坐标且互相咬合;但上游两处(#202022 指令的依据、color.json 的实际写者)在账本里是断的,只能推断。
```