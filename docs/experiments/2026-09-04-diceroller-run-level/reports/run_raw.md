已查完。所有证据来自转录原文,下面按「每一处修复 → 生成阶段问题」输出。

---

# 每一处修复

execute 结束于 `2026-09-03T16:46:29Z`(`stage-marks.json`)。此后对迁移工程 `dice-hmos/` 的**全部**落盘改动如下,按时间排序。

## A. 验证链路工具自身的修复(改的是 `dice-hmos/.claude/skills/` 下的脚本)

### A1. `toolkit-fact-indexer/.../extractors/ast_index.py`:`parser.parse(str)` → `parse(bytes)`
- **谁改**:主会话,`attributionSkill=android-fact-tree`
- **为什么**:新版 `tree_sitter_language_pack` 的 `parse()` 只收 bytes,传 str 抛 `TypeError: source must be a bytestring...`,被 `except Exception: return None` 吞掉 → 所有源文件解析失败 → `_HIERARCHY` 空 → `navigation_graph.nodes` 空 → screens=0 → 事实树 0 节点
- **哪一环**:vendored toolkit 与已装 tree-sitter 版本不兼容,且 **裸 `except` 把致命错误吞成"空结果"**,所以一路静默产出空树而不是报错
- **证据**:`81e0a463….jsonl:2101-2115`(17:04:27 复现 TypeError → 17:04:46 Edit);retrospect「上游 skill 改进建议」第 3 条「tree-sitter 0.26 API 兼容」(`81e0a463….jsonl:3617`)

### A2. `arkts-visual-verify/scripts/assert_run_success.sh`:`functional_checks.tested` 加 `.total` fallback
- **谁改**:主会话,`a2h-functional-merge`
- **为什么**:自检脚本读 `tested` 字段,而 sub-agent manifest 的 schema 是 `{total,passed,failed}`(`tested` 在 `interaction_test_summary.tested_count`)→ 真实执行记录被判成 0 = 假红
- **哪一环**:skill 脚本与 sub-agent 输出 schema 不同步(契约漂移)
- **证据**:`81e0a463….jsonl:3119`(18:24:09,补丁注释写明 "FIX(2026-09): …只读 tested 会把真实执行记录判成 0 = 假红");retrospect「关键经验」第 2 条「修脚本加 fallback,不修数据迎合脚本」

## B. verify 阶段 — 视觉对齐的两处真改动(唯一改了 App 可见行为的修复)

### B1. `Index.ets`:Roll 按钮文案改为运行时大写 `ROLL`
- **改了什么**:新增 `@Local rollLabel: string = 'ROLL'` + `aboutToAppear()` 里 `ctx.resourceManager.getStringSync($r('app.string.roll')).toUpperCase()`,`Button($r(...))` → `Button(this.rollLabel)`
- **谁改**:`visual-fixer` 子代理 `agent-a4874344c8fb6228d`
- **为什么**:visual-verify 出 P1 单 `ALIGN_PMainActivity_text_mismatch_roll-button-text` —— Android 端 Material 主题 `textAllCaps=true` 运行时渲染为 "ROLL",HMOS 端把资源串 "Roll" 原样直排
- **生成期为什么没做对**:**spec 把 AC 写反了,并且 plan 期的转换器发现了矛盾却服从了 AC**。
  - spec 的 android-analyzer 其实**记录过**这个事实:§3.4.3 排版表写着 `android:text=@string/roll ("Roll") | 默认 textAllCaps/字重继承 Material Button 样式`(14:47:19)
  - 但 AC14 被写成「按钮显示 'Roll' 且源码引用字符串资源键」——取自 uiautomator dump 的 `meta.json` 逻辑文本,不是渲染形态
  - 转换器在 15:50 的 thinking 里逐字权衡过:「MaterialButton default textAllCaps=true → displays "ROLL" … **But AC14 expects displayed "Roll"! So DON'T uppercase** … meta.json/AC wins for semantics」
