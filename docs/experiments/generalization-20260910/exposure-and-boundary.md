# 十三文件：曝光与样本边界收口（无 gold）

建议按两个独立队列登记全部13个文件，不挑arch11中“更合适”的三个，也不合并旧file-first-10分数。此处只冻结选取口径建议；runtime、调查任务、评分参考尚未因此冻结，没有运行模型、读取候选归因答案或执行历史命令。

| 队列 | 文件数 | 可以声称 | 不可以声称 |
| --- | ---: | --- | --- |
| dynamic1 | 6 | AIPPT同app、不同生成运行；限定旧experiments/handoff中未找到六文件逐项调查记录 | 未见app、未见工程、跨app保证 |
| arch11 post-Stage3 | 7 | AntennaPod不同迁移运行；明确内部检查点之后的既有文件原生修改队列；全部native正例入列 | 未见AntennaPod、全部未见文件家族、execute-final之后、第一次构建之前 |

两队列属于两个不同app谱系，但两种app都已有工具开发曝光，且阶段边界不同。因此分别报告结果、曝光层级与未知；13是任务数量，不是13个无条件独立或完全未曝光样本。AudioPlayerPage不得事后剔除、另选或挑最好重复来改善结果。

## 选取口径及完整名单

dynamic1沿用先前预声明规则：应用路径内，窗口前成功原生Write，窗口后至少两笔成功且非同文的原生修改，历史至少两个actor；按规范化小写绝对路径SHA256升序，从29项合资格文件取前六。原始排序、所有调用定位及169文件manifest见[候选清单](candidate-dynamic1.json)。

1. `entry/src/main/ets/dialogs/LimitedGiftDialog.ets`
2. `entry/src/main/ets/api/HttpCore.ets`
3. `entry/src/main/ets/components/works/WorksView.ets`
4. `entry/src/main/ets/components/template/RecommendView.ets`
5. `entry/src/main/ets/db/PptDb.ets`
6. `entry/src/main/ets/pages/ChoicePPTTemplatePage.ets`

arch11先定位明文Stage3完成及随后全工程FV-1关卡，再查既有应用文件的成功原生修改；全部7项入列，不按修改原因、模型预期表现或调优便利择优。它的阈值不冒充与dynamic1完全相同：arch11包含只有一笔后窗Edit的route_map。7文件共21笔后窗成功Edit；初始Write及所有后窗Edit的完整source/line/block/call_id/时间在[检查点资格JSON](arch11-checkpoint-qualification.json)。

| arch11文件 | 后窗成功Edit | 限定旧产物中的文件级曝光 |
| --- | ---: | --- |
| `entry/src/main/ets/pages/AudioPlayerPage.ets` | 3 | 旧pod730明确模型调查目标：3份result、3份prompt、3份metrics及1份judge产物命中 |
| `entry/src/main/ets/pages/VideoplayerPage.ets` | 3 | 旧Dice调查transcript一次字面提及；没有据此认定它曾是明确调查题或gold |
| `entry/src/main/ets/pages/Media3VideoPlayerPage.ets` | 3 | 旧限定范围无basename命中 |
| `entry/src/main/resources/base/profile/route_map.json` | 1 | 同上 |
| `entry/src/main/ets/pages/FeedItemlistPage.ets` | 7 | 同上 |
| `entry/src/main/ets/pages/FeedInfoPage.ets` | 2 | 同上 |
| `entry/src/main/ets/viewmodels/ItemPagerViewModel.ets` | 2 | 同上 |

7项是原生资格种子，不是全池修改效果的穷尽全集。后续gold阶段必须检查与这些目标相关的脚本、失败、过渡版本和前置任务；不能因选取阶段只用了native正例，就排除后续可证的脚本效果。

## 曝光审计：只查字面量和产物路径

检索覆盖`migloop/docs/experiments`和`C:/Users/hongy/projects/_migloop-handoff`，排除本轮新目录`**/generalization-20260910/**`。使用`rg -l -i -F --hidden --no-ignore`，只接收命中文件路径，不打开命中行、模型答案或旧judge正文。完整检索词、数量与路径在[exposure-metadata.json](exposure-metadata.json)。

- `transfer-app-arch11`和完整root UUID均0命中；`AntennaPod`、`de.danoeh.antennapod`字面量也为0。它们不推翻业务谱系元数据和pod730曝光事实：arch11缓存的Android源指向`AntennaPod-develop`；旧`2026-09-08-pod730`目录已有raw/tools/tools2调查和judge。通用`com.example.myapplication`不是可区分app的身份依据。
- Audio的实际产物根为`docs/experiments/2026-09-08-pod730/`，命中`{pod_raw,pod_tools,pod_tools2}/chain90-AudioPlayerPage.ets/{prompt.md,result.json,metrics.json}`及`judge/pod_tools_vs_pod_raw.chain.json`。这证明同名文件家族曾是明确调查目标；不证明arch11的具体版本或原因与旧题相同，也没有读取旧答案来作此判断。
- Video唯一命中`docs/experiments/2026-09-08-verdict-ui/dice_via3/chain02-EntryAbility.ets/rep1/transcript.jsonl`。只登记“调查转录出现过此字符串”，不由一次提及升级成旧gold或该文件因果调优。
- dynamic1项目、完整root UUID和六basename均0旧范围命中。但已有`dist/dynamic1-20260908.html`、README使用示例及live缓存曝光；AIPPT业务本身已用于0723等开发实验。
- arch11已存在`dist/arch11-lineage-20260818.html`和live缓存。旧静态UI/导航展示属于项目曝光，不自动等于逐文件因果答案调优。
- 所有0命中都只是上述本地边界的字面量结果，不覆盖外部聊天、未保存产物、别名或一切曾经的人工阅读。

