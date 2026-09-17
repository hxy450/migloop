# 新case-card skill：单次运行首稿→终稿语义审阅

审阅者：`audit_ablation_measurement`。依据 [case-card-single-run-plan.md](case-card-single-run-plan.md) 与封存 [Member参考](product-pair-member-reference.md)；参考SHA256为`D2B5AA9C3B83A51806E21E17A1B14324DA62C8E7057351477F034E1879A9164A`，未修改。

这是同一skill流程内的前后稿比较，**首稿已经收到skill并知道后续校验，不是纯无指导raw**。两次独立运行之间也不能排除随机性/调查时间差。只在各自metrics标记结束后读取该轮内容；调查期间仅轮询完成标记，没有给调查员反馈。

## 1. 自由调查轮 member-v1

根：`C:/Users/hongy/projects/_migloop-case-card-20260915/member-v1`。完成1429.36秒；最终report `31ed2132fa284cb7`，mechanical valid/path complete，语义仍需独立审阅。

### 首稿取法与审计资格

- 真首稿是`runs/inquiry/rep1/events.jsonl:145`的`item_73`，对应native transcript:530，2026-09-15T03:37:41.319Z。17节点卡被schema拒绝，没有入库；拒绝原因是file→file/self连接及引用不存在的18/19号节点。没有改用第二次首个成功保存稿。
- 审计提取：`reviewer-only/actual-submissions.json`数组[0]为首稿，[3]为终稿；[1]/[2]是中间稿。最终submit位于events:165/native:615，03:44:20.574Z。
- `audit_inquiry_usability`核实实际调查为MCP；2次shell仅读任务/新skill，33次investigate、38次page、4次submit；隔离未见越界，fresh Luna/high，过程中一次compaction。首提交后没有新investigate/shell，只有反馈page；已有证据可以复用，因此这本身不是违规或未复核的证明。

### 六家族

| 家族 | 真首稿 | 终稿 | 依据及变化 |
|---|---|---|---|
| images | omitted | omitted | 两稿未解释目标两张活动图的实际尺寸/比例修复；不从附文中自动替模型补答案 |
| cta | established | established | 首稿N2已明确C实收XML的match_parent、横20/上20/下17；N4给出C的100%+margin输出，N14给出F:436的Row/padding修复。终稿保留。垂直及传播错误另列 |
| price | wrong | wrong | 两稿都明确把含“/天”的整串30号错误归到C初写，并把S8称为保留。C61数字占位/￥16的反证未处理；详见下文 |
| indicator | established | established | 首稿N7已给出S8实际读到START、margin、black30/black50和style，N8指出其Write仍只设置尺寸，N14对应后修。该充分输入→保留偏离链在首次submit前已完成，不是反馈后所得 |
| mask | omitted | omitted | 未解释本页mask修复与生成输入；个别句子泛称编译未回退mask不算归因 |
| repair-compile | established | established | 首稿已具体定位F新增private helper→ProductItemCard跨struct调用→B去private/编译成功。终稿仍在summary、N15/N16及附证保留此链，但正确的F节点说明/着色被削弱 |
| 合计 | **3 E / 1 W / 2 O** | **3 E / 1 W / 2 O** | 无bounded_unknown；无家族级净增 |

E/6不是首次生成节点ACC；repair-compile属于返修新生。indicator认可S8实际充分输入下保留的边界，不强迫全历史唯一作者。另作的错误首次归责不会被总完成数隐藏。

### 核心未纠正与正确改坏

