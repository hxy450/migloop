# Transfer 执行层合同

本文件及 `run_transfer.py` 只处理公开任务、冻结和执行，不读取参考正文，不实现评分，不改变旧十文件 runner、runtime 或已冻结产物。官方 [Codex 非交互文档](https://learn.chatgpt.com/docs/non-interactive-mode) 用于核对 `exec --json`、标准输入及忽略个人配置的公开接口；实验实际 launch/native parser/settings 仍取自候选 manifest 绑定的旧 helper，未升级模型或改写旧协议。

## 输入及硬门

- `source-manifest.json`：`migloop-transfer-source-freeze/1`、`status=sources_frozen`，消费 `prepare_transfer_sources.py` 的完整 cohorts/files/tasks。保留全部声明顺序和数量，没有 10/436/228 限制；逐项 bytes/SHA 和完整目录集合同时核验，额外文件也算漂移。
- 显式 `--candidate` 及 `--candidate-sha256`：要求已冻结 `manifest.json`、`code-manifest.json`。后者路径相对 `code/src/migloop`，使用该候选绑定的 `run_pair.inventory` 原算法验证；拒绝包外文件或忽略掉的 bytecode。runtime 只从候选 `code` 复制，绝不从 `manifest.source` 的活跃 checkout 取代码。
- Registry：`migloop-transfer-registry-validation/1`，绑定 source manifest SHA 和候选 code digest，`runtime_stable=true`、before/after 完全相等。每 cohort 的 `registered` 是池相对 POSIX 路径，必须与完整 **files** 集合逐项相等，`registered_count=file_count`；JSONL 子集数量另核，只有 JSONL 注册齐全不能放行。仅 `passed=true` 或正确计数不足以放行。
- 参考封存元数据：`migloop-transfer-contract-freeze/1`，`status=frozen`、`frozen_at` 不早于候选冻结，绑定 `source_manifest_sha256`、`candidate_manifest_sha256`。其 `cohorts` 与源顺序一致，每项含 `id`、完整顺序 `task_ids`、`boundary_gap_reviewed:true`、`artifacts`；每个 artifact 为 `{role:reference|core,path,bytes,sha256}`，两类都必需。相对 artifact 路径按该合同文件目录解析。执行层只读取私有文件字节算哈希，不解析内容，不将其复制进池或 prompt。

完整注册仍不等于正文已读或 UTF-8 可解码：新的 registry artifact 另存 `decode_gaps` 和文本可解码计数。未知时间不借 mtime 认证，binary/未知仍为 gap；runner 只认证完整原始文件注册，不将其升格为作者或因果证据。

## 复用和新增边界

`freeze-candidate` 先从显式 runtime source 冻结新代码包，使用显式旧候选 template 的已认证 parser.inventory，前后核源一致；同时复制旧候选绑定的五个 helper 及本 transfer runner。它输出独立 `migloop-transfer-candidate/1`，没有旧 cases/baseline，也不读取 gold。后续 prepare 的 transfer runner 必须与该副本 SHA 一致。它只封存候选，不自动认证新池可用或允许模型执行。

后续 `prepare` 从这个冻结候选复制 runtime 和 helper，保存原路径/SHA。复用 `RAW.launch`、native parser、settings、工具 prompt、POSTPROCESS 和直接 MCP smoke；不调用旧十文件 prepare/verify/queue，也不调用旧 `registry_smoke` 的 JSONL-only 比较。新的薄 registry wrapper 复用冻结 `REGISTRY_SMOKE` 原脚本，按完整 files 比较。POSTPROCESS 只改技术 schema 名为 `migloop-transfer-final-verification/1`，包括基础 verifier 失败占位；时间/身份/格式检查无修改。新队列是公共数量参数化的调度，不提供原文预提取脚本。

公共问题两组同一原始前缀。工具组只追加原工具操作和结构化提交说明；raw 不读 helper 或答案。保留三个时间戳：

| 字段 | 用途 |
| --- | --- |
| `generation_end` | 生成输入包含上界；最终 `target.since_ts`，完整后置修改调查排除下界 |
| `repair_qualification_start` | 选样资格排除下界，不截断调查；两锚点间隔仍需解释 |
| `observation_end` | 完整调查包含上界；最终 `target.at` |

任务不提供修改原因、关键词、缺陷数量或预期作者。exposure 标签保留在 manifest/metrics，不放入模型问题。两 cohort 各自保留分母；本 runner 不聚合评分。

## 使用顺序（这里没有执行模型）

所有命令使用正式 Python 的 `-B`；示例中的路径和 SHA 均须换成最终冻结输入。缺少新的参考/核心或 source-complete candidate 时，prepare 拒绝。

```text
python -B run_transfer.py freeze-candidate --out FROZEN_CANDIDATE --runtime-source REVIEWED_SOURCE --candidate TOOLS_V4_TEMPLATE --candidate-sha256 TEMPLATE_SHA
# 之后独立检查全部源注册，并制作、审核、冻结参考/core。
python -B run_transfer.py prepare --out NEW --source-manifest SOURCES/source-manifest.json --candidate FROZEN_CANDIDATE --candidate-sha256 SHA --registry REGISTRY.json --contracts PRIVATE/contracts-manifest.json
python -B NEW/run_transfer.py verify --out NEW
python -B NEW/run_transfer.py smoke-offline --out NEW
python -B NEW/run_transfer.py run --out NEW --arm raw
python -B NEW/run_transfer.py run --out NEW --arm tools
```

`freeze-candidate`、`prepare`、`verify`、`smoke-offline` 没有模型调用；最后一个通过真实冻结 runtime 检查每个 cohort 的完整注册、guide 和默认 file overview 的真实 MCP 返回。`smoke-model` 是明确的单次模型连通性检查，另目录记录，非正式 rep，也不是运行器自动调用或失败重试。它与正式队列互斥；这里未执行。

固定 `gpt-5.6-luna`、medium、两 rep、并发 2、每次 1800 秒。一个 arm 完整预声明顺序为 rep1 全任务再 rep2 全任务；禁止 case 过滤、恢复、重试和覆盖。两个 arm 不重叠执行。基础设施/身份/记录失败停止后续调度，已开始的请求正常收尾；所有未开始任务留在 queue 尾事件。格式失败仍计为完成的实际模型尝试，不自动修稿。崩溃留下 ACTIVE 锁，拒绝后续执行，不自动清理或重启。

每次正式 run 前后核完整池、原始候选包、复制代码、helper 原件/副本、runner 原件/副本、任务、settings、封存合同及 Python/Codex 可执行文件。保存逐 run `immutability.json`；后验漂移将结果标 `harness_error`，保留先前 `raw-launch-metrics.json` 和全部原始产物，不把已产生费用删掉。`system_elapsed_seconds` 含完整性核验及工具后处理，原生 investigator elapsed/usage 仍单列；input+output，不重复加 cached/reasoning。

这些哈希是文件完整性合同，不是操作系统读取隔离、模型确实阅读正文、因果正确或完整虚拟环境依赖认证。个人 Codex 配置不写入；沿用旧 `--ignore-user-config`、关闭个人规则/技能/外网/额外代理的设置及原生上下文审计。

## 验证范围

新增 `tests/test_run_transfer.py` 使用小合成池和不合法 JSON 的 opaque 私有合同：证明不解析 gold，数量泛化、锚点/顺序/冻结硬门、同前缀、所有冻结面漂移、两 rep、失败保留及不重试。真实只读兼容回归另外验证 tools-v4 manifest `213d7b65…` 与 package digest `28b0ab3f…` 的原清单合同；没有据此认证 v4 能注册 dynamic1 全源，也没有扫描/构建真实池账本或调用模型。

当前已有旧 v4 缺源资格失败记录；新的 source-discovery candidate 和参考/core 尚未据此放行。这个 runner 的可执行实现不代表 prospective 实验已经启动。
