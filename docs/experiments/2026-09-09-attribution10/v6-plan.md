# V6：事实合同重构后的两种交付模式

预注册与验收见 [统一证据计划](../../proposals/2026-09-09-unified-evidence-plan.md)。本轮没有新 raw arm，也没有真实迁移实验；两道题均为已见开发题，不能把结果称为 holdout 或总体准确率。

- 冻结源提交：`4d5db4f`。
- 冻结目录：`C:\Users\hongy\projects\_migloop-eval-20260909\source-4d5db4f`。
- source inventory digest：`76a01f4fae7bf0fe142ade7b2a4f6c5cd6842dc9fc9b3f8dbaa60a8ac88b79cb`。
- runner SHA：`f9a7bc06ff26894ce6e9c13c7eb13b9a0554479b18e2c311b943695d89e43d45`。
- 请求模型：GPT-5.5，medium，native MCP；每次 1800 秒超时，最大并发两跑。实际模型/effort 仍须以每次返回记录核验，不能由请求值代替。
- common task 与原始池完全不变；每个 run 单独保存 prompt/config/完整调用返回/最终回复/提交原文/核验与指标，禁止覆盖。

| 案例 | pool digest | common task SHA |
| --- | --- | --- |
| Member S3/S4 | `a78b1373045f7558d6da3b76123e30d032635a2a0b4cdd665e7f80c0bdf8b337` | `e60ad7491cd5991a948f8c7128432feca230a59bee208640ca5b90a44d68dec1` |
| Codex C4 | `5bcd5ed757c468cea95f79591b41a4fb88cea2a6d6f4b5b1505e0026d2dbfc78` | `88561bcbf7c14a6b64beac1472dd35f174c7478356e3c333c1dd029ba887f727` |

产物根（均在实验根 `attribution10` 下）：`formal-v6-document/<case>/runs/tools/repN` 与 `formal-v6-reference/<case>/runs/tools/repN`。

两条队列交替顺序：

- Member：document rep1 → reference rep1 → reference rep2 → document rep2。
- C4：reference rep1 → document rep1 → document rep2 → reference rep2。

首批于 2026-09-09 17:43 UTC 启动。按照完整预定队列报告，不因某次写得好/坏选取或重试覆盖。若基础设施失败，原失败保留且新尝试另立目录/编号。

因果解释范围：两组共享全部事实准入、查询和 UI 改动，因此组间差别只用于检验最终交付协议。对比 V5 只能报告整体观察变化，不能将旧→新成本差都归到某一项改动。召回降低造成的候选、缺版本和未知不自动算正确；需按独立原文判断模型是否保住了可以查明的事实。

正式内容仍是 `migloop-verdict/1`。reference 组的最终短块只显式承诺最后一次真实 check 中的草稿，不替代草稿；通过认证后原文另存 `verdict.yaml`（原草稿为 JSON 则 `document.json`）。按文件投影另存 `findings.json`，其原因、角色、归属与建议仍是模型主张。`submission.json` 保留交付来源与未解决诊断。

状态：启动时没有模型结果；结果、逐条语义复核、实页截图另文保存。
