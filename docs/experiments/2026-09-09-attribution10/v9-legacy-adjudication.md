# V9 legacy：三个 rep1 的独立裁决

更新：三个 rep2 现已全部裁完，见本文后半追加节。前面的 rep1 评分与证据保留，不以重复结果替换；六跑汇总在文末及 JSON `rep2_review.all_six_run_summary`。

冻结源 `0be4164`，实际 GPT-5.5 / medium / native，均为 reference 提交。只审已完成的 `formal-v9/{member-center,dice-entry,splash}/runs/tools/rep1`；没有读取未完成重复、私有 holdout，没有修改旧评分、原始池、参考答案或运行产物，也没有调用模型。

沿用 [锁定核心口径](core-rubric-reconciliation.md) 和 [protocol](protocol.md)。原始 `reference-v1/legacy-reference.json` 未变（SHA256 `2c015536094fff1e42bb3b6b5cc2dce743c0f2a0f6924254027f7f8a5faac927`）。逐项事实状态、原文行散列、引用定位及完整指标见 [JSON](v9-legacy-adjudication.json)。事实细项比例不是准确率，core 也不是完整可审计归因通过率。

## 结论

| 题 | Core | 原事实细项 | 核心判断 / 独立标注问题 |
|---|---|---|---|
| S3 Member mask | pass | 2 supported、1 partial | 三站点和 1 透明 + 2 深色正确，H5 未点名仍是既定 minor；没有伪造 mask repair 版本。 |
| S4 Member price | partial | 2 supported、1 partial | 两轮价格修复、private 来源和真实编译正确；仍漏 Slice8 早期 Kotlin 输入→错误整写。tail 已独立为事件，不再假绑 v40。 |
| D1 Dice bridge | pass | 3 supported | 保留生成方实际输入调查，区分后续测试要求；10/10 与 AppStorage 不可观测没有混同。 |
| D2 Dice observer | pass | 2 supported、1 partial | ECAT 要求、SDK/入口读取、三次 Edit、编译边界正确；漏 may-throw WARN 属 minor。未重现 V8 rep2 的明确 memory“修复后”错述，但时序未查完整。 |
| S1 Splash BACK | partial | 3 supported、1 partial | 初版、entry-setup 删除与 Slice11 决策有据；只答 NavBar 兜底，漏实际 onWillDismiss 修复。另仍有 Slice11@v38 精确节点错绑。 |
| S2 Splash system bars | fail | 1 supported、2 partial | 整体隐藏/恢复方向正确，但两处明确把先前脚本新增的隐藏/import 归成 v53 才新增；还将主会话主题文档存在升级为生成方已经获得。 |

六题次 core 是 3 pass / 2 partial / 1 fail。已确认的额外实质问题三项均在 Splash：错误版本归因、错误新增效应时序、没有传递证据却声称已收到主题输入。不能据机械 check、token 降幅或 core pass 的部分题目宣布联合目标达成。

## Member：绑定改善，近因调查仍未补齐

报告：[verdict.yaml](../../../../_migloop-eval-20260909/attribution10/formal-v9/member-center/runs/tools/rep1/verdict.yaml)。本次 23 次 action，0 次 agent、0 次 blame；主要查看后期 fixer 和 builder，没有打开 Slice8 的早期源码输入或整写。

S3_E1 使用 `#a68daf720e780b4c2:15406@L103`。原始 fixer L103 的 `open(path,'w').write(new)` 位于 `report.append` 前，L104 同 ID `toolu_01T6WkXMhD7rUsHaSaMPuhgx` 成功回执确实列会员页 `3 sites import=+`。原始扫描 L71/L77/L80 给出 AppLoad 206、PayAgreement 704、RenewRule 728；脚本跳过已有 mask，分别填透明、深色、深色。L106/L107 只抽样读回 Pay，不能据此冒称三处设备验证；也不能因为没有正式版本就抹掉脚本已经执行的证据。本稿写“实际落盘值主要由脚本逻辑、脚本成功输出和脚本前 builder 分类联合支持”，整段没有否定执行，core pass。H5 既有透明仍未点名，是与旧稿同尺度的 minor。

