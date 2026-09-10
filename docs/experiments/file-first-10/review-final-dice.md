# Dice 冻结前交叉复核：主判断与辅助边界

2026-09-10。复核 `reference-units.json` 的 F10-03、F10-08 与旧 `review-v2/dice-index.md`，回查冻结 Dice 池原始字段；未读取新模型答案、未执行历史命令、未更改既有参考或评分文件。复核者已读过旧 Dice 样本，也参与新 Dice 候选底稿，属于开发暴露；本稿不是盲评结果。

结论：F10-03 指定核心事实核对通过，无需事实更正。F10-08 的 `identity-phase-and-conflict.supported` 把主判断和多个辅助反证连接成一句，若要求全部复述才给该单元分，会过严；冻结时应明确下述分层，而不是把整句当关键词合取条件。

## F10-03：判分所需的最小实质判断

| 单元 | 给该单元归因分需要解释的核心 | 不应强制复述的辅助细节 / 仅用于检查主动断言的边界 |
|---|---|---|
| label | 初版依具体交付规格使用资源文本 Roll；后期 Android 运行观测是 ROLL，修复在呈现层转大写。因此不能直接归为生成者忽略当时已明确要求的 ROLL。 | 不要求 AC14 编号、映射文档全名、主题继承全链、全部 call_id、资源读取的每个 API、精确时分秒；不要求复述“两条明确矛盾命令”，该命题反而未获证实。 |
| button-style | 已有按钮做形状、圆角/阴影等视觉对齐；这没有新增掷骰业务逻辑。 | 不要求列全 radius6、offsetY2、rgba0.26 等数字，也不要求给出唯一主题解析责任人；若主动声称全部视觉细节已复验，才检查其验证依据。 |
| test-integration | export 与新增 UI id 为后置单测/自动化访问接线，不能据此认定初版骰子功能缺失。 | 不要求三个 id 名称逐项复述、Step 编号或附加注释原句；未查明更早测试要求可保留未知，不须证明全池绝无早期要求。只说“新增测试接线”但把它同时归为漏做业务，则实质自相矛盾。 |
| logging | console.error 是视觉修复新增，随后 ECAT 才换为 hilog；不是初版生成引入。 | 不要求 hilog TAG/DOMAIN 数字、错误文本、全部导入细节；“更晚禁用 console”不能自动回溯为更早 actor 已知。没有主动声称 runtime 改善时，不要求专门列一段“未证明崩溃收益”。 |
| comment-policy | 后期质量检查驱动注释等整理；含 TODO 的无障碍资源/注释不自动等于未实现业务。 | 不要求列出每次注释 Edit、所有 AC/ledger/registry 编号或登记表单元格；目标文件之外的登记调整不能凭其存在就增设本文件漏答点。主动声称补完 TODO 业务、删除原资源或修改骰子算法才构成需要反证的错误。 |

上表是语义判断，不是要求调查员写五段固定答案。允许按自己的因果组织合并描述。20 次原生 Edit 是审阅覆盖账，不是20个判分点。文件级主因覆盖可同时记录修改范围漏项；不能因未抄数字、事件数或每条否定句就否决已解释的实质原因。

对于 label，具体交付规格与运行态的差异是本题核心，不是可删掉的装饰信息。仅解释“大写来自主题默认值”却不核当时实际交付内容，仍未完整解释生成期责任；但可获得另列的修改覆盖认可，不应顺带把其其它正确单元清零。

## F10-03 原始抽核位置

共同池前缀：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool`。以下 source 均相对该池，basename 写全；所有时间为 2026-09-03 UTC。`use→result` 已按相同 id 核对。文本缺席与脚本未知不扩成全历史形式证明。

| 事实 | source、物理行、调用 id、时刻 | 原始字段摘录 / 判断 |
|---|---|---|
| 具体 AC14 | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a349784d2663f1f0a.jsonl` L53→54；`call_e785b4fa907646d8a4003a05`；15:39:17.927→15:39:18.139 | Read `F001-dice-roll.md` 返回原文第80行：`判:ui ... 按钮显示 "Roll" 且源码引用字符串资源键`。不是只见资源名。 |
| 初版遵循该资源绑定 | 同一 `agent-a349784d2663f1f0a.jsonl` L75→76；`call_03b6a5a6c470427ca32a953a`；15:52:02.314→15:52:02.490 | Write 正文 `Button($r('app.string.roll'))`；没有 console.error；成功回执。 |
| 通用 allCaps 映射 | 同一 `agent-a349784d2663f1f0a.jsonl` L23→24；`call_9ba866ae361041d183f3a64f`；15:38:11.174→15:38:12.005 | 返回通用映射第57行 `android:textAllCaps → .textCase() 或手动转换`。这不是此按钮已解析为 true 的具体指令，不能与 AC14 拼成两条明确对立命令。 |
| Android 运行 ROLL | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a342b7d08c2ca580a.jsonl` L18→19；`call_abbbb1ef1ec14bb1b67d0dff`；17:42:46.455→17:42:46.576 | Bash 从 sweep XML dumps 提取字段，实际返回 `text="ROLL"` 与 `resource-id="com.example.diceroller:id/button"`。 |
| 视觉修复同时引入大写与 console | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a4874344c8fb6228d.jsonl` L68→69；`call_af435780b0de41ebafb443b1`；18:29:11.587→18:29:11.605 | Edit old_string 只有既有 onRollClick，new_string 追加 aboutToAppear、`getStringSync(...).toUpperCase()` 和 catch 中 `console.error(...)`；成功回执。 |
| 按钮样式调整 | 同一 `agent-a4874344c8fb6228d.jsonl` L70→71；`call_372fc11fa9ea4d0b9d6cb347`；18:29:21.552→18:29:21.758 | `Button(this.rollLabel)`，新增 Normal、borderRadius4、shadow；fontSize36、主要布局约束保留。 |
| 单测 export | `81e0a463-c9d3-4a7a-a671-b7f064830af1.jsonl` L3231→3233；`call_6977637f2b9e4a50aaac88a8`；18:39:07.392→18:39:07.441 | `class Dice` → `export class Dice`，新增注释明确 arkxtest 可见性；没有改 Dice 方法。 |
| 后置 id 接线 | `81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-aa1ccf93d575837a2.jsonl` L1 派单19:07:48.558；L22→23 `call_092afb020ddf4820ba7d28a7`，19:08:28.558→19:08:28.573；L25→26 `call_01ec83a7fd654ee3953d8eeb`；L28→29 `call_905a3efe7d694017a21b4add` | 派单明确“只做 ID 注入与 manifest”；三个 Edit 只追加 id/必要注释，且都有成功回执。 |
| 后置日志政策 | `2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a228e9716d833cbf3.jsonl` L1 派单21:16:51.419；L57→58 `call_61dff5fdb64446998c12315e`，21:19:36.408→21:19:36.415 | 指令要求 console→hilog；实际 old/new 明确替换同一 catch 日志。能确定更晚的明确要求，不能据此断定视觉 actor 更早已经收到它。 |
| 注释清理不同于补业务 | 同一 `agent-a228e9716d833cbf3.jsonl` L1；L66→67 `call_5a523f8e17d14cdeadc68f1d`，21:19:45.623→21:19:45.946 | 派单明确 `.accessibilityText($r('app.string.todo'))` “代码一行都不许删、不许改”；实际 Edit 只改该处注释，从“大写TODO/占位”转为资源键引用说明。 |

