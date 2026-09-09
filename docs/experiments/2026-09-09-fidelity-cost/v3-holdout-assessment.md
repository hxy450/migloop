# holdout-v3 MemberCenter 事后评审

评审时点：2026-09-09。四次运行 `raw/tools × rep1/rep2` 均已完成，模型均为 `gpt-5.6-sol`、effort `medium`，冻结工具源码为 `18ca512`。本评审只读四份报告、metrics、先前有限参照 [member-center-reference.md](member-center-reference.md) 与原始冻结 pool；未运行模型、未修改源码或旧 run。

结论：tools 两次都覆盖七类有限参照（把 Banner 色/位合并成一组，所以结构上是六个 defect），raw rep1 覆盖 7/7，raw rep2 漏掉动态 mask 脚本而覆盖 6/7。tools 两次在 input_total、wall 和 end-to-end wall 上均比同 rep raw 低至少 20%，效率门槛成立。但两份 tools 都把目标文件的“三个 mask 站点”错误描述为三个普通/深色 0.55 遮罩；原始脚本实际是 AppLoad 透明、PayAgreement/RenewRule 深色，H5 修复前已透明。tools rep2 还把 CTA 静态风险命名成已成立的“横向尺寸溢出”，强于 finding 与修后证据。由于中心修复事实发生语义错误，本次不满足“关键事项不退”的质量门槛，不能无条件接受；可判为“效率门槛通过、质量门槛未通过”。

## 1. 评审口径及参照边界

- 七类有限参照是：三处 controller mask 参数、两张优惠图尺寸、CTA 父 padding 重构、Banner 颜色、Banner left、价格最终两 Span、编译后两个 helper 去 private。它不是绝对人工金标；新增原文证据可修正其归因边界。
- 本轮确有两点超出先前参照的有价值发现：Slice 8 在整页 Write 前已完整读到 Android `initBannerData()` 的 `setIndicatorMargin(20...)`、`IndicatorGravity.START`、black30/black50；也读到同域弹窗说明中的 `dimAmount=0.55f → controller 侧设置`。因此 Banner 与至少 RenewRule 的明确语义并非纯粹到 visual-fixer 才出现。tools 两次在这点优于简单的“后期新增要求”叙述。
- 但“读到同域契约”不等于可以改写实际 patch 数量/类型；动态脚本本身仍须逐站点核对。
- Write/Edit/脚本成功、构建成功、设备视觉/交互验证分开评价。没有把报告 schema 通过当语义正确，也不因 raw 是散文而扣分。

## 2. 四份报告逐次评价

| 运行 | 七类覆盖 | 可靠内容 | 具体问题 |
| --- | ---: | --- | --- |
| raw rep1 | 7/7 | 最完整地分开 Stage 1 UI-only、Slice 8 整页重写和 visual-fixer；正确识别价格 ForEach 是中间态、固定两个 Span 才是最终态；正确写 AppLoad transparent、其他缺失 controller 用深色；找到后置 BUILD SUCCESSFUL 并明确无设备复测 | 对指示器位置称初始生成者读过主 XML、因而“更像转换遗漏”，但精确 START/颜色其实来自其未读的 Kotlin；后文对 Slice 8 最近写入责任已有修正。少数“初始未读 Kotlin”结论是有界零命中，报告本身有说明 |
| raw rep2 | 6/7 | CTA 区分最好：finding 要求增高/减底距，而实际只把 `100% + margin` 改成父 Row padding；价格最终两 Span、图片脚本、private 编译修正、构建/设备边界均正确 | 完全漏掉目标页三处 mask 动态改写。多处把根 UUID 写成不存在的 `9b3105a2-85ec-4898-9786-b3b220f06754`（正确为 `...4889-9786-b3c220...`），虽可由 agent 名/行号回猜，仍是引用缺陷 |
| tools rep1 | 7/7 | 六 defect 合理合并 Banner 色/位；正确追到 Slice 8 已读 Banner/price 真值；CTA 明确只修横向盒模型、未落实 finding 的高度/底部留白；价格最终 v15-v16 是两个固定 Span；确认第二轮构建、否认设备闭环 | defect A 标题为“三个会员页弹窗控制器补统一深色蒙层”。正文虽承认 H5 透明特例和只对 RenewRule 有直接早期义务，但未正确说明脚本在本页的三个实际目标包含 AppLoad transparent。中心 patch 事实有误 |
| tools rep2 | 7/7 | 生成者输入、Slice 8 更强输入、视觉 finding 后置量化、图片规则后增、private 错误由 fixer 引入等时间线清楚；构建与设备边界正确 | mask 错误更明确：称“v7 三个非-loading controller”并称脚本给“三个其他 controller”插入深色；实际只有两个深色，第三个是 AppLoad 透明。CTA 标题“横向尺寸溢出”也把静态风险解释写成已确认缺陷，见下节 |

