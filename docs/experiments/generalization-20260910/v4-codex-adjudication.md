# tools-v4 Codex 四跑证据裁决

2026-09-10。这是旧十文件开发集，不是新 13 文件盲评。先核冻结 core 与既有裁决尺度，再分别读取已完成的 F10-09/10 两 rep；没有重跑模型，没有修改 runtime、gold、报告或冻结包。

冻结 core SHA：`0d48f30f9e501eedd55b87e086590c72e8b7fb8096a939f56842b71703426497`。两文件各一个核心：Launch 的真实 Block→Default 及子按钮阻断近因；build-profile 的 product 对已有 default signingConfigs 引用补齐。最早作者未知、SDK细节/全部构建层级未复述，不清零核心。格式和原文定位审计独立，不把机械图成功当语义正确。

| 报告 | 核心 | 支持/断言 claims | precision | major | file pass |
| --- | --- | --- | --- | --- | --- |
| F10-09 rep1 | correct | 4/5 | 80.0% | 0 | 是 |
| F10-09 rep2 | partial | 4/5 | 80.0% | 1 | 否 |
| F10-10 rep1 | correct | 4/6 | 66.7% | 0 | 是 |
| F10-10 rep2 | correct | 5/6 | 83.3% | 0 | 是 |

partial 的数值 coverage 按冻结 validator 仍为 correct/total，即该跑 0/1；不等于完全没有识别修改。显式竞争假设不计 asserted 分母；重复 reason/edge/hypothesis/总结的同义因果主张合并。

## 关键判定

F10-09 rep1 正确解释外层 Block 阻断子节点及实际 Default 补丁，原始 A8027/8037/8052/8067/8110 支持。它把静态收尾/PASS 推成生成漏检机制，证据强度不足，记普通 unsupported；没有明确把 A8027 的修前时刻改成生成截止前，也没有无条件认证某具体生成作者，不因省略重复免责声明追加 major。关于没有证据证明 Default 的具体点击效果，按完整句解释，不改成“全池从未重建 HAP”。

F10-09 rep2 识别修改却没有解释外层对子按钮的阻断，只在“点击被拦截/穿透”之间保留泛化可能，核心 partial。明确重大错误原句：

> 生成阶段没有构建或设备复测记录；因此能定位“验证覆盖不足”这一局部环节，

A6120（`2026-08-16T21:28:08.140Z`）实际输出 `BUILD SUCCESSFUL`、`BUILD_EXIT_CODE=0`；A7687（生成截止 `2026-08-16T23:49:46.899Z`）明确 FV2 真实编译 1→0 和 unsigned HAP。A5717 等 worker NOT_RUN 不能代表整个生成阶段。这个错误历史前提被用于漏检机制，记 major1；没有把“本次未找到动机”硬改成“池内绝不存在”再重复扣重大错。

F10-10 rep1 核心签名引用修补正确。它把 A1566 原 unsigned 规则说成“不要修改 signingConfigs/signingConfig”，实际规则是确保不含这些配置/引用、已有则移除，记普通 contradicted；signed 门槛不足已解释遗漏的推论另记普通 unsupported。原生 B4944 的一行补丁、B4930 的现有材料/缺引用状态不因目标路径误拼成评测池目录而变成语义错误；错误路径及边只列 audit。

F10-10 rep2 正确读到 A4441 的清理报告：sender 确为 `/root/close_batch_02`，任务为 `stage-1-close`，不是虚构报告。全文明确代理报告不等于真实清理 write，A7970 明标“生成结束后不久”，因此不按具体作者虚构或明确生成快照倒灌判重大错。关于有意 unsigned / 后期 signed 目标变化只接受为竞争解释。

该跑另有明确错误句：

> 没有证据证明 2026-08-21 补丁后签名 HAP 成功生成、安装或完成设备回放。

B4966 的 signed/SignHap 报告、B5075 的安装/冷启报告，以及 B7694 的实际 signed HAP 构建安装输出反驳这个排他性否定。沿旧 F10-10 同类“现有记录只证明 unsigned 诊断和 patch”的尺度列普通 contradicted，不以新工具绑定标签事后增 major；它并没有由此宣称签名失败、业务已验证成功或另造修补原因。补丁单独充分性与历史构建/安装事实仍分开。

## 实际交付与证据边界

