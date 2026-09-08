# 结构化结论 → 调查树:一期闭环

日期:2026-09-08。基线 `dev/fixchain@40177ef`(Codex 的证据契约)。交接说明:`_migloop-handoff/2026-09-08-investigation-ui.md`。
本批只做:模型输出结构化结论 → 严格解析 → 核回账本 → 现有 fixchain 调查树按缺陷与版本着色 → 点节点看原因与证据。
不做通用根因机检、不重跑付费实验、不改 Codex 的证据契约。

## 1. 结论块(模型输出)

散文链照旧写在前面(附录);报告末尾再附一个 ```yaml 围栏块。schema 与词表在 `mcp_server.GUIDE`「结构化结论」一节,
`verdict.validate` 严格校验(未知键、词表外的角色 / 关系 / 检查结果、缺版本号、重复键都拒绝):

```yaml
schema: migloop-verdict/1
ledger: atoms-2026-09-08:17:3f1c…            # 照抄 sessions 首行「账本身份:」
root: file:entry/src/main/ets/entryability/EntryAbility.ets@v3
defects:
  - id: A
    title: 窗口全屏与状态栏没按 spec 设
    repair: {before: file:entry/.../EntryAbility.ets@v3, after: file:entry/.../EntryAbility.ets@v4, evidence: ["#a711c5d09fb676814:12@L88"]}
    entry: [agent:agent-a349784d2663f1f0a@v2]
    boundary: spec 是池外输入,停在这里
    nodes:                                       # 展示顺序;相邻不代表因果
      - {node: file:spec/pages/P0001.md@v1, role: 正常, reason: 明确要求了沉浸式状态栏, evidence: ["file:spec/pages/P0001.md@v1"]}
      - {node: agent:agent-a349784d2663f1f0a@v2, role: 进入·错, reason: 读了 spec 却没调用 setWindowLayoutFullScreen, evidence: ["#a349784d2663f1f0a:9@L41"]}
      - {node: file:entry/.../EntryAbility.ets@v3, role: 带病传递, reason: 缺该调用的版本被修复方读到}
    edges:                                       # 可省;每条对应账本里的一条 写 / 读 / 派发 边
      - {from: agent:agent-a349784d2663f1f0a@v2, to: file:entry/.../EntryAbility.ets@v3, relation: 写}
