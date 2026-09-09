# 归因输出、审计与成本的静态审查

范围：HEAD `6ffb74c` 的 `verdict.py`、`draft_check.py`、`atoms_text.py`、MCP `GUIDE`、实验 `run_pair.py`，以及两次 V5 运行记录。本稿只提出契约和验收办法，不改生产实现。现有 attribution10 十题及其反复运行均是开发集，不能称为未见测试。

## 结论

现有实现最值得保留的是三层分离：模型原话、坐标/引用/边的机械核验、以及 UI 展示。`verdict.build()` 不把可定位引用升级为语义事实，`check` 也明确不判原因真假。当前主要问题不是缺少更多字段，而是同一份长文档被生成、送入 `check`、修改后再次送入，最后再完整输出；同时最终结构仍以一张因果链为中心，不是以“哪个被修文件留下了哪些可复用事项”为中心。

建议分两步：先只做“已核草稿按哈希显式提交”的同题消融，保持 `migloop-verdict/1` 内容完全不变；确认闭环和成本后，再增加一个由后端生成的按文件投影。不要把输出结构重做、查询默认值修改和哈希提交捆成一次实验。

## 当前实现的正确边界

1. `verdict.py:43-55,84-138,179-326` 安全抽取最后一个 verdict 块，拒绝重复键、未知键、非法角色、非法节点版本格式和过深结构。旧 `migloop-verdict/1` 可以继续作为权威输入格式。
2. `verdict.py:602-719` 保存模型的 `reason/evidence/basis`，另附节点解析、引用状态、边状态和一致性告警。`document_sha256` 是规范化数据哈希，不是原始 YAML 字节哈希；两者用途不能混用。
3. `draft_check.py:31-137` 只检查声明结构、身份、坐标、引用、显式边、coverage 和一致性；`final_binding()` 还要求完整配对、可信工具来源、未截断返回、raw draft hash 与 canonical document hash 同时匹配。这能证明“最终采用了哪份已检查草稿”，不能证明草稿里的因果解释为真。
4. `run_pair.py:783-817` 先从最终回复抽取完整 YAML，再从录制的 transcript 检查最后一次 `check` 是否与最终文档同稿。当前实现不会替模型修稿，也不会用 check 输入覆盖缺失的最终稿；这是应保持的安全默认。
5. `atoms_text._render_pool_search()` 已明确按工具返回、工具输入、消息/自述、指令/注入分来源，并提示分类不判断内容真假。最多 30 个 agent、每 agent 每来源只展示最早一条，余量有标记；search receipt 只为实际展示的 first 记录建导航入口。这是线索接口，不是语义裁决器。

## 重复与无效展开

### 1. 同一 YAML 重复三次

C4 V5 的第一次草稿 4,055 字符，第二次 4,142 字符，两次 `check` 输入合计 8,197 字符；最终 YAML 又是 4,141 字符，三份结构化正文合计 12,338 字符。两次 check 返回仅 2,253 字符。Member V5 两次草稿输入更达 26,278 字符、返回 2,343 字符。

这些草稿既是模型输出，又会作为工具参数和后续上下文重新进入会话。不能只按 check 的短返回估成本，也不能从总 output/time 反推全由 check 造成：V5 的 search/action 数量和返回字符也变化了。C4 V5 为 58 calls、316,233 工具返回字符、input_total 1,428,312、cache_read 1,264,640、uncached 163,672、output 15,253、端到端 335.656 秒；美元费用为 NULL。`input_total` 已包含 cache read，不能再相加。

`GUIDE:106-109` 和 `run_pair.py:246-248` 已禁止重复完整散文，这减少了“散文 + YAML”双份，但没有解决“draft1 + draft2 + final YAML”的协议内重复。

### 2. coverage 把确定清单重新交给模型抄写

`coverage.manifest` 是账本确定生成的清单，最终 YAML 又要求逐项写 node/candidate。模型应负责每项的解释状态、理由、证据和关联缺陷，不应负责重新声明目标路径、版本、candidate 摘要等确定事实。继续让模型抄写会增加长度，也制造漏项、错 ID 和假坐标；`check` 随后再机械纠正这些抄写错误。

更小的表达是：后端给每个 manifest item 稳定的 run-local ID；模型只提交 `{item_id, status, defect_ids, reason, evidence}`。最终可归档 YAML 由后端把确定目标与模型主张合并，并明确标来源。

### 3. 链节点不应为 UI 完整性而重复