- **哪一环**:`a2h-spec` 的 AC / ui-manifest oracle 口径——**把 uiautomator 的逻辑文本当成显示文本**,并且这条错误 AC 的优先级压过了同一份 spec 里 analyzer 已写下的主题渲染事实
- **证据**:`agent-a1cdbdfd0be2dd5ff.jsonl:63`(14:47:19,analyzer 记 textAllCaps);`agent-a349784d2663f1f0a.jsonl:61`(15:50:09,converter 明确因 AC14 放弃大写);`agent-a4874344c8fb6228d.jsonl:1/66/68/70`(18:24:30 派单、18:29:03-21 三处 Edit)

### B2. `Index.ets`:按钮形状 Capsule → Material 小圆角矩形 + 投影
- **改了什么**:`.type(ButtonType.Normal)` + `.borderRadius(4)` + `.shadow({radius:6, color:'rgba(0,0,0,0.26)', offsetY:2})`
- **谁改**:同上
- **为什么**:P1 单 `ALIGN_…button-corner-radius` —— ArkUI Button 不显式 `type` 时默认 Capsule(半径=半高),与 Material `Widget.MaterialComponents.Button` 的 4dp 圆角矩形 + elevation 2dp 不符
- **生成期为什么没做对**:转换器在 15:50 已经意识到 Material Button 的默认形态(「corner radius 4dp, bg colorPrimary, text colorOnPrimary」),**只落地了颜色两项(backgroundColor/fontColor),形状与阴影漏了**;它当时的判据是「AC13/AC14 没有形状/颜色要求」,补颜色属于自选动作,形状就没补
- **哪一环**:plan 期的属性映射参考只覆盖**显式写在 XML 里的属性**(映射表里有 `android:textAllCaps → .textCase()`,但没有「Android 主题/控件默认样式 vs ArkUI 控件默认样式的差异清单」);AC 又只约束了位置/字号,没有形状 oracle → 两侧都没兜住
- **证据**:`agent-a349784d2663f1f0a.jsonl:61`(15:50:09,「Material default: … corner radius 4dp」但只写了 background/fontColor);`agent-a4874344c8fb6228d.jsonl:70`(18:29:21);retrospect「API 修正」表把 `ButtonType.RoundedRect`(finding 里的错拼)修正为 `Normal + borderRadius(4)`

> 附带引入的问题:B1 的 catch 里写了 `console.error`,以及 `getStringSync` 触发 deprecated WARN。前者在 D3 被 ECAT 改掉,后者到最后都没修(verify-report CHECK-2 记为 `Index.ets:62 getStringSync has been deprecated | WARN`)。

## C. verify 阶段 — 为了跑测试而回改主工程 + 补测试基础设施

### C1. `Index.ets`:`class Dice` → `export class Dice`
- **谁改**:主会话,`arkts-ut-verifier`(18:39:07,`81e0a463….jsonl:3231`)
- **为什么**:arkxtest 单测要 `import { Dice }`,生成期 Dice 是同文件内聚的**非 export** 类,测不到
- **生成期为什么没做对**:execute 期的「服务层契约 = 内聚 Index.ets」只考虑了结构保真,没考虑可测性;可测性是到 verify 才被提出的需求
- **哪一环**:execute 的服务层契约 / plan 未把「被测面可见性」纳入约束。retrospect 自己把它列为待审批设计决策:「Dice 可见性放宽 … 两约束冲突时取最小侵入」

### C2. 新建 `entry/src/ohosTest/ets/test/spec/F001_dice-roll.test.ets`(3 个 it)
- **谁改**:`agent-a3dee39ee51d8c82a`(18:42:22,CREATED)。属 verify 正常产出,非补漏。

### C3. `entry/src/ohosTest/ets/test/List.test.ets` 重写(注册 F001 套件;19:19 再次重写以并入 UI 套件)
- **谁改**:`agent-ac1d7fa32a05796ea`(18:43:36,UPDATED)/`agent-adfd3f8bcc1cfe28e`(19:19:51)

