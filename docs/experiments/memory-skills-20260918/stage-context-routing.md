# 使用阶段与适用情境分离（0.4.0）

## 用户约定

- when：使用经验的任务阶段＋具体动作。根据偏差环节和预防动作定位，如“规格提取时描述图片约束”或“界面实现时选择约束”。
- description：当前输入可观察的适用情境，如依赖wrap_content、adjustViewBounds或固有图片比例。
- summary/why：历史偏差及机制；recommendations/how/check：下一次在该阶段的动作与检查。

卡片和提炼后的经验沿用这个分工。阶段不绑定历史agent名、时间戳或固定Stage序号。来源支持多个阶段的不同动作时，可形成分别适用的经验。

## 实现

1. pack接受并保留draft.description，若提供则检查非空文本；图仍使用原compact格式。
2. Memory.apply接受lesson.description并保留到版本快照，来源与requires失效机制不变。
3. browse/search的条目预览显示title、when、description（另有ID/topic/status等索引字段）；不加载why/how或证据图。read再读完整短经验。
4. 全文关键词检索包括description；title/when/description匹配加权。阶段仅作查询线索，没有额外阶段硬过滤。首版仍是词项/CJK检索，不宣称新增语义召回能力。

旧case/1和memory/1兼容：description缺失时保留原when与原始存储，不自动猜阶段或情境；预览显示空description。以后由维护者依据来源补齐并正常发布版本。路由条件更改也会触发已记录依赖的复查。

## 指令组织

前三份SKILL.md包含完整操作与模板，一次读全。移入的triage.md、protocol.md、query.md从活跃包移除，可从Git/安装备份恢复；card.md保留短兼容入口，指向唯一正式模板。第四个skill继续渐进式读取经验：目录/预览→短经验→需要时才读来源卡。

inquiry内核、UI、服务端、旧实验快照和已有真实卡片/memory均未修改。没有部署hook或云端服务。

## 验证

139测试通过、1个Windows符号链接权限用例跳过；四skill静态验证通过。测试覆盖字段往返、旧数据不变、空/错类型拒绝、仅description命中、阶段加权但跨阶段保留、预览不带证据正文、修订后依赖失效，以及实际图checker兼容。

提交前GitNexus整体报告high、涉及6条pack/search调用路径，已告知并逐项对照实际diff；单函数预检均low。修改保留来源采集、版本hash和图检查器原逻辑。另用已安装0.4.0 CLI读取上一版测试生成的实际memory，旧条目能查询，所有存储JSON的hash前后相同。

尚未据此宣称Luna归因准确率或真实召回率改善；本次交付是字段语义与数据链路落地。

四个包已更新到`C:/Users/hongy/.codex/skills/`，逐文件hash与仓库一致。安装器自动备份旧版于`C:/Users/hongy/.codex/.migloop-skill-backups/20260918T065939Z-da6428d414a6`。
