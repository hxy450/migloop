```
文件: entry/src/main/ets/pages/GuidePage.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v13/v14/v15/v16

修复改了什么: 三处视觉纠偏——(1) v13 把返回键 Image 从 `.width(24).height(24).padding(20)` 改成 `.width(10+20*2).height(16+20*2)`;(2) v14+v15 新增常量 `TRACK_HEIGHT=4`,把进度条两条 Row 的 `.height('100%')`/`.borderRadius(10)` 改为 4vp / 2vp;(3) v16 在宿主 Swiper 上补 `.padding({bottom: this.windowModel.windowBottomPadding})`。

修复的依据: v13 依据派发词里 `SYSTEMIC_image-no-explicit-size`(P0) 直接点名「`GuidePage.ets:172` 那处要连 padding 一起改——ArkUI 的 padding 计入已声明尺寸,`.width(24).padding(20)` 内容区为负」,再自行取证资源固有像素(fixer v13 #23187 得 mipmap-xxhdpi/ic_guide_back.webp 30x48px @3x=10x16dp);v14/v15 依据 fixer v23 现读 `activity_guide.xml@v1[33-46行]`(SeekBar 占位框 200x20dp)+`platform-res/drawable/seekbar_horizontal_style.xml@v1`(#23456,轨道 shape height=4dp);v16 依据 fixer v29 读 `ALIGN_PGuideDifficulty1Fragment_layout_drift_bottom-buttons.md`(#23556:鸿蒙底部按钮行下移约 2.7% 屏高,影响 4 页)+ `GuideInitComponent.ets@v11` 的 WindowModel 用法(#23566)。

被改代码的来源: 返回键 24x24 与进度条 `.height('100%')/.borderRadius(10)/.width(200).height(20)` 均出自生成期 conv-guide(a2h-activity-converter, agent-aconv-guide-979179ee8c5e2b3d v1)写的 GuidePage.ets@v2——它的转换报告自述依据是「返回图标 ic_guide_back(icon 24vp + padding 20vp + marginTop 40vp)」和「SeekBar → 自定义 Stack+linearGradient,轨道 200vp × 20vp」,即只读了 `activity_guide.xml@v1`(#7417)就把 SeekBar 的控件占位框 20dp 当成轨道,24vp 则是 XML 里没有的自造值(iv_back 是 wrap_content)。slice15-guide v2(写 @v11)与 group3-closer v14(写 @v12)只做接线/箭头函数改写,原样留下这些行。v16 属纯新增:conv-guide 自述「沉浸式按 Layer 3 内联落地……前景避让用源码 40vp + FWD-REF 精修」,只做了顶部避让;slice15-guide@v11 接入 WindowModel 时也只用于 `guideTopInset()`,底部避让全流程从未有人写过。

生成时为什么没做好: 卡在生成链的 a2h-execute 转换这一环——conv-guide 读全了 `activity_guide.xml` 却把 wrap_content 补成臆造的 24vp、把 SeekBar 占位框 20dp 当轨道厚度,且始终没读 `drawable/seekbar_horizontal_style.xml`(真值 4dp),同时它套用的 `ui-migration-pitfalls.md@v1` 只覆盖 P-07/10/13/15/17,不含「ArkUI padding 计入尺寸(与 Android 外扩相反)」这条,该规则是 round-1 才被 fixer 现挖出来的。

是否必要: 必要——v13 不改则内容区 24−40=−16、返回键零可绘制;v14/v15 有 4dp 源真值;v16 有实测 2.7% 屏高漂移的 oracle,方向(上抬)正确。

证据(每条带坐标):
  1. GuidePage.ets@v13 diff:`.width(24).height(24)` → `.width(10+20*2).height(16+20*2)`;派发词(fixer v13 派发指令 SYSTEMIC_image-no-explicit-size 行)已点名 `GuidePage.ets:172` 与 padding 语义。
  2. fixer v13 #23187 原文:`mipmap-xxhdpi/ic_guide_back.webp pixelWidth:30 pixelHeight:48` → @3x = 10x16dp,佐证新尺寸取值。
  3. GuidePage.ets@v10 content 143-147 行已是 `.width(24).height(24).objectFit.padding(20)`,167-186 行已是 `.height('100%')/.borderRadius(10)/.width(200).height(20)` —— 早于 slice15-guide@v11 的重写,故源头是 @v2(conv-guide v1 #7450)。
  4. conv-guide(v1) 收尾报告自述「返回图标 ic_guide_back(icon 24vp + padding 20vp + marginTop 40vp)」「轨道 200vp × 20vp」,且 v1 读取集(#7409–#7448)只含 `activity_guide.xml@v1`、`GuideActivity.kt@v2`、`view.xml@v1`、`resource-mapping.md@v1`,无 `seekbar_horizontal_style.xml`。
  5. fixer v23 读 `platform-res/drawable/seekbar_horizontal_style.xml@v1`(#23456)+`activity_guide.xml@v1[33-46行]`(#23452),v15 新增常量注释写明「三层 `<shape><size android:height="4dp"/>`,layout_height=20dp 只是控件占位框」。
  6. fixer v29 #23556 展开的 `ALIGN_PGuideDifficulty1Fragment_layout_drift_bottom-buttons.md` §3:安卓 86.9%–93.6%,鸿蒙 89.6%–95.7%,下移约 2.7%,影响 Difficulty1/2/3 + Details 共 4 页;§5 亦写「鸿蒙需扣掉底部手势条避让后再对齐」。
  7. slice15-guide 派发词:GuidePage 是 Stage 1 已有产物、本轮只「填槽 + 接问卷状态流转」,可解释它为何不复核像素取值;group3-closer 写的 @v12 diff 只动 `onAdvance/onRetreat` 箭头函数体。

无法确认的部分: blame(@v13/@v14, changed=True) 对这 6 行一律返回「归属未知(断点后)」,conv-guide 为原作者是靠 @v10 复原内容 + 其自述报告推定,账本本身没有逐行签名;`spec/baseline/plans/resource-mapping.md@v1` §6.3 是否本身就把轨道写成 20dp(即是否属「spec 写错」)未展开核对;v16 用的 `windowModel.windowBottomPadding` 实际数值与那 2.7% 是否量级吻合无实录佐证(派发词明令不复测);单里另提的「否」按钮 borderRadius 15dp 一项未见修复动作。

置信: 中——三处改动的修复依据、时间线与被改行文本都能逐条落到工具坐标,但被改行的逐行归属是推定而非账本签名,且 v16 的量化对齐与 round-2 复验缺证据。
```