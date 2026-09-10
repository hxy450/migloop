# Codex outer exec → confirmed patch：只读诊断

2026-09-10；基于已完成的 [tools-v1 实测](tools-v1-codex-reachability.md) 与当前 repo v2 静态源码。未改源代码、未执行历史 JS/命令、未修改冻结工具。使用 gitnexus-debugging 流程核查工具可用性；GitNexus 未索引 migloop，遵守只读限制，不新建索引，改为源码/测试追踪。

## 结论

根因不是 raw_events 把两个 call ID 配错，而是 **collector 已在未证明 inner 操作执行时，将外层 JS 中的 patch 文本提升成 native_tool/confirmed**。change_inventory 和 diff 继承这一过强 proof，再与正确独立登记的 native patch 并列，产生额外 confirmed 行和 root 作者。

真实补丁确实发生；不足的是“outer 与 inner 一一对应”“outer 是唯一实际写者”的认证。不能用文件名、相邻位置、相近时间或相同 diff 来补造这两项身份事实。

## 真实 ID 与物理行

A=`rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl`；B=`rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl`。来源完整池、hash 见实测文档。

| 项 | 可确认的配对/独立事实 | 不能自动成立的联系 |
|---|---|---|
| Launch outer | A8066 `call_sOYpciVhfgk1glebywbIbHAY`，2026-08-17T03:11:06.675Z → A8068 同 ID，03:11:06.825Z | A8067 的 inner ID 不同；outer 空结果不是独立成功证据 |
| Launch native | A8067 `exec-4ef57557-1919-4ec6-b81e-4b4d9d8c112a`，03:11:06.817Z；success=true、精确目标和 Block→Default diff | 来源 root 归属不等于该独立事件的实际写者；时间/文本吻合只给候选关联 |
| signing outer | B4943 `call_bLvRxsabKt5jwrDAGfcDP0LK`，2026-08-21T11:15:04.158Z → B4945 同 ID，11:15:04.202Z | 不能把另一 exec ID 的事件强行并入 outer |
| signing native | B4944 `exec-9c2b0363-9806-4d9a-8733-06f2e3379843`，11:15:04.181Z；success=true、product 新增 signingConfig | 同上；只证明独立操作及其观察时刻，不证明作者/精确 mutation 时刻 |

实测每题 changes 都给两条 confirmed_change：native 行 agent=null/unknown，outer 行 agent=对应 `__main__`。diff 又把 outer 行标 basis=native、agent=root。raw_events 则正确保留 outer returned 与独立 patch independent 两种事件，没有宣称它们属于同一次 nested call。

## 当前 v2 的具体传播路径

`_extract_apply_patches` → `_patch_ops(via='tool')` → `_admit_ops(succeeded=outer_ok)` → confirmed FileRef → changes / temporal_state.diff / v3 edge binding。

1. `adapters/codex.py:245` `_extract_apply_patches` 用正则找字符串/变量形式的 `tools.apply_patch(...)`；不验证 JS 控制流、实际调用次数、嵌套回执或成功状态。
2. `atoms_collect.py:1995` `_codex_stdout` 以“不以 Script failed 开头”默认 ok=true。`Script completed\nOutput:\n{}` 因没有 `output` 字段，不携带 patch 成功证明，但仍返回 ok=true。
3. `atoms_collect.py:2106` `_codex_exec_ops` 无条件将抽出的 patch 交给 `_patch_ops`。后者产生 `via='tool'` 的 edit/write/delete；没有 independent native event 与调用身份字段。
4. `atoms_collect.py:1317` `_admit_ops` 把 via=tool 对应为 native_tool，使用 outer 的 succeeded 与 conditional=false 生成 execution=confirmed。
5. `atoms_collect.py:2230` `_walk_codex` 仅按 outer call_id 配对后，将上述 FileRef 挂到 root/child AgentRec；原始 pointer 是 A8066/A8068 或 B4943/B4945，不含中间独立事件行。
6. `change_inventory.py:373` 信任该 FileProof 生成作者明确的 confirmed_change；`:235`/`:396` 的原生覆盖判断按 source/line/path，无法覆盖物理行不同的独立 native event，于是再发一条正确的 author-unknown confirmed。
7. `temporal_state.py:36` 与 `verdict_v3.py:294` 继续信任 confirmed FileRef，派生 diff 作者和读写边。raw-only barrier 保护 known 状态，不会纠正已派生的 outer diff 作者字段。

