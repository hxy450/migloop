# Transfer 评分器接口

`score_transfer.py` 是独立只读裁决验证/汇总器，不调用模型，不执行历史命令，不改旧评分器、runner 或 runtime。它先核 package 的 manifest / READY / runner 字节绑定，再只加载 package 中冻结的 `run_transfer.py` 并调用 `verify`，核完整 source、candidate、helper、code、settings、任务和 private artifacts；无当前 checkout fallback。它仅解析合同指定的每 cohort **一个** core artifact，不解析 reference 正文。可额外传入外部已记录的 manifest SHA。哈希是完整性合同，不是对恶意文件系统的身份认证。

## Grade

目录为 `GRADES/raw|tools/TASK-ID/repN.json`，与运行目录 `PACKAGE/raw|tools/runs/TASK-ID/repN` 分离。保留旧 units/claims 语义，加显式绑定：

```json
{
  "schema": "migloop-transfer-grade/1",
  "case": "TASK-ID", "rep": 1, "condition": "raw", "cohort": "COHORT-ID",
  "transfer_manifest_sha256": "...", "metrics_sha256": "...",
  "report_sha256": "...", "core_contract_sha256": "...",
  "claims_review_complete": true,
  "units": [{"id": "unit-name", "outcome": "correct", "reason": "审阅理由",
    "report_spans": ["逐字报告片段"], "evidence": [{"source": "root.jsonl", "line": 1}]}],
  "claims": [{"id": "claim-1", "outcome": "supported", "reason": "审阅理由",
    "report_spans": ["逐字报告片段"], "evidence": [{"source": "root.jsonl", "line": 1}], "major_error": false}]
}
```

每个 core `TASK-ID/unit-name` 必须恰好出现一次，grade 的 unit id 使用斜线后的部分。outcome 延续 correct / partial / missing / wrong；partial 不进 correct 分子，但不等于 wrong。每个实质因果主张去重为 supported / contradicted / unsupported_asserted_as_fact / explicitly_hypothetical。显式假说不进 precision 分母；无事实断言时为 null。

`claims_review_complete:true` 是**审阅者声明**已覆盖全文实质主张，不是程序证明没有遗漏。major 必须为实际 contradicted/unsupported 断言，并有逐字报告片段及原始 source/line 对象；遗漏、合理未知、格式错误不自动变 major。语义支持和 major 实质性仍需独立原文审阅，不能靠验证器自行决定。

Grade 同时核最终 report SHA、metrics SHA、case/rep/condition/cohort/core/manifest；run 的 `prompt.md` 原则上须与冻结的该 case/arm 任务字节相同，只有下面实证的 Windows 落盘副本例外。旧记录若有 transcript SHA/session id，则核原生副本与 session_meta；整 arm 已记录的 session/hash 不得跨 run 重用。缺失这些历史可选字段不会被补造为新必填值。

### 实际提示词与 Windows 落盘副本（首轮运行中发现并修正）

`raw.launch` 将冻结的 LF 字符串原样编码送入 stdin，但 `Path.write_text` 在 Windows 把单独保存的 `prompt.md` 改成 CRLF。DYNAMIC1-05/rep1 首次实际验证因此被旧评分器（SHA `b0645dadc7b61ed0486fe3e982880792bb20eb4e61739c542a29f5b247a88f3e`）拒绝。这是记录副本的字节差异，不能不经核验就忽略，也不是模型归因错误。

该跑冻结任务为2070字节、SHA `1136312424772a5c4553bc529965a396f17b1d61074b906d2ee7c540a587313f`；磁盘副本2084字节、SHA `08a4296c4fd4077f05c4b8dfa8e171db2eeeeb76d93fdc3c6a8e8fb66bf28c02`，恰好14个LF变为CRLF。已与metrics绑定的原生转录L7，是首个turn_context后的首个response_item/user，其单个input_text全文与冻结LF任务逐字相等；L4环境消息不当任务。完整转录SHA和session_meta身份同时核回。

新增 `prompt_binding` 状态为：

- `exact_bytes`：保留原字节合同，不为旧记录偷偷增加原生消息布局要求；明确 `native_task_checked:false`。
- `windows_crlf_copy_native_exact`：仅当期望文本纯LF、磁盘副本恰为LF→CRLF确定变换，且哈希/会话绑定的首turn首响应为完整单块用户任务并逐字相等时接受。第二turn、后续用户消息、工具结果或引用文字不能补救；出现额外用户消息也拒绝该例外。
- `unbound`：其它文字、空白、BOM、混合换行、末尾换行变化、身份缺失、截断或未知原生布局均拒绝，不作通用归一化。

