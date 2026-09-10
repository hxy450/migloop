# 十文件原始组 baseline-v1

2026-09-10：已冻结并启动，尚未裁决分数。

- 冻结目录：`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/baseline-v1`
- manifest SHA256：`a26ed98abd0df003e0958791a8a2982425188f7cdaf853cbb06d80b046c33139`
- 10个文件、228份源JSONL、28个审阅端语义归因单元。题面不提供这些归因单元。
- `gpt-5.6-luna` / `medium`，每文件2跑，2并发，每跑1800秒；80轮仅提示、无强制轮数或token上限，无自动模型回退/调查重跑。
- 正式队列启动：2026-09-10 10:19:55 UTC；实时状态以冻结目录外层 `queue.jsonl` 与每跑 `metrics.json` 为准。
- 没有启动工具组、没有改生产MCP/UI、没有重新迁移或运行历史命令。

## 环境核验

现有 CLI 为0.153.4。采用逐次调用配置覆盖，不更改用户全局配置、技能或鉴权。禁用本次宿主技能、插件、网络检索、额外agent/MCP；仅原始组只读shell可用。`smoke-isolated-v2` 的原生转录确认实际模型/effort、没有宿主技能目录，并有且仅有一次成功的目录枚举命令，而非只相信模型回复的成功标记。

官方依据：[Luna模型](https://developers.openai.com/api/docs/models/gpt-5.6-luna)、[技能启用/停用](https://learn.chatgpt.com/docs/build-skills)、[配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。文档说明配置语义，实际是否生效以本次转录为准。它不证明操作系统已禁止一切池外读取；每跑仍需审计工具使用范围。

第一次预检 `smoke-isolated-v1` 在npm命令包装层因参数长度失败，没有启动模型。改用该已安装CLI的原生可执行文件后第二次通过；两份产物都保留，不计调查结果。

## 评分冻结的澄清

`private/scoring-core.json` 为核心判断合同，`private/reference-units.json` 为支持事实与边界集合，不能把后者每个分句都当必须复述。辅助细节未提不清零；明确错误指控、错归阶段/作者和假称行为验证分别核原句及反证。

最终交叉复核已读原始关键链并落三份报告：`review-final-0723.md`、`review-final-dice.md`、`review-final-rubric.md`。补充了会员页最早可见converter作者与较早private helper的区别。参考仍是有界开发参照，同模型体系交叉复核不是外部人工金标。

运行器与核验相关108条测试通过。生成参考、环境预检不计入调查员的任务token/时间；如报告工具总体成本，应另外计建账和提交处理，不能只比API输出。

## 裁决产物约定

`score_raw10.py` 只汇总明确写下的裁决，不自动让模型投票。每个判分保存最终报告精确片段、冻结合同hash、依据和理由。没有判分时显示pending，不制造0%准确率；超时且未交付最终答案计端到端未完成，不称其所有因果主张都错误。

先逐文件报告正确归因覆盖、实质断言精确率、重大错归、遗漏及耗时/token，再总结原始调查在哪一步失败。结果出来后才把实际失败映射到工具修改。
