# Inquiry MCP 调用与交付

三个工具：`investigate(requests=[...])` 批量 1–24 个独立查询；`page` 续结果正文；`submit(document="完整 YAML/JSON")` 保存结论。file/agent 等是 investigate 内的 op，不是独立 MCP 工具。不存在 guide/sessions/batch/check 工具。

## 时间、引用与续读

- 查询使用含时区 ISO 的 `at`，可选 `since`，闭区间。生成输入另开生成期范围，不沿用修复窗口的 since。版本/via 不作为查询参数。
- 每个 file/agent 查询返回 `scope_id`（`s-file-... / s-agent-...`）。继承 scope 时不要再混写 key/at/since。`WRITER.input_scope` 是写前输入范围；`write_scope` 是写入时刻；`WRITER.scope` 是查询截止，可看写后。
- 原文引用为 `e-...` 或完整 ref。`RESULT` id、scope id、link id 不是原文，不能猜前缀或截短身份。
- `next` 是记录列表下一页；`END FRAME next` 是本结果正文字符续帧。两者均读完才是本查询结果读完。每帧最多 9000 字符，选定全文保存在服务端，不必重新查。
- `page(result_id="返回的 RESULT id", offset=返回的整数)`；可批量 `page(requests=[{result_id,offset}, ...])`，1–4 项，各用自己的 offset，不与单条参数混用。
- 限额 `limit:1..100`（通常20，outline100）；`terms` 最多8个字面词，OR 匹配，不是正则；更换词/范围从 offset=0 开始。优先批量2–4项相关查询，避免一次塞满大量原文。
- 读取以返回时刻计；未知时间、未返回、失败不冒充确定输入或写入。缺原生关系仍可看原始脚本、返回，不能假设未发生。

## 常用查询

```json
{"op":"file","key":"唯一文件后缀或完整路径","since":"生成截止ISO","at":"观察截止ISO","view":"calls","limit":100}
{"op":"file","key":"同一文件","at":"生成截止ISO","view":"outline","limit":100}
{"op":"agent","scope":"返回的写前input_scope","view":"inputs"}
{"op":"agent","scope":"s-agent-...","view":"messages","limit":100}
{"op":"search","scope":"s-agent-...","terms":["关键词一","关键词二"],"limit":100}
{"op":"search","kind":"pool","at":"阶段截止ISO","since":"阶段起点ISO","terms":["关键词"],"group_by":"agent","limit":100}
{"op":"catalog","kind":"agent","q":"名称子串","limit":100}
{"op":"open","ref":"e-...","at":"涵盖该记录的截止ISO"}
{"op":"open","source":"逻辑转录文件名","line":123,"at":"截止ISO"}
{"op":"open","ref":"e-...","scope":"s-file-或s-agent-...","terms":["关键属性"],"context":6}
{"op":"blame","key":"文件","at":"生成截止ISO","terms":["代码片段"],"limit":100}
{"op":"file","scope":"s-file-...","view":"neighbors","limit":100}
```

file 的 `records` 是全部相关记录索引，`calls` 是相关调用（含未知脚本及其结果引用），`changes` 给原生 Write/Edit 参数全文，`outline` 给原生增删摘要；整文件 Write 不与假定前版重放。calls 默认折叠已知只读形状，`include_reads:true` 展开；折叠不影响 records/search。

agent 的 `inputs` 给原生读文件、初始/近期消息、工具返回三个重叠渠道，不是完整有效上下文；`messages`、`returns`、`records` 和 search 可继续查。工具返回包括失败/未配对，不能将返回文档内的 PASS 当真实执行。

pool/agent search 可加 `view:returns`。返回的 actor 分布和 `NARROW SAME QUERY` 保持时间/关键词，可转查其它检查者。records/messages/returns 支持 `order:newest|oldest`，其它 view 不支持。

open 默认完整原生正文，`pointer:""` 看完整 JSON 记录；显式 JSONPointer 选择字段。可给 terms 和 context(0–50)取所有字面匹配窗口，返回 literal_counts 和省略范围；窗口不是完整语法块。声称属性缺失，直接搜属性本身并核相关分支，不凭邻近片段。Edit/patch/未知写脚本的参数包不被关键词裁剪。`request_context` 给回执所答的真实调用，展开原请求核对象与时刻。

diff 比两个明确原文：`{op:diff,before:ref,after:ref,before_pointer:字段,after_pointer:字段,at:ISO}`。blame 只列原生片段演变，不认证首次作者或脚本没改。

neighbors 与 UI 共用投影，默认上游；`direction:downstream` 看下游。read 是 file→agent，write 是 agent→file，dispatch 是 parent→child。关系支持身份/发生时间，不自动证明内容因果传播。

