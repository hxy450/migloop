# V6 C4 reference：真实查看器核验

日期：2026-09-09。调查源/查看器均为冻结 `4d5db4f`；页面端口19667，使用已有 Chrome CDP19652。没有调用模型或修改源、冻结材料、原始 run。

页面：`http://127.0.0.1:19667/api/insight1/fixchain/01a021e5?probe=attribution10/formal-v6-reference/codex-c4/runs/tools/rep1`。

## 已核对

- `probe_basis_smoke.cjs` 与 `probe_smoke.cjs` 均通过。未提供 basis，诚实返回 `missing=[basis]`，不是伪造归因对照通过。
- 引用提交对应本 run 的 `verdict.yaml`，4856 UTF-8字节；浏览器 `structured.raw` 与该文件逐字一致，3条节点 reason 与原 YAML 逐条相等。
- 文档 SHA-256：`3251273b1be3698d699788f006389b3d0c8a2d2b4974bd825f3ec4aa63f1a88f`，与原 `submission.json` 一致。
- `document_source.kind=checked_draft_ref`、`verified=true`、`semantic_checked=false`，来源栏明确同 run 核查稿引用，只认证出处，不认证根因。
- 最后 check 为第76步，状态 `matched`、工具原始状态 `mechanical_clear`，返回0条问题、省略0条；第76步不在版本访问列表中。该结果不是归因准确率或修复验证。
- 76条MCP调用、0条宿主包装；页面有完整1–76步的调用行，可在面板滚动查看，不要求同时进入屏幕。
- 4个精确版本节点、5次版本访问、4条查询转移。查询时间线保留步骤 `[13,24,57,74]`；读写主图仅1条边：`agent:__main__:01a009fe@249 → file:.../LaunchAgreementDialog.ets@1`，`kind=write,status=true,source=ledger,steps=[13]`。其它导航没有混入主图。
- findings 为1文件/1事项/0未绑定。文件归集依据模型给出的 `repair.after=file@v1`；UI明确“版本坐标已核”与“模型声明修复关联/语义未核”不同，不自动补造 before 或缺失版本。
- 目前覆盖分母是0/0，页面说明空清单不代表调查完整或修复正确。
- 展开核查、来源、归集明细前后，trajectory SHA-256 均为 `fbb06f70bd0d12e73ed4c87fa10545bfaa27f56c6391ecd13d8cbd2552dce7c4`；evidence_graph SHA-256 均为 `9856b220b182bdb802a41ac13199175f4c48d973f29d8d34a47fe73bc3bc2c05`。
- 补充来源核验前后，run 中全部现有文件的名称与 SHA-256 相等，没有新增/改写任何运行产物。无 JavaScript 异常；文件抽屉实际内容已加载，不是只截到“装配中”。

## 发现：真实节点被占位节点遮挡

两个既有 helper 主要核DOM数量、边投影和状态，不检查矩形重叠，因此不能把其通过解释为所有节点都能实际看见。

在1900×1300视口中：

- `agent:__main__:01a021e5@18`，布局 `x=24,y=72`；
- 一个 `+2 未查` leaf 占位，布局相同；
- 两者实际矩形完全重叠：left=417.9585，top=267.8442，right=605.4528，bottom=296.5423。

四个真实节点均在画布视口内，但该 agent 被后画的占位块遮住。这是实际布局缺陷，不是丢失原始查询：节点和第57步仍在 trajectory/时间线中。应在后续独立查看器版本修复布局，保持本轮源和下面截图不变。

## 新截图

- [核查明细](screenshots/v6-c4-reference-basis.png)
- [读写主图与来源](screenshots/v6-c4-reference-trace.png)
- [按文件归集与原文原因](screenshots/v6-c4-reference-source.png)

三张截图均已实际查看；保留原布局遮挡状态。这里只核可追溯展示与交互，不裁定模型原因是否正确。
