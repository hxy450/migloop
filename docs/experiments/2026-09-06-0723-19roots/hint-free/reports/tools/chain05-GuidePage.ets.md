```
文件: entry/src/main/ets/pages/GuidePage.ets  修复方: visual-fixer / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v13、v14、v15、v16
修复改了什么: 四处视觉对齐——(v13) 返回图标 `.width(24).height(24)` 改为 `.width(10+20*2).height(16+20*2)`；(v15/v14) 新增常量 `TRACK_HEIGHT=4`，把进度条两条 Row 的 `.height('100%')`/`.borderRadius(10)` 改成 `TRACK_HEIGHT`/`TRACK_HEIGHT/2`；(v16) 宿主 Swiper 补 `.padding({bottom: windowModel.windowBottomPadding})`。
修复的依据: 派发词点名 `SYSTEMIC_image-no-explicit-size` 并直指 `GuidePage.ets:172`「ArkUI padding 计入已声明尺寸，`.width(24).padding(20)` 内容区为负」(fixer-r1 派发词全文)；随即实测 `mipmap-xxhdpi/ic_guide_back.webp = 30x48px` @3x → 10x16dp(#23187)。轨道厚度来自 finding `ALIGN_PGuideActivity_component_mismatch_progress-bar.md@v1`(fixer-r1 v22 读) + `seekbar_horizontal_style.xml` 三层 `<size android:height="4dp"/>` 原文(#23456)。底部避让来自 `ALIGN_PGuideDifficulty1Fragment_layout_drift_bottom-buttons.md@v1`(#23556)。
被改代码的来源: 返回图标尺寸与双层 Row 轨道均出自生成方 conv-guide(agent-aconv-guide-979179ee8c5e2b3d) v1 写的 GuidePage.ets@v2 —— 其结题报告自述「返回图标 ic_guide_back(icon 24vp + padding 20vp + marginTop 40vp)」「SeekBar → 双层 Row，轨道 200vp × 20vp」；依据是它读到的 `res/layout/activity_guide.xml@v1` 全文 + 页面 spec `page_0002_GuideActivity.md@v1`(D-008「不得硬编码 bounds」)。v16 的底部 padding 是纯新增：conv-guide 结题称「WindowModel 未就绪，前景避让用源码 40vp + FWD-REF」，slice15-guide@v11 接线时只把 P-S15-007 解成了顶部 `guideTopInset()=max(40, windowTopPadding)`，底部从未有人写过。
生成时为什么没做好: 漏读——conv-guide 读全了 activity_guide.xml(看到 `:26-27 wrap_content`、`:43 progressDrawable=@drawable/seekbar_horizontal_style`)，却没有顺这两个指针去取真值(既没量 mipmap 固有像素，也没打开 seekbar 的 drawable)，于是 24vp 是凭空取的默认值、轨道厚度退化成 `'100%'` 撑满 20vp 占位框。
是否必要: 必要，图标内容区 24−40=−16(零可绘制区)、轨道粗约 5 倍、底部按钮压手势条，三处都有安卓侧真值可对。
证据(每条带坐标):
  1. `activity_guide.xml@v1`(conv-guide #7417 全文读)：iv_back 是 `wrap_content` + `padding 20dp`，SeekBar `layout_height=20dp` + `progressDrawable=@drawable/seekbar_horizontal_style` —— 源码从未给出 24dp，也未给出轨道厚度。
  2. conv-guide 结题报告自述写下「icon 24vp + padding 20vp」「双层 Row，轨道 200vp × 20vp」——24 与 20 是转换方自定的。
  3. `res/drawable/seekbar_horizontal_style.xml@v1` 的下游读者只有 stage0-resources v6/v10，conv-guide 不在其中 → 生成期确实没读。
  4. fixer-r1 #23456 拿到该 drawable 原文：三层 `<size android:height="4dp"/>` + `gravity=center_vertical` → 轨道 4dp 垂直居中于 20dp 占位框。
  5. fixer-r1 #23187 `sips` 实测 `ic_guide_back.webp = 30x48px`(mipmap-xxhdpi) → 10x16dp，v13 的 `10+20*2 / 16+20*2` 由此得出。
  6. `page_0002_GuideActivity.md@v1`(conv-guide 全文读)只给了组件映射表(SeekBar→Slider)与 D-008「confidence=medium，不得硬编码尺寸」，既未解析 progressDrawable，也未给任何 drawable 固有像素 —— spec 这一环没把真值送到 converter 手里。
  7. `GuidePage.ets@v11` diff(slice15-guide v2)：只把 `guideTopInset` 升级为 `max(GUIDE_BACK_MARGIN_TOP, windowTopPadding)`，全文无任何 bottom inset → v16 是纯新增。
无法确认的部分: 逐行 blame 在 v13/v14 处均报「归属未知(断点后)」(GuidePage.ets@v12 blame，148 行未知)，故无法用行级签名直接证明这些行是 conv-guide@v2 落笔、而非 v3–v10 四次 closer 修改所引入；上面的归属是靠 conv-guide 结题自述 + v11 diff 里它们作为未改动上下文出现来推的。finding `ALIGN_PGuideActivity_component_mismatch_progress-bar.md@v1` 内容「无法复原」(外部输入无快照)，其判据强度与具体处方不可见。fixer 读的是 `platform-res/` 下的同名 drawable，与生成期 `res/` 下那份是否逐字相同，账本未直接对账。
置信: 中高 —— 修复侧的真值取证(#23187、#23456)与生成侧的读取集(conv-guide v1 全部读记录)都是原文级证据，链条闭合；扣分只在被改行的行级归属被 blame 断点挡住，以及 finding 原文不可复原。
```