# tools-v4：完整开发集退步，不晋升为更好版本

2026-09-10。十文件、各两重复全部完成；仍用固定 Luna medium、并发2、1800秒、不重试/修稿/换模型。原始组未重跑，参考核心和评分器未改。下面是旧开发集的AI证据裁决，不是人工双盲或跨业务泛化证明。

## 主要结果

| 指标 | 固定原始组 | tools-v3 | tools-v4 |
| --- | ---: | ---: | ---: |
| 文件等权正确归因覆盖 | 73.83% | 75.67% | 67.00% |
| 核心 correct / 总数 | 32/56 | 35/56 | 30/56 |
| partial / missing / wrong | 8/10/6 | 11/9/1 | 14/10/2 |
| 支持事实主张 / 事实主张 | 64/87（73.56%） | 66/79（83.54%） | 55/67（82.09%） |
| 核心全通过且无重大错的文件跑数 | 8/20 | 8/20 | 9/20 |
| 重大错误 | 11 | 4 | 3 |
| input + output token | 25,988,811 | 9,388,415 | 9,400,393 |
| 平均调查秒数 | 196.39 | 221.12 | 239.27 |
| 平均端到端秒数 | 196.39 | 232.07 | 254.58 |

正确覆盖不是含partial的宽松分；部分解释正确也不会说成整条原因正确。文件等权与核心数量加权是两种统计：v4后者为30/56=53.57%，不得混写。核心通过不认证报告里每条辅助断言都真实。事实主张数量由各报告实际内容去重而来，分母不同不能解释为同一组87条主张的精确率试验。

v4总token比原始组少63.83%，比v3基本不变；端到端比原始组慢29.63%，比v3慢9.70%。没有达成“更准且更快”。整文件pass与major有所改善不能抵消复杂文件覆盖退步，不据此晋升版本，也不倒删失败。

## 每个文件的两跑核心正确数

| 文件 | rep1 | rep2 | 主要未完成处 |
| --- | ---: | ---: | --- |
| F10-01 MemberCenterPage | 2/6 | 2/6 | 漏mask/images，价格生成输入与返修private编译链不足 |
| F10-02 SplashPage | 1/5 | 1/5 | 漏mask/icon/progress；rep1错归初版，rep2中间历史缺环 |
| F10-03 Dice Index | 2/5 | 3/5 | Roll明确规格与后期呈现冲突未恢复；rep2错归初版console |
| F10-04 0723 EntryAbility | 2/2 | 2/2 | 核心正确；rep2另错误否定历史成功构建 |
| F10-05 F003Repository | 1/1 | 1/1 | 核心正确，后置测试替代物未冒充最终平台等价 |
| F10-06 GuidePage | 2/3 | 2/3 | 20dp控件框/4dp轨道的输入传递还没接上 |
| F10-07 Dice EntryAbility | 2/2 | 2/2 | 核心正确；rep1另错误否定已有构建记录 |
| F10-08 AppScope/app.json5 | 1/2 | 1/2 | 漏entry已有资源到AppScope的实际复制链 |
| F10-09 LaunchPage | 1/1 | 0/1 | rep2未解释命中策略局部机制，并以不存在的“全生成无构建”作原因 |
| F10-10 build-profile | 1/1 | 1/1 | 核心正确，另有unsigned规则/后期验证范围错误 |

逐项原始证据和报告引文见 [0723五文件](../generalization-20260910/v4-0723-adjudication.md)、[Codex与Dice Index](../generalization-20260910/v4-codex-adjudication.md)、[Dice EntryAbility](../generalization-20260910/v4-f07-adjudication.md)、[AppScope](v4-dice-app-adjudication.md)。core里的辅助背景没有事后升为必答项。

## 这轮能定位的问题，和不能宣称的原因

实际trace显示：有些证据未展开到正文（Member private编译错误、Guide输入mapping），有些短任务已经全文交付仍未核后续效应（AppScope复制任务），有些取得worker局部NOT_RUN后误写为整个生成池没有构建。三类不能统一说成“工具缺证据”，也不能统一甩给“弱模型能力差”。

批量审计共有508项：476ok、24error、8deferred。ok仍可能只是前缀；有5次diff首项元数据在模型指定1800/4000字符预算内不可交付，有3次模型把不支持的sessions放进batch。报错与续取信息保留，不假装成功查询。

这轮同时改变传输减冗余、短任务预览和请求内解析复用，且模型运行期间存在源注册/哈希/测试等后台CPU与磁盘工作。因此它不是每项改动的因果消融或隔离延迟测量。离线相同查询变快不等于端到端变快；两重复也不能精确分离采样波动。当前结论只到“组合候选在这次完整开发对照中不达标”。

## 结构化与调查图（不是语义得分）

冻结生产代码逐池验证，全部原始报告、原始池和代码前后哈希稳定；没有修稿或模型调用。

- 严格结构通过11/20；另9/9失败原稿可由真实production probe投影为带警告的原生认证partial，原错误不被抹掉。
- 节点声明122：113 matched、1 invalid、8 unlocated。
- 边声明57：19 confirmed、23 not_observed、14 invalid、1 conflicting。未观察到不等于不存在，不为补成树而补画读写边。
- 引用出现374次：289ok、53outside_scope、27invalid、5unbound。重复出现分别计，不是374条独立事实；引用ok不认证因果。

新审计是生产payload检查，**未对v4重新做浏览器像素/DOM验收**。不能借v3截图冒充v4展示已测；也不能把strict失败留下的空严格图当作网页必然丢弃全部原稿。

## 冻结产物与成本口径

EVAL=`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10`。

- v4 manifest SHA `213d7b657a91602db7c777f963eca47c4dcc044340e3fcf6667f7f555f1586c0`，code digest `28b0ab3f71102060a64b9532d7808294096caecbcbf09c5d923e61bd38e5fcbb`。
- core SHA `0d48f30f9e501eedd55b87e086590c72e8b7fb8096a939f56842b71703426497`；裁决位于`tools-adjudication-v4`，全部validator通过。
- `tools-scores-v4.json` SHA `7c321171a5915f00cc7a962c35f1f6323fe65198720a271c8f559c8f038328e4`。
- `tools-delivery-audit-v4.json`和`tools-v4-graph-audit/formal-output-audit.json`为独立机械检查，失败/partial原件另外保存。
- v4 input9,245,743，其中cache7,261,696、非cache1,984,047；output154,650；reasoning/cache不重复加。后处理平均15.27秒已含在端到端，准备8.99秒单列。
- queue从19:26:40.950Z到20:10:16.873Z，约43分36秒；这是并发队列墙钟，不是累加各run时间。20跑全部完成，无未启动项。

后来发现并修复的新运行深层source发现、SourceSpec和文本附件问题不在v4模型包里。它们冻结为独立candidate-source-v2；其来源门通过不可以反过来给这20份报告加分。新13文件先建立并独立审核参考，再做首次跨运行对照；候选不能按新答案继续修改。
