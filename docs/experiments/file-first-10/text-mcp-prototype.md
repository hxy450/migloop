# MCP 文本呈现离线原型（2026-09-10）

结论：同一份真实 Dice 批量结果，无损共享重复值后，当前 JSON 正文加回执的 **83,219 字符**变成文本加实验回执的 **35,580 字符，减少 57.25%**。这是传输表示的收益，不是新增证据、token 节省或调查准确率提升。原结果仍然是 **4 ok / 20 deferred**。完整选中数据无损编码后仍有 131,817 字符，不能承诺 30,000 字符装下全部 24 项。

暂不建议据此切换生产格式。可以保留这个离线基线，后续若决定接入，先验证新格式在真实记录器、scope/引用认证和单页阅读中的兼容性。当前没有改 UI、JSON 查询内核、生产回执、冻结代码、模型报告或评分合同，也没有调用模型。

## 数据与复现边界

- 原请求：`tools-v2/runs/F10-03/rep1/query-trace.json` 的 step 16，24 个 `changes`，offset 0–23，limit 1，max_chars 30000；原请求逐字保存。
- 只读重放一次，2026-09-10T15:47:06.604262+00:00 开始，49.781 秒，注册来源 80 个。没有执行转录中的历史命令。
- 源码包前后 SHA-256 相同：`903ad2c9de0b99100ca8213b508a0ac2c091654d16e41d9cccdd7fa0fc2e4610`。清单覆盖当前 `src/migloop` 全部文件，排除解释器缓存；不是只检查几个被 import 的模块。
- 输入 trace SHA-256：`248c3398a65443c9187635c3f5c7ef123732599f04809c1aeb99261e8438eed5`。
- 完整原始 capture 保存在本地 EVAL 的 `tools-v3-text-prototype-20260910-1/`：`selected.json` 为真实 `batch` 中每个 query 在预算投影前的结果；`projected.json` 为同次 batch 的最终结果。临时 wrapper 只深复制 query 返回值，随后恢复函数，不改变结果。
- 本文以 `render-3/measurements.json` 为最终数字。早期根目录 / `render-2` 的文本文件保留，不能混用其数字；没有再次冷重放。render-3 脚本 SHA-256：`cbeb0b5b3c0a5b9382a53378a92b7ac8326bb50bd4533bb2d6787cc7a5209138`。

现有 `tools-v3-delivery-audit/*.json` 只有每项大小/状态等摘要，不能用于同事实文本压缩比较；本次另存完整数据解决了这一限制。原始历史材料只落本地 EVAL，没有复制整份转录进 repo 文档。

## 最小呈现合同

原型使用可读 YAML 文本和标准本地 anchor/alias，不是自然语言摘要。只把**完全相等**的容器、长字符串和 raw refs 在本条返回中定义一次，保留所有键、标量、列表顺序、原文预览、范围、未知项、gaps、计数、完成标记、分页和展开参数。没有默认值省略、状态升级、事实推断、跨窗口合并或跨响应别名。

范围、raw refs、pointers 的目录在正文里完整给出；`*scope_2` 或 `*raw_6` 的定义均在同一条返回内，不需要新 MCP 调用才能解码。不同 since_ts、缺少 id 的范围和 independent_antecedent 范围不会被合并为同一个值。数组顺序保持不变；对象键顺序不承担事实语义。

四组输出均经过 `safe_load(text).data` 与输入 JSON 树的严格规范化相等校验，canonical SHA 也相同。因此这里的大小变化不是通过把相关余项移出首屏、只留查询入口、删除 false/null 或把 unknown 改成已确认实现的。既有 JSON 中重复的 delivery 描述也保留在树中。

最小生产兼容方向（尚未实施）：查询内核继续返回 JSON 对象；MCP 增加明确版本的文本 renderer；记录器按新 marker 独立解析、验哈希、还原同一 JSON 树，再复用现有 trace/UI 数据路径。旧 renderer 和旧 parser 保留。不能把旧 `parse_receipt` 的 `json.loads(body)` 悄悄改成容错文本解析，也不能给新文本套旧 schema 让它冒充旧认证。

## 同数据大小对照

单位为 Python Unicode 字符数；不是 token。各行都是该行同一个输入树，不能跨行把交付覆盖差异当压缩收益。

| 输入树 | compact JSON 正文 | 文本正文 | 新 marker + receipt | 文本合计 | 相对 JSON 正文减少 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 完整选中 24 项（投影前） | 1,258,205 | 129,459 | 2,358 | 131,817 | 89.52% |
| 预算后完整 batch（4 ok / 20 deferred） | 82,913 | 35,015 | 565 | 35,580 | 57.09% |
| 选中 offset 0 的单页 data | 52,389 | 41,420 | 1,181 | 42,601 | 18.68% |
| 首个已交付页 data，offset 20 | 7,253 | 6,264 | 363 | 6,627 | 8.63% |

预算后现 renderer 的完整 wire（正文及原 marker/receipt）是 **83,219 字符 / 87,866 UTF-8 bytes**；文本完整 wire 是 **35,580 字符 / 36,723 bytes**。这里“完整 wire”指工具文本字符串，不包括外层 MCP JSON 协议帧。现 renderer 输出通过同一已保存树离线按现算法复现，不冒充新增真实 MCP 返回。

