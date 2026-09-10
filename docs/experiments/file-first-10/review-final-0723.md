# 旧会员页／启动页核心参考：冻结前独立复核

2026-09-10。本次只复核 `reference-units.json` 的 F10-01 `price` / `repair-compile` 和 F10-02 `back-gate`，并读取指定旧 review-v2 底稿作为定位入口；未访问调查模型答案文件、未执行历史命令、未改已有参考文件。原始证据均取自 `attribution10/formal-v1/member-center/pool`。其它图片、遮罩、系统栏等单元不在本次签核范围内。

结论：三条核心历史链没有需要推翻的事实错误，可以冻结；但应先澄清两处评分措辞，并把证据边界与必答核心拆开。特别是，“未复述边界”不等于“作出了越界主张”。

## 建议冻结的最小核心与条件边界

| 单元 | 正确归因的核心 | 不应成为额外逐项必答清单 | 真正需要拒绝的反向主张 |
|---|---|---|---|
| F10-01 price | 原价格整体统一字号，没有保留源的数字段强调／后缀基础字号；修复改为分段表达。生成期存在具体可核的丢失／沿用链，尤其 Slice8 写前实际收到相关源码，却仍写统一字号。表达和证据可用等价方式组织，不强制 actor 名称或补丁编号。 | ForEach→固定 Span 的全部中间过程、每个 helper 名称、每段字号数字、指示器同批改动、未验证所有样例、未证明上下文／skill 机制等。后三类未知可在文件级统一声明，不必每单元重复。 | 声称 Slice8 从未获得相关源；只因最后整文件 Write 就认定它首次引入统一字号；声称任意价串已证完全等价／设备全面通过。 |
| F10-01 repair-compile | 价格修复增加了被另一 struct 调用的 private helper，实际编译拒绝跨 struct 访问；后续去掉可见性限制，重新构建通过。这是修复阶段引入的问题。 | 动态分段具体怎么实现、完整 helper 名列表、两个 Edit 必须分两段叙述、具体行号必须作为答案措辞、反复强调“不是初版”“不是视觉验证”等。阶段已经说清即可。 | 把实际报错的 priceDigits/priceSuffix 归为最初生成；将这两个具名 helper 精确指为 L528 创建；或声称较早中间补丁已经发生了一个没有记录的编译失败。 |
| F10-02 back-gate | 初版页面级返回处理存在，Navigation 装配移除了它；后续弹窗 wiring 依赖 isModal 的解释没有形成充分保证。后修有“接管关闭请求”和“返回页面时补恢复弹窗”两种作用，不能混作同一个 callback 的同一效果。 | 每次作者名字、完整 D-020 决策分析、所有 DismissReason 枚举、回调幂等变量、无 result 的 pop 是否触发 onPop 的 API 定论、初版所有场景正确与否、唯一充分原因是否已证等。只要没有相反断言，不能因缺这些限定句扣整项。 | 把初版说成根本没有返回处理；把页面级 handler 删除说成“删除了已存在的弹窗 onWillDismiss”；将恢复 guard 当作消费原始关闭请求；说初版各弹窗态已经实测正确，或完整修复已设备闭环。 |

`supported` 当前混合了核心、补丁演化和边界。建议新增 `core` / `optional_detail` / `boundaries_if_claimed` 字段，或在评分合同明确等价解释；无需让模型背出全部 supported 句子。

遗漏 L352 恢复补丁应进入**修改覆盖不足**；如果只解释了关闭门禁原因，不要把已解释正确的这部分翻成“因果错误”。若保留 back-gate 一个归因单元且要求两作用均覆盖，则记 `incomplete`，与明确混淆两作用的 `wrong` 区分。会员页漏叙 L528→L592 中间策略同理，不应抹掉“统一字号丢富文本语义”已正确的归因。

## 两处必须澄清的措辞

### A. 可以识别最早记录中的统一字号作者，尚不能证明唯一生成根因

F10-01 price 当前写 `earliest unique author and deeper mechanism are not proven`，容易误伤更完整的调查。

原始 `agent-aconv-member-08b3dcf6deb3c515.jsonl` L61，2026-07-24T02:35:15.167Z，Write `toolu_01Av1mPVPn4rQrEuYyWyWqJH` 已写：

```text
Text(this.item.priceText)
  .fontSize(30)
```

L62，2026-07-24T02:35:15.242Z，同 ID 成功回执为 `File created successfully ... MemberCenterPage.ets`。这早于 Slice8 L264 整文件重写。

因此可以接受：“在现存记录中，最早的统一字号实现来自初版 converter，Slice8 后来沿用并增加动画分支。”不能凭此继续推断“初版作者已经收到富文本源码却忽略”，或“它是所有后期价格表现的唯一充分原因”。本次未补齐初版富文本输入链。

