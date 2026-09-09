# v3 时间边界与结论集成交叉审核

审核日期：2026-09-09。基线：`18b8f7f7f1181c942cda6066a1961fdbeb8837c2`（开始时的工作树变更随后已由主 agent 提交）。范围：`atoms.search_pool`、`atoms_text` 时间概览及搜索语义、`service.atom_json`、`verdict` consistency。未审查并行编辑的 UI；未运行模型、修改源码或冻结材料。依照 `gitnexus-pr-review` 的调用方/契约/测试清单直接读源码；无可用 GitNexus 索引，未为审查建立索引。

## 发现：until 的调用序号边界不等于输入可用时间边界

**P1，建议修正后再把 until 当作某时刻已知输入窗口。** 定位：`service.py:695–699`、`atoms_text.py:490–493`；派生载荷来自 `atoms.py:1130–1178`。旧文本已有按序号过滤行为，本轮 JSON 过滤和精确时间锚点使这个不一致同时出现在两个界面。

内存最小用例（同一个 agent，时间均为 `2026-01-01T00:00:ssZ`）：

| 动作 | use | done | 效应 |
| --- | --- | --- | --- |
| #1 Write | 00 | 01 | A.ets v1 |
| #2 Read | 05 | 20 | 返回 A.ets v1 |
| #3 Bash | 10 | 11 | 无文件效应，作为 until |
| #4 Write | 30 | 31 | A.ets v2 |

`agent(id, v=2, until=3)` 实际输出：

```text
time_scope.anchor.time = 2026-01-01T00:00:10.000000Z
time_scope.anchor.status = valid
actions.seq = [1, 2, 3]
reads = [{seq: 2, ts: 2026-01-01T00:00:20Z, at: 2, after_anchor: false}]
writes = [{ts: ...00Z, v: 1}, {ts: ...30Z, v: 2}]
```

因此，t=20 才返回的读仍显示在 t=10 的窗口，文本显示普通“写前读”，没有“截止时刻尚未返回”标记。JSON 的 `writes` 也未随 `actions` 截断，仍含 t=30 的写；`children` 使用同样的未截断派生方式。`scope_only=1` 只返回时间元数据，本身没有泄露这些正文行。

最小建议：统一一个只读 cutoff 投影，按已核实的截止调用 **use** 时刻区分调用与返回；调用前已发起但截止后才完成的输入应过滤或明确列为之后/未可用，缺失时刻保持未知。同步派生 writes/children；不要改写原始 action、账本或实际读取轨迹。补充并发完成和派生集合回归，不能只测试 `seq > until` 的普通后续动作。

## 未发现新增实质问题的部分

- `search_pool` 对文件版本与上下界统一 `ts_norm`，同一时刻的 `Z`、不同小数精度和时区偏移可正确包含；早一微秒的上界正确排除。未把此检查扩大为对任意无效/无时区时间戳的保证。
- 搜索新增说明符合实际字面子串匹配，`|` 不被当作 OR。零命中明确不证明无人见过或要求不存在；时间概览中的后续活动也明确不证明构建针对目标文件或验证成功。
- 时间概览只增加导航元数据，不增加图节点/因果边，也未把后续活动改记为生成前输入。未知锚点不生成后续检索窗口。`scope_only` 返回值不携带文件 diff/content 或 agent 正文。
- consistency 只在结论身份绑定后比较同一缺陷的已定位节点，缺陷之间的不同角色不互相冲突；保留原始角色/原因，新增 advisory 不替模型改判。`semantic_checked=false`、节点 `checked=not_checked` 保持，身份缺失/冲突时不以当前位置作一致性核验。
- 这些新增逻辑没有写回旧报告或冻结材料。审核不表示模型断言真实、修复事项完整或调查准确率合格。

## 验证

`test_time_scope.py`、`test_time_scope_surfaces.py`、`test_verdict_consistency.py`、`test_search_scope_language.py`、`test_service_serve.py`：**43 passed**。上述并发 cutoff 用例为独立内存复现，不改源码、不读取调查模型报告。已将实质发现即时发给主 agent；此记录不预先宣称后续修复通过。

## 后续修复核验（独立于冻结 v3 实验）

新增 `atom_scope.agent_until` 的只读投影；MCP 文本和 HTTP JSON 共用。晚返回或时间未知的读取不进入已可用输入，派生 writes/children 一起剪裁；动作索引保留 pending/unknown、原始指针及排除数量，不改账本、原文或实际模型轨迹。没有逐项时序来源的 aggregate result 不进入截止视图。同毫秒的结果/消息须结合相同转录的物理行先后，否则保持未知。依赖输入与真实读回分开。

26 项专门回归及其集成测试覆盖 Claude/Codex 收集、seen=True 无晚返回正文、JSON 派生集合一致、无效 cutoff 拒绝且不登记 MCP opened。旧词法测试改为真实后续效应版本内的窗口；比所查版本效应更晚的 until 现在明确拒绝，不再冒充该版生成前输入。尾部原文仍可通过 action 或生命周期查询打开。

此修复没有写入 `source-18b8f7f`；v3 两个 rep1 均未使用整数 until，因此不能用这个缺口解释它们的归因退步。工作树修复另行提交，冻结实验版本与显示版本须分别记录。
