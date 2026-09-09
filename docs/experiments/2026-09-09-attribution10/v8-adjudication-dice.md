# V8 Dice rep1：补足生成输入，仍漏验证信息且未省 token

固定六事实为 **5 supported、1 partial**。D1 的生成输入调查确有进步；D2 的构建 WARN 没有进入结论。另按预先单列的 Dice 10/10 原始回执补充，后续主机通道验证仍被遗漏。不是完整语义成功，也未达到成本节省门槛。

实际 GPT-5.5 / medium / native，冻结源 `b540cb2`，2026-09-09 19:41:16 UTC 完成；同 `reference-v1/legacy-reference.json`、同题、同 Dice 原始池。没有改旧 oracle、源代码、冻结材料或调用模型。逐项原句、完整来源路径、21 个引用的原事件 ID / SHA256 见 [JSON](v8-adjudication-dice.json)。

## 固定事实与核心回答

| 原事实 | 状态 | 依据与边界 |
|---|---|---|
| D1.f1 实际读页面、F001、沉浸式输入；生成 Write 无后来桥 | supported | 这次确实成功打开 generator@v2，含派发和累计 Read 索引，并核 v2 差分。原始 generator L51/L53/L57 三次 Read、L71/L72 成功 Write 相符。两次 raw 稿缺失的关键输入调查得到补足。 |
| D1.f2 后续设计、派发明确要求 Want→AppStorage，并成功 Edit | supported | UI-T Step3 派发、模板和设计原文；bridge agent L35–40 三对调用/成功回执，分别加入 import、生命周期调用和 consumeTestWant。 |
| D1.f3 分清阶段，不把后来要求倒推为初始违规 | supported | 明言零字面命中不证明早期语义要求不存在；未给初始生成者造红。生成 Write 为 15:51，桥 Edit 为 19:17。 |
| D2.f1 ECAT work list 明确要求 observer | supported | fixer 派发全文已打开；另列 21:12 的 memory 是后续规则来源，不宣称早期生成方读过。 |
| D2.f2 读入口和 SDK，三次成功 Edit | supported | 原生 L41–46 三对 Edit/成功回执支持 import、onCreate 注册调用与两个 hilog 回调。SDK 部分读取的版本不确定，不妨碍实际返回行支持导出/member 信息。 |
| D2.f3 后置原生成功构建，同时有 may-throw WARN | partial | 成功构建、HAP 和无主动触发回调的边界正确；全文没有 WARN。已打开的 builder L47/L48 输出就有 EntryAbility:140:5 等 WARN，未继续打开的 L51/L52 则给出 may-throw 正文。不能因为 0 ERROR 就漏掉这一固定事实。 |

两题的有界归因核心成立：测试桥来自后续测试阶段，observer 来自后续明确门禁；没有证据把这两项倒推成初始生成违规。D2 没有把编译通过当作异常回调已触发。`正常` 是对已执行指定工作的分类，不能脱离正文的运行时未知去理解成设备验收成功。

原始池为 `.../attribution10/formal-v1/dice-entry/pool`；主要转录：

- `81e0a463.../subagents/agent-a349784d2663f1f0a.jsonl`：生成输入、EntryAbility Write。
- 同根 `agent-a711c5d09fb676814.jsonl`：设计、模板、三次桥 Edit。
- `2f01bcdc.../subagents/agent-a27497cfed8c44856.jsonl`：observer 派发、SDK 和三次 Edit。
- 同根 `agent-a635575c78cd15ff6.jsonl:L43–52,L67–68`：实际构建任务、退出码、WARN 和 ohosTest/HAP。

## 验证状态：旧 Step4 没说假，但没有调查完整后续

报告称：

> “后续验证可确认编译/安装记录，但 UI 10 it 未进入断言体，不能确认桥的运行行为。”

其引用 `#a52d61ac7ab7033ba:4069@L390` 是历史 agent **Write 的 ui-report.md**，不是实际 aa-test stdout。工具调用第 24 次打开该 Write 输入的前 2,000 字，第 25 次打开输出只得到“文件创建成功”。正文准确叫它“Step4 报告”，本裁决也只按报告类证据计，不把文件写成功升级为内部全部验证已重新核实。

