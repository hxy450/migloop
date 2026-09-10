# tools-v1 Dice 可达性对账：静态预审与冻结代码实测

状态：**原始 27 次 Edit 已复核；20 跑结束后已完成冻结 v1 真池动态查询，结果见 §6。**

父端在正式 tools-v1 计时期间要求避免并发冷建账 / 全池查询。本审计当时仅整理指定原始事件和静态方法；下面 §2–§5 保留这一阶段的基准与方法。父端明确 20 跑全部结束后，于 2026-09-10 13:44 UTC 完成 §6 动态核验。实测覆盖仅针对所列基准和选定时间点，不可扩成“全池无漏项 / 没有任何错误写者”的总体保证。

本审计已读过 Dice 旧底稿、后续评分参考和冻结 private 文件，属于**开发暴露的独立机械审计**，不是盲调查，也不估计真实迁移收益。静态阶段未读取 tools-v1 在跑报告；动态阶段之前另按父端授权裁决了已完成报告。没有向调查员提供参考答案；本可达性核验未执行历史命令、调用模型或改动 src / runner / 快照 / gold / 成绩。

## 1. 固定范围与身份

基础目录：`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/`。

| 输入 | 定位 / 身份 |
| --- | --- |
| 正式工具清单 | `tools-v1/manifest.json`，SHA-256 `c2cb98381f4babf84e5249d8c6ef84873385058d79068da53ebef2fe60c94d61` |
| 代码清单 | `tools-v1/code-manifest.json`，SHA-256 `d2634253c9280d5326aedbeca79837c89910dae369243c49a37d08296f56f9f0` |
| 冻结代码 | `tools-v1/code/src/migloop`；manifest 声明 code_digest=`ce685b2ded0a8cccdfb63ff18a2353a1b6eee0b31b8e47409f38ec48fcba1ca4` |
| 冻结时刻 | manifest：`2026-09-10T12:48:22.960655+00:00` |
| 原题 | `baseline-v1/tasks/F10-03.md`、`F10-07.md`、`F10-08.md`；已逐份读取 |
| 核心合同 | `baseline-v1/private/scoring-core.json`，SHA-256 `0d48f30f9e501eedd55b87e086590c72e8b7fb8096a939f56842b71703426497` |
| 辅助参考 | `baseline-v1/private/reference-units.json`，SHA-256 `1701ce84b3c7b58dd2182ecc9f50f22b0f80b6fe7affbe459748283bb5ec3480`；只取 F10-03/07/08 |

以上四个 SHA-256 是本次对对应 JSON 文件实际计算的结果；code_digest 和下面的池内容摘要是 manifest 声明，不冒充本次对全部代码/池文件的独立复算。