S4_E1 使用 `#a68daf720e780b4c2:15731@L592`，不是 agent@v40 节点。原始 L592 在 21:30:17.239 写固定两个 Span 和 private helpers，L593 同 ID `toolu_01BrL9dsi5PB64tZiKVRfWoa` 在 21:30:20.292 返回 `ok` 与价格区读回。报告正确承认它是无正式效应版本的 tail 事件；若查看器列前一效应 v40 作为 context，它只能是上下文，不是该事件的版本或错误节点。随后 builder L23/L24 原生 private 错误、L32/L33 与 L34/L35 两 Edit、L36/L37 及 L39/L40 成功构建，均支持其价格/编译说明。没有把发现者当原始错误来源。

但原始 Slice8 `agent-aslice8-pay-80bbb1f44b77da0f.jsonl` L21/L24 在 07-24 15:33 已返回 Kotlin `replaceSpan` 数字段逻辑，L264/L265 在 16:04 成功整写却将非滚动后缀一起设 30vp。本稿只读 round-1 fixer L521/L523 的后期 XML/Kotlin，不能替代这条早期输入链。S4 仍 partial，不以少标红、更多“无法确认”算改善了核心近因。

S3 expected 引用 L605 是后来追加的 attempt，报告已称来源主张；不能另将其视为 L103 前实际派发的指令。S4 v10→v16 只作显式声明的调查区间，报告已说明 v10 是其他按钮修复，不把 v10 宣称成最初错误作者。

## Dice：核心链保留，memory 暂不判重复错述

报告：[verdict.yaml](../../../../_migloop-eval-20260909/attribution10/formal-v9/dice-entry/runs/tools/rep1/verdict.yaml)。实际成功打开 generator@v2、bridge@v4、observer@v3。设计 §F 的单独 file 导航失败，但派发全文、实际 Read 索引与三次成功 Edit 支持 D1 核心；没有为该失败伪称已展开全文。

D2 已打开 observer SDK 原文和 gate-build L43/L44 的原生 CompileArkTS、PackageHap、BUILD SUCCESSFUL；没有展开 WARN 专门日志，也未说 0 WARN。观察者回调仍未知。D1 的 later final-summary@v1 66 行在 transcript L160 被实际返回，包含等价通道 10/10、onNewWant×3、7 项不可观测以及 AppStorage 只作旁证。这是历史总结，不是本次直接重核全部 native 回执。评审另在原始 `593d4e86...jsonl` L260/L267 重核真实回执，仍作为旧 oracle 外的共同 addendum；它们发生于 21:01，早于 21:19 observer 修复，不能拿来认证 observer 修后运行。

本稿 memory 原句为：“要求来源可确认到 ECAT 修复任务和随后写入的 generator memory 条目；memory 条目是后续沉淀，不证明早期 Stage 1 当时已有该要求。”这不是 V8 rep2 的“时间在修复后，不能作为本次修复的先验来源”。按整段比较对象是早期 Stage1，不强加“修复之后”读法判重复错误。

不过它仅从修复后的搜索打开 `_index@v2`；transcript L175 已显示 v1 21:12、v2 21:57。原始 `257fed22...jsonl` L119 的 feedback 在 21:12:53.922，早于 observer L41–L45 的 21:19:24–39。应明确区分两者，现有稿未完成这一调查。早于修复也不证明 fixer 确实读取；本轮只记录“明确错述未重现”，不宣称时序问题已经完全解决。

## Splash：遗漏真实脚本，并再次混淆版本与效应

报告：[verdict.yaml](../../../../_migloop-eval-20260909/attribution10/formal-v9/splash/runs/tools/rep1/verdict.yaml)。47 次工具调用、19 次 action；8 次带 until 的搜索都截止当前池末时刻，其中四次只查 v53 之后，并非生成前输入核验。

