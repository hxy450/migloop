# V6 Member：四份工具组联合裁决

裁决对象：`formal-v6-document/member-center` 与 `formal-v6-reference/member-center` 的 tools rep1/rep2；均为原生 GPT-5.5 / medium，冻结源 `4d5db4f`。只读原文与已完成运行，不调用模型，不改冻结材料。裁决时间：2026-09-09 18:35:24 UTC。

结论：引用提交两次保住完整核查稿；document 两次最终文档均未绑定最后核查稿。核心语义没有稳定胜出：四份都答对三处 mask 的 1 透明＋2 深色、两轮价格修复及编译/视觉边界，但仅 reference rep1 交代 H5 例外，仅 document rep2/reference rep1 追到 Slice 8 的正确输入→错误整写。不能把更保守、引用齐全、basis 齐全或 mechanical_clear 当作准确率通过。

## 同一原文量尺

真值依据是冻结 `reference-v1/legacy-reference.json`（SHA256 `2c015536094fff1e42bb3b6b5cc2dce743c0f2a0f6924254027f7f8a5faac927`）和原始记录；55 条 locator 检查通过，实际 Member 池内 11 条相关记录 SHA 与冻结 witness 相符。旧 V5 报告、当前工具输出和 GUIDE 均不作 gold。

原文根目录：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/member-center/pool`。下表路径均相对此池；完整 SHA/运行路径/数值见同名 JSON。

| 核对事项 | 可复核原文 | 支持与限制 |
|---|---|---|
| 三处 mask | `ff019…/subagents/agent-a68daf720e780b4c2.jsonl` L81、L103–104、L106–107 | AppLoad@206→Transparent；PayAgreement@704、RenewRule@728→Palette。脚本先 write，再 report，成功返回报 3 sites，支持实际脚本写入，不只是意图；仅 PayAgreement 有相邻片段读回，不等于三个弹窗设备通过。 |
| H5 与最近重写 | `9b310…/subagents/agent-aslice8-pay-80bbb1f44b77da0f.jsonl` L264–265 | 原生整写已经包含 H5 Transparent；脚本跳过已有 mask 的块。不能把 3 sites 说成三个深色新增。 |
| 已有正确输入 | 同一 Slice 8 L21 请求、L24 返回；Kotlin 正文 276–282 行 | 数字段 replaceSpan/AbsoluteSizeSpan(30) 在 L264 整写之前实际返回；L264 仍把非动画 priceText 整串放入 30vp Text。 |
| 两轮价格修复 | fixer L528–529、L592–593 | 先 ForEach/splitPriceRuns，后固定 priceDigits/priceSuffix 两 Span。后一步新增 private helper；不能把中间态当最终态。 |
| 编译来源与验证 | `ff019…/subagents/agent-af0e3d2ae54dbf769.jsonl` L24、L32–37 | private access 原始错误→两次去 private Edit→EXIT=0/BUILD SUCCESSFUL。发现者是 builder，不是错误来源；构建不认证视觉。 |

四份实际 source/pool/task 均未变化；共同 task SHA `e60ad7491cd5991a948f8c7128432feca230a59bee208640ca5b90a44d68dec1`，pool digest `a78b1373045f7558d6da3b76123e30d032635a2a0b4cdd665e7f80c0bdf8b337`。

## 核心回答与完整标注分开

| 运行 | S3 核心 | S4 原实现归因 | 额外错误/限制 |
|---|---|---|---|
| document rep1 | 三值正确；漏 H5 | 只到 fixer 现状/finding；4 次 blame unknown 后未追 Slice 8 | mask 伪锚 v9→v10（v10 实为按钮修复）；尾后动作硬挂 v40，主通知硬挂 v43。 |
| document rep2 | 三值正确；漏 H5 | 找到 Slice 8 早期 Read 与 L264 整写，近因成立 | mask 伪宽锚 v7→v16；private 尾后动作仍挂 v40。正确保留 builder 读取就近绑 v14 的不确定性。 |
| reference rep1 | 三值及 H5 skip 完整 | 找到 Slice 8 输入/重写 | 额外把 conv-member 因沿用的 30vp 样式染红，依据不足；尾后动作仍刻意绑“最后已知 v40”。 |
| reference rep2 | 三值正确；漏 H5 | 1 次 blame unknown 后未追 Slice 8 | 把明确“不确定”的 v14 就近读取写成“在 v14 读到 helper”；尾后说明放在 v33 节点，版本级归因未完成。 |

reference rep1 的 conv-member 红点不能靠逐行 blame 证明：原 converter L61 将 priceText 注释为 rolling 数字（如 598），showBottom 单列 0.01/天；该报告自己的 counterevidence 也承认单个 30vp 样式不必然错。需另核初始输入及数据语义，不能因后来复用这行就补一个错误来源。

四份均核清两阶段价格修复和 private 编译来源，且没有把编译成功写成修后视觉通过。缺少早期输入追溯属于漏答；不因写了“无法确认最早作者”就当作完成因果调查。反之，记录支持实际脚本执行时，也不因未立正式版本就一律否认执行。

`#15731@L592` 的 V6 action 返回明确是尾槽 41、只有 40 个效应版本；不能把它自动吸附到 v40。builder 的 `#17287@L26` 返回明确写“v14 版本就近绑定（不确定）”；真实观测内容存在，不等于 formal v14 内容已获认证。