Dice 池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool`。manifest 固定 17 根、80 JSONL、合计 144 文件，content_digest=`653db4192d47366e8ca099e59ef2679e929056f18320d081768539b2f5b7443e`；池 manifest SHA-256 声明为 `b3f3aea8b01e439c5734fdc4cbe4dd0ebc9e3b4cf217b1af0a9ffcb3d97c8cf5`。

三题时间窗相同：

- 生成结束：`2026-09-03T16:46:30.036Z`，生成根 `81e0a463-c9d3-4a7a-a671-b7f064830af1.jsonl:1521`。
- 观察截止：`2026-09-03T22:09:07.188Z`，当前锚点 `49d451b1-f479-4c4e-bb39-9fa0dd06aeb0.jsonl:99`。
- 原题的修改范围是“生成结束之后至观察截止”；解释原因允许更早材料。时间查询的 `since_ts` 是包含端点的筛选，最终人工对账须排除恰在生成边界上的非后修事件。本次列出的 27 个目标 Edit 都严格晚于生成结束。
- 动态查询必须复用 `tools-v1/settings/F10-03.json` 的 MCP `env`，包括 `MIGLOOP_FROZEN_POOL`、`MIGLOOP_FROZEN_ANCHOR`、完整 17 根的 `MIGLOOP_FROZEN_ROOTS`；不能仅把 `PYTHONPATH` 指向冻结代码而忘记池环境。

## 2. 原始修改基准，不等于工具命中结果

本轮按已知 locator 定点读取原始 JSONL，读取原始 `tool_use.id` 与同源 `tool_result.tool_use_id` 配对。下列 Edit 的对应结果均为目标文件 `has been updated successfully`；旧底稿只用于找到地址，不作为成功修改的唯一依据。

各 source 别名均相对于上述 Dice 池；时间均为 **2026-09-03 UTC**。

| 别名 | 完整 source 相对路径 |
| --- | --- |
| G | `81e0a463-c9d3-4a7a-a671-b7f064830af1.jsonl` |
| C | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a349784d2663f1f0a.jsonl` |
| V | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a4874344c8fb6228d.jsonl` |
| I | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-aa1ccf93d575837a2.jsonl` |
| X | `2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a228e9716d833cbf3.jsonl` |
| T | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a711c5d09fb676814.jsonl` |
| E | `2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a27497cfed8c44856.jsonl` |
| A0 | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a39c5351955d3cd6b.jsonl` |
| A1 | `2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a87804892da9cfc8b.jsonl` |
| D | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a342b7d08c2ca580a.jsonl` |

### F10-03：Index.ets，20 次原生 Edit

目标：`entry/src/main/ets/pages/Index.ets`。事件数不是根因数。

| 编号 | source 调用→返回行 | 调用→返回时刻 | call_id | 修改内容 |
| --- | --- | --- | --- | --- |
| I01 | V L66→67 | 18:29:03.124→03.143 | `call_f8aae65f802040e3834dacd9` | 新增 rollLabel 状态与解释注释 |
| I02 | V L68→69 | 18:29:11.587→11.605 | `call_af435780b0de41ebafb443b1` | aboutToAppear 取资源、toUpperCase；catch 首次引入 console.error |
| I03 | V L70→71 | 18:29:21.552→21.758 | `call_372fc11fa9ea4d0b9d6cb347` | Button 使用 rollLabel，Normal / 圆角 / 阴影视觉调整 |
| I04 | G L3231→3233 | 18:39:07.392→07.441 | `call_6977637f2b9e4a50aaac88a8` | Dice 增加 export 供单测导入 |
| I05 | I L22→23 | 19:08:28.558→28.573 | `call_092afb020ddf4820ba7d28a7` | main_root |
| I06 | I L25→26 | 19:08:34.637→34.652 | `call_01ec83a7fd654ee3953d8eeb` | main_toolbar_title |
| I07 | I L28→29 | 19:08:41.246→41.256 | `call_905a3efe7d694017a21b4add` | main_dice_placeholder |
| I08 | X L40→41 | 21:19:16.259→16.498 | `call_5db253e02bda47708ca24068` | hilog import / 常量，头部溯源注释 |
| I09 | X L44→45 | 21:19:20.346→20.353 | `call_1e81d545becf4a3a92570556` | Dice 说明注释 |
| I10 | X L46→47 | 21:19:22.019→22.026 | `call_280e17e160d54bb98dba92ff` | 随机数说明注释 |
| I11 | X L49→50 | 21:19:29.837→29.849 | `call_88ceca4268a24f8595448c7b` | rollLabel 来源 / 忠实复刻注释 |
| I12 | X L51→52 | 21:19:31.390→31.758 | `call_9d8edc60ada140abb3ee6448` | 六面查表说明注释 |
| I13 | X L53→54 | 21:19:33.345→33.351 | `call_5dce5c8be201430fad5caa2c` | 掷骰触发说明注释 |
| I14 | X L55→56 | 21:19:35.168→35.184 | `call_9ec2acb82e6a4315a2cb60a6` | 运行时大写说明注释 |
| I15 | X L57→58 | 21:19:36.408→36.415 | `call_61dff5fdb64446998c12315e` | console.error→hilog.error |
| I16 | X L60→61 | 21:19:40.448→40.801 | `call_2b7211ed31b04d40bffe51af` | 状态栏说明注释 |
| I17 | X L62→63 | 21:19:42.101→42.108 | `call_c21577c7b5e942a88cccb498` | 标题栏说明注释 |
| I18 | X L64→65 | 21:19:43.960→44.031 | `call_d265ebfad979473982598cc1` | RelativeContainer 约束说明注释 |
| I19 | X L66→67 | 21:19:45.623→45.946 | `call_5a523f8e17d14cdeadc68f1d` | 未掷态 / todo 忠实复刻说明注释 |
| I20 | X L68→69 | 21:19:46.888→47.238 | `call_6ad19f9bd1d44ae1ad405ccc` | 标准按钮形态来源注释 |

核心因果检查点（不是额外清单缺陷）：

- C L54，15:39:18.139，`call_e785b4fa907646d8a4003a05` 返回具体 AC14：按钮显示 **Roll** 且引用资源。C L75→76，15:52:02.314→02.490，`call_03b6a5a6c470427ca32a953a` 初版 Write 使用 `Button($r('app.string.roll'))`，没有该 console.error。
- D L19，17:42:46.576，`call_abbbb1ef1ec14bb1b67d0dff` 返回 Android dump 的 `text="ROLL"`。这是生成之后运行证据，不得回投成生成者收到的具体 ROLL 指令。
- I02 新增 console，I15 后改 hilog；不能只凭晚期差异把 console 首作者安到初版生成。
- I04–I07 是后置测试接线；I08–I20 含日志门禁与注释整理，不是补掷骰业务或自动证明 todo 未实现。

### F10-07：EntryAbility.ets，6 次原生 Edit

目标：`entry/src/main/ets/entryability/EntryAbility.ets`。

| 编号 | source 调用→返回行 | 调用→返回时刻 | call_id | 修改内容 |
| --- | --- | --- | --- | --- |
| E01 | T L35→36 | 19:17:13.810→13.830 | `call_003bc0a35ce74684a5296325` | TestDataSetup import、测试桥键 / 宿主页常量 |
| E02 | T L37→38 | 19:17:21.617→21.630 | `call_6c1a4dd0da164350a549d420` | onCreate / onNewWant 调 consumeTestWant |
| E03 | T L39→40 | 19:17:35.691→35.704 | `call_04086bf7960b46e7b2a00be4` | Want→AppStorage / mock 实现 |
| E04 | E L41→42 | 21:19:24.777→25.164 | `call_f031a058037c467fb06fc159` | AbilityKit errorManager import |
| E05 | E L43→44 | 21:19:31.929→31.944 | `call_7013085c03274c8183fdd455` | onCreate 注册全局 observer |
| E06 | E L45→46 | 21:19:39.888→40.205 | `call_b6682a6aab774d88b1d1871d` | ErrorObserver 回调 / hilog / 注册方法 |

核心因果检查点：C L71→72，15:51:35.645→35.656，`call_459071197f484436b71237e5` 的初版 Write 已有窗口 / 沉浸式能力，并非整个 Ability 空壳。T L1（19:10:08.728）明确“只做测试代码与测试数据落地”、只追加桥，T L11→12（`call_769beeda1a324d3d95de7251`）读回测试设计。E L1（21:17:54.685）才是后置 ECAT observer 派单；其中“无 crash 报告”的绝对解释不能作为工具核验出的技术事实。

系统 jscrash 反例和后续构建 / 测试记录是**验证或反证入口**，不是新代码修改。旧 dossier 已定位 `agent-a52d61ac7ab7033ba.jsonl` L139→140，19:28:23.702→24.213，`call_a308ad2fae7c4c99a119b8ec`；该项本轮尚未再次展开，不将旧摘要冒充本轮新读回。

### F10-08：AppScope/app.json5，1 次原生 Edit + 相邻资产复制

| 编号 | source 调用→返回行 | 调用→返回时刻 | call_id | 修改内容 |
| --- | --- | --- | --- | --- |
| A01 | A1 L49→50 | 21:19:08.646→08.653 | `call_2a22aef71a3641f19092ca7c` | bundleName `com.example.myapplication→com.example.diceroller`；vendor `example→diceroller`；icon `app_icon→layered_image`；同一次 Edit |
| A-assets | A1 L45→46 | 21:19:00.755→00.809 | `call_c8f9430feac54929af417cb1` | Bash 复制 entry 的 background / foreground PNG 和 layered_image.json 至 AppScope；是相邻资源效应，不是对 app.json5 的第二次写入 |

本轮只读 A-assets 命令及返回，绝未执行 `cp`。原始返回有 copied 列表，完整匹配哈希等细节见既有 dossier；这些材料是否由 `events(file=app.json5)` 命中不可先验保证，复制命令本身未必要包含 app.json5 字样，应允许独立查该 agent 或相邻资源。

阶段反证已再次核原始：A0 L1，15:31:54.536，明确“**不碰 bundleName / vendor**（部署期 D-009）”；A1 L1，21:17:38.624，后置身份任务才要求两者改变。A0 L59→60，15:35:18.958→18.971，`call_9eeac76f5b9a45d6ac08a6ef` 是生成期 versionCode / versionName 对齐，不应计入后修清单。A01 没有改变这些版本字段。

## 3. 各查询必须分别证明什么

| 对账对象 | `changes` 需要核实 | `diff` 需要核实 | `events` / 原文需要核实 | 当前实测状态 |
| --- | --- | --- | --- | --- |
| I01–I20 | 逐调用映射，去重后覆盖已知 Edit；注释 Edit 不吞掉 | 不能只给最后一次净差异就称覆盖 20 次事件；需分辨早期视觉 / 后期 ECAT | 请求 old/new 与成功回执，按实际 source / 行 / call_id 回连 | 已实测：20/20，见 §6 |
| E01–E06 | 两阶段修改皆可发现，不只最后 observer 三笔 | 保留初版窗口能力；基线不得偷用后来的完整桥 / observer 状态 | 初版 Write、测试派单、ECAT 派单、原文与回执独立可查 | 已实测：6/6，见 §6 |
| A01 | 同一成功 Edit，不能制造多个作者或修复轮 | 前后 bundle/vendor/icon 均可比较，version 不变 | 初期禁止、后期授权、资产复制各自保持原始来源 | 已实测：1/1，见 §6 |
| A-assets | 不应冒充本文件另一条 confirmed change | app.json5 的 diff 不能认证 Android launcher 资产迁移 | 允许另查 agent / media；独立访问不强制与 app.json5 形成历史读边 | 已实测：file events 未命中，agent events 命中 |
| touch / 构建 / readback | 检查候选 / 观察行有没有被错标正文修改 | readback 最多支撑观察区间，不能自动推唯一写者 | 构建输出、触达、快照与真实 Edit 分开 | 所列两条 Bash 保留 candidate，观察行作者未知 |
| 生成前事实 / 生成后反证 | 不因清单没有它就称不存在 | 不能把截止末状态回投生成结束 | 更早查询不继承修复窗口的 since_ts；晚期证据按其实际时间展示 | 10 个状态点与 L61 早期字段展开已测；不是穷尽所有反证 |

`changes` 中缺少某项不直接等于原文不可达；`events` 只是原生事件入口也不等于自动完成原因归纳。相反，某文件 `diff` 有变化不能认证全部中间修改或先前输入已交付。静态阶段未填任何命中率；当前测得的数据与剩余限制集中在 §6。

## 4. 冻结实现的静态边界（不是运行结果）

- `service.py:41–104, 223–228, 440–463`：冻结池 / roots / anchor 显式校验、整池路径检查、账本内存缓存。后续动态运行不能换回工作区代码或宿主全局发现。
- `change_inventory.py:77–141`：额外原生效应通道对无可核作者的记录保留 `agent=None`、`author_status=unknown`、`source_agents_are_not_authors=True`；有源会话不等于确定写者。
- `change_inventory.py:150–255`：已解析操作与额外原生效应按 source/line/target 去重；仍需实际检查这批 CC Edit 有没有被准确收集，不能由函数存在推定全命中。
- `change_inventory.py:289–301`：观察差异使用 `observed_at`，`use_ts/done_ts/change_time=None`，作者未知。此状态不是发生修改的精确时间，更不是生成期或后修期唯一责任证据。
- `temporal_state.py:20–79`：按调用/完成时刻重放，晚到读取及未解析原生效应有边界/屏障；`query` 的 `known` 与原文入口分离。必须实测生成结束与晚期时刻，排查晚期 sealed / readback 被提前采用。

## 5. 空闲后执行方法（原计划，已按 §6 实测）

动态审计须单个 Python 进程串行冷建账一次，记录真实起止时间；使用 manifest 指定 Python，`-I -B -X utf8`，在导入前把 `tools-v1/code/src` 放到 `sys.path[0]`，并载入 `settings/F10-03.json` 的 MCP env。不得从 repo 执行测试 fixtures 来替代正式池，也不启动 MCP 调查模型。

核对 `service.__file__` 确实来自冻结路径后，使用 `service.session_ledger(manifest_case['sid'])`，再调用同一个冻结 `investigation.query` 内核：

```python
# 核心查询形式；本次实测将 limit 提到 200，diff max_chars 提到 120000。
args = {"path": case["file"],
        "since_ts": case["generation_end"],
        "at": case["observation_end"], "offset": 0, "limit": 40}
