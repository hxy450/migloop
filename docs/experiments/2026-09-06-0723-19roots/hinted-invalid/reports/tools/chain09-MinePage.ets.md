```
文件: entry/src/main/ets/pages/MinePage.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v40
修复改了什么: 给「我的」头区那层 Stack 补了 `.height(128)` + `.clip(false)`(带两行注释),纯新增 4 行、没替换任何旧行;同一版里还有一次脚本写(#23177,黑盒未立版)把四宫格图标补成 48x48、右箭头 12x12。
修复的依据: 单 `spec/fix/round-1/ui/ALIGN_PMineFragment_layout_drift_header-height.md@v1`(fixer-r1 v7 #23143 读),被派发词归到 P0 `SYSTEMIC_image-no-explicit-size`;fixer 自述根因是「Stack 高度=最大子组件高度,装饰头图成了撑高者」,128 = 安卓 `iv_user_icon` marginTop 60 + 68dp,对位 `iv_vip_enter` 的 `constraintTop_toBottomOf="@id/iv_user_icon"`。
被改代码的来源: 纯新增。承载它的头区 Stack 是 conv-mine v1 写的(MinePage.ets@v1:118-163,#8263):Stack 收在 `.width('100%')` 无高度、装饰图只给 `.width('100%')+Contain`,依据是它读的 `fragment_mine.xml` 和自定的尺寸策略「只采用源 XML 显式 dp,未标注尺寸的图标留固有尺寸+Contain,不硬编码 bounds(confidence=medium)」——这条正是派发词原话。前一版写者 slice17-home v29(v39,#17632)当时在做 F018 接线(diff@v39 是 checkUpate 转调),派发词只给「填 HomePage 四槽位/接线 + 单写者纪律」,没有版面校核职责,所以没补。
生成时为什么没做好: 转换错——a2h-execute 转换环(conv-mine v1)把 ConstraintLayout 拍成 Column+Stack(自述 P-07 约束表达力缺口)时,把「头区高度由 iv_user_icon 底边决定」的约束链丢了,又按派发词不硬编码 bounds,高度就空着交给最高子组件。
是否必要: 必要,128 能对着安卓 XML 逐值核出来,不钉死则装饰头图撑高头区、VIP 横幅及以下整体下移。
证据(每条带坐标):
  1. diff MinePage.ets@v40(fixer-r1 v12 #23181)只有 +4 行 `.height(128)/.clip(false)`;blame@v40 changed=True:替换 0 行、新增 4 行。
  2. fixer-r1 v7 #23143 读了 `ALIGN_PMineFragment_layout_drift_header-height.md@v1`;派发词把它并进 `SYSTEMIC_image-no-explicit-size`(P0)。
  3. conv-mine #8214 全文读 `fragment_mine.xml`(390 行):`iv_user_icon` marginTop 60 + 68dp(:25-28)、`iv_vip_enter` `constraintTop_toBottomOf="@id/iv_user_icon"` + marginTop 20(:60-68)→ 头区 128vp、横幅顶 148,与修复后 v40:400/406 + vipBanner `margin top:20` 吻合。
  4. MinePage.ets@v1:118-163(conv-mine v1 #8263)与 v39:360-403 逐行相同:Stack 结尾只有 `.width('100%')`,`icon_mine_top_bg` 只有 `.width('100%')+.objectFit(Contain)`。
  5. conv-mine 收尾报告:「ConstraintLayout → Column + Stack(P-07 约束表达力缺口)」「未标注尺寸的图标留固有尺寸 + Contain,不硬编码 bounds(confidence=medium)」——与派发词「confidence=medium → 不硬编码 bounds」同源,说明它读全了源码仍写错,不是漏读/读旧版。
  6. diff MinePage.ets@v39(slice17-home v29 #17632)是 `checkUpate` 业务转调,证明生成末环只接线不动版面。
  7. fixer-r1 #23178 的 awk 输出显示 Edit 之前 Stack 上确实没有任何 `.height`。
无法确认的部分: 单 `ALIGN_..._header-height.md@v1` 是外部输入、内容不可复原,单里实测偏差多少、阈值如何无法核;MinePage.ets v10–v31 多版「内容未知」、v17/18 处有 edit-miss 断点、v32 是「实录外修改」,blame@v39 对头区标「归属未知(断点后)」,我靠 v1 与 v39 逐行相同接续,中间是否有人短暂改过头区无法确认;该 finding 报的是 MineFragment(对应 MineComponent.ets,fixer 在 v7–v11 已同步修),MinePage 是同 UI 的重复副本,是否另有针对 MinePage 自身的截图判据无法确认。
置信: 高——修复内容、128 的取值来源、原作者代码及其书写依据都能落到工具原文(diff@v40、#8214 的 XML、MinePage@v1:118-163、conv-mine 与 slice17-home 的派发词);只有单的量化判据和断点区间的中途改动这两处存疑。
```