# tools-v4 F10-08 双重复独立裁决

只审旧开发集AppScope/app.json5两份完成报告，不接触新13文件gold，不重跑模型。原core SHA为0d48f30f9e501eedd55b87e086590c72e8b7fb8096a939f56842b71703426497；分母仍为identity-phase-and-conflict、icon-scope两个单元。两份metrics均status=completed、postprocess.status=completed。

成绩文件位于 `_migloop-eval-20260909/file-first-10/tools-adjudication-v4/F10-08/rep1.json` 与 `rep2.json`，均已用score_raw10.validate_grade(base=tools-v4, contract_base=baseline-v1)通过逐字span、报告hash、冻结分母等校验。

| 重复 | correct | partial | wrong/missing | supported/asserted claims | hypothesis | major |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rep1 | 1 | 1 | 0/0 | 2/2 | 0 | 0 |
| rep2 | 1 | 1 | 0/0 | 2/3 | 1 | 0 |

两份身份主判断均正确：初期dev-identity明令不改bundle/vendor，后期ECAT扩大任务范围后改写，不能倒推生成代理忘改。辅助vendor规则冲突和检测器误报未复述，不清零主判断。报告没有声称diceroller是已核真实厂商或skill没有冲突；rep2“指定…diceroller”简化了输入中候选与优先级，已保留边界注释，不另拆重复因果主张。

图标两份均解释新任务和app_icon→layered_image，但漏掉已有entry三件资产实际复制至AppScope的核心作用域关系，计partial。都没有把脚手架资产复制认证成Android launcher迁移，未要求调查员重新构建或跑实机。D-003沿用脚手架与AppScope内部资源复制不天然冲突；报告对更深层策略正确性保留未知，不仅凭“策略改变/覆盖”措辞判错。

## 核回原始事实

原始池为 `_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool`。逐条读回实际JSONL，未执行其中历史命令。

| source完整basename | 行/时间/call_id | 支持与边界 |
| --- | --- | --- |
| agent-a39c5351955d3cd6b.jsonl（81e0a463…/subagents） | L1，2026-09-03T15:31:54.536Z，无call_id | 原始scope=dev-identity派单明确“硬边界：不碰 bundleName / vendor（部署期 D-009）” |
| 同上 | L33→34，15:33:04.075→15:33:04.109Z，call_4d7173d3a6a44651901a7f15 | AppScope已有app_icon.png；entry已有分层三件资源；当时旧icon并非悬空 |
| 同上 | L35，15:33:14.434Z；L72，15:36:09.564Z | 同时期thinking及完成回报说明按D-003不迁移launcher、保留脚手架；这是记录的判断，不认证完整上游权威链正确 |
| 同上 | L59→60，15:35:18.958→15:35:18.971Z，call_9eeac76f5b9a45d6ac08a6ef | 成功Edit只调整版本1/1.0，支持身份字段保留 |
| agent-a87804892da9cfc8b.jsonl（2f01bcdc…/subagents） | L1，21:17:38.624Z，无call_id | 后期派单扩大身份/资源范围，明确从entry逐字节复制至AppScope；允许skill准许时保留app_icon，仍需补资源 |
| 同上 | L45→46，21:19:00.755→21:19:00.809Z，call_c8f9430feac54929af417cb1 | 实际cp三个资源，成功返回三对md5相同；旧app_icon保留，不是生成新的Android图标 |
| 同上 | L49→50，21:19:08.646→21:19:08.653Z，call_2a22aef71a3641f19092ca7c | 一次成功Edit改bundle/vendor/icon三字段；不是三个修复轮，也不证明精确磁盘修改瞬间 |
| 同上 | L53→54，21:19:24.502→21:19:24.694Z，call_6e915aae02594c01bf2f5ec0 | 真实返回AppScope三件齐备、layered及内部background/foreground引用均[OK]；静态检查不认证实机/launcher像素 |

## 两份unknown的区别

rep1写“资源文件效应未在本 finding 中扩展认证”，限定了自己的认证范围，不等于断言原池不存在copy或验证；不扣精确率。

rep2写“没有确认的 AppScope 资源写入证据证明 layered_image.json、background.png、foreground.png 在该窗口内已补齐。”这没有同样限定为未在本finding展开，而是否定窗口内确认依据；L45/46的实际复制+md5及L53/54的静态检查反驳该历史边界断言，计一条contradicted。由于主因仍正确指向后期任务、未倒责生成或虚构行为成功，major=false。其“没有本次重新运行的构建或实机验证”是合理未知，未另外处罚；作用域混淆明确作为hypothesis，不放进asserted分母。

## 交付与调查停止位置

两rep均拿到后期完整派单，却没有展开L45/46复制回执，显示“输入已送达但未完成后续效应核验”与“工具根本没有证据”不同。

- rep1 query-trace step10包含修复L1原始3670字符、next_offset=null；step14包含生成L72原始2615字符。outer transcript L41（19:43:11.956Z）虽有聚合截断标记，仍保留“逐字节复制”文字。不能把outer聚合截断直接等同内层MCP正文从未交付；也不声称截掉部分仍在investigator最终上下文。
- rep2 step13 expand包含修复L1原始3670字符；outer L47（20:04:54.921Z）9042字符无截断、含复制要求。step22展开生成L35 thinking与L59/60版本Edit；outer L81无截断。
- 两rep的changes仅提供修复L53/54各240字符preview，不把有ref等同完整检查返回已展开。没有L45/46全文展开认证记录。

报告hash：rep1=f3d442ce9b142b48abc51bff1f286f6ed43e317172f381c9080ccdfb3bce3421；rep2=eb72a3140ce28ab75ea0425f1711c3d900e66517de26878f5813beeefe7cf2f3。各grade保留metrics、query-trace、transcript hash和完整source路径。YAML、图边、引用坐标的机械问题不自动换算为语义归因错误。
