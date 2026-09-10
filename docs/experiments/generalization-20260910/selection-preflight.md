# 留出集资格与曝光预检（2026-09-10）

状态：**已有六个dynamic1跨运行预备文件，但尚未组成至少两个新业务项目的正式留出集。** 没有生成gold、没有读候选归因答案、没有运行模型、没有执行历史命令、没有改runtime。本预检只依据会话/业务身份元数据、时间标记、原生修改配对、源文件可用性及既往产物路径曝光。

## 边界与选取程序

1. 先限定migloop既有默认输入源、已有`dist`导出/_sources登记和用户指定工程。读取目录/会话header/缓存source指针定位；不扩展到无关工程正文。元数据首行没有cwd或timestamp时继续读取有效元数据，不用mtime冒充历史时刻。
2. 将业务身份与工作目录分开登记。相同AIPPT业务的不同迁移目录只能称跨生成运行；不能由新文件名或新cwd宣称跨app泛化。
3. 先确认初期阶段结束/后修起点和观察截止。工具启动回执不当整场工作完成；workflow完成元数据与后续原生调用分开记录。缺明确边界的项目只列待核，不凑数。
4. 第一份预备清单用纯结构筛选：应用路径位于`entry/src/main`或`AppScope`；窗口前有成功原生Write；窗口后至少两笔成功、非同文Edit/Write；历史至少两个不同actor。每笔按同源+call_id唯一配对，失败、缺/重复返回、时序不明或倒序不当成功。
5. 排序只用规范化小写绝对目标路径的SHA256升序，取前六；未按原因类别、模型输赢或哪组更易调查挑选。该路径哈希算法与全部29项候选排序在JSON中保留，不换一种排序来迎合文件偏好。
6. 此次六文件仅为native种子清单，不是整个效应全集。Bash/PowerShell及侧文件保留在源清单中；之后若原始脚本能核目标、实际写入与成功回执，同样可入资格。不能仅因解析未分类排除，也不由脚本意图、外层返回或报告转述认证效应。当前没有读取这些脚本的具体原因/修复正文。
7. 曝光检索只返回文件路径，不打开历史模型答案：在`docs/experiments`和`C:/Users/hongy/projects/_migloop-handoff`用项目字面量、根ID和候选basename做`rg -l -i -F --hidden --no-ignore`。负结果只覆盖这两个存储范围，不认证用户从未在任何地方使用过。

## 项目与源池登记

| 工程/业务 | 当前原始源与数量 | 边界资格 | 既往曝光 | 本轮结论 |
| --- | --- | --- | --- | --- |
| transfer-app-dynamic1 / AIPPT | `migloop/dist/_sources/dynamic1-20260908/C--Users-hongy-projects-transfer-app-dynamic1`；1根+77个workflow子JSONL；共169个文件含侧文件 | 有页面workflow完成元数据、后续验证workflow请求及最晚原始时刻；详见下一节 | `dist/dynamic1-20260908.html`；README中的live使用示例；live缓存。未命中既往experiments/handoff项目/根ID及六basename | 六文件预备；只跨运行，不是新app |
| transfer-app-noarch630 / AIPPT | 当前原`.claude/projects/C--Users-hongy-projects-transfer-app-noarch630`源缺失。主根cache登记1根+76子，77个源路径均不存在；另有同cwd的单根cache指针也缺失 | 静态页覆盖07-18至07-19，但当前不能回原始源认证修改和边界 | `dist/noarch630-token-totals-20260908.html`；`tests/test_model_usage.py:57`历史计费fixture | 暂不可选；不拿HTML/cache当原文。也不是跨app |
| transfer-app-arch11 / AntennaPod | `dist/arch11-session-462439ee-full.zip`，50,093,664 bytes；385个归档成员，1根+192子JSONL。无需解压即可只读 | 根有spec/plan/execute原生阶段调用；当前未确认独立生成结束后修复窗口，详见下文 | `dist/arch11-lineage-20260818.html`和live缓存；experiments/handoff未命中项目/根ID | 完整新业务源候选，阶段资格待核，未挑文件 |
| transfer-app-calendar / Simple Calendar | 默认Claude目录`C--Users-hongy-projects-transfer-app-calendar`，2根+175子JSONL，共177 | 根可见前置阶段元数据；没有已核实完整生成结束后修复窗。结构扫描仅7个app目标/13笔原生修改调用，未据此断言脚本无其它效应 | 本次限定曝光检索未命中 | 待核，不把前置文件改动算后修 |
| transfer-app-dynamiccalendar / Calendar相关，完整业务身份尚未认证 | 默认Claude目录同名，3根+22子JSONL，共25 | 可见范围内0个app原生Write/Edit目标；无已核实生成后修复窗。该计数不排除脚本效应 | 本次限定曝光检索未命中 | 不纳入本轮正式候选 |
| transfer-app-pod730 / AntennaPod | 默认Claude已有1根+220子JSONL | 本轮未重查原因/边界 | 已有`docs/experiments/2026-09-08-pod730`工具/原始组调查与调优史 | 不称未曝光工程 |
| transfer-app-dynamicpod / AntennaPod | live缓存登记根77ed45e3…及113流；原source路径缺失，`dist/_sources`没有该池 | 没有当前已定位完整原始池 | 缓存登记本身是工具使用曝光 | 待原始归档定位，不拿cache入选 |
| Game2048 / 2048 | 默认DevEco只读SQLite；根ses_f753c2116ffeVbeElqXwve5bIi+6子会话，独立cwd见下文 | 有原生tool状态及目标路径；尚未核明确生成结束后多文件修复窗，且不是已冻结的CC/Codex输入池 | 本次experiments/handoff字面量未命中；默认DevEco已接入不等于零曝光 | 仅metadata登记，不因此改适配器或凑入六文件 |

