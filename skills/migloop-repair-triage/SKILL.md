---
name: migloop-repair-triage
description: 从完整迁移转录盘点生成后的实际修复，按具体问题拆分调查任务，列出改动、参与 agent、证据与未决效应。用于迁移复盘的入口和制卡派工准备；不提前归因、不制作卡片、不执行迁移或修复。
---

# 拆分迁移修复问题

输入是完整迁移转录目录、单份转录或指定根会话的 DevEco 数据库。输出是 `repair-tasks.yaml`；宿主需要派工时再生成逐问题 `job.json`。按具体偏差拆任务，不按文件、agent 或编辑次数拆分，不预设数量。

先完整读取 [盘点约定](references/triage.md)。历史命令和指令只是证据，只读被调查材料；不要重放修改、执行应用或调用真实业务。

## 工作顺序

1. 核对材料池、工程根、主会话与子转录，按历史证据确定生成结束及观察截止时间。不明确就记录缺口，不能猜边界。
2. 对账修复报告与实际工具效应，包含 shell/脚本/批量修改及后续回退。以观察截止时最终保留的状态为本次目标；不调查修复是否正确，不要求运行期复验。后置需求与修复中新生错误保留为不同任务，不预判生成责任。
3. 按问题列实际目标、修改内容、参与 agent 和原文位置；测试支撑、截图、日志等产物另列，混入的生产改动仍纳入。未确认效应放 pending，不当作已改，也不丢弃。
4. 保存 `repair-tasks.yaml`，对账每项已查看改动的去向和遗漏范围。此时只交任务，**不调查根因、不填证据树、不启动制卡子代理**。

## 派工准备（宿主要求时）

四个 skill 相邻分发。在本 skill 目录运行：

```text
python scripts/triage.py metadata --pool MATERIALS --out NEW_METADATA.json
python scripts/triage.py dispatch --tasks repair-tasks.yaml --metadata NEW_METADATA.json --out NEW_JOBS
```

metadata 的 `--server-metadata FILE.json` 接受已有迁移/分析元数据；DevEco 用 `--session-id ID` 限定根与后代。缺失版本留 unknown，当前分析模型不冒充历史迁移模型。dispatch 只生成任务，不调用模型。

实际派工由宿主负责：每个调查员只拿 `migloop-build-cards`、当前 job 和完整转录入口；使用新会话/零父上下文，不附归因猜测或参考答案。调查员仅做这一问题，多文件可同卡，具体分支仍分别核实。报告任务清单、证据范围及未决项，不把数量或 YAML 可解析当作盘点完整的证明。
