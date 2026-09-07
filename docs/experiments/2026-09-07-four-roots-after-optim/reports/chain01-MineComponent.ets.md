```
文件: entry/src/main/ets/components/MineComponent.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2 / fixer-r1)  修复版本: v26–v30(fixer-r1 v7–v11,T+80:40–80:41)
修复改了什么: 给 3 处无尺寸 Image 补显式宽高——设置行右箭头 .width(12).height(12).flexShrink(0)(v26)、四宫格图标 .width(48).height(48)(v27)、VIP 字标按会员态 160.7x19 / 121x20(v28);再把头区装饰图从「撑高者」改回背景层:icon_mine_top_bg 加 .aspectRatio(1080/648)、外层 Stack 钉死 .height(128).clip(false)(v29–v30),并把原来写错的推断性注释改写成实测像素依据。
修复的依据: 4 张 round-1 finding 单,fixer-r1 v7 一次性读入(action #25104):ALIGN_PMineFragment_layout_bug_setting-row-arrow / _drift_service-grid-icons / _drift_vip-wordmark / _drift_header-height。单里给了安卓实测基线 dump 坐标与资源像素(36x36px=12dp、144x144px=48dp、363x60px=121x20dp、1080x648px),并直接点名源码行 MineComponent.ets:880-882 / 521-523 / 461-465 / 389-437;§5 的处方(补 .width/.height、Stack 钉 128vp + clip(false))与落盘的 v26–v30 逐条对应。
被改代码的来源: conv-minefrag(agent-aconv-minefrag-0c34d8c25c9daec8) v1 在 MineComponent.ets@v1(#9701,T+18:26)写的。依据有二:(1) 它读了 .claude/skills/android-ui-graph-query/references/ui-migration-pitfalls.md@v1 的 P-15(#9677),照 P-15 只写 .objectFit(ImageFit.Contain) 并在注释里标「P-15 需显式 Contain」;(2) 派发词要求「先 Read MinePage.ets」,它读到 MinePage.ets@v14(#9657)里 conv-mine v1 发明的「未标注尺寸的图标留固有尺寸交 icon-sizing 自愈」约定并原样搬进本文件。v29/v30 的 aspectRatio 与 Stack .height(128) 属纯新增(sessions:纯新增 19 行),v25 写者 slice17-home v36 那一版只动了别处、未触及头区几何。
生成时为什么没做好: spec 写错/不全——pitfalls P-15(@v1 第169-173行)只写了「ArkUI 默认 ObjectFit.Cover → 补 Contain」,完全没说 ArkUI 的 Image 不写 width/height 时不取固有尺寸而是撑满父容器,转换器照规则执行仍会漏尺寸;错误假设又经 MinePage.ets 在页间复制传播。
是否必要: 必要,箭头撑满导致同 Row 内 layoutWeight(1) 的 7 条标题被压成 0 宽、dump 里根本没有 Text 节点(P0 整页信息缺失),头区多撑高使「续订管理/关于我们」掉出首屏。
证据(每条带坐标):
  1. ui-migration-pitfalls.md@v1:169-173(外部输入,181 行)P-15 全文只到「修复: 设置 .objectFit(ImageFit.Contain)」,无尺寸要求;conv-minefrag v1 读它 #9677(命中 29 行)。
  2. conv-minefrag v1 收尾自述「P-15(4 处 Image 显式 Contain)」——它认为按规则已做完,正是漏尺寸的那 4 处。
  3. search(file=MineComponent.ets, q=P-15 / icon-sizing):两条被改注释「固有尺寸(源未标注 size),P-15 需显式 Contain」「固有尺寸交 icon-sizing 自愈」首次出现即 v1 ← conv-minefrag v1,v1→v25 逐版原文一字未改。
  4. search(file=MinePage.ets@v14, q=icon-sizing 自愈):首次出现 MinePage.ets@v1 ← conv-mine v1(#9596,T+17:07),conv-minefrag 在 #9657 读到该文件第 12/189/494 行 —— 约定是从上一页复制来的,不是本页独创。
  5. finding 单原文(#25104)明写「源注释『源未设 bar_rightDrawableSize → 固有尺寸』是错误推断:ArkUI 无『固有尺寸』缺省行为」「『固有尺寸交 icon-sizing 自愈』的假设没有落地」——修复方定的正是这条注释所代表的推断。
  6. diff(MineComponent.ets, v=26/27/28/29/30):五版改动与单 §5 逐条对齐;v30 的 .height(128) 注释复述了 fragment_mine.xml:68 的 constraintTop_toBottomOf="@id/iv_user_icon" 约束链。
  7. fixer-r1 收尾自述:该 SYSTEMIC 全仓 30 处 / 16 文件,密度逐张 sips 实测(并非全 @3x),MineFragment 头区被判为「元素撑大容器」的变体 —— 与 v29/v30 的写法一致。
无法确认的部分: (a) file 原子在 v14 有 edit-miss 断点,blame(changed=True) 对 v26–v29 被替换的 4 行一律报「归属未知(断点后)」,conv-minefrag 的作者身份是靠 search 的逐版原文同一性推定,不是逐行签名判定;(b) v14–v18 内容未知、v19 为「实录外修改」,这段里是否有人碰过这几行无法确认;(c) 四张单都要求修改前必须 Read sbs 拼图,但 fixer-r1 v6–v11 窗口内没有读该 jpeg 的记录,是否看过图无法确认;(d) conv-minefrag 只在 #9676 用 ls/grep 确认过资源存在,有没有量过 drawable 像素尺寸,账本里看不出。
置信: 高 —— 修复内容、修复依据(finding 单原文)、被改行的原始写者与其两条依据(P-15 原文 + MinePage 约定的读记录)都有直接工具坐标,唯一的推定环节(逐行归属)有 25 个版本的原文同一性兜底。
```