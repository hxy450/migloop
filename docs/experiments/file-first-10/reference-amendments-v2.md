# 非冻结参考补证 v2

本文件是评分审阅侧补证日志，不是新的评分合同或调查员输入。不得覆盖 `baseline-v1/private/scoring-core.json`、冻结 gold、既有 raw 成绩或运行产物。补证对 raw/tools 两组同样适用；新的正确说法按已有核心接受，不能因报告未读此补证而另加必答项，也不能替旧报告补写未表达的因果。

## Dice F10-03：生成者同时期记录的大小写取舍

发现于 tools-v1/F10-03/rep2 完成后的独立裁决。报告引用 `agent-a349784d2663f1f0a.jsonl:61`，复核者回到冻结池原始 JSONL，确认这不是 ledger 后写解释。该发现强化已有 `label` 核心所要求的具体输入→输出关系，不改变分母，不以泛用 allCaps 映射冒充一条本按钮明确大写指令。

原始池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool`。以下相对路径前缀均为 `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/`，时间均为 2026-09-03 UTC。

| 证据性质 | 完整 source basename / 物理行 | 时间 / call_id | 原文或直接观察 |
| --- | --- | --- | --- |
| 具体规格实际交付 | `agent-a349784d2663f1f0a.jsonl` L53→54 | 15:39:17.927→15:39:18.139；`call_e785b4fa907646d8a4003a05` | Read 返回 F001-AC14：`判:ui \| 按钮显示 "Roll" 且源码引用字符串资源键`。 |
| 同时期记录的取舍 | `agent-a349784d2663f1f0a.jsonl` L61 | 15:50:09.007；无 call_id，原生 assistant thinking | `Android Material Button details: textAllCaps=true → "ROLL".` 随后逐字讨论 AC14 显示 Roll，写出 `the AC expects displayed "Roll"! So DON'T uppercase (textCase default none). Use the resource as-is. Good — meta.json/AC wins for semantics.` |
| 随后的实际初版落盘 | `agent-a349784d2663f1f0a.jsonl` L75→76 | 15:52:02.314→15:52:02.490；`call_03b6a5a6c470427ca32a953a` | 原生 Write 实际使用 `Button($r('app.string.roll'))`，没有 `.toUpperCase()` 和这段 `console.error`；同调用返回成功。 |
| 后期 Android 运行观测 | `agent-a342b7d08c2ca580a.jsonl` L18→19 | 17:42:46.455→17:42:46.576；`call_abbbb1ef1ec14bb1b67d0dff` | Bash 原始返回按钮 `text="ROLL"`；不能因初期选择 Roll 就宣称 Android 原本也显示 Roll。 |
| 后期实际修复 | `agent-a4874344c8fb6228d.jsonl` L68→69 | 18:29:11.587→18:29:11.605；`call_af435780b0de41ebafb443b1` | 成功 Edit 新增 `getStringSync($r('app.string.roll')).toUpperCase()`，在 catch 中同时新增 console。原资源值不改，呈现改大写。 |

L61 能证明“当事人在记录中已经考虑 allCaps，且声明按具体 AC 的 Roll 判据取舍”。它不是对唯一、必然或完整脑内机制的独立测量；报告的“或被 spec 冲突判断压过”仍应作为机制竞争解释，不强改成唯一原因。其关于 meta.json、uiautomator 或截图的技术自述也没有因属于 thinking 就自动变成外部真值。实际落盘必须另由 L75→76 认证，后期呈现策略必须另由修复 Edit 认证。

该补证不要求精确复述 AC 编号；只要报告恢复了有原文支持的具体 Roll 输入/记录判断、首轮资源绑定、后期 ROLL 呈现及责任边界，可按冻结核心判 correct。仅泛称“生成漏了主题默认值”而未表达该关系，不能由评分员替它补答。没有要求调查员自己重跑迁移或设备测试。

### 原源身份

下列 SHA-256 本轮直接计算于冻结原文件 bytes；行 SHA-256 去掉行终止符后计算。没有修改池文件。

| 完整 source basename | 整文件 SHA-256 |
| --- | --- |
| `agent-a349784d2663f1f0a.jsonl` | `2864b8fb8491bbc9e42fc75c43f801bf3656497da66cc327a19bc859c5e16bf4` |
| `agent-a4874344c8fb6228d.jsonl` | `281f00f7af306d0ede1f60447e01200d3db41f4745aeaceb9eb8aeb386452ab4` |
| `agent-a342b7d08c2ca580a.jsonl` | `f16c99aaf324a615ee629c433962f686025b85c52ca9f8ba4e0e4cf8d48f1496` |

核心新增 L61 的行 SHA-256：`eb544c8e4138972a8eba7490904d48aab9eba65f7711e0c372a51d5ff9d27dae`；完整原文定位：`raw:836a94ff9a0fe5775a69:L61:eb544c8e4138972a8eba`。

初版实际输出定位：`raw:836a94ff9a0fe5775a69:L75:b5f0a6a502d34bea50ee`、成功回执 `raw:836a94ff9a0fe5775a69:L76:88509b60c82f60e9b50e`。后修输出定位：`raw:0257ba5ffad8eed6b0bf:L68:0eb15994c3fa85fe80f1`、成功回执 `raw:0257ba5ffad8eed6b0bf:L69:ccc476d0a6a37a04959d`。

审计操作仅定点读取已有原始文件及计算哈希，未冷建 ledger、未执行日志中的命令、未调用模型。补证内容不得提供给正在运行的调查员。
