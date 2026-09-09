# MemberCenterPage 冻结转录事实清单

## 口径

- 由独立 GPT-5.6-sol / medium 代理从原始转录整理，供后续逐条核验；不是人工裁定的金标，也未提供给被测调查员。
- 唯一目标：`entry/src/main/ets/pages/MemberCenterPage.ets`。只使用 `holdout-v2/member-center/pool` 内两个根及其子代理转录；下文均为相对 pool 路径。
- 这是有限参照集合，不宣称穷尽金标。转录命令仅作为历史数据读取，本次没有执行。
- `ok`/Write 成功只能证明当时共享工作树发生替换；`BUILD SUCCESSFUL` 只证明 ArkTS 编译/打包/签名通过，均不等于修后设备行为或像素正确。

## 生成前输入与后续要求

1. `agent-aconv-member-08b3dcf6deb3c515` 在 2026-07-24 02:26:08Z 收到 UI-only 任务：输出精确目标文件，覆盖 Banner、商品单选、支付方式、协议、CTA、优惠动画；支付逻辑留给 Slice 8；`confidence=medium`、不得硬编码截图 bounds、禁止编译（`9b3105a2-.../subagents/agent-aconv-member-08b3dcf6deb3c515.jsonl:1`，原始用户消息、无 tool ID）。它读取页面 spec（`:8`, `toolu_01TL1CtJ5Ce79mR1Mm967dU3`）、Android `activity_member_center.xml`（`:18`, `toolu_011TxfAFEPuoC44JuTMvy3SP`）与 `item_product_info.xml`（`:20`, `toolu_01WFGoWsupdYHKtvQS3KTvLN`）。这些支持布局/尺寸语义来源，但 synthesized view 与 medium confidence 不是设备像素金标。
2. 02:35:15Z 首次 Write 创建目标文件（同文件 `:61`, `toolu_01Av1mPVPn4rQrEuYyWyWqJH`; 成功结果 `:62`）。当时 `Indicator.dot()` 只有 5/5/10/5 几何，无颜色和左偏移。成功仅证明文件创建；该代理按要求未编译。
3. `agent-aslice8-pay-80bbb1f44b77da0f` 在 15:32:21Z 收到 F010 支付切片任务，要求先读 feature/API/Android anchors，再接线既有会员页（`9b3105a2-.../subagents/agent-aslice8-pay-80bbb1f44b77da0f.jsonl:1`）。它读取 F010 spec（`:10`, `toolu_01XugBanE5kB1jf34K6Z1QyB`）和 Android `MemberCenterActivitiy.kt`（`:21`, `toolu_011NHFj8Nxr2YVMafvTUkkjY`），16:04:37Z 用 Write 重写目标页（`:264`, `toolu_014KPLsf5z2NXVMADVFHfxbz`; 成功结果 `:265`）。该版仍有：无色/无位置的 Indicator；非滚动价格整串 30vp；CTA `width('100%') + height(56) + horizontal margin 20`。这是修复前代码的直接证据。

## 修复阶段实际修改事项

### 1. 三个 controller 的蒙层参数（动态全仓脚本）

- 原始修复任务要求先做 `SYSTEMIC_dialog-mask-too-light`（`ff019d8a-.../subagents/agent-a68daf720e780b4c2.jsonl:1`）。读取到的 finding 称三处修复前实测为 Android 255→115（约 0.55）、HarmonyOS 255→204（约 0.20），并要求扫描所有 controller（`:29`, tool result `toolu_01B8RaNhNXNsZ6LPHxobH1KV`）。
- 2026-07-26 20:41:07Z，`visual-fixer` 运行 `os.walk` 全仓脚本并直接 `open(path,'w').write(new)`；不是 Write/Edit 工具调用（`:103`, `toolu_01T6WkXMhD7rUsHaSaMPuhgx`）。规则：AppLoadDialog 写 `Color.Transparent`，其他漏设项写 `Palette.DIALOG_MASK`。
- 结果明确报 `3 sites import=+ entry/src/main/ets/pages/MemberCenterPage.ets`（`:104`, 同 tool ID）。结合生成版可核为 load、PayAgreement、RenewRule 三处；H5 生成时已有透明 mask。后续抽查显示 PayAgreement 新增 `maskColor: Palette.DIALOG_MASK`（`:106`, `toolu_019xb74vC9BgRv4xeSea6NmF`; 结果 `:107`）。
- 支持：三处确实被脚本改写、PayAgreement 具体值。不支持：三弹窗均有修后真机验证；finding 是修复前观察。