### C4. ohosTest 基础设施整体补全(**这是最大的一处生成期缺口**)
- **改了什么**:
  - 重写 `ets/testrunner/OpenHarmonyTestRunner.ets`(原文件被判「wrong version」)
  - 重写 `ets/testability/TestAbility.ets`(同上)
  - 新建 `ets/testability/pages/Index.ets`(原缺失)
  - 重写 `entry/src/ohosTest/module.json5`(原文件引用了**不存在**的 `$media:layered_image` / `$media:startIcon` / `$color:start_window_background`)
  - 新建 `resources/base/element/color.json`、`resources/base/profile/test_pages.json`、`resources/base/media/icon.png`
  - `entry/oh-package.json5` 补 `devDependencies: {"@ohos/hypium": "1.0.21"}`(原为空对象)
- **谁改**:`agent-ac20d808e5bc6be60`(18:48:41–18:49:07)
- **为什么**:不补齐,测试 HAP 编译/拉起必失败(卡空白页 / `The context is invalid` / `16000001 ability not found`)
- **哪一环**:**Stage 0 脚手架模板**(`android2hmos_resources_convert/template/`)带的 ohosTest 骨架是残缺且自相矛盾的(module.json5 引用了模板里根本没有的资源),而 execute 全程不碰 ohosTest 模块 → 缺陷一直留到 verify 才被发现并临时手补,**补丁只落在本工程,没有回流模板**
- **证据**:`agent-ac20d808e5bc6be60.jsonl:22`(18:46:04 诊断列出 1./2. wrong version、3. MISSING、4. 引用不存在资源)、`:52-68`(逐个 Write/Edit);写回结果显示 runner/TestAbility/module.json5 是 `updated`(文件已存在)、pages/Index.ets 等是 `created`

> 顺带暴露:`entry/src/main/resources/base/media/startIcon.png` 是 **68 字节的 1×1 灰度 PNG 占位图**(`file` 实测),即脚手架默认图标从未被替换。`agent-ac20d808e5bc6be60.jsonl:71`(18:49:15)

### C5. `Index.ets`:注入 3 个测试锚点 `.id()` + 新建 `entry/src/main/ets/test/testable-id-manifest.md`
- **改了什么**:`main_root`(Navigation)、`main_toolbar_title`(标题 Text)、`main_dice_placeholder`(未掷态 Column)
- **谁改**:`agent-aa1ccf93d575837a2`(19:08:28–19:09:22)
- **哪一环**:管线设计上 id 注入归 `arkts-ui-verifier` step2,但代价是 **verify 阶段回写 `src/main` 业务源码**;生成期页面完全没有可测锚点

### C6. 新建 `entry/src/main/ets/test/TestDataSetup.ets` + `EntryAbility.ets` 加 UI 测试桥
- **改了什么**:`EntryAbility` 引入 `TestDataSetup`、加 `TEST_MODE_KEY/TARGET_PAGE_KEY/HOST_PAGE_NAME` 常量、`onCreate` 与新增的 `onNewWant` 都调 `consumeTestWant(want)`,把 want 测试参数写进 AppStorage
- **谁改**:`agent-a711c5d09fb676814`(19:17:04–19:17:35)
- **为什么**:UI 测试要从 want 注入测试模式;模板 §6.2 的 `@StorageLink+@Watch` 桥是 V1 装饰器,而 `Index` 是 `@ComponentV2`,不可用 → 桥被迫收敛到 ability 侧
- **哪一环**:`arkts-ui-verifier` 的测试桥模板只有 V1 装饰器方案,与 execute 选定的 `@ComponentV2` 页面不兼容 → **模板与生成产物的装饰器体系不匹配**,现场临时改形态。retrospect 把它列为待审批决策「V2 测试桥形态」
- **注**:这条改动把纯测试用的桥接代码永久写进了 `src/main` 生产源码

### C7. 新建 `entry/src/ohosTest/ets/test/ui/P0001_MainActivity_UI.test.ets`(10 个 it)
- **谁改**:`agent-a711c5d09fb676814`(19:18:38)

