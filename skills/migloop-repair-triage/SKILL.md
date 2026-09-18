---
name: migloop-repair-triage
description: 从完整迁移转录识别生成后的实际修复，按具体问题整理改动、目标文件和参与者，生成后续归因调查的任务清单。
---

# 拆分修复问题

输入完整迁移转录目录、单份转录或指定根会话的 DevEco 数据库。输出 `repair-tasks.yaml`，交给后续制卡调查员。

1. **确定范围。** 找到工程、主会话与子转录，按历史记录确定生成结束和观察截止，记录依据及缺失材料。
2. **盘点修改。** 对照修复报告与实际调用，检查 Write/Edit、patch 和 shell/脚本的请求及回执，追到最终保留的修改。采用最终保留状态为本次正确参照。
3. **按问题分组。** 每项写清原表现、改成什么、涉及文件及参与 agent。同类问题可跨文件，不同验收要求分别成任务。截图、日志、测试支撑等另列；脚本对应用的实际修改仍纳入，效应待核的调用列 pending。
4. **保存并对账。** 按 [任务清单格式](references/triage.md) 写 YAML，核对已审查改动都有去向。根因与证据树由制卡阶段完成。

历史材料只读，调用用于取证。交付清单路径、调查范围及缺口。

## 准备派工

宿主需要 job 时，在本 skill 目录执行：

```text
python scripts/triage.py metadata --pool MATERIALS --out METADATA.json
python scripts/triage.py dispatch --tasks repair-tasks.yaml --metadata METADATA.json --out NEW_JOBS
```

已有服务端元数据用 `--server-metadata FILE.json`；DevEco用 `--session-id ID` 指定根及后代。dispatch生成任务文件，模型调度由宿主负责。

每个调查员使用独立新会话，只拿 `migloop-build-cards`、一个job和完整转录入口。任务提供修改线索，归因由调查员依据原文得出。
