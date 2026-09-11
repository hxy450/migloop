# 2026-09-11：人工评审错误更正（不是修改评测答案）

在把 i13 原稿交给机械核对时，发现之前两条人工反例本身是错的。按原数据库 handles 和逐条 source_record 核回原文后撤回；原始模型产物不改、核心单位标准不改，也不把这些撤回当工具提升。

1. `s-agent-eb3f1b28c6e5` 与 `s-agent-b7cac272cfd0` 都是 `81e0a463-c9d3-4a7a-a671-b7f064830af1:a4874344c8fb6228d`，只是截止分别为18:29:21.552和22:09:07.188。它们不是“检查者/修复者”两个身份。i09 medium、i13 high 的该项错误判定撤回。
2. `e-4e8699c255a6` 是ECAT worker `agent-a228e9716d833cbf3.jsonl` L57，确实将 `console.error` 改成 `hilog.error`。`e-229789c2e667` 是L60，改状态栏溯源注释。之前评审把两条颠倒。i11 high、i13 high 的该项错误判定撤回。
3. `e-b36ea4332843` 的主体是生成者 `agent-a349784d2663f1f0a.jsonl` L40，15:38:45.901Z，Bash回执确实含day/night themes.xml。i13“根据原生Read表确认没读themes.xml”的断言仍不成立。

更正后，i13仍8/10（返回键历史、日志视觉修复前序各部分完成），但列出的额外major只剩主题输入误判1条，不再声称另有错actor。i11、i09核心分均不变。不能把有限核对推广为其它断言全部正确。

复查产物：`C:/Users/hongy/projects/_migloop-scratch/inquiry-i14-review-i13-dice/review.json`，新索引重导、原稿相等为true；实际actor_notes为0，符合原文。literal_predecessors自动找到18:29新增日志→21:19替换日志，提示只是线索，不修改原报告。

后续人工扣分也必须展开坐标本体和具体载荷，不能凭节点昵称、相似scope或交接摘要判身份。模型节点reason、事实发生时刻、查询截止要分开。