### C8. UI 测试编译修复:`Component.getAccessibilityText()` 不存在 → §D 降级为弱断言
- **改了什么**:删掉 `readDiceFaceText()` 探针;`AC11` 的 `expect(a11y).assertEqual('TODO')` 改成 `assertComponentExist(ON.id('main_dice_placeholder'))`;`AC01/AC09/AC21/AC22/AC16` 共 5 条的值域断言全部转弱断言,oracle 值只留在注释里
- **谁改**:`agent-a52d61ac7ab7033ba`(19:26:35–19:27:31,6 处 Edit)
- **为什么**:`ERROR 10505001: Property 'getAccessibilityText' does not exist on type 'ON'`(×2),且真机 dumpLayout 证实本镜像 a11y 树 `text/description/originalText/hint` 全不透出
- **哪一环**:`arkts-ui-verifier` 的用例设计模板假定 `getAccessibilityText`(API 12+)可用,**没有对当前 SDK 的 d.ts 做能力核验**就写进设计
- **证据**:`agent-a52d61ac7ab7033ba.jsonl:105/107/109`;retrospect「编译错误 Pattern」表唯一一行 + 「API 修正」表第 1 行 + 上游建议第 15 条

### C9. 启动通道二分诊断与最终改形:`TestAbility.ets` 临时诊断代码 → 回滚;`ohosTest/module.json5` 加 `"process": "entry_test_host"`;P0001 测试改启动通道
- **谁改**:`agent-a52d61ac7ab7033ba`(19:45:29–19:54:51)
- **为什么**:emulator 6.0.0.112 上 `aa test` 共宿进程内任何 API 启动 entry 页都触发 `page not found! pages/Index` → `Load Page Failed` jscrash(5 次复现),`Driver.create()` 返回 null
- **哪一环**:**环境/镜像层限制,不是生成缺陷**。结果:CHECK-10 判 DEFERRED,ui PASS 0/10 全 UNREACHABLE
- **证据**:`agent-a52d61ac7ab7033ba.jsonl:260/262/275/277/281/297/305`;verify-report CHECK-10 节(`81e0a463….jsonl:3538`)

### C10. `spec/placeholder-registry.md` 统计头 0 → 1
- **谁改**:主会话 `arkts-ui-verifier`(20:17:06,`81e0a463….jsonl:3510`)
- **为什么**:plan 期写下的统计头是陈旧账,FV-1 append 了 `P-RES-TRANS-002` 却没 bump 计数
- **哪一环**:registry 的 append 路径不维护统计头(纯记账缺陷)。retrospect 上游建议第 5 条同类问题

## D. build/复核阶段(20:23–21:07)—— 零源码改动

- CHECK-10 复核修了两项**验证流程自身**的缺陷,都不是工程文件:① round-0 用的 `--psb` 是非法旗标,改用 `--pb __test_mode__ true`;② 每轮 `uitest start-daemon 0;` 泄漏常驻实例,9 轮堆积导致 `RET_ERR_CONNECTION_EXIST`。之后新增等价通道 harness `spec/verify/ui/round-1/replay_ui_cases.py`(宿主侧 Python 经 hdc+uitest 机械回放同一批断言,10/10 PASS)。
- 三次 `/a2h-build` 全部 `BUILD SUCCESSFUL, exit=0`。
- **证据**:`efdc8b71….jsonl:276`(probe.sh)、`:517` 起及 20:48:40 收尾汇报;`593d4e86….jsonl:175`(replay harness)、21:06:59 收尾汇报

## E. ECAT 对抗轮 iteration 0(21:18–21:20)—— 最后一批真实源码修复

判别器给出的维度分:`app_identity=0.6`、`crash_risk=0.125`、`placeholder=1.0`(自认误报)、`style=0.0136`,其余(page_audit/feature_check/entry_nav/source_parity/hallucination)**全 0**(`257fed22….jsonl` 末条,21:13:34)。

