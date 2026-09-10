# 冻结 tools-v1：0723 changes 余项与原文比对

2026-09-10。AI 只读审计，不是人工认证。全部语义评分完成后开展；未改模型报告、gold、runtime 或裁决。前半使用正式 v1 运行中记录的真实 MCP 返回，不是当前源码重放；末节另外记录固定 v2 快照的只读冷查询及浏览器检查。没有新模型调用、历史命令执行或重跑实验分数，不能据此主张归因质量提升。

## 版本与范围

工具目录：`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/tools-v1`。

- manifest SHA256：`c2cb98381f4babf84e5249d8c6ef84873385058d79068da53ebef2fe60c94d61`
- 冻结 code_digest：`ce685b2ded0a8cccdfb63ff18a2353a1b6eee0b31b8e47409f38ec48fcba1ca4`
- 原始池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/member-center/pool`，146 JSONL。
- ledger：`atoms-2026-09-10-temporal1:146:44b9dd029c52f8f3cd8c6265`
- 查询范围：`since_ts=2026-07-24T22:16:20.102Z`，`at=2026-07-26T21:48:57.793Z`，五个目标的文件 scope。

下述 24 是已核“目标文件 × 原生修改调用”对，不是 24 个独立 call_id，也不是缺陷数。Member/Splash 共用两个批量脚本，故已核集合有 22 个独立原生调用。集合来自已核请求、对应回执与代码/脚本内容，不宣称未知动态脚本和全部文件系统效应已穷尽。

## 真实 changes 返回与有界已核集合

MCP 返回取自原生转录 `payload.item.result.content[].text`，解析 JSON body，不把 receipt、模型复述或最终 YAML 当查询结果。batch 内只取对应 `items[i].data`。下表请求均 `limit=100`、`offset=0`，返回 `remaining=0`、`next_offset=null`；不存在本表因漏翻页而少数的情况。

| 文件 | 原文已核修改对 | changes 行数 | confirmed_change | candidate_effect | 已核但没进入 rows | 真实响应 locator |
|---|---:|---:|---:|---:|---:|---|
| MemberCenterPage | 8 | 6 | 5 | 1 | 2 | `runs/F10-01/rep2/transcript.jsonl:L26` |
| SplashPage | 6 | 4 | 2 | 2 | 2 | `runs/F10-02/rep2/transcript.jsonl:L29`, `/items/0/data` |
| EntryAbility | 4 | 4 | 4 | 0 | 0 | `runs/F10-04/rep2/transcript.jsonl:L30`, `/items/0/data` |
| F003Repository | 2 | 2 | 2 | 0 | 0 | `runs/F10-05/rep2/transcript.jsonl:L25` |
| GuidePage | 4 | 4 | 4 | 0 | 0 | `runs/F10-06/rep2/transcript.jsonl:L24` |
| 合计 | 24 | 20 | 17 | 3 | 4 | 仅此有界集合 |

这不是归因准确率。尤其 `gaps=[]`、`remaining=0` 不等于全历史完整：五份返回均明确 `complete=false`、`causal_complete=false`，并提供 `unclassified_related.query` 的 events 入口。v1 未声称 rows 穷尽修改，但用户/模型仍需发现并展开余项。

## 没有进入 changes rows 的两个批量脚本

完整原始 source 为：

`ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-a68daf720e780b4c2.jsonl`

| 调用及回执 | 原文短摘录与已核目标 | rows 缺口 |
|---|---|---|
| L103 `2026-07-26T20:41:07.872Z` → L104 `20:41:10.739Z`；`toolu_01T6WkXMhD7rUsHaSaMPuhgx` | 脚本遍历 `.ets`，跳过已有 `maskColor`；AppLoadDialog 加透明，其它控制器加 Palette.DIALOG_MASK，并 `open(path,'w').write(new)`。成功回执明确列 MemberCenter `3 sites`、Splash `1 sites`。 | 两目标的 rows 均未出现这个 call_id。动态枚举的输入不能直接以目标路径词法存在为必要条件；目标至少在回执中出现。 |
| L233 `2026-07-26T20:54:02.690Z` → L234 `20:54:05.517Z`；`toolu_01DeqiV3n9uPH5cLqUA6a8Yn` | `patch(path,old,new)` 内断言匹配一次、写文件、打印 `ok`。Splash 的 app-name 图补 185×125；Member 两张图补 aspectRatio840/942 和 height366+35。回执明确两目标均 `ok`，Member 两次。 | 两目标的 rows 均未出现这个 call_id。脚本有明确多目标路径与成功结果，不是“只有报告里提及源码路径”。 |

这是**已核多目标脚本的索引覆盖缺口**。本审计没有运行解析器内部诊断，因此不把具体某条正则/AST 分支认作已证唯一原因。也不因全项目扫描根包含另三个目标就给 EntryAbility/F003/Guide 加修改：该回执列表和显式 patch 列表没有这三个目标。

## 三个 candidate 可由原文进一步消解

同一 fixer source：

| 目标、call_id | v1 状态 | 原始请求/回执依据 | 有界结论 |
|---|---|---|---|
| Member；`toolu_01BrL9dsi5PB64tZiKVRfWoa` | candidate_effect | L592 `2026-07-26T21:30:17.239Z`：断言旧片段唯一，动态 ForEach 改固定双 Span，新增 private priceDigits/priceSuffix，然后写文件；L593 `21:30:20.292Z`：`ok` 且回显新的两个 Span。 | 有真实修复效应证据，不能说没有执行；它不是 Banner 常量写入。 |
| Splash；`toolu_01DzVErQMcevEwF2f5T3E1U8` | candidate_effect | L346 `2026-07-26T21:05:54.915Z`：新增 onWillDismiss、纠正 isModal 注释，同次给既有 Progress 加 strokeWidth13/enableScanEffect:false；L347 `21:05:58.983Z`：`ok SplashPage`，并打印新关闭拦截日志行。 | 两个修改意图都有原文；onWillDismiss 不等同之后 L352 的页面返回复位。 |
| Splash；`toolu_016H83iNne123bAaGFHtEhwF` | candidate_effect | L485 `2026-07-26T21:20:10.255Z`：新增 window import、进入隐藏、aboutToDisappear 恢复和 setSystemBarsVisible helper；L486 `21:20:13.995Z`：`ok`，其后 onRoute 读回还没有恢复调用。 | 这是返修中新建的系统栏接线。随后 L488/L489 的 onRoute 恢复是修内第二步，不能倒归生成阶段已有 aboutToDisappear 恢复。 |

成功状态不能只看 `is_error=false`，例如编译失败输出也可在成功 shell 回执内。本表同时检查断言、实际写入代码、对应 call_id、回执以及可见回读。它证明历史记录支持执行/内容，不是独立磁盘或设备重放，也不是泛化的安全脚本解释器认证。

## events 请求发生过，不代表原文已经交付

审计 Member/Splash 两个 rep 的原生 MCP 调用，发现以下两个 events 请求。它们均未返回事件正文：

| 运行及响应位置 | 请求 | 实际返回 |
|---|---|---|
| Member rep1：`runs/F10-01/rep1/transcript.jsonl:L33`, `/items/8` | events，文件 scope，同 since/at，limit200 | `status="deferred"`，`delivery.records=[]`，错误为“本批交付预算不足；此项正文未交付，请缩limit/max_chars或单独重查”。同批 diff 为 ok，多项 file/search 也 deferred，另一个 agent 为 scope error。 |
| Splash rep2：`runs/F10-02/rep2/transcript.jsonl:L42`, `/items/4` | events，文件 scope，同 since/at，limit100 | 同样 `status="deferred"`、`delivery.records=[]`、预算不足提示。同批 diff 和 blame 为 ok，多个 file/search deferred。 |

在这四份 Member/Splash 原生转录中，只查到上述两次 events 子请求；Member rep2 和 Splash rep1没有 events 请求。此句只描述记录的工具请求，不证明调查者没有从别的工具看到同一段原文。

因此不能把“已请求 events”记成“events 已展示全部余项”，更不能把未交付说成索引零命中。本审计也没有足够证据证明：若该页成功交付，模型一定会查到并解释全部缺项。

## 适合下一轮验证的假设，不是本轮收益结论

- 多目标/动态枚举写入可保守出现在独立的未决效应入口，以请求和结果坐标为依据，不能直接提升为写者真值。
- candidate 与已确认项同样提供清晰的原始请求、结果字段展开；不要求调用者把 unknown 填成错误的不存在。
- 批量预算不足时优先显式提醒“该请求正文零交付”，小页重查或按项预算可能改善余项发现，但尚未在此重跑实验。
- 将“索引没列项”“正文未交付”“模型未展开”“读后错归”分开统计。以上观察不能直接折算为工具提升、总 token 节省或纯模型失败。

## 工具运行证据 SHA256

均相对于 tools-v1，便于原样复核：

```json
{
  "runs/F10-01/rep1/transcript.jsonl": "8c8544d7e9ca43fca418c60da8b5984cf75a683a5140f26ed3ebb83d0db1a325",
  "runs/F10-01/rep2/transcript.jsonl": "946ee91c520e1c23da25bc53d5542422f0edac81471e632167e7fcaf51acf4a6",
  "runs/F10-02/rep2/transcript.jsonl": "0fdab4b9d47737a68ea0338a4b11fb44f2c3e9e1ddc293baf8ac6d206957ebde",
  "runs/F10-04/rep2/transcript.jsonl": "2768243e03a0627577e53bb402ee95eb02c73d48c7f05e4a116fdd581d99eafe",
  "runs/F10-05/rep2/transcript.jsonl": "f12722e0401d8aebc10017038461cbdac9eda6bd4fc458a1cb78773e10a7100f",
  "runs/F10-06/rep2/transcript.jsonl": "c477f6a7c00065af9c596f640defa707eb514076d911310e39b70a8091b3f2d1"
}
```

本审计不修改评分：冻结 core 判报告是否解释成立，工具内部是否确认只是一种过程证据；原始源仍是争议裁决依据。

## v2 固定快照：四个余项均可展开但不升作者

追加核验目录：`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/v2-0723-ui-audit-20260910-1`。

先尝试直接查询工作树时，四项字段断言已通过，但源码在运行期间被其他并行工作改动，最终签名屏障失败；该尝试不作为稳定版本证据。随后复制当时的 `src/migloop` 到上述目录 `code/migloop`，用一个隔离 Python 进程完成查询与真实报告投影，快照前后哈希一致。

- 快照 package_digest：`12fe84b53d73dd54eca65a3e2042a5d6c38487e0f6a1ca9d87980cdd438a20ab`。算法/逐文件 SHA 在 `probe-summary.json` 和测试脚本中定义；这是本审计快照摘要，不是 tools-v1 的 code_digest。
- 冻结池/anchor/roots 原样使用正式 settings/F10-01.json；登记源数 146。
- Member `unclassified_related.total=50`，Splash `total=74`；各用 related_limit200 的一页核到两个目标调用。类别全集并未在此逐项语义裁决。
- L103/L233 × Member/Splash 四项全部：`classification=unclassified_related`、`effect_status=unknown`、`agent=null`、`author_status=unknown`、`association=lexical_mention_not_effect`，且不在 `changes.rows`。
- 四项原生状态是 `returned`，只代表配到回执，**不等于效应或作者确认**。保留的 `source_agents` 是转录主体入口，不升级为修改作者。
- L103 匹配发生在结果 L104 的目标路径；L233 的请求及结果都匹配。两者都给出 use/result 的 raw ref、时间、block0、JSON Pointer，未强制要求调用输入先含精确目标字面路径。

原始字段展开位置为 `/message/content/0/input` 与 `/message/content/0/content`。完整四项输出保存在 `related-checks.json`，SHA256 `dc92005f0ed7b302d043b480309832c5dcc09262d9194ff93edb8f95438800f0`。这是余项可达性核验，不是把前面的原文人工判断写回系统状态，也不是宣称 v2 已理解任意脚本。

## 真实 v1 非合规报告：v2 局部预览与浏览器验证

使用未改动的 `tools-v1/runs/F10-01/rep1`。`tests/browser/real_partial_preview.py` 在上述固定源码快照中调用真实 `probe.probe_payload` → `time_probe`；没有伪造新 ledger ID 给旧报告：

- `native_report.verified=true`，来自原生最终文本 `transcript.jsonl:L102`；原始 report 文件 SHA 仍为 `b5dbca515efb5e283c44c0175666443d13c069de10e30fe32ec61f838d8fe51d`。
- 原 ledger 声明与快照构建身份相同，`identity.bound=true`，绑定范围仅 ledger/坐标，不认证因果。
- `partial_document=true`，原 schema 仍失败：`coverage[1].finding` 无对应 finding、`coverage[5].event` 重复。
- 全图 7 个有效节点、0 条有效边；4 条无效关系声明仍保留。没有为了连通补文件节点或画 agent→agent write。
- `real-partial-probe.json` SHA256：`a13f1f92e319d4c138a95685c143bcc3e8f06668cc83fa04e8f74e0b9baff5c6`；`probe-summary.json` SHA256：`2a16192fa28403c772c88bcbb635e227063e8a44523d2b961884b1c13cafca1a`。

浏览器核验分两层：

1. `tests/test_investigation_http.py` 使用合成源和真实 stdlib HTTP handler/query/check/preview，再由 CDP 操作真实页面粘贴 YAML；**31 项全通过**，包括严格正确稿和局部错误稿。局部错误稿保留 schema 错误、4 个有效节点与节点原因，仅画原有2条合法边，agent-agent write 被保留为无效声明而不画边。用户稿输入不改变 query trace 或 ledger；文本按文本展示，不执行 HTML。
2. `tests/browser/argument_graph_smoke.cjs` 用上面真实 `time_probe` 投影作为只读数据，经测试自有 loopback fixture HTTP 送入真实 HTML 渲染器。先测快照模板，再测新增角色颜色/拓扑的最新模板：都通过。真实 A finding 显示2个 agent 节点与原原因、0条边、1条无效agent-agent关系声明，并显示原稿格式诊断。合成图另外验证红/浅红/灰/绿角色颜色与中文“模型主张”图例；已有 input→agent→file 处于不同显示列；显式环保留3条原箭头和警告，不补节点/边，输入graph JSON逐字保持。

第二次浏览器运行是**固定快照投影 + 更新后的 UI 纯展示兼容**，不是把该旧报告认证到后来再次变化的当前 ledger。所用模板的测试后 SHA 为 `cbec3e360490d5123cd650f3cbd7b0b2ba625ff2d57e573fe167f4decc655e4e`。图片仅证明显示，不证明报告因果正确；测试页的 `fixture / V3 UI` 外壳标识也不是历史项目元数据。

两组截图分别位于 `screenshots/` 和 `screenshots-latest-template/`。最新图已由 AI 查看，不是人审认证：

- `screenshots-latest-template/real-partial-preview.png`：SHA256 `2db715b28abc5d4ef794d3c5f7bca410c369fd669f04f949058b7a4170b4b51e`，可见局部预览警告、角色着色、有效原因及独立断点。
- `screenshots-latest-template/real-partial-schema-errors.png`：SHA256 `f481be53095993cab8952ef46f9532bfec843a37360a29af0507deb25c6c92a8`，展开原稿格式诊断。

Chrome 以新专用 profile、Hidden/headless 方式启动，根 PID49720，CDP仅127.0.0.1:19658。测试结束后验证该PID属于本审计profile并关闭，端点不可达；Node自有HTTP server和测试HTTP线程均由finally/fixture清理，没有关闭用户Chrome或留下常驻服务。未删除截图、快照和浏览器测试profile。

途中新增合成测试曾因 `safe_dump` 为共享 evidence list 生成 YAML alias 而失败；调整测试夹具为独立 list 后31项通过。这不是生产预览器回归，也未通过放宽 YAML 安全规则让测试通过。
