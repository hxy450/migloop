# V11 legacy 独立裁决

当前仅三案 rep1 完成：Member S3 **pass** / S4 **partial**；Dice D1/D2 **pass**；Splash S1/S2 **partial**，共 **3 pass / 3 partial / 0 fail**。这是有界核心分层，不是完整准确率；Member 的原始输入近因仍缺，Splash 有实质精确节点错绑与原文引用错配，联合验收未通过。

冻结源 `cb3682f`，实际 GPT-5.5 / medium。沿用 [锁定核心口径](core-rubric-reconciliation.md)、原 `reference-v1/legacy-reference.json` 和原始池。新 ledger 指纹不套旧全局动作号，独立按转录标签、物理行、native ID 对账。[JSON](v11-legacy-adjudication.json) 保存每个原事实行、完整调用元数据、引用行 SHA、草稿绑定与成本。V10 已封存，不覆盖。尚无完成产物的 rep2 明列 pending，V12 另立文件。

## Member rep1：输入近因仍未追到

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v11/member-center/runs/tools/rep1/verdict.yaml)于 22:32:23 UTC 完成。

S3 三处206/AppLoad、704/Pay、728/Renew和值均对：1透明、2个Palette深色。报告写“据脚本分支，三处预期写入值分别为……”，并分别指出脚本汇总、Pay局部读回和未知最终全文。原始 fixer L103 明确 `open(path,'w').write(new)` 后才 `report.append`，同ID L104 成功回执报会员页3sites；未立正式版不能抹掉实际脚本效应。报告对另两处**最终状态**保留未知是合理边界，措辞偏保守不额外给分，也没有说三处设备效果已验收。已有透明H5未点名，按既定minor规则不降核心，S3事实细项2 supported/1 partial。

S4 找到了单Text30旧实现、L528的ForEach分段、L592尾后双Span/private helper，以及 builder L23/L24错误、L32/L34去private和本次真正打开的 L36/L37原生第二次构建成功。尾后脚本是事件S4_E1，没有伪造v40。红 fixer@v33说的是**收到错误输入**，不声称它是最初写作者。

但19次action均集中fixer/builder，没有Slice8或blame调查；唯一agent请求因via自身未打开被拒。原始 Slice8 L21/L24在07-24 15:33已返回Kotlin数字段 `replaceSpan/AbsoluteSizeSpan(30)`，L264/L265在16:04成功整写却把非滚动后缀一起设30。这条mandatory实际输入近因没有补上，S4仍partial。S4事实2 supported/1 partial；不能以保守“不知道原生成者读过何种finding”替代它实际读到正确Kotlin的可恢复证据。

16个最终原文定位唯一，最终稿与唯一check逐字一致；7 reviewed+31系统not_investigated。check的mechanical_clear不认证原因或题目完成。

## Dice rep1：主链成立，后置验证停在旧轮次

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v11/dice-entry/runs/tools/rep1/verdict.yaml)于22:37:32 UTC完成。

成功展开生成者agent@v2累计输入（page/F001/沉浸式）、桥agent@v5和observer@v3；第一次把observer文件v8当agentv8的请求遭拒，后来纠正，最终未造该版本。D1既核了生成Write无桥，也核后置Step3明确按设计§F写桥的派发、模板和三次Edit。D2实际展开SDK导出/ErrorObserver、worklist、三次Edit和原生主HAP/ohosTest构建结果。两题core pass；WARN未点名按原有minor处理，没有宣称0WARN或异常回调已验证。原事实5 supported/1 partial。

报告D1引用root81e L3402旧final summary的UI0/10、UT3/3，并正确限定summary来源和桥键未验证。但它仍没有展开独立addendum：root593d4e86 L260在21:01的原生10/10 PASS、HARD21/21、EXIT0。正文“后续验证只到编译/装机/测试通道尝试”作为整个池的完整总结不充分；须补轮次，不把旧0/10冒充所有后来记录。这是沿用raw/tools同尺度的验证完整性缺项，不偷偷把addendum追加为旧D1核心必填。该10/10明确桥键NOT_ASSERTED，且早于21:19 observer补丁，所以也不能拿来认证桥键或新观察者回调。

没有V10rep2那句memory“发生在修复后”的错误断言。22个最终原文定位唯一；两个check之间只删除entry_events列表，2warning→0，没有补查证据。6 reviewed+1系统not_investigated，补集不是已阅。

## Splash rep1：修复脚本已开，原始输入/装配链仍漏

[最终报告](../../../../_migloop-eval-20260909/attribution10/formal-v11/splash/runs/tools/rep1/verdict.yaml)于22:44:35 UTC完成。

S1知道初版callback、Slice11错误isModal理解、D-020与finding反驳，也打开L346完整脚本及L352兜底Edit；但没有调查entry-setup L123/L124删除callback这一mandatory环节。S2打开L485入页隐藏/离页恢复脚本和L488只补onRoute restore，未误称v53才新增全部隐藏；生成方实际输入边界也谨慎。但早已有据仅凭page/meta以及07-26 fixer查theme说明，没有核07-23主会话 L404原始theme读回或早期ui-manifest/design材料。故S1/S2均partial，原事实4 supported/3 partial。

L346和L485都在写目标后才print成功，配对原生回执分别L347/L486；账本候选/快照未知不等于这些脚本未执行。报告把S1作为“尝试/候选”仍偏保守，不能因此视为更正确。后置编译只按主会话/构建报告说明，没有伪造设备复测成功。

两项完整标注必须修正：

1. **实质精确进入节点错绑**。S1红 `Slice11@v37` reason以“v45原文显示……isModal:true……主要引入点”归因。但对应原始L294/v37只是把动画令牌判断改成 `isAnimationStale` 并加helper；isModal错误解释在L236/v22写入，D-020注释在L250/v26。累计file v45还保留错误不证明v37是引入该错误的动作。按锁定规则，作者/阶段主链正确但精确坐标错误列material，S1仍因mandatory缺链partial，不临时换成core fail。
2. **实质原文引用错配**。最终把 `#50a0622bcfe4a588:10582@L2` 用作派发硬约束及F001输入。原始L2仅是 `Other agents active...` 的system-reminder名单，不含这些要求；真实完整任务在L1。已打开agent画像确实展示了正确任务，因此不是说“派发不存在”，而是最终指定引用不支持所宣称内容。locator合法不等于证据支持。

18个最终locator均唯一；三个check第一份缺红node basis格式失败，第二份补basis后仍有2个search receipt无效引用，最后改成原文引用并保留1条中性post-anchor warning。最终matched不改变上述原文支持问题。4 reviewed+25系统not_investigated。

## 成本观察，不作为通过依据

| 案 rep1 | 输入（缓存已含） | 输出 | 总输入+输出 | wall / e2e秒 | 工具调用 / 返回字符 |
|---|---:|---:|---:|---:|---:|
| Member | 746,990 | 9,682 | 756,672 | 225.63 / 239.92 | 39 / 195,647 |
| Dice | 891,621 | 14,132 | 905,753 | 293.49 / 297.41 | 40 / 184,515 |
| Splash | 1,940,716 | 20,286 | 1,961,002 | 418.35 / 431.85 | 37 / 329,631 |

相对各案既有两raw平均总token，三个单次观察分别低71.88%、35.94%、40.68%；不把单跑与均值比较称成稳定收益或质量胜负。缓存不能再次相加，reasoning已含输出。成本降低不抵消mandatory缺链和material错误。

当前三份rep2未有completed结果，尚未评分。此文件只追加同源后续完成运行；不同源V12另立。

