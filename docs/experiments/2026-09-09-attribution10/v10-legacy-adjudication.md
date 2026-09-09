# V10 legacy 独立裁决

封存更新：V10 三文件的两 rep 均已完成，十二题次 core **7 pass / 5 partial / 0 fail**。这是有界核心分层，不是完整准确率：仍有两条确定 material false claim、一个 material 未充分支持的红进入点及一条条件标签细节错误。各次原判保留，后续 V11 另立文件，不覆盖本轮。

三个 legacy rep1 现已全部裁完：Member S3 pass / S4 partial；Dice D1 partial / D2 pass；Splash S1 partial / S2 pass。共 3 pass / 3 partial / 0 fail；另有 Member 一条分支条件细节错误、Splash 一个未充分支持的精确红进入点，不计成全量正确。V9 保留不改。

冻结源 `80c099e`，实际 GPT-5.5 / medium / native reference。沿用 [锁定核心口径](core-rubric-reconciliation.md)、`reference-v1/legacy-reference.json` 和相同原始池；V9 评分不变。尚在开发的 entry-effect 校验不是本轮真值或新门槛。只读完成运行、原始证据，不调用模型、不修改源/冻结材料；逐项数据及原文行散列见 [JSON](v10-legacy-adjudication.json)。

## Member rep1

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v10/member-center/runs/tools/rep1/verdict.yaml)于 21:46:25 UTC 完成。

| 题 | Core | 原事实细项 | 结论 |
|---|---|---|---|
| S3 | pass | 3 supported | 三站点 1 透明 + 2 深色、H5 原有透明并跳过全部明确；执行、快照复原和设备验证分开。 |
| S4 | partial | 2 supported、1 partial | ForEach→双 Span、tail private 来源、编译错误与去 private 修复成立；仍未核 Slice8 写前正确 Kotlin→坏整写。 |

### S3 完整补出 H5 例外

本稿实际打开 fixer `#15371@L42` 的四个 controller 索引、`#15395@L74` 的已有 mask grep、`#15397@L80` 的 builder 分类、`#15406@L103` 批量写与回执、`#15407@L106` Pay 读回。原始 L103 在目标写入后才 report，L104 同 ID 成功返回会员页 `3 sites import=+`。报告明确 206/AppLoad 透明、704/Pay 与 728/Renew 深色；761/H5 属原有 786 行 `Color.Transparent`，不算三个新增之一。本轮不再有先前的 H5 小缺项。

“另两处由脚本规则、脚本输出和 builder 盘点共同支持”是合理证据强度说明，不是否定实际执行；“未立正式版本/全文件无法复原”没有被用来抹掉原始写事实。也没有把三处输出当成三个设备场景已验收。

### S4 输入仍漏，编译来源诚实但调查不够深

实际查看主要集中在后期 fixer 和 builder：26 次 action，唯一成功 agent 是 builder@v3（`summary_chars=200`），没有 Slice8 agent、没有 blame。transcript L122 的全池 `AbsoluteSizeSpan` 搜索已经明确返回 Slice8 的 `#80bbb1f44b77da0f:13499@L21` Kotlin Read 入口，模型仍只开后期 fixer L523。

原始 Slice8 L21/L24 在 07-24 15:33 返回 `replaceSpan` 数字段逻辑，L264/L265 在 16:04 成功整写却把非动画后缀一起设 30vp。这条可恢复的最近实际输入链没有调查，故 S4 仍 partial；搜索返回入口不等于模型已经打开正文，也不因上下文里有命中就给完整近因信用。

private 错误则正确落在独立 **S4_E5 tail 事件** `#a68daf720e780b4c2:15731@L592`，没有再挂 v40。L592/L593 写后成功读回的双 Span/private helpers 与 builder L23/L24 两条 private error 对应，L32/L33、L34/L35 的正式 Edit 只去 private。builder L28 被就近绑定的 v14 读取没有被提升成“v14 内已写入 private”的版本事实。