S1 正确找到 entry-setup L123/L124 删除，而不是错归 Slice11。但整份最终稿没有 `onWillDismiss`，实际工具调用也未打开 fixer L346。原始 L346/L347 的同 ID `toolu_01DzVErQMcevEwF2f5T3E1U8` 先写真正 BACK 拦截修复并成功返回，随后 L352/L353 才另加 NavBar 重开兜底。后者不能代替前者，故 core partial。

另将 `agent:agent-aslice11-startup-50a0622bcfe4a588@v38` 标“进入·错”仍不正确：v38 对应 L342 的 **F001ViewModel DBPPTFactory import**；隐私控制器/isModal 解释对应 L236 agent@v22，D-020 重申对应 L250 agent@v26。本稿 reason 说的是正确 Slice11 阶段/actor，没有明确说 DBPPT import 引入隐私错误，所以该问题沿用旧口径列 material node_attribution_error，不仅凭它把 S1 从 partial 改 fail。

S2 更强的断言不能仅按“作者正确、坐标不准”处理：

> “后续 v53 才新增 import window、进入开屏隐藏系统栏、跳走/onDisappear 还原。”

逐版 coverage 又说：

> “v53 新增系统栏显隐：进入开屏隐藏，跳往 Guide/Home 前还原，aboutToDisappear 兜底还原。”

原始 fixer L485 在 21:20:10.255 发起脚本，新增 import、aboutToAppear(false)、aboutToDisappear(true) 和 helper，写后打印 ok；L486 同 ID 成功返回在 21:20:13.995。L488/v53 是 21:20:24.982 的独立 native Edit，**只补 onRoute(true)**。本次 transcript L145/L159 已实际返回 L485 的输入，报告也引用它；却在 actual 与逐版 coverage 两处把其新增效应合到 later v53。不是仅“到 v53 时已包含这些内容”的陈述，而是具体新增变更/先后错述，按既有核心时序标准判 S2 fail。整体隐藏/恢复方向仍在原事实细项列 supported，不用该细项冲抵错误。

S2 另称“生成方获得了 … resource/ui-manifest 中 `.Launch` 主题全屏透明系统栏信息”。其引用 `#9b3105a2:192@L520` 是**主会话 Write**，只证明早期文档存在。实际 converter v1 前输入中，resource-mapping 两次原生 Read 的 L11/L20 正文没有该主题项；L40/L54 只有 ui-manifest 路径索引，未有主题全文传递。已有 meta/spec/skill 说明全屏/安全区是事实，但不能升级为 `.Launch` 细节已经交给生成方。这是传递证据过断言，而不是评审从缺少 Read 反向证明“它绝不可能收到”。原始主会话 L404 在 07-23 12:36 的主题回执仍在池内；本稿打开 L520 早期文档足以支持“早已有”，不因未使用 L404 这一指定 locator 单独判错。

## 机械完整性与查询来源边界

三份 YAML 字节 SHA 均等于最后实际 check 草稿 SHA，`verdict.json.raw` 与最后调用的 draft 逐字相等，保存的正文也一致；各自 trace identity bound，最终 reference 被接受且 matched。没有发现这三份报告发生 source/body swap。各稿去重后的 20 / 18 / 13 个原文引用，其转录标签与物理行都唯一存在；JSON 留下原始事件 ID、时间和行散列。定位成功不证明所述变更、历史输入或归因成立。

Member 2 个 event_claims 的目标作用域与原始命令目标相符，未新增版本；Dice/Splash 没有 event_claims。三份模型 reviewed 分别 11 / 6 / 2 条，系统补集分别 27 / 1 / 27 条，明确是 `source=system_manifest, model_claim=false, not_investigated`，不是模型“已阅”或 `not_repair`。`complete=true` 只机械交代清单，三份 `declarations_complete=false`。Splash 必要脚本进入补集没有造假“看过”，但仍漏答核心；正文解释过的 L485 也不能被错误 v53 行替代。