## 3. 七类事项核对

### 3.1 三处 mask：四报告中最重要的事实分歧

原始 Slice 8 整页 Write 可核四类 controller 状态：

- `loadDialog` 未显式 mask；它的 Android AppLoadDialog 例外语义是 `dimAmount=0.0f`。
- `payAgreementDialog` 未显式 mask。
- `renewRuleDialog` 未显式 mask。
- `h5PayDialog` 已有 `maskColor: Color.Transparent`，不是待补站点。

visual-fixer 的 `patch_mask.py` 按 builder 分类：AppLoadDialog → `Color.Transparent`，其余缺失项 → `Palette.DIALOG_MASK`；结果报 MemberCenterPage `3 sites`。因此三处实际改动是“一透明 + 两深色”，不是“三深色”或“三个 non-loading”。raw rep1正确，raw rep2遗漏整项，tools 两次均在标题/正文中误报。

Slice 8 确曾读到 RenewRuleDialog 的 `dimAmount=0.55f` controller 契约，这是比有限参照更强的早期输入证据；但它最多增强 RenewRule 最近写入责任，不支持把 AppLoad 特例改成 0.55，也不证明三个普通 controller 的说法。

### 3.2 两张图片

raw rep1/rep2 与 tools 两次均确认动态 Python 脚本对精确目标做两次替换并返回两次 ok：img3 加 `aspectRatio(840/942)`，img1 加 `height(366+35)`。四份也都没有把静态扫描通过说成设备对齐。该项通过。

### 3.3 CTA：finding 与实际 patch 不能合并

修复前 finding 的设备量测是按钮在动画采样时“偏窄/偏矮”、底部留白更大，处方是增高、减少 bottom padding。fixer 随后以心跳 scale 和唯一平台安全区解释纵向/可见宽度差异，拒绝该处方；实际 patch 仅将按钮自身左右 margin 20 下沉为父 Row padding 20，height 56、纵向 margin 和 `windowBottomPadding` 均未改，并自称该改动主要“消除溢出隐患”、本身不应改变预期视觉。

四份都识别了实际 patch 与 finding 处方不同，这是关键覆盖。tools rep1和 raw rep2表述最克制。tools rep2 的 defect 标题“立即开通按钮横向尺寸溢出”及“没有保持可用内容宽度语义”是合理的静态盒模型风险判断，但不是 finding 已实测的根因，也没有修后设备结果确认；应降级为“静态风险/修复者诊断”，不能作为已验证的视觉缺陷。

### 3.4 Banner 颜色与 left

四份均覆盖；tools 将其合为一个 defect不构成漏项。原始 pool 支持 Slice 8 写 v7 前已读到 Kotlin 的 START、margin 20、black30/black50，却仍写默认居中/默认颜色。因此最近整页写入责任可明确落到 Slice 8；初始 UI converter 只读 spec/XML，未确认读到这些运行期配置。

修复值是截图近似灰 `#A9A9B0/#6B6B70` 与 `left=18`，不等同于源 Kotlin 的资源 token/20dp 原值。tools rep1注意到 left 18 与 Kotlin margin 20 不同，四份均无修后截图，不能宣称对齐完成。

### 3.5 价格最终结构

四份均正确区分：第一次 patch 的 `ForEach(splitPriceRuns(...))` 只是中间态；随后替换为固定 `priceDigits(...).fontSize(30)` 与 `priceSuffix(...).fontSize(16)` 两 Span。相邻独立 `￥` Text 才共同形成三段视觉。Slice 8 在整页 Write 前已经读取 Kotlin `replaceSpan(Regex("\\d+"))`，仍保留整串 30vp，因此其责任比初始 converter 更直接。

对于 `0.01` 把小数点并入数字的扩展，pool 只有修复者解释，没有后端格式用例或设备排版验证；tools 两次均保留此边界。

### 3.6 helper 可见性与构建

四份均确认 visual-fixer 新增的两个 private static helper 从 `ProductItemCard` 访问，导致首次构建两条 private-access error；builder 随后分别去掉 private，第二次返回 `EXIT=0 / BUILD SUCCESSFUL`，并完成 CompileArkTS、PackageHap、SignHap。