最终成功构建本次只按 builder say L54 / 主会话通知 L1758 说明。最后搜索精确字符串 `COMPILE RESULT:PASS`（transcript L250）没有命中；原始真正成功输出在 builder L36/L37 是 `EXIT=0`、`BUILD SUCCESSFUL`，L39/L40 是 CompileArkTS/PackageHap/SignHap。报告说的是“本次未找到/未展开成功原生日志”，没有断言池内从未构建。因此不判相反事实，也不取消真实后置构建这一事实；但不授予“本次直接核过原生成功日志”的信用。相较 V9 已直开的部分稿，这是查询深度回退。

### 一条额外分支条件错述

S4_E4 说 Android 的“**非 selected/非滚动分支**”走 `replaceSpan`。原始 Kotlin 的外层条件在 L24 内容第 262 行，是 `auditingStatus==0 && model.isCt() && limitProductBean.productId匹配 && first && !fullAnimation`；`model.selected` 在 269 行只选择滚动数字的文字颜色，不决定是否走 `replaceSpan`。

模型打开的 L523 只取源码 265–295 行，缺外层 if，保留内层 selected，确有把嵌套条件混同的诱因。这个错误标签记入 `extra_false_claims`（factual_detail），需要改正；报告主要“非动画数字/后缀分离”的描述仍正确，不额外发明核心问题分母，也不借一处标签替代 S4 已锁 mandatory 漏项的判断。未发现新的 material 作者/版本错绑。

### 机械记录与成本

共 12 个事件（S3 五个、S4 七个），覆盖 13 条模型 reviewed，其中 3 条 out_of_scope，另有 25 条系统 `not_investigated` 补集；没有为少答判成 not_repair。两个 check 间只移除了 entry_events 列表，红 tail 的 role/basis/证据仍在，没有追加证据查询；11 个声明冲突 warning 归零不代表语义通过。

21 个稿内去重原文引用的转录标签/物理行唯一存在，原始 ID/时间/行 SHA 留在 JSON。raw 与最后实际 check draft 逐字相等，YAML SHA256=`0846accd6c9adc17afedad291c56a003729c021d25d4916b710555e67f0bde5d`，身份 bound、reference matched。只能证明关联一致，不证明原因真假。

input **1,716,600**（cached **1,562,112** 已包含），output **18,171**，总 **1,734,771**；wall/e2e **402.44 / 416.06 秒**，56 次工具、285,307 返回字符。比同题 raw 两 rep 均值减少 **35.54%**，但比 V9 两 rep 均值更高；这是单次开发回归观察，不是稳定收益，更不能抵消 S4 缺口。

## 当时的待追加状态

初次写入时 Dice rep1 已确认 completed（21:51:44 UTC），Splash 仍 starting。随后 Dice 裁决追加如下；最新 completion 已确认 Splash 于 21:56:16 UTC completed，但尚未裁决，仍不计入已评 core 分母。V9 文档不再改动。

## Dice rep1

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v10/dice-entry/runs/tools/rep1/verdict.yaml)：**D1 partial、D2 pass**。原事实细项 D1 为 2 supported / 1 partial，D2 为 1 supported / 2 partial。不是因 agent 工具本身没调用而扣分，而是指定的生成时实际输入链没有由其他查询补齐。

D1 后置设计 §F、模板 Mount Bridge 和三次 Edit 都有原文支持，10/10 summary、aa start 与 AppStorage 不可观测边界也正确。但生成侧只做 `generator@v1` 的关键词检索，再开 file@v2；没有打开生成派发、页面/F001 实际输入。search 的 EntryAbility 命中虽列出 F001/skill 部分行，报告最终仍只概括 Layer1 关注，未追完整输入链。与 raw 两稿原来缺生成输入被判 partial 的尺度相同，不能因用了结构化 schema 而放宽。

本次 8 次 agent 调用仅成功 bridge@v4、ECAT 主会话@v5；observer 的多次人名/未打开坐标 via 被拒，generator 根本未打开。D2 并非因此自动失败：直接 action 已核 SDK、patch、后置入口读回和原生 CompileArkTS/PackageHap/BUILD SUCCESSFUL，明确 worklist 来源，callback 仍未知；这些支持 D2 核心。原参考中 observer 修前入口 Read 没展开、may-throw WARN 没说明，细项仍 partial。没有 memory 时序排除断言，不把未讨论视为已查清。

