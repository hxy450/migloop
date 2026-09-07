```
文件: entry/src/main/ets/pages/GuidePage.ets（返回按钮 iv_back，原 :172-176）  修复方: visual-fixer / fixer-r1(agent-a68daf720e780b4c2, toolUseId toolu_01APi9vUJuvdDSBK2JqMebM4)  修改时间: 2026-07-26T20:46:28.160Z

修复改了什么: 把返回箭头的 `.width(24).height(24)…​.padding(20)` 改成 `.width(10 + 20 * 2).height(16 + 20 * 2)`（即 50x56vp 总框，内容区回到 10x16vp），并补了 6 行注释说明「ArkUI 的 padding 计入已声明尺寸、与 Android wrap_content 外扩语义相反」。

修复的依据: round-1 视觉核验单 `ALIGN_PGuideDifficulty1Fragment_missing_element_back-arrow.md` +（其父）`SYSTEMIC_image-no-explicit-size.md`：真机截图逐像素扫 (0,70)-(180,200) 全是背景色 RGB≈(222,217,249)，但无障碍树里 `Image [0,130][130,260]` 节点在、点击 (65,195) 能回上一屏、`ic_guide_back.webp`(1020 bytes) 也在 —— 判定为「24 − 20×2 = −16 内容区为负 → 图标零可绘制区」，非资源缺失，影响 4 个引导页。尺寸取值不是照抄单子建议的 `.width(64).height(64)`，而是 fixer 自己 `sips` 实测源图 `mipmap-xxhdpi/ic_guide_back.webp = 30x48px`，÷3 得 10x16dp 后加 padding 反推。

被改代码的来源: 生成轮的页面转换 agent `aconv-guide`(agent-aconv-guide-979179ee8c5e2b3d) 在 2026-07-24T02:07:48.449Z 一次性 Write GuidePage.ets 时写下的。依据是 `activity_guide.xml:24-32`（`wrap_content` + `padding="20dp"` + `marginTop=40dp`）—— padding 20 是从 XML 逐字照搬的，而 **24vp 是它自己补的默认图标尺寸**：源 XML 只有 wrap_content，没有任何尺寸；它也没去量 drawable 像素。它自述的映射决策原文就是「返回图标 ic_guide_back（icon 24vp + padding 20vp + marginTop 40vp）」。

生成时为什么没做好: 输入的 `view.xml` 是合成的、`iv_back` 的 `bounds=""` 为空（无真机 dump），conv agent 自己也写明「view.xml is synthesized（无真机 dump）：bounds 为空」—— 于是 wrap_content 只能猜成 24vp；而当时手上的 pitfall 清单只覆盖了 P-15（Image 默认 objectFit），没有「ArkUI padding 计入尺寸 / Android padding 外扩」这条盒模型反向语义，所以 24 和 20 被同时写下且无人察觉冲突。

是否必要: 必要 —— 图标零可绘制区导致 4 个引导页的返回入口完全不可见（功能还在、只是看不见），是纯迁移缺陷，不改无法收敛。

证据(每条带位置):
  1. 原始代码与其依据：`agent-aconv-guide-979179ee8c5e2b3d.jsonl:64`（2026-07-24T02:07:48.449Z，Write GuidePage.ets，含 `.width(24).height(24).objectFit(ImageFit.Contain).padding(20)`）；同文件 `:88`（02:10:35.416Z）自述「返回图标 ic_guide_back（icon 24vp + padding 20vp + marginTop 40vp）」。
  2. 安卓源依据：同 agent `:19`（01:57:00.182Z）读到 `activity_guide.xml:24-32` —— `wrap_content` / `padding="20dp"` / `marginTop="40dp"`，**无任何显式尺寸**。
  3. 生成链断点：同 agent `:15`（01:56:54.582Z）读到的 view.xml 中 `iv_back` 节点 `bounds=""`；`:88` 明写「view.xml is synthesized（无真机 dump）：bounds 为空」。
  4. 缺陷发现：`agent-a68daf720e780b4c2.jsonl:172`（20:46:41.568Z）中 `ALIGN_PGuideDifficulty1Fragment_missing_element_back-arrow.md` 的「实际/源码缺口」段：像素扫描全背景色、节点在、点击有效、资源存在。
  5. 系统性归因：同文件 `:25`（20:33:50.807Z）`SYSTEMIC_image-no-explicit-size.md` 表格行「返回箭头零可绘制区 | GuidePage.ets:172-176 | ArkUI 的 padding 计入已声明尺寸，内容区为负」，并把「固有尺寸（源未标注 size）」这类注释点名为该族 bug 的源头。
  6. 修复取值的实测：同文件 `:165-166`（20:46:05.155Z → 20:46:07.804Z）`sips` 得 `./app/src/main/res/mipmap-xxhdpi/ic_guide_back.webp pixelWidth:30 pixelHeight:48`，据此 10x16dp。
  7. 两道生成期复核都放过了它：`agent-abatch3-closer-acbba18ff56f4773.jsonl:57`（2026-07-24T02:58:04.930Z，读到 GuidePage.ets:142-148）与 `agent-agroup3-closer-5aab096130b8eb86.jsonl:63`（2026-07-24T18:53:14.177Z，读到 :165-170）均原样读过该 5 行未提异议 —— 这两个 closer 做的是资源存在性/编译级检查，不做布局语义核验。
  8. fixer 收尾自述：同文件末尾（21:43:31.536Z）「第二条同源反向语义：ArkUI 的 padding 计入已声明尺寸（Android 是外扩）… 改成 `.width(10+20*2).height(16+20*2)`」，并称同款还修了 `icon_dialog_close`(×3)、`icon_home_top_vip`。

无法确认的部分: 修改后是否重新截图验证「深色 `<` 笔画像素出现」（单子第 5.2 条判据）—— 本转录内未见 round-2 复截结果，只见 fixer 自述已修。`24vp` 这个数字是否来自某份未在转录里出现的设计/尺寸约定（如 dp_24 token），无法确认；转录里 conv agent 拿到的资源表虽含 `dp_24 | 24vp`，但它并未引用该 token，此关联为推测，不作结论。fixer 未查 HarmonyOS 侧 `base/media`（无密度限定目录）下该图的实际渲染密度，10x16vp 与安卓 @3x 的等价性依赖 `ImageFit.Contain` 兜底。

置信: 高 —— 写入点、依据、发现单、实测取值、两次复核放行全部在转录里一一对上时间戳与行号，唯一未闭环的是修复后的视觉复验。
```