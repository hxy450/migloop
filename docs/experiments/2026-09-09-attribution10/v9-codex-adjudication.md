# V9 Codex C1–C4 独立语义裁决

状态：两次重复均已完成。范围为 `formal-v9/codex-c1..c4/runs/tools/rep1,rep2` 中由最终 reference 成功绑定的 `verdict.yaml`、冻结 `reference-v1/codex-reference.json` 及其两份原始 rollout。机械 `check` 只认证格式、身份和引用外壳，不认证下述语义。C2 rep2 没有任何被认证的最终文档，单列为交付失败而不做语义评分。

## 结论

七份有认证最终文档的运行核心结论均可接受，未发现重大虚假因果或行为闭环。C2 rep2 的最终 reference 被拒绝，不能用其四次未认证 check 草稿替代交付。系统投影的 target/event 引用均定位到真实 owner/seq，未把尾后事件伪造成文件版本或因果边。

完整注释层面四题都有可恢复缺项或证据层级措辞问题，因此不能写成“4/4 完整复原参考”。C2 的 coverage 未完整是独立的交付/机械问题，不推翻其正确的未知结论。

| case | 核心 | 完整注释 | reference facts | 主要边界 |
|---|---|---|---|---|
| C1 | 接受 | 有遗漏、轻微扩张 | partial / omitted / partial | 漏先 BLOCKED 与两次 closer 均未 build；静态门被扩写到未直接证明的隐式类型/同类不一致 |
| C2 | 接受 | 有遗漏 | partial / supported / supported / omitted | 正确不裁 fixer/reviewer 谁对；漏唯一 publisher 摘要与 canonical 联系人污染；coverage 不完整 |
| C3 | 接受 | 有遗漏 | omitted / partial / supported / supported | 正确保留两修法和最终效果未知；漏初始 Kotlin/layout/snapshot 与生成实现报告 |
| C4 | 接受 | 轻微证据层级过强 | partial / supported / supported / supported / supported | manifest 记录一次同意转场，不等于独立设备复核或补丁绑定；四类点击未闭环 |
| C1 rep2 | 接受 | 有遗漏 | supported / partial / supported | 漏 closer BLOCKED 原报告，实际补丁/no-op边界准确 |
| C2 rep2 | 未评分 | 交付失败 | not scored | 4 次 check 均 unverifiable，最终 ref rejected，无 verdict.yaml |
| C3 rep2 | 接受 | 有遗漏 | partial / partial / supported / omitted | 两修法边界正确；漏初始输入/生成报告与最终 fresh-capture 债 |
| C4 rep2 | 接受 | 有遗漏、轻微证据边界 | partial / supported / supported / supported / omitted | 漏后续 native build/install；保存回放记录不等于独立设备复核 |

## C1 rep1

最终稿准确识别补丁只把 `() => {}` 改成 `(): void => { return }`，两版默认回调都无业务副作用，因此核心成立。它也明确后续 PASS 不是点击验证。

缺口是没有交代 reference 的关键前半段：Batch closer 曾因该空回调返回 BLOCKED，而且 BLOCKED 与后来的 PASS 两个 closer 均 `build_run:false`。稿件称没有独立 linter finding 原文并非与 reference 直接矛盾——reference 的直接材料是 closer 报告而非独立 linter——但不应因此省略这条实际门禁记录。另将门描述为同时规避“隐式返回类型/同类不一致”超出“empty callbacks forbidden”的直接证据，属于轻微推断扩张。

后续全工程 build/install 是真实事件；没有目标源码/产物哈希，最多是后置过程证据，不能唯一绑定本补丁。稿件已有此边界，故不构成重大错误。

## C2 rep1

核心处理正确：fixer 称改经 WorksService，reviewer 称同 DAO/同事件、属于 wrong_edit；两者都是报告主张，目标源码、diff 与行为复测均缺失，不能判门面行为等价，也不能判作品未呈现已修复。稿件没有把 reviewer 当金标。

完整层面漏了两项：历史执行摘要称 PptRecordRepository 是唯一 post-insert CREATED publisher；Round 2 Works canonical 被系统联系人污染。前者在稿中仅由 F005/F006 规格与 reviewer 主张侧面覆盖，后者未覆盖。目标文件未进入账本，最终 check 仍为 `needs_review` 且 `coverage_complete=false`；submission 虽可交付，机械 coverage 不能称完整。

## C1 rep2

核心接受，且比 rep1 更准确：它明确实际补丁仍保留默认 no-op，所以没有实现主会话当时所说的“父组件必须传入”；运行语义仍是立即返回、无副作用。它也恢复了修改前读回、补丁、静态 PASS 与 `build_run=false`，并没有把后续构建背景写成 onAnswer 点击验证。

完整性上仍漏了一层直接记录：reference 的先前 closer 报告明确为 `BLOCKED`，稿件只引用随后主会话“发现硬门”的说法，没有直接引用或写出 closer BLOCKED。因此 facts 记 `supported / partial / supported`，不影响核心。

## C3 rep1

稿件正确区分了 Monitor/visibility、reviewer wrong_edit 主张、Round 2 条件/独立挂载主张，并明确 reviewer 和 fixer 的报告都不是源码事实。它还正确指出 Round 2 fixer 之前的 capture 不能验证后来的独立挂载补丁，最终仍需 fresh capture，真实根因和结果未知。

