# V12 Codex C1–C4 独立语义裁决

快照：2026-09-09 23:01:19 UTC。已裁决 2/8；未完成项保留为 pending，不记零分、不以草稿替代最终交付。

冻结调查源码 e67d7d7；沿 reference-v1 与 V9 Codex 相同 core 口径。最终 reference 需在同 run 的真实 check 输入中通过身份和双哈希认证；随后回读原始转录。check/coverage 不证明语义正确、看过全文或任务事实找齐。未访问私人 holdout。

| case | rep | 状态 | core | 完整注释 | 固定事实恢复 |
|---|---:|---|---|---|---|
| C1 | 1 | pending | — | — | — |
| C1 | 2 | pending | — | — | — |
| C2 | 1 | adjudicated | accepted | accepted_with_omission_and_invalid_coverage_metadata | supported / supported / supported / omitted |
| C2 | 2 | pending | — | — | — |
| C3 | 1 | adjudicated | accepted | accepted_with_recoverable_omissions | partial / supported / supported / partial |
| C3 | 2 | pending | — | — | — |
| C4 | 1 | pending | — | — | — |
| C4 | 2 | pending | — | — | — |

## 分母与边界

每 rep 固定事实数 C1=3、C2=4、C3=4、C4=5；不新增临时必答项，也不使用分数阈值重定义 core。参考文件 SHA-256：1d412a2779bb8d94bbc81d2698b4ba8b92ec97cb9acaccfcb158669476edeae5。26 条冻结参考原始记录的 SHA 已逐条核对。来源中的生成/修复/reviewer 报告只证明有人如此主张，不能替代源码、实际补丁或运行验证。

## C2 rep1

正确区分 fixer 的统一 WorksService 主张、reviewer 的同 DAO/同事件反证、源码与运行证据缺失；未把报告等价判断升级为业务事实，保留事务/异常/时序/刷新未知。按 V9 相同 core 口径接受。

完整注释：accepted_with_omission_and_invalid_coverage_metadata；需要纠错：true；需要补全：true。

- C2-F1 — supported：明确恢复历史唯一 post-insert publisher 记录并标为早先记录，而非直接业务源码。该语句虽无专门 action 引用，冻结原始 R2 L4934 确实支持。 最终稿短摘录：“PptRecordRepository 为唯一 post-insert WorksLibraryUpdated(CREATED) publisher”。

- C2-F2 — supported：准确引用 fixer 摘要的 WorksService 改动方向、目标路径及 CREATED，自述与实际行为严格分开。 最终稿短摘录：“生成完成统一走 WorksService 入库并发布 CREATED 事件”。

- C2-F3 — supported：准确恢复 reviewer 同 DAO/同事件及 wrong_edit 原话，并拒绝仅凭它认定行为等价或修复无效。 最终稿短摘录：“不能升级为已验证事实”。

- C2-F4 — omitted：未交代 Round 2 Works canonical 被系统联系人污染。原文 R2 L7574 及最终所引 #4832 输入 L7581 均有该边界，但最终稿没有恢复。

边界：无目标源码节点时使用真实 agent@v218 与 3 个事件；报告写回事件是文档效应，不是 PptGenerationViewModel 修改。后续 build/install 不等于 Works 呈现验证；未知内容和零命中不当不存在证明。

额外错误断言：本次未发现。

交付：accepted / checked_draft_ref；check #32 (call_SDnhMRk5CL3CjsZK8kUBXTbg)，状态 needs_review，最终记录 L198。原稿 SHA eaecbbed5508e9d0ba06ccda6450745ec33b537c3454d5848624cb102e5665fa；canonical SHA 90f83d770cda4ac39e07cb48e9321c1f9a50884ce5d5b8eb46d72724883922c4。reference 认证成功，第二次 check 与最终稿相同；仍 needs_review（3 errors + 1 warning）。全零 manifest_sha256 被模型明确称为机械占位，不是暗中伪造业务事实，但它不是有效 coverage receipt，必须另列需纠正的交付元数据。不能称完整机检通过。

定位：身份绑定 true；节点 1/1；事件 3/3；9 个去重 action 原始定位。原始路径、物理行、call_id、时刻和逐记录 SHA 见同名 JSON；定位成功不证明语义。

