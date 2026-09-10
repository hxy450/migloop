# v2 已完成运行：交付与表示问题（04/05 rep2）

只读审计，2026-09-10。未重跑模型、未冷建账、未改冻结工具或评分合同。以下是实际响应和报告的对应，不是已实验验证的模型心理因果。

目录前缀：`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v2/runs/`。行号均指各运行的 `transcript.jsonl`；`query-trace.json` 是辅助定位，不替代原始 MCP 响应。响应来自 `payload.item.result.content[].text`，JSON 后有凭据尾部。

## 已核响应

| 运行／原始行／UTC／MCP id | 实际交付 | 不能据此推出 |
|---|---|---|
| F10-04/rep2 L33；14:54:49.153Z；`exec-1d60ad29-8e1f-4990-9514-e631009746ae` | batch 50000字符。diff因`details`参数报错；生成前file匹配498条、只送9条、next=9。一次8-ref expand只完整送R5091，R5092送8461字符后续取；后面的ref明确not_delivered。 | `status:ok`不是全部结果已读；file第一页不是完整生成责任链。 |
| F10-04/rep2 L40；14:55:12.476Z；`exec-ad0f74a4-4994-4fe6-9f98-a42123fd3bf6` | 删掉diff的details后成功，4条派生差异完整返回。分拆expand后R5099/5100、R5123/5124/5126/5127完整返回。 | 第一次格式错误不等于材料不可达；重试确实恢复了修复链。 |
| F10-04/rep2 L47；14:55:25.649Z；`exec-2b63dfc3-a10e-4572-ae95-ef3c7448049b` | 生成前全池命中策略查询254条，只送7条；EntryAbility/debug另一组549条整项deferred。三个UI生成代理页分别只送5/89、5/88、24/85条。continuations含实际游标。 | 搜索未送达不能证明启动契约不存在，也不证明所有生成actor没有相关输入。 |
| F10-05/rep2 L42；14:55:10.244Z；`exec-8f3f2996-69ec-42bc-8267-29f9709fb291` | batch40000。Auth初始Write R193原文只送6645字符、next=6645；早期androidId/D-010等q_any共638条只送4条、next=4。修复R5221只送1813字符，R5222 not_delivered。 | Write关系已见，不等于初始正文和派工约束已完整交付。 |
| F10-05/rep2 L49；14:55:33.664Z；`exec-0ff35e31-e766-4130-8b9f-2ab5d6188951` | batch30000。早期D-010搜索197条整项deferred，错误为`first indivisible metadata/body unit does not fit`；早期androidId共354条只送2条、next=2。 | 不能把未取得材料写成池内无早期测试值线索；错误响应未提供足够内容证明究竟哪个不可拆字段最大。 |

04后续修复链补齐，但生成输入查询仍主要停在早期Navigation规范及UI代理；没有查询Auth或Startup作者上下文。05查询了修复根的后期agent页，没有查询已识别初始writer的Auth上下文。Auth L1原始输入实际明确“保持挂起、不要臆造取值”，并交付测试hex注册成功线索。该材料未在这些实际回执中完整交付；这解释的是调查可见范围，不是豁免报告事实准确性的理由。

## 字段语义与可见误解

1. **工具不代做语义判断，被混成调查员必须未决。** 04报告把4条coverage全部写unresolved，逐条理由为“确认了写入，但工具未完成语义校验”。实际batch delivery带`semantic_checked:false`。该字段仅声明工具未认证因果，不意味着调查员依据原文已解释的局部原因也必须unresolved。应分别呈现`mechanical_binding`、`model_explanation_status`、`external_validation_status`，不能删掉证据不确定性来让图变好看。
2. **同一ok包含完整、部分、未送达子项。** 实际续取信息是准确的，但散落在嵌套records与长continuations。可提供独立、短小的delivery摘要（匹配总数／本页实际数／尚未送达ref数／可直接执行的下一请求），保留原排序及完整总数，不按预设答案重排。
3. **整条JSON原文开销挤占真正字段。** 多ref展开反复被大记录前缀占满，调用者没有使用已有JSON pointer按字段展开。可首先交付原始record身份+字段目录+精确field continuation，并允许选择调用input、result正文、sidecar；不能把删去正文说成已读。
4. **大范围查询的前缀偏向最早记录。** q_any产生几百条结果，缩limit仍只重复第一页，关键后期生成actor输入可能在未送达部分。可提供可选的source/actor/time计数分面和从已确认writer跳到其调用时点上下文的明确入口；这应是一般导航能力，不是本题专用提示或强制调查路线。
5. **接口参数不一致有真实成本。** diff不收details，batch也不收sessions子操作；这些错误在完成运行中真实发生。建议guide给每个tool一份可复制最小参数模板，并让错误返回精确合法字段；不要静默忽略参数造成范围假象。

## 保留的正确边界与审计纠正

- 两报告都没有把大量未分类执行窗口直接算成额外写入；`current_state_certified:false`被用于保留未重新验证的范围，这本身不是错误。
- 不能因一份HTML成功渲染、source可打开或工具schema通过就认定归因正确；语义评分仍独立。
- `raw:ff2350280993d10b4d30`的源是`agent-aref-doc-analyzer-d4e8fbf7e1d0dbac.jsonl`，不是第二根`ff019d8a...`。本审计曾按相似前缀误映射，已机械核basename哈希并纠正04rep1的audit项；语义分数未变。实际早期搜索没有因此被证明泄漏未来记录。
- 未冷重查“最小不可拆元数据”大小，没有证明调整预算、字段目录或导航入口一定提高模型得分；上述均为下一版可验证的接口改进候选。
