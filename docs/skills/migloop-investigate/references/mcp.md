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
    unknown: [尚未查明的环节与缺哪份证据] # 无则 []
    hypothesis: 可选的机制假设
    recommendation: 针对环节的改进与验证办法；无法提出时说明依据
unexplained: [仍未解释的修改或效应]
reviewed:
  - {ref: "e-相关调用", effect: no_target_change, reason: 实际只读或只修改其它对象的依据}
  - {ref: "e-相关调用", effect: unknown, reason: 当前缺少什么效应证据}
```

节点 role 仅 `origin / propagated / context / repaired / unknown`。origin 是实际引入偏差的环节；propagated 是保留问题，不是已修好；repaired 是检查/修复方。一个 agent 可以在不同时间/问题中承担不同角色。也可显式 target:{file,at,since}、node:{kind,key,at,since}；不得和 scope 混写。节点时间须涵盖证据，不凭空加减毫秒。

一般不填 edges：按本 finding 已引原生读写/派发自动连线，中性端点不是模型归责。脚本效应须人工核文，可在 finding 的 `reviewed_edges` 给报告专属虚线（始终是候选，不能把词法命中升级事实）：

```yaml
reviewed_edges:
  - from: author
    to: output
    relation: write
    claim: 核实该脚本写此文件的依据与限度
    evidence: ["e-调用或回执"]
    review:
      at: "该事件的真实ISO时刻"
      quotes: [{ref: "e-调用或回执", text: "此记录内逐字可定位的相关原文"}]
```

from/to 必须是该 finding 内已声明的节点 id；read 方向相反。日期/引文可核不等于语义认证。带 report_id 的 neighbors 才包含该报告的补边，不写入事实索引。

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
