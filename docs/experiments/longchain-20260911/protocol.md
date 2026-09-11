# 长程归因诊断：先找实际失败，再谈工具收益

开发诊断，非泛化评测。只选已讨论的 F10-01 MemberCenterPage，原始组与工具组各一次，gpt-5.6-luna / medium / 1800 秒。没有自动重试、格式修复或强模型替答。旧分数、旧报告不覆盖。结构化输出成本计入工具组；本实验不能把格式差异的影响与工具影响完全分离。

两组共享 task.md，原始组只读 shell，工具组只用 MCP。先运行原始组，在恢复已确认遗漏的派发功能后冻结工具代码再运行工具组。本轮不根据原始组答案给工具组添加个案提示。两组原始材料完全相同，参考与本文件在材料池外。宿主越界访问通过实际轨迹审计，不声称 read-only sandbox 保证只能读取该目录。

## 预先固定的审阅标准（不注入调查员）

沿用 file-first-10/reference-units.json 的 F10-01 六个归因单元与 scoring-core.json 的语义判据：mask、images、cta、price、indicator、repair-compile。每项分别记 correct / partial / wrong / omitted，正确归因覆盖 = correct / 6，partial 不折算成正确。报告可以任意拆合，不能用段落数量加分。对所有额外因果主张另查证，重大错误独立列出；未知不自动算错，也不能替代已有正证据。

新增机制层只检查证据义务，不把固定故事当作唯一答案：

1. 历史规则/派工：是否找到当时实际生效的内容和交付关系，而非只报 skill 名称。
2. 输入→输出：至少一项生成偏差能对照已交付输入与当次输出，区分首次引入、继承、重写。
3. 检查边界：是否核过相关下游检查的实际范围/结果，不从 PASS 推导视觉正确或任意检查失职。
4. 改进边界：建议能对应已证缺口，机制假设与优化效果不冒充事实，列出验证方法。

逐项记 evidenced / partial / absent / contradicted；这是机制调查完成度，不是归因 ACC。不奖励跳数和 skill 指责数量。引用定位与边可核另计，不用 schema valid 代替语义正确。

## 已核原始见证与竞争解释

生成根 9b3105a2-85ec-4889-9786-b3c220f06754.jsonl：L1908 converter 模板；L4109 三段式模板；L4181 closer 模板；L4270 实际 Slice8 派发。

同根 subagents/agent-aslice8-pay-80bbb1f44b77da0f.jsonl：L1 实际任务；L21→24 Android Kotlin 读取（仅数字 AbsoluteSizeSpan(30)）；L75→76 既有会员页读取；L198→199 理解笔记（30项 Gap 未列非滚动价格字体分支）；L264→265 写入仍整串 fontSize(30)。初始 converter L61 已有相近呈现形状，不能由 Slice8 全文件重写认定它是唯一/首次引入者。笔记与代码遗漏同时存在，不证明前者导致后者；不发明笔记→实现 agent 的读边。

group2-closer-b7ebd5ae592d3c5d.jsonl L537→538：目录与 source-notes 行数检查；L575→576 handoff。该检查不能认证语义覆盖；不据此声称其他所有检查都不存在。

修复根 ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-a68daf720e780b4c2.jsonl：L521→524 XML/Kotlin 对照；L528→529 第一次价格分段修复；L592→593 固定 Span 策略引入 private priceDigits/priceSuffix。builder agent-af0e3d2ae54dbf769.jsonl L24 报 private 访问错误，L32→35 修访问修饰，L37 构建成功。此编译错误属于返修引入，不属于初代生成；构建不认证视觉。

输出必须列：各组实际答案、逐项裁决及原文、错误来自未找到/未展开/错读/越界推断/工具错误哪一类、token（含缓存与未缓存分开）、墙钟时间、schema/边核验。单次成功不证明工具优越，单次失败也不能推导方向无效。