Member/Dice 最终 check 均 0 error / 0 warning；Splash 第一次原文 L252 是缺红节点 basis 的 schema error（无有效 document hash，metrics 为 unverifiable），第二次补 basis 后 0 error / 3 个中性 post-anchor warning。没有新证据查询发生在两次 check 之间。不能把第一次包装成通过，也不能把第二次格式合法或 warning 清单当真值裁决。

## 成本：观察值，不是质量验收

| 文件 | input（其中 cached） | output | input + output | 工具字符 / 调用数 | wall / e2e 秒 | 比同题 raw 两 rep 均值 |
|---|---:|---:|---:|---:|---:|---:|
| Member | 1,149,920（977,408） | 11,196 | 1,161,116 | 147,691 / 44 | 263.69 / 277.06 | -56.85% |
| Dice | 931,727（817,664） | 9,350 | 941,077 | 188,338 / 38 | 213.26 / 216.76 | -33.44% |
| Splash | 2,976,822（2,760,192） | 13,931 | 2,990,753 | 428,732 / 47 | 322.36 / 336.06 | -9.52% |

cached 已包含在 input，reasoning 已包含在 output，不重复相加。每个 V9 这里只有 n=1，raw 为已锁同题同池两 rep 均值，不宣称稳定性或普遍准确率。Member 绑定改善但仍漏最近原始输入；Splash 核心与精确归因仍有实质错误，所以这批不能满足“更省 token + 更正确归因 + 忠实 UI”的联合验收。

## Rep2 首批追加：Member、Dice（当时 Splash pending）

本节独立追加，不替换以上 rep1 评分。来源仍为 `0be4164`；Member 于 21:26:47、Dice 于 21:36:18 UTC 完成。最后仅检查 Splash rep2 的 metrics 完成字段，状态仍 `starting`、`ended_at=null`；没有读取其草稿或转录，暂不计分。JSON 的 `runs/summary` 保留 rep1，新增 `rep2_review` 单独存本节。

| 题 | Rep2 core | 原事实细项 | 与 rep1 的具体差异 |
|---|---|---|---|
| Member S3 | pass | 2 supported、1 partial | 现在点名 H5PayDialog 761 已有 mask、不在新增三处；仍未明示其原有值透明。三处 1 透明 + 2 深色及验证边界正确。 |
| Member S4 | partial | 2 supported、1 partial | 实际打开 Slice8 原生整写和 v7 价格片段，红节点绑定正确 agent@v12；但没有查看该 agent 早期 Kotlin 输入，mandatory 半链仍缺。 |
| Dice D1 | pass | 3 supported | 直接展开设计 §F / 模板 Mount Bridge，不再停于 Read 索引；仍正确区分后置测试桥、等价回放与不可观测 AppStorage。 |
| Dice D2 | pass | 2 supported、1 partial | 0 效应 builder 读回和构建日志成为两个独立事件，不造版本；未作 memory 修复后排除断言，仍漏 WARN minor。 |

### Member rep2

[报告](../../../../_migloop-eval-20260909/attribution10/formal-v9/member-center/runs/tools/rep2/verdict.yaml)实际调用 1 次 blame、2 次 agent（都是 fixer）、31 次 action。transcript L186 的 unknown-blame recovery 明示“最近可靠全文 v7 ← Slice8@v12，不是被替换行作者”，也给了累计输入 agent 入口。本次跟进 L264 action（L188 返回输入 19,780/44,250 字，并非完整读完）、v7 diff，以及 L197 的 v7 第 1120–1209 行；后者确实展示 `Text(...priceText).fontSize(30)`。因此“看到真实坏整写”成立，不因 action 被截断否定另一次精确 file 片段。

但模型没有打开 Slice8 agent 或其 L21/L24；S4 红节点 basis.expected 仍引用 **后期 fixer** L501/L521/L523。这不能证明 Slice8 在原写入前是否已有正确 Kotlin 数字段规则，而该原文确实在池内可恢复。比 rep1 多找到一半关键证据，不改变锁定的 S4 partial；也不把当前正确 agent@v12 宣称为新的错版本。