### 2. 两张优惠图片补尺寸约束（动态批量脚本）

- 20:54:02Z 的 Python patch 对目标页做两次唯一替换（同文件 `:233`, `toolu_01DeqiV3n9uPH5cLqUA6a8Yn`）：`icon_vip_masked_img3_20` 在 width 280 后增 `aspectRatio(840 / 942)`；`icon_vip_masked_img1_20` 在 width 254 后增 `height(366 + 35)`，保留 bottom padding 35。
- 配对结果出现两次 `ok entry/src/main/ets/pages/MemberCenterPage.ets`（`:234`）。随后尺寸扫描只列出另一文件一处候选（`:236`, `toolu_01YU54EzkSMrRnQvcPqWUV5o`; 结果 `:237`），目标页不再被列出。
- 支持：两处实际改动且通过该静态扫描器。不支持：这两图此前有独立会员页 finding，或 366+35 已真机对齐；这是 SYSTEMIC 扫描带出的旁观修改。

### 3. “立即开通”CTA 横向布局

- 修复前 finding：Android CTA x=0.056→0.944、高约 7% 屏高；HarmonyOS x=0.075→0.924、高约 5.77%，底部留白更大（`:401`, `toolu_01TNhXhFRHWXbwkWjbX59zgN`; 结果 `:402`），并建议增高/减 bottom padding。
- 复核得到目标页 `.height(56)`、margin 20、心跳 scale 和唯一 `windowBottomPadding`（`:425`, `toolu_013eYDXVP5TaTQ9sez1LQDAF`→`:426`; `:433`, `toolu_01VR9WKRSAg4e98gXDyH3Lrv`→`:434`）；Android XML 明载 height 56dp、horizontal margin 20dp（`:430`, `toolu_018HkF74ftoZebLRLYr9inG9`→`:431`）。
- 21:16:18Z 实际替换为父 `Row().width('100%').padding({left:20,right:20}).margin({top:20,bottom:17})`，按钮仍 width 100%、height 56、带 scale（`:436`, `toolu_01JFX7XbxsbxexCTxvvuGvUy`; `:437`=`ok`）。没有增高或删安全区。
- 支持：margin→父 padding 的实际变更与 56dp 源真值。修复者将测得宽高解释为动画采样相位、底差解释为平台安全区（`:615`, `toolu_01XJTap83qih25dRyZQyQNkw` 的追加说明）；这是语义归因而非修后复测，不能宣称 finding 已视觉关闭。

### 4. Banner 指示器颜色

- 修复前 finding 称 Android 选中/未选中约 `#6B6B70/#A9A9B0`，HarmonyOS 选中约 `#0A6CFF`，形状已一致（`:501`, `toolu_01YGYsH1u6KQtX8A2AkLVXFF`; 结果 `:502`）。
- 21:24:15Z patch 给 Indicator 加 `.color(BANNER_DOT_COLOR)` / `.selectedColor(BANNER_DOT_SELECTED_COLOR)`（`:528`, `toolu_016bvcNnvDn4tHXcYJY7CzLh`; `:529`=`ok`）；21:24:34Z 新增常量 `#A9A9B0` / `#6B6B70`（`:532`, `toolu_012iDuZirwvtQcB6kboc6BwR`; `:533`=`ok`）。
- 支持：缺省色被覆盖，取值来自修复前截图采样。不支持：近似色是 Android 资源 token 真值，或修后像素已对齐。

