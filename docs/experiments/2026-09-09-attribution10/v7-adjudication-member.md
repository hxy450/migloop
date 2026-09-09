# V7 Member 独立裁决：两次重复，不合并成一次成功

两份均为 **5 supported + 1 partial / 6 原始事实**，共同遗漏“Slice8 在整文件重写前已收到正确 Kotlin 逻辑”。两份都另有重大版本/时间归因错误，因此不能把 10/12 完整事实行称为整体准确率，也不能称完整任务成功。rep2 不替代 rep1。

冻结源 `84bfcf8`；实际 GPT-5.5 / medium / native，reference 提交。rep1 完成于 2026-09-09 18:47:56 UTC，rep2 于 18:52:44 UTC。只读原始证据与已完成结果，没有模型调用、修改/重绑冻结报告或读取 holdout。逐项原句、定位与诊断保存在 [JSON](v7-adjudication-member.json)。

## 量尺与原始证据

使用冻结 `reference-v1/legacy-reference.json` 的 S3/S4 原始 `facts`，不以工具输出、旧报告、GUIDE、basis 或 check 为真值。参考 SHA256 为 `2c015536094fff1e42bb3b6b5cc2dce743c0f2a0f6924254027f7f8a5faac927`。每个原始事实独立标 supported / partial / omitted / contradicted；partial 不算完整命中。读取整个提交，coverage 中写明的事实也计入。

原始池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/member-center/pool`。下文原始行号均为 JSONL 物理行，不是代码行：

| 简称 | 池内原始转录 |
|---|---|
| fixer | `ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-a68daf720e780b4c2.jsonl` |
| Slice8 | `9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aslice8-pay-80bbb1f44b77da0f.jsonl` |
| builder | `ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-af0e3d2ae54dbf769.jsonl` |

| 原始事实 | rep1 | rep2 | 核心原文与报告断言 |
|---|---|---|---|
| S3.f1 三个待补站点是 AppLoad、PayAgreement、RenewRule | supported | supported | fixer L80/L81 直接列 builder；两稿都点名三者，rep2 还列 206/704/728。 |
| S3.f2 跳过已有 mask；AppLoad 补透明，其余缺失项补 Palette | supported | supported | fixer L103/L104 的实际脚本与同 ID 成功输出；两稿均写“缺 maskColor”的分支和值。 |
| S3.f3 3 sites 是总数；H5 已透明、没有算入本次补写 | supported | supported | 两稿 coverage 都明确 H5/h5PayDialog 已有 Color.Transparent，结合只补缺失和列出的三站点，已交代跳过 H5。不能只读摘要判遗漏。fixer L74/L75、Slice8 L264 支持既有透明。 |
| S4.f1 Slice8 已读正确 Kotlin，重写仍把非滚动数字/后缀统一 30vp | partial | partial | 两稿读到 file v7 的单个 30vp Text；没有找到 Slice8 写前 Kotlin Read。rep1“未绑定 slice8-pay 的完整 agent id，entry 留空”；rep2“Android 源码行本身未在本轮工具输出中展开”。 |
| S4.f2 先 ForEach 片段迭代，后固定 priceDigits/priceSuffix 两 Span | supported | supported | fixer L528/L529、L592/L593；两稿均说明两阶段和数字 30 / 非数字或后缀 16，未把中间态当最终态。 |
| S4.f3 visual fixer 新增 private helper，兄弟组件调用报错，builder 两次 Edit 后构建成功 | supported | supported | fixer L592/L593，builder L23/L24、L32–35、L36/L37、L39/L40。两稿均将新问题归于修复阶段，不怪初始生成者或发现者；没有把构建通过升级为视觉/所有价格格式通过。 |

关键证据强度不能混同：

- mask 脚本 L103 先执行 `open(path,'w').write(new)`，再 `report.append`，最后输出报告。L104 同一 native ID `toolu_01T6WkXMhD7rUsHaSaMPuhgx` 成功返回目标路径 `3 sites import=+`。这是实际执行证据，强于普通自述；L106/L107 另有 PayAgreement 写后读回。rep1 将它与报告一并称为“自述”偏保守，但其三站点/规则事实仍正确。两稿对最终 v16 全文和设备复验保持未知是合理边界，不因此额外加分。
- Slice8 L21 的 native Read 在 07-24 15:33:49.105 发起，L24 于 15:33:51.671 返回 Kotlin 276–282 行 `showNowPrice.replaceSpan` / `AbsoluteSizeSpan(30,true)`。整文件 Write L264 在 16:04:37.440 发起，L265 成功返回。真实“先读到、后未落实”在本池内可证，不是合理未知。
- builder L37 是实际第二次构建 `EXIT=0 / BUILD SUCCESSFUL`；L40 是 build2.log 中 CompileArkTS/PackageHap/SignHap 完成及 HAP 输出。rep1 实际展开后者，rep2 两者都展开；不只是最终 summary 的 PASS 主张。

## 额外归因与标注问题

### rep1

1. **尾后动作错挂红节点。** S4_COMPILE 将 `#15731@L592` 作为 fixer@v40 的“进入·错”。实际返回（rep1 transcript L167）明示“喂养槽 41；已记录 40 个效应版本，无可导航版本”。actor-level 的 private 引入归因正确，不代表可把动作倒挂到 v40。
2. **后来 finding 被当作当时输入。** file@v7 的 basis.expected 写“当时适用要求来自 visual finding”，引用 fixer L501。该 finding 读回在 07-26，而 v7 写于 07-24。后来发现可用来诊断代码，不能证明它是生成时输入；真正早期输入是未查询的 Slice8 L21/L24。
3. **已使用的价格证据被错称题外。** coverage 的 `candidate:d292748943711b74a369` 写“banner indicator 报告读取，与本题价格/mask 无关”。原始 L501/L502 同时包含 product-price-suffix finding；模型已在第 48 次调用展开，且用同一引用作 S4 basis。这不是单纯合法的“本题未调查”。
4. S3 repair 选 v9→v16 是宽泛历史窗口，不能当精确 mask before/after 快照；v16 实际去掉 priceSuffix 的 private。报告已声明候选写不是正式版本边、最终内容未知，须保留这个缓解边界。