changes = investigation.query(ledger, "changes", args)
diff = investigation.query(ledger, "diff", {**args, "max_chars": 6000})
events = investigation.query(ledger, "events", {
    "scope": changes["scope"], "offset": 0, "limit": 40})
```

必须按实际 `next_offset` 遍历，而非把第一页数量当总量；diff 的部分正文还需按实际返回窗口处理。对每个原生基准事件记录工具 event id、状态、作者字段、调用/完成/观察时间、原文引用及是否只能从事件或快照入口找到。用原始 call_id 和 source/行回对，不以工具自报状态自证正确。

另对三个文件分别在生成结束、各主要修复阶段前后及观察截止取有界状态，检查：初版是否无 console / 测试桥 / observer；app.json5 生成期版本对齐是否未混入后修；缺快照或屏障是否诚实返回未知。原文重查可使用独立的更早 scope，不把池内可访问解释成作者当时已读。

本可达性核验只更新本文的动态结果与限制，不修改冻结合同、raw/tools 成绩或实验提示。自有查询进程已结束，无 HTTP / MCP 服务进程遗留。

## 6. 冻结 v1 真池实测

### 6.1 执行身份和时段

使用正式解释器 `C:/Users/hongy/projects/migbot-elite/.venv/Scripts/python.exe -I -B -X utf8`。独立进程先将 `tools-v1/code/src` 插入 `sys.path[0]`，载入 `tools-v1/settings/F10-03.json` 的完整 MCP env，再导入并调用冻结 `service.session_ledger` / `investigation.query`。运行时逐一断言 `service`、`investigation`、`atoms`、`change_inventory`、`raw_events`、`temporal_state` 的 `__file__` 均位于冻结路径，未导入 repo v2。

- 成功核验进程：`2026-09-10T13:44:19.845646+00:00` 至 `2026-09-10T13:44:49.420943+00:00`，总计 **29.578 秒**；其中冷建账 **2.541 秒**。
- 实際账本身份：`atoms-2026-09-10-temporal1:80:121a06bcaf8b934444c18024`，`source_stats` 为 80 个来源，与正式报告使用身份一致。
- 运行前有两次审阅脚本从本文表格提取 call_id 时误选无 call_id 行，分别在 `13:43:40.406872`、`13:44:05.477694 UTC` 开始；均在冷建账约 2.5 秒后异常退出、尚未调用 changes/diff/events。只修正了临时审阅脚本的取表项过滤，没有改冻结工具。二者均已退出，且全部发生于父端确认 20 跑结束之后。
- 本轮重新计算 manifest 和 code-manifest 文件 SHA-256，仍分别为 §1 的 `c2cb9838…c94d61`、`d2634253…f9f0`。代码内容总摘要仍引用 manifest 声明的 `ce685b2d…1ca4`，不冒充本轮完整代码清单复算。

这里测量的是直接调用同一冻结查询内核的可达性，**不是重新跑一轮调查模型，也不是对调查员实际收到的批预算/截断正文作回放**。无法由这些耗时推断两组模型的延时收益。

### 6.2 修改基准逐项命中

changes/diff 使用原题 since/at，`limit=200`；diff 每行 `max_chars=120000`。三文件均一页返回全部清单，`next_offset=None`。file events 则按 `next_offset` 完整遍历；Index 需要两页，其余各一页。下表所有数量来自完整所选范围，不是默认第一页。

| 文件 | 原始 Edit 基准 | changes 总数 | confirmed / observed / candidate | diff 行数 | file events 原生相关数 | 普通/未分类记录相关数 |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| F10-03 Index | 20 | 25 | 20 / 3 / 2 | 20 | 251（2 页） | 367 |
| F10-07 EntryAbility | 6 | 10 | 6 / 2 / 2 | 6 | 80（1 页） | 115 |
| F10-08 app.json5 | 1 | 1 | 1 / 0 / 0 | 1 | 64（1 页） | 127 |

三个 changes 均 `gaps=[]`、`complete=false`；三个 diff 均 `known=true`、`gaps=[]`，全部 diff 行 `basis=native` 且正文未截断。file events 的来源数均 80、gap 0、undated 0。events 相关数包括只读、派单、其它文件写入中的提及等，**不是修改数，也不是 v2 未分类余项数**。

已用本稿 §2 原始 call_id 集合与 changes 的 `event_id` 后缀对账：27 个确认事件无缺项、无额外确认项，亦均可在 file events 按原生 call_id 找到。再将 changes 的 `legacy_ref` 与 diff 行 `ref` 全量对齐，27 个均有对应 diff。逐组检查返回执行者、use/done 时刻和 raw 原文行均与 §2 原生表一致：

| 原始编号 | 冻结返回执行者 | changes / diff 相同的 legacy 定位（各自附 §2 的原始行） |
| --- | --- | --- |
| I01–I03 | `agent-a4874344c8fb6228d` | `#a4874344c8fb6228d:2270@L66`、`:2272@L68`、`:2274@L70` |
| I04 | `__main__:81e0a463` | `#81e0a463:1272@L3231` |
| I05–I07 | `agent-aa1ccf93d575837a2` | `#aa1ccf93d575837a2:3109@L22`、`:3112@L25`、`:3115@L28` |
| I08–I20 | `agent-a228e9716d833cbf3` | `#a228e9716d833cbf3` 的 `4411@L40, 4415@L44, 4417@L46, 4420@L49, 4422@L51, 4424@L53, 4426@L55, 4428@L57, 4431@L60, 4433@L62, 4435@L64, 4437@L66, 4439@L68` |
| E01–E03 | `agent-a711c5d09fb676814` | `#a711c5d09fb676814:2881@L35`、`:2883@L37`、`:2885@L39` |
| E04–E06 | `agent-a27497cfed8c44856` | `#a27497cfed8c44856:4511@L41`、`:4513@L43`、`:4515@L45` |
| A01 | `agent-a87804892da9cfc8b` | `#a87804892da9cfc8b:4753@L49` |

