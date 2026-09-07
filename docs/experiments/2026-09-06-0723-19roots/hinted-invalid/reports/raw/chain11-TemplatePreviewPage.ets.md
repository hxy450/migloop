```
文件: entry/src/main/ets/pages/TemplatePreviewPage.ets  修复方: visual-fixer「fixer-r1」(agent a68daf720e780b4c2，主会话 ff019d8a-5172-4cdd-8ce3-77a21682c1b6)  修改时间: 2026-07-26T21:14:28.375Z（同一分钟内的配套 Bash 补丁 21:14:03.860Z）

修复改了什么: 把步骤条白卡的左右 15vp 从卡片自身的 `.margin` 下沉到调用点新加的一层 `Row().padding({left/right:15vp}).margin({top:10vp})`；同时把圆点行从「圆点-连线-圆点-…」改成 4 个 `layoutWeight(1)` 的 `StepCell`（单元内左右各垫一段 Divider，首末段透明），使圆点逐列与下方四等分标签行对齐。

修复的依据: round-1 视觉核验 finding `spec/fix/round-1/ui/ALIGN_PPPTTemplatePreviewPage_layout_drift_step-card.md`（P1 / ALIGNMENT_DIFF / source=arkts-visual-verify），带像素取样：安卓卡片跨度 x 0.044→0.954、圆点中心 0.157/0.385/0.615/0.844；鸿蒙实测页面底色与卡片同为 (255,255,255)、圆点中心 0.064/0.355/0.646/0.937，首尾各偏 9% 屏宽（fixer 转录 L401→L402，21:12:32）。注意 fixer 没有照抄 finding 的 root_cause_hint（hint 说「用了 justifyContent(SpaceBetween)、缺白卡背景」，实际代码两者都不是）——它自己读源码后定位为 `.width('100%')` 与 `.margin({left/right})` 叠加溢出父宽 30vp，白卡被撑满整屏所以轮廓消失（L405–L414，21:12:51–21:13:26）。

被改代码的来源: 生成轮的 `conv-preview`(a2h-activity-converter，agent-aconv-preview-00959aaf5f537b1b) 在 2026-07-24T02:32:18.631Z 首写；依据是它 02:26:54 Read 的 `app/src/main/res/layout/layout_ppt_step.xml`——它照搬了 `shapeView5` 的 `layout_marginHorizontal=15dp` / `height=100dp` / `shape_radius=15dp` / 白底，但把「圆点 Start/End 约束到 tv_step1..4」这组约束改写成了顺序 Row。后来 `slice18-pptgen` 在 07-24T19:40:13.066Z 整文件 Write 覆盖时把这段 StepBar/StepCircle/StepLine 逐字保留，未复核。

生成时为什么没做好: 卡在 converter 这一环——ConstraintLayout 的「圆点居中约束到同名标签」被降维成线性 Row，且 Android 的 `layout_marginHorizontal` 被直译成 ArkUI 的 `.margin` 挂在 `.width('100%')` 节点上（ArkUI 中 margin 在 100% 宽之外累加 → 溢出），而下游 slice18 只按文案 grep 了该布局、没再看几何，漏斗里没有任何一环回看渲染结果。

是否必要: 必要 —— 白卡不可见 + 圆点与标签错位 9% 屏宽是可见回归，且同一个 `layout_ppt_step` include 在 HomeTabComponent 里已有正确写法，改后两处才一致。

证据（每条带位置）:
  1. 修复动作: ff019d8a-.../subagents/agent-a68daf720e780b4c2.jsonl:420, 2026-07-26T21:14:28.375Z — Edit 在 `if (this.showStepBar)` 内包 Row + padding 15vp + margin top 10vp；注释写明「不能写在白卡自身 margin 上，否则与 width('100%') 叠加溢出父宽 30vp」。
  2. 配套结构改写: 同文件:416, 21:14:03.860Z — Bash/python 补丁把圆点行换成 `StepCell(0..3)`，并从 StepBar 根节点删掉 `.margin({top,left,right})`；新建的 StepCell 注释自陈「结构对齐 HomeTabComponent.stepCell」。
  3. 判据来源: 同文件:401→402, 21:12:32.663Z — 读取 step-card finding §2/§3（安卓 0.157/0.385/0.615/0.844 vs 鸿蒙 0.064/0.355/0.646/0.937；两侧取样均 (255,255,255)）；索引行见同文件:19 第 39 行「P1 | ALIGNMENT_DIFF | PPTTemplatePreviewPage | 步骤条白卡容器缺失+圆点与文案错位」。
  4. 被改代码首写: 9b3105a2-.../subagents/agent-aconv-preview-00959aaf5f537b1b.jsonl:57, 2026-07-24T02:32:18.631Z — Write 内容含与被改前完全一致的 StepBar（Row 里 StepCircle/StepLine 交替 + 根节点 width('100%') + margin left/right 15vp + backgroundColor white + borderRadius 15）。
  5. 首写者的原始依据: 同文件:19/20, 2026-07-24T02:26:54.073Z — Read `layout_ppt_step.xml` 全文，结果里明确有 `shapeView5 … layout_marginHorizontal="15dp" … shape_radius="15dp" shape_solidColor="@color/white"` 和 `shape_step1 … layout_constraintStart_toStartOf="@+id/tv_step1" / End_toEndOf="@+id/tv_step1"`（即圆点应以标签列为中心）。真值在上下文里，被转换环节丢掉。
  6. 覆盖者未复核: agent-aslice18-pptgen-24177a0006115183.jsonl:166, 2026-07-24T19:40:13.066Z 整文件 Write 时 StepBar 段与 4 中逐字相同；该 agent 对该布局的唯一一次读取是 :131, 19:29:41 的 `grep "tv_step\|android:text" layout_ppt_step.xml`（只取文案，未取几何）。
  7. 同源 include 的正确旁证: agent-aconv-hometab-afeccbf00da93597.jsonl:57, 2026-07-24T03:16:15.614Z — 另一个 converter 对同一个 `layout_ppt_step` 写成 4 个 `stepCell` 四等分；fixer 在 21:06:51/21:07:06（:357/:360）读了它并作为参照。

无法确认的部分: (a) finding 里的像素取样数值与截图我只看到 fixer 转录中的引用，未见 finding 文件本体/frontmatter，也无法独立复算；(b) 修改后是否重新截图复验通过，本次追踪未确认；(c) 为什么两个 converter（conv-preview / conv-hometab）对同一 include 各写各的——转录里没有共享组件或交接约定的记录，只能观察到结果分叉。

置信: 高 —— 修复动作、判据文件、被改代码的首写者/时间戳与其当时读到的 Android XML 原文四者在转录里逐条对得上，且被改前代码与首写内容逐字一致，中间无第三方改动。
```