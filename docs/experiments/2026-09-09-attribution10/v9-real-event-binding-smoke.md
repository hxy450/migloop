# V9 真实事件定位回放（不是模型成绩）

2026-09-09 20:42 UTC，使用冻结 `source-0be4164`、原 Member pool，通过 service.session_ledger 建账；仅在内存构造明确标为 `manual-fixture` 的 v2 事件声明，role=无法确认。没有修改原始 run/YAML、没有调用模型，也不对脚本因果作新裁决。

真实引用 `#a68daf720e780b4c2:15731@L592` 的结果：

```text
ledger = atoms-2026-09-09-file-evidence5:146:ea78ea16fd4b5a751c914797
schema_errors = []
binding.ok = true
owner_agent = agent-a68daf720e780b4c2
use_line / result_line = 592 / 593
tool_use_id = toolu_01BrL9dsi5PB64tZiKVRfWoa
tool / kind = Bash / other
use_ts = 2026-07-26T21:30:17.239Z
done_ts = 2026-07-26T21:30:20.292Z
action_ok = true
effect_version = null
context_anchor = agent-a68daf720e780b4c2 @v40
anchor_basis = prior_ledger_effect_order
context_available_before_event = true
temporal_relation = tail_after_anchor
paired_result = true
creates_node = false
creates_edge = false
semantic_checked = false
roles = {}
fixed = []
```

这证明新声明单位能保留真实尾后事件而不造 v41、不把事件角色挂给 v40。时序字段只比较此前效应的记录完成时刻，不证明内容被消费，也不认证该脚本的归因。实际模型是否会采用正确单位，仍由 V9 调查及独立语义/UI回放验收。

另对先前创建时stdout编码错误的 Member V9 case 独立调用冻结runner的check_frozen：pool_unchanged/source_unchanged/task_unchanged均为true，源摘要仍 `c5cc203b2e3583f7a8544b1c44a557faf92e3374bf74fb6329d4a6d4346ab127`。未覆盖或重建这个case。