这说明确认写入执行者在所列 27 条上没有错配，不证明他们是缺陷首次引入者，也不宣称工具对全池所有作者判断都正确。

### 6.3 哪些仅是观察/候选入口

Index 额外三条 `observed_change` 的观察时刻分别为 `18:33:37.611`、`19:10:24.969`、`21:23:41.463 UTC`；EntryAbility 两条为 `20:55:16.544`、`21:23:41.360 UTC`。五条均返回 `agent=null`、`author_status=unknown`、`use_ts=null`、`done_ts=null`、`change_time=null`，用 `observed_at` 表示看到后侧全文的时刻。它们没有被算进 27 条 confirmed，也没有在 diff 中制造额外已证作者行。

Index 与 EntryAbility 各保留同样的两条 `candidate_effect`：`call_afebad7ee5364ed4b444c0ef`（20:15:05.530→05.579）、`call_df65c4b5e96d4fb892f971c6`（21:06:18.476→23.938）。前者 actor 为 `agent-ac3b22afb4458cd07`，后者 `__main__:593d4e86`。这两个 agent 字段定位实际调用者，不认证其改过目标正文；原始命令包含 touch/构建，touch 本身只足以改变 mtime。v1 没把它们升级为 confirmed，但候选与已解释净文本之间的关系仍要人工审查。