- 09 rep1：22 录制步骤、36 批内项（32ok/4error），另有独立 expand。原生 A8067 和多个生成收尾报告完整交付；SDK/完整修前源码没有据此当作已全读。
- 09 rep2：19 步、19 批内项均ok，另有独立 expand。实际读了 A5717/2607/3906 的 NOT_RUN 和 B6090 的后期视觉报告；没有取得 A6120/A7687 完整构建记录，也未取得直接问题/SDK/修复说明完整材料。未交付不等于原池没有。
- 10 rep1：21 步、32 批内项（29ok/3error）。B4943/B4944 和生成结束消息完整交付；B4930 引用多一个摘要字符导致 record error。局部核心仍有原始证据支持，不把错误引用自动降语义。
- 10 rep2：25 步、31 批内项均ok。A4441、B4921/4923/4943/4944 完整交付；若干规则/配置读取只有有续取标记的前缀。没取到后期 signed 验证不能认证“没有证据”。

源 A 是 `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl`；B 是 `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl`。正文没有复制签名材料值。已有 A8052 完整 SDK 补证适用，不把旧局部截取当证据上限；本轮没有发现需要改变 frozen core 的新真证据。

四份 JSON 含完整 report/core SHA、逐字 spans、source/line/time/call_id、claims 与独立 audit，保存于 EVAL `file-first-10/tools-adjudication-v4/F10-09|10/rep1|2.json`。全部通过 `score_raw10.validate_grade(base=tools-v4, contract_base=baseline-v1)`；去重后 37 个原始 source/line 的 timestamp、显式 call_id 逐项核对，0 不匹配。该机械校验不替代上面的语义裁决。

## Cross-cohort addendum：F10-03 Dice Index

独立回读同一 frozen core、两份完整报告和必要原始行；未把父端暂定判断当证据，未读新 13 文件参考。

| 报告 | 核心单位 | 支持/事实断言 | major | file pass |
| --- | --- | --- | --- | --- |
| F10-03 rep1 | 2 correct / 3 partial | 4/5 | 0 | 否 |
| F10-03 rep2 | 3 correct / 1 partial / 1 wrong | 4/6 | 1 | 否 |

两跑均正确解释按钮样式对齐和后期注释治理；label 均 partial：识别 Roll→ROLL，但没有覆盖生成者实际已读 AC14 的正确 `Roll` 要求及其与 Android 运行时表现的张力。生成 agent `agent-a349784d2663f1f0a.jsonl` L53/54（`2026-09-03T15:39:17.927Z` / `15:39:18.139Z`）是实际 spec Read 配对，L61（`15:50:09.007Z`）明确权衡过 textAllCaps 与 AC14/snapshot Roll，L75/76（`15:52:02.314Z` / `15:52:02.490Z`）写入资源绑定 Button。不能将其改述为忽略明确 ROLL 指令，也不能仅以最终存在差异证明初始视觉输入不足。

rep1 测试集成只覆盖后期 UI IDs，遗漏 Dice export，记 partial；rep2 同时说明 export 和 IDs 的测试访问用途，correct。原始 export 是 root `81e0a463-c9d3-4a7a-a671-b7f064830af1.jsonl` L3231/3233（`18:39:07.392Z` / `18:39:07.441Z`），UT design `agent-a4b02fab91f3dc049.jsonl` L23（`18:38:20.338Z`）解释模块私有类的测试导入限制；IDs 属于 `agent-aa1ccf93d575837a2.jsonl` L1 的后置任务和 L22/23、25/26、28/29 的成功编辑，不是初始骰子业务缺失。

日志链 rep1 仅说 console→hilog，未指出 console 来自视觉返修，partial 而非全错。rep2 明确写“初始文件确实包含 console.error 及 Android/Kotlin/Material 等注释溯源。”，将返修引入归给初始生成，logging wrong、major1。原始初版 L75 完整正文没有 console；视觉修复 `agent-a4874344c8fb6228d.jsonl` L68/69（`18:29:11.587Z` / `18:29:11.605Z`）为 uppercase catch 新增 console.error；ECAT `agent-a228e9716d833cbf3.jsonl` L57/58（`21:19:36.408Z` / `21:19:36.415Z`）才替换为 hilog.error。ECAT L1 明确 todo 行保持行为，仅登记使用点/清理注释。

交付审计与语义分开：rep1 18 条录制步骤 / 19 个批内项均 ok，step14 完整交付初版 L75/L76；rep2 18 条 / 45 个批内项（40 ok、5 deferred），step18 完整交付初版 L75/L76 等材料，因此其初版 console 断言不是“未取得初版”的免责情形。rep1 的 5 个 strict schema 错误、rep2 的错误引用/关系另存 audit，不自动清零核心。

两份新 grade 位于 `tools-adjudication-v4/F10-03/rep1.json` 和 `rep2.json`，沿同一 baseline-v1 core 通过 `validate_grade`；28 处去重原始 source/line 的时间及显式 call_id 核验 0 不匹配。没有修改原报告、参考、旧评分器或运行时。