原预算只计 data，实际 data_chars 是 28,960；完整 JSON 返回含封装是 83,219。不能拿文本完整 wire 的 35,580 直接和旧 data-only 的 30,000 比较后宣称预算违约。完整选中树的 131,817 则明确表明：只换无损 renderer 也不能让全部选中内容挤进 30,000 字符。

单页收益明显小于跨项收益；24 次查询重复相关清单、范围、查询结构和通用边界声明，是这次批量去重收益的大头。这一个 Dice 请求不能代表全实验、所有查询类型或人/模型认知收益。另一个 JSON 按需折叠方案若移走部分首屏字段、让后续查询恢复，就不是此处的同树无损比较。

## 真实示例的存放位置

完整例子在本地 EVAL 的 `render-3/projected.first-page.readable.txt`。仓库文档不嵌入历史原文、精确 raw refs 或作者定位，避免将评测调查材料变成可被重新使用的答案提示；正文和定位仍完整保留于 EVAL，不在 runtime code 包或模型任务 prompt 中。

例子展示同页 scope/ref 定义与复用，并保留原始 pointer。某请求预览的表示总长为 401，实际交付 240 字符；回执记录 240，**不把来源总长当实际读到的长度**。完整原文仍须使用例子中的原有 expand 查询。

## 实验回执与验证

新的 `MIGLOOP_TEXT_PROTOTYPE_RECEIPT` 只附紧凑 JSON，不再附整份原 JSON。它包含 renderer schema、ledger、实际 UTF-8 文本 SHA-256、规范请求 SHA-256、实际出现的 scope 索引及材料位置元组。索引指向本条正文内的完整目录。

材料元组列在正文内定义：`[scope_index, ref_index, pointer_index, extent_index, offset, chars, next_offset, occurrences]`。完整 projected 树有 8 个材料条目 / 8 次出现，与现 JSON delivery 的条目数一致；完整 selected 树是 76 个不同条目 / 812 次出现。812 是重复文字出现次数，**不是 812 次独立读取**，也不是 812 个独立证据。目录/导航目标本身不算读到内容。

只遍历已知材料容器与实际 `text/preview/diff`；不把 query、continuation、body_sources 目录、delivery 描述当读取。前置请求的 `independent_antecedent` 使用它自己的明确 scope。decoded 原文预览有独立 extent，offset 使用 preview_start，不冒充原始 JSON 字节偏移或完整字段。正文哈希绑定实际全部文字；材料清单从解码后的正文重新计算并核对。

这只是离线验证器，不是签名或来源认证：能生成另一份正文的人也能重算普通 hash。生产仍需记录器核真实 call/result、ledger 身份、请求、时间和响应来源。单页 data 的大小试验没有完整 batch ledger，因此其 receipt.ledger 为 null；它不是可认证的独立 MCP 结果。

9 项内置构造检查覆盖无损还原、null/false/日期样式字符串/Unicode/多行原文、未知/gaps、前置范围、preview 起点与 extent、导航不计读取、重复出现计数，以及正文/请求/材料长度篡改拒绝。真实四组输入另做完整树相等检查。本次没有重新执行每个分页入口；只证明参数结构原样保留，不替查询内核承诺这些入口在任何状态下一定可执行。

## 接入风险与建议

- **认知收益尚未测**：锚点虽在本地可解，也要求读者回看定义。无损 YAML 是减少重复的保守基线，不等于优秀的自然语言事实卡片；不要把字符减少直接说成人/模型更容易判断。
- **重复文字不一定宜共享**：当前完全相等的事件容器、空列表也共享。数学上无损，但 `gaps: *shared_8` 可能比 `gaps: []` 难读。若后续按可读性保留短值/少量局部重复，应重新报实际 wire 大小。
- **旧消费者不能直接接**：生产 parser、trace 记录器、UI 还原、离线报告认证需版本化。只改工具 stdout 会令现有真实交付记录失效。
- **安全解析未产品化**：SafeLoader 禁止任意对象，但生产还需输入大小、深度、alias 展开数量/循环、重复 key、JSON 类型约束与内存上界；普通 hash 不抵御伪造响应。
- **预算不能截断文本**：不得用字符串裁切留下缺失锚点或一半原文/receipt。未来如接入，仍须在事实树层预算选择，再原子渲染可解析正文，并按真实文本分别核 data 与 envelope 的成本。
- **没有自动事实升级**：原 candidate/unknown/call_return/effect_certified、来源覆盖、gaps 和因果未检查标记全部不变。显示层节省不能证明查询内核或历史判断正确。

建议先保留此原型，不重跑 20 次模型，也不直接接生产。若下一步获准实施，可在新的显式 renderer 版本做少量无模型兼容测试；是否改成更易读的事实卡片和怎样处理通用说明，是另一个需要独立定义语义等价与预算合同的设计决定。

脚本：`capture_text_delivery.py`（一次重放、独占新输出目录）与 `text_mcp_prototype.py`（纯离线 renderer/validator）。重用已保存 capture 做下一版比较只需运行后者并指定新的 `--out`，无需再建账或访问历史池。
