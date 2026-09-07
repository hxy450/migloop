```
文件: entry/src/main/ets/pages/TemplatePreviewPage.ets  修复方: visual-fixer / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v8(fixer-r1 v21, #23412, T+81:11)
修复改了什么: 把 build() 里裸调的 `this.StepBar()` 包进一层 `Row().width('100%').padding({left/right: dp_15}).margin({top: dp_10})`,并加 4 行注释说明「白卡的左右 15vp 应由外层 padding 承担、不能写在白卡自己的 margin 上」;替换 v7 的 2 行、新增 10 行,全文件只有这一处 hunk。
修复的依据: round-1 单 `ALIGN_PPPTTemplatePreviewPage_layout_drift_step-card` §3 的像素实测(卡片轮廓不可见、卡片与页面底色同点取样均为 (255,255,255))(#23389);修复方自己复核了安卓真值 `layout_ppt_step.xml` 白卡 = match_parent + marginHorizontal 15dp(#23393/#23404),并用 python 读 color.json 确认 `color_page_bg=#ffF7F7F7` token 本就正确,据此**推翻了单里「缺底色 token / 缺白卡容器」的处方**,改判为「白卡 width('100%')+横向 margin 溢出父宽 30vp 把底色盖住」(fixer-r1 v21 收尾输出)。
被改代码的来源: conv-preview(a2h-activity-converter, agent-aconv-preview-00959aaf5f537b1b)在 v1(#8704, T+14:29)写的;它全文读了 `page_ppt_template_preview.xml`(#8673)与 `layout_ppt_step.xml`(#8675),把安卓两层(外层 ConstraintLayout match_parent + 内层 shapeView5 match_parent/marginHorizontal 15dp)压成一个 Column,逐属性直译为 `.width('100%') + .margin({left/right: dp_15})`(v7:385-391,blame 全归 conv-preview@v1)。
生成时为什么没做好: 转换错——a2h-execute 转换器这一环把 Android「match_parent + margin(父内收缩)」当作与 ArkUI「width('100%') + margin(父外溢出)」等价直译;放大它的是参考文档缺口(ui-migration-pitfalls.md@v1 读到的 52-181 行只有 P-12「默认 padding/margin 差异」,没有这条规则,#8702)+ 生成期无几何 oracle(派发词「⚠️ 禁止编译」、view.xml 为源码合成 bounds 为空)。
是否必要: 必要但不完整——缺陷真实且有像素取证,但 v8 只加了外层 padding,白卡自身的 `.width('100%')` 与 `.margin({top:dp_10,left:dp_15,right:dp_15})` 原样留在 v8:393-399,按修复方自己写下的 ArkUI 规则仍会溢出(左内缩变 30vp、右侧贴边),顶部边距也从安卓的 10dp 变成 Row 10 + 卡片 10 = 20vp。
证据(每条带坐标):
  1. diff TemplatePreviewPage.ets@v8:仅一处 hunk,`this.StepBar()` → Row 包裹 + padding 15;blame(v8, changed) = 替换 v7 的 2 行(285/287)、新增 10 行,被替换行 owner 全是 conv-preview@v1。
  2. blame TemplatePreviewPage.ets@v7:354-396 → StepBar builder 整段 conv-preview@v1;白卡属性 v7:385(`.width('100%')`)、387-391(`.margin` top10/left15/right15)。
  3. conv-preview v1 读 `layout_ppt_step.xml`(#8675,189/189 行全文):shapeView5 `layout_width=match_parent` + `layout_marginHorizontal=15dp` + `shape_radius=15dp` + `solidColor=white` —— 15vp 这个数值是对的,错的是承载它的机制。
  4. fixer-r1 v21 #23404:color.json `color_page_bg=#ffF7F7F7`,且 v7:303 页面根已 `.backgroundColor($r('app.color.color_page_bg'))` —— 证明单里「缺底色 token」的判断不成立,修复方改判正确。
  5. fixer-r1 v21 收尾输出「顺手修的旁观缺陷」:`width('100%') + 横向 margin` 溢出是修复期全仓扫描才发现的规律(同批修了 PayAgreementDialog / MemberCenterPage 等 4 处),说明生成期无人手里有这条规则。
  6. file(TemplatePreviewPage.ets@v8, content, 386-407):v8:393 `.width('100%')`、395-399 `.margin({top:dp_10,left:dp_15,right:dp_15})` 仍在 —— 与 v8 新加注释「不能写在白卡自身的 margin 上」自相矛盾;v7 704 行 → v8 712 行(+8)也印证只改了调用点。
  7. conv-preview 派发词(agent v1)「⚠️ 禁止编译」+ v8 收尾报告「view.xml 为源码合成(bounds 空)→ 尺寸全部取自 source layout XML」:生成链路没有任何渲染/几何校验能拦下这类溢出。
  8. 单 §4 第 3 条(圆点行 SpaceBetween 应改四等分,#23389)在 v8 未被处理,圆点/文案列中心错位(0.064–0.937 vs 0.155–0.845)这一半缺陷仍在。
无法确认的部分: ①`ui-migration-pitfalls.md@v1` 第 1-51 行没展开(conv-preview 另一次读 #8696 标「范围未知」),故只能确认 52-181 行无此条,不能断言全文都没有;②修复后未编译未复测(派发词「不重编、不复测」),v8 的实际渲染效果账本里没有像素证据,「仍会溢出」是按修复方自陈的 ArkUI 规则推出的;③`batch2-closer v1 #4399`(T+14:35)碰过本文件、方向不明未展开,但 blame@v7 只有 conv-preview/slice18 两位 owner,其影响未留存。
置信: 高 —— 被改行的归属、安卓真值、修复方的判据链都有 diff/blame/action 原文逐条对上;唯一推断成分是 v8 残留 margin 的运行时后果(见「无法确认」②)。
```