# Member 三臂整产品对照：审阅端语义裁决

2026-09-15 UTC；审阅者 `audit_ablation_measurement`。仅审阅端留痕，不提供给调查员，不修改模型稿、产品或既有 full10 分数。

依据封存的 [product-pair-member-reference.md](product-pair-member-reference.md)，其 SHA256 复核仍为 `D2B5AA9C3B83A51806E21E17A1B14324DA62C8E7057351477F034E1879A9164A`。原始来源别名 C、S8、F、B、G、G2、V、O 和 JSONL/正文行号含义沿用该文件。

本审阅不是无历史先验的盲审；参考在本轮新输出前封存。三臂结果分别读取、核验，不用后完成的一臂补前一臂答案。

## 1. 纳入对象与资格

| 组 | 本次审阅产物 | 资格/标识 |
|---|---|---|
| raw-v2 | `C:/Users/hongy/projects/_migloop-product-pair-20260914/member-raw-isolated-v2/runs/raw/rep1/report.md` | 根代理已确认最终隔离通过：22次shell均在task/pool，无产品skill、旧报告或fork。本审阅不重复实施该隔离审计 |
| 自由产品 free | `C:/Users/hongy/projects/_migloop-product-pair-20260914/member-free-v1/runs/inquiry/rep1/verdict.yaml`及`verdict.json` | `bac5a70f070e443a`；纳入编译产物自动附证 |
| MCP-only | `C:/Users/hongy/projects/_migloop-product-pair-20260914/member-mcp-v1/runs/inquiry/rep1/verdict.yaml`及`verdict.json` | `0ce3bb6f2caa4132`；纳入编译产物自动附证 |

`member-free-v1/runs/raw/rep1/report.md`是被确认读过旧实验输入的污染运行，**排除**。此前对它的局部检查已停止，没有将其内容或成绩与raw-v2择优拼接。

## 2. 六家族最终表

| 固定家族 | clean raw-v2 | 自由产品 free | MCP-only |
|---|---|---|---|
| images | partial | established | established |
| cta | partial | omitted | established |
| price | partial | partial | wrong |
| indicator | partial | omitted | partial |
| mask | partial | omitted | partial |
| repair-compile | established | established | established |
| 汇总 | **1 E / 5 P / 0 W / 0 O** | **2 E / 1 P / 0 W / 3 O** | **3 E / 2 P / 1 W / 0 O** |

三臂均无可计入的 `bounded_unknown`。未查清实际收件、未解释某族、或笼统声明覆盖未闭合，不等于原始池存在不可恢复缺口。

E/6是固定六家族的有界解释完成数，**不是全文断言准确率，也不是首次生成节点ACC**。repair-compile为返修新生，三臂都成立但不能算作首次生成归责命中。首次作者、首次可见坏配置与后继充分输入下保留偏离仍按参考分开。

评分不要求raw有树、node id或逐字复制属性。清楚表达的局部机制予以保留；缺的是实际正常输入收件→偏离关系时判partial，不为追求对称错误数强判wrong。工具的自动附证支持已经说出的具体判断；原文中恰好存在某种补丁，不会自动给未解释的家族补分。

## 3. clean raw-v2

报告共59行，以下是该报告物理行号。

| 家族 | 改动/机制是否解释 | 正常输入→偏离、首次/保留及评级依据 |
|---|---|---|
| images | 12、32解释固有尺寸与ArkUI约束差异，并称纳入全仓修复；未具体解释本页两张width-only活动图补比例/高度 | 缺C:19对应XML实际收件、C:61坏版本的对照。已有该族局部机制，故partial而非omitted；也不能把其全仓“多处仅objectFit”的概括自动解释成两张目标图完全无width |
| cta | 9、33正确指出100%+margin与Row.padding修复 | 未把实际收到的match_parent+margin20输入连接到C或S8具体输出；partial。局部横向原因正确，不因无树或无引用编号扣分 |
| price | 11、34正确描述后缀被整串30放大及数字30/后缀16的修复 | 没有S8:24实收富文本代码→264业务绑定/输出的归因。其“初始迁移”未明确限定converter，不能替作者添加“C首次引入”再判错；partial |
| indicator | 10描述默认居中/蓝色和后修left18、颜色 | 没有实际样式要求收件的actor/操作对照。C已有默认配置、S8实收要求后保留的区别未说明；partial |
| mask | 13正确说明目标相关默认遮罩差异及加载透明例外 | 未建立生成期具体controller写者收到的dimAmount要求。参考中的S8:258 RenewRule合同不能由审阅者代填；partial |
| repair-compile | 14完整说明新增private helper、跨ProductItemCard调用、随后去private编译通过 | 对应F:592–593、B:23–24、32–40，返修新生归类正确；established |