三个 v1 返回的 `unclassified_related` **仍只有** `query:{tool:'events',scope:...}` 和一句“纯提及/未分类原文另查，不升级为候选写者”；没有 `total`、类别计数或独立余项分页。不可拿 repo 后来新增的 related_* 能力描述此 v1。这里即使已知 27 条全命中，仍存在“把已识别清单当完整修改清单”的交互风险。

### 6.4 时间边界实测，不回投后期状态

使用 `blame(path, at, since_ts=None, limit=200)` 查询 10 个累积状态点；每次都返回 `known=true` 且单页装下全部行。下列存在/不存在只针对实际返回的代码文本，不是全池输入曾否交付的结论。

| 文件 / 截止点（2026-09-03 UTC） | 实测代码状态 |
| --- | --- |
| Index / 16:46:30.036 | 124 行；无 toUpperCase、console.error、export Dice 或 main_root。 |
| Index / 18:29:22 | 147 行；已有 toUpperCase、console.error；仍无 export Dice、main_root。 |
| Index / 22:09:07.188 | 158 行；已有 toUpperCase、export Dice、main_root；console.error 已消失。 |
| EntryAbility / 16:46:30.036 | 82 行；已有 setupImmersiveWindow，无 consumeTestWant、onNewWant 或 registerGlobalErrorObserver。 |
| EntryAbility / 19:17:36 | 122 行；已有测试桥、onNewWant，仍无全局observer；窗口能力保留。 |
| EntryAbility / 21:19:41、22:09:07.188 | 两次均 142 行；测试桥、onNewWant、observer、窗口能力均在。 |
| app.json5 / 16:46:30.036 | 13 行；bundle=`com.example.myapplication`、vendor=`example`、icon=`app_icon`；versionCode=1、versionName=1.0。 |
| app.json5 / 21:19:09、22:09:07.188 | 两次均 13 行；bundle=`com.example.diceroller`、vendor=`diceroller`、icon=`layered_image`；版本不变。 |

