# v2 事后评审：8 次运行逐次记录

评审时点：2026-09-09。`dice-entry` 与 `splash` 的 raw/tools、rep1/rep2 共 8 次运行均为 `completed`。本报告由另一名 GPT-5.6-sol / medium 代理进行只读事后审阅并整理，主代理复核关键记录与用量；不是人工金标、双盲试验或模型偏差已消除的评审。审阅材料是 v2 已存报告与 metrics、仓内 58 条 reference 原文锚点及冻结 pool；未另行发起调查请求，也未修改旧 run 或冻结数据。

结论先行：8 份报告都找到了各案的真实事项集合——Splash 六项、Dice 两项；不存在“tools 才能找到事项、raw 完全找不到”的观察结果。tools 的结构化版本/候选覆盖更整齐，raw 的长文更直接呈现时间线和物理行号。两组也都有重要缺口：Splash raw 两次均漏掉主会话在首次生成前已经读到 `windowFullscreen=true` 的证据；Splash tools 两次均错误收窄为“返修后未编译”，漏掉后置 builder 的成功构建。仅有 n=2 的开发重复、明显的协议包装差异和不稳定的 token/墙钟方向，不能推出统计显著性或固定质量/成本胜负。

## 1. 口径与完整性

- 8 次均使用 `gpt-5.6-sol`、effort `medium`、源码 `d862a94`。同一 case 的 raw/tools 共用同一 `common_task_sha256`，共同提示已经明确“当前根不是范围边界、两组均可读池内全部根及 subagents”；v1 的范围歧义已修复。arm 的完整 prompt hash 因工具说明不同而不同，这是实验处理本身。
- 8 份 metrics 均为 `recording_complete=true`，且 `integrity_after` 报告 pool/source/task unchanged。tools 四次 `verdict_ok=true`、coverage complete；raw 不使用该 schema，`verdict_ok=null` 不能解释为质量失败。
- [reference-evidence.json](reference-evidence.json) 的 58 条记录已机械核验原行 SHA、解码字段 SHA、摘录偏移、timestamp、UUID 和 tool ID，58/58 locator checks passed。它认证定位，不认证因果、平台 API 语义、设备行为或修复完备。
- 下文的“覆盖”是对已核实际改动的交代，不给 raw 散文套 tools schema 扣分，也不把 coverage 中 `not_repair` 候选数量当质量分。

## 2. 每次报告的独立评价

