# 弱模型工具试跑：查询性能审计

本报告仅审计工具调用开销、范围和重复文本，不调查会话根因、不评判归因准确率，也不作为 tools 与 raw 原始组的对照结论。未调用任何模型，未修改试跑产物或源码。

样本：`_migloop-eval-20260909/v1/dice-entry/runs/tools/rep1`，冻结源码 `1ccefe5`，实际模型 `gpt-5.6-sol`、effort `medium`。审计开始时仍在运行；本文已补齐最终指标：2026-09-09 06:18:47.265548 UTC 开始，06:30:14.825694 UTC 完成，墙钟 687.574 秒。pool/source/task 的运行后完整性检查均通过。

计算来源是原生 `events.jsonl` 的 MCP `item.started/item.completed`，按 item ID 配对，按首次出现顺序编号为下文的“查询 #N”。这不是账本 action 的 `seq`。06:31:38 UTC 读取的完整 events 为 772,998 字节、164 行，SHA-256 `96c1963cd9c86913ed86663c7ad2785d8706bbe8e3c5feeaffec4a143738d32a`。字符数按工具字符串结果解包后 `len(str)`，与最终 metrics 的 leaf MCP 合计一致；不是 token 数。41 个 wrapper 调用单独记录，不重复计入 77 个 leaf 查询。

## 最终量尺

| 工具 | 调用数 | 返回字符 | 占比 |
|---|---:|---:|---:|
| file | 13 | 121,150 | 44.32% |
| action | 12 | 64,048 | 23.43% |
| agent | 10 | 58,308 | 21.33% |
| search | 16 | 11,055 | 4.04% |
| diff | 9 | 7,695 | 2.81% |
| guide | 1 | 7,382 | 2.70% |
| sessions | 1 | 1,750 | 0.64% |
| blame | 8 | 1,255 | 0.46% |
| index | 7 | 737 | 0.27% |
| 合计 | 77 | 273,380 | 100% |

失败、拒绝、未返回均为 0。最终 metrics：总 input 3,124,627，其中 cache read 2,981,248、未缓存 input 143,379；output 17,649。thinking 5,908 已包含在 output 中，不重复相加。美元费用未报告，保留 unknown，不估价。

## 重复与新信息

完全相同的工具名和 JSON 参数调用：0 组；忽略 `sid/via` 后仍为 0 组。没有证据把本次成本主要归因于机械重试。

13 次 `file` 全部主动指定 `content=true, readers=true`：10 次没有行窗口、3 次有 `start/n`；没有纯索引 file 查询，同一 file@v 也没有再次调用 file。EntryAbility@v2/v3/v6/v7/v10 同时被 file 与 diff 查询，共 5 组。全文与差分是不同视图：差分可增加前后对比，全文可增加差分外上下文，不能按“同键同版”整组判为重复。

存在两对跨版本的返回源码逐字相同。比较时只移除工具添加的行号和一个分隔空格，保留源码缩进；仅证明返回文本相同，不证明中间没有实录外修改。

| 返回范围 | 首次全文 | 后续全文 | 后续正文段字符 | 原源码字符 |
|---|---|---|---:|---:|
| EntryAbility v2 → v3，82 行 | #19 `item_22`，L44 | #75 `item_80`，L158 | 4,007 | 3,560 |
| EntryAbility v6 → v7，122 行 | #76 `item_81`，L160 | #77 `item_82`，L162 | 6,188 | 5,417 |

对应源码 SHA-256 分别为 `2b7e9e925e4f066cdd6b2604661d90239d1b366f72e156a763a325bc514381e3`、`6e22c9a6a876a45b67733f0f67fd7f2636e95615d64fe9ec8b63d9d175ea631a`。后两次仍返回不同版本的脊柱、读者和证据状态；可优化的是 10,195 字符正文段中的重复文本，不是抹掉版本节点或全部查询。此前 v3/v7 的 diff 只返回“无 diff 正文”的说明，不能据此先验断言无需进一步读取。

10 次 agent 均指定 `seen=true, reads=true`。同一主会话的 `(4,5]`、`(3,4]`、`(0,3]` 是互不重叠窗口；另一个 agent 的 v2 后接 `(2,3]` 也新增范围，均不列为纯重复。16 个 search 的关键词、主体或时间界限不同，本审计不把范围不同的检索合并计算“浪费”。

