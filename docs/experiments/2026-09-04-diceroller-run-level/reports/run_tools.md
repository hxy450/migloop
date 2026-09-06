已查完。以下是结论。

---

## 每一处修复

> 时间轴锚点:T0 = 2026‑09‑03T14:26(a2h‑init);**execute 结束 = 16:46:29 = T+2:20**。下面 10 组改动全部发生在 T+4:02 之后,分属 `arkts-visual-verify`(T+4:02–5:28)与 `ecat-refine` iteration 0(T+6:50–6:54)两波。

### 1. Index.ets v4–v6 — Roll 按钮:大写文案 + Material 圆角 + 投影
- **改了什么**:新增 `@Local rollLabel: string='ROLL'` 与 `aboutToAppear()`(取 `app.string.roll` 再 `toUpperCase()`);`Button($r('app.string.roll'))` → `Button(this.rollLabel)`,追加 `.type(ButtonType.Normal)` `.borderRadius(4)` `.shadow({radius:6,color:'rgba(0,0,0,0.26)',offsetX:0,offsetY:2})`。
- **谁改的**:visual-fixer「修 round-1 视觉差异」`agent-a4874344c8fb6228d` v1–v3,T+4:02–4:03。
- **为什么要改**:verify 的 CHECK‑8 视觉相似度 0.93,round‑1 两条 P1 `ALIGNMENT_DIFF`(`ALIGN_PMainActivity_text_mismatch_roll-button-text` / `..._button-corner-radius`);sbs 双端图:左 Android「ROLL」+ 小圆角 + 淡投影,右 HMOS「Roll」+ ArkUI 默认 Capsule 无投影。
- **生成期为什么没做对**:**spec 漏写 + 转换错(读全了仍写错)**,两环叠加。
  - spec 环:`spec/baseline/ui/page_0001_MainActivity.md@v3`(主会话·81e0a463 v4/v12/v13 在 a2h-spec 阶段写,T+0:14–0:23)第 19 行只写「Button `@id/button`,`@string/roll`("Roll"),textSize 36sp,位于骰子图正下方 16dp」,第 27 行转换决策只有「`fontSize('36fp')`,文字 `$r('app.string.roll')`」——**全篇未提 textAllCaps、圆角、elevation**。
  - 转换环:conv-page-0001 自己读过 `values/themes.xml` 与 `values-night/themes.xml`(#2620,T+1:12),收尾报告里还写了 Button「`primary` 底 + `on_primary` 字(对齐 Material 填充按钮运行时形态)」,却只落了配色和 minWidth 88,没把 `Theme.MaterialComponents.DayNight.DarkActionBar` → `Widget.MaterialComponents.Button` 的默认形态(大写/4dp/2dp)换算过去。
- **证据**:`blame Index.ets@v6 changed=True` → 被替换行 `Button($r('app.string.roll'))` owner=`conv-page-0001@v3`;`diff Index.ets@v4/v5/v6`;visual-fixer 收尾「诊断(三层证据)」;page spec@v3:19,27。

### 2. Index.ets v7 — `class Dice` → `export class Dice`
- **改了什么**:一行,给内聚领域类加 `export`,并加注释「export 仅为 arkxtest 单测可见性放宽」。
- **谁改的**:**主会话·81e0a463 v77 直接写盘**,T+4:12(不是子 agent)。
- **为什么要改**:UT 用例 `F001_dice-roll.test.ets` 要 `import { Dice } from '../../../../main/ets/pages/Index'`,不 export 编译不过。
- **生成期为什么没做对**:**spec 没有可测性契约**。conv-page-0001 的派发词只给了「Dice 类内聚于 Index.ets,不抽独立 ViewModel 文件」(F001 服务层约定),没有任何「需被 ohosTest 导入」的要求;测试是 execute 之后才引入的,生成期无从知道。属编排顺序问题(测试设计晚于代码生成),不是转换错。
- **证据**:主会话·81e0a463 v77 窗口——写 Index.ets@v7 前读 `.claude/skills/arkts-ut-verifier/agents/step2-generate-agent.md@v1`(#2028);`diff Index.ets@v7`;retrospect 把「Dice export」列进 6 条待审批设计决策。

### 3. Index.ets v8–v10 — 注入 3 个 UI 测试锚 `.id()`
- **改了什么**:`.id('main_root')`(Navigation 根)、`.id('main_toolbar_title')`(标题 Text)、`.id('main_dice_placeholder')`(首屏占位 Column),各带一行注释。
- **谁改的**:`UI-T Step2 ID 注入` `agent-aa1ccf93d575837a2` v1–v3,T+4:42。
- **为什么要改**:arkts-ui-verifier 第三步的用例 selector 严格按 `ON.id` 优先级取 manifest 的 5 个 id;生成期只有 `imageView`/`button` 两个(Android `@id/*` 直迁),缺 3 个。
- **生成期为什么没做对**:**同 #2,生成链路里没有"可测 id"这一环**。conv-page-0001 的派发词/页面 spec 都没有 testable-id 契约,`testable-id-manifest.md` 是 T+4:42 才第一次存在。
- **证据**:`diff Index.ets@v8/v9/v10`;该 agent 收尾 `ID_NOT_INJECTED: ["imageView:109(既有,Android @id/imageView 直迁)","button:124(既有)"]`;其唯一驱动输入 `spec/test/ui-test/id-inject/P0001_MainActivity.md@v1` 生于 T+4:41。

### 4. EntryAbility.ets v4–v6 + 新建 entry/src/main/ets/test/TestDataSetup.ets — UI 测试桥
- **改了什么**:import `TestDataSetup`,加 `TEST_MODE_KEY/TARGET_PAGE_KEY/HOST_PAGE_NAME` 三常量,`onCreate` 末调 `consumeTestWant(want)`,新增 `onNewWant`,新增私有方法 `consumeTestWant`(want 参数 → AppStorage 桥键 + mock 注入 + 宿主自挂载特判);另新建 `TestDataSetup.ets`(12 行)。
- **谁改的**:`UI-T Step3 生成 P0001 测试` `agent-a711c5d09fb676814` v1–v4,T+4:50–4:51。
- **为什么要改**:UI 用例要靠 `__test_mode__`/`__target_page__` want 参数挂载被测页;`Index` 是 `@ComponentV2`,模板 §6.2 的 `@StorageLink+@Watch`(V1 装饰器)不可用,桥只能收敛到 ability 侧。
- **生成期为什么没做对**:**生成链路里没有测试宿主契约**(与 #2/#3 同根)。生成期的 EntryAbility 只有脚手架模板(v2,实录外写入)+ conv-page-0001 加的沉浸式四件套(v3);"@ComponentV2 下模板桥失效"这个约束是 Step1 设计阶段才发现的。
- **证据**:`file EntryAbility.ets diff=True` v4/v5/v6;该 agent 收尾 `SRC_FILES_MODIFIED: EntryAbility.ets(仅追加…沉浸式四件套/既有逻辑零触碰)`;`TestDataSetup.ets@v1` 写者 = UI-T Step3 v1 @T+4:50。

### 5. entry/oh-package.json5 v2 — 补 `@ohos/hypium: 1.0.21`
- **改了什么**:`"devDependencies": {}` → `{"@ohos/hypium": "1.0.21"}`。链型 = **template(模板原样留到修复期才改)**。
- **谁改的**:`UT Step3 编译跑测出报告` `agent-ac20d808e5bc6be60` v8,T+4:22。
- **为什么要改**:测试 HAP 要编译 arkxtest,缺依赖起不来。
- **生成期为什么没做对**:**execute 根本没产测试基础设施**——整棵 `entry/src/ohosTest/` 树(TestRunner/TestAbility/资源/module.json5)都是 T+4:18 之后才建的,该 agent 收尾原话:「第二步仅产用例;基础设施原状不可跑(Runner 无 Hypium 调用、TestAbility 抢跑且无 context 注入/无占位页/缺 color+icon+test_pages)」。脚手架模板发的是空 devDependencies,生成期无人碰它。
- **证据**:`file entry/oh-package.json5 diff=True`(v1 外部输入 T+4:18 → v2 T+4:22);该 agent 派发词「依赖:`oh-package.json5` 的 devDependencies 缺 `@ohos/hypium` 就加」;文件 v2「内容无法复原——edit 作用在未知状态上(盲写)」,仅 diff 可证。

### 6. AppScope/app.json5 v4 + AppScope/resources/base/media 三件套 — 应用身份与分层图标
- **改了什么**:`bundleName` `com.example.myapplication`→`com.example.diceroller`;`vendor` `example`→`diceroller`;`icon` `$media:app_icon`→`$media:layered_image`;并用 `cp` 从 entry 模块逐字节复制 `layered_image.json`+`foreground.png`+`background.png` 进 `AppScope/resources/base/media/`。
- **谁改的**:`agent-a87804892da9cfc8b`(账本名 fix-errobserver,实际派发词是 app 身份修复),v1,T+6:52。ECAT work list #10/#11/#12/#14/#15。
- **为什么要改**:ECAT 检测器判「bundleName/vendor 是模板默认」「AppScope media 缺分层图标三件」。
- **生成期为什么没做对**:**编排派发词按不存在的 ledger 条目设了硬边界 + 决策台账把图标划进 skip-list**,不是模型转换错。
  - 生成方 `app-identity` `agent-a39c5351955d3cd6b` v1 的派发词(主会话·81e0a463@v32)白纸黑字:「硬边界:**不碰 bundleName / vendor**(部署期 D-009)」;而它自己收尾就 fail loud 了:「**当前 ledger 尚无 D-009 正文条目**」。
  - 图标:它按 `spec/decision-ledger.md@v2` D‑003(approved,「launcher 图标资源组按 platform-glue 走 skip-list 不迁移」)跳过,并声称「已核验资产齐备」——但它列的 `layered_image.json / foreground / background` 是 **entry 模块**的,`AppScope` 作用域下只有 `app_icon.png`。这一步自检口径错了(AppScope 引用只能在 AppScope 资源内解析)。
  - 规范本身**当时就在手边**:`arkts-app-identity/SKILL.md@v2` 被 app-identity 全文读过(1‑222 行,#2702),第 45–49 行的输出清单里就有 AppScope 三件套,第 61/74 行给了 `applicationId→bundleName`、`vendor=第二段`;真值也在手边(`agent_bundle.v1.json:165 harmony_bundle_name=com.example.diceroller`、`build.gradle:10 applicationId=com.example.diceroller`)。
  - **而且生成期自己的门禁放行了**:主会话·81e0a463 终验 “PASS:…CHECK‑4 身份”,`BUNDLE: com.example.myapplication` 还被当既成事实写进了 UT Step3 的派发词。
- **证据**:`diff AppScope/app.json5@v4`;`file AppScope/app.json5` 脊柱(v3←app-identity v1 只改了 versionCode/versionName);app-identity 收尾第 5 条「未动字段」;fix 方收尾表 + 五步自检;`AppScope/resources/base/media/layered_image.json` 在 index 里显示「1 版 · 只被读过(外部输入)」= cp 落盘(该 Bash 被标「未解析读写(变量路径)」#572)。
- **后续反转(需如实记下)**:ECAT iteration‑2 自己推翻了这条判定——`.ecat/agents/generator/memory/arkts-app-shell/feedback_app-json5-template-defaults.md@v4` 第 9 行:检测器只认 `com.example.*` 前缀,而 Android 源本来就是 `com.example.diceroller`,「不能当缺陷盲改」;0.07KB 的 foreground/background 也「是 Android Studio 模板自适应图标…同类等价而非占位缺口」。所以 #10/#11/#14/#15 至少一半是检测器误报。真正有实质的是 icon 指针切到 AppScope 内可解析的 `layered_image`(打包期已验证 4/4 引用可解析)。

### 7. EntryAbility.ets v7–v9 — 注册全局未捕获异常观察者
- **改了什么**:`@kit.AbilityKit` import 补 `errorManager`;`onCreate` 内调 `registerGlobalErrorObserver()`;类尾新增该私有方法(`errorManager.on('error', observer)`,实现 `onUnhandledException` + `onException`,回调内只落 hilog)。+20 行。
- **谁改的**:`agent-a27497cfed8c44856`(账本名 fix-uitest,实际派发词是全局异常观察者),v1–v3,T+6:53。ECAT work list #13。
- **为什么要改**:全 app grep 不到 `errorManager.on|appRecovery|hiAppEvent`,未捕获异常直接杀进程、零 crash 报告。
- **生成期为什么没做对**:**这是 HarmonyOS 侧才有的框架要求,生成链路的 spec/plan/skill 里根本没有这一项**。EntryAbility 生成期只有脚手架模板(v2)+ 沉浸式(v3),`spec/baseline` 全部由 Android 源反推,Android 有免费的默认 crash handler,对照源码永远推不出这条。work list 原文自己就注明「HarmonyOS framework constraint with no Android counterpart — do not consult the Android source for this fix」。
- **证据**:`file EntryAbility.ets diff=True` v7/v8/v9;派发词全文;修复方 fail loud 记录(prompt 预设的 `@kit.ArkTS` 在本镜像不存在,实测改用 `@kit.AbilityKit`,证据链读了 4 个 d.ts);ECAT 已把它固化成生成侧记忆 `.ecat/agents/generator/memory/arkts-app-shell/feedback_global-crash-observer.md@v1`。

### 8. Index.ets v18 — `console.error` → `hilog.error`
- **改了什么**:第 65 行 `console.error(...)` → `hilog.error(DOMAIN, TAG, 'rollLabel uppercase failed: %{public}s', ...)`,并在 v11 顶部补 `import { hilog } from '@kit.PerformanceAnalysisKit'` + `const TAG='Index'` / `const DOMAIN=0xFF00`。
- **谁改的**:`fix-index` `agent-a228e9716d833cbf3` v1(import/常量)+ v8(调用点),T+6:53。ECAT work list #16。
- **为什么要改**:ECAT 派发词的 ArkTS 红线「No `console.*` — use `hilog`」;工程既有约定见 EntryAbility 顶部 DOMAIN/TAG。
- **生成期为什么没做对**:**不是 execute 引入的,是修复期第一波(visual-fixer)引入的,而它的参考资料就在示范 `console.error`**。`blame Index.ets@v18 changed=True` → 被替换行 owner = `修 round-1 视觉差异@v5`(T+4:02)。该 agent 的派发上下文里内嵌的适配参考原文就有 `catch (e) { console.error('foldable check failed', e); }` 示例代码(agent-a4874344c8fb6228d.jsonl 第 6 条 user 消息),且生成期整条链路(81e0a463 及其全部子 agent)grep 不到任何禁 `console.*` 的规则(0 命中)。属**规则在链路上不一致**,不是模型自作主张。
- **证据**:`blame @v18 changed=True`;`diff @v11`/`@v18`;grep 结果(禁 console 规则只在 2f01bcdc 会话出现)。

### 9. Index.ets v22 + spec/placeholder-registry.md v5 — 占位注释去 token 化 / 使用点登记
- **改了什么**:注释 `// UI 测试锚点:首屏占位(A2 变体,承载 accessibilityText='TODO' 断言锚,id-inject §1)` → `// UI 测试锚点:未掷态骰面槽(A2 变体,accessibilityText 绑 string.json:todo,id-inject §1;D-002 忠实复刻)`;**代码 `.accessibilityText($r('app.string.todo'))` 一行未动**,改为在 `spec/placeholder-registry.md` 的 P‑RES‑TRANS‑002 行把 location 扩到覆盖使用点。
- **谁改的**:`fix-index` v12(注释)+ v14(注册表),T+6:53。ECAT work list #1/#2。
- **为什么要改**:检测器 `\bTODO\b` IGNORECASE 扫到了注释里的 `'TODO'` 字面量与 `$r('app.string.todo')`,判 Unregistered placeholder。
- **生成期为什么没做对**:**生成期没做错**——`accessibilityText($r('app.string.todo'))` 是 `spec/decision-ledger.md` D‑002(C12 忠实复刻,approved)明令保留的 Android 原行为(`contentDescription="@string/todo"`),同时还是 F001‑AC11 的断言 oracle;被改的那行注释是 `UI-T Step2 ID 注入@v10`(T+4:42,也在 execute 之后)写的。问题在**检测器口径**:`\bTODO\b` 命中资源键 + 注册表解析只认单中段 P‑ID(`P-RES-TRANS-002` 被静默丢弃 → `registry_total=0`)。
- **证据**:`blame Index.ets@v22 changed=True` → owner=`UI-T Step2 ID 注入@aa1ccf93d575837a2 @v10`;fix-index 派发词「代码一行都不许删、不许改——这是 D-002 approved 决议要求的忠实复刻」;`.ecat/.../debt-registry-triage/feedback_placeholder-detector-mechanics.md@v2` 第 10/11 行把这两条口径缺陷写死了,并注明修法在 harness 侧(`check_placeholder.py` / `spec_parser.py`),Generator 侧永不自改。

### 10. Index.ets v11,v12,v13,v15,v16,v17,v19,v20,v21,v23 — 注释卫生:剥离 Android/Kotlin/Material 溯源
- **改了什么**:10 处纯注释改写,零代码行。头部三行溯源从 `app/src/main/res/layout/activity_main.xml`、`MainActivity.kt`、「尺寸取自源布局」改指 `spec/baseline/*`;「Android 端同文件内聚」「Kotlin `(1..numSides).random()`」「对应 Kotlin when (diceRoll) 各分支」「Android rollDice() 等价」「Material textAllCaps」「Android statusBarColor 的透出区」「Theme.DarkActionBar 等价」「ConstraintLayout →」「Material Widget.MaterialComponents.Button 默认」全部改成 Harmony 自身说法。
- **谁改的**:`fix-index` v1/v2/v3/v5/v6/v7/v9/v10/v11/v13,T+6:53。
- **为什么要改**:ECAT Generator 派发词 Rule 7「Comment hygiene (mandatory, no exceptions)——Android references in comments … MUST be stripped — the Harmony repo describes Harmony, not its Android origin」,主会话把它逐条展开写进了 fix-index 的「注释卫生(强制)」段。
- **生成期为什么没做对**:**生成链路的规范恰好相反,两套规则冲突**。页面 spec 模板本身就有「## 溯源」段并逐行列 Android 路径(`page_0001_MainActivity.md@v3:8-13`);conv-page-0001 的派发词把 `android_source_anchors` 当强制输入(「anchor 缺失/读取失败 → 必须 FAIL」)。全库 grep:「注释卫生」四字**只在会话 2f01bcdc 出现(28 次),生成期 0 次**。所以这 10 处不是生成缺陷,是下游 harness 新立口径后的追溯性返工。
- **证据**:`blame Index.ets@v11 changed=True` → 3 行 owner 全是 `conv-page-0001@v3`;`diff @v12..@v23`;2f01bcdc 首条 user prompt Rule 7 全文;grep「注释卫生」逐文件计数。

**附:同期测试目录改动(不入返修链,但同属 execute 之后)** — `entry/src/ohosTest/ets/test/ui/P0001_MainActivity_UI.test.ets` v12–v20 由 `gate-build` `agent-ab171858f8e6d6a08` 在 T+6:52–6:54 做的 6 条 TODO 注释改写(work list #3–#8);`entry/src/ohosTest/ets/test/spec/F001_dice-roll.test.ets` v2–v4 由 `agent-a7a4b445e36d5383f` 删「stub 恒产 3」类推测句(work list #9)。两者与第 9 组同根因(检测器 `\bTODO\b`/`stub` 口径),代码零改动。另注:ecat 三个 fix agent 的账本显示名与实际派发词错位(fix-errobserver 干的是 app.json5,fix-uitest 干的是 errorManager,fix-uttest 干的是编译门),归因请以派发词为准。

---

## 生成阶段问题总结

按「生成链路上哪一环该改」归拢,共 6 处:

**① 页面 spec 的样式保真度不足(a2h-spec 环,主会话·81e0a463 v4/v12/v13)**
`page_0001_MainActivity.md` 把 Button 只描述到「文案 + 字号 + 位置」,主题(`Theme.MaterialComponents.DayNight.DarkActionBar`)对控件默认形态的影响——textAllCaps、4dp 圆角、2dp elevation——一条没进 spec。下游 converter 拿到的是一份"结构对、皮肤空"的规格。
→ 对应修复 **#1**。

**② converter 读了主题却没做主题→控件默认形态的换算(a2h-execute 环,conv-page-0001)**
`themes.xml` 与 `values-night/themes.xml` 都读了,报告里也自称"对齐 Material 填充按钮运行时形态",落地只做了配色和 minWidth。属"读全了仍写错"。这是唯一一处纯粹的**转换错**。
→ 对应修复 **#1**。

**③ 生成链路缺"可测性契约":测试相关的源码接口在 execute 阶段完全不存在(编排环)**
export 可见性、UI 测试锚 id、want 测试桥、测试宿主依赖,四件事都要回改 `entry/src/main/` 下的生产代码,却全部由 verify 阶段的 verifier 补写。根因是测试设计(ut-design / ui-test design / id-inject)整体排在代码生成之后,converter 派发词里没有任何 testable-id / export / 测试桥要求。
→ 对应修复 **#2、#3、#4、#5**。

**④ 决策台账与派发硬边界挡住了本可落地的身份字段;而生成期自己的身份门禁又放行了(a2h-plan/execute 编排环 + decision-ledger)**
派发词以「部署期 D‑009」为由禁碰 bundleName/vendor,但 app-identity 收尾就报了「ledger 尚无 D‑009 正文条目」——一条不存在的决议挡了 5 个 work item;D‑003 把图标整组划进 skip-list,导致 `arkts-app-identity` SKILL.md 第 45–49 行的 AppScope 三件套输出清单虽被全文读过却未执行,app-identity 还把 entry 模块的资产误当作 AppScope 作用域已齐备。更关键的是 CHECK‑4「身份」在 `bundleName=com.example.myapplication` 下判 PASS,该值还被当既成事实传进了下游 UT 派发词。
→ 对应修复 **#6**。

**⑤ HarmonyOS 独有的平台必做项没有进入 spec/plan(a2h-spec/plan 环)**
全局未捕获异常观察者是 Android 无对应物的框架要求,而整条 baseline 由 Android 源反推,这类项天然推不出来,plan 里也没有"平台必做项清单"这一层。ECAT 已把它固化为生成侧记忆 `feedback_global-crash-observer.md`。
→ 对应修复 **#7**。

**⑥ 规则在生成链路与下游 harness 之间不一致,制造了大量"看起来是缺陷"的返工**
三条口径冲突,都不是模型判断失误:
- 日志:ECAT 禁 `console.*`,而生成/visual-fix 期链路 0 处禁令,visual-fixer 的参考资料本身还在示范 `console.error(...)` → **#8**;
- 注释:ECAT Rule 7 强制剥离 Android 溯源,而页面 spec 模板有「## 溯源」段、converter 派发词把 `android_source_anchors` 列为强制输入 → **#10**(10 处纯注释返工);
- 占位检测:`\bTODO\b` IGNORECASE 命中资源键 `app.string.todo`,注册表解析正则只认单中段 P‑ID 导致 `registry_total=0`,把 ledger D‑002 approved 的忠实复刻锚点误报成 unregistered → **#9**;身份检测器只认 `com.example.*` 前缀,与 Android 源真实的 `com.example.diceroller` 撞车 → **#6 的一半**。

**分量判断**:10 组修复里,真正可归到"生成阶段做得不好"的是 #1(spec 漏写 + 转换错)、#6(决策/门禁)、#7(平台必做项缺失),以及 #2–#5 这一整类编排顺序问题;#8/#9/#10 与 #6 的一部分是下游口径与生成链路不一致造成的返工,ECAT 自己在 iteration‑1/‑2 的记忆文件里已经推翻了其中几条。

**说不清的**:`entry/oh-package.json5@v2` 的全文无法复原(盲写,账本标「edit 作用在未知状态上」),只能凭 diff 判定改动内容;`AppScope/resources/base/media/` 三件资产的落盘 Bash 被标「未解析读写(变量路径)」,其内容仅由修复方自报的 md5 对账佐证,账本无独立记录;`build-profile.json5` 的 `ohosTest` target 是否在 execute 后被加过,账本显示该文件「只被读过(外部输入)」,**无法确认**。