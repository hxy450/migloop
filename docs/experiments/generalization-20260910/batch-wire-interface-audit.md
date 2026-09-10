# Batch wire 接口独立兼容审查

审查日期：2026-09-10。只新增测试和本记录；未修改 runtime、旧runner、gold、冻结包或任何报告。没有调用模型、读取holdout答案或冷建原始池账本。

结论：新wire正常路径、旧格式回退、三hash绑定和MCP/HTTP同选中数据均通过。审查发现一项已有包装兼容路径不一致，父端修复后已转为回归；当前没有未处理的复现问题。

## 实际端点与认证检查

新增 `tests/test_batch_wire_transport_review.py`（12项）。使用真实 FastMCP `call_tool("batch")`、真实 `serve.make_server` HTTP handler、`service.atom_json`、统一query/codec/receipt/probe代码。仅用小合成源替换session查找/账本加载；不是生产池/完整UI页面验收。

- 相同参数分别用1000、6000、100000字符data预算，通过真实MCP与POST HTTP恢复相同canonical树。为避免两次独立请求的缓存访问诊断不同，先把同一小合成源缓存预热；不将缓存统计当证据正文。
- 明确覆盖：低预算deferred、未知agent的error、7字符raw前缀及next_offset、expand中早于since/晚于at的两侧拒绝。deferred/error无data且delivery.records为空；拒绝的未来正文未泄漏。
- MCP只返回一个text块。较大示例实际选择新marker；强制codec保守decline时，真实MCP走完整旧JSON回退，未截断或改写canonical数据。
- 将实际MCP文本置于标准合成原生call/result录制后，`probe._transcript_calls`、`via.trace_identity`与`project_trace`完整核验。外国provider、pending调用不能仅凭自洽receipt绑定身份或显示已交付items。
- 新wire正文被改且仅重新计算wire body hash时，canonical hash仍使其拒绝；请求/预算和ledger/hash的负例与父端已有receipt测试一起通过。
- query_trace始终无历史edges，原始calls树前后不变。这里没有用查询顺序、folded locator或事后文稿补节点/历史读写关系。

## 发现并修复的兼容缺口

初次独立运行：7 passed、1 strict xfailed。标准原生MCP返回的显式text块若内容为受支持的单键 `{"result":"…receipt…" }`，`project_trace`调用 `probe._unwrap_result` 后得到recorded_response，但 `via.trace_identity`直接调用parse_receipt，没有安全拆包装，结果bound=None。

这是身份读取与轨迹读取的不一致，不是三hash绕过或伪造提供者成功；新旧marker均受影响。父端让via复用同一个安全单键unwrap后，wire和legacy两个反例均通过，已删除xfail。另加反例保证带额外字段、嵌套非字符串result不被递归拆解，不丢弃未知字段认证身份。初始失败事实保留在测试文件说明。

新marker入口已核：`parse_receipt`显式分派；新分支严格decode与三hash；`project_trace`同时识别旧/new marker；via经同一parser取得ledger。旧parser/旧hash归一分支未借“等价重渲染”重写旧回执。codec自身只验证结构/可逆性，native来源与实际返回bytes仍由调用层认证。

## 旧v3真实录制只读抽查

目标：`EVAL/file-first-10/tools-v3/runs/F10-09/rep2/transcript.jsonl`。SHA256：

`76c0b9818e150d68c16861740c451fae9cdff2594f04592e60a9005230cde070`

只读取其中tool调用/回执，不读取report或重跑调查。当前parser验证4条旧batch receipt均有效，均为真实 `codex_rollout_event/item_runtime`、provider=migloop、complete_pair=true。以下为录制中的item_id和runtime起止时间；它们没有独立call_id/use_line，未补造。

| transcript结果行 | 原生item_id | 开始UTC | 完成UTC |
|---|---|---|---|
| 29 | `exec-3ef85ad6-1d2b-4245-ab6e-0a4e161d8071` | 2026-09-10T17:34:35.962Z | 2026-09-10T17:34:42.748Z |
| 36 | `exec-10bb11e2-de00-450f-bb11-a4536914219f` | 2026-09-10T17:34:55.767Z | 2026-09-10T17:35:01.403Z |
| 45 | `exec-bb15817b-0b39-40a4-87a8-3f0f7d099c5c` | 2026-09-10T17:35:12.802Z | 2026-09-10T17:35:15.143Z |
| 59 | `exec-3b6f5138-bffe-40e1-b259-3ea4306dd63f` | 2026-09-10T17:35:34.611Z | 2026-09-10T17:35:34.731Z |

4条回执共列32个不同的已交付raw refs，按首次出现顺序抽8项回源核验，8/8源行hash一致；未将8项抽样说成32项已全检。源basename：

`rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl`

| 原始行 | 原始记录时间UTC | ref内容hash后缀 |
|---|---|---|
| 8067 | 2026-08-17T03:11:06.817Z | fde44a196809789bce24 |
| 8022 | 2026-08-17T03:09:58.506Z | 45c2921380a7ac8969e8 |
| 8023 | 2026-08-17T03:09:59.490Z | a1741a0991ea128fc1be |
| 8026 | 2026-08-17T03:10:07.171Z | 386a7758f462928a8f57 |
| 8027 | 2026-08-17T03:10:07.647Z | 7b79a7c1957fafda57b0 |
| 8036 | 2026-08-17T03:10:28.742Z | b72baaecbfcd72a4c191 |
| 8037 | 2026-08-17T03:10:28.882Z | 5ec9547aee067978dd24 |
| 8041 | 2026-08-17T03:10:33.425Z | 3c66558e5848b695533d |

这些ref的source key为 `cc96d29f0c27def672ec`；按注册源相同的Windows规范化路径计算，未改变原始文件/ledger ID。抽查只说明旧回执与原文坐标仍可核，不评价模型结论、作者或行为验证。

## 验证范围与局限

正式venv联合测试：新transport review、batch_wire_receipts、batch_wire、investigation、investigation_http、mcp_text_envelope、time_probe、time_receipts、probe_json_text，**174 passed，2 skipped，5.10s**。跳过项为既有可选浏览器测试；本轮没有Chrome/UI视觉验收。HTTP测试自建线程/连接均由fixture关闭，且断言源文件和账本未被查询改写。

max_chars仍是data预算：此轮只验证无损封装变短与正确记账，未把它宣称为最终工具文本/token总预算。缓存命中、定位打印、自洽hash、可打开原文均不认证模型采用了证据，也不认证因果成立。
