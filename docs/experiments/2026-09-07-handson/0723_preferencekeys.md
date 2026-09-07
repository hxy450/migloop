# 0723 · PreferenceKeys.ets 返修链亲手调查

SID ff019d8a(会话 9b3105a2) · 文件 `entry/src/main/ets/preferences/PreferenceKeys.ets` · 工具调用 20 次

---

## 第一段:链报告

被修的代码(链的起点):`PreferenceKeys.ets@v2`,主会话·9b3105a2 v243 于 T+38:57 纯新增 9 行
(`diff(PreferenceKeys.ets, v=2)`):

```
static readonly KEY_ANDROID_ID: string = 'android_id';
// D-010:HarmonyOS 无 Settings.Secure.ANDROID_ID 等价 API;Base-3 活体打靶实证后端只校验
// 非空 + 16 位十六进制格式。故生成一个稳定持久的 16-hex 值充当之。测试解锁,最终方案待后端敲定。
```

往回追:

**环 1 — 修复方为什么要加这个键**
谁:主会话·9b3105a2 v243(阶段 arkts-visual-verify)。
凭什么:用户指令 `/arkts-visual-verify 请修复下当前的登录问题`(#2416@L5146);随后 grep 到
`F013Service.ets@v15:181`(#2411@L5130),自述 "`F003Repository.ets:385` 调
`setPrivacyInfo(operators, '', '')`,第二个参数 androidId 传空串 → 后端 NOT NULL 列违约 → 游客注册
失败 → 拿不到 token → 登录全链阻塞"(`action(#2423)` 全文)。解法是复用 `DevicePrefs.getOrCreateMarkId()`
的持久化随机 ID 模式(读 `DevicePrefs.ets@v1` 15-64 行,#2431@L5180),照 `KEY_MARK_ID` 旁新增一个键
(读 `PreferenceKeys.ets@v1` 119-136 行,#2437@L5190)。
判定:**传递**(照上游事实与用户指令做的)。

**环 2 — 空串是谁写的、凭什么**
谁:`slice2-auth` v2,写 `F003Repository.ets@v1`,T+24:06(#20093@L193)。
凭什么:它在同一次写入里就地留了完整理由(`file(F003Repository.ets, v=1, start=338)` 第 341-348 行):

```
| Settings.Secure.ANDROID_ID | 无等价 API,后端 USER_INFO.ANDROID_ID 是 NOT NULL 列 | 见 P-BASE3-003 |
androidId 的取值方案是 D-010 后端阻塞项,唯一 canonical 登记点在 network/AppFormInfoManager.ets 的
P-BASE3-003(联调时与后端敲定后由该处注入)。本方法按现状传空串 —— 与「不调用本方法」时字段的取值
完全一致,不在此处编造设备标识,也不因为它阻塞而放弃另外两个可采集字段。
```

判定:**传递**。它没有自作主张,把球明确回踢到已登记的 canonical 点。

**环 3 — canonical 登记点 P-BASE3-003 是谁立的**
谁:`base3-network` v6,写 `AppFormInfoManager.ets@v1` 第 157 行 `// FWD-REF: P-BASE3-003
resolve_by=Slice 2 Step 3c`,T+21:51(#3453@L169)。
凭什么:派发词与收件(`search(q=D-010, agent=base3-network, v=6)`)逐字命令它这么做:

```
D-010 androidId:后端 USER_INFO.ANDROID_ID 是 NOT NULL 列,HarmonyOS 无等价 API。照常留字段与传参
路径,取值来源标 // FWD-REF 待 F003 联调定(不要臆造一个 UUID 就当解决了——那会让问题在联调时才暴露)。
```

它同一窗口内读到 `AppFormInfo.ets@v3` 第 32/84 行、`base_01_handoff.md@v1` 第 118 行、
`feature-plan.md@v2` 第 12 行,三处口径一致(blocking_dep,骨架先产)。
判定:**传递**,且是被明令禁止自行解决。
补注:环 2 与环 3 曾互指(base3 说 resolve_by=Slice 2,slice2 说 canonical 点在 base3 的文件里)。这个环在
T+24:47 被 `group1-closer` v30 打破 —— 它把 `AppFormInfoManager.ets@v7` 的标记改成
`resolve_by=backend-androidid-decision kind=platform-gap`(#13223@L199),定性为外部阻塞,不再指望端内解决。

**环 4 — D-010 是谁定的、定成了什么**
谁:主会话·9b3105a2 v65,写 `spec/decision-ledger.md@v1`,T+4:55(#838@L1471)。
内容(`file(spec/decision-ledger.md, v=1, start=163)` 第 163-176 行):

```
### D-010 · C17 · androidId 设备标识断点
事实(probe 实测,非推导):后端 USER_INFO.ANDROID_ID 是 NOT NULL 列。传空串触发
SQLIntegrityConstraintViolationException;传非空 16 位 hex 则 status=0 成功。imei / oaid 可空。
问题:HarmonyOS 没有任何 androidId 等价 API。
后果:不解决 → 游客注册失败 → 拿不到 token → 应用无法启动。
候选方案(须与后端敲定):
 1. 后端放开该列 NOT NULL 约束,允许鸿蒙端传空
 2. 鸿蒙端改用 OAID / AAID / UDID,后端按平台分别接收
 3. 后端为鸿蒙端新增独立标识列
```

表头一行记 `| D-010 | C17 | 阻塞,方案待定 | pending-approval |`(第 23 行)。
判定:**错**。同一段的「事实」行已经写明「传非空 16 位 hex 则 status=0 成功」,这正是 34 小时后修复方采用的
方案;但三条候选全部限定为后端侧改动,端侧自造稳定 16-hex 这一条**没有进候选清单**,整项挂 pending-approval。
好输入(probe 实证)在手,没有被转成可执行选项。

**环 5 — probe 事实从哪来(池外输入,追到头)**
谁:主会话·9b3105a2,喂 v39,T+1:06(#541@L929)。
凭什么:一次真实的后端活体打靶,响应原文
`{"status":-500,"toastMsg":"... SQLIntegrityConstraintViolationException: Column 'ANDROID_ID' cannot be null"}`。
随后写进 `spec/ref/backend-facts.md@v3`(#549)、`chain-auth.md@v5`(#553)、`api-inventory.md@v3`(#626,
明写「传非空 16 位 hex 成功」)、`feature-base.md@v1`(#687)、`F003-auth.md@v2`(#718)。
模板 `.claude/skills/a2h-spec/templates/backend-facts-template.md@v1` 第 41 行本来就有一格
`- DB NOT NULL：__（如 USER_INFO.ANDROID_ID）`(#38@L82,T+0:12)。
判定:**到头**(池外输入 = 真实后端响应 + 技能模板)。这一环没有错:事实采集完整且准确。

**环 6 — 本文件的生成方为什么没有这个键**
谁:`base5-preferences` v1,写 `PreferenceKeys.ets@v1`,T+22:36,320 行(#3874@L93)。
凭什么:文件头自述口径是「MMKV 键名的唯一事实源,键名值逐字复刻源码,任何情况下都不得改写」,并列了 5 处
源码键定义来源;它甚至显式拒收非 MMKV 键(`AI_PPT` 一条标「不是 MMKV 键 → 不迁入本层」)。
`android_id` 在 Android 侧从系统 API 取,源码 MMKV 里根本没有这个键,所以按口径不该出现。
它并非没看见 D-010:写 v1 之前(喂 v1,#3844@L69,T+22:29)它读到 `AppFormInfoManager.ets@v4` 第 148 行
`@param androidId 🔴 D-010 头号阻塞项`(`search(q=android_id, agent=base5-preferences)`,全生命周期 ≤v35
只此一条命中)。
判定:**缺**(相对当时口径,输入里没有「鸿蒙侧需要自建一个设备标识槽」这个需求;需求要到 D-010 被解锁才成立)。

**故障进入点:环 4。**
理由:环 5 把事实取全了(空串必失败 / 16-hex 必通),环 6、3、2、1 各自都忠实照上游做。唯独环 4 在同一份
文档里同时握着「16-hex 可通」的实证和一份只有后端选项的候选清单,把可端侧解锁的项判成 pending-approval。
这个判定沿 `decision-ledger@v1 → feature-plan@v2 / handoff@v1 / AppFormInfo@v3 → 派发词(不要臆造 UUID)
→ AppFormInfoManager@v1 P-BASE3-003 → F003Repository@v1 空串` 一路无损传递,直到真机登录失败才被推翻。
故障的形态是「决策未闭环」,而账本上每一环的执行都合规,所以生成期任何一环的自查都不会报错。

**修复侧多看到的:**
1. 运行现场。截图上的失败现象、编译通过后的真机登录链路,把抽象的 D-010 变成一个具体坐标
   `F003Repository.ets:385` 的空串实参(#2411 / #2423)。生成期只有静态推理。
2. 授权口径变了。用户一句「请修复下当前的登录问题」(#2416)把 pending-approval 的门打开,允许落一个标
   「测试解锁,最终方案待后端敲定」的临时值。生成期的派发词是反向纪律:「不要臆造一个 UUID 就当解决了」。
3. 时间差带来的现成资产。`DevicePrefs.ets@v1` 由 base5-preferences 于 **T+22:39** 创建
   (`file(DevicePrefs.ets, v=1)` 写者脊柱),而 base3-network 立 FWD-REF 是 **T+21:51**、slice2-auth 传空串是
   **T+24:06**。修复方能直接复用 `getOrCreateMarkId()` 的持久化随机 ID 模式(#2427 / #2431),这个模式在环 3
   做决定的时刻还不存在。
4. 事实本身**并没有**多。「16 位 hex 可通」T+1:06 就在账本上(#541、api-inventory@v3、decision-ledger@v1
   第 165 行),修复方 #2423 引用的就是同一条 Base-3 打靶结论。修复侧赢在现场、授权和可复用件,不在信息。

**无法确认:**
- `decision-ledger.md@v2` 标「实录外修改」,`AppFormInfoManager.ets@v8` 也是实录外修改(把 P-BASE3-003 的
  `kind=platform-gap` 改回 `forward-ref`)。谁改的、为什么,账本里没有。
- 环 4 那三条候选是不是在某次未记录的人机对话里被人为收窄的。主会话 v65 窗口里只有一句「产出
  decision-ledger.md(C4.8 grill #1 产出,D0 已定)」(#837@L1470),没有更细的推理留痕。
- `F013Service.ets` 各版本内容未知(`search(q=setPrivacyInfo, file=F013Service.ets)` 在 15 个版本里零命中,
  提示「内容未知的版本查不了」),我只能靠修复方 grep 的命中行号 181 认定它是调用侧,没能独立复核。
- 修复方是否在 v244/v245 补了 `DevicePrefs.getOrCreateAndroidId()` 的实现:从 diff 注释和 v246 改
  `F003Repository@v12`(#2450@L5221)可以推,但我没有逐版展开确认。

---

## 第二段:工具体验日志

### 逐次调用

| # | 调用 | 返回字数 | 评价 |
|---|---|---|---|
| 1 | `guide` | 2777 | 有用。两原子模型和标签表一次说清,后面所有标签(▲旧版 / 写前读 / 外部输入)都不用再猜 |
| 2 | `sessions path=PreferenceKeys.ets` | 574 | 有用。一行给全:生成方 / 修复方 / 两个时刻 / 纯新增 9 行。信息密度全场最高 |
| 3 | `file path=... v=2 content=1 diff=1 readers=1` | 23408 | **有误导**。我要 v2 的 9 行改动,它把 v1 的 320 行 creation diff 和全文一起倒出来,截断在 v1 的正文里,v2 的 diff 一个字没看到。白烧一次大调用 |
| 4 | `diff path=... v=2` | 639 | 有用。这才是我第 3 次想要的东西。`diff` 应该是默认入口,`file(diff=1)` 反而是陷阱 |
| 5 | `agent __main__ v=243 since=242` | 2831 | 有用。窗口切得准,读取集 + 自述 + 用户指令全在,一次就把修复方的推理复原了 |
| 6 | `search q=setPrivacyInfo file=F013Service.ets` | 120 | 没用但诚实。「内容未知的版本查不了」这句救了我,否则我会把零命中误读成否定证据 |
| 7 | `search q=androidId file=F003Repository.ets` | 972 | 有用。首次出现 v1 + 写者 + 命中行原文 + 「v2-v11 命中行未变」的压缩,一次定位到 slice2-auth |
| 8 | `file v=1 content=1 start=338 n=22 --from=` | 1705 | 有用。`start/n` 让我精确取到那段注释。`--from` 跳过脊柱是必需的,不然又是几千字 |
| 9 | `index query=AppFormInfo kind=ets` | 150 | 有用。我只知道类名不知道路径,一次补齐,还顺带给了版本数和读者数 |
| 10 | `search q=P-BASE3-003 file=AppFormInfoManager.ets` | 1367 | 最有用的一次。首立 / closer 改判 / 实录外修改 / 5 个读者,整个 FWD-REF 的一生在一屏里 |
| 11 | `search q=D-010 agent=base3-network v=6` | 1958 | 极有用。派发词、收件、读到的 spec 分组呈现,「凭什么」当场就答了。带起点的 search 是这套工具最强的一件 |
| 12 | `index query=decision kind=spec` | 297 | 有用。4 个文件里一眼认出 `spec/decision-ledger.md` 是 canonical 账本 |
| 13 | `search q=D-010 file=spec/decision-ledger.md` | 437 | 有用。给出第 163 行是详情段的锚点 |
| 14 | `agent __main__ v=65 since=63` | 4339 | **大半没用**。为看「写 decision-ledger 时手里有什么」,拿回 6 个批次共 30 多个安卓源码文件的读取行,和 D-010 无关的占九成;真正有价值的只有末尾两句自述 |
| 15 | `search q=ANDROID_ID agent=__main__ v=65` | 4932 | 极有用,虽然长。一次把池外 probe(#541)、5 份 spec 落点、模板占位符全线串起来,环 5 是靠它一次成型的 |
| 16 | `action id=__main__ seq=2423` | 523 | 有用。摘要里被截断的那句「16 位十六进制 a1b2c3d4e5f60718 注册成功」是全案的关键,只有展开才拿得到 |
| 17 | `search q=androidId file=spec/decision-ledger.md` | 424 | 有用。定位到第 163 行详情段 |
| 18 | `file spec/decision-ledger.md v=1 start=163 n=32` | 2096 | 决定性。三条候选方案里没有端侧自造这一条 —— 故障进入点就是在这一屏认定的 |
| 19 | `search q=android_id agent=base5-preferences` | 356 | 有用。全生命周期只有一条命中,把环 6 从「漏读」改判成「传递 + 缺」。零命中/单命中在这里是真证据 |
| 20 | `file DevicePrefs.ets v=1 --from=写者脊柱` | 381 | 有用。一个时间戳(T+22:39)撑起「修复侧多看到的」第 3 条 |

合计 20 次,约 5.0 万字返回,其中第 3、14 两次共 2.8 万字基本是废输出。

### 卡住的地方

1. **想看某一版改了什么,却拿到整个文件的历史**(#3)。`file(diff=1)` 的语义是「≤v 的全部写者及其 diff」,
   在 v2 上等于「v1 的 320 行 + v2 的 9 行」,而截断优先砍掉后者。绕法:改用 `diff(path, v)`。
2. **想知道「谁写了这个调用点的空串」,search 答不了**(#6)。`F013Service.ets` 15 个版本全部内容未知,
   按词查文件直接失效。绕法:换一个内容已知的邻居文件(`F003Repository.ets`)问同一个词,靠注释里
   的交叉引用跳过去。运气成分不小。
3. **想知道「主会话写 D-010 时凭什么」,窗口给的是噪声**(#14)。`agent(since=)` 按版本切窗口,但主会话
   一版之内能读几十个不相关文件。绕法:放弃窗口,改用 `search(q, agent, v=锚点)` 按词切,一次命中 17 条
   全是相关的。**结论:查主会话不要用 agent 窗口,要用带锚点的 search。** 这一条 guide 里没说。
4. **摘要截断在关键句上**(#15 的 `传非空 16 位 he…`)。要再花一次 `action` 或 `file(start=)` 才能补全。
5. **search 的匹配规则不透明**:我查 `android_id`,命中的是含 `androidId` 的行(#19)。这次帮了我,但我
   无法预判它做了多少归一化,也就无法把「零命中」当作强否定证据用。

### 多余的部分

- `file` 的完整正文复原:20 次里我只在 2 次真正需要正文,其余全靠 diff / search 命中行就够了,正文却是默认输出。
- `agent` 窗口里「读 N 个文件」的长清单(#14),每个都带范围标签和行号数组,我一个都没用。
- 「版本就近绑定(不确定)」在 #14 里出现了十几次,对结论没有任何影响,却占了大量字符。
- `search` 每条结果后缀的「→ blame(v=1) / agent(写者, since=…)」下一跳提示,同一格式重复十几遍;有用的
  是坐标本身,提示语可以只在开头说一次。

### 缺的部分

- **按行取 owner**。我从头到尾想问的是「`F003Repository.ets@v10` 第 385 行是谁写的」。`blame(changed=1)`
  只答「这一版改了哪些行」,没有 `blame(path, v, line=385)`。我是靠 search 的命中行号绕出来的。
- **决策项视图**。D-010 是这条链的真主角:它有登记点、状态(pending-approval)、候选清单、被哪些文件引用、
  被谁改判、在哪一刻解锁。这些散在 6 次调用里。一个 `decision(id=D-010)` 能把 #10 #11 #13 #17 #18 五次并成一次。
- **`diff` 支持范围**。`diff(path, v, around=385)` 或 `diff(path, v1, v2)`,现在只能整版对整版。
- **「这个事实第一次进入实录是什么时候」的正向查询**。我是反着从 decision-ledger 摸到 probe 的;若能问
  「`16 位 hex` 这个说法最早出现在哪」,环 5 一次就到位。
- **文件级的「内容已知/未知」标记**。`index` 给了版本数和读者数,不给可复原比例。若 `F013Service.ets` 在
  index 里就标「15 版全部内容未知」,我就不会浪费 #6。
- **时间轴对齐**。「A 做决定的时刻 B 还不存在」是本案最有说服力的一条,我是靠人肉比对四个 T+ 值得出的。
  一个 `timeline(paths=[...])` 会让这类论证变成一次调用。

### 该改的三条(按重要性)

1. **把「查主会话用带锚点的 search、不要用 agent 窗口」写进 guide,并让 `agent(since=)` 支持按词过滤读取集**
   (如 `agent(id, v, since, q=D-010)`)。这是本次唯一一次真正的方法论卡点,也是最大的一笔废 token(#14)。
2. **拆开 `file` 的三重身份,让 `diff(path, v)` 成为看改动的唯一入口。** `file(diff=1)` 在非首版上必然
   把首版的 creation diff 顶到前面并挤掉目标版,#3 一次烧掉 2.3 万字却零信息。至少应做到:截断时优先保留
   最新版的 diff,或对 `v>1` 默认只给该版。
3. **加决策项原子 `decision(id)`。** 这套账本已经有「版本文件」和「版本 agent」两个原子,而本案的因果主线
   跑在第三种东西上 —— 一个带状态机的决策项。它现在只能靠字符串 grep 拼出来,而它恰恰是故障进入点所在。