## YAML：同一份原稿、节点原因与证据

```yaml
schema: inquiry/1
target: {scope: "目标文件修复区间的 s-file-..."}
summary:
  generation: 完整说明生成要求、实际输入、偏差如何进入与保留；区分已证与假设
  repair: 后续具体修了什么，哪些是修复中新问题，实际验证到哪里
  unknown: [文件级未查明边界] # 无则 []
  findings: [A] # 总结涵盖的全部 finding id
recommendations:
  - target: 要改进的具体生成或交接环节
    action: 具体怎么改；不宜改时说明暂不改
    reason: 为何这项行动针对已发现的问题，而非泛泛补测试
    validation: 如何验证预期改进；效果仍待验证
    findings: [A] # 本行动针对哪些 finding
findings:
  - id: A
    title: 简短原因
    reason: 已核事实、各环节关系与边界；具体引文可写在这里
    changes: ["目标修复窗口的 e-调用", "e-回执"]
    nodes:
      - id: input
        scope: "实际查询返回的 s-file-..."
        role: context
        reason: 此处要求已充分且正确，本分支可停止的依据；或只是相关背景
        evidence: ["e-收到的原文"]
      - id: author
        scope: "实际查询返回的 s-agent-..."
        role: origin
        reason: 具体失误，不把读取或转述当写出
        evidence: ["e-实际写出"]
      - id: output
        kind: file
        key: 目标文件的完整路径
        at: "任务 observation_end 原样值"
        role: repaired
        reason: 目标历史端点，修复结果与运行期效果分别说明
        evidence: ["e-修复调用"]
    edges:
      - {from: input, to: author}
      - {from: author, to: output}
    unknown: [尚未查明的环节与缺哪份证据] # 无则 []
    hypothesis: 可选的机制假设
    boundary:
      status: supported_input
      nodes: [input] # 本 finding 已声明的节点 id，不是 scope
      reason: 何时送达的哪项正确输入足够指导实现，为什么可在这里停
unexplained: [仍未解释的修改或效应]
reviewed:
  - {ref: "e-相关调用", effect: no_target_change, reason: 实际只读或只修改其它对象的依据}
  - {ref: "e-相关调用", effect: unknown, reason: 当前缺少什么效应证据}
```

节点 role 仅 `origin / propagated / context / repaired / unknown`。origin 是实际引入偏差的环节；propagated 是保留问题，不是已修好；repaired 是检查/修复方。一个 agent 可以在不同时间/问题中承担不同角色。也可显式 target:{file,at,since}、node:{kind,key,at,since}；不得和 scope 混写。节点时间须涵盖证据，不凭空加减毫秒。

summary、recommendations 和 boundary 是同一 inquiry/1 的扩展字段，旧卡可不含，新技能交付必须给出。summary 的四个字段、每条 recommendations 的五个字段均按模板提供；findings 数组只填实际 finding id，不能写节点或源引用。原文引用可内联写在文本中，仍受原文与观察截止核验；新增事实先在对应 finding/节点落实，不靠文件总结额外归责。

boundary 只含 status/nodes/reason。status 仅 supported_input（相关输入充分，须指向 context 节点）、not_generation_error（此项非生成错误的依据）、unresolved（本分支未查明，nodes 可为 []）。每条 finding 都明确选择并说明；非 unresolved 须给本 finding 已声明、可连接的节点，机检只核形式与连接，不认证“输入充分”或“不是生成错”的判断。finding.recommendation 仍兼容，可由文件级 recommendations 覆盖该项后省略。

新情景卡明确填写 edges：from/to 是本 finding 的节点 ID，不是 scope。最简只填 `{from,to}`，服务端按 read:file→agent、write:agent→file、dispatch:parent→child 查两端范围内的全部已确认操作并附引用，不任挑一次。节点 `{kind:agent,key:完整转录名或唯一文件名,at:ISO}` 会解析为实际 agent；也接受已有 agent key。文件优先完整路径，歧义会报错。无需先打开原子取得 scope。节点 at 是历史截止，例如中间文件可取读取返回时刻，不表示那时发生了写。

需要精确限定操作时仍可填 `{from,to,link,claim}` 或 `{from,to,relation,evidence:[原生调用或回执],claim}`，不混用。单条引用唯一时补全并重核配对，多调用可用 link 消歧。未返回不借未来回执升级；关系、参与者和时间可核不等于内容传播成立。

