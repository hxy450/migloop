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

## 5. 到目前为止的结论

**工具赢在**:行级归属、逐版本区间、明确标出哪些内容无法复原、跨段一致的口径、时间更快(轮次多但每轮快)。**输在**:

1. **账本没有 thinking / 正文**。「为什么这么写」这一层缺失,是唯一一处真正的信息缺口,也是最贵的一条。
2. **sessions 既是起点也成了围墙**。工具组拿到 4 个文件后只看这 4 个;原始组自己定范围,看到了模板、验证工具、ECAT 空转。工具替模型回答了「什么算修复」,模型就不再自己回答了。
3. **摘要被当成原文**。工具给的结构越完整,模型越不去读原文;工具的一处措辞(「外部输入 T+4:18」)直接误导了它。
4. **轮数就是钱**。原子粒度细,20 个版本调了 20 次 diff;原始组一条脚本扫全部。`file(path, diff=1)` 一次能给全部版本的 diff,模型不知道。

超集在能力上是超集,在行为上不是:工具改变了模型看什么、信什么。

## 6. 决策日志(用户裁定,按时间)

- 2026-09-01:宁重写不糊弄,两原子基座;树上每列必须是真原子。
- 2026-09-02:每一个工具调用的输出都应能展开,永远不丢信息;收集器漏了会让工具 obsolete,解析不出的不许静默。
- 2026-09-02:前序轮回合内的返修也算修复方;修复 / 生成的判定可以肆意改,底层两原子不动。
- 2026-09-03:除了主管线,其他都不算生成;execute 结束之后的都是修复;修复期新建的代码文件也算修复。
- 2026-09-04:分析要忠实呈现不去重;每条链先总结生成期问题再归并,不许「分桶抽代表段」;双盲两组都不给链坐标、不给范围定义、不给流程,只介绍工具;段是容器、问题是单位。
- 2026-09-06:工具主干迁到本仓 dev/fixchain;hmigbot 的 migbot.insight 冻结;server 只做 UI 展示。

## 7. 下一步(按优先级)

1. 账本收 assistant 的 thinking 与正文,挂到它喂养的那一版上;agent 工具里看得到「写这一版之前它说了什么」。
2. 「外部输入」的时刻写成「首次被读于」,不确定的说不确定。
3. ~~sessions 除了链,把修复期所有别的写入按目录分组列出~~ → 已做一半(§4.7):脚本碰过、方向不明的工程文件已列出;spec/docs/测试目录下的修复期写入仍未列(它们不是链根,按口径不算修复)。
4. 降轮数:diff 支持版本区间,sessions 直接带每段的改动摘要;让第一手动作就拿到原来要 20 轮的东西。
5. 输出里保留「每条问题覆盖哪几版」一个字段(机械校验完备性用),其余不约束。
6. 改完在 DiceRoller 上重跑工具组看按钮那条能否自己归对,再上 0723(19 条链)做找全的压力测试。
7. 同步 server 的 vendor(线上链数会变);技能文档是否保留,看实验。

## 8. 文件索引

- `docs/experiments/README.md`:实验产物说明。
- `docs/experiments/2026-09-04-diceroller-run-level/`:两组 prompt、两份报告、评委 JSON、覆盖率与逐版清单、harness 脚本、链的状态快照。
- `docs/experiments/2026-09-03-per-chain/`:按链实验的提示词模板与评委 JSON。
- `docs/skills/migloop-investigate/SKILL.md`:run 级调查技能(未启用)。
- `docs/design.md`、`docs/development.md`:工具本身的设计与开发指南。
- 上游历史:hmigbot 仓 `feat/insight-filestory@1cc3faa4`(冻结);server 仓 `src/vendor/migloop`。