验证返回及summary逐run均保留实际/期望SHA、原生任务物理行和JSON pointer；结束时复核副本及原生证明没有漂移。首次失败与修复后真实通过保存在本地 `generalization-20260910/prompt-transport-audit-v1/{before,after}-fix-DYNAMIC1-05-rep1.json`。没有改runner、题目、模型、预算、原始实验文件、参考或grade；D05语义分仍为1C、事实4/5、major0。修复后评分器SHA为`633ec783d652530acf359209f7751078329d0524dde03f9750e90ada2990f610`。作者98项合成测试通过；root独立30项prompt测试通过。它们不认证恶意记录器或OS级隔离。

## 原文定位机检的限度

- source 必须属于本 cohort 的冻结池；basename 歧义时使用 pool-relative 路径。原始物理行必须存在。
- 提供 `timestamp` / `ts` / `time` 时，只比对 JSONL 原行顶层字面字段，计 `literal_timestamp_match`；不把 SourceSpec 未核的 JSONL journal 升级为有资格的事件时刻。所有结果显式 `source_policy_verified:false`。
- `call_id` / `callid` 只核已知 typed use/result 字段，计 `typed_id_field_match`。正文提及 ID、工具结果里嵌入的示例调用不算。匹配不证明调用配对、成功、作者或 code-host 内嵌命令执行。
- `call_id:null` 表示所核原行没有上述 typed 字段，单列 absent；若原行实际有 ID 则拒绝。省略字段表示未请求检查，不等同 null 检查通过。未知 timestamp:null 同理单列 absent，不计已匹配时刻。
- 非 JSONL 附件即使长得像事件 JSON，也不认证事件时间或调用 ID。可选 JSON pointer / exact excerpt 仅作**独立逐物理行**的 JSON 字段/decoded 字符串检查，绝不是 MCP 解码、scope 或正文交付认证。没有 pointer 时也可核 raw 或 decoded 字符串叶子的逐字摘录。
- 字符串 reference-ID 仅为 opaque cross-reference，单独计数，不宣传已核原文；不能独自支持机械认可的 major 原始依据。

## 汇总和失败

```text
python -B score_transfer.py validate --base PACKAGE --condition raw --case TASK-ID --rep 1 --grade GRADE.json
python -B score_transfer.py summarize --base PACKAGE --condition tools --grades GRADES --manifest-sha256 SHA --out NEW.json
```

Python API 为 `validate_grade(base, case, rep, grade, *, condition, manifest_sha256=None)` 和 `summarize(base, grades, *, condition, manifest_sha256=None)`。所有新输出拒绝覆盖；无自动生成语义 grade、重试、删题或更换参考。

任务和分母来自 manifest，非固定 10/13/26。此实验正常每 arm 为 13×2=26 跑，但测试也覆盖任意任务数/各文件不同 unit 数。只有**整个 arm 队列 finished 且每一跑均可评/已裁决**才给每 cohort 的正式 aggregate；两个 cohort 不合成一个总体准确率。未跑、待评、未结束为 pending，不记零；健康终止 timeout/incomplete 且无非空最终报告，才自动记 missing delivery。基础设施/身份/记录/后处理失败单列且阻止完整汇总，实际成本和原尝试保留。

每 cohort 报文件等权 correct coverage、correct/全部 core、supported/事实断言、核心全 C 且无 major 的完整文件通过，以及 major。另报全文无 contradicted/unsupported 的报告数；无 claims 时可满足该计数，但 precision 仍 null，且不因此 core-pass。自动无报告 missing 不算已审阅且全文干净的报告。同文件两个 rep 为配对观测，不是两个独立业务样本。

机械 schema/引用/身份统计独立，不能因图好看加分或格式错扣语义。成本保留 input（已含 cache）、output、input+output、cache 明细；缺失/skipped 不记 0。investigator 用原 `elapsed_seconds`（若无显式 investigator 字段），system 含前后核验与后处理，postprocess 另列但不再相加；queue start/end 的 makespan 与 run-time 总和分开。每项成本均显示 observed/expected 和 complete。汇总结束再次核冻结输入及已读 run/grade 文件，避免读取中漂移。

验证限于小合成 artifact；未运行模型、未冷建真实 ledger、未读新 reference 正文。完整通过测试数在任务交接报告记录。
