# V10 完整成本结果：跨过成本门槛，尚未跨过完整正确性门槛

14次工具调查与14次同题原始调查全部完成；七文件、十问题，每文件两重复，GPT-5.5 medium/native。工具源80c099e、reference最终提交；原始基线和共同任务/只读池沿用固定计划。不是新项目泛化或随机抽样统计证明。

## 成本

| 完整调查口径 | 原始组 | 工具组 |
|---|---:|---:|
| input_total + output | 24,899,105 | 16,725,127 |
| input_uncached | 2,961,513 | 1,570,332 |
| output（已包含在首行） | 151,992 | 182,379 |
| 端到端总耗时 | 4,084.73秒 | 4,093.67秒 |

总量节省 **32.83% token**，按七文件等权平均节省 **25.17%**。端到端耗时增加0.22%，即基本持平；不能说时间也节省20–30%。缓存输入已含在input_total，不加第二遍，金额未知。工具组有额外结构化/UI/机械检查交付，原始组没有这些义务；比较的是两种完整产品流程，不是只测检索器。

| 文件 | 两重复平均token节省 |
|---|---:|
| C3 GuidePage | 32.53% |
| C2 PptGenerationViewModel | 16.21% |
| MemberCenterPage | 55.42% |
| Dice EntryAbility | 2.30% |
| SplashPage | 46.64% |
| C1 callback | 1.82% |
| C4 agreement dialog | 21.25% |

全部14份工具最终交付通过账本身份/checked-draft绑定；V8/V9的跨SID混账失败未在这轮复现。18次被拒调用与2次工具错误仍计成本。不能从一次版本比较断言“固定范围”单独导致全部收益，同版也改了agent摘要，模型调查路径有波动。

## 正确性和审计分开

[六份legacy逐原文裁决](v10-legacy-adjudication.md)已封存：核心子题7 pass / 5 partial，但完整注释仍有两个material错误，另有未充分支持的红色归因和非实质细节错误。**这不是7/12的最终归因准确率，也不能宣布本案全部正确。**

- Dice rep2按修复后窗口找到memory的新版本，便把整个memory沉淀说成修复后；真实早期版本在修复前已包含相关规则。
- Splash rep2从后期快照含有某判定，推成该次writer改了它；原始Edit只补URL guard，真正谓词改写是更早的Slice11。引用和节点本身都能定位，不能替错误作者归因背书。
- Member仍漏生成者实际输入→错误整写的mandatory上游；Splash两次仍漏早期入口删除等mandatory链路。因此省token不能抵扣不完整归因。

Codex语义逐项裁决另见 [独立记录](v10-codex-adjudication.md)；本结果发布时还在补齐，不把已接受子集冒称八份全部正确。机械audit逐案另存冻结案目录，不替代这些语义结论。

原始数据统计：`C:\Users\hongy\projects\_migloop-eval-20260909\attribution10\v10-metrics-final.json`；计划 [v10-metrics-plan.json](v10-metrics-plan.json)，可用compare_suite.py复算，输出须用新文件名。

结论：开发集成本门槛达到，完整正确性/联合目标未达到。V9已完成保留集上工具反而多36.28% token、错误边界更弱的结果仍然成立，不能用V10开发回归覆盖它。后续V11/V12已用新目录冻结复测，不会修改这一轮。