有 3 次廉价的导航纠错：#49–51 用 `index(kind=src)` 找 SDK `.d.ts`，各返回 9 字符；#52–54 移除 kind 并放宽部分文件名后找到相应项。这增加调用数，但只有 27 字符空结果，不是当前字符开销的主要来源。

## action 范围与 diff 聚合

12 次 action 都是不同的 action seq，没有重复展开同一 action。两次结果是部分窗口：

- #34 `item_38`，账本 seq 462，`part=input, find=global, max_chars=30000`，返回原输入第 4,146–11,750 字。因 find 定位省略前 4,145 字，尾部已读完；不是 cap 截掉尾部。
- #66 `item_70`，账本 seq 1099，`part=input, find="global uncaught", max_chars=16000`，返回第 10,339–26,338 字／共 38,241 字，明确剩余 11,903 字、可用 `offset=26338` 续读。后续没有该 seq 的续页调用。这里只记录尚未读取的范围，不据此判定结论缺证。

`max_chars` 限制的是被选中的原文片段，不是整个返回包。#66 总返回 27,078 字符，输入正文之前有 10,973 字符，其中“命令提到、账本没记到读写”的导航节占 10,737 字符。12 次 action 的正文前内容合计 25,764 字符；其中此类候选导航共 18,607 字符，约占全部 action 返回的 29.05%。

没有任何 `file(diff=true, v_from=..., v_to=...)` 调用。EntryAbility v4–v10 的 7 次单版 diff 位于 #4/6/8/10/12/14/16，合计 4,377 字符；其发起事件均先于这一组首个返回，属于已并行发出的查询。现有区间接口能减少 leaf 调用数，但会附带 file 脊柱等内容，不能仅凭“7 次变 1 次”宣称节省 token 或墙钟；全部 diff 仅占本跑返回字符的 2.81%。

## 三项低风险改动建议

1. **action 的候选导航默认计数，显式分页展开。** 原文、事件 ID、输入/输出窗口与已确认读写指针继续返回；给未确认候选导航独立开关或页大小。依据 #34/L75 的 4,757 字符候选导航及 #66/L139 的 10,737 字符，可优先优化总计 18,607 字符的这一层；实际净节省还需扣除新计数和续页提示。检查应确保 `part/max_chars/offset/find` 的原文片段完全不变、候选可恢复，不把候选计数当作没有候选。

2. **GUIDE 和示例先给最小参数，明确何时升级展开。** 已有默认 `m_n=0` 被 #3/L11 主动传 `m_n=40` 覆盖：该次 file 返回 19,913 字符，候选节占 10,066。#55/L117 则一次打开 SDK 文件全部 624 行，返回 30,346 字符。建议示例先索引或按当前问题的词搜索，再给 `start/n`；`readers/seen/m_n` 仅在要检查下游、已见原文或未知候选时显式打开。保留所有主动全文和候选展开能力；不把这两次新文件访问直接判为无用。多个连续版本差分的示例可展示现有 v_from/v_to，但独立测量字符与时间，不能只比调用数。

3. **文件头提供可核验的“返回正文相同”提示。** 对可复原内容计算确定性 hash，并标明与哪个已显示版本的正文相同，让模型在 v2→v3、v6→v7 这种访问里选择只取新版本元数据。仍保留各 file@v 节点、访问步骤、版本脊柱、读者和未知/实录外标记；显式 `content=true` 仍返回全文。该提示只陈述复原正文相同，不升级为“没有发生修改”。这能针对上述两对重复正文降低反复展开的概率，无需猜测模型思路或削减新版本事实。

原始证据：[最终 metrics](/C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/tools/rep1/metrics.json)、[首次大文件展开 L11](/C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/tools/rep1/events.jsonl:11)、[SDK 全文 L117](/C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/tools/rep1/events.jsonl:117)、[action 窗口与导航 L139](/C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/tools/rep1/events.jsonl:139)、[后续同正文版本 L158](/C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/tools/rep1/events.jsonl:158)、[后续同正文版本 L162](/C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/tools/rep1/events.jsonl:162)。
