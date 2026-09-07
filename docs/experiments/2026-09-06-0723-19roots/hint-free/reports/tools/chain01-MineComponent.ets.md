```
文件: entry/src/main/ets/components/MineComponent.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2 / fixer-r1)  修复版本: v26-v30(另有 1 次未立版的脚本写入)
修复改了什么: 给 4 处只写了 .objectFit(ImageFit.Contain)、没写尺寸的 Image 补上显式 width/height(右箭头 12x12、宫格图标 48x48、VIP 字标 160.7x19 / 121x20)与 icon_mine_top_bg 的 .aspectRatio(1080/648);并把头区 Stack 钉死 .height(128) + .clip(false),不让装饰图撑高容器。
修复的依据: SYSTEMIC_image-no-explicit-size.md@v2(P0,severity/similarity 0.70/is_migration_bug:true)——ArkUI 的 Image 不写 width/height 时不取固有尺寸而是撑满父容器,并点名「固有尺寸(源未标注 size)」「交 icon-sizing 自愈」这类注释即高度可疑;加 4 张 ALIGN_PMineFragment_* 单(fixer-r1 v7 #23143);尺寸取值是它自己在 #23148 用 sips 逐张量安卓资源像素 ÷ 密度换算的。
被改代码的来源: 生成方 conv-minefrag(a2h-activity-converter,MineComponent.ets@v1 #8360),依据是 fragment_mine.xml + 迁移陷阱库 .claude/skills/android-ui-graph-query/references/ui-migration-pitfalls.md@v1(#8337/#8339);其收尾报告自陈「P-15(4 处 Image 显式 Contain)」,与本次被改的 4 处 Image 数量与位置吻合。v29/v30 的 Stack 定高是纯新增——前一版写者(slice17-home v19-v36,#17606-#17718)只做槽位接线,派发词里全是 P-S17-041..050 业务挂起项,不含视觉核对。
生成时为什么没做好: 参考知识库这一环写漏了——ui-migration-pitfalls.md@v1:169-173 的 P-15「Image 缩放默认值」只讲 ScaleType 差异、修复只给 .objectFit(ImageFit.Contain),整篇没有一条讲「不写 width/height 会撑满父容器」,转换器照它执行就必然把 wrap_content / adjustViewBounds / drawableTop 的尺寸信息丢掉。
是否必要: 必要,右箭头撑满行宽会把同 Row 内 layoutWeight(1) 的左标题压成 0 宽,导致 7 条设置项文案整体不渲染(SYSTEMIC 单:57),是 P0 可见故障。
证据(每条带坐标):
  1. sessions(file=MineComponent.ets):链类型 rework,生成方 conv-minefrag @T+18:25,修复方 fixer-r1 文件 v26-v30 @T+80:39。
  2. diff@v26/v27/v28 = 三处 Image 补 width/height;diff@v29 补 aspectRatio(1080/648);diff@v30 给 Stack 补 .height(128)+.clip(false)。
  3. blame@v26..v30(changed=True):每版只替换 1 行旧注释、其余 3-10 行全是新增;被替换的正是「固有尺寸(源未标注 size)」「固有尺寸交 icon-sizing 自愈」「P-15 需显式 Contain」这三种注释,与 SYSTEMIC 单:65-68 点名的识别特征逐字对上。
  4. ui-migration-pitfalls.md@v1:169-173(外部输入,72 个转换 agent 读过)——P-15 全文只有「ArkUI 默认 ObjectFit.Cover → 设 .objectFit(ImageFit.Contain)」,无尺寸条款。
  5. conv-minefrag v1 读取集(#8337 命中 29 行 / #8339 全文)+ 其收尾「Pitfalls: …P-15(4 处 Image 显式 Contain)」= 生成时的直接依据。
  6. fixer-r1 v10 #23161:先 grep 全仓已有 aspectRatio 先例(HomeDocComponent:189 的 488/68 等)再定 v29 的写法,不是拍脑袋。
  7. action(fixer-r1, #23238):同一轮还用 python heredoc 给 MineComponent.ets 的 icon_bg_open_vip 补了 .aspectRatio(990/240)——真实修改,但账本没立版本(sessions 末尾「方向不明」那条,实为写)。
无法确认的部分: ① 文件在 v14(2026-07-24T16:30 group2-closer,edit-miss)处有断点,v14-v18 内容未知,逐行归属自此「断点后未知」——被改那 4 行注释是 conv-minefrag v1 原文还是被 group1/group2-closer 或 slice17-home 改写过,无法逐行证明,「icon-sizing 自愈」这句措辞的作者尤其无法确认(v19 还有一次实录外修改)。② v29/v30 里 60+68=128vp 与 fragment_mine.xml:68 约束的引用,在 fixer-r1 v7-v11 的读取集中看不到它重读 fragment_mine.xml,数值应转引自 ALIGN_..._header-height 单,未直接取证。
置信: 中高——"改了什么/依据/为什么没做好"三段都有工具坐标直证(diff、SYSTEMIC 单原文、P-15 原文、conv-minefrag 读取记录与自陈),唯一软的一环是 v14 断点让被改行的作者只能靠"4 处 Image"数量与 P-15 注释措辞推定,而非逐行 blame。
```