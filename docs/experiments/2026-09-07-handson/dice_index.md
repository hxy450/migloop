# DiceRoller · entry/src/main/ets/pages/Index.ets 返修链亲手调查

SID 49d451b1 · 生成方 conv-page-0001(agent-a349784d2663f1f0a) · 修复方 修 round-1 视觉差异(agent-a4874344c8fb6228d)

被修的两件事(diff@v5/v6/v7):
1. 按钮文案 `Button($r('app.string.roll'))` → `Button(this.rollLabel)`,新增 `@Local rollLabel='ROLL'` + `aboutToAppear()` 里 `getStringSync(...).toUpperCase()`
2. 按钮形态 → `.type(ButtonType.Normal) + .borderRadius(4) + .shadow({radius:6, offsetY:2, 26% 黑})`(原来无 type,落 ArkUI 默认 Capsule)

---

## 第一段:链报告

**环 1 · 修复动作** — 修 round-1 视觉差异(visual-fixer) 写 Index.ets@v5/v6/v7(#4479/#4481/#4483 @T+4:02)。
凭据:派发词点名两条 P1 ALIGN 单;写前读了 `spec/fix/round-1/ui/ALIGN_..._text_mismatch_roll-button-text.md@v3`(#4427)、
`..._component_mismatch_button-corner-radius.md@v3`(#4429)、sbs 双端拼图 `MainActivity.jpeg`(#4431 Read 图)、
结构 oracle `MainActivity.struct.json@v1`(#4432),再用 `button.d.ts`(#4448/#4452/#4459)与 `build.gradle(.kts)`(#4461)坐实
"ButtonType.Normal = no rounded corners by default"和"Material Components 1.4.0 → Widget.MaterialComponents.Button 默认值"。
**判定:传递**(照上游 ALIGN 单与图证做的,没有自己发明)。

**环 2 · 被替换的那一行** — `blame(Index.ets, v=7, changed=1)`:v6 第 115 行 `Button($r('app.string.roll'))`,
原作者 conv-page-0001@v3(#4234@L75 T+1:25)。
- 大小写:它**看见过**。`search(allCaps, agent=conv-page-0001, v=3)` 两条命中 —— 参考表
  `android-to-harmonyOS-ui-atomic-component-mapping-reference.md@v1:57`(`android:textAllCaps` → `.textCase()`),
  以及它自己的 think #4218:"Android Material Button details: textAllCaps=true → \"ROLL\". Hmm — spec AC14 says 按钮文案 \"Roll\"",
  同一段还有"That's the Android runtime appearance: purple button \"ROLL\" white text"(search AC14 命中 4 行)。
  它读过 `values/themes.xml@v1`,拿到 `Theme.MaterialComponents.DayNight.DarkActionBar`(#4181)。有输入、想到了、按 AC 字面判据放弃了。
  **判定:错**(有好的输入没用,被下游 spec 判据反压)。
- 圆角/投影:`search(Capsule, agent=conv-page-0001, v=3)` **0 命中**,`cornerRadius` 只在参考表第 338 行出现过
  (`app:cornerRadius` → `.borderRadius()`,而安卓 Button 并没写这个属性)。它整个生成过程没考虑过按钮形状,ArkUI 默认 Capsule 是静默落进来的。
  **判定:缺**(输入里本来就没有"Material Button 默认 4dp 圆角 + 2dp elevation"这条知识,安卓源码里也确实没有显式属性)。

**环 3 · 判据把生成方按住了** — `spec/baseline/features/F001-dice-roll.md@v6:80`:
`F001-AC14 按钮文案取自字符串资源 "Roll"…判:ui | 按钮显示 "Roll" 且源码引用字符串资源键 · 真:src:…/values/strings.xml:3`。
这条判据把**源串**当成了**渲染形态**。它出生即如此:`search(AC14, file=F001-dice-roll.md)` → 首次出现 v1,
写者 主会话·81e0a463 v7(#1933@L279 T+0:20),v2–v6 该行从未变过。而且这句判据被原样抄进了生成方的派发词
("按钮文案 $r('app.string.roll') 非硬编码(AC14)",search AC14 命中派发词与收件各 1 条)。
写这条时同一 agent 手里有主题信息:`search(MaterialComponents, agent=__main__:81e0a463, v=7)` —— 它在 v3(#1887@L181 T+0:13)
读过 `values/themes.xml`,think #1891 记下 "theme MaterialComponents DayNight DarkActionBar. Button text size 36sp",
并写进 `spec/baseline/ui-manifest.md@v1`(#1893)。但只从主题里提取了颜色与字号,没有展开 Material Button 的默认渲染
(allCaps / 小圆角 / elevation)。**判定:错 —— 故障进入点。**

**环 4 · 页面 spec 同样没有** — `search(textAllCaps, file=spec/baseline/ui/page_0001_MainActivity.md)` 与
`search(圆角, 同文件)` 在 6 个版本里**均 0 命中**。转换决策表只有"Button 36fp margin-top 16vp"。
**判定:缺**(与环 3 同源:静态 XML→spec 的转写流程里没有"主题默认值展开"这一步)。

**环 5 · 上游到此为止(停在这里的理由)** — 再往上是 Material Components 库自身的 `Widget.MaterialComponents.Button` 默认样式,
属于池外输入:账本里只有**被读过**的安卓文件,没有人读过 Material 库源;而能暴露差异的另一条路——安卓真机渲染基线——
直到 visual-verify Phase 2(ALIGN 单 v1 = 主会话 v59 批量生成 #2917@L2518 T+3:40)才存在,spec 期(T+0:20)与生成期(T+1:25)都还没有这个文件。

**检测环(旁支)** — ALIGN 单 v1 由主会话 v59 脚本批量生成(external),v2/v3 由 `visual-verify batch01 HMOS 采集判定`
写(#6019/#6092)。单子正文给了双向实证:"missing: Android 有文本元素「ROLL」/ extra: HMOS 多出「Roll」",
similarity 0.93、is_migration_bug=true、root_cause_hint 直接点名 allCaps。

### 故障进入点
**环 3**(F001-AC14,主会话·81e0a463 v7,#1933@L279)。理由:安卓主题信息在 T+0:13 就已在手并被记进 ui-manifest,
但 AC 的判据是从静态 XML 属性直译的("按钮显示 Roll"),把库默认渲染排除在验收之外。
生成方本已独立想到 allCaps(#4218),是这条判据把它按回了原样直排 —— 一条错判据既造成了缺陷,又抑制了唯一一次自纠机会。
形状那一半(环 2 下半 / 环 4)是纯粹的"缺":两侧 spec 都没有"Material Button 默认形态"这一维,ArkUI 默认 Capsule 静默生效。

### 修复侧比生成侧多看到的
1. **双端 sbs 拼图**(#4431 Read `sbs/round-1/trip_2_logged_in_vip/MainActivity.jpeg`)—— 生成期该文件不存在。这是唯一能同时暴露"ROLL vs Roll"和"矩形 vs 胶囊"的证据。
2. **结构 oracle** `MainActivity.struct.json@v1`(#4432,由 visual-verify batch01 写于 #5944)—— missing/extra 成对文本元素,把视觉差异变成可判定的离散事实。
3. **两份 ALIGN finding 正文**(#4427/#4429)—— 含 root_cause_hint 与"改渲染层不改资源串"的具体改法。
4. **`build.gradle` / `build.gradle.kts`**(#4461)—— 拿到 Material Components 1.4.0,才敢把 4dp 圆角 / 2dp elevation 当成规范默认值。生成方 ≤v3 的读取集里**没有** build 文件。
5. **ArkUI 接口探测**:`button.d.ts`(#4448 命中 12 行 / #4452 / #4459 120-175 行)确认 Button 无 `textCase`、`ButtonType.Normal` 无圆角;`@ohos.resourceManager.d.ts`(#4469)确认 `getStringSync` 可用。生成方零次探测 d.ts,所以即便想做大写也没有现成路径。
6. **更新的页面 spec**:修复方读 `page_0001_MainActivity.md@v6`,生成方读的是 `@v3`。
7. 派发词层面:修复方的派发词直接写明"Android 原版是 Material Button(textAllCaps=true 运行时显示 ROLL,小圆角矩形背景)";生成方的派发词写的是 AC14 的字面判据。同一个事实,两轮里以相反的方向被喂给模型。

### 无法确认
- 生成方**最终**放弃大写的那句话原文。think #4218 全长 98512 字,`action` 只返回前 ~6.7k,恰好截在决策之前;只能靠 `search` 命中的 4 行拼出它的取舍。它 v3 之后的收尾报告里是否记过这个 deviation,不在本次窗口内。
- ALIGN 单 v1 是脚本批量生成(external, #2917),脚本正文没展开;"为什么切成两条单、similarity 0.93 怎么算"属于 visual-verify skill 内部,不在这条链上。
- 生成方是否真的"读全"了 `themes.xml`:那批读全部标 `[范围未知]`,只知道它命中了 parent 那一行。
- sessions 提示的"方向不明"动作 #3360(T+5:51)已展开核实:是写 AC claims 的 python heredoc,`Index.ets` 只作为路径字面量出现(证据串 `IDX + ':58-67'`),**不是**对 Index.ets 的写。顺带确认 AC14 在收尾时被回填成"渲染 'ROLL' 与 Android textAllCaps 渲染层形态一致",即判据事后被改口径,但 F001 spec 正文那一行始终没改。

---

## 第二段:工具体验日志

### 逐次调用(26 次)

| # | 调用 | 返回字数 | 评价 |
|---|---|---|---|
| 1 | `guide` | 2777 | 有用。标签语义(▲旧版/写前读/外部输入)和"主会话必须带 since"两条是全程最值钱的说明。 |
| 2 | `sessions path=Index.ets` | 2980 | 有用。一口气给出链根、生成/修复方 id、修复方分段、"修复侧多看到的"。但它把 6 段修复方全列了,我只需要第一段。 |
| 3 | `diff path=… v=5` | 453 | 有用。 |
| 4 | `diff v=6` | 648 | 有用。 |
| 5 | `diff v=7` | 810 | 有用,核心改动在这。 |
| 6 | `blame v=7 changed=1` | 283 | 最高信噪比的一次:一行输出直接定死原作者与它的版本号。 |
| 7 | `agent 生成方 v=3` | 10302 | 决定性但过长。真正用到的是读取集 + 两条 think;派发词全文(~2500 字)只用到 AC14 那一行,占位极大。 |
| 8 | `search allCaps agent=生成方 v=3` | 778 | 决定性。一次调用把"错"和"缺"分开了。 |
| 9 | `search MaterialComponents agent=生成方 v=3` | 1713 | 有用。但读命中那条把三个绝对路径全打了一遍,一行 400 字。 |
| 10 | `action #4218` | 6766 | **有误导**。原文 98512 字,只回前 6.7k 且不说"我截在哪、还有多少",恰好截掉我要的决策段。看着像"全文",实际是开头。 |
| 11 | `search AC14 agent=生成方 v=3` | 1305 | 决定性。派发词/收件/读/想/写五个种类分组,一次看清判据怎么从 spec 传到派发词再传到代码注释。 |
| 12 | `search cornerRadius agent=生成方 v=3` | 458 | 有用(近似否定证据)。 |
| 13 | `file F001@v6 content start=76 n=10` | 2653 | 决定性。但为了 1 行判据要连带吃 8 行别的 AC + 完整写者脊柱。 |
| 14 | `agent 修复方 v=3` | 8427 | 决定性。修复侧读取集全在这。12 条"注入技能"各占一行、又在时间线里重复一遍,纯噪声。 |
| 15 | `search textCase agent=生成方 v=3` | 779 | 冗余,命中与 #8 完全相同(同一 think 同一行)。我提前不知道两个词会落在同一行。 |
| 16 | `file ALIGN…@v3`(无 content) | 939 | 有用。写者脊柱直接指出"v1 是脚本批量生成、v2/v3 才是 verifier 写的"。 |
| 17 | `file ALIGN…@v3 content=1 --from="## 内容"` | 4989 | 有用。`--from` 起效,省掉重复的脊柱。 |
| 18 | `search textAllCaps file=page spec` | 114 | 有用的否定证据,单价最低。 |
| 19 | `search Capsule agent=生成方 v=3` | 129 | 同上,而且返回自带"零命中只能证明什么"的免责说明,防我过度外推。 |
| 20 | `search 圆角 file=page spec` | 105 | 同上。 |
| 21 | `file …/android/…/MainActivity.png` | 86 | 没用。"账本里没有该文件"——图片类产物查不到,我想确认"安卓基线截图什么时候才存在"这条时间线,只能绕。 |
| 22 | `action #4431` | 315 | 有用。证明修复方确实 Read 了 sbs 图 —— 而 agent 时间线里这条只显示 `Read (#4431@L26)`,**没有文件名**。 |
| 23 | `search AC14 file=F001` | 389 | 有用。"首次出现 v1 + v2–v6 命中行未变"这个形状正是我想问的。 |
| 24 | `agent 主会话 v=7 since=6` | 1400 | 有用但窗口太窄:只有 2 条读,看不到 AC14 引用的 activity_main.xml/strings.xml 是哪次读的。 |
| 25 | `search MaterialComponents agent=主会话 v=7` | 1054 | 决定性。把"spec 作者早在 T+0:13 就拿到主题"钉死,才敢把环 3 判成"错"而不是"缺"。 |
| 26 | `action #3360` | 4064 | 有用。消解了 sessions 里那条"方向不明",顺带发现 AC14 收尾被回填改口径。 |

合计约 5.1 万字返回,其中我真正引用进报告的不到三分之一。

### 卡住的地方

1. **想要"生成方为什么放弃大写"的原话,拿不到。** `action #4218` 声明"共 98512 字"却只给前 6766 字,没有 `offset` / `tail` / 关键词定位。绕法:回头用 `search` 换三个词(allCaps / AC14 / textCase)去撞同一段 think,靠命中行拼出语义。三次调用换四行文本,而且永远不知道有没有漏掉后面更明确的一句"decision: keep Roll"。
2. **想问"安卓渲染基线什么时候才存在",查不到。** `file(…/android/…/MainActivity.png)` 说账本里没有;图片作为证据被读过(#4431 那张 sbs jpeg)却不立版本、在 agent 时间线里连文件名都不显示。绕法:用 ALIGN 单 v1 的创建时刻(T+3:40)当代理时间戳。
3. **想一次问清"生成方 vs 修复方读取集的差集",没有这个查询。** sessions 的"修复侧多看到的"只列了 4 个文件,而真正的差集里最关键的是 `build.gradle`(定 Material 版本)和 `button.d.ts`(定 ArkUI 默认形态)——这两个它没列。绕法:人肉对比两次 `agent` 调用的读取集,~1.9 万字里挑。
4. **主会话窗口的粒度不合手。** `since=v-1` 只回 1 个版本的动作,而 AC14 的证据横跨 v3(读主题)到 v7(写 spec)。我第一次 `since=6` 看到的东西不足以定性,只能改用 `search(agent=主会话, v=7)` 才拿到 v3 的那条读。想要 `since=3 v=7` 这种区间,得先猜到该猜哪一版。
5. **同义词命中重复,事前不可知。** #15 与 #8 完全同结果,白花一次。

### 多余的部分(返回了但我一行没用)

- `agent` 的"注入技能"清单(修复方 12 条、生成方 3 条),在时间线里与"读 SKILL.md"重复计两遍。
- `agent` 派发指令全文里的报告格式要求、占位规则、stub 处理规则(生成方那 2500 字里约 2000 字)。链上只用到"行为契约"两三行。
- `file` 每次都附的完整写者脊柱 + 读者数 + 方向不明清单;我只在 #16 真的需要脊柱。
- `search` 读命中里把同一次调用的三个绝对路径原样拼接(#9 那条一行 400 字)。
- `sessions` 里 v8–v26 那 5 段后续修复方及其"依据/修复侧多看到的"(a2h-build、placeholder flags 等),与本链无关。

### 缺的部分(想要但没有)

1. `action(id, n, from="关键词")` 或 `offset=` —— 长 think 的定位截取。现在是"给你前 6.7k,自己撞运气"。
2. `diff(path, v_from=4, v_to=7)` —— 一次看完一个修复方的整段改动。我拆成 3 次 diff。
3. `readset_diff(agent_a, va, agent_b, vb)` —— 直接输出"修复侧读了而生成侧没读"的文件清单。这是本任务里唯一真正要回答的问题,却完全靠人肉比。
4. 图片/二进制证据的一等公民地位:被 Read 的截图应当在时间线里显示路径(现在是裸 `Read (#4431)`),并且能 `file()` 查到它是谁在哪一步产出的。
5. `agent(id, since=a, until=b)` 的真区间窗口,以及"这一版引用的每条证据是哪一版读进来的"反查。
6. `search` 的 `context=N`:命中行前后各给 N 行。有了它,#10 那次 6766 字的失败展开根本不必发生。
7. 一个"判据溯源"视图:AC14 这一行在 spec / 派发词 / 代码注释 / 收尾 claims 四处的同一份文本,现在要靠我自己在四次调用里认出来是同一句。

### 该改的三条(按重要性)

1. **`action` 的长文本必须可定位**:加 `from=` / `offset=`,并在截断处显式打印"已截,剩余 X 字,用 offset=N 继续"。当前的静默前缀截断会让人误以为看到了全文 —— 这是本次唯一一次被工具**误导**的地方(#10),也是"无法确认"那一条的唯一成因。
2. **把"读取集差集"做成一等查询**:`sessions` 已经有"修复侧多看到的"这个概念,但它只覆盖"上游写者可追的 spec 文件",漏掉了真正解释修复方为什么更强的两类输入 —— 构建配置(`build.gradle` → 库版本 → 组件默认样式)与接口探测(`button.d.ts` → 平台默认形态)。建议直接输出两侧读取集的差集并按类型分组(源码/spec/配置/接口/截图)。
3. **`agent` 分层返回**:默认只给"版本时间线 + 读取集",派发词全文、注入技能、想/说流水挪到 `verbose=1`。生成方与修复方两次调用花了 1.9 万字,其中约 6 千字是我要的。同时给 `search` 加 `context=N`,让"先 search 定位、再 action 展开"这条推荐路径真的走得通。