当前 v2 尚保留以上 collector 路径；修正不能只在 changes 最后按相邻行合并，否则上游 story、diff 与 graph 仍会看到虚假的 confirmed proof。

## 已执行的最小纯解析复现

只调用当前 repo 的 Python 解析器；下面的 JS 是输入字符串，没有运行。补丁目标 `/proj/A.ets` 是合成字符串，磁盘未写入。

```python
patch = '*** Begin Patch\n*** Update File: /proj/A.ets\n@@\n-old\n+new\n*** End Patch'
js = 'if (false) { await tools.apply_patch(' + json.dumps(patch) + '); }'
ops, detail, ok = atoms_collect._codex_exec_ops(
    js, 'Script completed\nOutput:\n{}', '/proj', {})
```

实际返回：ok=true；一条 `/proj/A.ets` edit，conditional=false，proof=`{operation_basis:native_tool, execution:confirmed, delivery:none, snapshot:unknown, rule:tool:edit}`。把 JS 换为直接 await 仍是相同输出。**死分支都被认证为写入**，排除了“只是在真实 trace 中两个视图重复展示”的解释；这是调用意图升级执行事实的解析缺陷。

## 最小修正边界建议

- 优先在 `_codex_exec_ops` 的 patch 分支堵住升级，不全局改变 shell/read 的旧规则：正则抽取的 patch 是意图/相关导航，outer completed 不能成为 inner confirmed。没有独立、可定位、无歧义的执行回执时，不发 confirmed FileRef；保留原始 patch 入口和未知说明。
- 明确区别“可能执行的 patch 调用”与纯字符串/注释/死分支提及。无法证明 JS 调用形态时可以只留 unclassified 导航，不能为了 state barrier 或画边把纯提及提升成候选作者。
- 独立 patch_apply_end 保持一个确认 effect（success/conditional/failure/精确目标按原规则），agent=null，changed_time_unknown=true，只在观察时刻可用。失败/时间未知仍保留候选或 gap。
- 只在真实 call_id/explicit parent-child link 与原始块坐标共同支持时建立 nested 关联；还要排除重复 use/result、fork 拷贝和源歧义。相同路径/diff/时间窗口可以注明候选联系，但不得据此确认作者或强行消除一笔可能独立的操作。
- 如无有效关联，允许“一条 native confirmed + 一条未确认 outer intent/相关事件”，不能当两次已确认净修改。diff 可为空而引导展开 native patch；如额外投影原生 diff，应标独立观察、作者 unknown，不借 outer 的 legacy ref/时间认证作者。
- 重新构建 ledger/失效旧 cache 的身份版本，避免已经落入缓存的 confirmed FileRef 继续影响状态/边。冻结 tools-v1 不改动，评测中只记录此限制。

## 回归缺口与兼容性

- `tests/test_atoms.py:559` 的 `_cexec` 用 outer completion/空内层 stdout 构造“成功 patch”；`:615` 的 `test_codex_collector_matches_cc_semantics` 当前直接断言此输入产生全文版本和 child 作者。应给正向 fixture 增加真实可证明回执，或将无回执例改为未确认，不能只维持旧断言。
- `tests/test_filestory_collect.py:98` 仍要求没有 inner receipt 的 Add/Edit 被立即落为版本；旧 `filestory_collect.py:253` 甚至在 request 解析时发 patch events。它不是本次 frozen changes 的直接路径，但若仍作为可认证来源消费，应隔离 legacy 意图投影或一并修正。
- `tests/test_change_inventory.py:85` 的 same-source/line/path 人工 Action 去重只覆盖“同一物理事件”情况，没覆盖真实 outer/inner 三行、不同 ID 的组合；必须增加该最小三行场景。
- 新测试至少覆盖：死分支/注释不 confirmed；outer 空成功 + independent success 只有一条确认且作者 unknown；inner failed + outer completed 不出现确认写入；独立 native 在 outer yield/result 之后出现不漏记；相同文件两次不同 native ID 不被错误合并；真正明示关联才允许绑定；patch cutoff ±1ms 不泄漏；旧 shell/read 正向用例不回退。

以上是诊断与修正范围建议，不是已实现修复。没有新建 GitNexus 索引或修改任何源代码。