建议把该边界改为：`The earliest recorded uniform rendering is identifiable in the converter's initial Write; its exact delivered rich-text input and unique causal responsibility are not established. Slice8 is a separate, evidenced propagation/input-output mismatch.`

### B. 泛称 private helper 的修复来源，不应被精确函数名规则误判

原始 `agent-a68daf720e780b4c2.jsonl` L528，2026-07-26T21:24:15.832Z，`toolu_016bvcNnvDn4tHXcYJY7CzLh`，已经写入：

```text
ForEach(MemberCenterPage.splitPriceRuns(this.item.priceText), ...)
private static splitPriceRuns(text: string): string[]
private static isDigitRun(run: string): boolean
```

L529，21:24:18.729Z 回执 `ok`。L592 才把它替换成 private `priceDigits` / `priceSuffix`，后续 compiler 实际报的是后两者。

所以“价格分段修复引入了跨组件访问 private helper 的问题，builder 去掉 private”是正确概括；若调查者把**泛称** private helper 追到 L528，也有实际代码依据。只有把**具名** priceDigits/priceSuffix 的创建精确错绑到 L528，或者声称 L528 当时已编译失败，才是错误事件主张。

当前 reject 的 `These private helpers ... by fixer:528` 可保留，但应明确 `These` 只指具名 priceDigits/priceSuffix，不涵盖所有私有分段函数。不要强制调查者列出两个中间 helper 名称来证明自己理解了大阶段。

## 独立核过的 MemberCenter 原始位置

| 完整源 basename／行 | 时间与 call_id | 原始依据 |
|---|---|---|
| `agent-aslice8-pay-80bbb1f44b77da0f.jsonl` L21→24 | 2026-07-24T15:33:49.105Z → 15:33:51.671Z；`toolu_011NHFj8Nxr2YVMafvTUkkjY` | Read 指向真实 Android `app/src/main/java/cn/sanfate/pub/platform/page/MemberCenterActivitiy.kt`；返回 276–282 行 `model.showNowPrice.replaceSpan(Regex("\\d+")) { AbsoluteSizeSpan(30, true) }`。相关源确实在写前交付。 |
| `agent-aslice8-pay-80bbb1f44b77da0f.jsonl` L264→265 | 2026-07-24T16:04:37.440Z → 16:04:37.575Z；`toolu_014KPLsf5z2NXVMADVFHfxbz` | 整文件 Write 的 `struct ProductItemCard` 中是 `Text(this.animatedPrice.length > 0 ? this.animatedPrice : this.item.priceText).fontSize(30)`；更新成功。 |
| `agent-a68daf720e780b4c2.jsonl` L528→529 | 2026-07-26T21:24:15.832Z → 21:24:18.729Z；`toolu_016bvcNnvDn4tHXcYJY7CzLh` | 脚本明确匹配统一 Text 的 old，替换为滚动／非滚动分支；非滚动 ForEach 生成 Span；新增 private splitPriceRuns/isDigitRun；同一脚本另改指示器。回执 ok。 |
| `agent-a68daf720e780b4c2.jsonl` L592→593 | 2026-07-26T21:30:17.239Z → 21:30:20.292Z；`toolu_01BrL9dsi5PB64tZiKVRfWoa` | old 为动态 ForEach；new 为 `Span(MemberCenterPage.priceDigits(...)).fontSize(30)` 与 priceSuffix 的16；新建 private helper。回执 ok，且后续源读回显示固定 Span。 |
| `agent-af0e3d2ae54dbf769.jsonl` L24 | 2026-07-26T21:45:43.530Z；`toolu_01SSSyTUpqQtQF1SjZy36FTe` | 实际 compiler：`Property 'priceDigits' is private and only accessible within class 'MemberCenterPage'`；priceSuffix 同类报错；`COMPILE RESULT:FAIL`。 |
| `agent-af0e3d2ae54dbf769.jsonl` L29 | 2026-07-26T21:45:55.438Z；`toolu_01B3ksjHD3ZYEfadAEE1SRA1` | 真实源读回含 MemberCenterPage 结束于源码1163，`struct ProductItemCard` 开始于1175，调用位于1222–1223；支持跨 struct，不只根据错误消息猜。 |
| `agent-af0e3d2ae54dbf769.jsonl` L32→33 | 2026-07-26T21:46:11.820Z → 21:46:11.895Z；`toolu_01W4Yg3nfX75u3Yxsk1X4wat` | native Edit：`private static priceDigits` → `static priceDigits`；成功回执。 |
| `agent-af0e3d2ae54dbf769.jsonl` L34→35 | 2026-07-26T21:46:12.739Z → 21:46:12.801Z；`toolu_01YcRVJymkRf9wtm51Pr5qt8` | native Edit：`private static priceSuffix` → `static priceSuffix`；成功回执。 |
| `agent-af0e3d2ae54dbf769.jsonl` L36→37 | 2026-07-26T21:46:18.585Z → 21:46:28.608Z；`toolu_01PcjKpCh43ea95hpoivTyih` | 实际回执 `EXIT=0`、`BUILD SUCCESSFUL in 6 s 859 ms`。只认证该构建，不认证视觉。 |

