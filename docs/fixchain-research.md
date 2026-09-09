# MigLoop 返修链路调查:我们在做什么、为什么、做到了哪一步

写给第一次接触这个仓的人(包括另一个模型)。读完应该知道:问题是什么、工具长什么样、数据在哪、实验怎么跑的、结论是什么、还差什么。所有数字都来自实际跑出来的记录,文中给出出处。

## 0. 一句话目的

> 目的就是希望通过工具,尽可能少 token、少时间地总结出我们迁移生成后为什么不能一次做对、为什么需要后续修复,把遇到的问题总结。相当于是「生成最终版」vs「修复后最终版」,中间的所有 diff 都要查链路:为什么要这么改,为什么不能一次生成对。最后在每一个 diff 都被追溯原因后,看情况总结根因,沉淀数据飞轮,因为我们有用户数据。

拆开就是三层:

1. **找全**:生成阶段结束之后,对迁移工程的每一处改动都是「生成没做对、事后补的」,一处不漏。
2. **每处归到具体一环**:被改的东西最初是谁在什么依据下写的,那一环缺了什么(spec 写错 / 读了旧版 / 漏读 / 转换错 / 派发词缺约束 / 规则事后才出现 …)。
3. **归并成管线该改什么**:同一上游的改动合成一条根因,落到 spec 模板、派发词、技能规则、门禁的具体位置。这一步的产物就是飞轮要沉淀的知识:下一次同类修复应该消失。

## 1. 背景:我们分析的是什么

### 1.1 a2h 迁移管线

Android→HarmonyOS 自动迁移由多 agent 管线完成。一次迁移(一个 run)的阶段:

| 阶段 | 做什么 | 备注 |
|---|---|---|
| a2h-init | 初始化工程、模板脚手架 | stage-mark 打在开始 |
| a2h-spec | 读 Android 源码,写 spec(页面 spec、feature AC、ui-manifest) | mark 打在结束 |
| a2h-plan | 切片、写 plan | 同上 |
| a2h-execute | converter / worker / closer / builder 子代理生成鸿蒙代码 | 同上;**它的结束时刻是"生成"与"修复"的分界** |
| a2h-verify | 各种 verifier(router / visual / fact-tree / ut / ui …),会派 fixer 回改代码 | 同上 |
| a2h-retrospect | 复盘报告 | 同上 |
| a2h-build | 编译修复循环(可多轮) | 同上 |
| ecat-refine | ECAT 对抗循环:判别器出 work list,修复方子代理改代码,可多轮 | mark 打在开始 |

管线跑在 Claude Code 上。每个会话一份 JSONL 转录;子代理各自一份;一个 run 里除了管线主线,还有 loop engine 续接的 worker、reviewer、ECAT 判别器与修复方,都是独立的 root 会话(DiceRoller 一个 run 有 17 个 root、63 个子代理)。run 级的 `stage-marks.json` 给出各阶段的时刻。

### 1.2 实录长什么样

- `<sid>.jsonl`:主转录。每行一条记录:`type` user/assistant,`message.content` 里是 text / thinking / tool_use / tool_result 块,`timestamp`,`uuid`,`attributionSkill`(管线阶段戳,不一定有)。
- `<sid>/subagents/agent-<id>.jsonl`:子代理转录;`agent-<id>.meta.json` 是描述。主转录里 Task 工具的 tool_result 带 `toolUseResult.agentId`,这是父子边的实锤。
- Write / Edit / MultiEdit 的 input 是写盘证据;Bash 里的 heredoc、脚本、cp、重定向也可能写文件;Read / Grep / Bash 的 tool_result 是「当时读到了什么」的证据。
- `stage-marks.json`:`{"marks": [{"stage": "a2h-execute", "ts": "..."}]}`。

### 1.3 为什么需要工具

一个中等 app 的迁移实录 30MB 起,几百次写、几千次 shell 调用、几十个 agent、跨十几个 root 会话。要回答「这一行为什么被改」,需要:文件的版本脊柱(每一版谁写的)、逐行归属(被替换的行是哪一版谁引入的)、写者当时的输入(派发词、读过哪些文件的哪一版、只读了哪几行)、跨 root 的池子。这些都能从原文推,但每次现推又慢又不一致;工具把它算成一本账,调查者(人或模型)对账本提问。

## 2. 工具:两原子账本 + MCP

### 2.1 两原子

- **版本文件 file(path, v)**:文件第 v 版。给 ≤v 的全部写者(每版是哪个 agent 在它自己的第几版写的、diff、来路:工具写 / shell / 脚本字面量推断 / 外部输入 / 实录外修改)、读了这一版的 agent(下游)、复原全文。
- **版本 agent agent(id, v)**:一个 agent 做出第 v 个对外效应(写 / 删 / 派发子 agent / 发消息)之后的状态。给派发它的人与派发词全文、收件箱、≤v 的全部读取(每条绑定读到的是文件第几版、行段、是否旧版)、产出、收尾输出。v 之后的活动与第 v 版无因果,截掉。

两原子互相以 (path, v) / (agent id, v) 引用。人和模型走的是同一张图。

### 2.2 账本怎么建(收集层要点)

`atoms_collect.collect_cc` 逐条走转录:等 tool_result 再落账(失败调用不记);相对路径按记录 cwd 加命令内 cd 链解析;shell 命令走 `shellparse` 白名单解析,目录 grep 按 stdout 反证成读,heredoc / 脚本字面量推断读写(低置信,标 `script`);Grep 工具命中行成行段读;Read 没有 `toolUseResult` 边车时从 `N\t内容` 行号前缀还原;派发边先用 `toolUseResult.agentId`,再比派发词全文,再退到开头 / id 前缀;SendMessage / teammate-message 进收件箱。解析不出但明显在读写的动作记 `unresolved` 原因,不许静默。每个动作存原始记录指针(转录路径 + tool_use 行 + tool_result 行),`action(id, n)` 随时展开原文,信息不丢。

阶段:记录的 `attributionSkill` 戳落到每笔动作;子代理没戳时继承派发那一笔的阶段;整份没戳的 root 会话(ECAT、reviewer、续接 worker)按 run 级 `stage-marks.json` 的区间按时间落阶段(管线技能的 mark 打在阶段结束,init / ecat-refine 打在开始)。

### 2.3 返修链的定义