inputs 顶部的 scope_id 仍是 agent；要画真实读取，用该 read link 的 from_scope 指向文件，不要把 agent 输入视图当文件。相同实体、相同时间范围的多个节点 ID 只是同一原子的不同判断；context 可依据实际到达的输入标注同一 agent，不需要伪造 agent→agent 的 read。较宽查询范围中的晚到输入不能支持较早写入。中间文件需要生成期历史时，不要继承 target 的修复窗口 since。

不同时间的同文件节点不会合并成捷径。末端节点是目标文件@observation_end，历史范围可不设 since；顶层 target 的修复区间不变。只有缺口时也保留 edges:[] 和明确 unknown。旧卡省略 edges 仍可载入，但其自动路径是背景，不是新技能要求的已交付论证；不要通过省略边换取自动连通。missing_evidence_links 仅为可选导航，独立对照不用强行连边。

执行检查可选 checks（位于 finding，与 edges 同级）：

```yaml
checks:
  - node: checker # 本 finding 已声明的实际执行 agent
    request: e-原始工具调用
    result: e-对应原生回执
    tool: Bash # 照原工具名；不是自己认为的用途
    claim: 具体检查对象、结果、范围与未认证的部分
    # 同一原文有多个调用时可加 request_block / result_block（原生块号）
```

服务端核原生配对、执行者、时间和工具名；返回 native_pair 不是“验证通过”。读日志也有真实配对、脚本也可能只转述旧日志，须核命令的实际内容。没有原生回执就保留未知，不将总结声明填进 result。checks 引用照样受观察截止约束。

首次不加 force/review，先提交普通 edges。收到 `unverified_edges` 的 `force_eligible:true` 后，复核该 agent 的原始工具调用；若确实是解析遗漏，可修订同一条边：

```yaml
# 顶层，引用真实存在的上次校验，不是自报轮数
revision_of: 上次submit返回的report_id
# 以下仍在 finding.edges 中，不另维护一套连接
edges:
  - from: author
    to: output
    force: true
    claim: 核实该脚本写此文件的依据与限度
    evidence: ["e-调用或回执"]
    review:
      at: "该事件的真实ISO时刻"
      quotes: [{ref: "e-调用或回执", text: "此记录内逐字可定位的相关原文"}]
```

服务端核 revision_of 是同一目标与时间范围、该边的两端身份/范围确实曾收到可复核反馈；改节点后不能借旧反馈。force 的 claim、evidence、review 必填。review.at 必须对应所声明 agent 的真实工具调用或回执，且在两端范围及报告观察截止内；原文摘录可定位，消息声明不能当调用。日期/引文可核不等于脚本语义认证；from/to 推导读写方向。补边固定 source:model_review/strength:candidate，仅带 report_id 的 neighbors 可见，不写入事实索引。

没有调用、引用无效、姓名歧义、时刻越界不能 force。未识别不是未发生；不确定时保留断点。旧 reviewed_edges/review 写法仍可加载已有卡片，但新提交同样受先反馈再补边的规则约束，不能用旧字段绕过。

补边不能覆盖已明确识别的原生操作身份：唯一调用锚点的实际 actor/文件与所画边矛盾时会被拒绝。多调用记录或不透明脚本仍需逐段核文，引用里的单个词不证明读写。`repaired` 节点也有展示路径，不计入问题路径完整性；不需要为展示修复而把它标成 `origin`。

submit 返回 report_id/source_sha256、issues、path_status、review_query、coverage_query。用 investigate `{op:review,report_id,offset:0,limit:100}` 和 `{op:review,report_id,view:coverage,offset:0,limit:100}`，按两层 next 续完。review 给引用时序、写者错位、较早同文修改、写后和全池返回等线索，仍由你核原文；不能据此直接认证机制。

修改差集的已知原生写并入 findings.changes；相关但非修改的调用用 reviewed，未知保留。path_status:complete 仅认证问题节点到目标的同问题时序路径；正常输入展示路径和未接入节点也可保留。坐标/引用错误要修；证据不足的断点不靠删结论消除。最终返回最后一次 submit 的 ID 和 hash，UI 按原稿展示。

## 随附脚本审核

提交后用 `investigation.json` 中 `runtime.python` 执行：

```text
<python> .agents/skills/migloop-investigate/scripts/check_card.py --task investigation.json --report <report_id>
```

宿主配置 `runtime.index_path` 指向这次 MCP 所用数据库，`runtime.code_root` 可指向同版代码包，未提供则使用已安装 migloop。不要更换这些配置来绕过审核。

退出码 0 = ready_for_review（仍待语义复核），1 = draft（可载入但有缺口），2 = invalid。脚本没有浏览器，因此 `browser_verified:false`；实际网页加载由宿主另测。它不生成/删除边，不改理由，不根据关键词替模型判根因。看到断链时核实真实连接，不能靠画无关边通过。
