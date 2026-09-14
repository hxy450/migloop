# MCP 调用与精简模板

investigate(requests=[...]) 批量独立查询，page 续正文，submit(card={...}) 保存精简卡；也可传 document 原始 YAML/JSON 字符串，二者不同时填。工具发现只列匹配工具名，不输出整份目录。工具结果直接转发 content.text，避免再次 JSON 封装和宿主截断。

## 查询和时间

```json
{"op":"file","key":"任务文件路径","since":"任务generation_end","at":"任务observation_end","view":"calls","limit":100}
{"op":"file","key":"任务文件路径","at":"生成截止ISO","view":"outline","limit":100}
{"op":"agent","scope":"返回的写前input_scope","view":"inputs"}
{"op":"agent","scope":"s-agent-...","view":"returns","terms":["字面词"],"limit":100}
{"op":"search","kind":"pool","at":"阶段截止ISO","since":"阶段起点ISO","terms":["词一","词二"],"group_by":"agent","limit":100}
{"op":"catalog","kind":"source","q":"转录名称片段","limit":100}
{"op":"open","ref":"e-原文引用","at":"涵盖该记录的ISO"}
{"op":"open","source":"注册转录名","line":123,"at":"涵盖该记录的ISO"}
{"op":"open","ref":"e-原文引用","scope":"返回的scope_id","terms":["属性名"],"context":6}
{"op":"blame","key":"文件路径","at":"生成截止ISO","terms":["代码片段"],"limit":100}
{"op":"file","scope":"s-file-...","view":"neighbors","limit":100}
```

每批1–24项，通常2–4项；limit 1–100，terms最多8个字面词、OR匹配、每词<=500字符。换词或范围从offset=0。next是记录列表下一页，END FRAME next是本次正文的续帧，二者都须续完才是读完。page(result_id,offset)，或page(requests:[{result_id,offset},...])每批1–4项，建议2项。

file的records是全部相关记录索引；calls含未知脚本和结果入口，默认折叠已知只读形状，可include_reads:true；changes是原生修改参数全文，outline是原生增删摘要，二者都不是脚本修改全集。agent的inputs是原生读表、任务消息、返回入口三个重叠渠道，继续用messages/returns/records/search查完整已记录范围。pool/agent search可加view:returns；records/messages/returns支持order:newest|oldest。

查询用带时区ISO at，可选since，闭区间。scope_id锁定范围，继承scope后不再填key/at/since。生成输入不要继承修复窗口since。input_scope是写前输入，write_scope是写完成时刻，WRITER.scope是本次观察截止。

at是查询截止，Read/Write的确定效应按完成/返回时刻。假如10:10:00.100发起、10:10:00.250返回，想纳入这次确定操作，两个端点都须覆盖.250，不能抄.100。这不让写后读取变成写前输入：链路沿原始操作时序检查，扩大截止也不会改变先后。

open默认完整原生正文；pointer:""看完整原记录；terms/context(0–50)返回所有匹配窗口和literal_counts，片段不是完整分支。Edit/patch/未知写脚本的参数包不按词裁剪。request_context给回执对应的原调用；核实际对象，不把相似输出当成同文件。e-...是原文引用，不是调查工具调用编号/RESULT/scope/link；也可用注册转录名+物理行号精确定位。

diff比较两个明确原文{op:diff,before:ref,after:ref,before_pointer:可选字段,after_pointer:可选字段,at:ISO}。blame仅给原生片段演变，不认证脚本没改或首次作者。neighbors和UI共用历史投影，可带report_id展开该卡虚线；独立查阅不产生关系。

## 最终只填这些

以下是字段模板，不是真实案例；用任务和实际查到的坐标替换占位符。优先作为card对象提交，无需双重转义。

