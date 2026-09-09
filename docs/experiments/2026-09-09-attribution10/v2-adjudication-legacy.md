# Formal v2 Member：S3 / S4 配对裁决

审计时间：2026-09-09 13:07 UTC。仅比较 `formal-v1/member-center/runs/tools/rep1` 与已结束的 `formal-v2/member-center/runs/tools/rep1`；未调用模型、修改源码、冻结参考或运行产物。路径基于 `C:/Users/hongy/projects/_migloop-eval-20260909/attribution10`。参照同一 `reference-v1/legacy-reference.json`，关键争点直接复核原始事件。[机器可读裁决](v2-adjudication-legacy.json)；[v1 裁决](formal-adjudication-legacy.md)。

结论：S4 的核心近因归属明显改善，S3 的假修复锚点和正常 entry 已消除；但 S3 对成功执行证据过度降级，coverage 至少四项错误地把“题外修复”标成 `not_repair`。因此是“核心归因有实质进步，完整标注仍不合格”，不是全项成功。

## 配对条件与限制

两轮问题均为 S3 / S4，使用同一实际池（v2 仍指向 `formal-v1/member-center/pool`）、同一 ledger、同一完整 common-task 和 prompt SHA；均为原生 MCP、gpt-5.5、medium。common-task SHA 为 `e60ad7491cd5991a948f8c7128432feca230a59bee208640ca5b90a44d68dec1`，pool digest 为 `a78b1373045f7558d6da3b76123e30d032635a2a0b4cdd665e7f80c0bdf8b337`。

模型面对的调查服务修改是 b197227→733c526 的通用 GUIDE：最近相关代码引入者、changed blame、后置验证窗口、entry / repair 自洽、YAML 块文本。未注入这些题的答案。提交还含 probe / viewer / 审计脚本及测试改动，不能简写成“整个提交只改一段提示词”；这些不构成新的原始调查证据。这里只是一对运行观察，不能将所有变化确定归因给某一句 GUIDE，也不能外推普遍胜率。

| 维度 | v1 | v2 | 裁决 |
|---|---|---|---|
| S3 三站点与值 | 1 透明＋2 暗色正确 | 站点、分支与值正确，但称仅“计划 / 推断” | 事实映射保持；执行结论过度保守 |
| S3 repair / entry | v9→v10 借时间窗；正常 fixer 在 entry | 省略无对应版本的 repair，entry=[] | 修正 |
| S4 最近引入者 | 只追初始 conv-member，漏 Slice8 | 打开 Slice8@v13 写入、@v1 输入和 Kotlin 原文 | 实质改善，核心通过 |
| S4 编译与行为 | 找到 private helper 错误，保留设备未知 | 保持正确，正常 builder 不再是 entry | 保持 / 改善 |
| S4 节点角色 | fixer@v45“带病传递”理由不自洽 | 同一问题仍在 | 未完全修正 |
| coverage | 22/22；题外版本 unresolved | 22/22，但至少 4 项真实题外修复 not_repair | 机械完整，语义退步 |

## S4：新增的是输入—实现证据，不只是多了一个作者名字

以下调用号按冻结 v2 `probe._transcript_calls` 的 primary transcript 顺序；L 为 v2 run 的 `transcript.jsonl` 物理行。

- #16 / #17 对 v11 / v15 调 `blame(changed=True)`，均明确返回“前一版或本版内容未知”。报告保留了这条边界，没有把未知端点拼成确定逐行继承。
- #29，L158，`call_bs8RdGTwb3LiasDi1okfI08W`，按修复前表达式搜目标文件，返回已知 v7 的精确旧代码和 `slice8-pay@v13` 写者。搜索首次命中不证明历史绝对首次出现；后续必须核写入及输入。
- #31，L172，`call_2LsbESbjvkbFxHCZ0lfLEz2S`，实际打开 file@v7 第 1135–1159 行，含整个价格字符串 `.fontSize(30)`。
- #33 / #34，L186 / L193，打开 Slice8@v13 的写入记录与 @v1 的早期实际输入；#36，L205，`call_mRWuykqREGq6ovQ9v2DmGmOH`，展开 `#20509` 的原始 Read 结果，确实包含 Kotlin `showNowPrice.replaceSpan(Regex("\\d+")) { AbsoluteSizeSpan(30, true) }`。片段够回答本题，未展开其余 2 万字符不是证据不足。

冻结原文 `formal-v1/member-center/pool/9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aslice8-pay-80bbb1f44b77da0f.jsonl` L24 / L264 仍是输入先于全量写入的直接证据。相较 v1 只查最初创建者，这确实补上了近因。后续两阶段价格改法、private helper 编译错误、去 private 与成功构建也保持正确。不能认证所有价格格式或修后设备视觉，报告没有这样扩大。

剩余角色问题：fixer@v45 仍标“带病传递”，但 reason 说它“修正原字号语义”，并以后来 ForEach 改固定 Span 为理由。仅后续再次改写不证明中间态保留了哪项上游缺陷。应核清具体缺陷后再标传递，不能把“后来又改过”当作带病证据。S4 的两处 entry 现为 Slice8@v13 / final fixer@v53，不再夹正常 builder，这是独立的改善。