S3 这次通过 fixer L42 的 controller 索引与 L71/L77 计数/缺失清单，明确把已有 H5 排除出三新增。S3 的四个事件是扫描、清单、批量写、只读抽样；S4 第五个事件单列 tail L592 并明确不是 file@v17。没有再将 tail 作为 v40 效应。普通 fixer@v34 的 reason 虽回顾早期 v33 和后期 tail，但已在文字/独立事件中分开，不能把所有普通 evidence 引用一律当成它声称“此节点内发生”。

覆盖清单是 18 条模型 reviewed（其中 4 条 out_of_scope）+ 20 条系统未调查补集。v10/v13/v14 及静态 git-status 候选没有被判成 not_repair。两次 check 之间仅删除正常/无法确认对象的进入点列表，没有新增原文查询；6 个声明冲突 warning 变为 0，不是因果真值认证。

### Dice rep2

[报告](../../../../_migloop-eval-20260909/attribution10/formal-v9/dice-entry/runs/tools/rep2/verdict.yaml)实际成功打开 generator、bridge、observer 和 Step4；19 次 action。transcript L127 直接返回设计 §F 第 224–232 行，明确 Want→AppStorage、EntryAbility 侧消费及 ComponentV2 约束；生成时点与后置要求没有混为一谈。后续 summary 分页已展开，描述等价回放、onNewWant×3 和 AppStorage 不可观测，没有要求它必须复述“10/10”这几个字符来得分；本次仍未直接重核 593d L260/L267 原生回执。

D2E1 `#a635575c78cd15ff6:647@L33` 是真实 builder Read，L34 同 ID 返回 v8 代码；本次 L187 已展示 import、register 调用及桥仍在。D2E2 `#a635575c78cd15ff6:656@L43` 是构建日志查询，L44 返回 CompileArkTS/PackageHap/BUILD SUCCESSFUL。该 builder 没有正式效应版本；本稿在一次非法 builder@v2 导航后改用 action，并用事件承载证据，没有伪造 builder@v1/v2。报告没有把编译认证成 callback 实际触发。

memory 本次没有被作为时序排除依据，也没有追早期 feedback，因此只记“没有该错误断言”，不算已经厘清时序。候选 `#616@L51` 实际展开 git diff stat + grep clean 静态自检，报告未把它当新写版本或行为验收。7 项均 reviewed，`declarations_complete=true` 只是逐项声明完整。两次 check 仅移除了与角色冲突的进入点列表，没有改证据或新增查询。

### Rep2 原文绑定及配对成本

两稿所有原文标签/行均唯一存在（Member 24、Dice 15 个稿内去重引用）；raw 与最后 check 草稿逐字一致，YAML 字节 SHA 分别为 `bcf3c7403a18839953acb36b834ce61caf675dd76897b3111c7d1c549e59f04a`、`e3d6737fc06127163ce839edb67b8950e2e95da9f2bf5a4527c60661b3bfbeb6`。身份 bound、提交 matched，不等于报告语义无缺项。此次未找到 Member/Dice 新的“node 与 basis.actual_evidence 精确效应版本矛盾”反例；不能为了设计新校验制造一条错误，也不能把 expected 的后置参考自动判为不合法反证。

| 文件 | Rep2 input（cached 已包含） | output | 总 token | wall / e2e 秒 | 两 rep 均值 | 相对 raw 两 rep 均值 |
|---|---:|---:|---:|---:|---:|---:|
| Member | 1,994,278（1,860,096） | 17,363 | 2,011,641 | 391.64 / 406.49 | 1,586,378.5 | -41.05% |
| Dice | 1,211,509（1,092,608） | 13,224 | 1,224,733 | 291.61 / 295.47 | 1,082,905 | -23.41% |

Member 两稿仍同为 S3 pass / S4 partial；Dice 两稿 D1/D2 pass，均有 WARN 小缺项。重复成本明显波动，不替换 rep1、不选最优。这次首批追加时 Splash rep2 未评分，以上十个已裁题次不是完整六跑结果；随后完成的裁决追加如下，rep1 Splash 的既有实质错误仍保留。