```yaml
target:
  key: "<任务中的被修文件路径>"
  since: "<任务generation_end，含时区ISO>"
  at: "<任务observation_end，含时区ISO>"
summary: |
  实际修改了什么；生成期当时要求和输出如何不一致，问题如何保留。
  哪些是新要求/修复中新生问题；修后实际验证与未查清项。
recommendations:
  - "修改哪个规则/交付/实现/检查，依据是什么，怎样验证效果；假设须说明。"
nodes:
  - key: "<实际输入文件路径>"
    at: "<涵盖实际交付的截止ISO>"
    reason: "该输入中哪些要求充分、何时实际交付，为什么本分支可以在此停；或其形成仍未查明。"
  - key: "<实际agent注册转录名>"
    at: "<涵盖相关写完成的截止ISO>"
    problem: true
    reason: "实际收到什么、产生或保留了什么偏差、后继如何受影响；不是笼统说没做好。"
edges:
  - from: {key: "<实际输入文件路径>", at: "<与上面同一截止ISO>"}
    to: {key: "<实际agent注册转录名>", at: "<与上面同一截止ISO>"}
  - from: {key: "<实际agent注册转录名>", at: "<与上面同一截止ISO>"}
    to: {key: "<任务文件路径>", at: "<任务observation_end>"}
```

按实际需要添加中间file/agent，不要求恰好两跳。同坐标一次定义，多边引用；不同时间两次定义，哪怕内容相同。目标端点可只写target，系统补显示节点；要给目标具体原因也可在nodes声明。problem不填只是未标红，不表示机检证明正常。多个问题在reason中分段口述即可。

系统绑定普通边的全部匹配确定读写/派发及原始请求/回执，自动附到相邻节点；不能证明节点reason，更不能证明每个修改已解释。语义关键证据（具体要求、检查结果等）可在reason/summary直接写原文引用，不要把不沾边材料强连成边。

## 机械失败如何修正

首次绝不加force。提交返回错误路径/坐标、实际事件时间和inspect查询；字段/身份错会尽量一起报。直接复制实际返回的身份和时间，不缩短目录、不改大小写、不把工具RESULT当原文引用。

普通边不确认且force_eligible:true时，核真实脚本或未解析调用。如果确实证明该agent对该file的读/写，下次在原坐标的同一条边加：

```yaml
force: true
reason: "哪次原调用如何读/写该文件，为什么认为静态索引漏识别；保留不确定性。"
evidence:
  - "e-实际原文引用"
  # 或 {source: "注册转录名", line: 物理行号}
```

列出你认为证明本边的实际调用及回执；同一关系可有多次调用，系统按调用分组、逐次核验，不合成一个虚构时刻，不需你拆填边。脚本定义等仅作背景的材料可在reason引用，不冒充执行调用。模型不填review、摘录、事件ID、修订ID；系统核原文并生成锚点，记录同次调查上次检查。其他agent的调用、消息里的自述、未来回执、伪造引用都不能force；不能倒置已知完成时间。两端身份或截止变了，先重新普通检查。

“有真实边但路径倒序”也不是通过：按blocked_branches核两次操作，找实际较早输入；可能原来的读只是事后读回。若相同坐标只找到较晚原生读，应先把节点截止收窄到实际较早交付窗口，再普通检查；有真实未解析输入才能随后force。不要挪时间迎合已认定的原因。

## 审核和交付

调查员自己按反馈补查/修稿。review_query展开作者、时刻、字面前序等反证提示，coverage_query看修复窗口未对账调用；提示不是新增必填字段，不要求为所有提及连边。与真实修改有关的遗漏需补进summary/节点原因，未查清具体保留。

用任务runtime.python执行scripts/check_card.py --task investigation.json --report <最后report_id>。ready_for_review表示声明的树可机械查验并加载；语义、停止边界和修改解释完备性仍待审阅。没有明确因果链或还有错误时交draft，不删难点拿通过。

最终给report_id / source_sha256 / 审核状态。原稿与系统投影分开保存，实际查阅轨迹也另存；树不是伪造的一条固定调查路线。
