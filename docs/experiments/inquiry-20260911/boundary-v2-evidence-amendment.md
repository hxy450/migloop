# 有界归因 v2：附带原始证据的裁决补充

2026-09-14。独立复核固定 `raw-high-i20-match-20260912` 与 `temporal-f10-v1` 的原始交付物。本补充只纠正证据判读及其理由，不修改既有 review JSON、results、金标、模型报告或调查员输入，不重跑模型。

## 证据合同

用户的产品设计允许调查员只提交 key、time、reason，由产品附带原始证据。因此工具组的受评交付物包括编译后的 `verdict.json`，不能只审阅提交的 `verdict.yaml`。适用以下对称原则：

- 既有 reason 加上已附原始证据，若直接支持一个具体判断，就算报告已提供证据。原文内已有的前后代码、任务理由和约束不必再复制成散文。这与 raw 正文加原始行号引用等价。
- 自动找到一条读写边不认证整段 reason。只能认可该原文实际支持的窄判断；材料中存在某条指令不等于相关执行者收到它。
- 审阅者可以打开已附引用核验，但不能补找新的关键输入、收件或责任关系，替报告构造原本不存在的判断，再给它完整分。
- 缺少重复叙述不扣分；缺少必要的因果关系仍可判 partial。子判断成立不自动让包含其他实际修改的冻结家族整体成立。

这具体澄清了 [bounded-attribution-v2.md](../file-first-10/bounded-attribution-v2.md) 第 34 行“报告已有可核原始坐标但没有复制长段原文，不算缺证据”的适用范围。

## F10-03：明确错误与保留缺口

原裁决：[boundary-v2-full-review.json](boundary-v2-full-review.json) 第 443 行；汇总：[boundary-v2-full-results.md](boundary-v2-full-results.md) 第 50 行。它们称工具的 `export class Dice` 仅为结果标签，未说明原始内部类与新访问范围的对照。这个概括遗漏了交付物已经附带的原始编辑。

工具交付物位置：

`C:/Users/hongy/projects/_migloop-evidence-delivery-20260913/temporal-f10-v1/F10-03/runs/inquiry/rep1/verdict.json`

其提交原稿 SHA256 为 `e5f3a25936d37c99d385f3e1cb00c4a58f0e687bbf532f3d0055ee83c6ac93ee`，report id 为 `30687fa74c584280`。

### export 子判断：应认可已成立

编译稿第 603 行起的节点 `card:n-9a72930db43f38e0`：

> 正常测试准备改动：export class Dice，保持同文件内聚契约；不是按钮缺陷。

节点实际关联 `56c56621f98c3e50:3231:6d01d1a0a9b4025a` 与 `56c56621f98c3e50:3233:3d90e08325ab65c5`。源坐标为 `dice-root:3231/3233`。第 3231 行是实际 Edit：旧代码为 `class Dice`，新代码为 `export class Dice`，同时加入：

> export 仅为 arkxtest 单测可见性放宽（arkts-ut-verifier Step1 设计决定）；不抽独立文件——spec 服务层契约「内聚 Index.ets」

第 3233 行确认编辑成功，时间为 `2026-09-03T18:39:07.441Z`，晚于固定生成截止。工具已经给出“正常测试准备、保留内聚契约”的判断；原文直接补足其前后代码与具体测试动机。这不是审阅者新增因果推理。固定 raw 报告第 77–95 行也使用 `dice-root:3231/3233` 支持同一判断。工具无需再复述一段跨文件 import 说明才能让这一子判断成立。

### 三个测试 ID：已有前后证据，家族仍有具体缺口

第 624 行起的节点 `card:n-f8bc50fc9871719b` 明确说明三个 ID 属于正常 UI 测试仪器改动、不改变业务或视觉修复。自动关联 `agent-aa1ccf93d575837a2.jsonl:22/23,25/26,28/29`。三次 Edit 分别添加 `main_root`、`main_toolbar_title`、`main_dice_placeholder`，均在新代码注释标明“UI 测试锚点”与 `id-inject §1`。

因此不能说工具缺少 ID 修改、用途或前后对照证据。但这几个输出引用没有关联实际 ID 设计正文/派单的输入收件。raw 第 55–65 行还引用了 `dice-root:3329` 的三项设计与 `dice-root:3342` 的明确注入派单。按照固定 v2 对后置输入的要求，工具整个 `test-integration` 家族仍保留这个未闭合的 ID 设计/交付关系；本补充只认可 export 子判断，不把家族直接升级。