### E1. `AppScope/app.json5` 身份字段 + AppScope 分层图标三件套
- **改了什么**:`bundleName: com.example.myapplication → com.example.diceroller`;`vendor: example → diceroller`;`icon: $media:app_icon → $media:layered_image`;从 entry media 逐字节 cp 出 `AppScope/resources/base/media/{background.png, foreground.png, layered_image.json}`
- **谁改**:`agent-a87804892da9cfc8b`(`a2h-migration-worker` + `arkts-app-identity`,21:19:00 cp / 21:19:08 Edit)
- **为什么**:模板默认身份原样残留到最终产物;Android `build.gradle:10` 的 `applicationId` 就是 `com.example.diceroller`
- **生成期为什么没做对**(三重失守,证据都很直白):
  1. **execute 期的派单 prompt 明令不许改**:app-identity worker 的 thinking 逐字记着「task prompt 说 `不碰 bundleName / vendor（部署期 D-009）`」,而 `arkts-app-identity` 的 `scope=dev-identity` 也把 bundleName/vendor 排除在外
  2. **它引用的 D-009 在 ledger 里根本不存在**。worker 自己 grep 后确认「D-009 didn't appear in the grep results … it's not present → ledger 未命中」,但因为 prompt 和 skill 两边一致,判为「no gap」放行 —— **一条不存在的决策编号被当成了免责依据**
  3. **verify 的 CHECK-4「App 身份校验」把它判成 PASS**:验证报告白纸黑字 `bundleName | PASS | com.example.myapplication`。这条检查只查字段在不在,不查是不是模板默认值
- **证据**:`agent-a39c5351955d3cd6b.jsonl:43`(15:34:35 thinking:「bundleName/vendor untouched (dev-identity + D-009)」)、`:47`(15:35:05「ledger 未命中 D-009 … 但两边一致 → no gap」)、`:59`(15:35:18 只改了 versionCode/versionName);verify-report CHECK-4 表(`81e0a463….jsonl:3538`);retrospect 却宣称 Base-0「converter 直写零漏网」——与事实矛盾;修复见 `agent-a87804892da9cfc8b.jsonl:45/49`
- **遗留**:cp 过去的 `background.png/foreground.png` 仍是 **68 字节 1×1 占位图**(md5 与源同为 `e44e7ec…`),iteration 1/2 又被检测器报 `0.07KB likely default placeholder`,最后靠 ledger D-003/D-004 豁免结案,**真图标始终没有落地**

### E2. `EntryAbility.ets` 注册全局未捕获异常观察者
- **改了什么**:import `errorManager`;`onCreate` 首行加 `this.registerGlobalErrorObserver()`;新增该私有方法,`errorManager.on('error', {onUnhandledException, onException})` 里落 hilog
- **谁改**:`agent-a27497cfed8c44856`(21:19:24–21:19:39)
- **为什么**:全工程无 `errorManager.on` / `appRecovery` / `hiAppEvent` crash watcher,任何未捕获异常直接杀进程且生产不可追溯
- **哪一环**:**HarmonyOS 框架侧的必备接线,Android 源里没有对应物,所以「照着 Android 抄」的整条生成链天然抄不出来**;而应用外壳脚手架(判别器 suggested_skills 指向 `arkts-project-scaffolder`)模板里也不含它。verify 的 11 项 CHECK 也没有任何一项覆盖 crash 可观测性
- **证据**:`257fed22….jsonl` 判别器 `crash_risk` 条目(21:13:34);`agent-a27497cfed8c44856.jsonl:41/43/45`

### E3. `Index.ets`:`console.error` → `hilog.error`
- **谁改**:`agent-a228e9716d833cbf3`(21:19:36)
- **为什么**:ArkTS 禁 `console.*`
- **哪一环**:这行是 **B1 的 visual-fixer 在 18:29 自己新引进来的**(`aboutToAppear` 的 catch 块),违反了工程既有的 hilog 规范;而 verify 的 CHECK-2 静态分析因为「codelinter 不在本 SDK 安装路径」退化成只看 hvigor 诊断,没抓到
- **证据**:`agent-a4874344c8fb6228d.jsonl:68`(引入)、`agent-a228e9716d833cbf3.jsonl:57`(修复)、verify-report CHECK-2 节