## arch11双锚点决定

原始根为ZIP内`462439ee-b5af-4443-8a58-2e785a2ef826.jsonl`。

| 用途 | 原始定位 | UTC时间 |
| --- | --- | --- |
| 生成期查询包含上界 | L2238明文：`**STAGE 3 完成!全 21 slice 全部接线!**` | `2026-07-18T01:23:20.239Z` |
| 后置修改资格排他下界 | L2243 Agent请求，call_id=`toolu_01HkxeGsEGcyLRderTGjGw6S`，description=`FV-1 Final Structural Closure` | `2026-07-18T01:23:52.130Z` |
| 全期调查观察包含上界 | 根L2309 | `2026-07-20T15:34:16.751Z` |

L2243的阶段头原文为`CALLER=a2h-execute STAGE=fv-1 ROLE=final-structural-closure（§6，进 a2h-verify 前 HARD-GATE）`。它是后置关卡输入，不应送入“截至生成结束”的查询或被当成最初生成者收到的需求；全期调查仍可读取它，并标清实际时间。

两锚点间31.891秒，全193份JSONL中仅有根L2239/L2241两个TaskUpdate请求及L2240/L2242各自返回。没有Write/Edit/Bash/PowerShell请求，没有应用原生写入。另核同源call_id配对：没有上述四类工具在L2238前请求却在其后才返回；没有L2238前的无返回调用，也没有无时间戳请求。原始定位与计数存于[边界和源可用性JSON](arch11-boundary-source-availability.json)。这些是限定协议/归档的结果，不证明世界上没有未记录的外部写入。

因此推荐保留双锚点，而不是把它们合并：L2238定义生成信息上界，L2243定义后置修改准入。虽间隔无应用写入，两者代表不同阶段语义。

已有任务状态核查也支持L2238：161次前置Agent尝试均已有终态，其中159completed、2次失败终止后有完成的补派；98次activity-converter均completed。最后原生终态为根L2236 `2026-07-18T01:22:40.914Z`，已配对completed子源的最晚记录为`2026-07-18T01:22:38.003Z`，均在L2238前。没有据此声称所有初次尝试成功或全部业务实现正确。此前已做过skeleton、batch、group等构建/检查，所以此队列不是未经任何修复的首稿。

## 原始资料能支持到哪里

arch11保留在`C:/Users/hongy/projects/migloop/dist/arch11-session-462439ee-full.zip`：385成员，193JSONL（1根+192子）及192meta sidecar。当前复核SHA256与先前一致：`9e3670140402600547399b1ed387da5d60bc52a413169abd733e9ea1491adf69`。不是由UI派生摘要反推原文。

后窗68次Bash均保留原生`input.command`字段，均有同源唯一成对tool_result，且返回在观察窗口内；4次`is_error=true`，没有`run_in_background=true`。本轮只检查字段存在、字节/字符长度、hash、配对与明确输出外存标志，不判断脚本具体目的或效果。每次的原始source、line、block、call_id、时间和命令SHA都已落盘，gold阶段可以逐项展开，不需要依赖当前文件版本或重执行历史命令。

68个已记录输出最大9328字符；前700字符内未发现显式`<persisted-output>`、“Full output saved”、“Output too large”或“Output has been truncated”标志，未发现该集合中的悬空外存输出定位。ZIP仅含JSONL/meta，不能据此保证所有被命令引用的外部脚本、临时文件或历史文件系统快照都已归档。4个错误返回缺少常规stdout字段，但原生错误记录仍存在；不能将它们误算成丢失配对。

dynamic1原始导出位于`dist/_sources/dynamic1-20260908/C--Users-hongy-projects-transfer-app-dynamic1`：78JSONL（1根+77子）、169文件含侧文件。完整manifest规范JSON SHA为`0810f41cf0aafaf745835639ac4eb60c902c22da660d3382e59e32c4175c8f6b`；[资格回读](qualification-check.json)已核169源hash与六个首Write加26个后窗Edit。页面workflow完成时刻`2026-07-29T01:59:05.818Z`与后续验证请求根L817 `2026-07-29T02:01:30.213Z`保持分别登记，观察上界根L2012 `2026-08-03T03:24:28.258Z`。workflow计算时长得到的结束时刻比保存的timestamp早2ms，该差异未抹平。

结论是“完整保留这些已记录源和后置请求/返回，足够进入有界原文调查”，不是“已经认证所有脚本效果或保证历史真值无缺口”。正式运行前仍须复制并冻结两套完整源manifest及明确任务窗口；gold若遇到外部文件缺失或执行含糊，保留unknown，不以意图、报告转述或外层成功补因果。

## 后续协议约束

- 保留全部6+7文件及原选择顺序，不因gold难易、工具得失、失败或未知调整名单。
- 两队列独立统计；旧raw/v1/v2/v3十文件结果不重算、不混入。曝光标签随每文件结果保留，不包装为完全未见app测试。
- gold和调查员视图分离；本预检不提供具体原因、诊断关键词、预期节点或作者结论。
- 资格是发生了后置修改，不是修改必需/正确，也不是最早生成者必然有错。脚本、失败、后置需求及过渡版本均在后续原文调查范围内。
- 本次只新增/补充实验审阅文档；未修改runtime、冻结报告或源池，也未启动模型。
