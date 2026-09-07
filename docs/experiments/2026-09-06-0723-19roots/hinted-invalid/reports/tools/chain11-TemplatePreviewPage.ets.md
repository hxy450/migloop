```
文件: entry/src/main/ets/pages/TemplatePreviewPage.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v8(fixer-r1 v21，#23412 @T+81:11)
修复改了什么: 把 build() 里裸调的 `this.StepBar()` 包进一层 `Row().width('100%').padding({left/right: dp_15}).margin({top: dp_10})`，并加 4 行注释说明「白卡左右 15vp 必须由外层 padding 承担，不能写在白卡自身 margin 上，否则与 width('100%') 叠加溢出父宽 30vp、白卡铺满整屏盖住 #F7F7F7 底色」。仅此一处 hunk(+10/−2)。
修复的依据: 单 `ALIGN_PPPTTemplatePreviewPage_layout_drift_step-card.md`(读于 #23389)的实测——安卓白卡跨度 x 0.044→0.954、鸿蒙卡片轮廓消失、底色与卡片同取样 (255,255,255)；但 fixer 推翻了单里「缺 #F7F7F7 底色 token」的处方：它在 #23404 查到 `color_page_bg` 本就是 `#ffF7F7F7`，改判根因为 `width('100%')+横向 margin` 溢出，并在 #23393/#23404 用安卓 `page_ppt_template_preview.xml:29-33`(include_step match_parent + marginTop 10dp)与 `layout_ppt_step.xml:12-14`(shapeView5 match_parent + marginHorizontal 15dp)取 15/10 的真值。
被改代码的来源: 被替换的 2 行(v7:285 注释、v7:287 `this.StepBar()`)是 conv-preview@v1 写的(blame v8 changed)；真正的缺陷体 StepBar 白卡(v7:385-395 `.width('100%')` + `.margin({top:10,left:15,right:15})`)同样是 conv-preview@v1。它的依据是 a2h-execute 派发词「不硬编码 bounds、尺寸取自 source layout XML(D-008)」+ 它读的 `layout_ppt_step.xml@v1`(#8675 全文)，把 `match_parent + layout_marginHorizontal="15dp"` 一比一直译成了 `width('100%') + margin`。
生成时为什么没做好: 转换错——生成链的「安卓布局→ArkUI 属性」映射这一环把 Android `match_parent`(宽度已扣掉 margin)当成 ArkUI `width('100%')`(margin 外扩、会溢出父宽)，而 conv-preview 当时读的 `ui-migration-pitfalls.md`(#8702，52-181 行)里 P-04…P-27 没有这条反向语义可挡。
是否必要: 必要，但修不彻底——缺陷本身有像素实证，可 v8 保留了白卡自身的 `.margin({left:15,right:15,top:10})`，与新加的 Row padding 叠成横向 30vp、纵向 20vp，按 fixer 自己写的规则白卡仍会溢出 Row 内容区 30vp。
证据(每条带坐标):
  1. `TemplatePreviewPage.ets@v8` diff 只有一个 hunk：`this.StepBar()` → 外包 Row + padding dp_15 + margin top dp_10(action #23412 的 Edit 原文)。
  2. `blame @v8 changed=True`：替换 2 行、新增 10 行，2 行原作者均为 conv-preview@v1。
  3. `TemplatePreviewPage.ets@v7:385-395` + blame 同段 = conv-preview@v1：白卡 `.width('100%')`、`.margin({top:dp_10,left:dp_15,right:dp_15})`、`.borderRadius(dp_15)`、`.backgroundColor(white)`。
  4. 安卓侧原型 `layout_ppt_step.xml@v1:12-14`(conv-preview #8675 全文读)：shapeView5 `match_parent` + `layout_marginHorizontal=15dp` + 100dp + radius 15dp —— 逐值对应上一条，属直译。
  5. 单的处方被证伪:`#23404` 打印出 `color_page_bg = #ffF7F7F7`，即单里「缺底色 token」不成立；fixer 收尾输出也自述改判为「白卡 width('100%')+margin 溢出把底色盖住」。
  6. fixer 在写 v8 前已读过白卡全文(#23397，v7 340-400 行含那三行 margin)，仍未删该 margin；`file @v8 content 393-400` 显示 `.margin({top:dp_10,left:dp_15,right:dp_15})` 与 `.padding(15/15)` 原样保留 —— 与它自己写的注释「不能写在白卡自身的 margin 上」自相矛盾。
  7. 之后两次碰这个文件的脚本都不是补救:#23450 是给 ChoiceTemplatePage/TemplatePreviewPage 插 `onBackPressed`，#23492 是把标题栏返回图标 24x24 改 12x19，均未触及 StepBar。
  8. 单里第 ② 条(圆点中心 0.064/0.355/0.646/0.937 与文案列 0.157/0.385/0.615/0.844 错位)在 v8 里没有对应改动——diff 未进入 StepBar 内部的圆点 Row(v7:359-368)。
无法确认的部分: ① v8 之后没有复测/截图记录(派发词明令「不重编、不复测」)，白卡叠加 margin 后的实际渲染宽度只能按 ArkUI 语义推断，无实证；② `ui-migration-pitfalls.md` 我只看到 conv-preview 读到的 52-181 行且输出被截断(共 9365 字)，不能断言全文都没有这条 pitfall；③ #4399(batch2-closer 脚本、方向不明)对本文件做了什么未展开；④ 单 §6 里 fixer 追加的 `round-1 attempt` 原文未取。
置信: 中高——改了什么、依据什么、原作者是谁、直译自哪一行安卓 XML 都有逐行/逐动作坐标可对；扣分项是修复后的实际渲染无复测证据，「仍会溢出」是按 fixer 自述的 ArkUI 语义推出的，不是实测。
```