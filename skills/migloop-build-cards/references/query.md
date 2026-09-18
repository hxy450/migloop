# inquiry 查询速查

原始转录和MCP可混用。通常每批2–4项：先定位片段，再展开写前输入。

```text
{op:catalog,kind:file,q:目标路径}
{op:file,key:完整路径,since:生成结束,at:观察截止,view:calls}
{op:file,key:完整路径,at:生成结束,view:outline}
{op:blame,key:完整路径,at:生成结束,terms:[被改的属性或表达式]}
{op:agent,scope:写者的input_scope,view:inputs}
{op:search,scope:同一写前范围,terms:[相关要求,符号],view:returns}
{op:open,ref:真实原文引用,at:包含该事件的截止时间}
```

按工具实际参数调用`investigate(requests=[...])`。scope继承时间范围；生成输入使用写前input_scope。消息、Bash返回也可作为输入，用messages/returns或原文补查。

列表next用于续列表；END FRAME next用`page(result_id,offset)`续当前结果。选中的相关请求/回执读完后再下结论。长源码可用多词窗口定位，随后核完整相关段落。直接转发content.text，减少重复包裹。

e-开头是原始记录引用，s-开头是查询范围，照抄返回值。文件at表示查询截止；中间有未知脚本时保留状态缺口。