### 5. Banner 指示器左对齐

- 同一 `:502` 结果记录 Android 指示器约 x=0.05→0.17、HarmonyOS x=0.43→0.56；数量和切页行为正确，仅位置不同。
- 与颜色共用 `:528`，新增 `.left(BANNER_INDICATOR_LEFT)`；`:532` 将常量设为 18。追加说明以 18/约374vp≈4.8% 并引用 Android `layout_gravity="left|bottom"`（`:615`, `toolu_01XJTap83qih25dRyZQyQNkw`）。
- 支持：默认居中改为显式 left 18及其选择依据。不支持：修后实际落点已达到 x≈0.05。数量/切页行为没有修改。

### 6. 商品价格后缀恢复 16vp；第一次实现不是最终态

- 修复前 finding 记录 HarmonyOS 将 `1/天` 作为单个特大 Text；其“1:2.5:1.4”只是初始估计（`:502`）。
- 正确源证据：`item_product_info.xml` 给 `tv_product_price` 16dp、`rollingTextView` 30dp（`:521`, `toolu_01Xv7nKGebpdFpBy9WvB35kC`; 结果 `:522`）；`MemberCenterActivitiy.kt` 非滚动分支用 `showNowPrice.replaceSpan(Regex("\\d+")) { AbsoluteSizeSpan(30, true) }`（`:523`, `toolu_01XBPsevwzempBkQ2sBNTsvW`; 结果 `:524`）。即数字 30，其余继承 16。
- 第一次改写 `:528` 使用 `ForEach(splitPriceRuns(...))` 生成 30/16 Span（`:529`=`ok`）。21:30:17Z 又把它替换为固定两个 Span：`priceDigits(...).fontSize(30)` + `priceSuffix(...).fontSize(16)`，新增 `priceSplitIndex`，示例兼容 `1/天`、`129`、`0.01/天`（`:592`, `toolu_01BrL9dsi5PB64tZiKVRfWoa`; `:593` 打印最终片段）。`splitPriceRuns` 只是中间态。
- 支持：字号语义与最终结构。不支持：真机排版；从串首消费数字/小数点是否覆盖所有后端格式在池内未知。

### 7. 编译暴露后去掉两个 helper 的 private

- `hmos-builder` 读 build1 日志，编译器报 `priceDigits` / `priceSuffix` 为 private、却被 `ProductItemCard` 访问（`ff019d8a-.../subagents/agent-af0e3d2ae54dbf769.jsonl:23`, `toolu_01SSSyTUpqQtQF1SjZy36FTe`; 结果 `:24`, 目标行 1222/1223）。
- 21:46:11Z 两次 Edit 将 `private static` 改为 `static`（`:32`, `toolu_01W4Yg3nfX75u3Yxsk1X4wat`; `:34`, `toolu_01YcRVJymkRf9wtm51Pr5qt8`）；成功结果 `:33`、`:35`。
- 重跑构建（`:36`, `toolu_01PcjKpCh43ea95hpoivTyih`）结果 `:37` 为 `EXIT=0` / `BUILD SUCCESSFUL in 6 s 859 ms`；`:39`, `toolu_018NaGFwR1R7NvbhGWqtq7ET`→`:40` 显示 CompileArkTS、PackageHap、SignHap 完成。
- 支持：访问级别修复消除了当次编译错误。不支持：价格视觉、Banner、CTA、蒙层或设备交互正确。

## 最小结论

冻结池可直接核实该文件在修复阶段至少经历：3 个 controller 的 mask 参数补齐、2 张图片尺寸约束、CTA 父 padding 重构、Banner 两色与 left=18、价格后缀 16vp Span 拆分，以及两个 helper 去 private；随后整包构建成功。本清单尚未核到修后设备复测，不据此证明池内绝无相关记录，也不能升级为“会员中心已达到 Android 视觉/行为一致”。
