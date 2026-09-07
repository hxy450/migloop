```
文件: entry/src/main/resources/base/element/color.json  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v3
修复改了什么: 全文只改一行 —— 资源 token `color_home_tab_bg` 的值由 `#ff202022`(深灰)改为 `#ffFFFFFF`,即把 4 个 Tab 页共用的底栏背景改成纯白。
修复的依据: 单 `spec/fix/round-1/ui/_systemic/SYSTEMIC_home-tab-bar-dark-background.md@v2`(fixer-r1 v1 #22994 全文读):§1 android_anchor 写明安卓 `activity_home.xml:21 ll_bottom_tab android:background="@color/white"`,§4 指到 `color.json:180-181`,§5 处方就是「改这一个值即同时修 4 页」;P0 / is_migration_bug=true / affects 4 张 ALIGN 单。主会话·ff019d8a@v74 的派发词表格也复述了同一条处方。
被改代码的来源: 无实录内写者 —— color.json v1 是外部输入(T+13:32,内容未知)、v2 是「实录外修改」(T+15:55),blame(v3,changed=True) 对第 181 行给「归属未知(断点后)」。但依据可确定:Stage 0 的 stage0-resources(派发自主会话·9b3105a2@v77,要求「colors.xml 107 个色值全部转 color.json」)在收尾输出里认领了 color.json(99 色);该值与安卓 `app/src/main/res/values/colors.xml:18 <color name="color_home_tab_bg">#202022</color>` 1:1 对应 —— 是机械照搬 token,不是设计判断。
生成时为什么没做好: 断在页面转换这一环 —— conv-home v1 读全了 `activity_home.xml`,明知 `ll_bottom_tab` 是 `@color/white`,却按主会话 9b3105a2@v82 派发词与 resource-mapping 的机械 token 表把底栏裁决成深色(转换错:读全了仍写错,且上游派发词已把「深色」当成前提)。
是否必要: 必要 —— 安卓实测基线与布局锚点双证底栏为白,4 页逐页复现的同一行根因;且该 token 全仓只有底栏一个消费者,改值不外溢。
证据(每条带坐标):
  1. `color.json@v3` diff(fixer-r1 v1,#23045 T+80:31):唯一改动 `color_home_tab_bg` `#ff202022 → #ffFFFFFF`;fixer 收尾自述「一行改动 + 两处误导注释订正,没碰 Tab 文案色」。
  2. `SYSTEMIC_home-tab-bar-dark-background.md@v2` L41/L44-45/L54/L57:安卓 `ll_bottom_tab` = `@color/white`,鸿蒙实测 `#202022`,处方即改 color.json 该值。
  3. blame(color.json@v3, changed=True):被替换的 v2:181 归属「未知(断点后)」;file 脊柱显示 v1=外部输入、v2=实录外修改,生成侧无记录写者。
  4. conv-home v1 读 `app/.../colors.xml@v1`(#7592)看见 `18: <color name="color_home_tab_bg">#202022</color>` —— 该值来自安卓 token 原样搬运;stage0-resources 收尾输出认领 color.json(99 色),与 #21366 实测 99 条一致。
  5. `spec/baseline/plans/resource-mapping.md@v1`(stage0-resources v25 写,#21418)第 93 行 `| color_home_tab_bg | #ff202022 | app/.../colors.xml |`(原文见 conv-home #7622 输出)——这是纯 token→$r() 映射表,并未主张「底栏用它」。
  6. 主会话·9b3105a2 v78 于 T+13:49 读该 mapping,随后 @v82 派发 conv-home 的指令里直接写死「底部导航深色背景 `$r('app.color.color_home_tab_bg')`(#202022)」。
  7. conv-home v1 收尾输出「底栏配色冲突裁决」:承认源布局是 `@color/white`,仍以「浅色文字白底不可见 + resource-mapping 锚定深色 + 与你的指令一致」为由采用深色 token —— 知情覆盖了实证。
  8. fixer-r1 v1 grep(#23001)→ 绑定读(#23024)显示该 token 全仓仅两处消费:`color.json@v2:180` 与 `HomePage.ets@v28:11,461`,改值影响面封闭。
无法确认的部分: color.json 第 181 行的直接落盘动作没有实录(实录外修改 / 断点后),归到 stage0-resources 是靠其收尾输出与值 1:1 对应的间接推断;`app/.../colors.xml` 与 `resource-mapping.md` 全文均「无法复原」,无法核 `color_home_tab_bg` 在安卓侧是否另有(深色主题等)真实消费者 —— 若有,把 token 值改白而非改 `HomePage.ets:461` 的引用会埋隐患;`HomePage.ets:461` 那一行当前的直接写者同样是断点后未知(仅能溯到 conv-home 的裁决)。
置信: 高 —— 修复动作、修复依据、token 值的安卓出处、以及「明知 @color/white 仍选深色」的裁决原话四条都有直接坐标,唯一薄弱处是落盘动作本身没进实录。
```