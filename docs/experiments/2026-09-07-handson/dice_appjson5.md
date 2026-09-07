# 亲手调查:AppScope/app.json5(SID 49d451b1,DiceRoller,2026-09-03)

被修文件 `AppScope/app.json5`,4 版。修复 v4 只动了 3 个字段:

```
bundleName: com.example.myapplication → com.example.diceroller
vendor:     example                   → diceroller
icon:       $media:app_icon           → $media:layered_image
```
(diff AppScope/app.json5@v4)

这 3 行其实是**两条独立的链**,故障进入点不同,必须分开追。

---

## 第一段:链报告

### 版本脊柱(共同起点)

```
v1 ← 外部输入        T+1:00  内容未知(脚手架落地)
v2 ← 实录外修改      T+1:09  13 行,DevEco 模板默认值
v3 ← app-identity v1 T+1:09  只改了 versionCode 1000000→1 / versionName 1.0.0→1.0
v4 ← fix-identity v1 T+6:53  改 bundleName / vendor / icon
```
(file AppScope/app.json5 v=4;diff @v3;diff @v4)

`blame @v4 changed=1` 对这 3 行的回答是「归属未知(断点后) 3 行」——因为它们来自 v2 这个「实录外修改」。
v2 的时刻(15:35)与 app-identity 用 Read 工具读全文那一次(#4344@L49,15:35)是同一时刻,而它在 15:33
已经 `cat` 过同一个文件(#4320@L33);合理推断 **v2 不是真有人改,而是「内容第一次可见」被记成了一版**,
这 3 行的真实作者是脚手架模板本身。下面按这个理解走。

---

### 链 A —— bundleName / vendor(照规则不写)

**环 1 · 脚手架模板**(AppScope/app.json5@v1→v2,外部输入 / 实录外)
模板默认值 `com.example.myapplication` / `example` 进入工程。池外输入,无人可问。
**判定:缺**(输入里本来就是占位值)。

**环 2 · 技能定义**(`.claude/skills/arkts-app-identity/SKILL.md@v2`,action #4312@L23 原文 L30 / L132-139)
```
132  - bundleName: 从 applicationId 映射   ⚠️ 仅 scope=full
133  - vendor: 从 namespace 提取组织名     ⚠️ 仅 scope=full
135  > scope=dev-identity(a2h-execute Stage 0 调用):跳过 bundleName / vendor——
136  > 二者与签名证书 / AGC 应用上架强绑定,属部署期决策(迁移 ledger C-类目,对应 D-009)。
```
同一条规则在 `.claude/skills/a2h-execute/references/stage-0-resources.md@v1` L52 又抄了一遍
(search q=D-009 agent=主会话·81e0a463 v=32,命中 #2193@L914)。

这条规则有两个支撑,在本工程都不成立:
- 「与签名证书 / AGC 强绑定」:ledger C13 记的是 **signingConfigs 为空(debug 默认签名)、无 AGC**
  (修复方派发词 #521@L96 引用)。前提不存在。
- 「对应 D-009」:`search q=D-009 file=spec/decision-ledger.md` 在 6 版的**已知内容**里零命中。
  这是一条悬空引用 —— 技能拿一个本工程 ledger 里没有的编号当权威。

**判定:错**。规则本身是「有好的输入(applicationId 就在手边)却规定不许用」,而且它给的理由未按工程实际校验。

**环 3 · 主会话·81e0a463 v28→v32**(派发,#2238@L1026)
读到 stage-0-resources.md@v1 L52(#2193@L914)后,把约束原样搬进派发词:
> 硬边界:**不碰 bundleName / vendor**(部署期 D-009)

**判定:传递**。一字未改,连编号一起搬。

**环 4 · app-identity v1**(id=agent-a39c5351955d3cd6b,Stage 0b 应用身份落地,a2h-execute)
它**手里有正确值**:读 Android `app/build.gradle` 时看见 `applicationId "com.example.diceroller"`
(search q=applicationId agent=app-identity v=1 → #4327@L39),并在思考里写下:
> `- applicationId: com.example.diceroller (only for report; not written per dev-identity)`(#4336@L43)

然后只写了 versionCode / versionName(diff @v3)。
**判定:传递**。不是漏读、不是转换错 —— 是照硬边界主动弃用了正确值,且在记录里说明了。

**环 5 · fix-identity v1**(id=agent-a87804892da9cfc8b,Fix app.json5 template identity,ecat-refine)
写 v4(#1002@L49)。它的派发词(主会话·2f01bcdc @v4,#521@L96)给了两样生成期没有的东西,见下节。

**链 A 故障进入点:环 2(技能定义)**。
理由:环 3、环 4 都是忠实传递,链上唯一一次「有输入而选择不用」的判断写死在技能文件里;
而这条规则的两个依据(签名/AGC 绑定、ledger D-009)在本工程一个不成立、一个查无此条。
链追到技能定义即到叶子(技能文件是池外输入,再往上没有账本边)。

---

### 链 B —— icon(有输入没用)

**环 1'· 技能定义**(同一份 SKILL.md@v2,#4312 原文)
dev-identity **明确包含图标**:
```
30  scope: dev-identity(仅 dev 安全字段 app_name / versionName / versionCode / 图标,跳过 bundleName / vendor)
130  - icon: "$media:layered_image" (不变)
145  - foreground.png → AppScope/resources/base/media/foreground.png
146  - background.png → AppScope/resources/base/media/background.png
150  9. 生成/验证 layered_image.json
```
**判定:传递**(规则本身是对的)。

**环 2'· 主会话·81e0a463 派发**(#2238@L1026):「目标:app_name … / versionName / versionCode、**图标资源**」。
**判定:传递**(指令正确,图标在范围内)。

**环 3'· app-identity v1 —— 断在这里**
它亲眼看到 AppScope 侧图标资产是残缺的:
- #4320@L33 的 `find $P/AppScope -type f`:AppScope 下只有 `app.json5`、`element/string.json`、`media/app_icon.png`
- #4331@L41 的 `ls -la`:`AppScope/resources/base/media/` 只有 `app_icon.png`(68 字节);
  `entry/src/main/resources/base/media/` 才有 `background.png / foreground.png / layered_image.json`
- 同一次调用里 `cat` 了 entry 的 `layered_image.json`(合法的 layered-image 格式)

它却用 ledger D-003 把整个图标项 skip 掉(读 decision-ledger.md@v2 [62-100行],#4338@L45)。
D-003 原文(file spec/decision-ledger.md v=2,L87-95):
> D-003 无死码裁决需求;launcher 图标走 skip-list …
> **依据**:图标是 Android adaptive-icon/webp 体系,无行为语义,仅视觉资产;**脚手架已提供合规默认图标**

D-003 说的是「不迁 Android 的图标美术资产」。app-identity 把它扩成了「脚手架图标一律不动」,
于是 `icon` 停在 `$media:app_icon`,AppScope 三件资产也没补。它的思考(#4336@L43)写的是
「脚手架图标已齐且 layered_image.json 合法」—— 而它看的是 **entry 作用域**的那份,
app.json5 是 **AppScope 作用域**,引用必须在 AppScope 资源内可解析。作用域被混了。

**判定:错**。技能第 6/8/9 步 + 现场两次 ls 都是好的输入,没用上。

**环 4'· fix-identity v1** 用**同一条 D-003** 得出相反结论(#994@L40):
> D-003 确认:图标沿用脚手架资产、不迁 Android 图标组——与本次「复制工程内已有脚手架三件套到 AppScope」一致

先 `cp` 了 background/foreground/layered_image.json 到 AppScope(#999@L45,md5 逐一核对),
再把 icon 切到 `$media:layered_image`(#1002@L49)。

**链 B 故障进入点:环 3'(app-identity 自身)**。同一份 ledger 文本、同一个技能,两方结论相反,
差别不在输入而在解读:生成方把「不迁 Android 图标」误读成「不整理脚手架图标」。

---

### 修复侧比生成侧多看到的(三样,都有坐标)

1. **ECAT Discriminator 的 work list**(主会话·2f01bcdc 的开场指令,action #468@L3)
   第 10/11/12/14/15 条逐条点名 app.json5:
   `bundleName is template default: 'com.example.myapplication'` /
   `vendor is template default: 'example'` / `layered_image.json missing in AppScope media` /
   `foreground.png not found in AppScope media` / `background.png not found`。
   这是一个**静态检查器**的输出,生成期(T+1:09)根本不存在 —— ECAT 循环在 T+6:44 才起。

2. **`intermediate/agent_bundle.v1.json`**(file agent_bundle.v1.json v=1)
   外部输入,**首次出现在 T+2:34**,比生成写 v3 的 T+1:09 晚 1 小时 25 分。
   主会话·2f01bcdc 在 #510@L75 grep 到 `harmony_bundle_name: "com.example.diceroller"`(165 行 / 276 行),
   #516@L82 判定「流水线意图 bundle 名已定」,写进派发词(#521@L96)。
   生成侧不可能读到它 —— 那时文件还没进池子。

3. **对 D-009 前提的反查**:修复派发词把 ledger C13(signingConfigs 空、无 AGC)拿出来,
   直接推翻「改 bundleName 会致签名/AGC 不一致」这个技能理由(#521@L96)。
   生成侧从未质疑该前提(#4336@L43 只是照办)。

注:`sessions` 给的那条「修复侧多看到的: spec/decision-ledger.md ← 主会话·1d2ef418 写(#42)」**是错的**,见工具日志。

---

### 顺带发现:修复引入的新偏差(vendor)

技能的映射规则(#4312 原文 L74-75):
```
74  namespace / applicationId 的组织名 → vendor
75    规则: 提取第二段 (com.example.app → example)
```
`com.example.diceroller` 的第二段就是 `example` —— **按技能规则,正确值与模板默认值同形**。
检查器只做形状匹配(「vendor is template default: 'example'」),派发词据此下令「不得保留 `example`」,
fix-identity 写成了 `diceroller`(diff @v4)。这是修复侧为满足检查器而偏离技能规则。
派发词本身说过「skill 规则与本 prompt 冲突时以 skill 为准」,这里没照做。
**判定:错(修复侧)**;但最终哪个值对要看部署期,账本里无证据,归入无法确认。

---

### 无法确认

- **v2「实录外修改」到底是不是真改动**。我的判断(读出来的幽灵版本)是靠时刻对齐 + #4320 的 cat 推出来的,
  工具没有「这一版是被写出来的还是被读出来的」这个字段;因此 blame 的「归属未知 3 行」我按「脚手架模板」处理。
- **D-009 是否真的不存在**。`search q=D-009 file=spec/decision-ledger.md` 的否定只覆盖「已知内容的版本」,
  6 版里有几版内容未知、是哪几版,工具没说。否定证据强度要打折。
- **vendor 最终该填什么**。部署期没在这条实录里。
- **`$media:app_icon` 原本是否会导致构建失败**。AppScope media 里 `app_icon.png` 存在,引用可解析;
  work list 第 12/14/15 条是按技能期望形状报的,不是编译错(该轮「Compile errors: (none)」,#468@L3)。
  也就是说链 B 修的是规范符合性,不一定是真缺陷。

---

## 第二段:工具体验日志

### 逐次调用(20 次)

| # | 调用 | 返回字数 | 评价 |
|---|------|---------|------|
| 1 | `guide` | 2777 | 有用。标签语义(▲旧版 / 写前读 / 实录外修改)后面全用上了 |
| 2 | `sessions path=app.json5` | 808 | 有用又误导。一步拿到生成/修复双方 id + 跨会话关系;但「修复侧多看到的」那条是错的 |
| 3 | `diff path=… v=4` | 361 | 有用。三行改动,零废话 |
| 4 | `blame v=4 changed=1` | 350 | 半误导。3 行全报「归属未知(断点后)」,真答案(脚手架模板)它其实推得出来 |
| 5 | `file v=4 content=1 readers=1` | 1215 | 有用。版本脊柱暴露了 v2 这个关键结构 |
| 6 | `diff v=3` | 202 | 有用。一眼看出生成方只改了版本号 —— 整个调查的转折点 |
| 7 | `file v=2 content=1 readers=1` | 845 | 有用。模板默认值原文 |
| 8 | `agent id=app-identity v=1` | 6967 | **最有用**。派发词全文里的「硬边界」直接定案。但 1/3 是噪声(见下) |
| 9 | `search q=D-009 file=spec/decision-ledger.md` | 89 | 有用。89 字的否定证据,性价比最高的一次 |
| 10 | `action app-identity 4312` | 7321 | **决定性**。技能定义原文 L132-139,链 A 的叶子 |
| 11 | `action app-identity 4331` | 3858 | **决定性**。现场 ls 证明它看见 AppScope media 残缺 → 链 B 定性为「错」而非「缺」 |
| 12 | `search q=D-009 agent=__main__:81e0a463 v=32` | 841 | **决定性**。一步从派发词跨到 stage-0-resources.md@v1 L52 |
| 13 | `file spec/decision-ledger.md v=2 content=1 readers=1 start=84 n=18` | 3099 | 有用。D-003 原文;readers 列表顺手证伪了 #2 的结论 |
| 14 | `action fix-identity 1001` | 162 | **没用**。想要的是那段 4249 字收尾汇报,展开出来是一句 162 字的 say |
| 15 | `agent __main__:2f01bcdc v=4 since=3` | 377 | **没用**。窗口只剩一条「派发 fix-identity」,派发词全文没给(得走 `agent id=fix-identity` 才有) |
| 16 | `search q=harmony_bundle_name agent=__main__:2f01bcdc v=4` | 1292 | **决定性**。修复侧独有输入的出处 |
| 17 | `file agent_bundle.v1.json v=1 readers=1` | 777 | 有用。证明它 T+2:34 才进池 → 生成侧不可能读到。但 readers 里没有 2f01bcdc,与 #16 打架 |
| 18 | `action app-identity 4320` | 3857 | 半有用。佐证 v2 是幽灵版本;输出恰好截断在我要的 `cat app.json5` 之前 |
| 19 | `agent __main__:2f01bcdc v=1` | 3522 | 有用。ECAT 起点 + 修复侧读取集 |
| 20 | `action __main__:2f01bcdc 468` | 6771 | 有用。work list 原文;但前 9 条 placeholder 与本链无关,占了一半篇幅 |

合计约 45000 字返回,其中真正进结论的大概 12000 字。

### 卡住的地方

1. **「v2 实录外修改是谁干的」问不出来。** blame 直接给「断点后归属未知」,file 给「unknown」。
   我的绕法:把 v2 的时刻(15:35)和 app-identity 那次 Read(#4344,15:35)对齐,再用 `action 4320`
   看 15:33 的 `cat` —— 推断 v2 是「内容首次可见」造出来的版本,不是真改动。这是我自己拼的,工具没背书。
   代价是 2 次调用 + 一个只能写进「无法确认」的结论。

2. **拿不到 agent 的收尾汇报全文。** `agent id=fix-identity` 的摘要写着「收尾输出 … (截断,共 4249 字)」
   并标了坐标 (#1001@L48),按提示 `action(id, 1001)` 展开,得到的是同一时刻那句 162 字的 `说`。
   里面本该有「vendor/icon 最终取值及依据」和自检五步输出 —— 我没绕成,只能靠派发词 + 思考摘要反推,
   所以 vendor 那条只能定到「偏离技能规则」,拿不到修复方自己的说法。

3. **「修复侧多看到的」答歪了。** `sessions` 说是 `spec/decision-ledger.md ← 主会话·1d2ef418 写(#42)`。
   两处都不对:(a) 生成侧的 app-identity 也读了**同一版** decision-ledger.md@v2,三个行段
   (#4324@L37 1-60行、#4338@L45 62-100行 / 125-140行),这在 `file spec/decision-ledger.md v=2 readers=1`
   的读者表里白纸黑字 —— 它不是差集;(b) 标的写者 1d2ef418 这个会话在 T+7:32 才碰到 app.json5(file @v4 读者表),
   比修复(T+6:53)晚 39 分钟,而 fix-identity 读的 v2 是主会话·81e0a463 v27 写的(#2178@L870)。
   **一个晚 39 分钟发生的写,被说成了修复的依据。**
   我的绕法:自己用 `file(readers=1)` 反查读者表证伪,再用两次 search 把真差集
   (agent_bundle.v1.json + ECAT work list)挖出来 —— 多花了 4 次调用。

4. **技能约束的来源只能靠撞。** 我想问「『不碰 bundleName』这句话最早出自哪」,没有直查入口。
   是碰运气用 `search q=D-009 agent=主会话` 才撞到 stage-0-resources.md@v1 L52。
   如果这条约束没有 D-009 这种可搜的编号,我就找不到它了。

5. **readers 表和 search 对不上。** `agent_bundle.v1.json@v1` 的读者表只列了主会话·81e0a463 的 3 次,
   但 `search` 明确显示主会话·2f01bcdc 在 #510@L75 grep 到了它的 165/276 行(标签「命令输出推出」)。
   两个入口对同一件事给了不同答案,我不知道该信哪个,只好两个都写进报告并注明。

### 多余的部分

- **`agent` 视图里技能注入刷屏。** app-identity 和 fix-identity 各有 17 行
  `读 .claude/skills/*/SKILL.md@v1 [注入]` + 17 行 `注入技能: xxx`,同一件事说两遍,
  每个 agent 占 ~34 行、约 1/3 篇幅,而且这 17 个技能里只有 1 个(arkts-app-identity)与本链有关。
- **`file readers=1` 的读者流水。** decision-ledger.md@v2 列了 30 条,我用了 2 条。
  (不过正是这 30 条帮我证伪了 sessions,所以不是纯浪费,只是没有排序/过滤。)
- **`action` 输出里的绝对路径。** #4320 的 `find` 输出每行 110 字符的前缀完全一样,真信息只有末尾文件名;
  3857 字里估计 2500 字是重复路径,还因此被截断在我要的内容之前。
- **work list 前 9 条 placeholder 条目**(#468),与 app.json5 无关,占了 6771 字的一半。

### 缺的部分

- **版本来源要分档。** 现在 `external` / `实录外修改` 混在一起。至少要拆出第三档
  「读出来的(内容首次可见,非改动)」;并且 blame 遇到这种行应该直接答「脚手架/模板默认值(外部输入)」,
  而不是「归属未知」—— 后者把一个可知的事实说成了不可知。
- **约束溯源入口。** 想要 `origin(q="不碰 bundleName")` 这类查询:一句约束在派发词里出现,
  它是抄自哪个 skill / reference / ledger 条目,应该能一步反查,而不是靠编号碰运气。
- **agent 长文本的可展开坐标。** 摘要标了「截断,共 N 字」就必须给一个真能展开出这 N 字的动作号。
- **`sessions` 的「修复侧多看到的」要么算对要么别给。** 正确定义应是
  (修复方读取集 ∪ 修复方派发词引用的事实) − (生成方读取集 ∪ 生成方派发词),且要过滤掉晚于修复时刻的写。
  这是整个工具里唯一直接给结论的字段,现在它给了个反例。
- **派发词 diff。** 本链的真正开关是同一个 skill 被两次调用时 scope 不同
  (生成期 `scope=dev-identity` vs 修复期未传 scope,等价 full)。这一点要人肉比对两段派发词全文才看得出来,
  应该有「同一 skill 的多次调用及其参数差异」的直查。
- **`file(readers)` 与 `search` 的口径统一**,或至少在 readers 表里注明「本表不含命令输出推出的读」。

### 该改的三条(按重要性)

1. **修掉 `sessions` 的「修复侧多看到的」。**
   它是唯一一个直接给因果结论的字段,却在本链上给出了「生成方也读过的同一版文件」,
   并把依据标成一个**晚 39 分钟发生**的写。错的结论比没有结论更糟 —— 我差点顺着它去追 1d2ef418。
   改法:真差集 + 时间因果过滤 + 每项带坐标;算不出就留空。

2. **拆「实录外修改」,并给 blame 兜底。**
   本链 3 行被修的代码,blame 的回答是「归属未知」,而真实答案(脚手架模板默认值)其实推得出来。
   模板默认值是返修链里最常见的一类根因,它恰好落在工具的盲区里。
   把「读出来的(内容首次可见)」从「实录外修改」拆出来,blame 就能答「模板默认值,来自外部输入 v1」。

3. **长文本坐标要能展开 + 折叠技能注入噪声。**
   `action(#1001)` 展开不出摘要许诺的 4249 字收尾汇报,直接害我丢掉修复方对 vendor 取值的自述;
   同时每个 agent 视图里 34 行技能注入刷屏(相关的只有 1 个)。
   一个该给的没给,一堆不该给的每次都给 —— 这两件事合起来,让 `agent` 这个本来最有用的原子性价比掉了一半。
