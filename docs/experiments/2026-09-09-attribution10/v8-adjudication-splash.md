# V8 Splash rep1：找对删除者，却用后续版本代替两段真实脚本

固定七事实为 **4 supported、3 partial**。比 raw rep1 正确区分了初始 callback、entry-setup 删除和 Slice11 接线；但 BACK 核心修复 `onWillDismiss`、入页隐藏系统栏都没有查明。两个核心回答仍不完整。

实际 GPT-5.5 / medium / native，冻结源 `b540cb2`，2026-09-09 19:48:20 UTC 完成。同 `reference-v1/legacy-reference.json`、同题、同原始 Splash 池；没有改 oracle、源、冻结产物或调用模型，也未读私有 holdout。逐原句、完整路径及 43 个不同原文引用的事件 ID / SHA256 见 [JSON](v8-adjudication-splash.json)。

## 固定事实逐项

| 原事实 | 状态 | 结论 |
|---|---|---|
| S1.f1 初版已有返回禁用要求和 onBackPressed | supported | 实际打开 converter 输入、Android onBackPressed 和初始 Write；没有诬称初版完全未实现。“正确输出”按静态意图理解，不认证初版设备行为。 |
| S1.f2 entry-setup 删除，D020 后续接受外壳差异 | supported | v1–v28 逐版 diff 已展开，file v6 是 entry-setup v7 的真实删除操作；没有像 raw rep1 错归 Slice11。 |
| S1.f3 Slice11 错信 isModal；finding 反驳；后修 onWillDismiss | partial | 前两段正确。实际修复 L346/L347 已追加 onWillDismiss，但模型没打开，最终只讲后面的 Navigation 复位兜底。 |
| S1.f4 后置其他 builder 成功 | supported | 已查询 builder 与主会话收尾，编译成功与设备复验分开。完整提交中信息在 S2 也计入，不苛求每题重复。原生 builder L36/L37 与报告相符。 |
| S2.f1 生成前主会话实际收到 windowFullscreen=true | partial | 打开了 07-23 12:43 的 ui-manifest v1，正确证明早期材料已有 Launch 全屏；但没有回到 12:36 主会话原始 theme 回执 L404，未建立本条“谁实际看见了原始主题”的完整事实。不是说早期方向错，也不强制某个唯一 locator。 |
| S2.f2 生成输入有 full_screen、安全区；细节传递未完整证明 | supported | converter agent 和实际 spec/meta/资源/source 多个原文已查；不把 style_sources 列表或搜索命中当历史读取。 |
| S2.f3 入页隐藏＋离页/跳转恢复 | partial | 正确描述后一个 onRoute 恢复 Edit；真实 L485/L486 已先加入入页隐藏、离页恢复和 helper，报告仍称隐藏“可能已存在”。 |

核心归因改善应保留，没查明的真实改动也不能因更保守就算答对。七行细项计数不是整体准确率；raw rep2 同为 4 supported＋3 partial，但它有错引与未锁定删除者，本次则有下述候选效应遗漏，不能用相同计数抹平差别。

## 核心缺口：正式版本不是唯一事实入口

以下均在冻结原池 `ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-a68daf720e780b4c2.jsonl`，不是当前文件推测或工具摘要真值：

| 原始调用 | 实际内容与回执 | 本次处理 |
|---|---|---|
| L346→L347，`toolu_01DzVErQMcevEwF2f5T3E1U8` | 替换控制器加入 onWillDismiss；重写“isModal 吃 BACK”的错误说明；明确 D020 只覆盖弹窗外；另改 Progress。`open(p,'w').write(s)` 后才打印 `ok SplashPage`，同 ID 输出还 grep 到新增回调的 hilog 行。 | 文件/agent 返回候选原文入口，但没有 action 打开。coverage 标 explained，理由是“候选写动作对应 v52 前的脚本输入，随后账本确认形成 SplashPage@v52”。 |
| L352→L353，另一调用 | 只追加 `.onNavBarStateChange`，栈空且隐私未表态时重新开弹窗。 | 正式 file v52 diff；成为 S1 唯一讲明的修复。 |
| L485→L486，`toolu_016H83iNne123bAaGFHtEhwF` | import window；aboutToAppear 调 false；aboutToDisappear 调 true；新增 setSystemBarsVisible helper。写入后输出 `ok`，随后 grep onRoute。 | 未 action 打开；coverage 同样将它解释为“v53 前脚本输入，随后账本确认形成 v53”，正文隐藏仍未知。 |
| L488→L489，另一调用 | native Edit 在真正跳往 Guide/Home 的 onRoute 开头恢复系统栏。 | 正式 file v53；模型只据此确认还原。 |

这四条不是同一动作的输入与产出版。后面的正式 delta **不能证明或替代**前面脚本的全部效应。账本因有限静态解析暂不为 L346/L485 建正式版本，可以保留谨慎标签；调查者仍能打开同 ID 原文，根据真实写入后的输出核实际操作，而不必补造版本或完整快照。