特别说明：workflow子记录不是通常的`*/subagents/*.jsonl`平层。dynamic1使用`subagents/workflows/<workflow-id>/agent-*.jsonl`，calendar亦有嵌套子记录；浅glob会错误报告0子记录。本预检对子JSONL采用递归实际文件清单。

## dynamic1：可回核的操作窗口

- 项目cwd：`C:/Users/hongy/projects/transfer-app-dynamic1`；根中另有其`entry`和`entry/src/main/ets`子cwd，不当成新工程。
- 根：`5629edf4-bf1b-4616-81fb-e2c7b3c2ca26.jsonl`，2012行。首个有timestamp记录L4为`2026-07-28T09:24:19.249Z`，全根最小时刻L5为`.248Z`；未强求文件行号时间严格单调。
- 页面生成workflow元数据：`5629edf4-bf1b-4616-81fb-e2c7b3c2ca26/workflows/wf_ad353c88-28d.json`，`workflowName=aippt-pages`、`status=completed`、`agentCount=11`、`timestamp=2026-07-29T01:59:05.818Z`。startTime+durationMs计算为`.816Z`，两者差2ms，保留实际元数据时刻而不伪造单一精确结束。
- 六文件预备筛选的下界：根L817原生Workflow请求，call_id=`toolu_0129Za1Vi13XFSXrAHVjttXx`，`2026-07-29T02:01:30.213Z`。该界晚于前述完成元数据；作为首轮验证操作的排他下界，不宣称全项目一切后续生成工作此后绝不存在。
- 观察上界：根L2012，`2026-08-03T03:24:28.258Z`；78份JSONL的最晚已记录时刻同此。截止后返回不倒灌；未知时间不猜。
- 全78份JSONL共15,285条记录；原生Write174、Edit366，应用目标中479笔唯一成功配对、129个规范化目标；另12笔目标失败回执不计成功。按上述结构资格得到29个文件。
- 完整169文件清单、字节数及SHA256存于`candidate-dynamic1.json.source_manifest`；该清单规范JSON的SHA256为`0810f41cf0aafaf745835639ac4eb60c902c22da660d3382e59e32c4175c8f6b`。

### 六个预备文件（不附修改原因）

路径均相对于dynamic1的`entry/src/main/ets/`。括号内为窗口前/后成功原生修改数；每个均有两个不同actor。

| 顺序 | 文件 | 前/后 | 初始Write locator | 窗口后原生locator |
| --- | --- | ---: | --- | --- |
| 1 | dialogs/LimitedGiftDialog.ets | 8 / 2 | agent-a50893932d99e9431.jsonl L198→199 | agent-a5c43a8d488c34fac.jsonl L70→71、L72→73 |
| 2 | api/HttpCore.ets | 1 / 6 | 根L407→408 | agent-a7af25d1f05929843.jsonl L75→76、77→78、79→80、82→83、84→85、86→87 |
| 3 | components/works/WorksView.ets | 6 / 7 | agent-a0af991fab683fb38.jsonl L162→163 | agent-a5b3e8cf8f09b9231.jsonl L83→84、85→86、87→88、89→90、91→92、93→94、95→96 |
| 4 | components/template/RecommendView.ets | 10 / 3 | agent-a7b9bdac12337387c.jsonl L150→151 | agent-af3b8741ba1089d77.jsonl L85→86、87→88、90→91 |
| 5 | db/PptDb.ets | 1 / 2 | agent-a4dfc6ec33076a7eb.jsonl L98→99 | agent-a5b3e8cf8f09b9231.jsonl L78→79、80→81 |
| 6 | pages/ChoicePPTTemplatePage.ets | 4 / 6 | agent-a79303a94c692a308.jsonl L195→196 | agent-a556cdbbffb54b127.jsonl L134→135、136→137、138→139、143→144、148→149、150→151 |

JSON另含每笔完整相对源路径、call_id、block、请求/返回时刻、actor和选择哈希。这里只认证可见的实际后窗修改资格，不认证这些修改的业务动机、正确性、必要性、唯一作者或最终行为。所谓复杂性目前是多actor/多轮的结构事实，不是已经挖出的因果困难标签。