`GUIDE:107-110` 已说 nodes 只放判定必需节点，查询轨迹自动展示；但 v1 YAML 仍把节点角色、节点 reason/evidence、repair、entry、edges 和 coverage 都放在同一 defect 下，容易诱发“把所有打开过的节点再抄一遍”。UI 所需的是原因条目，不是第二份访问轨迹。显式因果边有证据才保留；普通浏览路径继续从录制轨迹生成，不进入模型结论。

## agent `since` 窗口的输入欠账

`atoms_text.render_agent()` 调用 `agent_atom(..., since=since)` 后，只展示该窗口内动作。派发词正文不会重印，而是给出“见 agent(id, v=1)”和字数（`atoms_text.py:544-547`）。这并非静默丢失，但更早的 read/inbox/inject 没有一个统一、机器可读的“本窗口省略了多少输入”摘要。模型若不再开 v1 或全文窗口，很容易把“窄窗口没显示”误写成“生成时没有”。

建议 MCP 与 UI 共用以下窗口元数据，而不是再追加一段提醒：

```yaml
input_scope:
  anchor: agent:<id>@v<N>
  included_versions: [M, N]
  prior_prompt: {present: true, chars: 1234, ref: "#…"}
  omitted_prior: {reads: 17, inbox: 2, injects: 3, other_inputs: 4}
  complete_for_agent_lifetime: false
```

这里的计数和 ref 必须由账本生成。它不把早期输入全文塞回窗口，也不声称哪些早期输入与当前缺陷相关；调查员可按 ref、全文 agent 或有界 search 补查。`GUIDE:66-69,102-103` 对主会话窄窗口和子 agent 早期 spec 的区别仍应保留。

## UI 与 MCP 的缺省值不一致

当前严格入口的实际规则是：

- `basis` 整体可省；红节点缺 basis 只产生一致性 warning，不使 YAML 失效（`verdict.py:589-598`）。
- 一旦提供 `basis`，五个字段都必须非空，双方 evidence 也必须至少一项（`verdict.py:164-176`）。
- UI 只有在 `basis` 是对象时才展开，并为缺字段显示“未填写（不推测）”、为空列表显示“未列引用”（`fixchain.html:1401-1437`）。对当前严格解析通过的新 YAML，这两个 fallback 原则上不可达；对完全省略的 basis，UI 又不显示面板。

因此 UI fallback 是历史/防御性显示，不应被描述为当前 MCP 可提交的缺省值。建议在规范化载荷中增加系统生成的状态，而不是给缺字段补模型文字：

```yaml
basis_status: not_required | absent_warning | complete | invalid_legacy
```

正常/无法确认节点为 `not_required`；红节点无 basis 为 `absent_warning` 并显示机械告警；完整 basis 为 `complete`；旧载荷的部分对象为 `invalid_legacy`，保留原字段但不补写内容。UI 显示“模型未提供”时必须标为系统状态，不能伪装成模型说过“未知”。MCP 文本、JSON payload 和 UI 应从同一枚举渲染。

## 最小的按文件沉淀契约

不要立即废弃 v1。建议把“作者格式”和“UI/归档格式”分开：

1. 旧 `migloop-verdict/1` 继续严格解析，行为不变。
2. 后端把任何有效 v1 文档投影成 `migloop-findings/1`；未来若引入更短作者格式，也投影到同一结构。
3. UI 只消费规范化投影，不直接把 YAML 文本当事实。

最小投影如下：

```yaml
schema: migloop-findings/1
ledger:
  id: <系统核到的账本身份>
  status: matched
files:
  - file:
      path: entry/src/main/ets/pages/X.ets
      versions: [<系统核到的返修版本>]
      source: ledger
    items:
      - id: <文档内唯一 id>
        defect: <问题/变化短语，模型主张>
        repair:
          before: <解析后的节点或 null>
          after: <解析后的节点或 null>
          evidence: [<逐条带定位状态>]
        causes:
          - node: <解析后的节点>
            role: <模型角色>
            reason: <模型原话>
            evidence: [<模型引用 + 系统定位状态>]
            basis: <模型原字段或 null>
            basis_status: <系统枚举>
        recommendation: <模型建议；没有就 null，不自动生成>
        boundary: <模型原话；没有就 null>
        audit:
          semantic_checked: false
          advisories: [<系统机械告警>]
```

必须满足的归属规则：

