# 新 13 文件：source-v2 首次同条件对照

本记录在首个调查模型启动前建立。候选、来源及参考已经冻结；当前还没有本轮正确率或成本结果。此前旧十文件的 v4 回归不被本次准备工作抵消，见 [v4 完整结果](../file-first-10/tools-v4-results.md)。

## 问题和分母

dynamic1 六文件、arch11 七文件，均只问整个文件实际修改及为何生成截止时未做成，不给修改族标题、数量或责任提示。独立取证后参考分别归并为9个核心修改族，共18个；每个文件两个重复，每组26跑。两个队列分别报告文件等权正确归因覆盖、核心 C/P/M/W、实质主张支持率、重大错误及完整文件通过率，不把52跑当作52个独立项目。

候选在新参考前固定。原始源取证者与另一审阅者回看原文、修改、实际输入、候选命令及反证；最终由主审批准24个私有产物。dynamic1额外有不调用migloop、不执行历史脚本的独立内容重建，与36次完整Read观察逐行相符。它不证明所有中间隐藏效应均已恢复。arch11的阶段边界为post-Stage3/pre-FV1，不冒称execute-final；其分批交付和占位许可按原文逐条区分。

这仍是**同业务、跨运行**检验：dynamic1是AIPPT另一运行；arch11是AntennaPod，已有页面家族曝光。不是未见业务泛化，也不是人工双盲。

## 冻结身份

本地根：`C:/Users/hongy/projects/_migloop-eval-20260909/generalization-20260910`。

| 产物 | SHA-256 |
| --- | --- |
| `source-freeze-1/source-manifest.json` | `92d42b2d7b7dcf6a5cbebb4498f2036ca0130be56a65f218e57d55905c9d0e89` |
| `candidate-source-v2/manifest.json` | `19d9a70955694ce4c9fce5aaedf77dcfa80ffe6f7e66a21eac74cc9b8367434b` |
| candidate code digest | `50c63af5702f8671811833bf3bf38720d766cecc41f18859a88e25b27434786d` |
| `reference-freeze-v1/contracts-manifest.json` | `1ff7229fe1026b589734f7a0dacfd05b28f337025e9a146ed56d4eb9878d1cbf` |
| `reference-freeze-v1/review-approvals.json` | `b120faa23fddbaf3a6f112261096bb47b8e913ef0f2a5570341cb351402d9c12` |
| `pair-source-v2-v1/manifest.json` | `37d1e36c1e9ff66e0e92c0471fc8892d3998924be87f2ad485396b1a3ae51b7c` |
| frozen `run_transfer.py` | `bf8cac6c4ff53ab30ebebfa7939c63b7e3e8f724fe1ed435c489dfa5e160e962` |

参考正式冻结时间：2026-09-10 21:42:38 UTC；源、代码和24个已审批文件在发布前后核哈希，没有模型运行。发布脚本的SHA为`2a27587249340a06703f3bef9297157121b8cb615eeb97bd4441c539f9eafba6`，对应提交`5aa1821`。root独立联合测试为199 passed、3 skipped；Windows junction反例通过，两个普通symlink创建受权限限制跳过。测试不是因果判断正确性的替代品。

## 执行合同

Luna medium、每文件2重复、并发2、每跑1800秒；先整个raw组，再整个tools组，无自动重试、修格式追问、模型降级或失败删题。新原始组完成后固定，不为压低基线反复重跑。两组共享源、边界和公共问题；工具组附通用工具/结构化输出说明，并承担其实际成本。

完整554文件注册、同预算MCP内容门及全部13公开目标的真实MCP入口已通过，详见[来源门记录](source-freeze-report.md)。正式package仍须完成自己的`smoke-offline`才允许启动。注册、部分正文投递、引用定位和因果正确分别统计。

评分使用[参考协议](reference-protocol.md)和[独立评分器合同](transfer-score-contract.md)。私有答案不进入模型材料池；运行器核其字节哈希但不解析答案。read-only限制和提示词不构成OS级读取隔离证明，调查轨迹仍需查是否遵守材料范围。成本是input+output，cache不重加；调查、含核验的端到端、并发队列耗时分别列。正式模型运行期间不跑全量pytest、性能压测或冷建其他ledger，以降低上一轮时间比较的后台负载混杂。

若新证据推翻参考，保留原版、登记修订并对两组对称重评。首次解盲后若用于调优，该批即为开发曝光，下次不能继续称留出。

## 执行日志（进行中，不是完整成绩）

package自身 `smoke-offline` 于21:44:31 UTC完成，两个cohort均通过、model_calls=0；产物SHA为`5fc4d5da949604e937ee1a0dd020e227fa4b4ac7f29c0d5e6571dc25e778989e`。raw正式队列于21:45:36 UTC启动，26项、并发2。首两项DYNAMIC1-01/02 rep1正常完成，实录确认均为gpt-5.6-luna/medium，原始记录完整且无host skill目录注入。后续调查仍按冻结顺序进行，不依据首批报告改候选。
