# V6 / V6B：完整报告、引用交付与原始组

范围只有 Member（S3/S4）与 C4，均为已用于开发的题，不能外推十题或新项目。工具八跑：document/reference各两题各两次；原始组四跑：两题各两次。全部 GPT-5.5 medium/native，冻结源4d5db4f、中性任务/原文池一致，所有运行完成且保留。

## 成本：有节省迹象，但不能挑口径

每行是两次重复的均值。总token为input_total+output，cache已包含在input_total。

| 任务 | raw 总token | tools document | tools reference | reference相对raw |
|---|---:|---:|---:|---:|
| Member | 2,691,060 | 2,420,181 | 1,925,176.5 | 少28.46% |
| C4 | 1,410,037 | 1,442,282 | 1,298,191.5 | 少7.93% |

reference四跑相对raw四跑的合计少21.40%；两个调查任务等权的降幅平均18.20%。不能只报合计21%而省略任务差异，也不能把最终小引用字数下降当作完整调查节省。Member reference rep1反而更贵、rep2较便宜，方差明显。两题的reference平均端到端耗时都仍高于raw，未证明省时。

document对照说明：reference两题都原样保住最后实际check的草稿，四次均matched；Member document两次最终回复都改过核查稿，均mismatch，一次还丢31条候选。这个交付保真收益是直接观察，不是原因正确的证明。

## 语义：仍未联合通过

- C4的静态近因、实际补丁/读回与R1未构建边界六跑都抓住。raw rep2和tools document rep1漏后续Harmony manifest记录；tools reference rep1对保存记录的设备级措辞略过强；其余也须分清记录与独立设备复核，没有一致胜者。
- Member的三站点1透明+2Palette多数抓住，H5跳过例外仍不稳定。原始两跑都未追到Slice8生成前的实际Kotlin输入；工具每个交付模式各一次追到、一次漏掉。工具reference还分别出现多归责converter、把不确定v14读取写成确定的错误，不能用链更深抵消。
- raw也有真实定位但语义不适配的引用（rep1 L605不是价格attempt）；工具引用全部可定位，同样不等于reason得到支持。
- 尾后动作挂在较早agent版本、无实际端点却填宽repair区间，是结构化结论仍要解决的表达问题，不藏在机械通过率后。

完整逐项依据在 [C4工具](v6-adjudication-codex.md)、[C4原始](v6b-adjudication-codex.md)、[Member工具](v6-adjudication-member.md)、[Member原始](v6b-adjudication-member-raw.md) 及同名JSON。评审回查原文，但已知组别，不称为双盲评测。

## UI与下一步

050eed4仅修布局，真实页面中独立搜索组件/子桩不再遮住已访问节点；原路线、原因、错误引用/缺失覆盖不改。复核仍发现两个未绑定路径候选被画到未来文件版本的读边，已如实记在 [UI报告](v6-alternative-viewer-050eed4-ui.md)，不能把几何通过说成关系全对。

V7把这类关系退回无版本的路径线索，另加未知blame续查入口、短guide和按需完整schema。V6没有用这些改动，不追记收益。继续统一reference交付，是因为原文一致性更可靠，不是已经证明它语义一定更强。
