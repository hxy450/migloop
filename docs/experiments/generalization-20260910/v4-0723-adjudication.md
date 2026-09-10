# tools-v4：0723五文件、两重复的独立证据裁决

这是旧开发集的AI审阅，不是人工双盲裁决，也不是新13文件留出评测。没有读取新留出gold，没有改runtime、冻结core、模型报告、旧grades或原raw基线，没有模型调用、重跑基线、冷建账本或执行历史命令。

范围：`F10-01/02/04/05/06`各rep1/rep2，共10份。均在metrics.status=completed、postprocess.status=completed及verdict产物齐备后才裁决；未用未完成答案计分。schema、引用和图的机检与因果语义分开，机械无效不自动变major，机检有效也不自动变correct。

## 冻结合同与文件

- core：`EVAL/baseline-v1/private/scoring-core.json`，SHA256 `0d48f30f9e501eedd55b87e086590c72e8b7fb8096a939f56842b71703426497`。
- tools-v4 manifest SHA256：`213d7b657a91602db7c777f963eca47c4dcc044340e3fcf6667f7f555f1586c0`。
- EVAL：`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10`。
- 新裁决：`EVAL/tools-adjudication-v4/<case>/repN.json`，没有覆盖此前arm的裁决。
- 原始对照：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/member-center/pool`。必要原文回核涉及12个不同源basename；生成与后置修复时刻分开。

全部10份已执行`score_raw10.validate_grade(base=tools-v4, contract_base=baseline-v1)`，核对report SHA、core SHA、每个必需unit及所有decision的精确report_spans。另逐条核对unit/claim证据的原始行timestamp、call_id和短引文，0个字面不匹配。机械核对不替代正文因果裁决。

## 结果（仅此五文件子集）

| 文件 | rep | C/P/M/W | 支持主张/事实主张 | major | 核心pass |
| --- | ---: | --- | ---: | ---: | --- |
| F10-01 | 1 | 2/2/2/0 | 4/4 | 0 | 否 |
| F10-01 | 2 | 2/2/2/0 | 3/3 | 0 | 否 |
| F10-02 | 1 | 1/0/3/1 | 1/2 | 1 | 否 |
| F10-02 | 2 | 1/1/3/0 | 2/2 | 0 | 否 |
| F10-04 | 1 | 2/0/0/0 | 2/2 | 0 | 是 |
| F10-04 | 2 | 2/0/0/0 | 2/3 | 0 | 是 |
| F10-05 | 1 | 1/0/0/0 | 1/1 | 0 | 是 |
| F10-05 | 2 | 1/0/0/0 | 1/1 | 0 | 是 |
| F10-06 | 1 | 2/1/0/0 | 3/3 | 0 | 否 |
| F10-06 | 2 | 2/1/0/0 | 3/3 | 0 | 否 |

小计：16 correct、7 partial、10 missing、1 wrong，共34核心单元；支持事实主张22/24；major 1；核心pass 4/10。此子集文件/重复等权correct coverage为64.0%，按unit汇总为16/34=47.1%，二者口径不同。不要把这些子集数字冒充全20跑、总体准确率或工具提升。明确hypothesis不进入precision分母；一条因果链的重复node/edge文本去重，不逐节点重复计错。

## 核心判断与正反证

### F10-01 MemberCenter：两个rep均2C/2P/2M

- CTA和indicator正确。原生fixer L436/L437把横向margin改为外层Row padding；L528/L529加指示器显式色彩/位置，L532/L533补常量。不因纵向margin仍保留、或未知更早唯一作者而清零。
- mask和images均遗漏。fixer L103/L104按用途补透明/深色mask，本Member三处、Splash一处；L233/L234对既有图补比例/尺寸，均有本目标成功输出。不能从工具未认证候选就认定它们未发生。
- price为partial。两份都解释统一30与数字/后缀分段，但未恢复生成期输入已送达仍未落实的关系：Slice8 L24（2026-07-24T15:33:51.671Z）确实读到`showNowPrice.replaceSpan`和`AbsoluteSizeSpan(30,true)`，L264（16:04:37.440Z）仍全串fontSize30。泛称读页面/XML、或只用后期fixer读到源码，不能替代这半条归因。
- repair-compile为partial。实际链是fixer L592新增private价格helpers、L593成功；compiler L24报`Property 'priceDigits' is private...`（priceSuffix同样），L32/L34去private，L37构建成功。rep1仅归到编译验证环节，rep2甚至保留必要性未知；两者都未解释返修新helper跨struct访问这一核心机制。没有因未知就判wrong/major。
- rep1承认L592脚本成功，只说candidate_effect未认证独立净修改，不误读为执行失败。rep2的假hash/自环/引用格式另审，不用来自动增加语义major。

### F10-02 Splash：rep1 1C/0P/3M/1W；rep2 1C/1P/3M

- 两份系统栏局部生命周期原因均正确：fixer L485/L486先加进入隐藏、消失恢复和helper；L488/L489再在onRoute恢复，因为Navigation宿主压子页不销毁。核心不强制推断最早唯一责任或每条辅助接线。
- rep1的major来自实质错归，不来自role或格式。报告称“但生成后的实现把 isModal 等同于系统返回键拦截，实际行为未达到要求”，并把converter设为该原因的生成输出，随后将L352复位当直接BACK关闭修复。原始conv L71完整Write有`.onBackPressed(() => true)`、没有isModal/controller；entry-setup L123/L124装配时删除处理；Slice11 L236/L237后加控制器及“isModal:true 让弹窗吃掉系统返回键”错误假设；fixer L346/L347才补onWillDismiss，L352/L353另补协议页返回复位。去重只计一个major，没有从初版handler存在推定它已运行正确。
- rep2正确看到初版handler和协议页无result pop的复位问题，但未恢复装配删除、后续Slice11假设及关闭拦截这条中间链，因此back为partial；未照抄rep1的wrong标签。
- mask/icon/progress三核心均漏。L346同时给既有Progress补strokeWidth/enableScanEffect，不是新增缺失业务进度。rep1结尾限定“进度条缺失”finding缺少修改证明，没有直接断言无任何绘制修改；不额外造一个major。

### F10-04 EntryAbility：两个rep均2C

- 两份均区分既有debug/release业务分支的启动漏接，与返修先误挂F013Service.setDebug再因编译改AppTrackConfig。原生R5099→R5110→R5123/R5126及成功返回相符；生成期Slice2 L169已读到HttpLog默认false及入口setDebug规则，允许更早唯一责任未知。
- rep1“记录中未交付…/未在已展开记录中确认”限定当前交付，不当全池无构建。
- rep2另有事实断言：“没有观察截止前的独立成功构建或运行行为验证可供本调查重新确认。”R5131（2026-07-25T01:56:28.547Z）明确原生`BUILD SUCCESSFUL in 5 s 498 ms`反驳其观察窗成功构建否定。计contradicted、major=false：未据此倒归生成者或伪造运行成功，也不把成功构建等同独立登录/行为测试。该句与rep1的明确“未交付”限定分开处理。
- aentry-setup L68/L70实际是imports/WindowModel与onWindowStageCreate的Edit，不能单独认证它创建整个onCreate。报告对“生成结果漏接”的主要局部原因成立，未据此认唯一最早遗漏者；细部引用边界单列，不仅凭origin/边的结构标签追加major。

### F10-05 F003Repository：两个rep均1C

两份均把有意挂起、真实后端阻塞与后置测试解锁区分：Slice2 L1明确“保持挂起、不要臆造取值”，L193实际留空且标D010；更早root R930有ANDROID_ID不能为null的失败；R5203加持久随机16hex并明确测试范围，R5214/R5221接入目标文件且成功。rep1未逐字引用派单，但明确将生成输入/方案描述为待决platform gap，不以字词缺失清零。两份都未把替代物认证为最终Android/后端等价方案。

### F10-06 Guide：两个rep均2C/1P

- 返回图内容尺寸与含padding外框混淆正确：conv L64已写24×24+padding20，Slice15 L181沿用；后修L168改成10×16内容加双侧padding。报告定位到真实初版而非只怪最后重写者，不要求逐笔复述全部版本。
- bottom inset正确：L580/L581实际加在宿主Swiper，统一给六子屏底部避让，不是修改finding建议的子按钮。更深WindowModel机制或首轮唯一责任不是满分必需项。
- track为partial：都解释20dp占位框与4dp轨道，但仍未把原始输入传递接上。资源actor L155已读完整drawable的4dp；页面actor L39成功收到的mapping给了颜色、渐变、radius和自定义Stack建议，却遗漏4dp；随后L64仍用100%填满20高。此局部传递证据不等同整个生成池没读过4dp。两报告的读取未知按上下文限定页面actor，没有扩大罚成全池否定。

## 实际交付诊断（不自动改变语义分）

以下仅据`query-trace.json`中真实receipt的`items.delivery.records`，不把引用入口/指针当完整正文已读，也不从未记录某段反推用户永远不可获得。

- Member rep1步骤7的首个changes(limit100) deferred；后续继续查询。步骤15交付L592 input/L593 output各240字符preview_or_pointer，以及compiler L32/L34 input各200字符，但未见L24编译错误或L37成功结果的raw_segment。rep2所核交付表同样未见mask/images/private-error关键正文段。
- Splash rep1步骤11完整交付L352（2064字符），其原文明确是协议页返回；L488只交首1173字符并留next_offset。未见初版/装配/L346完整链。rep2步骤16已交付完整初版L71（7805字符），故它确实更正了初版有handler；中间装配/L346仍未见正文交付。
- Guide rep1的L39只有240字符preview_or_pointer，L64首8609字符后仍有next_offset；rep2把L64经5000+3943字符续完，并读完整L168，但未见L39完整mapping正文交付。原文中完整mapping确实存在，不是历史信息消失。

这些是已送达证据范围的定位，不是对具体工具改动的因果效果实验；不据此声称已经证明“某优化必能消除所有漏查”。本次没有新增会改变冻结core的真值发现或评分修订。后续若复核语义边界需更改未发布裁决，应保留原件与hash后作审阅修订，不改模型报告或静默回写旧arm。