旧底稿包含早期 UI 路径受阻、后期另一套 replay 成功与不可观测项，这些是验证范围背景。本次未重新审尽 replay，未用其要求调查员背诵10/10、21/21或7项不可观测；只有在回答主动主张“全视觉通过”或“截止仍无任何后验记录”时才按对应原始证据检验。不存在新运行认证。

## F10-08：需要拆开的主判断和辅助反证

| 现有单元 | 主判断，满足即可取得该归因单元的核心认可 | 辅助反证，不提及不能自动清零 |
|---|---|---|
| identity-phase-and-conflict | 初期 dev-identity 明确禁止改 bundle/vendor；后期 ECAT 身份任务扩大范围并实际改了这些字段。因此默认值保留不能直接归为初期 actor 忘改/不遵指令。 | vendor 的第二段规则与不得 example 的冲突；后续 `com.example.*` 检测器继续误报源包名；真实厂商名、签名与安装是否最终确认。它们用于约束相应主动断言，而非必须全列才能理解阶段主因。 |
| icon-scope | 既有 entry 分层资产被复制到 AppScope，配置 icon 引用随之切换；解释资源作用域补齐与引用变化。 | md5、精确字节数、保留 app_icon 的名字、初期完整图标策略仍未知；不能由复制自动认证 Android launcher 迁移完成。若回答只说“补图标”而没有说明实际来自既有 entry/作用域转移，修改原因尚不充分；若已解释这个关系，未再逐项列上述限制不应失分。 |

最小判分例：回答解释了早期禁改→后期扩大身份范围，也解释了 entry→AppScope 图标复制和引用切换，但没有提 vendor 第二段冲突或检测器正则，两个核心判断都成立。回答只解释身份阶段而完全漏掉图标，可计身份单元，另记图标单元未完成；不应将整文件判为“归因全错”。

“辅助”不表示可以胡说。若主动断言 diceroller 是已核真实厂商、原包名一律不合法、旧图标引用必悬空或 Android launcher 已被证明逐字节迁移，应按该断言的原始证据计入精确率/错误项。是否推翻已获得的主判断，要看它是否实质推翻阶段责任或资产来源，不把每个辅助错误机械等同于该文件全部归因无效。

相关 F10-08 证据已在 `candidate-dice.md` 原文核对，此处只列冻结解释所需定位，不再次穷尽历史：

- 早期禁改：`81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a39c5351955d3cd6b.jsonl` L1；Read L23→24 `call_d4970dd01f094b548d8da86d`，实际 skill 也写 dev-identity 跳过 bundle/vendor。
- 后期扩大范围和三字段 Edit：`2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a87804892da9cfc8b.jsonl` L1、L49→50 `call_2a22aef71a3641f19092ca7c`；配套资产 copy L45→46 `call_c8f9430feac54929af417cb1`。
- vendor 冲突只在讨论其正确性时要求核查：同一 `agent-a87804892da9cfc8b.jsonl` L1 与 L25 skill正文、L60 修复者取舍自述。后者不能自证取舍无冲突。
- 源包名与检测器反证：`70f369a3-58ac-4f4f-b30a-45e8497983b6.jsonl` L73→75 `call_5d7033b366a34cea9fd97315` 返回 Android applicationId；L157→159 `call_66591deda54c419daa094142` 返回检测器 `re.match(r"com\.example\.", bundle)`。

建议在读取本轮模型答案前冻结这一解释：`supported` 是允许成立的参考内容集合，不能把所有分句都当作全有全无的评分前提；`reject` 检查主动错误主张，不是必须逐条复述的否定清单。本稿未调整单元数量/分母，也未查看任何答案来决定边界。