1. **价格首次归责未纠正。** 首稿summary/N4明确“初版含/天整串30”“首次已证引入点”，N8甚至称S8“没有引入第一份内容”；终稿N4仍说初始转换把金额与后缀合并30，N8仍传播初始偏离。C:61内容52限定priceText为数字598，112/135–139待业务接入，545–556是￥16＋数字30，默认数据为空；C:65–74没有接入后缀。S8:264内容351才接入stripCurrency(showNowPrice)，1080–1081仅去货币符号。明确反证不因树可加载而消失。
2. **正确字号字段被改错。** 首稿和第二稿N3正确区分tv_product_price16、rollingTextView30、tv_price_day14；第三稿开始改为“价格后缀14sp”，终稿照留。C:21的14是独立日均价条，不是价格后缀；该新误述与已附原文冲突。反馈没有要求改字号，此变化不能说成校验纠错。
3. **新出现的修复后仍待修状态。** 首稿N9位于S8 Write时刻，作为待修状态合理；第三稿把N9移到2026-07-26T21:22:55.328Z，仍称CTA待修，终稿保留。但F:436–437已在21:16:18.424/21:16:21.471完成CTA改动；新附F:514/516只看indicator/price，没有CTA。它修好了寻找真实读取时刻的形式，却没有同步修正内容状态。
4. **CTA finding借用了别的读调用。** 终稿N13→F强制边使用F:501＋V:349，前三个indicator/price finding也用同组证据。F501命令列的是两个indicator finding、price finding、WebView图标finding，不含CTA；V349是verifier写入包，不证明F收件。因此该CTA专属读边无所引原文支持，不能把机械valid叫四份finding输入均闭合。
5. **有条件的软化不是完整纠正。** 首稿summary把“过大的底部安全区/间距”当生成偏离，终稿summary删除此因果断言、缩到横向布局；但N13仍将finding与横向100%+margin混写。V:349的Member CTA finding实际记录上移、按钮变矮、留白大，处方是改高度/底padding；F:628另把垂直偏差类比动画采样，并把横向修复列为旁观缺陷。没有核出此区别，不能记为垂直根因已解决。
6. **正确归责展示减弱。** 首稿N14对F明确标problem并解释其新生private错误；终稿N14删掉这段，改把下游文件N15标红。summary/N16仍足以保留repair-compile的E，但不应宣称F归责展示改善。同时正确的finding输入N10–13由非problem改红，未说明这些报告本身为何有错，混淆“报告了问题”与“报告作为输入有问题”。

### 反馈实际促成了什么

- 首稿schema错误后，第二稿纠正节点编号和连接，真正把S8、F、B放入读写链；这属于结构/连接纠正，不能当作新增归因。
- 后续反馈指出消费方在旧cutoff下没有确认读取、脚本边未解析、B节点cutoff不足等；后稿移动目标/报告读取时刻、扩展B截止时刻，并最终对6条边附上脚本依据。三份indicator/price finding的F501读调用及F436/528/592写调用确实存在，属于证据挂接改善；CTA的错误共用边及待修状态例外如上。
- 第三稿改reason/着色时出现后缀14等新错误；校验器没有指出其语义正确性。不能把“发生在反馈之后”全都算成“反馈发现并纠正了归因”。
- 据机械审计，第三稿反馈`4b422bf38a3f48c7`仅送达0:11686/13892，native:603末尾仍有next=11686，余2206字符未读便第四次submit。第二稿反馈完整读过。故不能宣称四步反馈复核流程已完整执行。

阶段结论：此轮证明了从无效连接到机械可加载的改善；没有证明六家族归因净提升。重要首次归责错误保留，并发生正确字段改错、读取状态错移等退步。

## 2. 直接原始材料轮 member-direct-v1

根：`C:/Users/hongy/projects/_migloop-case-card-20260915/member-direct-v1`。完成1625.78秒；最终report `1461e904cd684b8f`，mechanical valid/path complete。只在完成后读取稿件。

### 首稿取法与审计资格

- 真首稿为`runs/inquiry/rep1/events.jsonl:54`的`item_27`，native:201，2026-09-15T03:35:36.342Z；14节点、schema拒绝。短agent名及两条file→file/self连接已同时被首反馈指出。最终为events:178/native:663，03:55:28.329Z。
- `reviewer-only/actual-submissions.json`共16项，[0]是真首稿，[15]是终稿。6次schema拒绝、10次保存均保留，不挑有利中间稿。最终12个作者节点加自动target共13节点、14条绑定边、3条force。
- 独立机械审计核实48次shell（首稿前23、之后25）、15次page、0次investigate；shell只涉及隔离任务/skill/原始pool，page只取自身反馈。实际Luna/high、fresh、无fork；技能全文实际送达。配置按`direct-mode.json`实际sidecar核对，不把prepare基础配置不同算污染。详见该轮`reviewer-only/isolation-and-submission-audit.md`与`submission-mechanics.json`。

### 六家族