- **fix_after** = 最后一段 a2h-execute 的结束时刻。之后任何会话 / 子代理的写都是修复;没有 stage-marks 才退回按阶段名排序。
- **链根** = 修复方写过版本的、工程根目录下的代码与配置文件,三条同时满足:在 cwd 之下;扩展名 .ets/.ts/.js/.json5/.cpp/.h 或 resources/** 下的 .json;不在 spec/docs/.claude/.agents/.ecat/.migbot/build/oh_modules/.hvigor 下。只放开扩展名会多出 98 条 /tmp、scratchpad、spec 产物的假链。
- **三种链根**:rework(生成过又被改,问为什么被改)/ created(修复期新建,问为什么生成期没有它)/ template(模板或外部原样留到修复期才改,问为什么生成期没改它)。测试目录(ohosTest、test、testability、testrunner)的文件不进 created / template。
- **段** = 文件 × 一个修复方的连续版本。修复方按第一笔修复时间取;`fixers_all` 列出各段的文件版本与时刻。段是容器,**问题**才是归因单位:一个段里几件不相干的改动就是几条问题。
- 生成方 = 被修行的原作者(逐行签名,确定性);行级不可得时退回文件的生成侧写者并说明原因。

### 2.4 工具面

MCP 服务 `python -m migloop.mcp_server`(stdio,需要 `mcp` 包;`claude mcp add migloop -- python -m migloop.mcp_server`)。八个只读工具,全部带 `sid`(会话 id 或 8 位前缀;池子 = 同工程的兄弟 root 会话,上限 64):

| 工具 | 参数 | 给什么 |
|---|---|---|
| guide | — | 两原子定义、标签含义、各工具说明、建议路径 |
| sessions | file? | 全部返修链:被修文件、生成方、各修复方分段(文件版本 + 时刻)、被修行 ★ 原作者、修因;带 file 只回那条链 |
| index | kind?, query? | 账本目录:全部 agent 与文件各一行 |
| file | path, v?, content?, diff?, start?, n? | 写者脊柱、读者、复原全文、逐版 diff |
| agent | id, v?, since? | 派发词全文、收件箱、逐版读写、收尾输出;主会话用 since 取窗口 |
| blame | path, v?, start?, n?, changed? | 逐行是谁在哪一版写的;changed=True 只列这一版替换掉的行 |
| diff | path, v | 某一版的 unified diff |
| action | id, seq | 某次工具调用的完整原始输入输出 |

同一份输出的 HTTP 化身:`migloop <sid> --serve` 起本机服务,`GET /api/insight1/atom/<sid>/text/<tool>`(参数同名);返修链页 `/api/insight1/fixchain/<sid>`,报告页带审计卡。

### 2.5 代码地图(src/migloop)

| 模块 | 职责 |
|---|---|
| adapters/claude.py, codex.py, deveco.py | 转录格式适配:提取层(报告页用)、阶段戳、会话发现 |
| shellparse.py | shell 命令白名单解析 |
| filestory.py | 文件原子内核(6 种事件 → 版本脊柱)、逐行签名、**build_fix_chains**(链定义全在这里)、is_project_code |
| atoms.py | Ledger(stories + agents)、agent 版本编号、派发边、阶段下沉、file_atom / agent_atom / blame / build_evidence |
| atoms_collect.py | CC / codex 收集器、stage_intervals_from_marks、fix_boundary、脚本字面量推断 |
| atoms_text.py | 给模型看的紧凑文本渲染(每个工具一个 render_*) |
| audit.py | 报告页「风险点」规则(含返修追溯卡、execute-no-build 等) |
| mcp_server.py | FastMCP 八工具 + GUIDE |
| service.py / serve.py / cli.py | 本地服务层、HTTP、命令行(独立工具自己的) |
| render/templates/fixchain.html | 链页:探索树 + 抽屉 |
| docs/skills/migloop-investigate/SKILL.md | 给调查 agent 的 run 级技能(目前实验中未启用,见 §5) |

## 3. 数据:实验用的会话在哪

会话本体不进仓(30MB 起,含用户工程路径)。以下是本机位置;`~` = `C:\Users\hongy`。

### 3.1 DiceRoller(2026-09-03 的 run,主战场)

- 导出包:`~\Downloads\a2h-export-DiceRoller-b24983af1b9ddf5d.tar.gz`(a2h-export v4,msid 4671dcdd,run c6941f0d,80 个会话切片)。布局 `runs/<run>/epoch-0/sessions/{main-<sid>,agent-<aid>}.jsonl` + `manifest.json`(sessions[] 带 kind / agent_type / stage_intervals);agent 文件首条记录带父 `sessionId`。
- 工具吃的 Claude Code 布局(由 scratchpad 的 `analyze_export.py --intervals` 落成):`~\.claude\projects\-export-DiceRoller-0903\`,17 个 `<sid>.jsonl` + `<sid>\subagents\` + `stage-marks.json`。**查询用 sid `49d451b1`**(时间上最后一个 root,池子 = 其余 16 个前序)。
- 原始组用的同一份拷贝:`<scratchpad>\export-dice\raw_arm\`(会话级临时目录,可能已被清理;与上面那份内容相同)。
- 17 个 root 的角色:管线主线 81e0a463(有戳)、首启 aab6a114、loop engine 续接 worker ×3(a2h-build 戳)、reviewer ×5(只 Glob)、ECAT 判别器 ×4、ECAT 修复方 ×3(2f01bcdc 是 iteration 0 的主会话,派 fix-index / fix-uitest / fix-uttest / fix-identity / fix-errobserver / gate-build)。
- 关键时刻:T0 = 14:26:14(池子最早动作);execute 结束 = **16:46:29**;visual-verify 16:47→20:19;build ×4;ECAT 21:07 起三轮。
- 账本结果(工具现状):4 条链、8 个修复段、28 个修复版本(AppScope/app.json5 v4;entry/oh-package.json5 v2;EntryAbility.ets v4–9;pages/Index.ets v4–23)。逐版清单见 `docs/experiments/2026-09-04-diceroller-run-level/version_ledger.txt`。

### 3.2 0723(aippt 迁移,真实用户会话,压力测试用)

- `~\.claude\projects\-Users-chenjiamin-arkTs-arkts-pilot-project-aippt-version-aippt-0723\`:修复轮 `ff019d8a-5172-4cdd-8ce3-77a21682c1b6.jsonl`,生成轮 `9b3105a2-85ec-4889-9786-b3c220f06754.jsonl`。查询用 sid `ff019d8a`(池子含 9b3105a2)。没有 stage-marks,修复方按阶段名判。
- 账本结果:19 条链(15 rework + 2 created:WXEntryAbility / WXPayEntryAbility + 2:module.json5 rework、color.json template)。这个 run 比 DiceRoller 大得多(几百次写、6553 次 shell 调用),是「找全」真正的考验,run 级双盲还没在它上面跑。

### 3.3 线上

migbot-server(`https://123.60.33.134:8444`)展示的是上传的会话切片,用的是 `src/vendor/migloop` 那份旧代码,链数与名字和本仓当前口径不同;server 现阶段只做 UI 展示,不接 AI 分析。

## 4. 实验:怎么做的、结果是什么

所有实验用 `claude -p`(Opus 5)无头跑一个调查 agent,harness 记录 usage / 工具调用序列 / 费用 / 时间,结论由另一个 Opus 盲评(A/B 随机,不知来源)。harness 与产物在 `docs/experiments/`。

### 4.0 2026-09-02,0723 的 AboutUsPage 一条链,第一次工具 vs 原始(工具优势最大的一次)

第一次对照:本会话里的 opus 子 agent,用 7 个 HTTP 文本端点当工具(curl,等价于 MCP;复跑加了 action),先读技能文件(七步路径 + 固定结论格式 + 六类定性,明写「只能通过工具看实录」,**没有原始转录**),prompt 给全坐标(sid、文件名、示例调用连 v=11 都带了)。对照组同一模型只给原始 JSONL 目录、生成轮 / 修复轮是哪两个会话、子代理布局与 tool_use 结构说明,禁止碰端点与 migbot 代码,同样只查这一个文件。所以这次赢的是「紧凑文本 + 有人指路 + 只查一条链」三件事叠加,不是单纯「有工具」。定性都是「漏读」(conv-aboutus 读全安卓侧但没读鸿蒙 AppScope/app.json5,把 `appInfo.label` 当应用名)。

| | 纯工具 | 原始转录 |
|---|---|---|
| 首跑 | 26 次调用 / 97.5K token / 6.2 分 | 57 次调用(它自报 25)/ 178.8K / 11.4 分 |
| 修掉「shell 读的 stdout 不入账」后复跑 | 29 次 / 117K / 5.2 分 | 同上 |

省 45% token、46% 时间。首跑证据面少于原始组(账本丢了 grep 命中行和 cat 输出),由此定下「每个动作存原始记录指针,action(id, n) 随时展开原文,信息不丢」;复跑后证据面反超原始组(多出 spec 反写污染、SDK 只读 570–625 行段两条),7 条证据逐条按原文复核属实。这次没有 harness,数字来自当时的记录(记忆文件),产物未入仓。

### 4.1 2026-09-03,0723,按链调查,工具省 token

一条链一次调查,提示词给链坐标(文件 / 修复方 / 生成方)+ 四步路径。5 条链:

| 变体 | 费用 | 结论 |
|---|---|---|
| baseline | $6.87 | 每条 12–21 次调用,成本主体是每轮重读上下文 |
| A:sessions(file=) 只回目标链 + blame(changed=True) 只列被替换行 | $4.96(−28%) | 五条定性一致,**采纳** |
| B:agent 默认折叠非目标版本窗口 | 没省 | 把 AboutUsPage 从「spec 写错」误判成「漏读」,**撤回** |

顺带揪出收集器 bug:34 条链里 19 条是假的(一张 24 条 .ets 路径的数据表被当成写目标)。

### 4.2 2026-09-04,DiceRoller,按链双盲(4 条链)

三组:纯工具 / 原始转录(Read/Grep/Bash 自己找)/ 超集(工具 + 原始)。**设计缺陷:三组都拿到了我们工具算出来的链坐标**,「找全」这一步被替代了。结果:定性 4/4 一致;评委 4/4 更信原始组(引用 uuid / 行号 / 绝对时刻,不依赖工具就能回查);超集 vs 纯工具 4/4 超集胜,超集 vs 原始 3/4 原始胜。费用 纯工具 $3.49 / 615s,超集 $4.38 / 921s,原始 $4.52 / 1079s。

### 4.3 2026-09-04~05,DiceRoller,run 级双盲(极简 prompt)

用户否决了给范围定义、给流程、给技能作为 hint 的做法:两组同一段任务(见 `prompts/prompt_run_common.md`,全文不到 400 字:execute 在 16:46:29 结束,之后对迁移工程的改动都算修复,查清每一处为什么要修、生成期为什么没做对,再总结),工具组多八行工具介绍,原始组只有转录布局说明。各跑一次。

| | 工具组(MCP + 原始) | 原始组(只有 Read/Grep/Bash) |
|---|---|---|
| 费用 / 时间 | $5.89 / 12.7 分 | $5.59 / 15.3 分 |
| 轮次 / 工具返回字符 | 74 / 188K | 44 / 257K |
| 输出 token | 37K | 47K |
| 8 个修复段覆盖(机械对账) | 8/8 | 8/8 |
| 28 个修复版本(人工逐版对账) | 27/28,漏 Index v14 | 清单里 28/28,报告按事情归 10 组 |
| 盲评 具体度 / 一致性 / 根因 | 5 / 4 / 4 | 5 / 5 / 5 |
| 只有己方有的发现 | 5 项 | 15 项 |
| 评委更信 | | 原始组 |

两份报告与评委 JSON 在 `docs/experiments/2026-09-04-diceroller-run-level/`。评委列的 6 条冲突里三条能凭原文裁定:

- **Roll 按钮大写**:原始组对。转换器 15:50 的 thinking 明写「textAllCaps → ROLL,但 AC14 要显示 Roll,所以不大写」(`agent-a349784d2663f1f0a.jsonl:61`)。根子是 spec 把 uiautomator 抓到的逻辑文本当显示文本写进了 AC。工具组归成「转换错」,因为**账本只收工具调用,不收 agent 的 thinking / 正文**。
- **ohosTest 那些文件 verify 前就存在**:原始组对(Write 返回 updated 不是 created)。工具组把「外部输入 v1 于 T+4:18」读成了创建时刻,那其实是首次被读的时刻,是工具措辞的问题。
- **registry_total=0 的机制**:工具组对(注册表解析正则丢多段 P-ID),原始组的「统计头陈旧」不完整。

原始组的做法值得记:它前 8 次调用自己造了一个简版的我们的工具(索引 execute 后全部 tool_use → 扫 Edit/Write 并排掉 spec/docs/.claude/.ecat → 扫 Bash 里的 cp/mv/重定向 → 按行号倒转录含 thinking),然后逐个写者读原文,43 次调用。它没有逐行归属、没有版本脊柱、每次现扫 30MB;在 4 个文件的规模上不吃亏。

### 4.4 每次实验修掉的工具 bug(都有测试)

| 症状 | 根因 | 修法 |
|---|---|---|
| 0723 19 条假链 | `open(p,'w')` 判据只看引号后一个字母,`'wired'` 被当写模式;脚本全文倾向兜底 | 模式串必须完整短 token;倾向兜底只对 ≤3 个字面量的小脚本生效,其余记「方向不明」 |
| Index.ets 多出一版假修复 | heredoc 里 `"MainActivity": ".../Index.ets"` 是映射值 | 紧跟冒号的字面量不算写目标 |
| Read 丢读 | 服务端切片没有 toolUseResult 边车 | 从 `N\t内容` 行号前缀还原 |
| ECAT 六个子代理名字配串 | 派发边按派发词前 120 字对齐,并行派发的开头一样 | 用 Task 结果边车 `toolUseResult.agentId` |
| EntryAbility 修复方报成 ECAT、时刻晚两小时 | 修复方按 id 字母序取 | 按第一笔修复时间取 |
| 子代理显示裸 id | 血缘层名片 desc 为空,整卡覆盖账本名片 | 按字段补空 |
| visual-verify 全算生成侧 | stage-mark 被当起点 | 管线技能的 mark 是阶段结束 |
| app.json5 / module.json5 / color.json 不入链 | 链只认 .ets | 工程根目录下代码与配置 + 噪音目录排除 + template 链根 |

### 4.5 三次对照的配置一路在变,数字不能横比

| 日期 | 单位 | 工具组配置 | 给不给链坐标 | 给不给流程 | 结果 |
|---|---|---|---|---|---|
| 09-02 | 1 条链 | 纯工具(无原文) | 给 | 四步技能 | 工具省 45% token、46% 时间,证据面复跑后反超 |
| 09-03 | 5 条链 | 纯工具 | 给 | 四步技能 | 变体 A 再省 28%;没有原始组 |
| 09-04 | 4 条链 | 纯工具 / 超集 / 原始 | 三组都给 | 四步技能 | 纯工具 −23% 费用 −43% 时间但盲评输;超集 ≈ 原始价钱、更快 |
| 09-04~05 | 整个 run | 超集 / 原始 | 都不给 | 都不给 | 费用持平、工具组快 17%、盲评输 |
| 09-06 | 19 根(0723) | 纯工具 / 原始 | 原始组被给了修复方+转录+时间(作废) | 都不给 | 打平:$26.76 vs $26.33 |
| 09-06 | 19 根(0723) | 纯工具 / 原始 | 都只给文件名 | 都不给 | 工具 −7% 费用 −20% 时间 −19% 调用;盲评 16/19 一致、更信原始 17/19 |
| 09-07 | 4 根(0723) | 新工具 / 旧工具 / 原始 | 都只给文件名 | 都不给 | 新工具 −23% 费用 −15% 时间(vs 旧工具);盲评 4/4 一致、更信 {'原始': 4} |

省钱的来源本来是两条:工具输出比原文紧凑,以及有人告诉它走哪几步、只查目标链。后两次按用户要求把第二条拿掉(不预设问题、不给流程),第一条的优势就被轮数吃掉了(§5 第 4 点)。

### 4.6 2026-09-06,AboutUsPage 三组重跑(legacy 工具 / 现在的工具 / 原始转录,各 2 次)

回答「工具到底省不省」:同一条链、同一个 harness(`claude -p`,Opus 5),legacy 与现在的工具用同一套按链 prompt(七步路径、给链坐标、只准用工具、25 次上限),原始组用 09-02 对照组原话改的模板。产物在 `docs/experiments/2026-09-06-aboutuspage-three-arms/`。

| | legacy 工具(22d88c0e) | 现在的工具(dev/fixchain) | 原始转录 |
|---|---|---|---|
| 费用 | $1.64 / $1.45 | $0.92 / $0.90 | $2.52 / $2.35 |
| 时间 | 254s / 194s | 149s / 121s | 403s / 418s |
| 调用 | 17 / 16 | 13 / 15 | 29 / 32 |
| 工具返回字符 | 119K / 114K | 62K / 61K | 142K / 87K |
| 输出 token | 13.3K / 11.2K | 7.7K / 7.0K | 24.6K / 24.3K |
| 定性 | spec 写错+漏读 ×2 | 转换错 / spec 写错+漏读 | 漏读 ×2 |

- 现在的工具比原始转录省 63% 费用、67% 时间;legacy 省 37% / 45%。09-02 的「省一半」复现,现在的版本比 legacy 再省四成,省在 sessions(file=)、blame(changed=)、agent 看见的行只留行号三处。同一会话同一组调用的文本体量对比见 `harness/measure_tool_text.py` 的输出:file/diff/blame/agent 单次体量两版相同,新参数都往小走。
- 六份报告事实层一致(conv-aboutus 首写 `appInfo.label`,spec 第 51 行是它回填的,slice6-risk 照抄,两人都没读 AppScope/app.json5,修复方读了);标签三种叫法。盲评三对都更信原始组(具体度 5:5,一致性 3–4:5)。
- 原始组多找到四条事实,工具组六次都没有:同轮 abase3-network 读了 app.json5 就写对了同一映射;主会话 Stage 0 在 01:54 就看到过 `$string:app_name`;closer 复核时 Read 带 `limit:150` 没覆盖到出错行;真机 UI 树原文。前两条是「谁在什么时候看到过这个事实」的全池检索,工具没有这种查询。
- **暴露并修掉的账本 bug**:现在的工具 rep1 判「转换错」,依据是 file 工具的读者列表说 slice6-risk「全文」读过三次 AppFormInfoManager.ets;原文里它只 grep 过一次方法名。读者列表把 start/n 为空的读一律标「全文」,grep 命中对账出来的读也被冒充成全文。修法:读的范围四种说法 —— 全文快照 / 行段 / 命中 N 行 / 范围未知,不是全文的不许冒充全文(`atoms_text._read_span`,`ReadRec.full`)。这是「工具措辞误导模型」的第二例(第一例是「外部输入 T+4:18」被当创建时刻)。

### 4.7 2026-09-06,账本里三种事实分开摆:确定的写 / 观测到的变 / 碰过

AboutUsPage 三组重跑之后的复盘:这个缺陷的修复动了两个文件,真正改错值的 F012ViewModel.ets 是修复方用 python heredoc 读改写的,收集器看到既读又写就放弃,账本没立版本、不成链;⚠ 只挂在修复方的时间线上,`file(F012ViewModel)` 显示只有一版,`sessions` 里没有它。展开的口子(action)一直在,缺的是文件侧和链侧的入口。

用户定的逻辑:脚本里出现的路径**不猜方向**,记成「碰过」,不立版本;file 原子末尾列出「碰过它、方向不明的调用」带动作号;sessions 末尾按文件归组列出「修复期被脚本碰过、方向不明的工程文件」加 agent id 对照表;版本脊柱每一版带写它那次调用的动作号。全部是已有 ⚠ 的换位重挂,不新增任何推断。结果:0723 sessions 多出 54 个文件 83 次触碰(其中 vv-static-B 一张数据表就碰了 24 个 .ets,以前是 19 条假链,现在是 24 行「方向不明」);DiceRoller 2 个文件 2 次。`Touch` / `FileStory.touches` / `Version.act_seq` / `fix_period_touches`。

### 4.8 2026-09-06,0723 全部 19 根,纯工具 vs 原始转录,两组都只给文件名

单位是「一个修复 agent 对一个文件的那次修改」(用户裁定);0723 的 19 个被修文件各只有一个修复方,所以是 19 根。两组各派 19 个独立的 `claude -p`(Opus 5),一根一个进程,互不共享上下文,合计 38 个。两组的任务段与输出格式逐字相同,都只给文件名和「修复轮 = ff019d8a 会话」这句数据描述,不给修复方、版本号、时间、生成方、链根种类、流程;工具组的说明只有「8 个查询命令、先调 guide」,原始组只有转录目录的结构。模板在 `docs/experiments/2026-09-06-0723-19roots/prompts/`(`*_tools0.md` / `*_raw0.md`),落盘的 38 份提示词经泄露检查命中 0。

**第一轮作废**。第一次跑(同目录 `hinted-invalid/`)我把修复方 id、它的转录文件名和精确到毫秒的修改时间写进了原始组的提示词 —— 这三样全是账本算出来的,违反 09-04 的裁定(原始组不给链坐标)。结果两组打平($26.76 vs $26.33),而且原始组每轮上下文从 09-06 的 58K 掉到 38K:**给时间戳等于给了 since 窗口**。用户看出来后重跑。

**正式结果(无提示,各一次)**:

| 19 根合计 | 纯工具 | 原始转录 | 差 |
|---|---|---|---|
| 费用 | $26.64 | $28.57 | −7% |
| 总耗时 | 75.0 分 | 93.9 分 | −20% |
| 调用次数 | 375 | 462 | −19% |
| 输出 token | 246K | 306K | −20% |
| 每轮平均上下文 | 34K token | 40K token | −15% |
| 工具返回 | 152 万字 | 134 万字 | +14% |
| 出错 | 0 | 0 | |

逐根费用两边都在 $1 到 $2.2 之间浮动,工具便宜的 11 根、原始便宜的 8 根;单根只跑一次,噪声与差值同量级。

**费用去了哪(逐调用解剖,`harness/seg_anatomy.py`)**:费用 ≈ 轮数 × 每轮上下文。工具组 74 次 agent 调用里 38 次不带 since,整段返回 51 万字,占全部返回的三分之一(单次最大 4.1 万字);原始组对应的是自己写 `python -c` 查时间线,单次最大 1.9 万字。原始组「找人」阶段(打开修复方转录之前)平均 5 次调用、1.2 万字,占它返回的 15%;工具组对应的固定开销是 ToolSearch + guide + sessions 三次约 1 万字,所以定位这一项工具只净省 2 次调用 —— 在 146 份转录里 grep 一个文件名本来就快。

**09-06 的「省 60%」是什么**:同一根 AboutUsPage 四次对照 —— 09-06 工具组(七步路径)15 轮 × 23K = $0.91;09-06 原始组 31 轮 × 58K = $2.44;这次工具组(只给文件名)22 轮 × 37K = $1.50;这次原始组(只给文件名)26 轮 × 35K = $1.46。路径值 7 轮和 14K 上下文,是工具组涨价的全部原因;原始组同一份提示词两次跑出 58K 与 35K 的每轮上下文(09-06 它写脚本整段倾倒时间线,单次 17K 三次),单根一次的方差就这么大。所以 60% 里一半是路径与窗口纪律(提示词侧),一半是抽样。

**修掉的工具退化**:加「碰过」附录(§4.7)时,sessions 带 file 也把全工程 54 个文件 83 次碰过全列出来,每根固定 6466 字,从每根第二次调用起一直留在上下文里。修法是附录按文件过滤(`atoms_text._same_file`,只被碰过、没有链的文件带 file 问也能看到自己的记录);0723 上 sessions(file=AboutUsPage.ets) 从 7255 字回到 971 字。它占返回的 7%,修掉后总费用只动了 0.4% —— 大头不在这。

**盲评(Opus,A/B 随机,`judge/hint-free_tools_vs_raw.json`)**:定性一致 16/19;具体度 原始 95 vs 工具 79(原始 19 根全 5 分);一致性 82 vs 79;「更可信」原始 17、工具 2。评委给出的理由几乎每根一样:原始组的坐标是 jsonl 行号 + UTC 时间戳 + uuid,「可直接回查」;工具组的坐标是 path@v / agent vK / #n,「内部版本号、记录号,二级索引」;其次是工具组在 blame 断点处(edit-miss / 实录外修改后「归属未知」)如实写「无法确认」,原始组直接读 Write 原文把它补上了。三根定性不一致的都是「同一失效链的不同一环」:MineComponent 工具停在 P-15 指南缺条款,原始追到 icon_autofix 从没被调用(run_loop.sh 在 macOS 崩、主会话降级只跑 2/5 项、自认「执行疏漏」);DesignTokens 工具说 dimAmount 在弹窗转换环丢掉,原始举证它已被采成契约、断在宿主接线层;MemberCenterPage 工具说漏读 spec,原始说读到了 Kotlin 真值但只搬了 if 分支。多追的那一跳,证据多在 agent 自己的正文里(§5 第 1 点)。

**归因聚类两边一致**:D-010 androidId 三根(DevicePrefs / PreferenceKeys / F003Repository)两组都归到 Base-3 占位策略与主会话派发词的「不许臆造」;微信三根(WXEntry / WXPay / module.json5)都归到 P-S2-012 把宿主 Ability 注册和 SDK 依赖捆成一个占位;HomePage 与 color.json 都归到「按资源名而非布局引用定深色」;HomeTab / Mine / MinePage / TemplatePreview 都落在 Image 尺寸与 ArkUI 布局语义。按根推断再归并这条路两组都走得通。

### 4.9 2026-09-07,五步优化落地后四根验收(新工具 / 旧工具 / 原始转录,同四根)

按用户批准的计划(§7 第 8–10 项及其前置)在 dev/fixchain 上按 TDD 逐步提交:fd79532 基线 → a1fe697 读写记录修对 →
7e54d3c 记录补全 → a3fa86d agent 视图索引化 → e528336 带起点的 search。测试 207 → 235。每步在 0723 上的实测:

- **读写记录修对**:假 v1(存在性守卫里 `wc -l < X` 被当读)20 个页面文件 → 1;幽灵路径(短文件名按 cwd 拼出的假文件、
  cd+cat 快照挂错目录、ls 裸名字被当读)327 → 5;外部输入版本 2496 → 1404,版本总数 4598 → 3529;工程内 368 个外部输入文件
  全部有了来源指针(mkdir / --out / 脚本正文里的目录字面量 → 「可能由此次运行生成」,首见前最近 3 次运行)。
  连带修法:Write 结果为 created 时假前身作废;touch / --out 是写;heredoc 落盘的脚本进脚本表;正则字面量不当路径。
- **记录补全**:assistant 正文(主会话 670 段 12 万字)、thinking、主会话 149 条汇报收件(带前缀「Another Claude session
  sent a message:」曾一条没记)、操作者指令、技能注入(12 份 15 万字,挂 SKILL.md 读者)全部入账、同一套编号、action 能展开。
  三份转录对账:工具调用 / 正文 / user 消息的「账本无编号」全为 0(只剩本地命令回显 8 条,故意不记)。
- **agent 视图索引化**:slice6 v14 33315 字 → 18441,conv-aboutus v4 18832 → 10515;读按调用合行、工程外路径缩短、
  看见的行默认只留行号、收件一行一条、(#n@L行) 带转录行号、agent/action 认名字。8 千的目标没到,剩下的是每条读的标签和行号本身。
- **search**:只在 agent 到第 v 版为止的记录或文件到第 v 版为止的内容里找,命中分组带下一跳,锚点之后只计数,无起点不搜。
  0723 验收命中原始组多追的那几跳:conv-home ≤v1 查 @color/white 命中它读的 activity_home.xml:21 和两段自述;主会话在生成→修复
  区间查「执行疏漏」命中 #2515@L5412;file AboutUsPage 查 appInfo.label 首次出现 v1 ← conv-aboutus。

**四根验收**(MineComponent / DesignTokens / AboutUsPage / HomePage,工具组只给文件名,模板只多了 search 一个名字;
原始组复用 §4.8 的报告,同一份提示词):

| 同四根合计 | 新工具 | 旧工具(§4.8) | 原始转录(§4.8) |
|---|---|---|---|
| 费用 | $4.32 | $5.59 | $5.60 |
| 时间 | 12.2 分 | 14.4 分 | 21.3 分 |
| 调用 | 82 | 85 | 95 |
| 工具返回 | 227K 字 | 316K 字 | 264K 字 |
| agent 调用(整段 / 带 since) | 5 / 3,8 次 / 81K 字 | 13 / 4,17 次 / 205K 字 | |
| search | 21 次 / 41K 字 | 无 | |

新工具比旧工具省 23% 费用、15% 时间;比原始转录省
23% 费用、42% 时间。agent 整段调用从 13 次降到 5 次,
模型改用 search(平均 2K 字一次)定位再展开。

**盲评(Opus,A/B 随机,`judge/tools-after_vs_raw.json`)**:定性一致 4/4;具体度 工具 16 vs 原始 20;
一致性 工具 15 vs 原始 18;「更可信」{'原始': 4}(§4.8 同四根是原始 4:0)。

四根的「生成时为什么没做好」:
- MineComponent:spec 写错/不全——pitfalls P-15(@v1 第169-173行)只写了「ArkUI 默认 ObjectFit.Cover → 补 Contain」,完全没说 ArkUI 的 Image 不写 width/height 时不取固有尺寸而是撑满父容器,转换器照规则执行仍会漏尺寸;错误假设又经 MinePage.ets 在页间复制传播。
- DesignTokens:漏读 —— 安卓侧真值 BaseDialogFragment.kt@v2:47 `dimAmount = 0.55f` 全实录只有 conv-worksmore v1 读到(#12371, T+18:55),它按"页转换器不碰宿主"把窗口形态(含 maskColor rgba(0,0,0,0.55))只写成给调用方的约定注释,没人接;Base-6 建 token 表时既没读这个基类、其所读的技能文
- AboutUsPage:spec 写错——conv-aboutus 只读了 `resource-mapping.md@v1:615`（「appName 应写入 AppScope/app.json5 的 label 字段」）就把「运行期经 bundleManager 读 appInfo.label 取真值」当结论固化进 baseline spec 并标「已实装」，全程没读过 `AppScope/app.json5` 本体，
- HomePage:转换错——conv-home 把「资源字典里存在一个叫 tab_bg 的深色 token」当成了「底栏用这个 token」的判据，压过了它已经读到的布局真值属性；错误口径在上游派发词里已被预置（主会话 v15 #249 只读了 colors.xml 的色值定义，没核布局引用）。

AboutUsPage 这次追到了 resource-mapping.md@v1:615「appName 应写入 AppScope/app.json5 的 label」这一环(§4.8 里只有原始组到了);
MineComponent 用 search 查出「固有尺寸交 icon-sizing 自愈」的约定是从 MinePage.ets@v1(conv-mine)复制来的,但没去主会话的
时间区间里查「执行疏漏」—— search 的区间用法模型没自己想到,这是下一轮看的点。产物在 `docs/experiments/2026-09-07-four-roots-after-optim/`。

**第二次四根(收尾改索引行、file 读者默认关之后,`rerun-2/`)**:$4.51 · 12.8 分 · 97 轮 · 93 次调用 ·
每轮重读 26K token · 输出 41K · 返回 215K 字。和第一次($4.32 / 12.2 分 / 86 轮)比多花 4%,
不是工具变大(agent 均次从 1.0 万字降到 7.9K),是模型多问了 11 轮、search 从 21 次到 29 次 —— 单根一次的抽样噪声就是这个量级,
两次新工具合起来看:比旧工具省两成费用,比原始组省两成费用、四成时间。11 次 agent 全带版本、4 次带窗口;HomePage 那根模型自己
用窗口在主会话里查了「深色」和 color_home_tab_bg。盲评 4/4 一致,更信原始 {'原始': 4},具体度 16 vs 20,
一致性 17 vs 18;理由仍是坐标可回查,以及 MineComponent 把一次范围有限的 search 零命中说成「icon-sizing 自愈是杜撰」——
接收方(icon_autofix.py)存在且从没被调用,证据在主会话生成→修复区间的话里,模型没去那里查。对策:sessions 带文件时把派发者
和生成→修复的区间连同 search 的写法摆到链那一行上(已做)。search 同时修了两处:写入 / 派发命中显示命中的那一行而不是 JSON
开头;文件里命中行未变的版本折成一行,HomePage.ets 那次 9148 字变 2146 字。

### 4.10 2026-09-07 晚,不再盲跑:亲手用工具追链,撞出什么修什么

用户裁定盲跑暴露不了问题(两组「定性一致」是评委口径宽松:只比结论一句话,不比链);要我自己或子代理亲手用工具追,
每条链写成「环 1 → 环 k」的形式,每环写「谁、凭什么、判定(传递 / 错 / 缺)」,追到池外输入、批量生成的脚本或技能定义为止,
指出故障从哪一环进来。否决了「工具一次把整棵树铺出来」(锥太宽会把整个仓拉进来),链骨架仍由模型逐跳走,工具只保证每跳
有坐标、有下一跳。

**AboutUsPage 亲手追(六环全通)**:fixer-r1 v12(#25209@L240)← 缺陷单 AboutUsActivity_01 由 vv-t2-A01 依 真机 dump + 截图
写成 ← slice6 抄了 baseline spec v2:51「已实装」← conv-aboutus 把 resource-mapping.md@v1:615「appName 应写入 app.json5 的 label」
当成事实,全程没读 app.json5 本体 ← stage0-resources 在 613 行写「交给 arkts-app-identity,仅记录」,app.json5 的 label 从没被写
(实录外 v2 才出现 `$string:app_name`)← 技能定义在系统提示里,账本里没有记录。故障进入点是 stage0 那一环:计划记下了,没人执行,
也没有完成检查;后面每一环都是「传递」。修复侧比生成侧多的只有一样:有人把应用跑起来看了这一页。

**MineComponent 亲手追(10 次调用 ≈ 2 万字)**:conv-minefrag v1 的「固有尺寸交 icon-sizing 自愈」在任何转录记录里都没有来源 ——
它来自子代理类型定义(系统提示),账本的数据边界;blame 在 edit-miss 断点后给「未知」,而断点前后同文的行本可以沿用原作者。

亲手追撞出来、当场修掉的账本问题(都有测试):

| 撞上 | 修法 | commit |
|---|---|---|
| 依据窗口只看喂养那一版,fixer 早一版读的单被漏掉 | 往前看三版 | 7715556 |
| since 窗口里派发指令整段重印 | 窗口视图不重印派发,给定义提示 | 7715556 |
| page_0031 首版记「外部输入」,其实是主会话 #347 跑 gen_page_specs.py 一批 58 份生成的 | 脚本产物首版记「批量生成」,写者 = 跑脚本的 agent(最长前缀匹配、同批计数);工程根这种覆盖过半文件的目录不当输出目录 | 50bad3f |
| resource-mapping.md 是 `cat a b c > f` 拼的,内容记「未知」,615 行查不到写者 | cat 拼接记派生写入,各段已知就拼出来 | 50bad3f |
| 脚本正文里的目录字面量(ROOT="spec/pages")没当输出目录 | 目录字面量算目录提示,基变量排除 | 50bad3f |
| edit-miss / 实录外修改之后行级归属全「未知」 | 断点后重锚版与断点前最后已知版逐行同文的行沿用原作者,标「跨断点同文推定」 | 010b167 |
| 链行只说修复方读了哪张单,不说单从哪来 | sessions 加「修复侧多看到的」:单的写者(写 / 脚本碰过)+ 写单前看的证据类型(真机 dump / 截图 / 安卓基线 / 编译输出 / 接口探测 / spec);技能注入与 SKILL.md 不算依据 | 60a26e1 |

「修复侧多看到的」在三根上的样子:AboutUsPage 的单 ← vv-t2-A01 写(#24499),此前看了 截图 18、真机 dump、安卓基线 26;
MineComponent 的三张 ALIGN 单 ← 主会话脚本碰过(#24196),一张 ← vv-t1-A02 写,此前看了 真机 dump 3、截图 5;
DiceRoller app.json5 的依据是 decision-ledger.md ← 主会话·1d2ef418 写(#42)。这一行就是飞轮要的分类:生成期缺的是哪一类反馈。

用户对 app.json5 这类根的裁定:修复侧比生成侧多的是运行期观测(真机 dump / 截图),生成侧本来就没有,所以结论不是「谁写错」,
是流程缺口 —— 计划记下没执行、没有完成检查、生成期没有运行反馈;这种「spec 全是脚本批量生成、从没被归因到」的怪事本身就是发现。

### 4.11 2026-09-07 深夜,四根子代理亲手追链(只许用工具),摩擦清单直接变工具改动

规程(`docs/experiments/2026-09-07-handson/HANDSON_PROTOCOL.md`):一个子代理一根,只能经 call.py 调工具,不许读转录、不许看仓;
交付链报告(每环谁 / 凭什么 / 判定)+ 工具体验日志(逐次调用字数与评价、卡点、多余、缺的、该改的三条)。四份报告原文在同目录。

| 根 | 调用 / 返回 | 故障进入点 | 修复侧多看到的 |
|---|---|---|---|
| DiceRoller Index.ets(ROLL 大写 + 按钮圆角) | 26 次 / 5.1 万字 | 主会话·81e0a463 v7 写 F001-AC14(#1933@L279):把源串「Roll」当渲染形态定成判据;生成方 think 里已想到 textAllCaps→ROLL,被 AC14 按回去(错);圆角一半两侧 spec 都没有 Material 默认形态(缺) | 双端 sbs 拼图、struct oracle、build.gradle(Material 1.4.0)、button.d.ts(ButtonType.Normal 无圆角);生成方零次探测 d.ts、没读 build 文件 |
| DiceRoller app.json5(bundleName / vendor / icon) | 20 次 / 4.5 万字 | 两条链:bundleName/vendor 进入点在技能定义 arkts-app-identity/SKILL.md「scope=dev-identity 跳过 bundleName/vendor(D-009)」—— 理由在本工程不成立(无签名 / 无 AGC),D-009 在 ledger 六版已知内容里查无此条;icon 进入点在 app-identity 自己:亲眼见 AppScope media 残缺,却把 D-003「不迁安卓图标」读成「脚手架图标不动」,entry 与 AppScope 作用域混了 | ECAT 静态检查器的 work list(T+6:44 才有)、agent_bundle.v1.json(T+2:34 才进池)、对 D-009 前提的反查(ledger C13);顺带发现修复侧 vendor 改成 diceroller 违反技能映射规则(第二段就是 example) |
| 0723 PreferenceKeys.ets(KEY_ANDROID_ID) | 20 次 / 5.0 万字 | 主会话·9b3105a2 v65 写 decision-ledger D-010(#838@L1471):同段「事实」已写「传非空 16 位 hex 则成功」(T+1:06 真实后端打靶 #541),候选方案却全是后端侧,整项 pending-approval;其后五环全部忠实传递(派发词甚至明令「不要臆造 UUID」) | 运行现场(真机登录失败落到 F003Repository:385 的空串)、授权口径变了(用户一句「请修复登录问题」)、晚出生的现成件(DevicePrefs.getOrCreateMarkId T+22:39);事实本身没有多 |
| 0723 WXEntryAbility.ets(created) | 23 次 / 4.9 万字 | 主会话·9b3105a2 v124 派发词(#1447@L2899)「WXEntryActivity 注册 → 华为侧无等价,属三方 SDK」,与同一会话 T+0:01 自己 grep 出的 manifest 清单(#23@L66,`${applicationId}.wxapi.WXEntryActivity`)矛盾,配合「输出=单文件、不写共享文件」把口子焊死;结构根在页面清单按 .java 枚举,manifest-only 的 alias 从没成为一页(批量脚本,停) | 安卓 manifest 的 alias 层(生成侧零 manifest 读取)、装配后全仓视野(零调用点是 7 小时后才能做的 grep)、生成侧自己写的注释被当契约对账 |

四根的共同点:**故障进入点都不在转换器,在决策 / 判据 / 派发词那一环**(AC14、技能定义、D-010、派发词),转换器和修复方几乎全是
「传递」;修复侧多看到的大多是运行期观测、晚出生的现成件和授权口径的变化,新事实很少(PreferenceKeys 那根修复方引的就是
生成期 T+1:06 的同一条打靶结论)。这就是飞轮要归的类:生成期缺的是「把已知事实转成可执行选项 / 跑起来看一眼 / 完成检查」。

四份日志里的摩擦(合计约 20 万字返回,进报告的不到三分之一),当天改掉的(commit 60a26e1 之后一次提交,tests 269):

| 撞上(报告原话) | 改法 |
|---|---|
| think #4218 有 9.8 万字,action 只回前 2 万且不说截在哪,决策句在后面,只能拿 search 撞 | action 加 offset= / find=,截断处明说「剩余 X 字,offset=N 继续」;think / say 正文在输入侧,窗口作用在那一侧 |
| 修复方 Read 了双端拼图 MainActivity.jpeg(#4431),时间线里只剩裸 Read | 图片 Read 记 via=image 的读(有边车 type=image,或无边车按扩展名),不立版本,时间线带文件名 |
| 「修复侧多看到的」列的是生成方也读过的同一版 decision-ledger,写者还标成修复后 39 分钟才写的 1d2ef418 | 写者按修复方读到的那一版取;这一行改叫「依据单的来历」;新增「修复方读了而生成方没读」真差集按类型分组 |
| 查 WXEntryAbility,依据列的是 MineFragment 的 4 张单,真正的 WXCallbackActivity_01 单不在列表里 | 依据按被修文件挑:单名含词干或内容提到该文件的才列,其余只计数「窗口内另 N 张单与本文件无关」 |
| app.json5 v2「实录外修改」是幽灵版(内容首次可见),blame 把模板默认值答成「归属未知」 | 外部输入 / 批量生成首版内容未知时,第一张全文快照填进首版;被修行来自外部输入时原作者写「外部输入(模板/脚手架默认值)」,生成方只认 agent |
| 收尾摘要标「共 4249 字 (#1001)」,展开是 162 字的 say | 收尾坐标指向父会话的派发调用 action(父, #n),全文在那条结果里 |
| 每个 agent 视图 17 行「注入技能」+ 17 行「读 SKILL.md · 注入」 | 注入只列一次,超过三份折一行 |
| file(v=2, diff=1) 先倒 v1 的 320 行创建 diff,目标版被截掉,2.3 万字零信息 | diff=1 只给第 v 版;创建版 content=1 不再把全文打两遍 |
| F013Service.ets 15 版全内容未知,按词查文件白跑 | index 标「N 版内容未知」 |
| 查主会话「写 spec 时凭什么」用窗口拿回 30 多个无关读;不知道 blame 能查单行;created 链三个否定证据要 5 次拼 | GUIDE:主会话凭什么用带锚点的 search;blame(start=行, n=1);created 链三问;结论要求改成整条链按环判定 |

没改、记下的:写级(而非版本级)读取归属 —— 用 heredoc / 脚本改文件的 agent,那些写不立版本,夹在中间的读全被下一次真写吸走
(fixer-r1 v26 吞了 20 多条无关读,差集也因此混进别的文件,渲染只能点明「看类型别看单个文件」);决策项原子 decision(id)
(D-010 的登记 / 状态 / 引用 / 改判散在六次调用里);search 的 context=N 与 diff 的版本区间;派发词的来源分解(哪句是模板固定
话术、哪句是模型现写 —— 环判「错」还是「传递」取决于它);约束反查 origin(q);readers 表不含命令输出推出的读、与 search 口径
不一;curl 里的 127.0.0.1 被当路径;动作号 #n 在账本重建后会漂(加了读边之后 #4431 变 #4435),引用要带 @L。

### 4.12 2026-09-07 深夜,按口径挑六根:两组同题,按环盲评

用户要按「最多跳 / 生成→修复耗时最长 / 生成期改动最多 / 修复期改动最多 / 最耗 token」挑案例。口径从账本算
(`docs/experiments/2026-09-07-six-cases/case_metrics.py`):token 按「写这一版的 agent 在上一效应→这一效应之间花的
上下文 / 输出 token」挂到文件版上(0723 转录每条 assistant 记录带 usage;DiceRoller 导出包 usage 全 0,做不了);
「最多跳」当时用带 400 节点上限的 BFS 量,0723 四跳就撞上限,不准 —— 见下面 DP 一节。

两组任务一字不差(`task_chain.md` / `task_rewrite.md`):追到头,每环「谁、凭什么、判定(传递 / 错 / 缺)」,指出故障进入点
和修复侧多看到的;工具组只给文件名(泄露检查 0)。评委改按环比(`judge_chain.py`):各找到几环、共同环上判定是否一致、
进入点是否同环、坐标可核性、更可信、对改流程更有用。

| 根(口径) | 费用 工具/原始 $ | 调用 | 进入点同环 | 更可信 | 更可行动 |
|---|---|---|---|---|---|
| DiceRoller EntryAbility(最多跳) | 1.32 / 1.67 | 24 / 25 | 是 | 工具 | 原始 |
| 0723 HomeTabComponent(最耗 token) | 1.44 / 2.09 | 29 / 31 | 是 | 原始 | 原始 |
| 0723 MemberCenterPage(耗时最长) | 1.25 / 2.16 | 29 / 24 | 否 | 原始 | 原始 |
| 0723 SplashPage(生成改 51 版) | 1.41 / 2.91 | 30 / 35 | 否 | 原始 | 原始 |
| 0723 GuidePage(修复改 4 次) | 2.10 / 2.22 | 34 / 29 | 否 | 原始 | 原始 |
| 0723 EntryAbility(生成改 36 次、修复没动) | 1.71 / 2.25 | 26 / 23 | 否 | 原始 | 工具 |
| 合计 | 9.23 / 13.30 | 172 / 167 | 2/6 | 1:5 | 1:5 |

工具组便宜 31%、快 24%(1865 s vs 2470 s),调用次数一样,返回字数 36.5 万 vs 66.3 万。按环评输了,逐根核对之后错分三类:

- **账本缺边**:MemberCenterPage 修复方用 python heredoc 的 `s.replace(old, new)` 改文件,账本记「脚本黑盒」不立版本,链的修复方
  成了后面只放宽 private 的 build-verify-r1,进入点落进修复轮内部。→ 当晚修:python heredoc / -c 的规整读改写按 ast 解成确定读写
  (`s=open(p).read(); s=s.replace(a,b); open(p,'w').write(s)` → edit;常量 `write_text` → 全文写;原样写回不立版本;解不出的仍是黑盒),
  MemberCenterPage v10–v16 归 fixer-r1(commit 5edfe7d)。
- **查询范围错**:SplashPage 工具组只在 conv-splash 一人的记录里搜 windowFullscreen,零命中写成「生成期各输入零命中」,被原始组用
  AIPPT_design.md 证伪。账本里其实有:AIPPT_design.md@v1:471(ref-doc-analyzer,T+0:59)、主会话 #249 读 themes.xml(T+0:33)。
  GUIDE 里写了三次「零命中只证明范围内」都没用 → 改成结构的:每次 search 第二行是「范围」;不带起点必须带 until_ts,
  `search(q, until_ts=生成时刻)` 全池查那一刻之前所有 agent 记录 + 所有文件已知内容,结果自带范围行(0723 那次:146 个 agent、
  2271 个文件、内容未知 349 版),结论要求写「没有」必须抄这一行(commit 3168753)。
- **账本缺内容**:0723 EntryAbility 工具组说「该文件没进修复轮」,其实开屏状态栏那张 ALIGN 单点了它;那张单是 vv 代理用渲染脚本
  写的,账本里内容未知,`search(file=)` 答「内容未知的版本查不了」。要从后来的完整读回填(现在只有全文 Read 回填,grep 到的行不算)。

DiceRoller EntryAbility 两组同一进入点(转换器写 v2,缺:安卓对照物没有全局异常观察者,派发词把范围限死在沉浸式与 F001 契约),
原始组多追了两跳到 ECAT 判别器会话与 crash_risk 检测器配置 —— 工具组停在「会话入口指令注入,账本里无写者」:另一个缺边,
跨会话的指令文本其实是前一个会话的输出,可以按同文对上。0723 EntryAbility(改 36 次)两组都查出 37 版里约 19 版是派发词授权的
「注入-编译-还原」自验脚手架、`setDebug(true)` 硬编码留在终态;分歧在进入点(工具:Base-1 派发词缺 elide 一条;原始:技能没规定
共享 WindowModel 的归属,8 份同名桩)。

**上游跳数改成建账时 DP 预存**(commit 见下):用户口径「agent→文件→agent 每一次转换算一跳」。节点 = 文件版与 agent 版,边只指向
更早时刻(写者的读在写之前,派发在子之前),按时间序扫一遍 depth = 1 + max(前驱),0723 5570 个节点 0.1 秒。两个口径都存:
累计(agent 写之前读过的一切都是前驱,诚实上界)与窗口(只算上一效应之后读的);index / file / agent / sessions 都印「上游 N/M 跳」。
0723 十九根累计口径 554–606 跳、窗口口径 5–136 跳:累计量的是管线深度(主会话几百轮),窗口量的是最近一轮手里的东西;
挑「链最长」看窗口那一列(HomeTabComponent 132、MineComponent 134、WorksComponent 136)。


**修掉之后重跑(工具组重跑,原始组报告不动,评委同一套)**:第二次(ast 读改写 + search 范围行 / 全池 until_ts + 上游跳数)
`cases_tools2`;第三次(再加 for 循环 echo 分隔切段、脚本字面量正文记「部分内容」、GUIDE 修复轮没动的文件先全池查提到)只重跑
第二次还输的三根 `cases_tools3`。每根取最新一次:

| 根 | 第一次 | 第二次 | 第三次 | 评委给的理由(最新一次) |
|---|---|---|---|---|
| DiceRoller EntryAbility | 工具 | 工具 | — | 两处零命中都写明范围(80 个 agent + 570 个文件,内容未知 54 版),覆盖两簇改动 |
| HomeTabComponent | 原始 | 工具 | — | 唯一追到池外叶子;负面结论一律显式限定范围 |
| MemberCenterPage | 原始 | 工具 | — | 11 环 vs 6,进入点回到生成侧(两处不同缺陷各自成链) |
| SplashPage | 原始 | 原始 | 工具 | 覆盖返修全部维度(返回键 / 进度条 / 状态栏),blame 逐行签名 + 读取集 + 派发词三方互证;零命中带范围 |
| GuidePage | 原始 | 原始 | 工具 | 共同环 8 个判定全部一致、进入点同一个;每条否定都写范围,原始组反而有两处全局否定 |
| 0723 EntryAbility(改 36 次) | 原始 | 原始 | 原始 | 20 版内容未知(base 层 cp .bak 还原、shell 写)的推定;三次都从 sessions 0/29 推「修复侧没多看到」,没去全池查文件名 |
| 合计 | 1:5 | 3:3 | 5:1 | 进入点同环 2/6 → 3/6 → 3/6(不同的三根是同一文件两处缺陷各追一条) |

费用:第二次工具组 $8.96 / 29 分(原始 $13.30 / 41 分);第三次三根 $4.43。

**第四次(09-08,当天全部改动之后再跑一遍六根,`cases_tools4`)**:工具 3 : 原始 3(DiceRoller / GuidePage / MemberCenterPage 信工具,
HomeTabComponent / SplashPage / 0723 EntryAbility 信原始),进入点同环 3/6,费用 $10.7。和第三次「每根取最新一次」的 5:1 放在一起看,
单根一次跑的盲评在同一套工具上会翻(HomeTab 与 SplashPage 两次跑一次工具一次原始),噪声就是这个量级;稳定的是三件事:
DiceRoller 与 GuidePage 每次都信工具、0723 EntryAbility 每次都信原始、进入点同环的根两组结论一致。评委这轮点名的工具组问题
仍是同一句:范围有限的零命中被当成因(HomeTab 权限侧「依 D0 不接线本就正确」没检验)。六根两份报告并排见 Artifact「六根返修链对照」。评委翻过来的理由几乎都是同一句:「对每条否定断言写明
检索范围与覆盖度」—— 范围行不是措辞,是模型能引用的东西之后,行为就变了。剩下那一根输在两处:shell 写(cp .bak 还原、
heredoc 拼接)的 20 版内容未知,链建在推定上;以及模型没有对「修复轮没动的文件」做全池查(GUIDE 已加,未重跑)。

### 4.13 2026-09-08,换会话:pod730(Windows、221 个 agent、没有修复阶段),「为什么反复改」三根

用户要求别只在 0723 上测。本地有分量的只有 pod730(AntennaPod 迁移,Windows 机器跑的,主会话 8001 行 + 220 个子代理);
它全程停在 a2h-execute、没有 stage-marks,所以没有返修链,只能测 0723 EntryAbility 那种题:一个文件生成期被改了几十版,为什么。
挑了 MainPage.ets(126 版、12 个写者、85 版内容未知)、HomePage.ets(57 版)、AudioPlayerPage.ets(52 版),两组同题
(`task_rewrite.md`),模型 claude-opus-5(两组与评委,result.json 的 modelUsage 可查)。

**先亲手走**,撞出四类,当场修:
- Windows 幽灵路径:同一个 MainPage.ets 在账本里是三个文件(`C:/…`、Git Bash 的 `/c/…`、cwd 已在 `…/ets` 下又写工程相对路径
  拼出的 `…/ets/features/shell/src/main/ets/…`)→ 盘符归一、连续重复 ≥3 段折掉、单一 cat 快照按归一化路径对账(8c1a3d2)。
- `python -c` 里 `s2 = s.replace(...)` 结果赋新变量被当黑盒,MainPage v42 之后 85 版全盲的第一刀 → 解成 edit(ea9a248);
  v43 是 `re.sub` 真算不出,之后 178 次读全是 grep、没有一次全文读,所以从 v43 起仍是未知,这是诚实的。
- 大会话的字数:`index(kind=agent)` 不带 query 一次 3.4 万字(221 个 agent)、一个 52 版的 agent 整段 1.8 万字、126 版脊柱 1.35 万字
  → index 不带 query 上限 80;agent 超过 25 版且不带 since 窗口读只给条数;脊柱同一写者连续几版折一行(ffdc12e、059541b)。
- 解析脚本正文的 SyntaxWarning 刷屏(75a6302)。

**第一次(工具组比原始组贵 40%)**:

| 根 | 工具 $ / 轮 / 返回字 | 原始 $ / 轮 / 返回字 | 评委 |
|---|---|---|---|
| MainPage | 3.21 / 29 / 15.8 万 | 2.39 / 25 / 9.4 万 | 原始 |
| HomePage | 2.45 / 31 / 7.9 万 | 1.52 / 14 / 6.7 万 | 原始 |
| AudioPlayerPage | 2.46 / 33 / 8.0 万 | 1.86 / 23 / 7.0 万 | 工具 |
| 合计 | 8.12 / 93 / 29.4 分 | 5.78 / 62 / 24.9 分 | 1:2 |

钱不是花在逐版看:MainPage 那次 file 只调了 2 次,大头是 index(kind=agent, limit=300) 3.4 万、5 次 agent 4.6 万、8 次 search 4.4 万。
用户点破的根因:原始组一段 python 把这个文件全部 Edit 的 old/new 扫出来,拿到的是「谁、什么时候、改了什么」;我们的 file()
只给「谁、什么时候」,改动正文要另调 diff(path, v),而 `file(diff=1)` 又被 §4.11 那次(PreferenceKeys v=2 被创建 diff 顶掉)改成
「只给第 v 版」。模型拿到脊柱看不到改动,只能去翻 agent / index / search。→ `file(path, diff=1)` 不带 v 改成改动日志:每版一行头 +
改动正文(截 600 字,创建版只给行数),一页最多 40 版,v_from / v_to 翻页;带 v 仍只给第 v 版(e991c4f、5748df1)。
MainPage 126 版一页 2.3 万字;原始组同题 24 次调用 9.4 万字。

**第二次(改动日志之后,原始组不动)**:

| 根 | 工具 $ / 轮 / 返回字 | 评委 | 进入点 |
|---|---|---|---|
| MainPage | 2.38 / 24 / 10.6 万 | 原始 | 同环(都指「本页是 11 条 registry 槽宿主」那句派发词) |
| HomePage | 2.16 / 32 / 8.6 万 | 原始 | 不同(工具:派发词把「不实现 6 个 Section」与「写出各槽接线」压给同一 agent;原始:converter 首版把 6 个尚不存在组件的参数面写成断言式注释) |
| AudioPlayerPage | 2.11 / 27 / 9.9 万 | 原始(第一次是工具) | 不同(工具:Convert 建 v1 埋 25 条 FWD-REF + 自画遮罩;原始:§5 遮罩规则没有归属条款) |
| 合计 | 6.65 / 83 / 24.0 分 | 0:3 | |

费用从贵 40% 降到贵 15%,时间已低于原始组(1441 s vs 1494 s);模型自己会翻页(v_from/v_to、diff_chars 200–420)。
可信度上这类题原始组仍赢,评委的理由集中在三点,前两点是账本的洞:
1. 三处「实录外修改」原始组至少还原了一处真实写者(Base-6c 的 bash 写)—— 收集器漏了一种 shell 写法;
2. 原始组的坐标带 UTC 秒级时间戳 + old_string/new_string 原文,能用 `old_string ≡ 上一次的 new_string` 坐实回改;我们的版本号坐标做不了这种互证;
3. 模型自己的判断:把三个 batch closer 的正常补充一律判「源码没读全」、多环判「传递」、漏掉双份 NavigationNames 这条结构债。

**结论**:返修链那类题(有生成方、修复方、缺陷单)工具组 5:1;「为什么反复改」这类题信息本来就在 Edit 列表里,原始组一段脚本
就够,工具组现在费用持平、时间更快、可信度仍输,输的两条里一条是收集器的洞(见 §7)。

### 4.14 2026-09-08,调查覆盖:把模型做的调查展开在返修链路页上

返修链路页(`/api/insight1/fixchain/<sid>`,server 上 vendor 的同一模板)本来就是给人做调查用的两原子探索树。
这一步不另起页面,只把一次调查员(模型)的跑叠上去:它每一次工具调用落到哪个节点、报告里每一环指到哪个节点、
判成什么、故障进入点是哪一环。

- **入口**:`?probe=<run 目录,相对 MIGLOOP_RUNS>`(如 `cases_tools4/chain10-SplashPage.ets/rep1`),或左栏「调查覆盖」框手填后「载入」;
  数据来自 `/api/insight1/probe/<sid>?run=…`(`probe.py`),读 run_probe.py 落的 `metrics.json`(transcript.seq,逐次调用)
  与 `result.json`(报告正文)。
- **调用 → 节点**:file / diff / blame → 文件@版;agent → agent@版;action → 动作号反查归属 agent 与它喂养的版本;
  search 带 agent / file 的落到对应节点,全池的挂在面板上;sessions 落到链根。
- **报告环 → 节点**:每一行 `环 N …` 里按出现位置取坐标(`path@vN`、agent id、`#n@L行`),第一个是这一环的主语,
  判定(`判定: 传递 / 错 / 缺`)只落在主语上,其余坐标只算「提到」;同一节点被几环判过取最重(错 > 缺 > 传递)。
  「故障进入点:」之后(可跨行)第一个环号是主进入点,正文里「…的进入点是环 N」再补几个。
- **页面上(第一版只上色,用户看了一眼就指出树没跟着长)**:树是懒展开的,只给已经画出来的节点上色,根的 17 个直接上游里
  只有 2 个在集合里,其余 24 个查过的节点都在更深层,看起来「只展开了一个 agent」。用户裁定:查过的都要展示,以被修文件
  向左长成树;被归因的链路整条标红(agent、file 节点都红)。
- **调查树(3ca4919)**:根开好之后沿账本的边 BFS 自动往上游长,每一层只展开落在 probe 集合(查过 / 判过 / 提到)里的子节点,
  其余折成一个「+N 未查」桩(点开可看);同一个键只展开一次(主会话在很多 agent 的派发边上都会出现,再出现只标「已在上方展开」);
  最深 10 层;沿边够不到的查过节点(模型用 search 跳过去的)列在面板「查过但不在这棵树上」。报告环的主语节点整条标红,
  链上相邻节点之间的边也红,判定文字仍分 传递 / 错 / 缺,进入点描边;长完整棵适应视口。
  SplashPage 那跑长成五列:根 ← conv-splash v1 / slice11-startup v37 ← AppLoadDialog.ets@v5、F001 spec、SplashPage 旧版、
  派发它们的主会话 ← conv-apploaddlg v1、主会话 9b3105a2 v60 ← ref-doc-analyzer v10 ← 主会话 v1;根下 +12 未查、主会话 v60 下 +230 未查。
- 左栏面板列全部环与步骤,点一环或一步就把那个节点开成根,树按它重新长。
- **SplashPage 那一跑(cases_tools4 rep1,$1.91 / 30 轮)**:29 次调用 26 次落到了节点(3 次是 guide 与全池 search),
  10 环 6 个节点带判定,三条缺陷各自的进入点(环 9 派发词、环 6 conv-splash、环 3 slice11)都在树上:
  上游一列里 conv-splash v1 与 slice11-startup v37 被标出,其余十几个 closer 变淡 —— 模型查了谁、漏了谁、把问题定在哪,一眼可见。
- **约束**:报告得按 GUIDE 的格式写(`环 N`、`判定:`、`故障进入点:`),池外一环(安卓源码、模板)没有判定就不上色;
  坐标解析不到的调用(3/29)只在面板里列,不落树。vendor 到 migbot-server 由用户定。

### 4.15 2026-09-08,脚本这一类到底缺什么:不是解析,是接线

用户追问「脚本读写无法静态解析,是不是我们最主要的问题」。把几轮输掉的根按原因归类:脚本 / 命令解不出效应的
(MemberCenterPage heredoc、0723 EntryAbility 20 版 cp .bak / shell 写、pod730 HomePage 自定义替换函数、MainPage 一次 re.sub
之后 85 版全盲、vv 渲染脚本写的单内容未知、运行期观测不是文件)占一大半,且是唯一还在持续输的一类;其余是查询范围
(已结构修)、模型判断、坐标可核性、跨会话指令边。

再往下追,发现材料并不缺:agent(id, v) 就是按版本切片的结构化转录,每条命令都列着,解析不了的还打「⚠ 未解析读写」带 #n,
action 展开就是全文 —— 和原始组扫转录看到的一样。差在三处接线:文件侧没有反向指针(「实录外修改」的叶子不带命令号);
静默错解不打标(分析器以为解对了的没有 ⚠);模型不点(0723 EntryAbility 的 cp .bak 账本标「内容未知」而不是 ⚠,模型就按
行数推了,原始组读了 cp 那行)。

用户点出原始组的办法:按文件名 grep 转录,脚本正文里含这个路径的命令直接跳出来 —— 这可以在建账时预先做。做了(930d692):
- 收集层对每条 Bash / PowerShell / codex exec 记 `detail.mentions`:命令行 + heredoc 体 + 它跑的脚本正文里长得像路径的词,
  带前后 60 字;建账时按后缀对到账本里的文件(只有文件名的对所有同名文件,标 ambiguous)。
- `file()` 末尾新增「提到它的命令(N,其中 M 条账本没记到读写)」:每条标明账本记到了什么(写@v / 读 / 碰过 / 没记到),
  action 展开命令原文自己判;index 行带「M 条命令提到它但没入账」;GUIDE:版本无法复原 / 实录外修改先看这一节。
- 这一节等于原始组的 grep 结果,解析器放弃的、当成无关的、写在 heredoc 正文里的都在。脚本这一类上两组材料持平,
  我们多的是「账本记到了什么」这一列。

还没做的两条:分析器解出的每一版带「解法」(工具写 / heredoc 全文 / ast 读改写 / 重放 / 推断),模型看到「推断」就知道该核;
对已知内容重放 sed / replace / re.sub(字面量模式)直接算出结果立版本。以后的会话该在源头收效应(post-Bash 工作区快照),
历史会话只能靠上面这些。

### 4.16 2026-09-08,外部评审后的第一批:不让推断越级成为事实

评审(docs/proposals/2026-09-08-review-brief.md 送评,GPT 两轮意见)在 ca3f3b0 上构造反例,确认账本有几处把推断记成了事实,
且 #n 坐标随解析能力升级而漂。裁定:第一批以稳定身份、状态机正确、时间边界、证据分层、完整性测试为交付,不扩 UI;
时间坐标(F)不做,分层建账(G)不依赖 F。每条反例写成回归测试(tests/test_evidence.py,先红后绿),8d802a3 落地:

| 反例 | 修法 |
|---|---|
| Write a → 不透明写 → Edit → Read 得 c:快照封到不透明写那版,Edit 版留白,读却绑它且 certain | 状态未知时的盲 Edit 进 pending,快照封在最后一次未知写上;状态已知的 edit-miss 仍走断点 + 观测重锚 |
| 00:00 发起 Read、00:10 Write、00:20 才返回:读被算成那次写的输入 | Action 记 done_ts,输入喂的版本按完成时刻算 |
| `--out-dir` 跑完输出 nothing changed,首见文件被记成它生成(作者、版本都指向它) | 目录级候选不再升级成作者:作者仍是外部输入,gen_runs 留候选,file() 标「候选生成运行 #…(目录级线索,未证实;同批 N 个)」;0723 由此 398 个首版是「外部输入 + 候选」 |
| 解析器多认出一条读,后面同一次 Write 的 #n 从 2 变 3 | 稳定事件 id = 会话:转录:tool_use_id(缺 id 用行号),action() 印出;#n 只是本次建账的句柄 |
| via=tool 实线、via=script 虚线,按来源定强弱 | 每版带证据标签:工具写·报告成功 / Edit·报告成功 / 推导·heredoc 全文 / 推导·ast 读改写 / 推导·黑盒写 / 观测·首次读到 / 观测·内容变了无写者 / 首见·内容未进上下文,+观测封口 |
| `printf x > A; exit 1` 写了文件,账本因失败不收 | 失败命令保留指针,标「命令失败,效应未知(可能已部分执行)」,目标文件挂候选;0723 有 105 条 |
| `false && cp b A; true` 没执行 cp,账本记成写 | && / \|\| 之后的操作标「条件分支,是否执行未知」(cd / mkdir / echo 这类前件除外);0723 有 25 版,EntryAbility 那些 cp .bak 还原都在其中 |
| 子代理 00:10 跑 fix.py,主会话 00:40 才写;脚本表共享、主会话先走 | 脚本表全池预扫(带写入时刻),按运行时刻取版本,Edit 同步;运行时尚不存在的标「脚本正文未知」(0723 100 条);跑的 .py 也走 ast |
| 提及最多 40 条静默截断;只被提到的文件没入口;未完成调用丢指针 | 记 mentions_truncated(0723 20 条);目录已知的只被提到文件建入口「只被提到」(195 个);未完成调用保留 src / tuid / 提及 |
| 缓存键只看 root 转录 | pool_key 含 subagents/*.jsonl |
| probe 引用 #n@L 不校验 L | L 与账本行号对不上的进 bad_refs,不落节点;面板标「引用无效」 |

建账时间 13 s → 18 s(预扫 + 跑脚本走 ast + 提及带 cwd 解析),记忆化仍未做。评审第二轮补的四条纠正一并记为口径:证据强弱按断言
不按来源;glob 在已知文件集上展开是候选且集合可能不完整;并发只有先于 / 晚于 / 重叠不确定三种;分页保证可检索,不保证默认铺全;
引用核验只证明位置存在、原文匹配。第二批(评审排序):全量词法索引与分页、输出提及(I)、A、B、C、引用校验接进评委。

### 4.17 2026-09-08,评审后第二、三批:词法层做全、稳定引用、树上虚线、按缺陷分组、评委接核验

用户裁定「全做完,中途不停」。按评审排序继续,每条先红后绿:

- **词法层第二批(c21bcf7)**:提及收工具输出(git status 的 modified、构建报错、grep -rl);按分档列(改动类 / 正文提到 / 输出里 /
  其他逐条,只读检查折叠,m_all=1 铺);一页 40 条 m_from 翻页,没返回的不算看过;每条标它落在哪一版的窗口;内容未知 / 实录外修改的
  版本行给「窗口内提及 N 条(改动类 K)」和「窗口内有写能力的命令 N 条(全池):search(q='', kind=write, since_ts, until_ts)」的查法,
  不自动铺;search 命中在 Bash 里、账本没记读写时带「可能碰到 X」;agent 槽里解不出效应的命令直接带「可能碰了 X@v」;
  agent(id, v, until=#n) 把槽截到那条命令。回归集 tests/test_lexical.py。
- **稳定引用(c762198)**:cite_check.py 对旧报告机械核验,坐实评审反例 ②:账本重建后,工具组报告里 #n@L 有 22/47、13/33、14/27、12/32、5/33
  对不上(#n 漂了),原始组的 jsonl:行号 与 toolu_ id 全部可核。引用格式改成 (#n@L行·转录标识):#n 是本次建账的句柄,
  @L行·标识是转录位置不漂;账本存 locs / by_loc,probe 与 cite_check 按 (标识, 行) 反查,#n 漂了也能对回去。
- **提速(1cd0719 + c762198)**:parse_shell / _split_segments / _tokenize / _resolve / _split_segments_ops 记忆化,分档按段边界一次算,
  输出只扫前 20KB;0723 建账 18 s → 9 s(评审复测的 13 s 是这次改动之前的基线)。
- **树上虚线 + 按缺陷分组(5bf3ffb)**:文件节点上游挂「⋯ 可能写 agent vN」虚线节点(词法层沾边的改动类 / 正文提到 / 输出里,
  按 (agent, 版本) 合成,不立版本不进 blame,点它开抽屉),只读提及折成灰桩;probe 解析报告环的【A 返回键】标签,面板按缺陷切换,
  只留那条链红。评委脚本 judge_chain --sid 把两份报告的引用核验一行拼进提示词,位置无效不计可核性(位置有效也只证明记录在,
  不证明断言成立)。
- **词法层扩到全部记录种类(6d14c16)**:完备性差集检验 lexical_gap.py —— 拿文件名 grep 整份转录,和账本入口按 (转录, 行) 对。
  SplashPage 918 行提到它,原来只覆盖 621;派发词 / 发消息 / Write·Edit 写入内容 / 说·想·收件正文里的提及进账后覆盖 793。
  剩下 125 行:98 行是 Read 结果正文里提到(别的文件内容里有它的名字,search(q, file=) 按词能查,不当动作入口),
  其余是 file-history-snapshot / attachment / queue-operation 这类 harness 记录。EntryAbility 406 → 348,MemberCenterPage 405 → 354,余同。
  派发词默认列(谁被告知了这个文件),写入内容与正文折叠计数。

没做、明确放下的:坐标全面换时间(评审否决,用稳定引用代替);分层建账(记忆化后 9 s,首屏收益不够,搁置);重放(H,评审要求状态机
稳了再渐进);源头收快照(L,以后的会话);原始转录组的跑落到树上(它引的 jsonl:行号 现在能按 by_loc 反查,接线未做)。

### 4.18 2026-09-08,第二轮评审(REQUEST CHANGES)逐条修:R1–R8

第二轮独立验收(`C:/Users/hongy/projects/_migloop-review-aa277bb/`,14 条失败用例 + 真实 0723 审计脚本)指出「有实质进展,但不能验收全部落地」。
16 条用例原样进 tests/test_review2.py,先全红,eb972ff 全绿(338 通过)。逐条:

| 评审项 | 反例 | 修法 |
|---|---|---|
| R1 引用不唯一 | 子代理文件名 agent-aconv-apploaddlg-8ea… 的 8 位标识 aconv-ap 非 hex 且 17 个短标识各对两个文件;同一记录两个 tool_use 撞位置;13,878 个可生成坐标往返只 3,474 有效 | 标识取文件名末尾整段 hex;引用改成标识在前 `#转录标识:n@L行[/块]`(cases_tools5 的报告里模型把后缀标识截掉了七成,放前面是坐标的一部分);by_loc 撞键记歧义不 first-wins;旧短标识唯一才迁移;audit_0723 往返 13,878/13,878,撞键 0 |
| R2 条件分支污染状态 | `false && 写 A=b; true` 报告成功,再 Read 得 a:账本多出 v2=b 和一次「实录外修改」 | && / \|\| 之后的写不进正式状态:只记「条件分支,是否执行未知(候选写)」并进全池写候选;读不受影响(读的证据是它的输出)。0723 上 25 版条件写退成候选 |
| R3 脚本表拿错正文 | Write fix.py 报 Permission denied 仍入表;子代理 Edit 过的脚本主线用旧正文;/tmp/one 与 /tmp/two 的同名 fix.py 串用 | 预扫描按 tool_result 成败入表、收 Write/Edit/MultiEdit/heredoc、全池按时刻回放;运行时先按完整路径查,basename 只在唯一时兜底 |
| R4 覆盖量尺 | lexical_gap 把相邻行当覆盖:无入口的 file-history-snapshot 紧挨 Write 被算覆盖 | 按动作自己的 tool_use / tool_result 行精确配对;SplashPage 815/918、EntryAbility 358/406、MemberCenterPage 372/405 |
| R5 有副作用的命令折成只读 | find -delete、git -C /proj restore 判 readonly,全池写候选为空 | git 跳过 -C/-c 找子命令;find 看 -delete/-exec;改动类提及进写候选 |
| R6 收集截断 | 一次动作 40 条以后的路径没进索引;输出 20k 字符以后没扫也没标 | 收集上限 2000 条(展示层再分页);扫描预算 2MB,超出记 mentions_scan_truncated |
| R7 缓存 | 转录追加后重建账本,search 仍读旧行 | 转录行缓存键带 (mtime, size);不带 v 的 search 是整个生命周期 |
| R8 核验边界 | jsonl:0、@v0 判有效;toolu 正文里提到也算 | 行号 ≥ 1、版本 ≥ 1;toolu 只认 tool_use 的 id;核验状态分 ok / drifted / ambiguous / missing / untagged |

评审同时明确的边界,记为口径:引用「位置可核」不等于「原文支持断言」,树上和评委都要分开标;前后快照只证明净变化;
五根 0723 反复用于开发,只算开发回归。cases_tools5(新工具、旧的后缀标识格式)五根报告:引用 19/33/35/44/22 条,位置可核 13/9/21/9/9,
无效里绝大多数是模型抄引用时把 ·标识 截掉了(5/24/14/35/12 条无标识)—— 标识在前的格式就是为这个改的,下一轮才能量到。

**cases_tools5 vs cases_raw,评委接引用核验后(judge_chain --sid ff019d8a)**:四根全部信原始组(HomeTab / GuidePage / MemberCenter /
SplashPage;可行动 3:1 原始),EntryAbility 因目录名 chain94 / chain90 不配对另评。评委每根都把「工具组坐标核不回去」写进理由
(HomeTab 6/19 无效其中 5 条无标识;GuidePage 24/33 无标识,含定案用的四条;MemberCenter 14/35;SplashPage 35/44),这正是核验器
设计的效果 —— 它惩罚的是模型抄引用截掉后缀标识,不是账本事实错。实质分歧也有:HomeTab 原始组用同轮兄弟 conv-homedoc 的正例把
「没有输入」和「有输入没用」切开(工具组判缺,原始组判错,评委信后者);GuidePage 两组进入点同环、时序互相印证,工具组「返回图标缺」
的判定和自己的「无法确认」互相拆台;MemberCenter 价格支同一环(动作号 264 都对上),文件级首错分歧;SplashPage 状态栏支两组结论
相反,评委信原始组(派发词没给指针 ≠ conv-splash 没错)。这一轮定位为开发回归:代码、prompt、五根都是反复调过的。
cases_tools6(标识在前的格式,其余不变)在跑,用来量引用格式这一项。

### 4.19 2026-09-08,结构化结论 → 调查树:一期闭环

评审两轮之后,用户把目标说清了:工具驱动的调查每一步落在节点上、结论落成一份可复查的结构,载入页面就能看到
「问题节点红了、每个节点有原因」。GPT 的交接说明(`_migloop-handoff/2026-09-08-investigation-ui.md`)加了三条边界:
修复后的版本不染红;「带病传递」不等于失职;YAML 里相邻不等于账本里有边。这一批按它做:

- 模型在散文链之后附一个 `schema: migloop-verdict/1` 的 yaml 块(格式在 GUIDE「结构化结论」一节);`verdict.py` 严格解析,
  节点坐标显式解析并校验版本范围,证据引用按 `resolve_ref` 各自带状态,边按账本的 写 / 读 / 派发 核成 true / false / unknown / not_checked,
  相邻项只自动核一遍并标 implicit。`repair.before/after` 是锚点不是角色,after 标带病算无效。
- 账本身份 `atoms.ledger_identity`(代码版本 + 转录清单摘要)写在 `sessions` 首行;harness 自己算一份存进 `verdict.json`,
  载入时不一致只告警。harness 抽不到 / 校验失败做一次 `--resume` 修复重试,两份结果与费用都留。
- 页面不新建:`probeRolesFor` 按 (缺陷, 键, 版本) 匹配着色,抽屉顶部「调查结论」块列原因与证据(可展开原文),
  面板列缺陷 / 修复锚点 / 节点诊断 / 边状态;步骤层独立(失败调用不算查过,索引 ≠ 正文)。
- 全仓 395 passed(基线 382 + 13);细节、schema 样例、真实一跑与已知边界见 `docs/proposals/2026-09-08-verdict-ui.md`。
- 用户看第一版树后裁定:调查树只收模型查过的 + 结论点名的 agent@版本 / file@版本,每个一次;第二版曾按「第一次出现在哪一步的返回里」
  挂父节点,用户追问「是不是在 invent heuristic」—— 是:记录只有调用序列和返回文本,进入边没有实录。定稿:结构只用账本核成 true 的
  写 / 读 / 派发 / 前一版,根 = 被修文件的最终版本,路线只是节点上的步号,「出现于 #j」只做事实标注;不在根上下游锥里的单独一列。
  `probe._trajectory` + `probeBuildTrajectory`;没有转录的老 run 退回账本树。全仓 399 passed。
- 路线要成为记录只有一条路:模型自己声明。file / agent / action / blame / diff 加可选参数 `via`(从哪个节点、凭哪一行来),
  harness 原样记录,probe 解析成声明边逐条和账本边对照(重合 / 不重合 / 跳 / 无法解析),页面画蓝色虚线,不参与布局。全仓 400 passed。
- 用户看了 via 的填法(一半是 sessions / search 跳、一次指向没打开过的 v8)后定稿:模型任一时刻站在一个节点上,file / agent 是移动、
  via 必须逐字等于已打开的节点(索引 = 整个,某版 = 那一版),第一次可写 sessions;blame / diff / action / search 不移动不开节点。
  服务端 `via.py` 强制,不对不执行;树直接按 via 走,每跳按账本标关系;老 run 退回账本边树。全仓 403 passed。
- 两处根因修掉:整个节点的「未查」按全部版本算且桩可沿账本展开;换根不再跑老 BFS;载入调查后不画词法候选。
  事实澄清:file 索引 = 最新版视图(一字不差),agent 整个 = 最后一版 + 尾巴。这一跑 14 个结论节点只有 3 个精确打开过 ——
  下一步(待用户定):结论只能落在打开过的版本上。
- 用户定稿:file / agent 的 v 必填,via 必须带版本且逐字等于打开过的节点,逻辑只剩这一条;树上从此没有「整个 / 索引」节点。
  顺带用现有 16 个 run 算了两组的依据覆盖:原始组每份报告只给 1–10 条坐标(严档几乎全核不回),工具组每份 19–95 条、97% 落在
  它看到过的返回里;同题 0723 五根工具组便宜 16%、快 24%。「更准」仍未证明 —— 评委得按依据覆盖评,不按细节多少。

## 5. 到目前为止的结论

**工具赢在**:行级归属、逐版本区间、明确标出哪些内容无法复原、跨段一致的口径、时间更快(轮次多但每轮快)。**输在**:

1. **账本没有 thinking / 正文**。「为什么这么写」这一层缺失,是唯一一处真正的信息缺口,也是最贵的一条。
2. **sessions 既是起点也成了围墙**。工具组拿到 4 个文件后只看这 4 个;原始组自己定范围,看到了模板、验证工具、ECAT 空转。工具替模型回答了「什么算修复」,模型就不再自己回答了。
3. **摘要被当成原文**。工具给的结构越完整,模型越不去读原文;工具的一处措辞(「外部输入 T+4:18」)直接误导了它。
4. **轮数就是钱**。原子粒度细,20 个版本调了 20 次 diff;原始组一条脚本扫全部。`file(path, diff=1)` 一次能给全部版本的 diff,模型不知道。

超集在能力上是超集,在行为上不是:工具改变了模型看什么、信什么。

**2026-09-06 全 19 根对照之后的补充(§4.8)**:

5. **同起点、无流程时,工具省一到两成,不是一半**。省的是调用次数和时间;费用只省 7%,因为工具组三分之一的返回是整段拉 agent(模型不带 since),每轮上下文和原始组一个量级。09-06 的 60% 一半是路径与窗口纪律(提示词侧),一半是抽样。
6. **坐标体系对外不可核**。盲评 17/19 更信原始,理由几乎全是「jsonl 行号 + 时间戳 + uuid 可回查,path@v / #n 不可」。账本每个 #n 背后都有原始记录指针(action 用的就是它),输出里带上就行;这不是事实差距,是展示差距。
7. **blame 断点是真缺口**。edit-miss / 实录外修改之后行级归属标「未知」,工具组老实写「无法确认」,原始组读 Write 原文补上。断点后的归属能不能从下一次全文 Write 重建,值得做。

**2026-09-07 五步优化之后(§4.9)**:

8. **四类账本欠账修掉之后,同四根新工具比旧工具省 23% 费用、比原始转录省 42% 时间**;
   模型有了带起点的 search 就不再整段拉 agent(13 次 → 5 次)。§5 第 6 点(坐标不可核)靠 (#n@L行) 解决,
   第 7 点(blame 断点)靠假 v1 修掉解决了页面首版那一半,edit-miss 那一半还在。

**2026-09-07 晚亲手追链之后(§4.10)**:

9. **「定性一致」宽松:只比结论一句话,不比链**。改成按环评:每环谁、凭什么、判定;进入点是否同一环;坐标可否回查。
   工具的账本边界露出来了:技能定义 / 子代理类型定义在系统提示里,账本没有记录,「来自类型定义」只能是模型的推断,不是图上的节点。
10. **修复侧多看到的通常只有一类:运行期观测**。生成侧没人把应用跑起来看;归因要归到「生成期缺哪一类反馈」,不是归到某个 agent。
11. **四根亲手追,故障进入点全在决策 / 判据 / 派发词一环,转换器几乎全是传递**(§4.11)。工具要能一步指到那一环:
    判据溯源(某句约束抄自哪条 spec / 技能 / ledger)和写级读取归属是下一批要补的。
12. **六根按环评 1:5 输给原始转录,每个错都能归到账本的一条边 / 一段内容 / 一次查询范围;修掉之后同六根重跑翻成 5:1**(§4.12)。
    翻过来的理由集中在一句:否定断言带范围。工具赢在便宜三成、快两成、覆盖面宽(多条缺陷各自成链)、否定可核;
    输的那根是 shell 写的内容未知 —— 账本的洞每修一类就少输一类,这是收敛的。
13. **换会话(pod730,Windows)之后**:账本在新会话上先撞出四类新洞(盘符、相对路径拼接、`s2 = s.replace`、大会话字数),都是一晚能修的;
    「为什么反复改」这类题的信息就是 Edit 列表本身,`file(diff=1)` 改成分页改动日志后费用持平,可信度仍输在一种没解出的 shell 写法
    和转录级坐标(时间戳 + old/new 互证)。工具赢的是链,不是所有题。

## 6. 决策日志(用户裁定,按时间)

- 2026-09-01:宁重写不糊弄,两原子基座;树上每列必须是真原子。
- 2026-09-02:每一个工具调用的输出都应能展开,永远不丢信息;收集器漏了会让工具 obsolete,解析不出的不许静默。
- 2026-09-02:前序轮回合内的返修也算修复方;修复 / 生成的判定可以肆意改,底层两原子不动。
- 2026-09-03:除了主管线,其他都不算生成;execute 结束之后的都是修复;修复期新建的代码文件也算修复。
- 2026-09-04:分析要忠实呈现不去重;每条链先总结生成期问题再归并,不许「分桶抽代表段」;双盲两组都不给链坐标、不给范围定义、不给流程,只介绍工具;段是容器、问题是单位。
- 2026-09-06:工具主干迁到本仓 dev/fixchain;hmigbot 的 migbot.insight 冻结;server 只做 UI 展示。
- 2026-09-08:file 以索引为主 —— 改动正文只在 diff=1 时给,不带 v 分页(一页 40 版),带 v 只给第 v 版;不能为一类题把别的题的 token 撑爆。
- 2026-09-07(深夜):跳数按「agent→文件→agent 每一次转换算一跳」建账时 DP 预存;零命中必须带范围。
- 2026-09-07:报告要写整条链,每环「谁、凭什么、判定(传递/错/缺)」追到池外 / 批量生成 / 技能定义为止,指出故障进入点;否决工具一次铺整棵树;盲跑暴露不了问题,靠亲手(含子代理)用工具找优化点;修复侧 vs 生成侧的差别按「缺哪一类反馈」归。

## 7. 下一步(按优先级)

1. 账本收 assistant 的 thinking 与正文,挂到它喂养的那一版上;agent 工具里看得到「写这一版之前它说了什么」。
2. 「外部输入」的时刻写成「首次被读于」,不确定的说不确定。
3. ~~sessions 除了链,把修复期所有别的写入按目录分组列出~~ → 已做一半(§4.7):脚本碰过、方向不明的工程文件已列出;spec/docs/测试目录下的修复期写入仍未列(它们不是链根,按口径不算修复)。
4. 降轮数:diff 支持版本区间,sessions 直接带每段的改动摘要;让第一手动作就拿到原来要 20 轮的东西。
5. 输出里保留「每条问题覆盖哪几版」一个字段(机械校验完备性用),其余不约束。
6. ~~改完在 DiceRoller 上重跑工具组看按钮那条能否自己归对,再上 0723(19 条链)做找全的压力测试~~ → 0723 全 19 根已跑(§4.8)。
8. ~~工具输出的每个 #n 旁边带原始坐标~~ → 已做(§4.9,(#n@L行))。
9. ~~agent 默认索引化~~ → 已做(§4.9);8 千字的目标没到(18K),剩下的是标签与行号本身。
10. ~~blame 断点后的行级归属~~ → 已做(§4.10,跨断点同文推定,010b167);不同文的行仍是未知,那是真缺口。
11. ~~search 的时间区间用法~~ → 已做(sessions 链行直接给派发者与生成→修复区间的 search 写法,4dc27ba)。
12. 子代理类型定义边:带 subagent_type 的 agent 给一条到 `.claude/agents/<type>.md` 的读边(内容不在转录里,先立节点),
    「来自类型定义」才能成为图上可指的一环;hook / system 记录(stop_hook_summary)同理入索引。
13. 任务说明改成「追到头并指出故障进入点」,两组一样;评判改按环比(找到几环、进入点是否同一环、坐标可否回查)。
14. ~~子代理亲手追四根的摩擦清单归并成工具改动~~ → 已做(§4.11,十二条);codex 侧本地没有带修复阶段的会话
    (transfer-app-d3 那份 0 条链),先不做。
15. ~~写级读取归属~~ → 规整的 python 读改写已按 ast 立版(5edfe7d);循环 / 正则改写的仍是黑盒。
19. 脚本渲染出的文件(vv 的缺陷单)内容回填:从后来任何完整读回填之外,grep / sed 看到的行也拼进「部分已知」。
20. 跨会话指令文本的来源:ECAT 的 work list 以会话入口指令注入,它是前一个会话(判别器)的输出 —— 按同文对上,给一条边。
21. ~~修掉三类之后重跑同六根~~ → 已做(§4.12,1:5 → 5:1)。
22. shell 写的内容未知:`cp x.bak x` 还原、`cat a b > c`(已做)之外,`cp` 的源内容已知时目标也已知(现在只记 wderived 内容未知);
    0723 EntryAbility 20 版未知大半是 .bak 还原。
23. 「修复轮没动的文件」GUIDE 加了全池查提到,没重跑验证。
24. ~~pod730 HomePage「实录外修改」里原始组还原的那处 Base-6c 的 bash 写~~ → 是脚本里自定义的批量替换帮助函数
    `def rep(p, pairs): 读→循环 replace→写` 再 `rep('x.ets', [(old, new)])`;按形状识别、每次调用解成 edit(bb985a7)。
25. 坐标带绝对时间戳:评委反复信原始组的「UTC 秒级时间戳 + old/new 原文」;(#n@L行) 旁边加时刻,diff 里给 old/new 原文互证。
26. 再找带修复阶段的会话(migbot-server 导出)验证返修链在 0723 之外的表现。
27. 调查覆盖(§4.14)vendor 到 migbot-server;原始转录组的跑没有节点坐标,只能按它引用的 jsonl 行反查到动作再落树,还没做。
28. 版本带「解法」标签(工具写 / heredoc 全文 / ast 读改写 / 重放 / 推断);对已知内容重放 sed / replace / re.sub 立版本;
    「实录外修改」的叶子带窗口内的命令号(§4.15)。
29. 调查树按缺陷分组:报告环的【A】【B】【C】标签进 probe,面板按缺陷切换,只留那条链红。
16. 判据 / 约束溯源:origin(q) 或 search 不带 agent 只查文件内容(spec / 技能 / ledger),回答「这句话最早出自哪」;
    派发词的来源分解(模板固定话术 vs 现写)。
17. decision(id) 视图:登记 / 状态 / 候选 / 引用者 / 改判 / 解锁时刻一次给全。
18. 再跑一次同四根(或全 19 根)看盲评是否从「更信原始 4:0」翻过来 —— 这次要按环评。
12. 未入账的:hook / system 记录(stop_hook_summary 241 条)、queue-operation;cp / mv 血缘。
13. 全 19 根再跑一次新工具,和 §4.8 横比(用户定)。
7. 同步 server 的 vendor(线上链数会变);技能文档是否保留,看实验。

## 8. 文件索引

- `docs/proposals/2026-09-08-evidence-contracts.md`：接手修复的证据契约与机械验收；条件读写、候选屏障、只读脚本历史、引用及扫描缺口。不是新一轮模型质量结论。
- `docs/experiments/README.md`:实验产物说明。
- `docs/experiments/2026-09-07-four-roots-after-optim/`:五步优化后四根验收 —— 新工具报告、实发提示词、metrics、盲评、
  各步在 0723 上的度量脚本(假 v1 / 幽灵路径 / 外部指针 / 覆盖对账 / 体量 / search 探针)。
- `docs/experiments/2026-09-06-0723-19roots/`:全 19 根两组对照 —— 两组模板、38 份实发提示词、38 份报告、逐根 metrics、盲评 JSON、解剖脚本;`hinted-invalid/` 是作废的第一轮。
- `docs/experiments/2026-09-04-diceroller-run-level/`:两组 prompt、两份报告、评委 JSON、覆盖率与逐版清单、harness 脚本、链的状态快照。
- `docs/experiments/2026-09-03-per-chain/`:按链实验的提示词模板与评委 JSON。
- `docs/skills/migloop-investigate/SKILL.md`:run 级调查技能(未启用)。
- `docs/design.md`、`docs/development.md`:工具本身的设计与开发指南。
- 上游历史:hmigbot 仓 `feat/insight-filestory@1cc3faa4`(冻结);server 仓 `src/vendor/migloop`。