### 注释：保留 D-002 的证据存在，政策触发关系未闭合

第 653 行起的 cleanup 节点 `card:n-95f61ab60dbf9da6` 关联 `dice-cleanup:49/55/66` 等实际 Edit。第 66 行把 TODO/占位注释改写为：

> UI 测试锚点：未掷态骰面槽（A2 变体，accessibilityText 绑 string.json:todo，id-inject §1；D-002 忠实复刻）

所以“只有清理结果”不足以准确描述其全部附证：既有 D-002 与真实 todo 绑定的保留已有支持。但节点 reason 只写可观测性和注释整理，没有说明后置检查为何要求去除注释 token、同时保留业务资源；实际派单 `dice-cleanup:1` / `dice-fix-root:84` 也未关联到该节点。`comment-policy=partial` 保留，缺口限定为政策触发及交付关系，不能说 D-002 保留证据不存在。

`logging=partial` 亦保留：报告没有指出 `console.error` 由视觉返修先引入。核验该来源应看 `dice-visual:68/69`；不能仅凭最终 hilog 清理节点代写这个阶段判断。

## F10-04 与 F10-07：无需改变家族状态

F10-04 工具 summary 的“Base-3 handoff 明确要求这两个 debug 开关”混淆了两个来源。`base3:272` 只明确列出 `HttpLog.setDebug(isDebug)`；`AppTrackConfig` 的启动注入要求在 `slice11:78` 实际收到的源码第 195–205 行。工具编译稿附证包括 closer/修复操作，未补齐这些输入到具体遗漏输出的关系，故 debug 家族的 partial 有实质依据。

时序也需精确表述：`slice11:323` 在 16:09:30 已提供一次 `cross_slice_edits_needed`；工具说的“其余无”则是 `slice11:349`，16:35:38，晚于 closer 16:35:16 的具体编辑。后一回执确实晚，不能据此推断此前不存在 F001 交接。

F10-07 两组的测试桥、异常观察者均已说明后置 §F/ECAT 输入、对应输出与原作者义务未证边界，保留 established。raw 具体位置为报告第 23–33、47–76 行；工具为 summary 及测试设计/观察者节点。工具初始 writer 标红与自己保留的责任边界不一致，属于应独立记录的图义问题，不撤销后置需求解释。

## 对固定 28 家族分数的实际影响

| 判断 | 本补充结论 | 对 established 家族数的影响 |
| --- | --- | ---: |
| F10-03/export 子判断 | 认可成立，纠正原裁决理由中的证据遗漏 | 0：它不是独立冻结家族 |
| F10-03/test-integration 家族 | ID 设计/交付关系仍未闭合，保留 partial | 0 |
| F10-03/comment-policy | 承认已附 D-002 保留证据，收窄 partial 理由 | 0 |
| F10-04/debug、F10-07 两家族 | 保留既有状态 | 0 |

本次补充没有使工具 established 从 7/28 增为 8/28，也没有改变 raw 的 13/28。它纠正了具体解释与子判断，不是重新穷尽 56 项的另一轮评分，更不是确认其他裁决全部正确。

## 原始证据定位约定

下列路径均位于 `C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/`；行号指物理 JSONL 行。

| 别名 | 相对路径 |
| --- | --- |
| dice-root | `dice-entry/pool/81e0a463-c9d3-4a7a-a671-b7f064830af1.jsonl` |
| dice-fix-root | `dice-entry/pool/2f01bcdc-0a92-4961-a64d-5b181f03b3d3.jsonl` |
| dice ID injector | `dice-entry/pool/81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-aa1ccf93d575837a2.jsonl` |
| dice-cleanup | `dice-entry/pool/2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a228e9716d833cbf3.jsonl` |
| dice-visual | `dice-entry/pool/81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a4874344c8fb6228d.jsonl` |
| base3 | `member-center/pool/9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-abase3-network-f9a03317492be8c4.jsonl` |
| slice11 | `member-center/pool/9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aslice11-startup-50a0622bcfe4a588.jsonl` |

固定 raw 报告位于 `C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/raw-high-i20-match-20260912/runs/<F10-ID>/rep1/report.md`。本补充属于审阅材料，不作为调查员 skill/prompt 或模型输入。