模型拿到的 agent 线索只露出 200 字脚本开头，两个正式 diff 只显示兜底/还原。最终 coverage 的 explained 既没有说明核心真实改动，也把它们和后续不同调用错误地连成“随后形成同版”。这是重要的完整标注问题，不能拿结构上的 29/29 遮住。

这些回执证明记录中的脚本已执行对应写入，不证明最终设备状态或完整行为验收。报告保留 round-2 未复验是正确的；本裁决扣的是可核实的代码修复未查明，不是要求凭编译宣布行为 fixed。

## 原始输入与角色的精度边界

主会话 `9b3105a2-85ec-4889-9786-b3c220f06754.jsonl:L404` 于 **07-23 12:36:37.214** 返回 themes.xml：Launch 主题含 `windowFullscreen=true`、透明状态栏/导航栏。07-23 12:43 的 ui-manifest 是后续生成的概述。本次在首 check 被拒后确实打开 ui-manifest v1 的 65–72 行，不能说只引用未打开搜索；但它没有追到原始主题回执和传给 converter 的链路。

S2 用“更像已有信息未传递/未转换成实现义务”是受限推断，不是已认证唯一 skill 或派发者根因。`进入·缺` 的红色仍是模型角色声明；搜索发现早期资料不补造 converter 的历史 Read。

S1 还有两点措辞/粒度需区分：

- Slice11 原注释实际说隐私弹窗**需要**挡 BACK，并错误相信 isModal 已经完成；“把 D020 豁免扩展到隐私门禁”比原文更强。更准确的原因是误判 API 已满足义务，而非有证据显示它主动允许隐私门禁豁免。报告其他段保留了这一区别，不算换错了 actor。
- 红节点 Slice11@v26 对应 L250 的 D020 注释改写，确实重申错误解释；真正引入控制器与最早 isModal 解释的是 L236，agent@v22 / file@v38。v26→file@v42 写边正确，但不能让 UI 把它显示成控制器首次引入。模型的“错误决策点”可解释为后续确认点，尚不足以声称最早进入点。

初始 callback 的静态正确意图不等于初版设备真值；历史 finding 是实际记录的测试主张，不等于本次独立复跑。模型明确保留了这两个界限。

## 调用、检查与 coverage

44 次调用：guide 2、sessions 1、diff 2、file 4、agent 7、action 16、search 9、index 1、check 2。16 次 action 全用完整 ref 且成功；7 次 agent 中仅 fixer via=sessions 一次被拒，后续正确重试。converter、Slice11、fixer 两个窗口和 builder 均有实际成功访问，不能把最终红节点直接当访问日志，但本次确有上游查询。

9 次 search 均用 until_ts，无 seq-only until；最初主题/状态栏查询截止在 07-26 后置全池末时刻，不是生成前窗口。本次没有把这些后置搜索等同生成方输入，而用实际旧 ui-manifest 版本确认已有信息。没有 blame 调用。

第一份 check（第 42 次，transcript L220）：1 error＋3 warnings。错误是用 search receipt 当 evidence；warnings 为 file v6 缺 basis、两个红 agent 的 actual 引用含后置 finding。

随后实际新增一次 file 查询，打开 ui-manifest v1；把 evidence 换成文件坐标。同时 file v6 从红降为无法确认，并非补了 basis。最后 check（第 44 次，L238）是 **needs_review，0 errors＋2 warnings**，不是 clear。后置 finding 可合法反驳旧代码；中性 post-anchor warning 既不认证原因，也不要求一刀切删红。本次保留两个红 agent，没有假造尾后新版本。

最终 43 个不同原文引用均对应真实转录/物理行；matched 只证明提交与检查的正文一致，不能证明候选与后续正式版的解释成立。

coverage：2 正式版本＋27 候选＝29，9 explained、20 out_of_scope、0 not_repair、missing=0。题外 mask/image 等留 out_of_scope 合法，不扣未调查无关事项；真正有问题的是本题两个关键候选已标 explained 却未说明其真实写入。29 项不是 29 个真实缺陷或修复。

## 成本观察值

| 指标 | V8 tools rep1 | 同题 raw 两次均值 |
|---|---:|---:|
| Input（含 cached） | 1,972,612 | 3,289,939.5 |
| 其中 cached | 1,778,688 | 3,031,552 |
| Output（含 reasoning） | 19,706 | 15,630 |
| Input + Output | 1,992,318 | 3,305,569.5 |
| 工具返回字符 | 350,484 | 7,060,047.5 |
| 模型运行秒 | 418.639 | 484.686 |
| 端到端秒 | 432.073 | 497.095 |

总 token 观察值减少 **39.7%**，模型运行减少 **13.6%**。cached 不再次加到 input，reasoning 不再次加到 output。单个工具样本不能证明稳定收益，且本次仍漏两段直接影响答案的实际脚本；因此省 token 的观察值成立，完整原始归因与 UI 语义忠实的联合验收尚未证明。