这是修复新代码引入并在构建阶段消除的错误，不属于初始生成者或 Slice 8。构建只证明当次共享工作树可编译，不证明 CTA、价格、Banner、mask、图片在设备上正确。四份在此均合格。

## 4. 引用与原始事件

- raw rep1的 pool 相对路径、物理行和 tool ID 可直接核回；缩略 ID 与同文件行号组合可唯一定位。
- raw rep2 的错误根 UUID 是实际引用缺陷，不能当可点击路径；大部分 agent 文件名、行号、tool ID 仍足以人工恢复，但报告生成应禁止 UUID 手抄。
- tools 的 `#agent:sequence@Lphysical` 与 `file:...@vN` 是 MCP 可展开定位符；coverage 22/22 通过只说明结构上交代完 9 versions + 13 candidates，不认证 reason 的语义。
- holdout-v3 的 MCP transcript 中 `structuredContent` 出现 0 次，返回只保留 `content`，已消除 v2 的同字符串双份包装。rep1/rep2 分别有 120/94 个 MCP leaf，但 wrapper 仅 20/35；调用数、wrapper 数、字符和 token 是不同口径，不能互相替代。

## 5. 成本与耗时

`input_total` 已包含 `cache_read`；`input_uncached = input_total - cache_read`。output 已含报告的 reasoning output，不再加 `thinking_reported`。四次美元成本均为 null，只能报告 token/墙钟观察值。

| arm / rep | wall_s | end_to_end_s | input_total | cache_read | input_uncached | output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| raw rep1 | 918.0 | 938.8 | 5,857,151 | 5,606,528 | 250,623 | 24,305 |
| tools rep1 | 705.6 | 730.4 | 1,898,182 | 1,737,344 | 160,838 | 18,099 |
| raw rep2 | 945.5 | 966.1 | 4,878,524 | 4,625,152 | 253,372 | 20,799 |
| tools rep2 | 728.0 | 753.1 | 3,573,863 | 3,405,824 | 168,039 | 17,249 |

同 rep tools 相对 raw：

- rep1：wall -23.1%，end-to-end -22.2%，input_total -67.6%，uncached -35.8%，output -25.5%。
- rep2：wall -23.0%，end-to-end -22.1%，input_total -26.7%，uncached -33.7%，output -17.1%。

两次描述均值：raw/tools wall 931.7/716.8s，end-to-end 952.5/741.7s，input_total 5,367,838/2,736,023，uncached 251,998/164,439，output 22,552/17,674。n=2 仍不是统计显著性证据；rep1/rep2 input 降幅差异很大，也说明成本不由 calls 数单独决定。

## 6. 协议门槛的有限判断

约定门槛是“关键事项不退，并且 input 或时间至少改善 20%”。本轮效率半边明确通过：两次 tools 的 wall/end-to-end 均约下降 22%，input_total 也分别下降 67.6%/26.7%。覆盖数量也未退：tools 两次均交代 7/7，而 raw rep2 只有 6/7。

但质量半边不通过：tools 两次在 mask 的实际三站点语义上均错，把“一透明 + 两深色”写成三个深色/non-loading；这是七类参照中的中心代码事实，不是轻微措辞。tools rep2 对 CTA 又把未设备验证的静态风险提升成 defect 标题。故本评审不建议按协议接受当前 tools 结果为“关键事项不退”。

若修正 mask 事实并把 CTA 根因降级为静态诊断，现有观察将满足有限门槛；仍只能表示这两次 holdout 的质量/效率门槛通过，不能推广成稳定总体收益。

## 7. 建议

1. 动态脚本必须输出逐站点 builder、before/after 和分类值，不能只报每文件 `3 sites`；否则最容易把透明例外汇总成统一深色。
2. finding 的观测子断言与实际 patch 分开建账：CTA 的纵向差异未修、横向 padding 是附加静态修正，不能用一个 defect 名覆盖。
3. 对整页重写者生成“已读源码 UI 配置消费表”，Banner START/颜色与 price span 这类 Kotlin 真值应在 Write 前显式核销。
4. 保留构建与设备两个门禁：本轮 build 已闭环，视觉/支付行为没有；后续父流程的 UI 实测应独立记录，不能回填成这四份调查报告已经验证。
5. 保持 MCP 单一 `content` 返回，并继续同时报告 leaf、wrapper、token 与墙钟；不以调用数直接解释成本。

本结论仅覆盖冻结 pool 和七类有限参照，不认证没有其他修改、缺陷或验证证据。
