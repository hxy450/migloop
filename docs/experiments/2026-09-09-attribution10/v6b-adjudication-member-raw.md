# V6B Member：两次 raw 裁决及同题对照

对象：`formal-v6-document/member-center/runs/raw/rep1`、`rep2`。两次均为 GPT-5.5 / medium，source `4d5db4f`、同一冻结池与中性题目，完整性检查均未变化。裁决时间：2026-09-09 18:42:33 UTC。

量尺、原始文件及证据锚点沿用 [四份工具组裁决](v6-adjudication-member.md)。评审者已看过工具组报告，因此不是盲评；但原文 oracle 在输出裁决前已重核，不以工具摘要/旧报告作 gold，也不因保守或少写就判准确。

## 两次 raw 的语义结果

| 项目 | raw rep1 | raw rep2 |
|---|---|---|
| S3 三站点与 1 透明＋2 深色 | 正确，引用同调用 3 sites 返回 | 正确；更多依赖规则和收尾自述，未引用现成 L104 执行汇总 |
| H5 既有透明例外 | 明确 H5 已透明，不归本轮 | 正确排除已有 786 行透明，但未点名 H5；部分完成 |
| S4 最近生成输入→错误写入 | 缺 Slice 8 L21/24→L264/265 | 同样缺失；只引后期 fixer 记录的 Android 规则 |
| ForEach→固定双 Span 两阶段 | 漏第一轮 ForEach，只讲双 Span 与编译修复 | 两阶段齐全，引用 L528、L592–593 |
| fixer 引入 private；builder 修复 | 正确，含两次 Edit 与直接构建返回 | 正确；最终 PASS 引用主要落在 builder 收尾报告 |
| 修后设备/像素验证 | 未冒称通过 | 未冒称通过 |

raw rep1 的“原实现”主要由修复后源码注释描述，加上更早 converter 的自述；这不足以完成 Slice 8 的实际输入/责任链。raw rep2 虽然还找了 A02 finding 和原始 UI 文本，但仍未把正确 Kotlin 输入在生成之前已返回这一事实接到 Slice 8 整写。两者均按同一量尺记漏答，不因“不另读原工程”而放宽：需要的 Kotlin 原文已经在允许读取的冻结转录内。

S3 的实际脚本执行与最终状态分开：原始 fixer L103 中 write 在 report 之前，L104 同 ID 成功返回 3 sites；它支持实际写入，不只意图。L107 只读回 PayAgreement；另两处的最终片段/设备结果缺失，不抹掉已有执行证据，也不据此宣称全站点最终视觉已验证。

## 引用真实性不等于证据适配

两次列出的唯一原始记录分别核了 19 / 23 个，携带的 native tool ID 分别核了 13 / 16 个，均存在且配对匹配；这只是定位检查。

发现一条明确的语义错引：raw rep1 用 fixer `agent-a68daf720e780b4c2.jsonl:L605` 支撑双 Span 价格修复 attempt。原始 L605 是 tab 背景与 mask attempts（`/tmp/att3.json`），没有价格修复内容。它另引的 builder L29 确实含双 Span 源码，所以不能把整项事实判假，但 L605 不能作为该项证据。

raw rep2 引的 L615 不同：该长脚本确实包含 `ALIGN_PMemberCenterActivitiy_font_mismatch_product-price-suffix` 的 attempt、Android 规则与双 Span 说明，因此引用适配；它仍是 fixer 主张，不是 Slice 8 当时读过源码的证明。额外核了 A02 L391–392 的 finding 列表/汇总，以及 walker L347 返回中四种价格文本，均有原文；不把这些材料升级为修后视觉验证。

## 成本与工具组比较

总 token = input + output；cached 包含在 input，reasoning 包含在 output。返回字符与最终答复长度不等于 LLM token，不用字符比值冒充成本收益。

| 运行 | input（含 cached） | output | 总 token | 工具数 / 返回字符 | 运行 / 端到端秒 |
|---|---:|---:|---:|---:|---:|
| raw rep1 | 2,311,821（1,960,960） | 14,315 | 2,326,136 | 29 / 8,192,610 | 431.00 / 442.45 |
| raw rep2 | 3,039,282（2,730,496） | 16,702 | 3,055,984 | 34 / 8,578,838 | 493.26 / 505.11 |

| 两次均值 | 总 input＋output | 相对 raw 观察减少 |
|---|---:|---:|
| raw | 2,691,060 | — |
| tools document | 2,420,181 | 10.07% |
| tools reference | 1,925,176.5 | 28.46% |

reference 均值的 token 观察降幅落在 20–30% 目标区间；但不是稳定性或统计显著性证明，也不是联合验收通过。reference rep1 更贵、rep2 更便宜；其平均 output 为 23,272.5，反而高于 raw 的 15,508.5。reference 平均运行 494.06 秒，raw 462.13 秒；本样本未显示耗时收益。

## 是否已经“更准且忠实”？

尚不能宣布。

- 原文归因：raw 两次均缺 Slice 8 链；reference 只一次补齐，另一次又遗漏。reference 两次都交代两阶段修复，较 raw rep1 完整，但 rep1 又出现依据不足的 converter 红点，rep2 丢失 v14 读取不确定性。不能只挑好的一次或只数正确句子。
- S3：raw rep1 的 H5 例外完整，raw rep2 至少明确排除既有透明；工具 reference 也仅一次点名 H5。没有一致的 S3 优势。
- 提交保真：reference 两次完整保留核查稿并 matched，是可观察的协议收益；不等于因果主张属实。raw 不受相同 coverage/schema 输出义务约束，不把 raw 没有这类标注计为错误。
- UI：本文未做浏览器视觉验证。工具组尾部动作错挂已有 agent 版本、把就近读当确定版等问题须由图忠实呈现其声明和证据边界，不能为“更准”分数藏掉。

这份对照保留全部六次结果，不替换不利重复。后续 V7 的 recovery/短 GUIDE 没有进入 V6，不把未测改动收益记在本轮。

