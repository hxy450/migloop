```
文件: entry/src/main/ets/components/MineComponent.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2 / fixer-r1)  修复版本: v26–v30(fixer-r1 v7–v11,T+80:40)
修复改了什么: 给四处未写尺寸的 Image 补显式尺寸——右箭头 .width(12).height(12).flexShrink(0)(v26)、四宫格图标 48x48(v27)、VIP 字标按两态 160.7x19 / 121x20(v28)、头图 .aspectRatio(1080/648)(v29);并把头区 Stack 钉死 .height(128).clip(false)(v30)。
修复的依据: spec/fix/round-1 的 4 张 MineFragment ALIGN 单(#25104@L119,来源为 Android Phase 2 实测基线截图 + dump 坐标),单里直接写明「ArkUI 的 Image 缺省不取固有尺寸、会撑满父容器」;所有像素数由 sips 实测资源文件得到(#25109@L122:36x36 / 144x144 / 482x57 / 363x60 / 1080x648);派发词把 SYSTEMIC_image-no-explicit-size 列为 P0(fixer-r1 派发指令)。
被改代码的来源: 生成方 conv-minefrag v1 写 MineComponent.ets@v1(#9701@L69)时就这么写的,四处注释各自署明依据——「P-15 需显式 Contain」「固有尺寸(源未标注 size)」「固有尺寸交 icon-sizing 自愈」;其中「icon-sizing 自愈」这套说法是它读兄弟产物 MinePage.ets@v14(#9657@L26,首见于 conv-mine v1 写的 MinePage.ets@v1:12/178/482)照抄来的。v30 的 Stack .height(128) 是纯新增,v29 的写者(同为 fixer-r1)未写。
生成时为什么没做好: spec 缺项——ui-migration-pitfalls.md@v1:169-173 的 P-15 只讲 objectFit 缺省(Cover vs FIT_CENTER),对「ArkUI Image 不写 width/height 时不取固有尺寸」只字未提,转换方照 P-15 补了 Contain 就以为收工,又把上一页杜撰的「交 icon-sizing 自愈」当成兜底。
是否必要: 必要,右箭头撑满行宽把同 Row 内 layoutWeight(1) 的 7 条标题压成 0 宽、整页文案不渲染,是 P0 级信息缺失。
证据(每条带坐标):
  1. 修复范围与作者:MineComponent.ets@v26–v30 全部由 fixer-r1 v7–v11 写(file 脊柱,#25116/25118/25120/25134/25136@L130-146)。
  2. 被改的原始行来自生成第一版:search(file=MineComponent.ets, q="P-15" / "icon-sizing") 均显示首次出现于 v1 ← conv-minefrag v1,四条注释逐版原样传到 v25。
  3. spec 缺项:ui-migration-pitfalls.md@v1 第 169-173 行的 P-15 全文只有「设置 .objectFit(ImageFit.Contain)」,无尺寸缺省行为;conv-minefrag 确实读了它(#9677@L46 / #9679@L49)。
  4. 「icon-sizing 自愈」无上游依据:search(agent=conv-mine, q="icon-sizing", v=1) 在其派发词/读取/收件里零命中,只命中它自己那次写(#9596@L82)——是写者自造的兜底假设,不是规范。
  5. 修复方的判据是实测而非推断:ALIGN_PMineFragment_layout_bug_setting-row-arrow.md §3/§4 点名「源注释『源未设 bar_rightDrawableSize → 固有尺寸』是错误推断」,并给出安卓 dump 坐标(免费次数[105,1114] 等 7 条)与鸿蒙右值被顶到 x=113 的对照(#25104@L119)。
  6. 尺寸取值可核:#25109@L122 的 sips 输出与 v26–v29 写入的 12/48/160.7x19/121x20/1080:648 逐一对得上。
  7. 归属断链的原因:blame(v26..v29, changed=True) 对被替换的那 4 行均报「归属未知(断点后) 1 行」,因 file 原子记录了 v14 处 edit-miss 断点(2026-07-24T16:30:26);作者是靠 search(file=) 的逐版首现回溯定的,不是靠 blame。
无法确认的部分: (a) v29/v30 的 Stack 高度推算(fragment_mine.xml:68 约束链、60+68=128vp)在 fixer-r1 v6–v11 的读记录里看不到它读 fragment_mine.xml,该行号很可能来自 header-height 单正文,但那份 finding 在 #25104 输出中被截断,未展开核实;(b) 同窗口也没有读 sbs 拼图 jpeg 的记录,而单里要求「修复代码前必须 Read sbs 拼图」——不能断定它没看,只能说账本里没有这条读;(c) v14–v18 内容未知、v19 是实录外修改,这段期间这四处有无被人碰过无法确认。
置信: 高。修复方、修复版本、被改行的原始写者与其自述依据、spec 缺项、以及修复取值的实测来源,五个环节各有独立坐标且互相印证;只有头区高度那一条的推导来源留了缺口。
```