### E4. 注释卫生:`Index.ets` + `P0001_MainActivity_UI.test.ets` + `F001_dice-roll.test.ets` 共 ~24 处注释改写
- **改了什么**:剥掉全部 Android 溯源字样(`app/src/main/res/layout/activity_main.xml`、`MainActivity.kt`、`Kotlin (1..n).random()`、`Material textAllCaps`、`Theme.DarkActionBar`、`ConstraintLayout`、`Android @id/imageView`…),`'TODO'`/`'stub'` 字样改写成「初始无障碍资源值」「未掷态槽位」等措辞
- **谁改**:`agent-a228e9716d833cbf3` / `agent-ab171858f8e6d6a08` / `agent-a7a4b445e36d5383f`(21:19:16–21:20:21)
- **为什么**:ECAT Generator prompt 的 Rule 7「Comment hygiene (mandatory, no exceptions)」把 Android 引用和 TODO/placeholder 字样定为 severity=high
- **哪一环**:**两套规范互斥**。execute 期的溯源注释(`// 结构溯源: app/src/main/res/layout/activity_main.xml`)是 a2h 管线自己要求写的可追溯性约定,ECAT 的注释卫生规则又要求删。而 9 条 placeholder 命中里,判别器自己已经判定 **8 条是注释文字、1 条是 ledger D-002 approved 的合法项**,并在 `priority_overrides` 里逐条标 low 且写明「不得删除决策性注释」——Generator 仍然把它们全改了一遍。这是**为了让检测器闭嘴而改代码**,零功能收益,反而损失了溯源信息
- **证据**:2f01bcdc 的 Generator prompt Rule 7(`2f01bcdc….jsonl:3`);判别器 `priority_overrides` 9 条(`257fed22….jsonl` 末条);三个子代理的 Edit 明细
- **编译门**:改动后 `agent-a635575c78cd15ff6` 跑真实编译 `BUILD SUCCESSFUL in 8s185ms`

## F. ECAT iteration 1 / 2(21:27–22:09)—— 零源码改动,只补账

### F1. `spec/decision-ledger.md` 新增 D-004 + 两行审批流水
- **改了什么**:D-004「bundleName/vendor = Android applicationId 原样映射,源取值形似模板时以源真值优先,不改名」,approved;iteration-2 又追加一行对账复验记录(维持 D-003/D-004)
- **谁改**:iteration-1 Generator(21:48:24/33/37)、iteration-2 Generator(22:02:31)
- **为什么**:检测器用 `com.example.*` 前缀启发式判「模板默认」,但 Android 源的 applicationId 本来就是 `com.example.diceroller`;正确出口是补 ledger 决策留痕而不是再改名
- **哪一环**:**ECAT `app_identity` 检测器的启发式没有 parity check**(不比对 Android applicationId,只看前缀),对 beginner 级 Android 工程必然误报

### F2. `.ecat/agents/generator/memory/` 下 6 个记忆文件(新建+多轮修订)
- `arkts-app-shell/feedback_global-crash-observer.md`、`feedback_app-json5-template-defaults.md`、`debt-registry-triage/feedback_approved-fidelity-not-debt.md`、`feedback_placeholder-detector-mechanics.md` + 两份 `_index.md` + `MEMORY.md`
- **谁改**:iteration-0 Discriminator(21:12)、iteration-1(21:34/21:48)、iteration-2(21:57/22:02)
- **意义**:这是唯一把教训沉淀成可复用资产的动作;其中 `app-json5-template-defaults` 的描述直接写着「资源转换 pass 覆盖不到 app.json5 身份字段与 AppScope 分层图标,模板默认值会原样残留到最终产物」

### F3. 两轮都没能收敛的死循环
- iteration 1 → 2 的熵 `ΔH = +0.0000`,work list 8 条**一字未变**。原因:占位维度 5 条命中的根因是 ECAT 检测器读到 `registry_total=0`(而 `spec/placeholder-registry.md` 在 20:17 已修正为 1),检测器代码在 harness 源里,而 loop agent 的启动参数带 `--disallowedTools Edit(//…/hmigbot-plus/src/migbot/**)` —— **Generator 被设计性禁止修改评估器,于是这条误报永远修不掉**
- **证据**:`70f369a3….jsonl:231`(21:46:55 thinking,ps 实测到 disallowedTools);`70f369a3….jsonl:3` 与 `1d2ef418….jsonl:3` 的 work list 逐条对比;`81e0a463….jsonl:3510`(registry 已修)

