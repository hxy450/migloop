# SourceSpec 引用、传输及 UI 独立审计

2026-09-10。审查者仅新增合成测试、只读抽查脚本及本说明；未修改 runtime/template、旧报告、回执、评分或源池。GitNexus Exploring 检查发现没有 migloop 索引，因此未新建索引，改用源码调用点和实际接口测试。没有模型调用，没有新 transfer 池冷建账本，没有读取新 gold 或新题原因。

## 发现与处理

发现一处展示可达性缺口：可唯一定位但时间未知的辅助文件证据被 `verdict_v3.resolve_evidence` 正确标为 `undated`，旧 `argumentEvidence` 却只允许 `status=ok` 展开，且把其他状态一概描述成未核定位。父端已修模板；审查者独立验证修后行为：

- 明示“查看时间未知原文（全池独立查阅）”，发送 POST batch → record，`include_undated=true`；保留原 `at` / `since_ts`，不改用 latest。
- 仅该独立查阅使用 pool scope；原证据挂在 agent 节点也不会给辅助文件补 owner。真实 API 仍拒绝用该 agent scope 读取无归属附件。
- 原证据对象、模型原因、PROBE、查询轨迹和关系不修改。旁注明确该查阅不证明节点输入或历史关系。
- 普通 `ok` 证据沿用原 scope；`outside_scope`、`invalid`、身份未绑定仍没有展开捷径。

未发现 SourceSpec 40 位来源 key 在已测接口被截成 20 位，或辅助文件因内文 agentId/timestamp 获得作者、历史时刻或候选写边。

## 合成覆盖

新增 `tests/test_sourcespec_transport_audit.py` 共 11 项，使用真实 service 的小池构建、source discovery、collector、ledger、HTTP handler、MCP call_tool、query kernel、receipt parser 和 v3 binder。只替换测试服务入口 sid 查找、隔离缓存、无阶段区间；没有用手写 registry 代替生产 SourceSpec 构造。

| 检查 | 结果 |
| --- | --- |
| 新来源 40hex；不带 SourceSpec 的直接读取仍 20hex | 保持两种协议，旧 ref resolve 不重写 |
| 同 basename 辅助 journal | 新 ref 可区分；旧歧义 ref 仍拒绝，不挑一个 owner |
| aux 空 owner，内文未来 timestamp/agentId | `ts=null`、无虚构 actor；不推高 latest |
| HTTP/MCP 同参 batch | 解码 canonical 完全一致；正文、原 ref、scope、错误项和交付一致 |
| 未显式 include_undated / agent 归属不符 | 独立 error；delivery 不记未返回正文 |
| 原生来源不可信 / 回执正文篡改 | trace unverified，无已读原文和新增边 |
| aux 模型图证据 | undated 留在图中；possible_write 不获认证 |
| UI 实际模板 JS | 20/40 ref 完整 POST；正文按文本展示；人工打开不改图/轨迹 |

联合 `test_source_contract_review`、`test_nested_source_addresses`、`test_auxiliary_source_views`、`test_time_atom_transport_audit`：**67 passed，3.65 秒**。运行目录为 EVAL `file-first-10/pytest-sourcespec-ui-audit-b`。这是 Node 执行模板 helper 的回归，不冒充新一轮完整 Chrome/生产页面截图验收；测试创建的 HTTP 线程全部关闭。

## 一份真实旧 v4 完成稿抽查

使用 tools-v4 `F10-01/rep1`，检查 metrics 的 investigator/postprocess 均为 completed 后才读取引用串；未分析其原因正文。报告 SHA：`959bf737d76ab63417c452143723ff295df0415355c94b6983ee0ea11d0df4a4`。冻结包 manifest SHA：`213d7b657a91602db7c777f963eca47c4dcc044340e3fcf6667f7f555f1586c0`。

在报告 14 个去重 20hex raw refs 中，按出现顺序抽前 8 个：7 个原字符串/内容均保持，且新 SourceSpec 40hex 读取为同一物理行；1 个 `raw:74db82da69411ea169ff:L8:ad64e76d503b475b7192` 摘要不匹配。隔离加载原冻结 v4 resolver 后同样拒绝该引用，另 7 个同样接受；**不是新协议回归，也未自动把 L8 改成同报告出现的 L9**。

同一转录内 5 份实际 wire batch 回执（native result 行 42/49/56/63/72）均由当前 parser 校验通过，保留原 ledger 和 body hash。这里只证明录制正文/请求/canonical 的自洽，不将旧 ledger 身份改写成新 ledger，也不认证原因、已读未交付正文或历史读写关系。

完整定位、样本 source/line/time/source SHA、两版 resolver 结果、回执摘要及 runtime 文件 SHA 保存于：

[legacy-F10-01-rep1-comparison.json](/C:/Users/hongy/projects/_migloop-eval-20260909/generalization-20260910/sourcespec-ui-audit-1/legacy-F10-01-rep1-comparison.json)

原初抽查文件另存不覆盖。manifest/report/metrics/native transcript/verdict 的前后 SHA 一致；只读抽查用 source-only registry，不构建实际旧应用 ledger，不变更任何旧结果。脚本为本目录 `audit_legacy_sourcespec.py`，输出必须新文件，默认最多 8 个、硬上限 12 个引用，不输出原始正文。