- 文件桶来自账本 repair manifest 或已解析的真实 `repair.after`，路径、版本、写者、diff 是否存在、coverage 目标和引用定位状态均为系统事实，不能由模型自报后直接标绿。
- `defect/reason/recommendation/boundary/role/basis` 永远标 `source: model` 或继承模型来源；可定位 evidence 只说明位置存在。
- 一个 defect 涉及多个实际修改文件时，可在多个 file bucket 下放同一 item 的引用，正文只存一份并以稳定 item ID 去重。没有可核修改文件的事项进入 `unbound_items`，不能虚构文件桶。
- recommendation 与已实施 repair 分开：前者是建议，后者必须有账本版本/patch 证据。不能因建议合理就显示为“已修”。
- v1 没有 recommendation 字段时保持 null；不要从 notes 或 reason 猜。若以后需要模型直接作者化建议，应新增版本化 schema，而不是放宽 v1 的未知键规则。
- 原始 YAML、规范化投影、机械审计和运行 metrics 分别保存。投影失败不覆盖原文，旧 YAML 始终可重新载入。

## 以文档哈希提交已检查草稿

这是最值得先试的一个成本改动，因为它只去掉最后一次整稿重写，不改变调查路径、schema 或语义内容。

建议新增一个很小的最终引用块，例如：

```yaml
schema: migloop-verdict-ref/1
ledger: <id>
draft_sha256: <最后一次 check 输入的原始字节 hash>
document_sha256: <规范化文档 hash>
```

可信闭环必须同时满足：

1. 最终引用是模型显式输出，不由 harness 猜“最后一个看起来好的草稿”。
2. 仅在本次 run 的完整 transcript 中寻找同 provider、同 `check` 工具、同 sid/ledger、完整 call/result 配对且未截断的调用。
3. 从那次调用的原始 `draft` 参数取回字节；重新严格解析 v1，核 raw hash、canonical hash、check 返回的两个 hash、身份及 issue digest。hash 不是服务器签名，可信性来自本次录制的调用身份和完整配对。
4. 匹配后，harness 把这份**已实际作为 check 输入交付过的文本**另存为 `verdict.yaml`，再走现有 `verdict.build()`。不得从 canonical JSON 反序列化“还原”一份模型从未交付的 YAML。
5. transcript 缺失、call 不完整、正文被截断/改写、最后 check 不匹配、最终 ref 指向旧 run，全部硬失败；保留原回复和失败诊断。可提示模型重新输出完整 YAML，但不能静默修复、覆盖原 run 或跨 run 捞草稿。
6. `mechanical_clear` 仍不表示语义正确；`needs_review` 是否允许显式提交应由产品策略决定并在 ref 中带 issue digest，不能通过删问题清零。
7. 现有完整 v1 YAML 路径继续支持，因而历史报告和无 transcript 场景向后兼容。

V5 已证明 raw draft hash 与 canonical document hash 都有必要：格式差异可以不改变 canonical 文档，而原始传输保真仍需 raw hash。`d14853c` 修复的是 reviewer 对显式 text 正文的字节保真，不是把 JSON 比较放宽，也没有更改旧 metrics。

## 单一优先实验与公平指标

先只实现“最终 ref 绑定最后一次已验证 check 草稿”，不要同时改 GUIDE 查询策略、agent 窗口、按文件 schema 或语义检查。

实验要求：

- 开发调试可复用 attribution10，但必须明确它已见；正式结论用另行冻结、未参与设计的新题集。
- 同一题、同一冻结 pool/source/common task、同一具体模型与 effort、同一 native transport、同一超时和工具白名单；baseline 输出完整最终 v1，variant 输出 ref。配对顺序随机化，每次结果逐条保留，不挑最好一次。
- 质量硬门：最终 canonical document hash 与最后一次真实 check 完全匹配；UI 加载后的 files/items、模型原话、引用状态和告警与完整 YAML 路径逐字段一致；失败/无 transcript 不得产出结构化成功；独立语义裁决不因 arm 改变。
- 成本主指标：final answer 字符、output tokens、input_total、uncached input、cache_read、端到端 wall。辅助指标：check draft chars、check return chars、工具 calls/return chars、重试次数、成功载入率。`input_total` 与 cache_read 分列，不相加；NULL 美元保持未知。
- 解释边界：该实验只能测“省去最终全文重写”的影响。若模型因新协议改变调查长度或 check 次数，需单列；不能把总 token/时间变化全归因于 hash ref。

成功标准应先看闭环无退化，再看成本：所有配对题均能从同 run 原始 check 输入恢复完全相同的 canonical 文档，零静默恢复/跨 run 绑定/假成功，语义裁决不退；随后报告每题 output、input 和 wall 的变化。只有在这些门通过后，才值得继续试“基于已绑定草稿提交小 patch”来减少第二次完整 draft；那是下一项实验，不应与本次混测。