| 家族 | 真首稿 | 终稿 | 依据及变化 |
|---|---|---|---|
| images | omitted | omitted | 未解释目标活动图的高度/比例改动；recommendations泛称Image检查不算调查结论 |
| cta | established | established | 首稿summary/N2/N4已将C读Android布局、match_parent横margin直译100%+margin、F改Row/padding串起来；C:19、C:61及F:436支持此窄判断。终稿保留。finding数量、动态纵向及force引用错误另列 |
| price | wrong | wrong | 首稿N4明确说初始生成代码造成价格后缀大，并称S8保留；终稿N4的“具体已证偏离”与summary/N6继续将单一价格Text当初始错误传播，没有区分数字占位与S8接入showNowPrice。C:61、S8:264反证与自由轮相同 |
| indicator | partial | partial | 解释默认位置/颜色、后续修复及S8保持同形代码；但没有建立实际充分正常输入→这一偏离的边界。C未读Activity的有限材料缺口可以保留，不能替代S8:24已实际读到START/margin/颜色再Write的证据。模型未说这条链，审阅者不补写；这不是全池真实缺证的bounded_unknown |
| mask | omitted | omitted | 未解释3处mask修复或RenewRule实际收件；不从自动附文代写 |
| repair-compile | established | established | 首稿summary/N12/N13已具体解释F新增跨struct private helper→2条编译错误→B去private且PASS；终稿保留，B:24/29/32–35/54支持。具体中间版本时间有纠正，不等于首次发现这一因果链 |
| 合计 | **2 E / 1 P / 1 W / 2 O** | **2 E / 1 P / 1 W / 2 O** | 无家族级净增；修复新生项仍单列，不凑首次生成ACC |

这里不因短agent名/schema错误降低首稿语义分，不因终稿树短而扣分。CTA的正常输入可以由简洁原因和实附布局共同支持，不要求复制全部XML属性。indicator的P则是实际欠缺输入判断，不是篇幅不足。

### 实际纠正、保留错误与传播边界

1. **确有时间/证据纠正。** 首稿N12把“固定两个Span、跨struct helper”的修后版本放在21:24:34.699，但F:528此时写的是动态ForEach/`splitPriceRuns`；固定两个Span及`priceDigits/priceSuffix`要到F:592–593的21:30:17.239/20.292才出现。第8稿将对应文件cutoff移到21:30:20.292，第11稿移到B实际Read的21:45:55.438，终稿保持，消除了这一提前挂版本错误。G2截止从首稿16:50:09.346移到16:50:21.022，也覆盖了实际第二个import Edit。B截止最终覆盖两次Edit及PASS，不再仅到第一次Edit。
2. **核心价格归责没有纠正。** 首稿把“单Text已有”直接当“后缀字号缺陷已发生”，终稿虽缩短措辞，仍明确C输出是已证偏离、S8是传播。C61的数字598、空商品列表和待接入业务状态不能证明含后缀错误；S8:264内容351接入`stripCurrency(product.showNowPrice)`才改变实际输入条件。终稿没有合理等价地撤回这项首次归责。C未读Activity这一窄事实本身可以成立，但不能据此把尚未接入的后缀错误提前实证化。
3. **未查与缺证没有解决。** 两稿都正确保留“spec没有指示器颜色/位置和Span细节”的限制，但未利用S8:24的真实Kotlin收件。最终“完整要求缺失仍是已证生成期边界”只适合限定C该次输入，不能概括所有生成期责任方；没有把这条正常输入补上，indicator仍P。无需继续追唯一首作者，也不需要把全部Activity机制塞进树。
4. **删节点不等于纠正错误计数。** 第3稿删除首N10 finding索引节点和冗余终态文件节点，解决了file→file结构问题；但“五项P2”一直留在summary和最终N10。F:19索引的Member条目实际只有4个（2个indicator、price、CTA），CTA横向100%+margin是F:628明确另列的旁观修复，不是第5个观察finding。删除索引节点还减弱了可见的修复要求输入，不能算发现/传播链更加完整。
5. **force读证据是真实局部读取，不是这些缺陷的完整读回。** 最终N9→F附F:106，确实读目标文件，但仅`sed 704,725`的PayAgreement段，描述为Verify edits；它发生在F:103–104已改mask之后。不能据此认定读到了price/indicator/CTA，也不能把N9当完全未经后置修复的G2终态。N9新增“视觉偏离仍待观察”也晚于已有V观察报告。保留下来的相关视觉问题仍可能待修，但历史内容/观察时序不是卡所暗示的完整不变传递。
6. **force写证据有过度概括。** 最终N10→N11只附F:528，确实是price/indicator脚本写；其reason还称该调用改了CTA，但CTA实际是F:436。F528也不是固定两个Span/helper的最终改写（那是F592）。B:29实附读回可以支持模型已经写出的最终helper状态，故不抹掉repair-compile的E；但不能把F528一条引用宣传成覆盖三项全部写入过程。
7. **纵向根因有实际降调，但不是已证修复。** 首稿把动画相位/安全区称作造成观测差异的解释，终稿N11与建议改成需固定状态复核的未完成项，这是较审慎的限定；summary仍有“受…影响”的肯定口吻。V:349的CTA原finding与F:628的类比解释没有被独立实验闭合。可记录局部措辞改善，不能计入六族新增E或纵向根因验证。