| 运行 | 实际事项覆盖 | 做得好的地方 | 需修正或保留 |
| --- | --- | --- | --- |
| Dice raw rep1 | 2/2 | 清楚区分测试桥是 verify 后加、异常观察者是 ECAT 后加；列出生成前 EntryAbility、三次桥 Edit、三次 observer Edit；直接找到 `agent-a635…` 后置主包/ohosTest 构建与新增 WARN，并明确无 crash 触发验证 | 把初始沉浸式生成列作“第三组改动”有助上下文，但不应误读为本案第三个后续修复；部分主会话摘要仍被谨慎标为自述，边界合理 |
| Dice raw rep2 | 2/2 | 同样不把后置测试/质量门禁倒算给 Stage 1；辨认 touch 不是文本修复；桥的设备态写为 DEFERRED | observer 后置构建只引用主会话结构化转述，并称池内没有完整原始构建日志；其实 `agent-a635575c78cd15ff6.jsonl:48` 有 `BUILD_EXIT_CODE=0`/0 ERROR，`:52` 有新增 may-throw WARN。结论方向正确，证据层级低报 |
| Dice tools rep1 | 2/2 | v4-v6 与 v8-v10 分账清楚；把 v7 touch 判为非修复；直接引用 `agent-a635…` 构建，明确只认证编译、不认证异常回调；零命中边界写得克制 | 结构较长，候选清点并未增加新的语义事项；一次流重连记录不影响完成，但应与语义结论分开 |
| Dice tools rep2 | 2/2 | 与 rep1 一致并更保守地把 opaque v7 标 `unresolved`；补到桥写入后的真实编译及 observer 后置构建/WARN；生成者输入和后置门禁边界准确 | 一个工具请求被 rejected，但最终 coverage 完整且无 pending/failed；仍不能把 schema 通过解释成 observer 运行时已验证 |
| Splash raw rep1 | 6/6（写成五组，BACK 与协议返回复位合并） | 找到初版 `.onBackPressed`、entry-setup 删除、Slice 11 D-020/isModal 假设、六项实际 patch、`agent-af0e…:37` 后置 BUILD SUCCESSFUL；明确无修后设备闭环 | 系统栏归因漏掉生成前主会话已读 `windowFullscreen`; “主题证据到修复阶段才读取”过强。首个引用链接指向伪造的 `/C:/Users/hongy/projects/_eval_harmony_v1/HarmonyOS/TODO`，下一行还误写 `9b5102d…`; 虽然后续相对路径可核回，这两个不能作为证据定位 |
| Splash raw rep2 | 6/6（五类返修，BACK 内含复位） | 本组最完整的 raw 时间线；准确区分初版返回实现、entry-setup 回归、Slice 11 平台假设；图片/遮罩动态脚本、低置信进度 finding、后置成功构建与设备缺口均交代 | 仍只检查 converter 自身读取链，漏掉主会话生成前已读取主题事实，因而把 `windowFullscreen=true` 的直接证据说成后期新增。更准确应是“上游已有、未闭包进 converter 派单/读取” |
| Splash tools rep1 | 6/6 | 唯一在 rep1 中恢复“主会话先读主题、派单未传专属系统栏要求”的路由根因；覆盖两项未入账脚本；识别进度 finding 与 Android `gone` 冲突 | 开头把 BACK 与协议返回笼统写成“生成阶段实现错误”，未强调初版 converter 已正确拦 BACK、问题进入于 entry-setup/Slice 11。称“修方实测从 WebView BACK 后未回弹窗”归错角色：可核的是历史验证/finding 记录被 fixer 读取，不是 fixer 自己完成设备实验。最重要的是错误写“返修明确未编译、未复测”并据 v60 无读者推断无构建，漏掉 `agent-af0e…:37` |
| Splash tools rep2 | 6/6 | 较明确地区分 BACK/复位的 Slice 11 进入点与初版；明确上游参考设计早有 `windowFullscreen`、converter 未读；六项和两项动态脚本都覆盖 | 与 tools rep1 相同地把 fixer 派单的“不重编、不复测”扩展成整个后续池无构建；应区分“调查员尚未核验”与“后续没有构建”，后者被 `agent-af0e…:37/:40` 反驳。本次未核到修后设备复测，不能据此认证它绝不存在 |

## 3. 按原文事项对账

### Splash 六项

| 事项 | 8 报告中的覆盖情况 | 原文支持与正确边界 |
| --- | --- | --- |
| 隐私弹窗 BACK | 四份 Splash 均覆盖 | S02/S04/S05 证明初版要求、Android 源与实现都存在；S08-S10 是 entry-setup 删除；S11-S17 是后续 D-020 与 `isModal` 假设；S19-S20 是 `onWillDismiss` patch。不能归成“初版没读要求” |
| 协议页返回后复位 | 四份均覆盖，raw 合并在 BACK 项 | S21-S22 确认 `onNavBarStateChange` 增量。历史 finding 报告场景，不是本评审亲测；“谁实测”应归历史验证/采集环节，不能写成 fixer 自测 |
| 进度条 stroke | 四份均覆盖 | S03 证明生成前已读 XML height 13dp，S05 已有 Progress/height；S19-S20 只是补 `strokeWidth:13`。默认 4vp与视觉修复效果仍是历史解释，未独立设备复验；Android `gone` 冲突应保留 |
| 系统栏显隐 | 四份均覆盖，但 raw 两次少一段上游证据 | 除 S23-S26 的 patch 外，冻结池主会话在初次生成前已经读取 `windowFullscreen=true`。converter 自身未读主题正文也成立。正确归因是“事实已进入上游上下文，但未闭包进页面派发/读取”，不是“要求后期才出现” |
| app-name 图片尺寸 | 四份均覆盖 | S27-S28 证明批量脚本确实为 Splash 补 185×125；它不是独立 Splash finding。555×375 与 /3 是历史资源取证，不能单独证明修后显示对齐 |
| 弹窗遮罩 | 四份均覆盖 | S29-S31 证明全仓脚本命中 Splash、后读回 `maskColor`; S32 是共享 token 改动。修复前 alpha 是历史 finding；无修后截图 |