额外核据与限定：

- 9称“动画缩放和底部安全区本身被确认是正确的”过强。F:431/434只证明动画代码和bottom padding存在；F:628将Member CTA类比为动画采样相位，独立的目标页复验没有完成。可说“此次未改、仍有竞争解释”，不能说整体正确性已确认。此错不抹掉横向局部解释。
- 41关于macOS大小写不敏感、Python dylib导致pipeline问题，并非无源猜测：G:4460、4520等有相关记录；G:5405实际读回FV-1只跑两个detector，5412有执行疏漏总结。保留其对流程记录的概述；不能进一步认定这就完成了本页五类缺陷各自的输入→偏离或唯一首次作者证明。
- 24准确注意到源码合成bounds与UI-only/禁编译边界；禁止converter单独编译不是它违反任务。16、59正确保留编译PASS不等于round-2视觉通过。
- 报告没有重犯“3个扫描命中减2个图片修复”的集合错误，也没有明确说C已收到完整后缀业务语义。本轮不把污染raw曾有的错移植到本稿。

## 4. 自由产品 free

N为提交YAML中从1开始的节点序号。

| 家族 | 模型已说出的判断及证据 | 裁决 |
|---|---|---|
| images | summary具体写出img3 width280/margin30、img1 width254/padding35均缺height/aspectRatio，以及后补840/942、366+35；N2实收XML、N5自动附C61/C73，N6附S8工作前态 | C:19内容255–263、342–353→C:61内容181–184、442–445及C:73的实际缺约束形态成立；声明的F修复值可由F:233–234核真，不需要补新归因。established |
| cta | 最终summary、节点理由均未解释100%+margin或Row/padding的实际目标修复 | 虽附文内有CTA代码，不等于模型提出其归因；omitted |
| price | summary解释Spannable被压平、后修两Span；N3仅说商品XML有16/30层级，N7明确“不能据此把后续差异回溯归给初始生成者” | 后修机制可核，但未说明S8真实收到的Kotlin语义及showNowPrice数据接入；partial。与MCP-only不同，本稿没有明确把“价格后缀不符item XML”确定归入C的节点理由，不能强判同一个首次归责错误 |
| indicator | 提到了Banner→Swiper等输入映射，但没有解释目标indicator位置/颜色的实际后修 | 输入文件/附代码存在不能替模型写该判断；omitted |
| mask | 最终稿未解释目标controller遮罩修改 | 51条任务的泛称及未闭合声明不等于该族归因；omitted |
| repair-compile | summary及N9–N11说明F价格脚本新生private跨struct错误、B放宽可见性、编译签名成功 | N9附F:592–593，N10附B:29，N11附B:32–35；B:36–40核实际成功，非只凭总结。established |

语义与展示分开：

- **问题节点没有实际着色字段**：YAML中`problem:true`布尔字段数量为0；只有N5、N9、N10的reason内写了`problem:true`文本。编译产物这些节点均为`role=context`。这是实际UI/结构交付错误，不因文字中已经提出错误判断就宣布着色成功；也不抹掉文字与原文共同支持的images、repair-compile语义成绩。
- **价格脚本前后态混用**：N8被描述为F:593返回后的“两个Span修复结果”，但7→8绑定S8历史Write，8→9又用F:592脚本读取作为输入边。F:592读取的是替换前动态Span状态，593才是固定Span结果。图应区分旧输入与新输出；机械路径complete不证明S8产生了这份返修后状态。
- 图片实际修复F:233并未被当前主写入边自动附上；目前主强制边集中在F:592–593。summary的图片修复数值及机制明确、可在原池核实，因此语义不判遗漏；展示层仍应补对应写入证据，不能说现有价格边已经逐族展示完整。
- N9的21:30:20是价格脚本回执；51/51“处理完成”是F:628于21:43:31的后续报告，且处理包括未修/待判。不能把该价格端点等同为全51条均已修好或视觉验证完成。
- summary将禁编译与“无法该阶段发现后续访问问题”并列，不能据此把F后来新生private错误归给初始生成门禁；无论当时是否编译，都不能检验尚未产生的F补丁。稿件自身对返修新生已作正确区分，保留这项成绩。