## 提交与 coverage

| 运行 | 原分母 | 最终交代 | 最后核查绑定 |
|---|---:|---|---|
| document rep1 | 7 版本＋31 候选 | 7 行，漏 31 候选；3 deferred | mismatch。核查稿有 38 行，最终删掉候选却声称完整核查/mechanical_clear。 |
| document rep2 | 同上 | 38 行；14 explained、17 deferred、7 not_repair | mismatch。唯一 check 为 needs_review（3 errors/1 warning），最终又改文档，未再匹配核查。 |
| reference rep1 | 同上 | 38 行；15 explained、23 deferred | matched，checked_draft_ref accepted。 |
| reference rep2 | 同上 | 38 行；17 explained、21 deferred | matched，checked_draft_ref accepted。 |

38 项不是 38 次修复。document rep2 的 7 个 not_repair 对应实际盘点、grep、import 检查，原文支持其非写入；不同于否定真实修复。两个 reference 均把已经用于 S4 的 price-finding 候选 `d292748…` 标 out_of_scope，理由是“不是单独写入”，仍混淆了“本题未调查”和“不是修复写”；应单独记这条标注限制。

合法节点、引用定位和显式写边只核坐标关系。不能把渲染器自动列出的 implicit adjacency 当作模型明确声明的假边；本报告也不以此给 UI 因果准确率打分。

## 成本观察

input 包含 cached input，二者不可再相加；output 已含 reported reasoning，不重复加。总 token = input + output，无价格估算。

| 运行 | input（其中 cached） | output | 总 token | 工具数 / 返回字数 | 运行 / 端到端秒 |
|---|---:|---:|---:|---:|---:|
| document rep1 | 1,572,921（1,452,544） | 23,472 | 1,596,393 | 47 / 165,980 | 481.76 / 494.80 |
| document rep2 | 3,219,866（2,995,200） | 24,103 | 3,243,969 | 80 / 470,252 | 523.82 / 537.07 |
| reference rep1 | 2,942,494（2,780,160） | 26,476 | 2,968,970 | 61 / 249,505 | 569.86 / 583.30 |
| reference rep2 | 861,314（749,568） | 20,069 | 881,383 | 49 / 165,721 | 418.26 / 431.13 |

两次均值：document 2,420,181 总 token；reference 1,925,176.5，观察少 **20.45%**。但 reference rep1 更贵、rep2 更便宜，组内波动大；输出 token 均值仅少约 2.17%，不能把全部差额归给短最终引用。这个 n=2 的 document/reference 比较不是 tools/raw 对照，也不足以证明稳定节省或准确率提升。

时间过滤：document rep1 为 0；document rep2 用 4 次 until_ts（包括归因前的表达式检索和后置验证窗口）；reference rep1 用 1 次生成 Write 之前的 until_ts，打开真实 Slice 8 Read；reference rep2 为 0。四份均未使用序号 until。找到更早输入的两份有实际 Read 原文支撑，不是仅凭搜索命中推断历史读取。

## 当前判断

已支持：引用提交能在这两次运行中保留原核查稿及完整清单。未支持：稳定的“少 20–30% 总 token＋更好原文准确率＋忠实 UI”联合验收。raw 两次须用同一量尺另裁，不能混入本文均值；V7 blame recovery 及其他后续修改未进入这些 V6 运行，本文不将其潜在收益计入。