## S3：不造版本正确，但“未立版本”不是执行证据不存在

v2 已正确省略 mask 的 repair 字段，不再用 v9→v10 假装此脚本的状态差异，也将 entry 留空。三站点与值仍对：AppLoadDialog→`Color.Transparent`；PayAgreementDialog / RenewRuleDialog→`Palette.DIALOG_MASK`。对独立读回只覆盖 PayAgreement、未见三处设备复测的区分值得保留；H5 已透明且被跳过仍未明确点名。

问题在“因账本未立目标文件版本，不能单独确认三处都实际落盘”的推理。调用 #9，L71，`call_ZnFiLqUZqGXL8ds9hdzXSngB` 已返回完整 Bash 输入和成功工具结果，包含：

```python
open(path,'w').write(new)
report.append((path, len(edits), need_palette and 'DesignTokens' not in src))
# 报告循环在全部写操作之后输出
```

输出明确 `3 sites import=+ entry/src/main/ets/pages/MemberCenterPage.ets`。原始 fixer L103 / L104 的 cwd 是 `/Users/chenjiamin/arkTs/arkts_pilot_project/aippt_version/aippt_0723`，工具 ID `toolu_01T6WkXMhD7rUsHaSaMPuhgx` 前后一致，`is_error=false`、`stderr=""`、`interrupted=false`；与本题完整路径相符。这不是单纯 say / 修复总结，也不是还没执行的脚本计划。

可以据此表述“成功工具执行记录支持脚本对该目标完成三处写入，按已核分支一透明两暗色；完整文件状态未复原，仅一处独立读回，修后设备表现未知”。这不要求给未登记动作造 file@v，也不把输出提升为独立读回 / 视觉验证。若将系统候选标签反过来否定已经展开的更强执行证据，就把解析器覆盖限制错当成原始证据上限。S3 因此是站点/数值核心保持、执行事实结论不足，不宜以“保守”概括为完全正确。

## 覆盖标注：至少四项违反共同任务要求

两轮 byte-identical common-task 明确：“题目范围外的版本/候选可简记 unresolved 并注明本题未调查，不可为省事认定 not_repair。”v2 却写了：

| 条目 | v2 reason 的实质 | 为什么不能 not_repair |
|---|---|---|
| Member@v10 | 底部按钮宽高 / 边距；本题未展开 | 未调查或题外，不是已证实非修复 |
| Member@v13 | Swiper indicator 颜色 / 位置“修复”，不属 S3/S4 | 理由自身承认修复 |
| Member@v14 | banner indicator 常量 / 注释“修复”，不属 S3/S4 | 同上 |
| `candidate:87dd5a4b1ea9aaf30258` | 已展开 #23624，补两张会员页图片尺寸 / 比例 | 是对同一目标的实际题外修复，不是非执行或其他目标 |

图像项的原始 fixer L233 命令先 `open(path,'w').write(...)` 后打印 `ok`，L234 输出两次 `ok entry/src/main/ets/pages/MemberCenterPage.ets`。v2 调用 #10（L73，`call_mjtXOhZAwlDdI0ncBu63iZM8`）已经返回这份证据，不是审计者要求模型追未打开材料。最低改法是这四项 `unresolved`、注明本题范围外；不要求为了给 coverage 找 defect 而扩写全部题外修复。

其余十个 not_repair 中，前三个已展开的只读扫描有不同的依据，不能因上述四项错误就全判错。报告 / git-status 类等其他候选不在本次扩大审查范围；“至少四项”是已核下界。GUIDE 示例里的“核清无关”存在范围理解风险，但 common-task 已明确禁止按题外归 not_repair，不能据此替报告豁免。

机械指标仍必须保留 `schema=true, coverage_complete=true, accounted=22/22, unresolved=5, not_repair=10`。它说明逐项填写，不证明 status 语义正确；unresolved 从 9 降到 5 也不能当作四个未知已被查清。

## 成本与效率：观察到的变化并不一致

| 指标 | v1 | v2 | 变化 |
|---|---:|---:|---:|
| wall 秒 | 324.45 | 341.34 | +5.2% |
| MCP 调用 / 拒绝 | 55 / 0 | 53 / 4 | 少 2 次调用，多 4 次拒绝 |
| leaf 返回字符 | 238,198 | 200,620 | −15.8% |
| input 总量 | 1,723,544 | 1,937,108 | +12.4% |
| 其中 cached | 1,595,904 | 1,821,184 | 已包含于 input |
| uncached input | 127,640 | 115,924 | −9.2% |
| output | 13,948 | 12,748 | −8.6% |

四次拒绝分别为两次非首跳 `via=sessions`、一次把 file search receipt 用于 agent 目标、一次 agent ID 不存在，随后均有替代查询推进。返回字符下降不等于累计 input 下降，也不保证总耗时缩短。美元 cost 为 null，cached 不再加到 input，reasoning 不再加到 output；不据单次配对宣称普遍成本优势。

最终判断：S4 回答所缺的核心归因证据已补；S3 锚点/entry 改善但成功执行事实被过度削弱；coverage 仍有明确违规。后续若做实验，应预先分别记录核心回答、角色/锚点、执行证据等级和覆盖语义，不能只看 schema/complete 或节点深度。