没有在这些选定状态点发现大写、console、测试桥、observer 或最终身份向生成结束倒灌。blame 同时保留未知文本来源：Index 各点 10 行；EntryAbility 初始/桥后为 33 行、observer 后/最终为 32 行；app.json5 初始 11 行、后修/最终 8 行。`known=true` 是内容状态，不是所有行作者已知。

### 6.5 独立查阅与跨文件入口

**资产复制：** `call_c8f9430feac54929af417cb1` 不在完整 `events(file='AppScope/app.json5', since_ts=生成结束, at=观察截止)` 的 64 个 native 相关事件里；该调用未词法提及 app.json5。这不表示复制不存在。

换成 `events(agent='agent-a87804892da9cfc8b', since_ts='2026-09-03T21:18:59Z', at='2026-09-03T21:19:01Z')`，实际返回唯一一条 Bash `returned`，正是原始 L45→46：

- use：`raw:2f0a4bfbb1087f9da721:L45:ec5131ecc2d5f7088c8c`，`/message/content/0/input`，517 字符。
- result：`raw:2f0a4bfbb1087f9da721:L46:0e926659f8ae63cf8598`，`/message/content/0/content`，875 字符，`failed=false`。

这是 entry→AppScope 相邻资产复制的可核入口，不是第二笔 app.json5 Edit，也不能认证 Android launcher 迁移。允许沿实际修复代理独立查阅；不应要求先伪造本文件的历史读边才允许看它。