原始 `593d4e86-a947-4e62-8027-013014c2bafc.jsonl:L256→L260` 在 21:01 有另一个主机脚本通道的同 ID 原生成功回执：**10/10 PASS、HARD 21/21、7 UNOBSERVABLE**；L265→L267 读回 14 个 dump、onCreate / LoadPage / onNewWant×3 和结果摘要。L260 的桥键检查明确 `NOT_ASSERTED`，所以这不是 AppStorage 认证，也不是原有 arkxtest 全断言闭环。

这一新增材料与 [两次 raw 基线](v7-baseline-legacy.md) 使用相同尺度，仍是单独 addendum，没有悄悄扩写旧六事实。V8 没打开 L260/L267，也没报告后来 10/10；raw rep1 同样漏掉，raw rep2 则至少按“转引摘要主张”提到 10/10，但也未直接核原生回执。**不能把漏掉的新状态算作原有 Step4 状态造假；也不能把“桥键未知”本身扣错。**应判完整后续状态未答全。

本次 `Tests run` 搜索（第 30 次，transcript L156）从 observer 修复后的 21:19:39 开始，因此它不包含 21:01 的主机回放；其他几个搜索从 19:18 开始，时间范围包含该回放，但词项和后续选择未带来原文打开。不能据此指控服务隐藏了证据。

## 真实调用与机械检查

50 次工具调用：guide 2、sessions 1、file 4、agent 10、action 21、search 10、check 2。21 次 action 均用完整 `ref` 且成功，没有猜 action owner id 的失败。

agent 只成功 3 次：generator@v2（transcript L90）、bridge@v5（L92）、observer@v3（L93）。其余 7 次拒绝是 sessions 作为 agent via 3 次、via 文件尚未打开 2 次、把 file v8 当 observer v8 1 次、零效应 builder 误请求 v1 1 次。最后一类靠原文 action 仍完成构建核查，不能给零效应 builder 造 v1。

8 次 search 用 until_ts，无 seq-only until；另 2 次搜索限定 generator@v2。正文正确限制零命中的适用范围。

首个 check（第 49 次，L259）有 **9 errors**：

- 4 个搜索 receipt token 被当成可解析原文引用。
- 3 条桥写边都把累计 agent@v5 当成各次实际写者；真实是 agent@v2、v3、v4。
- 2 条 observer 写边把累计 agent@v3 当成前两次写者；真实是 v1、v2。

最后 check（第 50 次，L268）为 **mechanical_clear，0 errors / 0 warnings**。两次间没有新证据调用，模型删除了无效引用和全部显式边。最终没有继续保留这些假边，不能把首稿错误扣成最终错误；但删除也不补足 WARN 或后续主机回放。累计 agent 节点仍可合法用于已见输入总览，不能被 UI 重新自动解读成所有文件版本的具体写者。

最终 21 个不同原文引用均能对应原始转录和物理行；定位不等于原文支持每个断言。保存稿与最后 check matched、`semantic_checked=false`。没有红节点；不因 basis/check 齐全与否额外加语义分。

coverage 7/7：6 个正式修复版本均 explained，1 个实际 `git diff --stat`＋grep/echo 自检候选 not_repair，已打开原文，处理正确。没有将真实改动谎称无修复。这里的 7/7 是清单逐项交代，不是 7 次修复正确或全文件因果闭环。

## 成本和联合验收

| 指标 | V8 tools rep1 | 同题 raw 两次均值 |
|---|---:|---:|
| Input（已含 cached） | 1,616,936 | 1,404,194.5 |
| 其中 cached | 1,495,040 | 1,206,784 |
| Output（已含 reasoning） | 14,910 | 9,736 |
| Input + Output | 1,631,846 | 1,413,930.5 |
| 工具返回字符 | 207,988 | 3,750,566.5 |
| 模型运行秒 | 334.963 | 216.212 |
| 端到端秒 | 338.905 | 219.210 |

总 token 观察值 **增加 15.4%**，模型运行增加 54.9%。返回字符大幅减少不等于累计模型 token 减少；cached 不能再次加到 input，reasoning 也不能再次加到 output。单个工具样本对两次 raw 均值不证明稳定因果效果，但已不能声称本样本达到 20–30% 节省。

应保留 D1 真正补足生成输入的提高，也应保留 D2 新漏 WARN 和 D1 后续状态缺项。六行都是 5 supported＋1 partial，不代表两类稿件等质，更不能当整体准确率。当前“总 token 节省＋原始归因更准＋UI 如实显示”联合条件仍未通过。