generator 普通“无法确认”节点写 @v1，而 file@v2 的真实 writer 是 @v2。本稿 reason 明说“**后续形成的 EntryAbility@v2**”，search L243 也明确标这些动作“锚点之后”，不是声称 v1 的效应或红色引入点；不把这类普通后置引用一刀切判错。设计/模板、回放 summary、builder 读回和日志共 6 个事件也没有造新的正式版本。10/10 依据仍为历史 summary，真实启动是旁证，不是直接核 L260/L267 或证明 observer 修后异常行为。

本轮实际账本为 `atoms-2026-09-09-file-evidence5:80:c0cc62829271122172d2fc77`，global seq 与 V9 不同；current_root 仍 49d...，pool/task digest 相同，trace bound。按本轮原始标签/行/ID核验，不拿旧 seq 重绑；这里不擅自把身份差异解释为伪造或追查生产机制。

18 个稿内去重原文位置唯一存在，正文等于最后 draft，YAML SHA256=`eec062bbe48c79482e21452ff7a4858ecb84bb6e34ce11d96f825160a4ab815a`。首 check 的 3 errors 来自把 search receipt 当原文 ref；最终换成真实 L69/L70/L71 引用，没新增证据查询。最终 0 error / 0 warning / matched 不证明输入链完整。coverage 是 6 个模型 reviewed + 1 个系统未调查静态自检候选。

input **1,438,560**（cached **1,315,328** 已含）、output **13,687**，总 **1,452,247**；wall/e2e **304.88 / 308.64 秒**，45 次工具、222,176 返回字符、7 次拒绝、1 次完全重复。相对同题 raw 两 rep 均值 **增加 2.71%**，本次没有达到节省 token 的目标；D1 也从 V9 两稿核心通过回退为 partial，不能据 source 更新预判更好。

## Splash rep1

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v10/splash/runs/tools/rep1/verdict.yaml)于 21:56:16 UTC 完成，确认完成后读取。**S1 partial、S2 pass**。S1 原事实细项 2 supported / 1 partial / 1 omitted；S2 为 2 supported / 1 partial。

这次模型确实跟进了 recovery 的两次候选脚本：transcript L126/L142 分别返回 L346 的输入和 `ok SplashPage` 同 ID 回执，L112/L143 返回 L485 输入和 `ok` 回执。前者先写 `onWillDismiss` 再报告，后者先写 window/helper、入页隐藏和 disappear 还原再报告。最终分别为 S1_E1/S2_E1 独立事件，并准确说明正式 v52 只新增 NavBar 兜底、v53 只新增 onRoute 还原。没有重复 V9 rep1 把脚本隐藏/import混成v53新增的错误；不是只看候选摘要后声称查过。

S1 的 Slice11@v26 指向真实 D020 注释重申及 isModal 错误判断，未再挂无关 v38。但 entry-setup 部分只概括 Navigation/pageMap 装配、引用 L121/L155，没有追 L123/L124 真正删除 callback 的动作；它也没有调查或报告 builder 后置成功构建。因此按同一 mandatory 口径仍 partial。报告没有明确说池内从未构建，不把该漏项改判相反事实。

S2 已有早期 ui-manifest@v1、实际生成 meta/skill 输入及传递缺口说明，入页隐藏与两个恢复点的实际写入都处理，core pass。未回到主会话更早 L404 原始主题回执仍只是细项部分；不要求某一特定 locator 才能证明早已有。

但完整红节点标注尚不足：报告将 converter@v1 标 **进入·缺**，同时明确“具体要求没有充分传递到生成输入”，counterevidence 又说 `needs_immersive_safearea=true` **不等于隐藏系统栏**。现有材料支持全局主题→生成输入的缺口，却未确定缺口到底在上游提炼/派发还是生成方已获等价要求却遗漏。把精确红进入点落在 generator 仍需要更多依据。这不是要求必须收到某个 API 拼写，也不是证明生成方绝无隐式要求；记录为 `unsupported_causal_claims / material_annotation`，不伪装成已证相反历史事实。S2 核心回答与完整可审计归因分开。