**早期取舍：** 对 `raw:836a94ff9a0fe5775a69:L61:eb544c8e4138972a8eba` 使用 agent scope（`agent-a349784d2663f1f0a`，`at=生成结束`，`since_ts=None`），实际调用 `record(pointer='/message/content/0/thinking', offset=60400, max_chars=2300)`，成功展开含 `textAllCaps`、AC14 与 `So DON'T uppercase` 取舍的字段正文，耗时约 0.030 秒。它不依赖把后修 since_ts 强加给生成输入，也不要求把独立查阅投影成历史传播边。具体源与解释界限见 [reference-amendments-v2.md](reference-amendments-v2.md)。

### 6.6 结果的适用范围

本次实测支持“这三个文件的已知原生修改及所列独立材料在冻结 v1 中可达”，不支持“调查员一定收到全部材料”“模型必然正确归因”“未知脚本效应已穷尽”或真实迁移收益。构建、系统 jscrash、后期回放等原始验证/反证已在底稿有定位，但本次动态查询没有逐一展开它们，不把静态地址自称为本次实际交付。

三个 `unclassified_related` 没有数量/分页的 v1 限制、跨文件 copy 需另查 agent 的事实，不能被已知 Edit 命中率掩盖。没有更改 frozen v1、runner、gold、rawgrades 或工具组已完成报告；成功核验进程退出码 0，无自有进程遗留。
