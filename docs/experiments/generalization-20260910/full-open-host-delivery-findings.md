# Full-open 开发轮：原生返回与模型可见输出分层

2026-09-11，运行 `development-full-open-v1`；不是全轮胜负报告。

## 已复核的交付事实

首批 dynamic1 六文件 rep1 均已完成。只读 `audit_host_delivery.py` 检查冻结转录，产物在 GEN 下 `delivery-audits-full-open-v1/`，每份绑定完整转录SHA。它不建账、不调用模型、不改原记录，不按相邻事件/相似参数推断父子。

| 文件 | 模型输出记录数 | 带显式外层截断警告 |
| --- | ---: | ---: |
| DYNAMIC1-01 | 10 | 3 |
| DYNAMIC1-02 | 9 | 4 |
| DYNAMIC1-03 | 12 | 6 |
| DYNAMIC1-04 | 7 | 4 |
| DYNAMIC1-05 | 10 | 4 |
| DYNAMIC1-06 | 10 | 4 |

上述输出记录包括外层执行器/工具发现等，不等于MCP调用数、已读证据数或错误归因数。没有截断警告不认证全文送达；有警告也不自动证明某条具体遗漏由截断造成。

D01 的具体反例：`transcript.jsonl` L27是外层exec请求，L29是内部McpToolCall完成事件，L30才是绑定外层call_id的模型输入输出块。L29保存完整服务端batch返回，L30带 `Warning: truncated output (original token count: 221603)`，而原 `query-trace.json` step6为 `recorded_response`。221603是外层报告的裁切前token数，不是本次模型计费输入token。

`probe._transcript_calls` 为runtime item记录完整开始/完成时刻与服务端返回；`_deduplicate_runtime_calls` 没有同id的模型调用可合并时保留独立runtime项。这能证明调用确实执行，不能证明外层exec完整转交。`investigation.project_trace` 原先没有把这两层的交付边界展示出来。

## 下一候选的审计修正

不是删除runtime调用，也不是假装模型没查过，而是新增共同 `delivery_boundary`：

- runtime/exec事件摘要：服务端返回可记，模型可见为未知（不是“确定没看见”）；保留查询及回执。
- 有原生use/result配对的模型输出记录：单列已记录。仍不宣称全文、理解或采纳，截断状态独立。
- 老记录/缺provenance：未知，不默认全量交付。
- batch子项继承父返回边界；UI显示中文标记和来源定位，不产生外层/内层连边，也不把查阅顺序变成历史读写边。

运行中使用的candidate、run package、GUIDE和参考均未改。修正只在工作树/后续提交，旧实验产物不重写。对后续UI载入旧run可重新投影，但这不改变当时实际调查或评分。

合成验证58项通过：包括实际原生转录解析→合法内部receipt→时间trace、标量/批量共同边界、无父子id链接不猜、实际模板函数执行的父子继承/旧记录未知。不是全仓重跑或生产浏览器截图验收；原实验仍继续。

GitNexus无migloop索引，按调试技能回退到源码和定点原记录。OpenAI Docs确认历史中单条工具输出有独立的 `tool_output_token_limit` 配置，但文档不足以证明当前外层exec警告仅由该设置造成，本轮不改配置或对照条件。[官方配置说明](https://learn.chatgpt.com/docs/config-file/config-reference)

## 语义裁决进度与边界

已正式落盘并通过固定评分器原文/身份核验的三份：D01 rep1 两个P，D02 rep1 一个W且major1，D05 rep1 一个C且major0。不是完整队列分数，不按这三份推断全轮准确率。

- D01：两个修改近因正确，但仍否认已有生成前布局/资源读取证据；又把G201的尺寸Edit误指给G198初Write。深层未知不扣分，但unknown标签不能豁免错误的历史证据断言。
- D02：root343/344在09:44已读ResponseInterceptor，407/408在09:47才写HttpCore；427/428是09:48的规格Read。报告以规格较晚读取支持未获Android输入的中心原因，责任边界错。不是引用位置对就算归因对。
- D05：实际恢复了DAO输入→共享分支误加DESC→只移除收藏排序的链，不把无ORDERBY认证成必然ASC。

独立Luna初审也犯错：D02曾倒置Read/Write，D01漏审unknown中的否定断言。root核原时刻后裁决，没有采纳其初始全C建议；D05初稿还含两段非逐字摘录，被机械检查拒绝后修正。这说明评分不能只相信另一代理。评分标准和gold未因这些报告修改。

D03/D06初读能看到派工/输入证据改善，arch11仍有把后来接线写回初生成者的风险，待完整原文裁决；不提前给分或宣布胜出。后续应单独检验外层转交方式、索引噪声/分页与提前停止，不把组合候选的变化归功于某个单项。