关键参考原始出处：

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L4934 / call_nfwjmlicObG8LyPwc3f5ZPgb：exactly one post-insert WorksLibraryUpdated(CREATED) publisher: PptRecordRepository

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L7574 / call_rHkspr6Fzhub0xEU83VOrdsF：BLOCKED_PWorksFragment: canonical 误采集系统联系人; WorksFragment_generated_work_missing

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L7683 / call_BYzt9sjwzhzxLipXgCsr6q4Y：生成完成统一走 WorksService 入库并发布 CREATED 事件

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L7680：reviewer: 同一 DAO 且已发布 CREATED；替换未改变行为

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L7686 / call_XHYFotPT6f6XWmbIyXSilnMV：写回 Works wrong_edit 到 visual-fixer-summary.md

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L7825：最终消息复述 Works 等价门面替换未触及真实根因

## C3 rep1

正确恢复 Monitor/visibility 与独立挂载两个来源假说及 reviewer 反证，明确它们不是源码/设备验证；真实根因和修复结果保持未知。沿 V9 相同 core 口径，不把可恢复的初始输入缺项重新设为核心否决。

完整注释：accepted_with_recoverable_omissions；需要纠错：false；需要补全：true。

- C3-F1 — partial：有早期 Slice 1 槽位计划与生成者 5110ms/panorama 自述；未恢复 Kotlin/layout/snapshot 初始输入。 最终稿短摘录：“5110ms progress flow 与 panorama auto-scroll 已实现”。

- C3-F2 — supported：明确 transient/occlusion capture debt，并定位 Round 0 low_confidence 工单。 最终稿短摘录：“IMPL_MISSING/P2/low_confidence”。

- C3-F3 — supported：Round 1 reviewer Monitor 反证与 Round 2 currentStep===5 独立挂载报告均准确，均标来源主张。 最终稿短摘录：“第 6 步移出缓存 Swiper，currentStep===5 时独立真实挂载并传 active/progress”。

- C3-F4 — partial：明确 final manual review 未消除；fresh capture 仅写作下一步建议，未恢复历史最终 need-info/fresh-capture 欠账记录。 最终稿短摘录：“Round-2 最终仍有 GuideInit 两项低置信 manual_review 债”。

边界：未将 reviewer 当金标；未把 Round 2 无 GuideInit wrong_edit 标记等同实际视觉通过；无目标正式 file 版本或源码 diff 时用真实 agent/event，而非 file@v0。

额外错误断言：本次未发现。

交付：accepted / checked_draft_ref；check #35 (call_a6PMnfyAFnFUs8WVMRJj7d5i)，状态 mechanical_clear，最终记录 L191。原稿 SHA 7352b967c13f8d6c8326672bfbd38c4d06bd610648fc09df63c7b9e54455d15a；canonical SHA 22558f07d6d7f0ad39c342a45d27c67146944dcfac0c8f165c8d865285a794c1。check mechanical_clear 且 coverage expected=0 只认证外壳；不是本题 4 个事实均恢复。

定位：身份绑定 true；节点 4/4；事件 6/6；8 个去重 action 原始定位。原始路径、物理行、call_id、时刻和逐记录 SHA 见同名 JSON；定位成功不证明语义。

关键参考原始出处：

- rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl L2013 / call_b5NIkmLWkXtjLgHjdKGnc9WQ：GuideInit Kotlin/layout/snapshot; 展示引导加载动画并倒计时进入首页

- rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl L2781：GuideInitComponent: 5110ms progress flow ... implemented

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L5879 / call_8PsHI1kc3azM3FxOJBhI8I0j：GuideInit tickets confidence: low_confidence

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L6957：reviewer: Monitor 未建立新渲染链，progress 已响应式消费

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L7683 / call_BYzt9sjwzhzxLipXgCsr6q4Y：currentStep===5 独立挂载；缓存子树首次 inactive 构建假设

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L7653：need-info: GuideInit fresh capture

- rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl L7825：GuideInit 仍有两项低置信人工复核债

## 审计保留

调查源码 SHA：526e8f61bd30b14b67b742e8c52dbebde933b04d09d9a77eca92434a4188c658。每份的 source/pool/task 完整性、runner SHA、最终稿与原始记录哈希均在 JSON 单独保留。用量仅作描述，不进入语义评分。未修改 run、冻结源码、参考分母或其他评分文件。