```

查询本身也留记录:file / agent / action / blame / diff 都多了可选参数 `via`,模型每次填「我从哪个节点、凭哪一行来查它」(照抄坐标,
或 `sessions` / `search:<词>` / `task`);harness 原样记进 metrics 与转录,服务端解析成「声明边」并逐条和账本边对照(重合 / 不重合 /
跳 / 无法解析),页面画成蓝色虚线(不重合橙色),不改树的结构。`正常` 的 reason 只要一句话。

角色只有五个:正常 / 带病传递 / 进入·错 / 进入·缺 / 无法确认。修复锚点(`repair.before/after`)是定位信息,不是角色:
修复后的版本只挂「修复落点」金框,标成带病的会被判无效(diag),不染红。`boundary` 单独放,不拼进角色。

## 2. 核验(服务端,`src/migloop/verdict.py`)

模型主张与检查结果分字段,互不越级:

| 层 | 字段 | 取值 |
| --- | --- | --- |
| 节点主语 | `ok / diag` | 显式解析 `file:…@vN` / `agent:…@vK`(主会话 `__main__:<sid8>`,名字唯一也认);版本范围 1..n,v0 / 越界 / 缺版本 / 不在账本都无效,不拿证据节点顶替 |
| 证据 | `status` | 动作引用按 `atoms.resolve_ref`:ok / drifted / missing / untagged / ambiguous;节点坐标 ok / invalid;别的文字 unparsed。有效只证明位置可核 |
| 边 | `status / relation / note` | 按账本核 写(版本文件的写者 + 写者版本)/ 读(读记录、喂养版本、certain、dep、conditional_reads)/ 派发(parent + parent_ver):true / false / unknown(候选:就近绑定、条件读、词法沾边)/ not_checked(端点无效)。nodes 相邻项自动核一遍并标 `implicit`,核不出来标「未证实」 |
| 事实机检 | `checked` | 一期一律 `not_checked`;模型自带的 `checks[]` 原样展示 |
| 身份 | `identity` | `atoms.ledger_identity` = 代码版本常量 + 转录清单(标识 / 文件名 / 大小 / mtime)摘要;harness 存的身份与当前账本不一致就告警,不静默把旧 vN/#n 当现在的节点 |

标注键是 (缺陷, 节点种类, 节点身份, 版本):`roles[key] = [{defect, kind, v, role, reason, evidence, …}]`,同一节点在 A 下正常、
B 下进入错是两条记录;页面切换缺陷时按记录过滤,不先合并。

步骤层独立:`steps[i].ok`(失败调用不算查过)与 `steps[i].scope`(索引 / 正文 vN / 差分 / 归属 / 搜索窗口 / 原文 #n),
蓝框「查 #k」的悬停提示列出每一步的范围 —— `file(v3, content=false)` 显示为「索引 v3」,不等于看完 v3。

## 3. 载入与页面

- harness(`exp/run_probe.py`)每次跑完:抽块 → 校验 → 坏了就 `claude -p --resume <同会话>` 做**一次**修复重试(只让它重发块,
  `--max-turns 3`,`--no-repair` 可关);两次结果、修复费用、harness 自己算的账本身份都落在 `rep1/verdict.json`;
  `metrics.json` 多了 `verdict_ok / verdict_errors / repair / cost_usd_total / harness_identity`。
- 服务端 `probe.probe_payload`:先读 `verdict.json`(以当前 schema 再校验一遍),没有就从 `result.json` 正文抽块;
  没块 = `legacy: true`(旧散文报告仍按环正则解析,面板标 legacy,没有新式核验)。
- 页面入口不变:`/api/insight1/fixchain/<sid>?probe=<run 目录相对 MIGLOOP_RUNS>`,或面板里输入目录点「载入」。
- 树 = 账本边 + 步号,零推断(`probe._trajectory` → 页面 `probeBuildTrajectory`)。节点只有 agent@版本 / file@版本 两种:
  模型真的用 file / agent / action / blame / diff 落到的 + 结论块点名的(角色节点、repair 前后、edges 两端、证据里的坐标),
  每个出现一次。结构只用账本核成 true 的关系:写(agent@vK → file@vN)、读(file@vN → agent@vK)、派发(agent → agent)、
  前一版(同一文件相邻两个在场版本,标跳过几版);根 = 被修文件的最终版本(账本最后一版),生成与修复都在它上游(左)。
  一个节点只有一个布局父(层数最小的下游邻居,写 / 读 / 派发 优先于前一版),其余账本边照画不复制节点。
  模型的路线只有节点上的步号「查 #k」(按精确版本);「出现于 #j」= 那一步返回文本里含这个坐标,是事实标注,不画边 ——
  第一版曾按「第一次出现的那一步」挂父节点,那是推断,已撤。和链上任何节点都没有账本边的单独一列「查过 · 无账本直连」。
  「+N 未查」= 账本里这个节点还有几个上游邻居没被查,不展开;词法候选(⋯ 可能写)不画。没有 transcript.jsonl 的老 run 退回账本树。
  模型声明的来处(`via`)画成第二种线:蓝色虚线,和账本边重合的标 ✓,不重合的橙色标 ✗,从 sessions / search 跳过来的只在徽标上标「跳」;
  这是模型自己说的路线,不是推断,也不参与布局。
- 角色着色(进入·错 深红 + 描边;进入·缺 黄;带病传递 红;正常 绿;无法确认 灰虚线;修复落点 金框),
  节点上每条缺陷一个徽标(`A 进入·错` / `B 正常`),别的版本只挂灰标「A 判的是 v3」;两端都红的账本边画红线,
  一端是「可能写」候选的画红虚线。查过 / 未查桩 / 树外查询 / 按缺陷切换都保留。
- 抽屉:点文件或 agent,头部之后插「调查结论」块 —— 每条缺陷下的角色、原因、边界、证据行(✓/≈/✗ + 诊断;
  动作引用可展开原文、跳到 agent;节点坐标可打开)、核验状态(未机检 / 无效引用 N 条)。
- 面板:账本身份不匹配告警、schema 错误(原始块可看)、每条缺陷的修复前后 / 进入点 / 边界 / 节点(无效的带诊断)/
  边(✓ ? ✗ + 说明,隐式的标「相邻项,自动核」)、失败步骤标 ✗ 并带范围。

## 4. 验收对照(交接第五节)

| # | 要求 | 落点 |
| --- | --- | --- |
| 1 | 2 正常 / 3 进入 / 4-5 传播 / 6 修复落点全流程,修复前后不串色 | `test_payload_colors_by_defect_and_version`、`test_repair_after_cannot_be_marked_diseased`;页面 `probeRolesFor` 按版本匹配,`p-fixed` 不带 `p-chain` |
| 2 | A/B 共用节点角色不同,切换不串色;多版本不连坐 | 同上 A/B 用例(`agent-c@v1` 在 A 进入·错、B 正常);`other` 只挂灰标 |
| 3 | 无效主语、v0 / 越界、无标识 / 缺块号 / 伪造引用有诊断,不补成别的节点 | `test_nodes_resolve_with_version_range_and_invalid_subjects_stay_invalid`、`test_evidence_refs_keep_their_own_status` |
| 4 | YAML 相邻但账本无边不画实线;中间环可保持未知 | `test_edges_checked_against_ledger_not_adjacency`:相邻自动核标 implicit,核不出标「未证实」;树上只有账本边 |
| 5 | 失败查询 / 仅查索引 / 条件读不显示为成功读到具体证据 | `steps.ok / scope`;读边遇 certain=False / dep / conditional_reads 只给 unknown |
| 6 | 旧账本身份不匹配告警;历史报告仍可读 | `test_identity_mismatch_and_legacy_are_flagged` |
| 7 | 真实页面浏览器验证并留截图 | 见第 5 节 |
| 8 | 382/2 基线不回退,新增测试 | 全仓 **395 passed**(382 + 13 条 `tests/test_verdict.py`);`ruff` 触碰文件无新告警;`mypy` 5 个改动文件无错 |

## 5. 真实一跑:DiceRoller `49d451b1` · EntryAbility.ets

产物在 `docs/experiments/2026-09-08-verdict-ui/`(run 目录 `dice_yaml/chain02-EntryAbility.ets/rep1/`、harness 副本、截图)。
载入:`MIGLOOP_RUNS=docs/experiments/2026-09-08-verdict-ui python -m migloop 49d451b1 --serve --port 18651`,
打开 `/api/insight1/fixchain/49d451b1?probe=dice_yaml/chain02-EntryAbility.ets/rep1`(会话 `49d451b1` 在本机 `~/.claude/projects` 下)。

| 项 | 值 |
| --- | --- |
| 模型 / 模板 | claude-opus-5 · `prompt_template_chain_yaml.md` + `task_chain.md`(散文链 + yaml 块),`--max-turns 40` |
| 轮数 / 工具调用 / 工具返回字数 | 22 / 21 / 106,149 |
| 费用 / 墙钟 | $2.26 / 7.6 min |
| 结论块 | 第一次就通过 schema 校验,没有触发修复重试;`ledger` 字段与 harness 算的账本身份一致(`atoms-2026-09-08:80:9065b7a0…`) |
| 缺陷 | 2 条(A 生成期没有 UI 测试桥;B 全 app 无全局未捕获异常观察者),进入点都指到 `conv-page-0001 v2`(进入·缺) |
| 节点 | 12 个主语全部解析有效(文件 4、agent 8,含主会话 `__main__:81e0a463` / `2f01bcdc` / `257fed22`) |
| 证据 | 节点上 33 条 + 修复证据 6 条,全部 `ok`(位置可核;不等于原文支持 reason) |
| 显式边 | 8 条(写 3 / 读 2 / 派发 3)全部核成 true |
| 隐式边(相邻项自动核) | 8 条:候选 2、未证实 6 —— 模型的 nodes 顺序不是链序,页面标出来,不画实线 |
| 修复锚点 | A:v3 → v6;B:v7 → v10;两个修复后版本只挂「修复落点」,没有染红 |

页面验证(截图在 `screenshots/`):01 载入后文件根 · 02–03 以进入点 agent 为根,抽屉顶部「调查结论」块(A / B 两条,各自角色、原因、证据、核验状态)·
04 点证据「原文」展开那次 Write 的原始输入 · 05 树 1:1,A 下 `MainActivity.kt@v1` 绿(正常)· 06–07 根节点 `conv-page-0001 v2` 红 + 进入点描边 ·
08 切到缺陷 B,同一个 `MainActivity.kt@v1` 不再着色(它只在 A 下有角色)。控制台无报错。

验证中修掉的两个页面问题:以节点为根时抽屉不经 onNode,结论块没插进去(补 `drawerFor`);结论块 class 与既有版本行 `.vrow` 撞名导致布局叠字(改 `p-` 前缀)。

用户看第一版树后指出:同一个文件在每个父节点下各列一遍、一整列「⋯ 可能写 主会话·81e0a463」词法候选 —— 原因是树还是账本上游树,
probe 集合只按键不按版本留节点(结论有 `主会话·81e0a463@v90`,它的每个版本都算命中)。改成轨迹树后(截图 10)同一跑 19 个节点
(文件 9、agent 10)各出现一次:根 `EntryAbility.ets@v3`;`conv-page-0001 v2` 下挂 `MainActivity.kt@v1` / `SKILL.md@v1`(#14 看到);
`P0001_MainActivity.md` 下挂 `UI-T Step1 v1`(#16 看到);其余节点都是 #3 sessions 那一步带进来的(返修链摘要把修复方、主会话、文件版本
一次列全),挂根、虚线。`tests/test_trajectory.py` 4 条;全仓 399 passed。

用户再问:「你是不是在 invent heuristic?我们到底有没有记录模型的路线?」—— 没有。记录只有调用序列(每步落在哪个 agent@版本 / file@版本)
和每步返回文本;「模型因为第 j 步看到才走过去」转录里没有,「第一次出现」规则是推断。于是树改成账本边 + 步号(上面第 3 节的现口径),
根改成被修文件的最终版本 `EntryAbility.ets@v10`。同一跑 21 个节点(文件 11、agent 10)、26 条账本边、4 个无直连(截图 11):
`v10 ←写 fix-errobserver v3 ←派发 主会话·2f01bcdc v5`;`fix-errobserver v3 ←读 v7 ←前一版 v6 ←写 UI-T Step3 v4 ←{派发 主会话·81e0a463 v90,
读 test-case-template.md@v1, 读 P0001_MainActivity.md@v1 ←写 UI-T Step1 v1}`;`v6 ←前一版(跳过 2) v3 ←前一版 v2 ←写 conv-page-0001 v2 ←读 SKILL.md@v1`;
`MainActivity.kt@v1` 挂在主会话 v90 下(读),到 conv-page-0001 v2 的读边照画。无直连:主会话·257fed22 v6、2f01bcdc v4 / v1、593d4e86 v23。

按用户要求把 GUIDE 的 `root` 改成「被修文件的最终版本」后重跑一次(`dice_yaml2/`,截图 12):21 轮 / 20 次调用 / 88,595 字工具返回 /
$1.70 / 5.6 min;结论块第一次就过校验,`root: …EntryAbility.ets@v10`,账本身份一致;2 条缺陷、14 个节点全部有效、显式边全部核成 true
(面板:已证实 11 / 候选 1 / 未证实 4,后两类都是相邻项自动核出来的)。这一跑模型把中间版本列成了角色:A 下 `EntryAbility.ets@v2 / v3` 带病传递,
B 下 `v1`(模板)进入·缺、`v3` 带病传递、`v7` 无法确认;进入点仍是 `conv-page-0001 v2`。树:15 个节点(文件 9、agent 6)、20 条账本边、
1 个不在根上下游锥里的节点(`主会话·2f01bcdc v1`,它读过 v7,那条读边照画):
`v10 ←写 fix-errobserver v3 ←{派发 主会话·2f01bcdc v5, 读 v7 ←前一版 v6 ←写 UI-T Step3 v4 ←{读 test-case-template.md@v1, 读 P0001_MainActivity.md@v1 ←写 UI-T Step1 v1,
读 v3 ←前一版 v2 ←{写 conv-page-0001 v2, 前一版 v1}}}`,`v6 ←前一版 v4` 另挂一支。控制台无报错。

模型这一跑的观察(不是机检结论):散文里 12 环,结构化块里没有一个「带病传递」节点 —— 它把中间的文件版本(v3 / v7)只放在 repair.before,
没有当传播节点列出;`notes` 里如实写了 v3 / v7 两版是 touch 强制重编、内容改动无法确认,以及 273 条提及只看了 48 条。

加 `via` 后再跑一次(`dice_via/`,截图 13):19 轮 / 18 次调用 / 85,885 字工具返回 / $1.63 / 5.0 min;结论块一次过校验、账本身份一致;13 个节点全部有效、25 条证据全部可核、11 条显式边全部核成 true。落节点的 12 步里 10 步带了 via:与账本边重合 4、不重合 0、从 sessions / search 跳过来 4、在同一文件另一版上继续看 2(标「同一节点」);模型写的 via 原文如 ile:…EntryAbility.ets@v8 写者 fix-errobserver、gent:agent-a27497…@v1 派发自 主会话·2f01bcdc @v5、search:errorManager → 指令 喂 v1 (#2f01bcdc:462@L3)。树 16 个节点(文件 9、agent 7)、22 条账本边、侧列 1 个(主会话·2f01bcdc v1)。这一跑模型点名的修复方版本是 fix-errobserver v1(写 v8),上一跑是 v3(写 v10),两者账本里都成立,树随节点集合变、边的含义不变。

## 6. 已知边界

- `checked` 一期全是 not_checked:边核只覆盖 写 / 读 / 派发 三种账本关系;reason 正文没有任何机检。
- 读边的 true 只说明「这个 agent 在喂养第 K 版之前确实读到了这一版」,不说明它读全了或用对了;seen / 行段没有进边核。
- 隐式边只核相邻两项;模型没列出的中间节点不会被自动补进子图(树上仍能看到账本实际路径)。
- 身份摘要按转录清单的 (标识, 文件名, 大小, mtime) 算,转录追加一行就变;同一份数据换机器 mtime 不同也会报不匹配 —— 这是保守方向。
- 修复重试只做一次、只重发块;两次都坏的 run 面板显示载入失败与原始块,主张不上树。
- 旧 run(没有 verdict.json)如果报告正文恰好有结论块也能载入,但身份显示「未记录」。