一个错误原文引用尝试 `#aa2d...:16295@L273` 被拒，模型后用 id+seq 获得正确 L227，最终引用已纠正；没有拿失败调用冒充成功打开。最终 16 个稿内去重原文标签/行均唯一存在，raw=最后draft逐字，YAML SHA256=`d8e8058a5848d94f4c62a6cc8303ded5a53d2e3cabafc765f9bd191434269063`，identity bound、reference matched。check 仍有 3 warnings：两个正常修复事件列作进入点、一个中性后置引用，不是 schema 失败也不是语义通过。

coverage 是 4 条模型 reviewed（2正式差分+2真实脚本）和 25 条系统未调查补集；没有伪称补集已阅。48 次工具、457,446 返回字符，成功打开 converter、Slice11、fixer，未打开 entry-setup 或 builder；8 次搜索带池末 until。

input **1,964,353**（cached **1,741,312** 已含）、output **11,168**，总 **1,975,521**；wall/e2e **267.52 / 281.45 秒**，对 raw 两 rep 均值减少 **40.24%**。这是 rep1 观察，不能抵消缺失的装配/构建责任链或尚不足的红进入点。

## 本轮边界

三个 V10 legacy rep1 全部完成、无 pending。S3 的 H5 例外、Splash 两真实脚本及其独立事件是具体改善；Member 原始 Slice8 输入仍漏、Dice 生成输入回退、Splash entry-setup/后置构建仍漏，不能宣称正确性与成本联合验收通过。未来 entry-effect 校验没有参与本次评分；旧 V9 评分没有改动。

## Rep2 追加（按各案完成顺序，最终均已完成）

本节独立追加，以上 rep1 与 V9 原判不变。运行中的案子只检查 completion 字段，不读 events、草稿或先行评分。

### Member rep2

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v10/member-center/runs/tools/rep2/verdict.yaml)于 22:20:46 UTC completed、verdict_ok=true。**S3 pass / S4 partial**，原事实细项合计 4 supported / 2 partial。

S3 仍正确给三站点 1 透明 + 2 深色，并明确脚本执行/自报计数、Pay局部读回与设备验证的区别；但这次又没有点名 H5 原有透明并跳过，按既定 minor，不能用 rep1 已补全替本稿补答案。S4 仍只有修复方后期读回、finding/attempt，没有 Slice8 写前 Kotlin L21/L24→错误整写 L264/L265 的调查；因此 partial。两次 agent 调用（builder/fixer）都因 via=sessions 被拒，无成功 agent，所有实际原文调查仍集中在后期 fixer/builder。

改善是成功构建这次没有停在 say/通知：先查 `COMPILE RESULT:PASS` 零命中后，实际打开 `#af0e3d2ae54dbf769:17296@L36`，transcript L147 返回原生 `EXIT=0` / `BUILD SUCCESSFUL in 6 s 859 ms`。private helper、两次去 private Edit 与该构建时间顺序对应，仍不认证视觉像素。本稿没有重复 rep1 的“非 selected”分支标签错述；rep1 的错误原样保留，不被第二次消掉。

14 个事件（S3 五个、S4 九个）、无版本 nodes，不代表调查完整。tail `#15731@L592` 单列 S4_E4，承认执行并用后续编译佐证，无伪 v40/v17。4 个 reviewed 候选与 manifest 原始动作逐一对应；14 个稿内去重引用均唯一定位。raw=最后实际draft逐字，YAML SHA256=`6666972978a72bb48824b1b17ad76deda25c5f50eea578bee524c701cdf618b1`，身份 bound、最终 matched。两个 check 间只删进入点列表，没有新增证据；6 个冲突 warning 清零不是近因通过。

