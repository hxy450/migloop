# 任务清单格式

## 盘点口径

记录材料池、历史工程根、主会话及子会话；生成结束/观察截止使用有依据的带时区时间，未知填null并说明。DevEco按指定根会话及后代只读查询。

两条线对账：报告/派发给出问题线索，实际修改请求及回执确定修改范围。脚本需核当时正文、执行结果及各目标效应；失败调用可能部分成功，未决效应列pending。追到最终保留状态，回退掉的尝试作为历史过程。

按具体偏差和验收要求分组。同一问题可跨文件，一个文件也可涉及多个问题。区分生成遗留、后置要求与修复中新生错误；归因留给制卡阶段。

| 内容 | 去向 |
| --- | --- |
| 应用行为、UI、资源、身份或构建配置修改 | issues |
| 测试宿主、mock、测试ID/参数桥 | set_aside: test_support |
| 截图、日志、报告、索引及临时产物 | set_aside: artifact |
| skill、测试框架等管线自身改动 | set_aside: pipeline_tooling |
| 报告了问题但未实施修改 | set_aside: unrepaired |
| 执行/目标/效应待核 | pending |

按实际用途分类；一个调用混有辅助产物和应用修改时分别记录。修复采用最终保留状态为参照，questions聚焦修改、输入和来源，无需新增“补跑截图证明修复正确”的任务。

## YAML

```yaml
schema: migloop-repair-triage/1
scope:
  project_roots: []
  source_roots: []
  materials: []
  generation_end: null
  observation_end: null
  boundary_evidence: []
issues:
  - title: "具体偏差"
    observation: "原表现与目标表现，标明报告来源"
    changes:
      - files: ["真实目标路径"]
        change: "改了哪些属性/操作，最终保留什么"
        evidence: ["原始修改请求与回执位置"]
    participants:
      - agent: "转录路径或数据库session标识"
        role: "发现/协调/修复/复核等实际角色"
        action: "此人具体做了什么"
        evidence: ["对应原文位置"]
    questions:
      - "留给制卡调查的输入、偏差来源或交接问题"
set_aside:
  - category: artifact
    item: "已检查产物组"
    reason: "用途"
    evidence: []
pending:
  - item: "效应待核调用"
    evidence: []
    next_check: "可核查的历史材料"
coverage:
  reviewed: "实际审查过的会话、调用和时间范围"
  gaps: []
```

占位值换成真实材料，无条目用[]。JSONL引用用相对转录名、物理行号和必要的调用ID；数据库用session及message/part主键。声明引用所属材料池。批量修改可共享脚本引用，同时列出已有依据的具体目标。

交付前确认已审查的应用修改都有issue/搁置/未决去向，包含主会话直改、批量脚本和修复后再修。报告缺失转录及未扫描范围。清单无需持久ID或图节点，后续dispatch自动补身份。