---

# 生成阶段问题总结

把上面的原因归拢,生成链路上有 **7 处该改**:

## 1. spec 的 AC/oracle 口径:把 uiautomator 的「逻辑文本」当成「显示文本」
最贵的一处。同一份 spec 里,analyzer 已经写下了 `textAllCaps` 继承 Material 样式(§3.4.3),AC14 却按 `meta.json` 的 `text="Roll"` 写成「按钮显示 'Roll'」。转换器在 15:50 明确看到了矛盾,**选择服从 AC**。错误的 AC 不只是"漏了",它还**主动把正确实现挡了回去**。
→ 对应修复:**B1**。
→ 该改:UI 快照抽取要区分 logical text / rendered text;AC 生成器遇到主题级渲染变换(allCaps、textAppearance、tint)必须以渲染形态为 oracle,或至少不得断言与 analyzer 事实相反的内容。

## 2. plan 的属性映射参考只覆盖「显式 XML 属性」,不覆盖「控件默认样式差异」
映射表里有 `android:textAllCaps → .textCase()`,却没有「Material Button 默认 = 4dp 圆角矩形 + elevation 2dp」vs「ArkUI Button 默认 = Capsule」这类**两端默认值不同**的条目。转换器凭常识补了颜色,漏了形状。
→ 对应修复:**B2**。
→ 该改:映射参考补一张「控件默认形态对照表」;或在 converter 侧强制对每个控件枚举「Android 主题默认 → ArkUI 默认」的差集。

## 3. Stage 0 脚手架模板的 ohosTest 骨架残缺且自相矛盾
`module.json5` 引用了模板里根本不存在的 `$media:layered_image`/`$media:startIcon`/`$color:start_window_background`;TestRunner/TestAbility 是错版本;`testability/pages/Index.ets`、`color.json`、`test_pages.json`、`media/icon.png` 全缺;`oh-package.json5` 没有 hypium 依赖。execute 全程不碰 ohosTest,缺陷一路留到 verify 才被人肉手补,**且补丁只落在本工程、没有回流模板,下一个工程还会再踩一次**。
→ 对应修复:**C4**(以及被它拖累的 C3)。
→ 该改:模板自洽性做一次静态校验(所有 `$xxx:` 引用必须在模板资源里可解析);ohosTest 骨架补全下沉到 Stage 0,而不是 verify 现场造。

## 4. 「不许改 bundleName/vendor」的边界,依据的是一条不存在的 ledger 决策;verify 的身份检查又太弱
派单 prompt 写「不碰 bundleName / vendor(部署期 D-009)」,skill 的 `scope=dev-identity` 同样跳过。worker grep 确认 **ledger 里没有 D-009**,却因为「prompt 和 skill 两边一致」判为 no gap 放行。随后 verify CHECK-4 把 `com.example.myapplication` 判成 PASS,retrospect 还写成「converter 直写零漏网」。三道关全部放行,直到 ECAT 才逮住。
→ 对应修复:**E1**(以及后续 F1 的补账、F2 的记忆沉淀)。
→ 该改:(a) 派单 prompt 引用 ledger 编号时必须可解析,解析不到就 fail-fast 而不是继续;(b) `arkts-app-identity` 的 dev-identity 作用域应把 bundleName/vendor 纳入(至少做一次 applicationId parity 比对);(c) CHECK-4 从「字段存在」升级为「字段 ≠ 模板默认 且 = Android 源真值」。

## 5. HarmonyOS 独有的框架接线,整条「照 Android 抄」的链路天然抄不出来
全局未捕获异常观察者在 Android 源里没有对应物 → spec 不会写、plan 不会排、converter 不会生成、verify 的 11 项 CHECK 也没有一项覆盖 crash 可观测性。判别器的原话:「crash-observability 是本轮唯一会放大其他风险后果的横切缺陷」。
→ 对应修复:**E2**。
→ 该改:应用外壳脚手架模板默认注册 errorManager 观察者;或在 plan 里建一份「HarmonyOS 必备项清单(无 Android 对应物)」并纳入 verify 门控。

