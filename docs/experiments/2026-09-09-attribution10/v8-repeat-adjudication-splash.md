# V8 Splash rep2：主链补齐，精确归因与引用仍退化

按既有核心标准，**S1 core=pass、S2 core=pass**；固定事实 **6 supported、1 partial**。这次确实打开首稿漏掉的两段脚本和成功回执，不能把局部“写入意图”四字变成新词表门槛。但有 **2 项 material 错误标注**，`annotation_requires_correction=true`：完整、可审计的归因仍不通过，不能凭 core pass 宣布全正确。

实际 GPT-5.5 / medium / native，冻结源 `b540cb2`，2026-09-09 20:33:31 UTC 完成；同题、同冻结原池/reference-v1。未修改源码、旧运行、参考或访问 holdout。完整逐项原句与定位见 [JSON](v8-repeat-adjudication-splash.json)。

## 固定事实和主链

| 原事实 | rep2 | 判断依据 |
|---|---|---|
| S1.f1 初版已有返回要求及 callback | supported | 实际开 v1 正文、converter 输入、Android onBackPressed、F001。正确说明初版有 NavDestination 拦截，不把它说成设备认证。 |
| S1.f2 entry-setup 删除，D020 后续接受外壳差异 | supported | 第3次 file 返回真实 entry-setup v7 / file v6 删除 diff；最后明确 entry-setup 改宿主/API环境。结合初版→v6叙述已指出装配变化，不强制再出现“删除”这个字，也不混成 Slice11 动作。 |
| S1.f3 Slice11 错信 isModal，finding 反驳，追加 onWillDismiss | supported | 后文明确“v52/v候选修复分别覆盖…重开和 dismiss 拦截”；两脚本输入/成功输出实际打开，不再像首稿只知正式复位兜底。精确 agent@v38 错绑另列。 |
| S1.f4 后置另一 builder 成功 | supported | 实际打开 builder 的完成通知，记录 PASS，未声称行为复测。独立原生 L36/L37 支持构建事实；通知仍是来源报告而不是 stdout。 |
| S2.f1 生成前主会话原始 theme 回执已有 windowFullscreen | partial | 打开早期 AIPPT_design v1 和前身 Write，足以支持核心“早已有”；但没有追 root L404 原始主会话读取，细项不满。 |
| S2.f2 概括性生成输入与细节传递未完全证明 | supported | 实际开 converter/meta/source/F001，另有生成前 until_ts 搜索；boundary 限定未确认传入具体主题，不把零命中作绝对不存在。 |
| S2.f3 入页隐藏＋离页/跳转恢复 | supported | L485 输入/输出及 L488 Edit 都打开，最终说明候选 helper 隐藏/恢复和正式 onRoute 还原；没有把未知最终设备行为说成通过。 |

这是按完整段落的语义判定，不按必须复述某个词或必须引用同一条 locator。相比首稿，决定性原文确已查到，关键改法也进入结论；这份提高应保留。与此同时，下面的精确事件错误不能被事实命中冲抵。

## 两段脚本：这次是真正打开了

原始 fixer 转录 `ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-a68daf720e780b4c2.jsonl`：

- **L346/L347**：脚本加入 onWillDismiss、修正 isModal/D020 说明；`open(p,'w').write(s)` 后才打印 `ok SplashPage`，同 ID grep 读回新增 hilog 行。调查第58/59次调用完整展开输入/输出，保存在本次 transcript **L283/L295**。
- **L485/L486**：脚本加入 window import、aboutToAppear(false)、aboutToDisappear(true)、setSystemBarsVisible helper，写后输出 `ok`；下一条 L488 才另加 onRoute(true)。调查第29/32次展开输入/输出，位于 **L147/L172**。

脚本不是正式独立版本，不等于没发生写入。最终局部称“修复意图/写入意图”偏弱，应明确记录中的实际执行与未知最终持久/设备状态；但 notes 同时称“候选修复分别覆盖…dismiss拦截”及“补成…隐藏/恢复”，没有直接否认执行。故不因缺“实际执行”固定短语再判 mandatory 未调查。

早期主题方面，AIPPT_design@v1 在 **07-23 13:02** 已记录 windowFullscreen=true、透明 status/navigation bar；第50/51次打开设计片段及其前身 Write。比生成时间早，需求并非 round-1 新增这一核心有据。原始 root L404 的更早 **12:36** 回执仍没查，按原 facts 留 partial，不悄悄加成满项。

## 两项明确实质错误，必须修正

### 1. 正确 actor/决策挂错到无关 agent@v38

最终 S1 entry 和红节点为 `agent-aslice11-startup-50a0622bcfe4a588@v38`，reason：

> “Slice 11 接入隐私弹窗时只配置 autoCancel:false、isModal:true，并在 D-020 注释中认定隐私弹窗会吃 BACK”

