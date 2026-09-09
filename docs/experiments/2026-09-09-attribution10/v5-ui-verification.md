# v5 实页 UI 复验

日期：2026-09-09。只读复验同一批 `formal-v5` 调查产物；未重跑模型、修改生产代码、冻结源或原始 run。以下是界面与机械记录的一致性检查，不是缺陷准确率或归因真值评审。

## 查看器对照

调查与原始查看器源为 `5b770be`；修正正文保真后的只读查看器为 `d14853c`。原服务 19663/19664 和新服务 19665/19666 分开，旧截图没有覆盖。

| 项目 | C4 | MemberCenter |
| --- | --- | --- |
| run | `formal-v5/codex-c4/runs/tools/rep1` | `formal-v5/member-center/runs/tools/rep1` |
| 原 `metrics.json` | `unverifiable`，仍保留 | `unverifiable`，仍保留 |
| 原 5b770be UI | `unverifiable`，与当时载荷一致 | `unverifiable`，与当时载荷一致 |
| 新 d14853c UI | `matched`，最后核查 #58 | `matched`，最后核查 #64 |
| 实际 check 步号 | #57、#58 | #63、#64 |
| 新查看器提供的诊断 | 首次 2 条、最后 0 条 | 首次 3 条、最后 0 条 |
| 返回省略量 | 两次均为 0 | 两次均为 0 |
| basis | 缺失；未声称完成原文对照 | 实际存在，已核选中节点的展示与原始结论块一致 |

两份原始 metrics 的状态与最终 document hash 均通过只读读取确认：原状态没有被新查看器回放写成 matched。新 UI 的 matched 仅表示最后一次真实核查记录与当前稿对账一致，不证明模型阅读/采纳反馈，也不证明归因正确。

## 真实界面断言

使用 `tests/browser/probe_basis_smoke.cjs` 和既有 `probe_smoke.cjs`，连接已存在的 Chrome CDP 19652。两个脚本在两个新页面均通过，无 JavaScript 异常；四张新截图均已实际打开查看。

| 检查项 | C4 | MemberCenter |
| --- | --- | --- |
| 结构化 schema 错误 | 0 | 0 |
| 结论身份 / 查询身份 | 均绑定，UI 显示 matched | 均绑定，UI 显示 matched |
| 原始调用记录数（含 check） | 58 | 64 |
| 轨迹实体显示数 | 6 / 6 | 14 / 14 |
| 文件/agent 访问记录 | 3 opened | 6 opened + 2 rejected |
| 声明转移：预期 = 实际绘制 | `[10, 11]` | `[31, 37, 43, 48, 59]` |
| 点击节点显示对应原因 | 通过 | 通过 |
| check 被添加为版本访问/图边 | 没有 | 没有 |

`probe_basis_smoke` 将每条已提供 issue 的全部 JSON 字段或原始字符串与展开后的 DOM 文本逐项比较，同时核对省略数和完整 coverage 返回。不是仅检查诊断数量。

仍可查到的首次核查告警：

- C4 #57：`reference_drift`（`#01a009fe-68e3-7f42-b76b-5e863c555976:4564@L8032`）；`invalid_node`（`agent:__main__:01a009fe@v253`，已知效应范围 1..252）。#58 为 `mechanical_clear`，首次告警没有消失。
- Member #63：`invalid_node`（`agent:agent-af0e3d2ae54dbf769@v6`，已知效应范围 1..5）；两条 `invalid_reference`，分别位于 `S3.nodes[4].evidence[1]` 和 `S4-compile.nodes[2].evidence[3]`，原引用均为 `#af0e3d2ae54dbf769:L54/0`。#64 为 `mechanical_clear`，首次诊断仍完整可展开。

Member 的归因对照本次选中缺陷 `S4-price`、节点 `agent:agent-aslice8-pay-80bbb1f44b77da0f@v13`。结构化节点行和实际原因抽屉中的 expected、actual、counterevidence 以及两组 original_ref，均与 `p.structured.raw` 经只读 `verdict.parse_block` 解析后的原模型字段逐字一致。此处验证的是展示保真，没有把这些模型文字当作迁移事实或独立金标。C4 没有 basis，脚本明确输出 missing，不伪造对照通过。

覆盖计数也不是完整性或语义证明：C4 的清单分母为 0，0/0 不证明全部真实修复已找齐；Member 为已登记 22/22（9 个版本、13 个候选），其中 deferred/unconfirmed 各 8、声明 not_repair 2，不能写成 22 项均已解决或验证正确。

## 展开不改写调查轨迹

新查看器内，展开核查明细、选择缺陷、打开已有节点原因和展开 basis 前后，完整 trajectory JSON 的 SHA-256 分别保持不变；steps、图实体 ID 和绘制的转移集合也逐项保持不变。

```text
C4 before = after:
55453e454fc2811e62d68051f0b1cba0aaebcd2a14a81fc7054a31a5a7eff497

Member before = after:
af5b988a145c54d568022c71e1aeea61d2686fde7f19e59530017abaa8ca5dba
```

此不变性是在同一查看器版本内比较。不能将不同查看器的归一化载荷 hash 混为原始 run 文件 hash；原始调查/metrics 仍保留原状态。

## 页面及截图

- C4 新页面：`http://127.0.0.1:19665/api/insight1/fixchain/01a021e5?probe=attribution10/formal-v5/codex-c4/runs/tools/rep1`。截图：[原 5b770be 状态](screenshots/v5-c4-basis-check.png)、[d14853c 核查明细](screenshots/v5-c4-basis-check-viewer-d14853c.png)、[基本轨迹](screenshots/v5-c4-trace.png)。
- Member 新页面：`http://127.0.0.1:19666/api/insight1/fixchain/ff019d8a?probe=attribution10/formal-v5/member-center/runs/tools/rep1`。截图：[原 5b770be 状态](screenshots/v5-member-basis-check.png)、[d14853c 归因对照与核查明细](screenshots/v5-member-basis-check-viewer-d14853c.png)、[基本轨迹](screenshots/v5-member-trace.png)。

诊断和长归因正文位于可滚动面板，单张截图不等于全文交付；完整内容保真由上述 DOM/载荷/原模型块断言核对。