### rep2

1. **把真实但版本绑定不确定的读升级成 v14 内容。** 报告写“build-verify-r1 读取到 v14 时…”及“v14 引入/保留最终价格 helper”，将 v14 标红并在 coverage 算价格/编译修复。实际返回（rep2 transcript L207）明确 `v14 [1100–1239行 版本就近绑定(不确定)]`。原始 fixer L532/L533 的 v14 只在 21:24:34 加 banner 常量；priceDigits 脚本 L592 在 21:30:17 才发生。后来的真实观察不能变成更早正式版本的快照。
2. 不再给 fixer@v40 标红，但将尾后第二轮修复写在 fixer@v33 的理由下，并声明到 file@v14 的候选边。第一轮 v11/v12 的 v33 写边正确；尾后动作没有因此获得正式节点坐标。
3. file@v7 的 expected basis 同样使用 07-26 的 A02 finding（fill.py / manifest）说明“当时 finding 要求”，没有查 07-24 输入。它承认没有直接展开 Android 原文，未把 finding 的三级字号估算当作独立设备验证。
4. L501 这次正确归为价格证据；但 L615 混合 attempt 被概括为“立即开通按钮尝试记录候选，本题未调查”。L615 实际也有价格修复及将估计比例纠正为 16/30/16 的说明。**out_of_scope 本身允许未调查，不判非法或虚假**；这里只记录索引说明不完整、相关反证未查，强度低于 rep1 对已用证据的自相矛盾。
5. 同一 S3 fixer@v5 同时声明“正常/无法确认”，以及两条候选边的版本关系未确认，已被原 check 提醒，未被审核者忽略。

两份均没有把 v10、v13、图片脚本等题外真实修改称为 not_repair。rep1 v14 正确题外；rep2 错误地将它纳入价格修复。38 个分母是 7 正式版本 + 31 待核候选，不是 38 个真实修复。

## 实际调查路线与协议

两份均 **blame=0、agent=0**，没有调用 recovery，也没有打开 Slice8 原始 Read/Write 动作。因此不能说新 recovery 帮助发现早期 Kotlin 输入。

- rep1：maskColor search 第 15 次调用 → receipt 打开 file v7 第 23 次（780–804 行），第 30 次再读价格区。第一份 check 指出猜出的 `agent-80bbb1f44b77da0f@v12` 不存在；下一次直接删 entry，没有解析真实 `agent-aslice8-pay-80bbb1f44b77da0f`。文件正文/写者脊柱已暴露 human label 与转录 tag，但未给可直接调用的真实 id；这是观察到的接口问题，不推断模型私有原因。
- rep2：同样通过 maskColor receipt，第 21 次打开 file v7 价格区，没有继续上游。16 次带 until_ts 的 search 全从 07-26 开始，范围不含 Slice8 07-24 的输入；这不是在正确生成窗口内查无证据。
- 两份均无 seq-only until；rep1 的 3 次 until_ts 用于后续验证窗口，rep2 有 16 次。不能把“用了时间参数”当作核过生成前输入。
- rep1 最终 matched，最后 check mechanical_clear；rep2 matched，但 check needs_review（0 errors / 3 warnings：两条候选关系、同节点角色冲突）。两份 semantic_checked 都是 false。
- 两份 coverage 38/38；rep1 19 explained / 19 out_of_scope，rep2 20 / 18；missing、not_repair 都为 0。结构完整没有验证每个 reason 属实。

## 观察成本与诊断停止边界

运行目录均位于 `C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v7/member-center/runs/tools/repN`。每份保存的 verdict.yaml SHA 与 matched draft 一致：rep1 `999a69648fc6873d561817e1f0b6084119d80cb81678b783d37b754fef2dafd5`；rep2 `e92ad82e20daf3007aa6188f3e68e2e9fb2f7d530e8a8d2cd9fae076883d0644`。

| 指标 | rep1 | rep2 | 均值 |
|---|---:|---:|---:|
| Input（已含 cached） | 1,256,613 | 1,402,118 | 1,329,365.5 |
| 其中 cached | 1,123,328 | 1,251,840 | 1,187,584 |
| Output（已含 reasoning） | 22,173 | 18,350 | 20,261.5 |
| Input + Output | 1,278,786 | 1,420,468 | 1,349,627 |
| 工具调用 | 56 | 74 | 65 |
| 工具返回字符 | 195,754 | 215,300 | 205,527 |
| 模型运行秒 | 458.359 | 404.237 | 431.298 |
| 端到端秒 | 471.846 | 417.722 | 444.784 |

cached 不再加到 input；reasoning 不再加到 output。这里是同一文件两个重复的观察值，不宣称稳定 20–30% 节省或准确率胜出，也没有单独完成 UI 忠实性验收。与 raw、V6 的跨组比较应由总实验报告按同任务/池及全部样本计算，不能挑较便宜的一次替换另一次。

V7 在 Member/C4 四次计划诊断后停止扩大，理由是已定位到可调用 id/引用接口和 UI 绑定问题，而不是继续消耗完整套次后才下结论。本文件只裁决 Member。下一版 action(ref)、真实 id 及 UI 修正不属于冻结 `84bfcf8`，不得倒算进 V7 的语义或成本收益。