## Splash rep2 完成补充与六跑汇总

[Splash rep2 最终稿](../../../../_migloop-eval-20260909/attribution10/formal-v9/splash/runs/tools/rep2/verdict.yaml)于 21:40:20 UTC 完成，状态 completed、verdict_ok=true。确认完成后才读取正文及调用。它有 41 次调用，其中 **0 action、0 agent、2 blame、11 file、21 search**；14 次搜索带固定池末 until，其中 8 次仅看 v52/v53 后窗口。

| 题 | Rep2 core | 原事实细项 | 判定依据 |
|---|---|---|---|
| S1 | partial | 1 supported、2 partial、1 omitted | 初版 callback 与 D020/isModal 决策有据；没有交代 entry-setup 删除、实际 onWillDismiss 修复、另一 builder 后置成功构建。 |
| S2 | partial | 1 supported、2 partial | 主题早已有、生成方实际输入未证主题细节，边界比 rep1 准确；v53 只跳转恢复也说对，但没有调查入页隐藏脚本。 |

此次两个 recovery 返回并非完全没给原文入口：transcript L66 明确列 `#a68daf720e780b4c2:15567@L346` 为 **显式效应待核调用**，L68 同时列 L346 和 `#a68daf720e780b4c2:15655@L485`。模型只跟进初版/v42 快照及搜索，没有打开这两次真实脚本。L346/L347 的 onWillDismiss 与 L485/L486 的入页隐藏、helper、disappear 恢复，仍是同一原始 rubric 的必要事项，不能因为被系统补集列为未调查而免答。

S1 的进入节点改成 **agent@v26**，确实对应 L250/v42 的 D-020 注释重申，不再是 rep1 的无关 DBPPT import@v38。原句“在 v42 明确写入 CustomDialogController”“v42 装配了隐私弹窗”需要精化：v42 **快照**含 controller/onPop，v42 **本次 diff**只改 D020 注释，首次控制器代码在 L236/file@v38。整段没有明确声称“v42才首次新增 controller”，也确有新写入的 isModal 行为断言和正确决策节点，所以不把这种非唯一读法硬判成新的核心时序错误；它仍因三项 mandatory 漏核而 partial。

S2 不再像 rep1 那样声称 v53 新增隐藏/import，明确 v53 只 `onRoute` 恢复；也不再把主会话主题文档存在当成生成方已收到。它写“没有打开到生成方确实读取主题字面的证据”，并保留零命中不能证明不存在的边界。该限定是改善，但后续真实隐藏没有调查，故仍 partial，不以“更保守”自动过关。

本稿没有新确认的 material false claim；27 个候选均保留 `system_manifest / model_claim=false / not_investigated`。只有一个 check，0 error / 2 个中性 post-anchor warning，最终 matched。15 个稿内去重引用均能唯一定位，raw 与最终 draft 逐字一致，YAML SHA256 为 `a5ece00cd3f85e77972af20d3f676a21a5922795570d2451633fb6aa6322e44f`。这些机械事实不能补足未调查的修复。

Splash rep2 input **1,196,332**（cached 1,051,648 已含）、output **9,755**，总 **1,206,087**；wall/e2e **236.76 / 250.46 秒**。两 rep 平均总 token **2,098,420**，对同题 raw 两 rep 均值减少 **36.52%**。从 rep1 的 2,990,753 到 rep2 的 1,206,087 波动很大，而且后者又漏装配/构建环节，不将成本下降本身解读为质量提高。

六跑十二题次最终为 **6 pass / 5 partial / 1 fail**；rep1 的三项 Splash 实质错误原样保留，rep2 不替换它。Member 仍两次缺 Slice8 写前输入；Splash 两次都漏关键真实脚本、rep2还漏装配和构建；Dice 两次核心通过但 WARN 与原生验证来源细项仍保留。没有 pending legacy V9 run。这个结果不满足完整正确归因的联合验收，也不是十二个二值准确率试验或泛化结论。