## 6. verify 的静态检查形同虚设,自身工具还带 bug
- codelinter「不在本 SDK 安装路径」→ CHECK-2 退化成只看 hvigor 诊断,漏掉了 visual-fixer 自己新引进的 `console.error`
- `assert_run_success.sh` 读错字段名产生假红(A2)
- `ast_index.py` 的裸 `except` 把 tree-sitter API 不兼容吞成「空树」而不是报错(A1)
- `getAccessibilityText` 被测试设计模板当成可用 API,实际本 SDK d.ts 没有(C8)
- round-0 的 `--psb` 非法旗标 + uitest daemon 泄漏(D)
→ 对应修复:**A1、A2、C8、D、E3**。
→ 该改:验证工具链的前置能力核验(SDK d.ts 实际有没有这个 API、codelinter 装没装、脚本 schema 与产出对不对得上)应作为 verify 的入口检查,并禁止裸 `except` 把工具故障降级成空结果。

## 7. ECAT 检测器的口径缺陷,把对抗轮空转成了「改注释迎合检测器」
- `placeholder` 维度:grep 型检测器把**决策性注释**里的 `TODO`/`stub` 字样当占位符;`registry_total` 读不到工程已登记的 `P-RES-TRANS-002`;而检测器代码在 harness 里、loop agent 被 `--disallowedTools` 禁止编辑 → **误报结构性无解**,iteration 1→2 熵 ΔH=0,work list 一字未变
- `app_identity` 维度:`com.example.*` 前缀启发式没有与 Android applicationId 做 parity check,对 beginner 工程必然误报
- Generator prompt 的 Rule 7 与 a2h 的溯源注释约定直接冲突;判别器已在 `priority_overrides` 里把 9 条全标 low 并写明「不得删除决策性注释」,Generator 仍全改了
→ 对应修复:**E4、F1、F3**(以及 C10 这条本可以让检测器归零、却因口径不通而白修的记账修正)。
→ 该改:(a) 占位符检测只扫代码不扫注释,并接上工程 registry 的真实读取口径;(b) `app_identity` 加源真值比对;(c) 「注释卫生」规则要与管线自身的溯源约定对齐,不能互斥;(d) 若检测器口径漂移是熵的唯一来源,loop 必须能把它上报/豁免,而不是逼 Generator 改代码。

---

### 一句话概括
这次迁移的**功能面是干净的**——ECAT 五个功能判定维度(page_audit / feature_check / entry_nav / source_parity / hallucination)全部 0 分,23/23 AC 通过,三次编译全绿。execute 之后所有的修复,没有一条是「业务逻辑写错了」。真正的问题集中在三类:**spec 的 oracle 口径把对的实现挡了回去**(B1/B2)、**脚手架与配置域的收尾从来没人负责**(C4/E1/E2 —— 判别器原话:「都在页面域之外 … 属于脚手架/配置域收尾缺口」)、以及**验证与对抗环节自身的工具口径不可靠**,既漏报了真缺陷(CHECK-4 判 PASS、CHECK-2 漏 console),又制造了大量假红把最后两轮对抗空转掉。

### 需要说明的不确定项
- ohosTest 那套残缺骨架具体来自哪个模板文件,我只能确认「文件在 verify 之前已存在且内容错误」(Write 返回 `updated` 而非 `created`),没有转录直接展示 `template/entry/src/ohosTest/` 的原始内容 —— 归因到「Stage 0 脚手架」是基于该目录由管线模板铺设这一点,**严格说无法百分百确认**。
- verify-report CHECK-4 写「自适应图标 PASS —— Android 源为 mipmap png 直迁,md5 一致」,与 ledger D-003(launcher 图标不迁移)和实测 68 字节 1×1 占位图相互矛盾;这句话的来源我没有找到支撑证据,**无法确认它是笔误还是核查错误**。