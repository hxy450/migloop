# v5 草稿机检交叉审查

审查时间：2026-09-09。对象为冻结前工作树中的 `draft_check.py`、`probe.py`、HTTP/MCP 接入及其测试。仅读源码和临时合成转录；未调用模型，未打开本轮实验答案，未修改冻结输入、历史报告或参考答案。此文不是 v5 质量结果。

## 结论与复现

本轮先发现并反馈以下边界。生产修改由主代理负责；本审查只新增 `tests/test_draft_check_adversarial.py` 与本文。

| 边界 | 可构造反例与影响 | 最小修正及回归 |
| --- | --- | --- |
| 显示文档与核查文档错绑 | `verdict.json.data=B`、`raw=A`，实际图上显示 B；若从 raw 取最终 hash，`check(A)` 会错误匹配 B。 | `verdict.build` 对实际通过 schema 的 data 计算 `document_sha256`；probe 用此 hash，不再重解 raw/report。覆盖 A/B 互换、raw 缺失/损坏、data schema 失败。 |
| 删掉 coverage 可清除分母 | 已提供目标和返修清单时，`coverage: []` 报缺项，而完全省略字段曾跳过对账，返回 mechanical_clear。 | 有链清单/目标即对 `data.get("coverage")` 对账；旧 schema 仍可解析，但未提供不能算完成。合成用例保留 3 个版本和 1 个未确认执行候选；无目标明确标范围未核。 |
| 原生完整配对未设标志 | Claude `tool_use/tool_result` 和 Codex `function_call/output` 已按原 ID 配齐，却没有 `complete_pair=True`；新 checker 严格判定使它们都不可核。 | 在解析器确实配齐、来源无冲突后明确登记完整配对；不能把缺 ID、缺结果或裸工具名升级。另以有起止时间的 Codex 原生叶事件作阳性对照，不伪造其 call_id。 |
| 结论身份与轨迹身份需同时通过 | sessions 属于当前账本、check(A) 也匹配，但保存结论的 harness_identity 指向另一账本。只检查轨迹身份会绕过结构化结论的 fail-closed。 | 最终绑定同时要求 trace 与 structured identity 均 bound；合成测试保留身份冲突原文，不重绑。 |

验证状态：四项修正均已复核。新增 16 个对抗用例全部通过，连同已有 checker、probe、trajectory、basis 回归共 **129 passed**（2.34 秒）。本有界审查未发现剩余冻结阻断；不代表已验证整个系统或模型质量。

## 保留的机制与准确边界

- `document_hash` 使用通过 schema 的 canonical JSON：排版和映射顺序不影响匹配，主张文本变化会改变 hash。`draft_sha256` 另绑定实际提交字符串，二者不能混用。
- 最后一次 check 指调用序列的最后一项，不选择“最近成功且碰巧匹配”的历史结果。最后一次缺返回或返回不可解析时，不能回退此前成功核查。调用并发完成次序不是“模型采用顺序”的证明。
- 完整返回、原工具来源、参数和原生调用 ID/叶事件配对是核查记录前提；错误返回、截断交付、来源冲突、未配对和身份冲突不能匹配。原生叶事件只有 item_id 时保持 call_id 缺失。
- `matched` 只表示最后核查对应当前显示文档；该 check 仍可是 `needs_review`。测试要求保留 warning 计数及 `semantic_checked=False`，不能把“同稿”说成“通过归因审查”。核查结果中的 issues、omitted_issues、coverage 同时保留；返回计数和状态须自洽，不能靠复制两个 hash 而省掉整份反馈结构。
- `resolve_evidence` 只定位动作引用或节点坐标，不读取并判定原文支持程度。已有测试将 `atoms.action_raw` 换成必失败函数，checker 仍正常给出定位诊断；原文内容没有因此被认证，也不证明模型曾看过。
- MCP `check` 和 HTTP JSON/文本共用 evaluate/render；它们不调用 ViaState.open，不消费首次打开权限，不创建 file/agent 访问或图边。已有同源测试先 check 后首次 `file(..., via=sessions)` 仍可打开。
- 草稿上限 120,000 字符；反馈最多 40 条，完整计数与省略数另留。coverage 分母仍含版本及执行候选；候选不是“已经发生的修复”，逐项交代也不验证理由真假。

来源可信度须明确：这些 hash 是内容绑定，不是服务器签名；当前威胁模型信任原生转录/受控 harness 未被任意篡改。拥有修改整份转录权限者可重算 hash，因此 UI 的“调用记录认证”只能理解为来源与配对结构可核，不能理解为密码学认证。原生 MCP 返回也不证明外层包装把反馈完整交给模型，或模型实际阅读/采纳了它。

核查范围仍以调用的目标文件为界，不代表整项用户任务或所有文件都完成。最终匹配摘要不是另一份 coverage 证书；独立的最终 coverage/identity 诊断仍须保留显示。

## 可复核入口

- `src/migloop/draft_check.py:15`：`document_hash`；`:30`：`evaluate`；`:112`：coverage 范围；`:140`：`final_binding`。
- `src/migloop/verdict.py:430`：`resolve_evidence`；`:617`：`build` 中实际文档 hash。
- `src/migloop/probe.py:248`：实际显示文档与双重身份绑定；`:284`：`_structured`；`:370`：`_transcript_calls`；`_deduplicate_runtime_calls` 末尾：完整配对标志。
- `src/migloop/service.py:670` / `:736`：HTTP JSON/文本 check 分支；`src/migloop/mcp_server.py:403`：MCP `check`。
- `tests/test_draft_check_adversarial.py`：显示 A/B 交换、身份冲突、coverage 省略、三类原生来源、最后失败不回退、裸工具名、同稿仍有警告。
- `tests/test_draft_check.py`：只读、语义边界、反馈预算、定位错误、MCP/HTTP 同源及不打开节点。

复跑命令（临时目录使用新的名称）：

```powershell
& 'C:\Users\hongy\projects\migbot-elite\.venv\Scripts\python.exe' -X utf8 -B -m pytest tests/test_draft_check.py tests/test_draft_check_adversarial.py tests/test_probe.py tests/test_trajectory.py tests/test_verdict_basis.py -q --tb=short -p no:cacheprovider -o pythonpath=src --basetemp C:/Users/hongy/projects/_migloop-trace-audit-20260909/v5-check-final
```
