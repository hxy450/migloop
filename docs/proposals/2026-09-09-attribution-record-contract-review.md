# 归因条目、尾后事件与 coverage 的最小统一契约评审

## 结论

建议把目前被迫挤进版本坐标的三种概念拆开：

1. 'target_file'：条目讨论哪个文件，是任务范围/模型声明，不是修复版本事实。
2. 'event_claims'：某个原始事件承担了什么作用；事件可挂到真实 agent 节点作调查锚点，但事件本身不是 agent/file 版本。
3. 'coverage_manifest'：系统认证的待交代清单及其补集；补集可以机械标为“未调查”，不能批量冒充 'out_of_scope' 或 'explained'。

不建议直接放宽 'migloop-verdict/1' 的未知键。它当前以严格 schema 防止静默吞错；应保留 v1 原样兼容，待契约稳定后用 'migloop-verdict/2'（或独立实验 schema）显式启用。

## 1. 文件作用域与历史 repair 分离

V1 的 'findings.project' 只按已解析的 'repair.before/after' 分桶。没有真实 repair 端点的条目只能进入 'unbound_items'。这会奖励模型把同一路径上较宽的两个版本写成 repair 区间，即使动态脚本没有形成对应版本，或条目只是调查该文件。

建议每条 defect 增加模型原文：

    target_file: entry/src/main/ets/pages/MemberCenterPage.ets

check/build 另生成不可由模型自报的解析结果：

    target_binding:
      declared_path: <模型原文>
      task_path: <harness/check 的 file 参数>
      task_scope_match: true | false | unknown
      canonical_path: <仅在可无歧义解析时填写>
      source: model
      task_source: harness
      creates_node: false
      semantic_checked: false

规则：

- 'target_file' 不带版本，绝不调用 'resolve_node'，不创建 'file@v'、repair、writer 或 evidence edge。
- task path 可以在账本中没有版本；它仍是任务范围，但不是历史文件原子。
- 精确规范化可以接受任务相对路径与唯一工程根绝对路径；同名后缀多匹配必须报歧义，不能 first-wins。
- 'repair' 继续可选且语义不变。只有真实 before/after 节点存在时，才表示模型声称的历史修复区间；没有端点就省略。
- findings UI 可按 'target_file' 展示条目，但标为 'scope_association'。只有 repair 端点产生 'historical_repair_association'；二者不可合并成“已修文件”。
- legacy v1 没有 'target_file' 时保持现有 'unbound_items'。即使 harness 有单一任务文件，也只能另列 'task_scoped_legacy_items'，不能静默改写模型文档。

这样 Member S3 的批量 mask 脚本可明确“本条针对 MemberCenterPage”，同时保留“脚本未形成可导航文件版本”的事实；不再借 v9→v10 或最终 v16 安置条目。

## 2. 尾后动作使用事件声明，不借最近 agent@v 承担时态

尾后 action 有真实原文、时间、调用状态和引用，但没有新的 effect version。把作用写进最近 'agent@v40' 的 role/reason，会把“v40 后发生”误读成“v40 状态中已经发生”；据此画边还会捏造文件版本。

建议 defect 增加：

    entry_events: [E1]
    event_claims:
      - id: E1
        event: "#a68daf...:15731@L592"
        anchor: agent:agent-a68daf...@v40
        temporal_relation: after_anchor
        role: 进入·错
        reason: |-
          <模型对该事件作用的解释>
        evidence: ["#a68daf...:15731@L592", "#af0e...:17286@L23"]
        basis: <红角色沿用 expected/actual/counterevidence>

机械解析另产出：

    event_binding:
      owner_agent: agent-a68daf...
      seq: 15731
      use_line: 592
      call_status: returned
      effect_version: null
      context_anchor: agent:agent-a68daf...@v40
      anchor_match: true
      creates_node: false
      creates_edge: false
      semantic_checked: false

规则：

- 'event' 必须是可唯一解析的原始 action 引用；check 校验 owner、行、块、调用配对和当前 ledger。
- 'context_anchor' 由账本按事件发生前最后一个真实 effect 节点给出，最好由 action 输出供复制；模型不能自行按时间“就近找版本”。事件前无真实 agent 版本时 anchor 为 null，事件仍可展示。
- 'temporal_relation' 由系统重算。'after_anchor' 是时序事实，不是因果关系。
- event role/reason/basis 仍是模型主张。红事件同样要求 expected、actual、反证；引用通过不认证解释。
- 'entry_events' 可把首次引入定位到事件，而不把 anchor 节点标红。节点 role 只描述该真实版本时的状态。
- event 不参与 file/agent 拓扑，不生成 repair 端点、版本、读写边或 blame owner。UI 可用虚线/徽标指向调查锚点，并写明“事件，不是版本节点”。

Member #15731 可据此承载“生成 private static helper，后续构建报跨 struct 私有访问”的主张；v40 仅作调查上下文。后置 builder 的真实 v15/v16 仍按账本版本表示。

## 3. Coverage 使用认证清单与未调查补集

当前让模型逐项复制约 31 个 candidate/version 并重复 'out_of_scope'，成本高且容易误读：逐项存在只证明机械对账，'coverage_complete=true' 不等于逐项读过或解释正确。

建议 'sessions(file=目标)' 返回短 receipt：

    coverage_manifest:
      schema: migloop-coverage-manifest/1
      ledger: <ledger identity>
      target: <精确任务路径>
      manifest_sha256: <有序 version/candidate 身份及必要类型字段的 hash>
      versions: 7
      candidates: 31

