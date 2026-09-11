# 同代码 Luna 推理深度对照

i03 medium已跑会员页和Dice Index；两个原稿仍needs_revision。入口改进帮助模型发现原来漏掉的脚本，但没有解决错误计数、原生边乱接和过早停止。为区分界面缺口与推理预算，另做high对照：模型仍gpt-5.6-luna，原池/任务/产品源码/通用GUIDE与i03完全相同，仅model_reasoning_effort从medium改high。先同两文件各一次，保留所有结果。

此前所有medium/raw结果不改、不重跑。high不是同条件优于raw的证据；即便成功，也必须把推理深度影响单列。产品验收可选择有效配置，但不能把它宣传成纯工具结构的收益。不改用户全局Codex配置。

Luna支持high设置：[官方模型说明](https://developers.openai.com/api/docs/models/gpt-5.6-luna)。实际是否改善只能由本次对照判断。`e7f07f4`保存i03产品及原运行器；新运行器仅扩展显式effort参数，旧轮次仍保存各自运行器/配置/源码摘要。

## 已完成四跑（2026-09-11）

开发者按冻结的scoring-core.json逐项核原文，不是独立盲评。核心原因覆盖与额外错误分开：次要细节未提不清零，但主动说错仍记录，不能用核心分掩盖。

| 文件 | 核心归因 | 模型秒数 | 总token（含缓存输入，不重复加thinking） | 已发帧完整呈现 | 图节点/可核边 |
|---|---:|---:|---:|---:|---:|
| F10-01 会员页 | 5/6，price partial | 1047.11 | 7,105,234 | 151/151 | 24/8 |
| F10-03 Dice Index | 4/5，logging partial | 1084.14 | 6,763,728 | 166/166 | 12/22 |
| F10-08 Dice app.json5 | 2/2 | 582.31 | 4,065,893 | 107/107 | 9/4 |
| F10-09 Codex Launch | 1/1 | 340.80 | 1,870,220 | 90/90 | 4/1 |

这是4文件14项中的12项核心覆盖，不是10文件整体分数，也不是12项完整报告无错。四稿mechanical_status均valid，但至少以下错误使整体验收失败：

- 会员页A原句“四个CustomDialogController没有maskColor”“扫描到MemberCenterPage四处”：Slice8原始Write `agent-aslice8-pay-80bbb1f44b77da0f.jsonl:L264`中4个controller已有1个maskColor；fixer `agent-a68daf720e780b4c2.jsonl:L104`明确回执3处。补透明/深色配置这一核心覆盖，主动虚构数量/初态另计错误，不代表本finding完全正确。
- 会员页B及unexplained原句“观察截止前无第二次编译成功回执”：`agent-af0e3d2ae54dbf769.jsonl:L37`在21:46:28.608Z明确`EXIT=0`与`BUILD SUCCESSFUL`，早于21:48:57.793Z截止。错误否定验证事实。
- 会员页price只追了converter的XML和无Kotlin原生Read，未核后续Slice8实际收到的Kotlin（L24）及统一字号输出（L264）。界定为partial，不能把“未找到唯一首因”当作已回答可证明的输入/输出问题。repair-compile在同一B中识别返修新增辅助方法、继发访问问题和可见性修补；按核心语义计覆盖，但错误否定编译成功仍单列。
- Dice C知道ECAT把console改hilog，却未定位console是视觉返修新增，logging partial；“生成阶段漏登记定位为空registry/自检分类”又超过D-002允许保留源侧todo所能支持的结论。不能因为后期审计这么定性就认证生成违规。
- Codex A原句“现有材料支持的已证局部原因是验证面只确认了结构/接线”：引用5717/5830是子代理检查报告，不足以确认所有实际验证行为；应限定“记录未提供命中验证证据”。Block→Default代码级近因仍符合核心，对最初作者和设备验证也保留了未知。
- Dice正文有`e-e6a9b4ad9dbf4a8b`等非有效原文句柄；结构化evidence数组可核，不等于散文里每处引用都可核。当前检查器未覆盖自由正文中的这类引用，不得把valid宣传成全报告引用无误。

app.json5的两条核心边界成立：A明确dev-identity禁止改bundle/vendor、后期任务扩范围，不把保留模板算忘改；B说明复制entry已有分层资源到AppScope，不认证Android launcher迁移完成。vendor真实主体未证实也保留了未知。

结论：high更能做完坐标和调用对账，但速度/总token代价很大，且仍出事实错误。不能靠升思考深度宣布工具完成。i04回到medium，对写前输入入口、只读形状折叠及通用反证规则做产品层验证。

原稿分别位于`inquiry-iterations-20260911/i03-high/F10-XX/runs/inquiry/rep1/verdict.yaml`；report_id依次为`672e7c81f600481e`、`7b6b1dba653e44f0`、`e5739feebe4f4ed3`、`5ab652714e1b43cf`。同轮全部运行保留，不选最好一次。