## 5. MCP-only（统一记录此前独立裁决）

| 家族 | 模型已说出的判断及证据 | 裁决 |
|---|---|---|
| images | N4明确“活动图缺比例/高度”，N2实收C:19，N4附C:61/C:73坏版本，N9附F:233 | 同一附XML实际包含两目标图254/280、adjustViewBounds，C初写缺约束、S8保留与F修复相接；established，不要求把全部属性抄进reason |
| cta | N4明确100%宽叠横向margin、N9说明外层Row/padding；C:19内容183–200及C:61内容389–396、S8:264、F:436均已附 | 横向正常输入→C偏离→S8保留→修复成立；established，不扩大为垂直问题完全解决 |
| price | N3声称item XML要求同串数字段放大而非后缀；N4明确指责converter“价格后缀映射不符item XML，输入充分” | 附证C:21实际是￥16/Ticker数字30；C:61内容52、527、545–556仍为数字占位，直到S8:264内容351才绑定完整showNowPrice、1080–1081只去货币符号。将后缀错误倒归C有直接反证；wrong。N6泛称“不证明每项最早作者”没有撤回N4具体错误 |
| indicator | N4确有默认indicator坏配置，N9有颜色/位置修复；N1实收spec只有循环、形状和尺寸 | 没有实际灰度/左对齐要求收件的充分链；封存参考S8:24不是本稿已使用证据。最早坏配置可核，但输入边界partial |
| mask | N7附F:43确实列四个controller；N9附F:103按builder补遮罩 | 后修目的/操作可核，生成期dimAmount收件未说明，不能自动加入S8:258；partial |
| repair-compile | N9附F:592，N10附B:29，N11附B:32–35；仅返修新生private错误标红 | 具体新生和纠正成立；established，不计首次生成节点ACC |

额外限定：N2的match_parent+15dp描述的是C:19内容91–101的`bg_vip_equity`，不是被修两活动图或CTA。举例定位偏宽，但同份已附XML实际有目标约束，足以支撑N4已有窄判断；不把此展示欠精确放大为整族无证。反之，“输入充分”的总括不能由此扩展到价格Span、indicator颜色/位置或所有dialog要求。

F:43真实返回四个controller，不与另一次只列三个缺mask候选的F:78混淆。H5已有透明，不能把四个都判遗漏。B:29为价格尾段读回，不能冒充整页视觉验证。两条force关系有真实grep/脚本依据；20条绑定边和机械valid均不认证理由或视觉效果。其未把编译PASS当视觉PASS的限定正确。

## 6. 本轮结论与冻结状态

MCP-only本例完成的有界解释最多，但存在明确价格归责错误；自由产品少覆盖三族且问题布尔字段失效；clean raw-v2提供了局部机制与流程概述，但五个生成相关家族均未建立实际收件→具体偏离的完整链。这里不能推出工具普遍更优、只能通过MCP才可靠、或树越长越好；更不能与旧full10拼批或当作多文件ACC。

本文件只记录三份纳入产物。成本、耗时和输入隔离见主实验记录`product-three-arm-member-results.md`；未启动任何额外模型，未修改冻结参考或被测结果。

审阅产物SHA256：

| 对象 | SHA256 |
|---|---|
| free YAML | `17EB53164B82BFD89A97DCA4771365CABD7EBE1B26BC3EF6AF0FFB8C8733BEE6` |
| free JSON | `04B6C9BC7E0E4B8F48514BA0D8B0C537B4B2F18D4B1D37771C60FFBF775F8963` |
| MCP-only YAML | `66AC3799C016FB2D995EA5B87F7E7201D8DE899ADC221535B059838EA051BB47` |
| MCP-only JSON | `BE51845361104C9CEB7472077F4D977515F6F35D1ECDDE9232B68ED5DDBFF1F6` |
| clean raw-v2 report | `4FC78B280EA92384591E52FEE80EB5097B5604A561E0C0EF1D9DDB710E0AFA66` |