coverage 为 8 条模型 reviewed + 30 条系统未调查补集，无 not_repair。input **648,570**（cached **544,768** 已含）、output **15,854**，总 **664,424**；wall/e2e **331.38 / 344.76 秒**，41 次工具、150,113 返回字符。Member 两 rep 总 token 均值 **1,199,597.5**，对 raw 两 rep 均值减少 **55.42%**；两次同为 S3 pass / S4 partial，未满足完整正确归因。大幅成本差异不是单次可以消除的随机性或质量证据。

Dice rep2 最近 completion 检查仍 starting；Splash rep2 尚未完成，暂不计入本节分母。任务继续到这两份完成后追加。

### Dice rep2（22:26:09 UTC 已完成）

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v10/dice-entry/runs/tools/rep2/verdict.yaml)：**D1 pass / D2 pass**，原事实细项 5 supported / 1 partial，但**完整标注不通过**。这次实际成功打开 generator@v2、bridge@v4、observer@v3，页面/F001/沉浸式与修前 Entry/SDK 输入都补回；D1 不再是 rep1 的输入漏项。观察者的原生编译/打包已核，WARN 仍是 minor。

附加实质错误与 V8 的固定判例相同，必须独立保留。D2.boundary 原句：

> “没有把后续记忆文件 .ecat/agents/generator/memory/arkts-app-shell/_index.md 的沉淀作为当时修复依据；它发生在修复后，只能说明该要求后来被记录。”

原始 `257fed22...jsonl` L115 在 **21:12:47.694** 写同路径 `_index@v1`，正文已含全局异常观察者条目；L119 在 **21:12:53.922** 写 feedback。observer 三 Edit 是 **21:19:24–39**。本次 search 只从 21:19:39.888 开始，transcript L135/L174 返回的确是后来 a329e202 L95 的 `_index@v2`，但它不能抹掉更早 v1。报告没有限定“v2这次改写在修复后”，却据此排除当时来源，属于 material `memory_feedback_wrong_time_exclusion`，不是小漏项。

正确边界仍是：早于修复不等于证明 fixer 实际读过，但不能用错误时间排除。直接 ECAT worklist→SDK/实现→构建的核心主链成立，所以沿原尺度保留 D2 core pass；不临时增加 memory 为旧 oracle 必答项，也不因此宣称全报告正确。

D1 本次只展开旧 Step4 `ui-report@v1` 和 L199 带参数启动，交代当时 UI 10 条 beforeEach ERROR、0/10可达；没有再开或报告后来 593d L260/L267 的 10/10等价回放。该后置事实按固定 addendum 列全量缺项，旧阶段 0/10 本身真实；报告未说所有后续永远0/10，因此不造一个相反断言。AppStorage 内部值/observer callback 未验证的边界仍正确。

23 个稿内去重原文引用与唯一候选都定位到正确动作。候选 `#4520@L51` 确为 git diff stat + grep 自检，not_repair 有原文支持。raw 等于最后 draft，YAML SHA256=`c9692b85a129367a403152bbd79b50b43a2bf78e81c260d2cd0c9febb2cbbaa7`。两次 check 只改进入点列表，memory 错述原样留存；最终0 error/0 warning、matched并未核语义。

input **1,295,771**（cached **1,176,064** 已含）、output **14,745**，总 **1,310,516**；wall/e2e **309.01 / 312.58 秒**，48 次工具、208,244 返回字符。Dice 两 rep 均值 **1,381,381.5**，只比 raw 均值减少 **2.30%**，不达20–30%成本要求，且有实质归因错误。Splash rep2 仍待完成，任务继续。

### Splash rep2（22:31:19 UTC 已完成）

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v10/splash/runs/tools/rep2/verdict.yaml)：**S1 partial / S2 pass**，原事实细项 4 supported / 2 partial / 1 omitted，**不代表本案归因正确**。

