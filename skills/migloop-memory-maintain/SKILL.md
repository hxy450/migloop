---
name: migloop-memory-maintain
description: 基于已有经验库和新增、修订或撤回的问题卡，提炼候选经验、比较归并并发布有来源的版本。用于维护迁移经验及其依赖关系，不执行当前迁移任务。
---

# 维护迁移经验

把问题卡中的事实和建议提炼为短经验，维护明确的适用条件、例外和证据。经验目录只帮助检索；分类相同不构成因果或合并依据。

先读 [维护协议](references/protocol.md)。命令相对于本 skill 目录执行，召回命令位于相邻 `migloop-memory-recall/scripts/recall.py`。三个 skill 应保留相邻分发结构；操作本地经验库不等于部署云端或安装 hook。

## 工作顺序

1. 确认用户指定的经验库与卡片范围。已有库先 `python scripts/memory.py snapshot --store STORE`；新库才用 `init --store STORE`。记录当前 revision。
2. 通过 `python scripts/memory.py ingest --store STORE --cards CASE.json --base-revision REV` 入卡；多份卡可在同次请求提供，空库首次导入可省 base revision。撤回使用 `withdraw --store STORE --case ID --reason TEXT --base-revision REV`，可用 `--claim diagnosis` 或 `--claim recommendation:1` 仅撤回某条结论。它们保留来源版本，并使已记录的失效依赖进入复查，不替模型生成或审核经验。
3. 读取反馈并 snapshot 取得当前 revision，检查新增、修订、撤回卡影响的经验及上层依赖。用相邻召回脚本的 `search/read/browse --all-statuses` 找少量相关既有经验，涵盖候选、争议及待复查记录，不能只比较 active。
4. 对每个具体主张判断新增、补证、条件分支、冲突、退役或无可复用经验。按当时证据判断，不能把多文件同批修改当作多次独立验证。当前范围不足时保留 candidate 或 disputed。
5. 写包含 `base_revision`、`upsert`、`retire` 与必要目录描述的提案。每条经验绑定具体卡片 claim 及卡片 revision；依赖其他经验时显式写 `requires`。标题、when、unless、why、how、check 保持短而可执行。
6. 在模型语义审核后，用 `python scripts/memory.py apply --store STORE --plan PLAN.yaml` 做机械校验并发布版本。语义审核是本维护任务的一部分；不用额外请求一次笼统批准。版本冲突时读取最新 snapshot、比较变化并重做提案，不能只改 revision 强行覆盖。

`active` 表示本次维护者审核后可供默认召回的历史建议，不能描述为系统认证的真值。机械校验能检查引用、版本、结构和依赖，却不能证明归因或建议有效。

来源修订、撤回或下层依赖失效时，上层经验应停止默认使用；查清之前不得绕过 `needs_review`。重新激活必须核实新的依据、条件和所有依赖，不因新卡同名而自动恢复。

交付新 revision、增加/更新/退役及待复查范围、主要归并理由与仍存在的争议。只保留一份规范经验正文，主题移动或多个目录入口不制造重复经验、不删除源卡。