### 反馈对应的改善范围

- 首3次无效稿修正命名、路径和无效file→file/self边；第5稿将初始Read request时刻改为实际return。第6/7稿还一度把后置F/B日期误写成7月24日，schema指出其cutoff前不存在证据，第8稿恢复7月26日。这是反馈实际指出、模型实际改正的坐标错误，但不是首稿原有的归责错误被发现。
- 随后的检查要求找到真实读写/消费时刻；第8–14稿进行版本及消费方cutoff调整，末稿为3条未解析关系加入原文force。版本提前挂接的纠正有实证收益；正确归因的主体内容早在首稿已有，价格过早归责没有因此改变。
- 经审计，第9次反馈只读6076/10728、第12次5371/7820、第13次5310/7214就修订。不能把“完整反馈后”的force自述当全部分页复核已完成的证据。

## 3. 两轮结论与复核坐标

| 运行 | 首稿→终稿 | 归因净提升 | 已见真实收益 | 不可忽略的代价/错误 |
|---|---|---|---|---|
| 自由调查 | 3E/1W/2O → 同分 | 0家族 | 无效图变可加载、部分真实读取/写入证据挂接 | 价格过早归责保留；正确后缀字段改错；CTA修后状态/收件挂接新错 |
| 原文直读 | 2E/1P/1W/2O → 同分 | 0家族 | 无效图变可加载、固定Span版本及截止时刻纠正 | 价格过早归责保留；五P2计数/横向finding混淆保留；局部读写被说成完整传播 |

两轮表明本次机械反馈可以帮助修图、定位部分真实事件/版本；**尚未证明同稿反馈能提升六家族归责准确率**。自由轮与直读轮的调查质量差异也不是本次随机化消融，不能据单次差异归功于MCP。首次稿已经受同一skill指导，不能叫无指导原始基线。

原文缩写使用同一历史池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/member-center/pool`。下列为JSONL物理行；“内容行”是该条Read/Write正文内部行，不混用：

- C：`9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aconv-member-08b3dcf6deb3c515.jsonl`。9(spec)、19(页面XML，内容183–200 CTA)、21(item字号)、61(初写，内容52/112/135–139/545–556价格占位)、62(回执)。
- S8：同generation目录`agent-aslice8-pay-80bbb1f44b77da0f.jsonl`。24(Activity实际返回：内容224–236 indicator、275–283 replaceSpan)、76(目标读回)、264/265(Write/回执：内容351业务价格绑定、399–407 indicator、561–568 CTA)。
- G2：同generation目录`agent-agroup2-closer-b7ebd5ae592d3c5d.jsonl`。73局部检查，345/346与349/350两次协议Edit。
- F：`ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-a68daf720e780b4c2.jsonl`。19索引、103/104 mask先修、106/107 PayAgreement局部读回、233/234 images、436/437 CTA、501/502 finding读、516/517 price/indicator读、528/529动态Span与indicator、592/593固定Span/private helper、628最终说明。
- B：同observation目录`agent-af0e3d2ae54dbf769.jsonl`。24两条实际错误、28/29目标局部Read、32–35两次去private、37/40构建输出、54回执。
- V：同observation目录`agent-a64594a2e464bd6af.jsonl`。349写finding脚本，含CTA实测/处方与indicator/price观察。

本轮direct提交引用的原文副本在`C:/Users/hongy/projects/_migloop-case-card-input-20260915/member-direct-v1/mcp/pool`，保持相同子路径/物理行。首稿与终稿均按原因及可核原文评审；自动附证可支持既有窄主张，但不让审阅者替模型新增未写的正常输入或首次归责。此文仅评审端使用，不修改封存reference、不覆盖full10、不反馈给调查员。