### Dice 两项

四份 Dice 报告都完整覆盖：D08-D17 支持 UI 测试设计、派发及 Want→AppStorage 桥三次 Edit；D18-D26 支持 ECAT 新要求、SDK 查询和 observer 三次 Edit。四份均正确指出二者晚于初始页面生成，不能自动算成初始 converter 的 Android 对等遗漏；同时也没有用零命中绝对认证更早语义不存在。

验证层级方面：测试桥写入后有真实编译证据，但设备 UI 通道没有闭环；observer 写入后 `agent-a635575c78cd15ff6.jsonl:48` 返回主构建成功/0 ERROR，`:52` 报新增 may-throw WARN。构建不证明主动未捕获异常触发、回调执行或日志回收。raw rep1 与 tools 两次抓到这组直接证据；raw rep2只抓到主会话转述。

## 4. 引用可定位性

- raw Dice 两次与 Splash raw rep2 主要使用“相对 pool 路径 + 物理行 + 完整或缩略 tool ID”。在同一行/文件上下文下，缩略 ID 可唯一核回，应接受，不要求为排版重复长 ID。
- tools 使用 `#agent:sequence@Lphysical`、`file:...@vN` 等账本定位符。它们不是文件系统链接，但在各自 MCP transcript 中可唯一展开；抽查与 Sxx/Dxx 原文锚点一致。coverage complete 只说明结构分母已交代，不认证 reason 字段的因果。
- Splash raw rep1 的 TODO 绝对路径是伪造占位，且 `9b5102d803bbcde6.jsonl` 不是实际文件名；这两处应判引用缺陷。它后续使用的 `9b.../subagents/agent-aconv-splash-9d5902d803bbcde6.jsonl:9` 等仍可唯一定位，因此不必否定整份报告。
- “没有下游 reader”不能用来否定后续 opaque builder/命令结果；这正是 Splash tools 两次漏 `agent-af0e…` 构建的机制性错误。

## 5. 验证状态：构建与设备必须分开

Splash 修复者的入站任务确实写“不重编、不复测”，但共享池后面另有 `hmos-builder`：`agent-af0e3d2ae54dbf769.jsonl:37` 为 `EXIT=0 / BUILD SUCCESSFUL`，`:40` 显示 CompileArkTS、PackageHap、SignHap 完成。raw 两次均找到；tools 两次均漏掉或反向断言未编译。该构建能确认返修后的共享工作树可编译，不能逐项认证 BACK、协议往返、系统栏生命周期、进度条、遮罩或图片。

Dice 的 `agent-a635575c78cd15ff6.jsonl:48/:52` 同理：主包和 ohosTest 构建成功，且有新增非阻断 WARN；不是 observer 行为测试。UI 测试桥另有历史设备/daemon 阻断，不能因 HAP 产出改写为 UI 场景通过。

因此 8 份报告共同成立的设备结论只有“未形成修后端到端闭环”；“历史验证代理/finding 记载了修复前现象”与“本调查或修复者亲测”必须分开。

## 6. 用量与耗时：逐次观察，不重复加 cached

`input_total` 已包含 `cache_read`; `input_uncached = input_total - cache_read`。output 已包含报告的 reasoning output，不再加 `thinking_reported`。`cost_usd_total` 八次均为 null，不能换算真实美元成本。

