# V7：四跑诊断结果与早停

V7是84bfcf8，Member与C4各两次，全部GPT-5.5 medium/native/reference。没有扩到全部十题，原因见 [诊断早停记录](v7-diagnostic-stop.md)。所有报告/原始调用/check/草稿保留，四次最终文档均matched。

## 不能只看合计token

原始对照为V6B相同任务、池和模型，每任务两跑。缓存已含在input_total，表中总token=input_total+output。

| 任务（两次均值） | raw | V7 tools | 相对raw |
|---|---:|---:|---:|
| Member | 2,691,060 | 1,349,627 | 少49.85% |
| C4 | 1,410,037 | 1,605,235 | 多13.84% |

四跑合计少27.95%，两任务等权降幅平均18.00%。这不是在完整评测集证明20–30%收益，更不是正确性更强。真实用量轮数与字符量的区别见 [成本画像](model-round-cost.md)：V7 C4两次均30个用量增量，V6 reference为26/17，短GUIDE没有保证少走往返。

## 语义与展示

- Member：两稿各5条原始事实supported、1条partial，均没找到Slice8在生成前已收到正确Kotlin输入；两稿都未调用agent或blame，不能给recovery记收益。还分别把尾后动作挂较早版本、把不确定v14读写成确定快照、用后置finding描述生成时依据。
- C4：核心静态近因两次可接受。rep1把较晚同项目build/install对补丁产物的支持说得过强，并漏Harmony manifest；rep2正确处理保存记录和补丁绑定边界。四类Event枚举遗漏记事实行partial，不因未复述全部名词就判核心失败。
- UI：两真实页的131步、原始引用/原因/草稿来源和几何检查通过，但发现“无repair文件关联”误禁用真实引用；现有图也漏掉了模型显式声明且账本真实的边，因为只投影via转移。后者是定义过窄，不意味着可以把搜索当读写。

详见 [Member裁决](v7-adjudication-member.md)、[C4裁决](v7-adjudication-codex.md)、[UI核验](v7-ui-verification.md) 及同名JSON。评审回查原始记录且知道组别，不冒称双盲。

下一版本b540cb2修地址契约、边界诊断、UI引用身份和显式真边；这些改动不倒算V7收益。原始组剩余题目继续补齐，可以作为下一候选的同题对照，工具组旧四跑不拼入新版本成绩。
