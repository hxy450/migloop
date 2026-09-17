# 接口与反馈操作

使用现有 inquiry MCP 的 `investigate / page / submit`，不新建校验器。调查可走原始读取；MCP 主要提供可选导航、原文定位和卡片提交。

## 提交与复核

- `submit(card={...})` 提交 SKILL.md 的完整卡对象；也可用 `document` 提交原始 YAML/JSON 字符串，两者不同时填。普通节点和边的原始证据由系统绑定。
- 返回 `issues / unverified_edges / paths` 指出未核实的身份、时间和交接。若只返回 `feedback:{result_id,offset,complete:false}`，用 `page` 续完整反馈后再处理。
- `investigate(requests:[{op:"review",report_id:"返回的报告号",limit:100}])` 复查报告原文引用、时间和路径；`view:"coverage"` 查看未对账调用。未对账调用不是已证漏修，提示也不是标准答案。
- `ready_for_review` 表示声明可核并可载入，不认证输入充分、原因正确、内容持续传播或修改解释完备。

仅普通检查后返回 `force_eligible:true` 的同坐标边可补：

```yaml
from: 1
to: 2
force: true
reason: "核对哪次真实调用后，为什么认为这是未解析的读写；本次核实对归因有什么影响。"
evidence:
  - {source: "实际转录名", line: 123}
```

数字、名称必须换成实际来源；也可用原文 `e-...` 引用。提供对应调用及回执，不将脚本定义、计划或他人调用当成执行。force 仍核身份、时间和原文，不能引用晚于端点的材料。改变端点后先重新普通检查；系统关联同次调查前稿，无需填 revision_of。

## 可选调查入口

`investigate(requests:[...])` 可批量独立请求。以下示例展示字段，不是真实案例：

```json
{"op":"catalog","kind":"source","q":"转录名称片段","limit":100}
{"op":"file","key":"真实文件路径","at":"历史ISO","view":"calls","limit":100}
{"op":"agent","key":"真实转录身份","at":"历史ISO","view":"inputs","limit":100}
{"op":"search","kind":"pool","at":"历史ISO","terms":["关键词一","关键词二"],"limit":100}
{"op":"open","source":"真实转录名","line":123,"at":"覆盖该原文的历史ISO"}
```

file/agent 用 key+at，可选 since；返回的 scope 可以代替整组坐标，不混填。确定 Read/Write 按回执完成时刻，调用发起不等于已经收到内容。生成输入不能继承修复窗口 since。file calls 含未解析调用入口；原生 changes/blame 不保证覆盖脚本。agent inputs 不是完整上下文，原始 records/messages/returns 仍可查。

每批 investigate 1–24 项，通常 2–4；limit 1–100；terms 最多 8 个字面词，OR 匹配。搜索覆盖指定历史范围，不只当前显示片段。需要更精确接口参数时看工具服务说明，不猜参数或引用。

正文过长用 `page(result_id,offset)`，offset 取 `END FRAME next`；列表自身的 next 是下一批记录，不是正文续帧。`DEFERRED.requests` 是待送请求，按其游标继续。page 可批量 requests，每批 1–4 项。直接转发返回文本，不在宿主再次拼接多个大响应造成截断。原文 e-引用与调查 RESULT、scope、节点序号不同。
