# V2 receipt / scope / event 独立边界审查

2026-09-09，只读审当前工作源码，不改生产文件、不读私有 holdout、不重写冻结记录。使用代码探索技能；仓库无 GitNexus 索引，直接沿调用链核源码。结论：**未发现本次范围内需要阻断冻结的 fail-open、跨文件补集或伪造已阅问题**。发现的非阻断 API 命名风险已由主代理改为 declarations_complete，见末节。

## 逐项核验

| 边界 | 实现与判断 |
|---|---|
| V1 兼容 | `verdict.validate:187` 仅 schema 明确等于 v2 才派发；`verdict_v2.validate:19–46` 创建独立 legacy 验证视图，未修改源文档。v1 使用 target_file/recommendation 等新字段仍报未知键。v2 RED node/event 才强制 basis，未逆改 v1。 |
| 原稿与哈希 | `verdict.build:657` 对实际传入 data 的原始 canonical JSON 哈希，含 v2 字段；`draft_check.document_hash` 同样验证后对原文档哈希。legacy 验证视图不用于 hash。submission 测试确认改 recommendation 会使最终绑定 mismatch，未把不同稿件混绑。 |
| 清单范围 | `coverage_receipt.receipt:19–27` 哈希整个清单，包括 target、ledger、policy、items/candidates 顺序、事件和诊断。`reconcile:52–64` 同时要求 identity_bound、当前 ledger、有效 manifest 和摘要一致；不匹配不展开补集。check 自己从 chains 与显式 file/root 生成 manifest，不把模型提供的 target_file 当成新清单。 |
| target 不是 repair | `verdict_v2.target_binding:49–54` 仅解析实际已有 story，缺失/歧义/身份不符保留状态；`extend:57` 不写 roles、fixed 或 edges。测试 unknown target + 空 nodes 后，repair.before/after 均为 None，不生造文件节点。 |
| 补集不是模型审阅 | `coverage_receipt.reconcile:68–72` 只把原 reconcile 的 missing 放到独立 complement_rows，标 source=system_manifest、model_claim=false、semantic_checked=false，不塞入模型 rows，也不合成为 out_of_scope/not_repair/explained。零 reviewed 时，模型逐项声明仍为 0。 |
| 非法行不被吃掉 | 原 coverage 先按 occurrence 识别已声明坐标；receipt 仅移除 missing 类型错误，保留 duplicate/invalid_status/unknown_defect/invalid_rows 等。非法或重复的显式行不会通过补集变有效；超量截断也保留错误。测试重复52＋非法53后，补集只有真正缺失54，complete=false。 |
| 旧清单 | probe 经 coverage_snapshot.select_manifest 再 reconcile_document，只有 harness 元数据能提供 recorded manifest；已有选择器核 ledger、目标路径、版本/事件/candidate身份。非法记录不静默回退成完整新清单。新 receipt 不重算旧 v1 声明。 |
| 事件只作事件 | `event_claims._binding:119` 先身份再 action_query.resolve；要求唯一原动作与 src 指针，漂移按唯一原位置而非猜 seq；未绑定不解析 evidence/basis 原文。模型不能自报 anchor/version/checked。 |
| pending 与时间 | `event_claims:144–175` 取同 owner 在当前动作之前的真实 effect 顺序，不把尾后槽强绑末版为 effect_version。paired_result 需要有原生 tool ID、非未知状态和不同 result 行；pending 不伪造 result_line。context_anchor 明示 prior_ledger_effect_order，完成时刻另比较；重叠不声称事件前可用，时序可用也不证明内容消费。 |
| 不升级为语义 | target、event、basis、receipt、check 均保留 semantic_checked=false。event creates_node/creates_edge=false；对别的文件的上游事件可以作为模型证据，但不把它收进本文件修复补集。target 的存在不认证该缺陷属于整份用户任务。 |

`receipt` 是与服务器/调用者可信生成的清单内容绑定，不是密码学签名，也不是模型真正阅读过各项的证明。若未来接收任意外部自报 manifest，须先走现有清单来源/坐标校验，不能只靠对该外部对象计算 SHA。

## 实测与剩余非阻断风险

运行实际 venv 的 `test_verdict_v2.py`、`test_coverage_receipt.py`、`test_event_claims.py`、`test_submission.py`、`test_draft_check.py`：**95 passed**。临时合成池放在独立 basetemp；没有接触真实冻结池或调用模型。

额外内存复现：有效三版本 manifest，reviewed 显式三项全部 `status=out_of_scope`。

```text
complete=true
review_complete=true
counts.reviewed=3
counts.deferred=3
counts.unconfirmed=3
counts.not_investigated=0
```

`coverage_receipt.py:78` 的 review_complete 实际只表示“所有清单项有显式有效声明、没有系统补集”。它不能表示“所有项目已调查”，因为 out_of_scope 明确是本题未调查，即使 explained 也不证明实际阅读。当前 UI 使用“模型逐项交代”“机械交代齐全，不代表已调查”，所以没有看到显示升级；建议后续将其改名或另加 `declarations_complete` 并明确兼容语义。不要为了把这个布尔值变 false 而改写模型原状态，也不要把所有未解决项统一当格式失败。

交付前更新：主代理已将新 API 字段统一改为 `declarations_complete`，本审查通过源码检索复核 receipt/check/专测均已同步；上述复现保留为修改前审计记录。主代理另报告全量 1,402 passed，本子审查独立运行的范围仍是前述 95 项，不混报成自己执行过全量。

本审查不认证模型将如何使用新 event/receipt 入口，更不能用 95 个机械测试替代独立语义裁决。尤其 V8 Splash 的两个实际脚本已表明：坐标与补集都正确，模型仍可能不打开关键原文而给出不完整解释。
