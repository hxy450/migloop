# 完整附件与显式源合同：独立审阅收口

此审阅覆盖post-v4工作树的发现、source metadata、原始地址、时间策略、缓存和真实查询/回执消费者。不读新gold、不执行历史命令、不启动模型；不修改旧冻结产物或旧分数。当前已测范围未发现未修复的实质地址/时间/作者升级漏洞；不等于无界安全证明或真实源注册门已经完成。

## 附件发现的最终边界

`cc_sources.all_source_paths(root)`返回根JSONL本身，然后是`<root-stem>`目录树内全部普通文件，排序稳定；不只看`subagents/*.jsonl`，也不只看扩展名。符号链接/reparse点显式拒绝，不执行附件。`subagent_paths`仅是兼容JSONL子集包装；`discover`与主代理的pool_key各自使用完整源函数，不在一次collector内部再独立扫描子集合。

actor仍仅来自根及subagents树内按既定原生envelope/旧直接子目录兼容规则确定的转录。其余文件全部进`auxiliary_sources`；未知JSONL、workflow JSON、meta、日志文本、脚本和binary都不由目录或内容意图获得actor。只有actor转录参加脚本预扫描与实际walk，两者共用同一次发现快照。

真实dynamic1仅做文件名/字段形态的发现回核，得到全部169文件：

| 分类 | 数量 | 时间策略 |
| --- | ---: | --- |
| actor转录（1根+70子） | 71 | `record` |
| workflow journal JSONL | 7 | `unknown` |
| JSON附件（含meta/workflow） | 77 | `unknown` |
| 文本附件 | 10 | `unknown` |
| JS附件 | 4 | `unknown` |

即71 actor源+98辅助源，169份source metadata，169个唯一logical_name。这里的169是实际文件发现计数；端到端真实原始registry及展开门由主代理另核，不能拿本计数冒充已完成的原文交付。

## 显式合同及已修反例

`CCSourceSet.source_metadata`和`Ledger.source_metadata`以规范化物理路径为本机查找键；值只含`logical_name`、`timestamp_policy`，不含语义答案。根逻辑名为root JSONL basename；附件逻辑名为`rootName.jsonl/<相对root-stem路径>`。`build_ledger`在identity冻结前复制/校验合同并纳入摘要，辅助源内容及source_stats也纳入；不靠basename相同或内容相同合并journal。

审阅期间发现并反馈的两类实质边界已由主代理改为显式合同解决：

1. 用绝对路径中第一个/最后一个`subagents`猜namespace，不能保证任意冻结目录搬迁稳定。特别是pool的父目录也叫`subagents`时会把主机前缀纳入身份。最终不再猜路径：只有显式logical_name生成40hex键，无合同的standalone读取仍用旧20hex basename键。新增反例已核：搬到`unrelated-parent/subagents/frozen`后ref和ledger identity均不变。
2. 附件JSON/JSONL自带`timestamp`不代表到达时间。最终全部aux为`unknown`，store扫描/单行读取、native索引和latest均应用合同；latest及全局/请求级native cache把合同也纳入键。伪2099时间戳不会推进latest；只改变policy而不改文件字节/mtime/owner也会失效。

旧20hex引用仍由完整registry检查basename唯一性；歧义拒绝，不由内容摘要猜源。`resolve`保留调用者原ref而不悄悄升级，新40hex引用按明确合同寻址。同名journal各有独立地址，旧歧义引用不被“修好”为任意一个。

辅助原文中即使原样包含`tool_use`、成功`tool_result`或`patch_apply_end`，unknown策略下也仅是可展开raw内容，不进入真实native事件，不造作者、版本或读写关系。binary保持注册，解码失败给出明确gap；不静默排除，也不伪造可读正文。

## 独立真实消费者回归

新增`tests/test_source_contract_review.py`使用合成证据通过实际查询/渲染/receipt函数，而非仅比较返回shape。覆盖：

- 旧20/新40的record结果、scalar time receipt、batch receipt均保留所供ref及精确物理行。
- 字段expand保留原ref、实际字段文本、unknown时刻；陈旧内容对两版引用均拒绝。
- 旧action引用能导航到其请求/返回两个明确40hex原文引用，不靠猜basename或只按seq。
- 附件中的原生样例envelope只留下无owner、无时间、无annotation的原文；无events、无file stories。
- 全局及request-local native cache对policy和logical_name变化失效；latest cache对policy变化失效。
- 源合同在identity冻结前复制，调用方后续改自己的metadata对象不污染账本。

新增`tests/test_cc_source_attachments.py`覆盖完整附件发现、JSON/TXT/JS逐物理行检索及展开、binary gap、附件不进入actor预扫、以及追加/新增/删除附件使warm service ledger失效。附件扩展先有8项有效红测，后经发现与主代理合同集成转绿。

最后联合回归：**351 passed，6 skipped**，约5.22秒。包括新source review/附件/发现、主代理nested addresses/cache/aux views，以及raw events、request scan reuse、temporal、atom overview、investigation、time input delivery、batch receipts、atoms和collection uncertainty。6个skip均因Windows无法创建真实符号链接；reparse位拒绝断言通过，未将skip算成实机链接验收。

本轮新测试在此前全套pytest collection之后新增，因此单独报告，不冒充早先全套结果。输出目录为`EVAL/../source-contract-final-02`（完整路径在配套JSON）。当前关键运行时文件SHA256与测试计数见[source-contract-review-runtime.json](source-contract-review-runtime.json)，便于主代理最终freeze对账。

## 限制与交接

- 路径边界检查不是对恶意并发替换文件系统的安全沙箱；正式实验仍需稳定完整源快照。
- 对非JSONL附件提供的是物理行raw证据，不是把整份多行JSON自动解释为有时序的事件。`unknown`是明确证据边界，不因成功文本或时间字段自动解除。
- 真实169文件可发现不等于已认证其脚本效果、读者、后置修改原因或gold完整性。
- 此修复与tools-v4分开登记，必须另冻结新candidate后才能开始留出调查。旧报告、gold与分数均未修改。
- 本子任务负责的运行时代码及测试已停止编辑，交主代理完成全套回归、真实全附件registry/展开门和正式冻结。
