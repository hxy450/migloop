# 从历史审查到可载入树：GuidePage 单例

本轮只验证一条端到端交付：历史 visual-verify 审查入口 → 自由调查 → 同一调查员提交 YAML → 逐条审查 → 原探索页面载入。不是新的基准成绩，不重跑原始组，不声称归因全对或已经节省成本。

## 运行与原稿

- 目标：0723 的 `entry/src/main/ets/pages/GuidePage.ets`，既有 F10-06。
- 起点：修复会话 `ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-aa2d7cdfd6a5cf89f.jsonl:235`，历史 visual-verify manifest 写入。审查声明不是标准答案。
- 生成截止：`2026-07-24T22:16:20.102Z`；观察截止：`2026-07-26T21:48:57.793Z`。
- 运行器复用 `file-first-10/run_raw10.py:launch`；干净索引，冻结调查代码（6b0d50d），没有加载旧报告或参考答案。原始只读 shell 与 inquiry MCP 均可用，实际调查使用 MCP。
- 模型和实际 turn_context：`gpt-5.6-luna / high`。只启动一次模型调查，无第二模型、无自动重跑、无人工改写提交；模型在同一调查内自行修订了三次提交。
- 时长 585.934 秒；导入 11.147 秒。输入累计 5,957,905（其中缓存读取 5,713,664，非缓存 244,241），输出 26,804。累计输入包含每轮重复上下文，不能宣传成仅消耗 244K 总输入。
- 最终报告：`6adf6cd7e4ba464d`，原稿 SHA256 `351c645e7864cf91fb4b3b3e2704d6451d108ffadcf47b68d9b2e7c249103203`。
- 本地产物：`C:/Users/hongy/projects/_migloop-tree-tests-20260912/review-guide-luna-high/`；YAML 在 `runs/inquiry/rep1/verdict.yaml`，完整模型转录、查询轨迹、提交原文、开销与审计同目录保留。
- 预览：`http://127.0.0.1:8878/?report=6adf6cd7e4ba464d`。只是本机预览，不是部署服务。

运行清单最初漏掉审计器要求的 `case.generation_end/observation_end` 与 `import_seconds`。补的是未变更 prompt 中的边界和实际导入耗时；原清单保存在 `manifest.before-audit-metadata.json`。模型输入、设置、冻结代码和 YAML 没改。不要把这项元数据修补混同为模型修稿。

## 核查结果与限度

机械审计：84 次独立查询尝试、79 成功、5 失败（其中原文展开 48 次、44 成功）；106 个发送帧均在宿主转录定位到，84 个结果中 51 个续读到了完整正文。其余结果没有全量续完，不能宣称全部材料已读。宿主出现过一次截断包装，详见 delivery-audit。最终原稿与 native submit 输入/返回和 final_answer 的 ID、hash 一致。

三类修改对应四个原生 Edit，引用和关系检查通过；原生修改差集没有漏项，相关调用清单没有未处置项。这仍只是当前索引清单及模型 effect 判断，不认证所有脚本语义，更不认证全部归因。

人工复核的事实边界：

1. 返回图标：生成者的 Android XML Read 回执（`aconv-guide` 转录第 19 行）有 `wrap_content` 和 `padding=20dp`；初始 Write（第 64 行）确有 `width(24).height(24).padding(20)`；返修 Edit 改成内容尺寸加 padding 的总尺寸。局部映射不一致有输入、输出、修改三方依据。视觉“不可见但可点击”来自当时检查者记录，不是本次重新运行验证。
2. 轨道：同一 XML 给的是控件 `layout_height=20dp`，内部形状由 `progressDrawable` 定义；初始 Write 的两条 Row 确是 `height('100%')`。Luna 最终仍把独立核查 4dp drawable 留为未知；审查者另外核到资源 agent `astage0-resources-a72c95c804e188d5` 第 155 行返回，三层 shape 均为 `height="4dp"`。这不证明生成者本人收到过该返回，更不能把本次审查者补查冒充 Luna 的证据。
3. 底部避让：历史 immersive skill 的实际 Read 回执（`aconv-guide` 第 43 行）规定宿主全屏页承担 Layer 3、子组件不自行 inset；meta Read（第 13 行）给 `full_screen_page / needs_immersive_safearea=true`。最终组装输出缺底部避让，与后修在宿主补 padding 对应。但把它进一步解释成特定编排机制，还不充分。最终稿把“可能是后置平台契约”保留为竞争解释，须结合后续组装者实际收到的合同继续核查，不能据此否定生成期已有的 skill 条款。

初稿把子组件未自补 safearea 也标为 origin，路径未闭合；模型自行降为 context。**未闭合本身不证明子组件无责**；支持降级的实质依据是历史 skill 的子组件豁免/宿主责任条款。

## 只补载入投影，不换 UI 或查询底座

此前报告的正常输入即使已经引用，也不作为树路径的目标：只画 origin/propagated，容易显得只查一跳。本次：

- 问题路径仍在 `tree.paths`，`complete/problem_nodes` 判据不变。
- 同一时序与证据检查另外给 `tree.context_paths`：显式背景节点，以及已引用 read/dispatch 的中性上游端点。
- agent 上的输入判断可以由该窗口内已确认的实际收件支撑，不要求拿输出 Write 充当输入证据。
- 普通候选不画；未连通的背景材料不硬接；系统补出的中性端点不冒充模型判断。
- 同一个旧 renderer 载入两类路径，节点原因仍来自未改动的 YAML，手动展开继续用同一 neighbors 数据。不是模型脑内推理或按调用顺序画线。

最终页初始是 **6 个节点、5 条实线**：GuidePage ← 两个生成阶段 agent；初始转换者 ← Android XML，后续组装者 ← 两个已读取子组件。原稿的 6 个问题节点主张均有历史路径（包括挂在根文件上的三项输出主张），不等于 6 个不同画框或 6 项独立缺陷。

尚有 3 个背景节点未接入：C 的早期 safearea 收件判断及其 meta、skill 端点。该 finding 没引用足够的早期写出/后续读取把它们连到后续组装输出。它们在载入详情中保留，不跨 finding 借用别的问题的证据制造连接。整条 skill → 后续组装的解释链因此尚未完整。

浏览器实测：载入后截图 `review-guide-live-browser/loaded-report.png`；点问题节点截图 `loaded-node-reason.png`；继续手动展开、原文、时间入口可用；0 个普通候选被误画，0 个 JS 错误，手动操作未污染模型调查轨迹。浏览器和调查模型均已退出，仅保留一个 8878 预览服务。

回归：219 个 inquiry 相关测试通过；新增正常输入路径、agent 收件理由、无关材料不得连接、读取前时间边界、与手动树合并/保留原稿等检查。GitNexus 影响检查提示路径投影为报告/HTTP 共用的高影响函数，未修改查询/索引语义；现有 `service.py` 与 DevEco 测试的其它未提交改动未纳入本次提交。
