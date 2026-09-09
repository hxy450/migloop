# V8 Dice rep2：核心主链正确，新增了错误的输入时序排除

按 [既有核心口径](core-rubric-reconciliation.md)，**D1 core=pass、D2 core=pass**；固定事实仍为 **5 supported、1 partial**，缺项是 may-throw WARN。但本稿另有一条实质时序错误，**完整标注必须修正，不算完整通过**。core pass 不能遮住错误排除输入。

实际 GPT-5.5 / medium / native，source `b540cb2`，2026-09-09 20:18:02 UTC 完成；同题、同冻结池和 reference-v1。没有新增 oracle 门槛、模型调用或冻结修改。逐项定位和 24 个最终原文引用的事件 ID/SHA256 见 [JSON](v8-repeat-adjudication-dice.json)。

## 主链与细项

生成方 agent@v2 确实成功打开，含页面/F001/沉浸式输入和未含测试桥的 Write。Step3 的专门要求、模板/设计/EntryAbility Read、三个成功 Edit 均有据；三次生成前关键词零命中被限定范围，未倒灌成初始违规。D1 三条固定 facts 均 supported。

D2 直接要求来自 ECAT work list 与 fix-errobserver 派发，随后 SDK、三次 Edit、gate-build 实际读取/成功构建齐全；未声称运行时异常回调已经触发。前两条 facts supported；第三条仍漏 WARN，按首轮既有判例是 minor 完整性缺项，不改核心 pass。

## 实质错误：较晚副本不能抹去较早反馈

D2.boundary 原句：

> “后续存在记忆文件反馈，但时间在修复后，不能作为本次修复的先验来源。”

冻结原始 `257fed22-fb0e-48de-bee9-0791c45a90a9.jsonl`：

- L115，21:12:47.694，Write `_index.md` 已链接 global-crash-observer。
- L119，**21:12:53.922**，Write `feedback_global-crash-observer.md`，原生 ID `call_8ce3690fd9384f04ab8d47bb`，正文明确注册 observer。
- 实际 observer 修复三次 Edit 是 **21:19:24–21:19:39**，所以该反馈早于修复。

这条反证不是本裁决临时从池外补来：本次第 37 次 search，transcript **L190**，已经返回反馈 v1 和 index v1，作者 257fed22、T+6:46；修复是 T+6:53。第 33 次搜索（L173）另外看见修复后的 `_index.md@v2`、后续 Read 和其他副本。不能把较晚索引/读取当成反馈第一次存在，更不能据此排除早版输入。

正确修正是区分早期反馈与后期副本，同时保留“没有证明 fixer 实际读过该反馈”。**早于修复不等于因果来源；晚查到副本也不等于原输入晚出现。**原稿的否定理由是错误的，不只是没多写一条证据，也不是无伤大雅的措辞。

不因这次新查到的附加字段临时增加旧 reference 的核心分母：ECAT→fixer 的直接要求链仍正确，所以 D2 core pass 保留；但 `extra_false_claims` 记录 1 条 material 错误，`annotation_requires_correction=true`。这会影响管线改进建议，不能只用核心通过数宣称“归因更准”。

## 后续 10/10 状态比 rep1 完整，但引用等级仍需保留

这次实际打开 round1 final-summary 的全部 66 行（第 28 次，L156），以及真实启动探针 L168（本次第 30 次，L158）。总结记录 10/10、HARD 21/21、onNewWant×3，并保留 AppStorage 不可观测及 canonical 通道 DEFERRED；因此不再像 rep1 只停在早期 10 ERROR。

但没有打开独立 addendum 的 L256/L260 回放回执、L265/L267 读回。报告开头称“round1 记录”正确，后句“较强地证明”仍应保持“历史总结记载”的层级，不能说本调查直核了所有原生执行结果。原始 addendum 确实支持主机通道成果，**不支持桥键已被直接断言**。该边界与 raw 两稿使用相同标准。

## 机械修正与成本

46 次调用；6 次 agent 中 3 次成功；16 次 action 全成功，其中 7 次完整 ref、9 次 legacy id+seq。4 次 file/agent via 或版本拒绝。13 次 search 都带 until_ts，无 seq-only until。

首 check 有 8 errors：错写者版本、错派发窗口、search receipt 冒充 evidence、零效应 builder@v1。最终修正写者版本并删去不成立的节点/边，最后 check clear、matched；两次间没有新证据查询。最终7条显式写边对应正确真实效应窗口，不能拿首稿错边冒充最终稿仍错；但 checker 不验证上述 memory 排除理由，clear 不是语义认证。

coverage 7/7＝6 正式版本 explained＋1 实际 gitdiff/grep 自检 not_repair，处理正确。没有红节点，不能由少 warning 推断原因全对。

| 指标 | rep1 | rep2 |
|---|---:|---:|
| Input（已含 cached） | 1,616,936 | 1,595,474 |
| 其中 cached | 1,495,040 | 1,488,384 |
| Output（已含 reasoning） | 14,910 | 14,279 |
| Input + Output | 1,631,846 | 1,609,753 |
| 运行秒 | 334.963 | 331.319 |
| 工具返回字符 | 207,988 | 238,949 |

两工具稿总 token 均值 **1,620,799.5**，比 raw 两次均值 1,413,930.5 **增加 14.6%**。两稿都真正补足了 raw 缺失的生成输入，但 rep2 新增错误时序排除，省 token 门槛也未满足。必须把这两点同时保留，不能用 core pass 或 rep2 补了 10/10 状态包装成联合验收成功。