V2 文档只写有实质判断的行：

    coverage:
      manifest_sha256: <照抄 receipt>
      reviewed:
        - node: file:...@v11
          status: explained
          defects: [S4]
          reason: |-
            ...
          evidence: ["#..."]
      complement:
        status: not_investigated

check 重算 receipt 并输出彼此独立的计数：

- 'manifest_identity_valid'
- 'manifest_items_total'
- 'reviewed_rows_valid'
- 'not_investigated_items'
- 'mechanically_accounted'
- 'semantic_review_claimed'（模型逐项声明，仍不认证真假）
- 'trace_opened_items'（系统按认证调用轨迹另算，不能由模型填写）

关键约束：

- complement 只允许 'not_investigated'，不能默认成 'out_of_scope'、'not_repair'、'unresolved' 或 'explained'。
- 'mechanically_accounted=true' 只表示 receipt 与 reviewed+补集无缺项/重复；UI 禁止显示为“全部已解释”。
- reviewed 行继续要求证据引用；仅 receipt 不证明模型看过任何 item。
- receipt 绑定 ledger、精确 target、清单排序/类型和 schema；跨账本、跨目标、删改 item、旧 receipt 都 fail closed。若还需跨 harness 防混，再绑定 harness identity。
- 离线 findings.json 保存 receipt 与系统展开后的补集身份；展开行标 'source=system_manifest'、'review_status=not_investigated'。
- V1 coverage 列表继续原样加载，不能自动压缩后改变旧文档含义。

## 最小统一输出形状

V2 defect 最少包含 'id/title/target_file'，真实历史存在时才写 'repair'；真实节点解释放 'nodes'，无版本动作放 'event_claims'，进入点分别用 'entry' 与 'entry_events'，'edges' 仍只收可核账本边。顶层 coverage 使用 receipt、reviewed 和 not_investigated 补集。'target_binding/event_binding' 与展开 manifest 属系统投影，不回写模型原文。

这保持三个正交问题：

- “条目谈哪个文件”不回答“哪个版本被修”；
- “事件发生且可定位”不回答“它创建了哪个版本/是谁的节点状态”；
- “清单无遗漏”不回答“模型逐项调查或解释正确”。

## 兼容、防伪与成本风险

- 使用显式 v2，保留 v1 loader/projector；不要让同一 schema 在不同程序中漂移。
- target/task mismatch 应报错或显著 warning，不能用 root 猜补；多文件任务使用 harness 白名单。
- event 引用必须绑定同 ledger 的真实 call；消息正文里的“#123”或模型自造 id 无效。event 证据不进入 '_rel_read/_rel_write'。
- manifest hash 只是服务端可重算的清单身份，不是查看证明或语义签名。
- repair 缺失不能从 target/event 推导；event 里出现写命令也不能自动生成 file version。
- legacy UI 同时显示“历史 repair 未绑定”和“任务范围为 X”，避免 scope 分桶掩盖证据缺口。
- 主要节省来自删除 31 条重复 coverage reason。新增 target/event 很短；receipt 应只传 hash+计数，离线 UI 用系统 sidecar 展开。
- 风险是 schema/guide 学习成本和 event role 被误画成节点 role。应比较 input total、uncached、output、wall、checked draft 字符、check 次数、伪 repair/node/edge、event 时态错误及未调查披露。核心语义不退化后才能算成本改善。
- 已有十题和 Member/C4 是开发集，只能作开发证据。

## 由 V6 失败构造的验收测试

1. **无 repair 端点**：正确 target_file、无 repair 时，条目进入文件 scope 但 historical repair 仍 unbound；节点数和版本数不变。
2. **拒绝宽 repair**：模型用最早/最终版本包住未入账脚本事件；target 匹配不能使 repair 获得事实背书。
3. **Member #15731 尾后事件**：绑定真实 #15731，context anchor=v40、effect_version=null；UI 不把 v40 标成事件已发生，不画 event→file 写边。
4. **后续编译反证**：event claim 可引用 builder private-access 报错；check 只认证位置，不认证因果。
5. **未来版本防投影**：#15731 早于 v15/v16 时，不得因路径相同把 event 绑定到这些版本。
6. **31 项补集**：模型 reviewed 2 项时，结果为 manifest accounted、reviewed=2、not_investigated=29、semantic complete=false。
7. **禁止 complete=explained**：零 reviewed+合法 receipt 仍可机械 accounted，但 UI/API 不得出现“全部解释/全部看过”。
8. **receipt 防混**：跨 target/ledger、乱序删项、旧 harness identity 均拒绝；不回退早期 receipt。
9. **legacy v1**：旧 coverage 与 unbound_items 语义不变；新 projector 不把 harness target 静默写成模型 repair。
10. **公平成本回归**：同一 Member 任务比较 V1 31 条列表与 V2 receipt；若 output 降低但核心归因、未调查披露或可核证据退化，不算通过。

## 推荐顺序

先做 system-owned coverage receipt 与 UI 的 'not_investigated' 补集，收益最大且不触碰账本。第二步加入 target scope 投影，仍不改 repair。最后试 event claims；它需要 check、viewer、findings 和角色展示共同支持，最容易因 UI 连线重新引入伪因果。每一步都保留 v1 兼容路径并独立验收。