另一个**不新增强制题目**的接受边界：L592 的 `priceSplitIndex` 把 `.` 当 numeric，且只把开头数字／点作为第一段；真实 Android `Regex("\\d+")` 匹配数字段。本底稿不把最终固定两 Span 当作所有字符串的精确语义复刻。如果调查者基于这两份原文提出小数点／非前缀数字等静态差异，应审查并接受有界发现；不能因为参考只写“分段修复”就拒绝新证据，也不应在冻结前临时增加必报的额外缺陷。

## 独立核过的 Splash 原始位置

| 完整源 basename／行 | 时间与 call_id | 原始依据 |
|---|---|---|
| `agent-aconv-splash-9d5902d803bbcde6.jsonl` L9 | 2026-07-24T01:56:39.240Z；`toolu_01HzaxtnGPqoBRGu77uek45v` | 写前页面 spec 返回“converter 必须实现”、`返回禁用 / SplashActivity / onBackPressed 空实现`。可证初版收到页面级返回禁用要求。 |
| `agent-aconv-splash-9d5902d803bbcde6.jsonl` L26 | 2026-07-24T01:56:54.615Z；`toolu_0128HxkRCFyGY236DdACkKeX` | 实际 Android 源 393–395 行：`override fun onBackPressed() { //启动页禁止关闭 }`。 |
| `agent-aconv-splash-9d5902d803bbcde6.jsonl` L71→72 | 2026-07-24T02:07:13.800Z → 02:07:13.860Z；`toolu_01Np1dfx5cY3fQ9uZrHBVkbq` | 初版 Write 的 build 根是 NavDestination，末尾 `.onBackPressed(() => true)`；成功创建。它是页面处理，不是初版已经存在的弹窗 onWillDismiss。 |
| `agent-aentry-setup-07108f5df45c357c.jsonl` L123→124 | 2026-07-24T02:32:52.166Z → 02:32:52.249Z；`toolu_013Nfm3n767E96Qvd74pqbfv` | Edit old 包含 `.onBackPressed(() => true)`，new 删除它并增加 Navigation 的 `.navDestination(this.pageMap)`、`.mode(NavigationMode.Stack)` 和 API 差异说明；成功更新。 |
| `agent-aslice11-startup-50a0622bcfe4a588.jsonl` L236→237 | 2026-07-24T16:00:31.136Z → 16:00:31.208Z；`toolu_01HK6amCmnLqbfQFefbryS7b` | 实際 new 创建 privacyDialogController，设置 `autoCancel:false, isModal:true`，注释称 isModal 吃返回；同时已有协议页跳转前关闭、onPop 重开路径。成功更新。 |
| `agent-a68daf720e780b4c2.jsonl` L346→347 | 2026-07-26T21:05:54.915Z → 21:05:58.983Z；`toolu_01DzVErQMcevEwF2f5T3E1U8` | 脚本新增 onWillDismiss 回调，只记录 reason、不调用 action.dismiss；修正 isModal/D-020 注释；同次补 Progress style。回执 `ok SplashPage` 并打印新增 handler 的源码位置。 |
| `agent-a68daf720e780b4c2.jsonl` L352→353 | 2026-07-26T21:06:31.863Z → 21:06:34.814Z；`toolu_01TRP8mc5pnikgvEnDDkDRuG` | 另一次脚本新增 `.onNavBarStateChange((isVisible) => { if (isVisible && this.vm.privacyDialogVisible) this.openPrivacyDialog() })`；回执 ok。是恢复 guard，不是前一关闭拦截的别名。 |

这里不要求调查者背出“无 result 的 pop 导致 onPop 不触发”：L352 的注释是“onPop **未必**触发”，不是独立 SDK 行为证明。代码的实际条件是 `isVisible && privacyDialogVisible`，并没有新增直接查询 stack.length 的语句。原因可表述为“加强从协议页返回后的恢复保障”，无需把未核定的 API 假设升级成真值。

同样，初版确实存在返回处理且源要求已交付，但没有本次限定证据证明它在后来的所有弹窗组合态下必然有效。也没有证明删除该行是最终白屏的唯一充分原因。该边界用来约束额外断言，不应要求每个合格答案逐句重复免责声明。

## 冻结建议

保留现有三个归因单元与主事实；澄清上述 A/B 后即可继续实验。不要为了旧清单的完整性增加必答 helper 名、每个精确数字、API 定论或重复未知声明。没有新的重大事实错误需要停跑；这次签核只覆盖上述三单元，不把它写成整个 F10-01/02 全字段独立认证。