主要遗漏是初始生成阶段已有 GuideInit Kotlin/layout/snapshot 输入以及生成报告声称实现 5110ms 进度流。`low_confidence/transient_capture_debt` 只被覆盖债、manual review 和 fresh capture 债近似交代。核心未知边界仍正确，因此属于可恢复的完整性缺项。

## C4 rep1

代码级链条完整：写前源码为可见态 `HitTestMode.Block`，SDK 摘录解释 Block/Default，原生 patch 和读回确认一行改为 Default；同轮 build 因 `.migbot/config.json` 缺失而失败，已有 HAP 早于补丁。后续根确有 native build/install 成功。稿件未归责旧 Block 的引入者，也未把尾后动作绑定成新文件版本。

后续 `capture_manifest.json` 的原生读取确实记录 `同意并继续 → page_change → GuideStatusFragment`，但这是保存的 manifest/运行记录，不是本次调查独立重放设备。稿件写“支持运行时点击能越过”并在 boundary 简写为“新包运行点击越过”，证据层级略强；它同时明确非专项 hit-test 验证、未覆盖“不同意”和两个协议链接、缺补丁到产物源码哈希，因此不升格为重大闭环错误。

## C4 rep2

核心同样接受。它完整覆盖写前 Block、SDK 语义、原生 patch、读回 Default、同轮构建受阻与旧 HAP 边界，并比 rep1 更明确地说后置回放不能证明 v249 当场构建安装含补丁的 HAP。target 匹配；五个 event 均绑定真实 owner/seq，只有 patch 获得真实 `effect_version=249`，尾后 readback/walk/replay 与文本 judge 都没有伪造文件版本或边。

完整性上的主要退步是遗漏 reference fact 5：后续根原生输出中的 `BUILD SUCCESSFUL` 与 `HAP installed`。稿件改用 edgewalk/replay 说明后置行为链，但这不能替代构建/安装事实。四个 Event 名称仍未枚举，按既定最低标准只记 partial。

证据层级仍需收紧：`#2788@L1073` 是 exec 读取 walk report，`#3670@L3758` 是 exec 读取 checkpoint/capture_manifest；它们支持“保存的后置记录称同意按钮曾推进到 Guide”，不是本次调查独立执行点击。稿件已经明确这是后置回放/人工介入、没有补丁绑定，并保留 judge fail、协议链接未点等反证，因此该措辞边界不构成重大错误。

## C2 rep2

不做语义评分。运行最终确实提交了 `migloop-verdict-ref/1`，但 submission 记录四次 check 全为 `unverifiable`，`matched_check=null`、`status=rejected`，且没有生成 `verdict.yaml`/`findings.json`。因此即使 `result.json` 的过程消息概述了一个看似谨慎的结论，也不能把未认证草稿恢复成最终交付。这是独立的交付失败：`verdict_ok=false`、`coverage_complete=false`。

## C3 rep2

核心接受。稿件准确区分 round-0 Monitor/active 尝试、round-1 reviewer wrong_edit 主张、currentStep=5 独立挂载自述，以及早于该挂载修法的 capture；明确无目标 file@v/diff，真实根因和两种修法运行效果都未知。

完整层有三处缺项：只用早期 `initStep` 代码形态和后续覆盖清单近似覆盖生成前输入，未恢复 Kotlin/layout/snapshot 与生成报告声称已实现 5110ms 进度流；对持续 low-confidence/transient debt 只部分覆盖；没有明确交代最终 manual review / fresh capture 债仍保留。六个 event 均为真实 owner/seq，尾后或文本事件没有 effect version 或新边。

## 交付与成本（rep1）

| case | verdict / coverage | input total | cache read | uncached | output | calls | tool chars | wall / e2e s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 | true / true | 1,225,459 | 1,113,600 | 111,859 | 13,504 | 51 | 199,870 | 285.554 / 288.316 |
| C2 | true / false | 957,449 | 880,128 | 77,321 | 11,148 | 41 | 112,602 | 259.031 / 261.789 |
| C3 | true / true | 2,300,034 | 2,189,312 | 110,722 | 13,161 | 73 | 163,180 | 307.406 / 310.177 |
| C4 | true / true | 1,704,423 | 1,578,496 | 125,927 | 14,895 | 62 | 222,050 | 344.092 / 346.806 |
| C4 rep2 | true / true | 918,576 | 811,520 | 107,056 | 12,534 | 35 | 245,343 | 260.997 / 263.835 |
| C1 rep2 | true / true | 677,179 | 591,872 | 85,307 | 10,632 | 29 | 130,512 | 228.590 / 231.331 |
| C2 rep2 | false / false | 1,673,242 | 1,500,672 | 172,570 | 17,284 | 58 | 224,340 | 374.659 / 377.354 |
| C3 rep2 | true / true | 1,080,594 | 996,352 | 84,242 | 11,748 | 63 | 115,735 | 270.022 / 272.906 |

这里的 input total 已含 cache read，不能再次相加。字符、调用数与 token/时间是不同量，本表不作单因果成本解释。rep2 完成后再作逐次重复性比较。