S1 恢复了 Slice11 v38 的协议页回跳实现、group2 后续状态与修复候选/正式 NavBar 兜底，并打开后置 BUILD_STATUS PASS 通知。但完全没有交代 entry-setup 删除 callback 与 D020，也没有解释 Slice11 的 isModal 判断如何被 finding 反驳；叙述缩成 popInfo 返回链，原 mandatory 缺口仍在。S2 采用明确生成前时间窗，早期主题存在/生成方实际输入未证主题细节分开，generator 改为无法确认，不再强定红进入点；隐藏/helper 脚本与 v53 正式新增恢复调用也分开，主链可通过。没有独立设备复验的边界正确。

新增一条**确定的实质作者误归**。报告 group2-closer@v45 的原句：

> “group2-closer v46 改写/补强 openAgreementPage…并把判定改为 vm.privacyDialogVisible”

所引 `#b7ebd5ae592d3c5d:9242@L351` 的原生 Edit（`toolu_01J61BUS87ognmrTzXEAdQAk`，16:50:28.209）只在函数开头加入空 URL guard 和“不走 WebViewLauncher”的说明，没有更改回调判定。真正把 `reopen && !PrivacyGateReady.agreed()` 改成 `this.vm.privacyDialogVisible` 的是更早 **Slice11 L239**：`toolu_017jShgEerwM5aHzA8aS1eBs`，16:00:45.985，原始行 SHA256=`4dfd6c4851780fcb8a29b6f051905d10801b80783c158a6e3a359f3c6a21fd6c`。

本次只打开 file@v46 快照；快照中存在这一判定，不证明 v46 的 writer 新改了它。node@v45 与 L351 本身可定位，也不能替该说法提供语义支持。按冻结口径保留 S1 core partial / 原分母，不把新增 group2 支线临时变成核心必答项；但 `wrong_actor_for_specific_change` 明列 material，完整可审计归因不通过。

S2 “把还原动作移到 onRoute”的文字也宜精化为“新增主要触发点”：v53 diff 只增加 onRoute(true)，原 disappear(true) 兜底未删除。整段没有明确宣称删除旧调用，可理解为主要时机调整；不因这一非唯一口语读法硬加 core fail 或 material false。

L346/L485 本次打开的是输入而非独立 output；工具头报告成功、脚本包含写入，原始同 ID 回执仍在池内。报告按修复阶段说明效应，未假称本次读完全部回执或已设备复验。两条 event_claims 是 finding 来源事件；普通节点里的修复引用和实际脚本仍需分别审，不能只数事件多少。

12 个稿内去重原文标签/行全部唯一存在，raw=最后draft逐字，YAML SHA256=`6af26037a83cacbfcef2964d7f21392763f3473c20991e6dd56c91974b05a1b1`，identity bound、reference matched。第二次 check 只改进入点列表；4 warnings→0，没有新增原文，也没有纠正 group2 错述。coverage 2 条模型 reviewed + 27 条系统未调查补集，没有把补集称为模型已阅。

input **1,538,158**（cached **1,385,984** 已含）、output **14,047**，总 **1,552,205**；wall/e2e **306.59 / 319.93 秒**，44 次工具、250,436 返回字符。Splash 两 rep 总均值 **1,763,863**，对 raw 均值减少 **46.64%**，但两次均有 S1 mandatory 漏项，且本次有实质作者误归。

## V10 六跑封存汇总

| 文件 | Rep1 core | Rep2 core | 两 rep 平均总 token | 对同题 raw 两 rep 均值 |
|---|---|---|---:|---:|
| Member | S3 pass / S4 partial | S3 pass / S4 partial | 1,199,597.5 | -55.42% |
| Dice | D1 partial / D2 pass | D1 pass / D2 pass | 1,381,381.5 | -2.30% |
| Splash | S1 partial / S2 pass | S1 partial / S2 pass | 1,763,863 | -46.64% |

核心 7 pass / 5 partial 不等于归因全部正确。rep1 Member 条件标签错误、rep1 Splash 未充分支持的红进入点、rep2 Dice memory 错误时序排除、rep2 Splash group2 具体变化作者误归全部保留；两个 material false claim 独立否决联合验收，不能被更多未知或较低 token 抵消。没有 pending V10 legacy run。本文件及 JSON 评分现封存，可提交；后续变体必须另开文档。