| case / arm / rep | wall_s | input_total | cache_read | input_uncached | output |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dice raw rep1 | 643.8 | 3,232,354 | 3,052,160 | 180,194 | 16,916 |
| Dice tools rep1 | 641.3 | 2,492,193 | 2,309,760 | 182,433 | 11,594 |
| Dice raw rep2 | 679.0 | 3,147,432 | 2,848,000 | 299,432 | 14,228 |
| Dice tools rep2 | 482.5 | 880,848 | 770,944 | 109,904 | 13,258 |
| Splash raw rep1 | 985.5 | 4,905,089 | 4,655,232 | 249,857 | 20,799 |
| Splash tools rep1 | 855.6 | 5,769,183 | 5,535,744 | 233,439 | 22,114 |
| Splash raw rep2 | 1,299.2 | 6,709,406 | 6,271,744 | 437,662 | 29,092 |
| Splash tools rep2 | 910.5 | 4,885,495 | 4,669,312 | 216,183 | 23,109 |

逐配对看，方向并不恒定：

- Dice rep1 tools 的墙钟几乎相同（-0.4%），uncached 反而 +1.2%，只是 total/output 较低；rep2 tools 的墙钟 -28.9%、uncached -63.3%。
- Splash rep1 tools 墙钟 -13.2%、uncached -6.6%，但 input_total +17.6%、output +6.3%；rep2 tools 墙钟 -29.9%、uncached -50.6%、total -27.2%。

两次均值仅作描述：Dice raw/tools wall 661.4/561.9s、uncached 239,813/146,169；Splash 1142.4/883.0s、343,760/224,811。n=2 是开发重复，不是统计显著证据；不能从 rep2 的大幅下降推断稳定收益，也不能把 Splash rep1 的 total 上升推断固定劣势。

## 7. FastMCP 重复包装与调度混杂

Dice tools 的 MCP 原始返回存在协议级重复：rep1 的 55/55、rep2 的 68/68 次返回中，`content[0].text` 与 `structuredContent.result` 逐字相等。对应 metrics 还显示：

| run | MCP leaf calls / chars | rollout wrappers / chars |
| --- | ---: | ---: |
| Dice tools rep1 | 55 / 230,586 | 23 / 381,139 |
| Dice tools rep2 | 68 / 203,353 | 15 / 199,417 |

这与本机 FastMCP 1.29.0 对字符串返回的默认结构化输出一致。它说明工具 arm 的模型输入包装含重复字段，也说明 rep1/rep2 即使 leaf 调用更多，wrapper 数/字符仍可因批次合并和调度显著下降。leaf chars、wrapper chars和 token 是不同口径，不能相加或互换。

当前源码 v3 已计划/实现关闭 `structured_output` 且保持原文字节，但它不属于冻结的 v2 处理；本报告不把未来修正回写成 v2 已控制条件。模型后一次更少 token 可能同时受缓存、调用批次、包装与调查路径影响，不能单因“账本更省”解释。

## 8. 总结与后续判据

在这 8 个观察值里，tools 的优势是结构覆盖、版本/候选去重和 Splash 上游主题路由；raw 的优势是自然时间线，并在 Splash 两次都找到后置构建，raw rep1 还直接找到 Dice builder/WARN。两边都能覆盖真实修复清单，也都会产生可核的归因遗漏。

后续比较至少应：

1. 保持 v2 的明确全池 scope，并预先冻结“事项覆盖、因果、引用、构建、设备”五个分栏；schema 只做结构校验。
2. 修复 MCP 双份返回后重新跑独立重复，记录 batch 调度、leaf、wrapper 与 token，避免协议噪声冒充方法收益。
3. 把 opaque 后置 builder 纳入统一索引；不能用目标版本无 reader 推断池内无构建。
4. 给历史实测注明 actor 和证据层级：验证代理报告、fixer 读取、独立截图/日志、修后复测不可混写。
5. 每次运行都保留，而不是挑最好一次；扩大重复并控制缓存/并发后，才讨论稳定成本差异。

本评审只认证上述已核范围，不认证冻结池之外没有更多修改、要求或验证，也不把六 Splash/二 Dice 当成无穷完备金标。