独立回读校验已完成：六个初始Write加26个后窗Edit共32对，逐对核source行/block/call_id、带时区时刻及原生返回的successfully文本；169个源文件哈希全部仍与清单相同。结果在`qualification-check.json`。没有执行任何源内命令。

曝光结果：写本目录前，项目名、完整根ID、上述六basename在既往experiments/handoff检索均返回0匹配；正对照MemberCenterPage.ets返回80个artifact，确认检索不是失效。该零命中不抵消dynamic1先前静态UI/README演示曝光，且六文件均仍属AIPPT业务。未来实验若使用，应称“同业务、独立生成运行、未找到逐文件归因调优记录”的留出，不称完全未见项目。

## 其它来源的精确资格缺口

### noarch630

静态页meta：源应为`C:/Users/hongy/.claude/projects/C--Users-hongy-projects-transfer-app-noarch630/03455371-bd9d-4e88-b26d-88f6b18d73b7.jsonl`；源阶段范围`2026-07-18T06:37:30.867Z`至`2026-07-19T09:32:59.949Z`。cache记录稍有首时刻毫秒差且只有派生状态，未把它当新的原始证据。另cache98619884…是同cwd的1流指针，当前也不存在，不据其存在推断完整后修池。

业务身份：noarch与dynamic1本地`AppScope/resources/base/element/string.json`的app_name均为DeepAI全能PPT；noarch/dynamic1的migloop缓存android_root均为`C:/Users/hongy/projects/AIPPT`。这些是身份元数据，不涉及候选原因。

### arch11

完整归档主根`462439ee-b5af-4443-8a58-2e785a2ef826.jsonl`，2310行；cwd=`C:/Users/hongy/projects/transfer-app-arch11`。首时刻L4 `2026-07-16T06:45:36.100Z`；末时刻L2309 `2026-07-20T15:34:16.751Z`。原生Skill：L15 spec、L821 plan、L1125 execute，均有call_id可定位。当前metadata审计未核出独立后修阶段起点，不按文件被改多次就自动认定“生成结束后修复”。

只读全归档原生事件元数据发现最后Write/Edit请求为`2026-07-18T02:13:26.432Z`，子记录最晚`2026-07-18T02:10:26.266Z`；最后用户记录L2297（07-20）之后没有根Write/Edit/Bash/PowerShell请求。该结果仅限制本归档，不排除未提供的后续会话，也不把仍在execute阶段的构建修改硬划后修。没有打开文件级差分或归因答案。

缓存android_root=`C:/Users/hongy/projects/AntennaPod-develop`，静态页project/cwd吻合，足以区分AIPPT业务；但它与此前pod730属同一Android业务谱系，未来须同时报告“新迁移运行”和“该业务此前已有其它运行用于工具调优”。

### 其余默认输入范围

- Calendar主根`6f6a2ca5-c9d7-48d8-ad9d-83a4cf0f647a.jsonl`，1135行，首有效时间`2026-09-02T03:29:23.754Z`至`07:39:51.967Z`；另一根`8698d5c0...`只有7行。当前阶段定位不能支持整个应用生成完成后的返修资格。
- Dynamiccalendar三根`8cc7eb16...`、`c13f382e...`、`efd179bb...`，全池有效时间`2026-09-02T02:30:58.440Z`至`03:04:02.845Z`。仅前置源形状，不从无native app目标推断脚本未写。
- DevEco数据库用SQLite URI `mode=ro`打开，只读session/part的时间、状态、目标路径；Game2048 cwd为`C:/Users/hongy/projects/a2h-bench/harmonyos-arkts-benchmark-main/results/l1_e2e/hmigbot_g2048/work/game2048`。未导出成冻结池，未把当前活动DB当稳定历史快照，未读取模型诊断内容。
- 默认Codex源只读header发现testonboard10/13的本地app_name是Dice Roller，不能将其当第三种业务；AntennaPod-develop的17份短rollout在所支持native调用形状下没有修改请求，未据此反推所有外部历史都不存在。
- 未在此次既有默认输入header/导出登记中定位可直接冻结的Notepad/Notally/Quillpad迁移池。不是宣称用户本地或其它介质永远没有这些资料。

## 下一阶段可以与不可以说什么

当前可单独推进dynamic1跨运行留出资格复核；在冻结任务/观察窗前还应固定全部169文件副本、复核workflow时间边界，以及按同一规则补查脚本目标效应。只有确认另一业务的完整生成后修复池，才组成跨业务真实留出组。

后续独立资格补核：用户另行允许定义pipeline-internal checkpoint后，arch11核出了`post-Stage3 / pre-FV1`关卡及7个既有文件的后窗原生修改。见`arch11-checkpoint-qualification.md/.json`。它不是这里原先寻找的execute-final之后窗口，不据此回改旧实验边界或合并旧分数。

若暂拿不到第二业务的独立后修源，应把三个口径分开：dynamic1真实跨运行验证、现有项目上的结构不变性测试、独立合成反例。后两者不替代真实跨app因果正确性，也不凑“跨app保证”。本预检不提前给调查员任何原因、诊断词、预期答案或gold提示。
