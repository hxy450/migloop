---
name: migloop-memory-recall
description: 在迁移任务理解后、首次修改前，或收到经验查询提醒时，按当前任务查找并读取相关历史经验。仅按需召回，不维护经验库或执行迁移。
---

# 按任务召回经验

理解当前输入后，查询指定经验库；在本 skill 目录执行：

```text
python scripts/recall.py search --store STORE --query "事前可见的任务条件"
python scripts/recall.py browse --store STORE --topic TOPIC
python scripts/recall.py read --store STORE --ids ID_A ID_B
```

任务明确就搜索，否则浏览；局部无匹配时用全库关键词及同义词兜底。批量读短经验，核实 when/unless 再采用；当前要求优先。只有争议或缺依据才读卡。

默认只用 active，记录已读 ID/版本，同任务不反复查。适用性已核实或已查范围无匹配即可继续；未查完应报告未完成。分页与证据操作按需读 [使用约定](references/usage.md)。安装不配置 hook 或云端服务。
