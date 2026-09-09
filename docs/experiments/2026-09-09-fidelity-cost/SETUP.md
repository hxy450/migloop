# GPT-5.6-sol 接入记录

正式配对之前的连通性检查，不用于证明 raw/tools 哪组更好。原生事件、真实 rollout、命令和用量保存在本机 `C:/Users/hongy/projects/_migloop-eval-20260909/sol-mcp-smokeN/`，失败没有覆盖。

| 运行 | 结果 | input（含缓存） | output | CLI 秒 |
| --- | --- | ---: | ---: | ---: |
| smoke1 | MCP 需要审批；查询工具尚未声明只读 | 39,694 | 419 | 29.30 |
| smoke2 | 模型按描述发现 guide，因共享说明使全部工具命中而停止 | 25,391 | 327 | 27.34 |
| smoke3 | 禁用 code-mode host 并没有切成直接工具；MCP 报宿主不可用 | 22,813 | 274 | 24.81 |
| smoke4 | guide 成功且结束标识正确 | 27,446 | 226 | 43.08 |

四次真实 turn_context 均为 `gpt-5.6-sol / medium`，订阅 CLI 没有返回实付美元，记录为 unknown。另有一次无工具登录检查成功：10,419 input、12 output。两次最早的 CLI 参数位置检查未进入模型请求。

修正：九个 migloop 工具准确声明只读/非破坏性/封闭数据访问；服务器共享说明不再把 guide 的名称加进每个工具描述；工具发现按工具名而不是描述匹配。两组保留当前客户端所需的 code-mode host；没有关闭系统审批或更改用户全局配置。

真实宿主形态中，外层 `exec` 有自己的 call_id，内层 MCP 则记录在 `event_msg / item_completed / McpToolCall`，使用独立 item_id 和开始/完成时刻。不能把外层 ID 当内层 ID，也不能只解析 function_call 而漏掉所有查询。成本统计把 wrapper 返回与 MCP 返回分列，不重复相加。
