# V12 legacy 独立裁决

当前已落盘Member与Dice的rep1裁决；Member为S3 **pass**、S4 **partial**，Dice见下文。其余未裁决，队列与评审已因额度停止，见[检查点](2026-09-10-checkpoint.md)。没有把更多未知或检查通过计成正确性提升。冻结源`e67d7d7`、实际GPT-5.5/medium；后续viewer不拿来重绑调查，V10/V11各自保留。

使用相同 [核心口径](core-rubric-reconciliation.md)、`reference-v1/legacy-reference.json` 和冻结原始池；只读已完成报告及原文，无模型调用。[JSON](v12-legacy-adjudication.json)含每条原facts状态、实际调用、定位行SHA、原稿check绑定与额外标注问题。

## Member rep1

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v12/member-center/runs/tools/rep1/verdict.yaml)于22:59:06 UTC完成。

S3三站点/1透明2深色正确，明确“批量脚本真实执行成功”“实际被该脚本触碰3处并补import”，同时区分Pay直接读回、其余最终快照未知与未做像素复验。原始L103在write后才report、L104同ID成功回执支持实际效应；没有因未立正式版把所有写入否掉。H5未点名仍是既定minor，不降core；事实2 supported/1 partial。

S4增加14次diff，查了v1-v9，并找到Slice8整写v7仍把stripCurrency后整串设为30。可是25次action、唯一成功agent仍集中fixer/builder，没有展开Slice8在整写前收到的Kotlin L21/L24。原始正确数字段输入在15:33返回，16:04整写仍错误；这是mandatory近因，找到v7输出不等于补齐输入链，S4仍partial、事实2 supported/1 partial。

ForEach→双Span/private、builder private error→两Edit去private→原生第二次BUILD SUCCESS均正确。S4E3独立绑定尾后脚本，不造v40或新file版本；本次引用builder L26/L27真正grep到了private helper及调用点，没有把不确定Read绑成确定旧版本。

### 早期红节点仍缺因果基础

报告把file v1列为“进入·缺”，reason为“后续finding要求保留Android多级字号时，这一实现缺少后缀降号结构”，counterevidence又承认“当时是否已有完整Android span要求进入上下文未知”。

v1原文converter L61确有 `Text(this.item.priceText).fontSize(30)`，但接口注释把priceText称rolling数字，另有showBottom字段。单靠这段语法及更晚finding，不能确认最初版本具体后缀数据、当时适用输入，更不能认证它是最初原因。原始Slice8实际读取正确Kotlin后重写的近链仍漏。列为**material 未充分支持的因果标注**，不伪称已证明相反历史原因，不把已有S4 partial改成新门槛fail；完整标注须修正。

两个check之间仅替换或删除12个search/diff伪引用，没有再查原文；最后mechanical_clear不认证红v1原因。19个最终原文locator唯一存在，原始tag/行/native ID/SHA独立留存；原稿与最后check逐字一致。9 reviewed+29系统not_investigated，补集不是模型已调查。

输入2,053,412（缓存1,924,608已含）、输出19,919，总2,073,331；wall433.41/e2e446.73秒，58次工具/217,173返回字符。相对两raw平均低22.95%，但比V11 Member rep1的756,672显著增加；都是观察值，不证明单变量稳定改善，更不抵消mandatory输入遗漏。

后续同源rep分别追加，不用更好的一稿替换这一稿。

## Dice rep1

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v12/dice-entry/runs/tools/rep1/verdict.yaml)于23:04:50 UTC完成。D1/D2均core pass；原facts 5 supported/1 partial。累计当前已评分四题次3 pass/1 partial，不是完整准确率。

生成者agent@v1成功返回的实际读索引包含page L51、F001 L53、immersive L57及入口L47；后置桥派发、设计/模板读取和三Edit均已开。虽然生成后的EntryAbility L71/v2 Write未专门展开（事实细项留partial），但不是先前“没打开生成输入”的缺链情形；不因必须某个version数字而再造核心门槛。该v1实际是WindowModel效应，报告未把它声称为EntryAbility写版本。

D2完整worklist/SDK/三Edit、后置编译和may-throw WARN说明成立。后置observer构建用builder L82总结；D1另有20:15 builder-verify-final L29原生CompileArkTS/PackageHap片段。没有把20:15构建当成21:19观察者的验证，也没有认证异常回调。

最终D2说记忆/索引位于更晚会话，不能倒推**初始生成**，不等于说它在observer修复后；不能重复扣V10rep2那条实质时序错误。完整性仍缺独立10/10 addendum：它曾打开root593d L385 Edit的**output**并find该词，得到只含回执、不含编辑正文的无匹配提示，却未改input或追L260原生10/10。原Step4 UI0/10报告是真实旧轮次，不授予池内最终验证状态已核的信用；10/10也不认证桥键。

8次agent中两位0效应builder被错误请求v1，后改action(id,seq)/search(v0,after=true)定位；最终没有造builder节点。generator证据L3属于skill注入、具体派发在L1；实际画像已显示L1，保留引用精度不足，而不否认收到任务。20个最终locator唯一、final与lastcheck一致；两check只删entry_events使6warning归零，6reviewed+1系统补集不等于全部已调查。

输入1,874,150（缓存1,742,848已含）、输出14,843，总1,888,993；wall330.14/e2e333.84秒，51调用/251,340返回字符。相对两raw平均**增加33.60%**，不满足节省目标。
