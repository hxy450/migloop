# 自由调查与事后论证链：实施合同

状态：查询、论证图和运行器首版已实现，待冻结工具组验证归因效果。保留两原子作为入口；原始事件是底座，不是第三类必走因果节点。

## 不变量

- 模型不填via、不按图强制导航；调用与交付由服务器/运行器记录。事后论证不能改写真实轨迹。
- file/agent/全池查询、检索、展开、diff/blame使用显式时间范围；晚到返回不算更早输入。版本仅旧报告兼容。
- 原始记录独立于Action识别保留；原生调用按源/id/块核验；失败/重复/孤立/未分类不能静默丢掉。
- 确认操作、可能效应、纯提及分开。读写链存在不等于某问题传播成立，界面分别标关系核验与模型主张。
- 模型可以给断链/未知；不为了漂亮的树造边，也不要求每个结论节点都曾单独调用file/agent。
- UI与MCP共享选取/范围/对账内核，批量每项有成功/失败/未交付、分页和证据范围。
- 老schema1/2和旧运行保持可读，新时间文稿采用schema3；不把时间强行映成最近v。

## 分工与接口

- raw_events.py：不依赖Action分类的原始调用配对与时间索引。
- investigation.py：共享scope、batch、expand、changes和返回凭据/轨迹投影。底层复用temporal与保守state replay。
- change_inventory.py：已识别操作、独立原生补丁效应、两次可靠全文观察之间的差异。观察到变化不补造写者或精确修改时刻；观察区间跨过生成结束，不认证变化必在修复期。
- verdict_v3.py/time_probe.py：时间节点、显式读写证据、传播主张、反证、未知、覆盖差集；旧入口仅early dispatch。
- fixchain.html：独立论证图+真实查询时间线；粘贴文稿只显示文稿，不借用别次调查轨迹。
- serve.py/MCP：传输适配；不在传输层各做一套证据语义。

批量请求为`requests:[{tool,args,scope?}]`。scope是不可变的`{kind,key,at,since_ts}`；各项独立，不使用隐式当前节点。返回items逐项含`item_index/tool/args/scope/status/data/delivery`；批量截断不把没交付的项目算看过。

`expand.refs`接受原文引用或`{ref,pointer}`：后者按JSON Pointer仅交付指定字段，可继续按字符分页。回执区分摘要、全文片段、字段片段、派生diff；没有交付全文时不记成全文已读。`batch.max_chars`当前限制序列化data正文，查询/凭据封装另计，不是整个网络响应的硬上限。

file/agent/search默认折叠大型关系注释，显示省略计数；`details=true`配合较小limit展开。文件页优先显示目标文件的关系，而不是把批量命令触及的所有其他文件复制进每一条记录。搜索仍在完整时间范围原文上执行，不搜索折叠摘要。

文稿顶层：`schema:migloop-verdict/3, ledger, target:{file,since_ts,at}, findings, coverage`。finding含本地id、title、reason、时间nodes、显式edges、changes、可选hypothesis/recommendation/validation/unknown。节点给role/reason/evidence/counterevidence；边给relation/evidence/claim。关系绑定与传播语义分别显示，默认不自动认证因果。

## 验收与实验

先反例回归：未知工具不丢、Bash修改入口、重复/孤立调用、时间跨界、范围继承、部分批量失败、引用漂移、纯提及不造边、断链可展示、search/diff实际交付不强制原子补调用。再测UI真实载入与旧报告兼容。

冻结的十文件raw baseline保持不变。工具组继续Luna medium，同任务/原始池/停止条件，单列GUIDE和格式开销；格式成功不算归因正确。原始参考/裁决不得进入调查员上下文。没有质量/成本结果前，不宣称达到20–30%节省或正确性提升。

用户在service.py/deveco.py及对应测试的未提交改动不动；本次改动单独提交。

## 实施检查记录（不是效果实验结论）

- 最终冻结前全量回归：1,941 passed、1 skipped（可选CDP浏览器测试；此前独立启用后已通过）。这是实现回归，不是归因准确率。
- 真实HTTP/浏览器：页面粘贴v3文稿→POST check→节点/边核验→POST batch展开原文通过；人工稿不借用另一次模型调查轨迹。测试用合成账本和真实handler/query/verdict，不声称已验证真实模型会写对归因。
- 0723会员页固定截止`2026-07-26T21:48:57.793Z`、同40条首屏：旧默认约232,620字符；摘要后50,358字符，`details=true`为233,751字符；匹配语料均641条。数字是`json.dumps(...,ensure_ascii=False)`的字符数，不是token、更不是整场调查的成本改善。
- 运行器复用已冻结raw任务、Luna medium、2次重复/2并发/1800秒上限；冻结完整工具代码副本，检查三池228份JSONL及208份sidecar。开发smoke快照禁止进入正式运行队列。结构化最终稿成本计入工具组，不自动格式修复、重跑或回退模型。
