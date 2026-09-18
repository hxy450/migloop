---
name: migloop-memory-recall
description: 在理解当前迁移任务与输入后、首次修改前，按需查找和读取适用的历史经验；也用于收到经验查询提醒后的召回。
---

# 按任务召回经验

先理解当前规格、源码和任务，再查指定经验库。在本 skill 目录执行：

```text
python scripts/recall.py search --store STORE --query "任务阶段 具体动作 输入特征"
python scripts/recall.py browse --store STORE --topic TOPIC
python scripts/recall.py read --store STORE --ids ID_A ID_B
```

先看返回的title、when（使用阶段与动作）、description（适用情境）选择条目，再批量读完整短经验，对照description/unless决定如何采用。当前要求优先。

任务明确就搜索，需要找路就浏览。阶段是线索而非硬过滤：一个agent可能跨职责工作，局部无匹配时，去掉主题限制，用动作、API名或同义词跨阶段搜索。旧条目的description为空时结合原when判断，必要时展开正文。

默认读 active 经验，证据卡在有争议或需核实时展开。记录已读ID、版本和采用/跳过理由；完成核对后继续原任务。任务或输入明显变化时再查，库不可用或分页未完时注明召回缺口。

分页、来源核查和版本操作按需读 [使用约定](references/usage.md)。hook提醒由宿主接入，本skill负责收到提醒后的查询。
