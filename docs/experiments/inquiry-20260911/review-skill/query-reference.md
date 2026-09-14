# 可选 inquiry 核验

原始 shell 读取保留；工具仅帮助定位实际输入、写入和时间，不改变复核交付要求。发现工具时只列匹配 inquiry 的名字，然后直接调用 investigate/page；不必调用 guide/submit，也不要求卡片。

`investigate(requests=[...])` 一次通常 2–4 个查询。直接转发返回的 `content.text`，不要重新包成大 JSON。`END FRAME next` 是同一结果的续帧，`page(result_id,offset)` 续到无 next；列表数据的 next 是下一批记录，两者不同。

```json
{"op":"file","key":"任务file","at":"任务generation_end","view":"outline","limit":100}
{"op":"file","key":"任务file","since":"任务generation_end","at":"任务observation_end","view":"calls","limit":100}
{"op":"file","key":"任务file","at":"任务observation_end","view":"relations","limit":100}
{"op":"agent","scope":"返回的input_scope","view":"inputs","limit":100}
{"op":"agent","key":"实际record_owner","at":"该次写入请求时刻","view":"inputs","limit":100}
{"op":"search","kind":"pool","at":"历史截止ISO","terms":["实际关键词一","实际关键词二"],"group_by":"agent","limit":100}
{"op":"open","ref":"返回的e-原文引用","at":"任务observation_end"}
{"op":"open","source":"注册转录相对路径","line":123,"at":"任务observation_end"}
{"op":"open","ref":"返回的e-原文引用","at":"任务observation_end","terms":["实际关键词"],"context":6}
{"op":"catalog","kind":"source","q":"转录名片段","limit":100}
```

scope 继承身份与截止，不再混填 key/at/since。file 输出的 WRITER.scope 截至观察，write_scope 截至最近写完，input_scope 截至这次写发起之前；它不代表所有更早写入的输入。查更早写入应打开实际请求，用 `IDENTITY.record_owner` 与该请求时刻查 agent inputs。

`IDENTITY.source` 是 open 的注册转录路径，`record_owner` 是 agent 身份，不可互换。复制完整身份，不缩写。没有 e-ref 可用 catalog 找 source 后按物理行号 open。open 完整原文默认不设 context；要裁出匹配窗口则 terms 与 context 同时填。用 observation_end 读取历史记录不等于该记录在生成期已存在，归因仍以原文自身时间与真实交付为准。

inputs 返回已识别读取、任务消息与工具返回入口；跟随 message_query / tool_return_query 可核未被原生 Read 表覆盖的输入。请求及回执都核对，request_context 预览不是效应证明。缺脚本效应时直接读原始调用；不得把没有索引行当成没执行。搜索 terms 为最多 8 个字面词 OR，不需要猜唯一正确关键词。
