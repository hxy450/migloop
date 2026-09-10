# 跨运行源发现修复：独立于 tools-v4

后续完整附件/显式身份合同扩展已收口，当前实现与最终测试以[source-contract-review.md](source-contract-review.md)为准。下文保留第一阶段JSONL修复的发现及红绿记录；最终边界已扩到root-stem全部普通附件，dynamic1为71 actor源+98辅助源共169文件，身份不再从主机路径猜namespace。

本修复由dynamic1源冻结预检触发，不来自候选归因答案或模型得分。没有读取gold、执行历史命令、运行付费模型或修改旧冻结报告。现有tools-v4旧十文件运行不包含本修复；跨运行candidate必须另行冻结修复后的代码与源池，并通过真实注册门，才能开始gold/调查。

## 元数据事实与原缺口

dynamic1导出中有78份JSONL：1根、70份`agent-a<16hex>.jsonl`及7份不同workflow目录中的`journal.jsonl`。此前“77子JSONL”是文件数量，不能解释为77个agent。70个agent stem均唯一；journal有7个同名stem。arch11 ZIP的192个子JSONL均为唯一`agent-a<16hex>.jsonl`。

dynamic1子路径实际为`<rootUUID>/subagents/workflows/<workflow-id>/...`，没有直接位于`subagents/`下的JSONL。旧`collect_cc`和`collect_cc_pool`的脚本预扫描分别使用平铺glob，所以只发现根；两处独立发现还可能在预扫描与实际收集之间纳入不同的文件集合。

本次只读取journal的type/字段名：记录是`started/result`，字段集合为`agentId/key/result/type`，无原生message、cwd或timestamp。它们不能按目录归给root，也不能把7份journal覆盖到同一`agents['journal']`，更不能从路径补派发关系。

## 当前接口及边界

- `cc_sources.subagent_paths(root) -> list[str]`：递归发现根自身`<root-stem>/subagents`树内全部普通JSONL，含journal和未知JSONL；保持原调用路径拼写和原平铺排序。主代理的pool_key复用此函数，完整源变化可触发失效。
- `cc_sources.discover(roots) -> CCSourceSet`：输出`roots`、`groups`、`actor_transcripts`、`auxiliary_sources`。原生`message{role,content}` envelope支持子转录识别；纯workflow journal为aux，未知嵌套源为aux。旧直接子目录中的未知/空转录保持兼容，但明确journal仍不造actor。不是以非`agent-*`文件名一律认作aux。
- `collect_cc_pool(..., *, sources=discovered)`及`collect_cc(..., *, sources=discovered)`：返回类型仍是agent字典；同一次发现的actor集合同时用于脚本预扫和实际walk，不把辅助journal当脚本执行者。已知aux原文通过独立registry保留。
- `build_ledger(agents, *, auxiliary_sources=())`：在identity冻结前纳入辅助源。辅助源进入source_stats及内容摘要，以portable逻辑源键区分同名journal，不赋actor。builder指纹新增`cc_sources.py`和`transcript_store.py`。
- 明确拒绝同池不同actor源的相同stem、不同根的sid8碰撞，以及同一个源出现于多个根角色。相同字节不等于相同actor；不合并作者。完全重复的同一根路径只发现一次。
- 符号链接/Windows reparse点显式拒绝；不跟随，也不默默跳过。来源边界是指定根与其自身subagents树，不扫描兄弟工程。目录层级从不产生parent或dispatch。
- 发现结果是本次文件列表快照，不是对恶意并发文件系统替换的安全沙箱；分类读前后检查mtime/size。生产调用仍应使用稳定冻结池。

主代理负责`service.py`集成以及`transcript_store.py`的无owner辅助registry和portable引用；本子任务未编辑这两份文件。引用方案与辅助源身份一起通过后续整体验证，不将新源覆盖宣称为因果质量提升。

## 独立验证

正式venv为`C:/Users/hongy/projects/migbot-elite/.venv/Scripts/python.exe`，测试显式设置`PYTHONPATH=src`，使用EVAL下新的独立basetemp。初次环境尝试遇到venv未editable安装以及系统pytest临时目录权限问题，不计作产品红测。

有效红跑复现8个目标行为失败：嵌套原文缺失、单根/池脚本未预扫、同根/跨根actor覆盖、sid8覆盖、嵌套源缺失、预扫与walk源集合漂移。另一个旧平铺兼容断言起初错误地要求Windows路径分隔符统一；已改为逐字比较旧glob产物，未借此改变旧路径表示。

- 新`tests/test_cc_source_discovery.py`：18 passed、6 skipped。覆盖递归/限定路径、unknown原文保留、journal无actor、任意合法native文件名、同stem/sid8拒绝、共享发现快照、脚本表、辅助源身份/统计、跨冻结路径搬迁及旧平铺ID/顺序/阶段兜底。6个真实符号链接用例因Windows无创建权限跳过；reparse标志拒绝用例通过，不声称这6项已实机执行。
- 旧回归联合220 passed：`test_atoms.py`、`test_collection_uncertainty.py`、`test_frozen_pool.py`、`test_source_visibility.py`、`test_transcript_tags.py`、`test_temporal.py`、`test_temporal_atom.py`。
- 真实dynamic1仅做元数据发现验证：`subagent_paths=77`；`actor_transcripts=71`（根+70）；`auxiliary_sources=7`（全部journal）。没有为此冷建原始账本或读取具体修改原因；正式78源registry及可展开门由主代理后续核验，不能把发现计数冒充已完成的端到端注册验收。

独立测试目录保留在EVAL旁：`cc-sources-red-01`、`cc-sources-green-01`、`cc-sources-green-02`、`cc-sources-regression-01`。未覆盖先前实验产物。运行时代码已停止编辑，等待主代理全套回归、提交及新candidate冻结；尚无gold。