原始 **Slice11 L342/L343** 的 v38 实际是给 **F001ViewModel.ets 添加 DBPPTFactory import**，ID `toolu_01SGxtvNEPX7YfdSJW9eSi7P`。控制器/首次错误 isModal 解释在 **L236：agent v22 / file v38**；D020 重申在 **L250：agent v26 / file v42**。本次 agent 返回 L102 已明确这些不同版本。

这里判为 `material node_attribution_error`：reason 讲的是正确 Slice11 阶段/actor，没有直接写“v38 的 DBPPT import 动作引入 isModal”，所以不把它重新加工成核心相反事实；但**红色进入坐标仍是错的**，不是可以忽略的显示问题。累计查询锚点不能充当错误进入效应。

初 check 还曾把 v38→file v45 声明为写边，被告知真实写者是 v37 后改正。改一条边没有纠正仍留在 entry 的 v38。完整归因不通过，UI 必须显示这是模型错误坐标，不代为挪到正确版本。

### 2. 生命周期 grep 被误说成 Android 主题复核

`candidate:b60465cde470e4475666` 的原文是 fixer **L481/L482**，ID `toolu_01HS1zwyoVKWev6p7ApLxPqi`：grep **SplashPage.ets 的 lifecycle、window import、onRoute/vm.navigated**，没有查 AndroidManifest/themes，也没有 windowFullscreen 返回。

最终 coverage 却标 explained 并称：

> “S2 Android 主题复核候选，确认 Manifest/themes.xml 中 Launch 主题与 windowFullscreen。”

这是错误证据适配，不是 minor 遗漏。真正 Android 查询是另两调用 L476/L478；模型实际打开它们，不代表这条候选可以冒充它们。须保留 `extra_false_claims`，不得因 candidate ID 有效就认证其语义。

另有未充分支持的表述：expected 将 Android 要求说成“状态栏/导航栏都不显示”；已有主题原文只给 windowFullscreen 和导航栏透明，透明本身不证明导航栏必须隐藏。实际 fixer helper 隐藏二者是代码事实，不自动证明二者都是原 Android 强制要求。此处作为需补依据的范围问题，不再计作第三条已证假事件。

## 五轮 check 没补查证据，却削弱了引用

66次调用，31次 action 均用完整 ref 且成功；6次 agent 中4次成功；3次 via 拒绝。10次 search 带 until_ts，其中2次限定生成方写前；没有 seq-only until。

最后一条来源查询输出在 **20:21:55.463**；之后至结束约 **696秒**，没有再查原始证据，只读 GUIDE、生成/改写草稿和 check。

| check步骤 | 原始返回 | 不同原文引用数 |
|---|---|---:|
| 61 | 3 errors、5 warnings | 41 |
| 62 | 201 schema errors，161项未展开 | 17 |
| 64 | 47 errors、14 warnings，21项未展开 | 39 |
| 65 | 4 errors、2 warnings | 5 |
| 66 | 0 errors、2 warnings | 4 |

第二个文档没有有效 canonical hash，因此 metrics 将该次标 unverifiable；其真实工具返回仍明确为201个 schema 错误。不能把 unverifiable 改说成它从未返回，也不能视为核过有效文档。

最终 matched，仅说明与最后受检正文相同；仍是 needs_review，不是 clear。两个 warning 是 converter L86 收尾报告晚于 v1及其窗口，报告可以转述旧工作但不是 v1 当时事件。这些边界与模型原因真假分开。

最终只剩4个不同原文引用，均真实。**27个候选的 evidence 全为空**，其中6项标 explained。候选 ID 仍可通过 manifest 找到原文，因此不是彻底不可追溯；但最后删除脚本/finding/build的具体引用，明显削弱了论断与原文的连接。29/29＝2正式版本＋27候选，8 explained、21 out_of_scope、0 not_repair，不代表29个修复或29项归因正确。

## 与首稿及原始组并列

| 项目 | tools rep1 | tools rep2 |
|---|---:|---:|
| 核心 S1/S2 | partial / partial | pass / pass |
| 原facts细项 | 4 supported / 3 partial | 6 supported / 1 partial |
| 两脚本输入＋回执打开 | 0 | 2 |
| 完整标注 | 需修正 | 需修正，至少2项实质错误 |
| Input（含 cached） | 1,972,612 | 3,908,727 |
| 其中 cached | 1,778,688 | 3,612,672 |
| Output（含 reasoning） | 19,706 | 40,473 |
| Input + Output | 1,992,318 | 3,949,200 |
| 运行秒 | 418.639 | 924.751 |

两次总 token 均值 **2,970,759**，相对 raw 两次均值 3,305,569.5 仅减少 **10.1%**；运行均值 **671.695秒**，反而增加 **38.6%**。rep2 单次比 raw 均值贵19.5%。cached/reasoning均已计入，不重复相加。

更长时间确实伴随更多关键原文查询，但不能因此给分；给分依据是实际打开与最终主链内容。同时错误进入坐标、错适配候选、引用削减都保留。成本均值未达20–30%节省、完整归因未过，联合验收仍不成立。
