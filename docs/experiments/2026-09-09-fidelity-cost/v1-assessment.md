# v1 / rep2 事后评审：观察记录，不作公平质量胜负

评审时点：2026-09-09 07:31 UTC。四次运行均已结束；本次只读已存结果、metrics 与冻结原始转录，没有调用模型、执行历史命令或改动冻结池。

结论：工具组在这四个观察值中用时、输入 token 较少，也找到了部分更完整的生成归因；原始组补到了工具组漏掉的 Splash 图片/遮罩和两案的后置构建证据。但 v1 的共同提示词存在实质歧义，Splash raw 主动排除了池内生成根，证据使用范围不一致。不能据此宣布任一组质量获胜，也不能宣称固定成本收益；必须修订共同提示词并重新配对运行。

## 1. 资料与核验口径

实验根目录为 `C:/Users/hongy/projects/_migloop-eval-20260909/v1`，下文简写 `V1`。本报告只取每案每组的 `rep2`：标签 rep2 不等于有两次有效重复，本表每格只有一次观测，不能把 rep1 的试跑混入样本量。

| 案例／组 | 最终回答与原始事件位置 | 用量来源 |
| --- | --- | --- |
| Dice raw | [result.json](C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/raw/rep2/result.json) 的 `response_text`；[events.jsonl:79](C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/raw/rep2/events.jsonl:79) | [metrics.json](C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/raw/rep2/metrics.json) |
| Dice tools | [result.json](C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/tools/rep2/result.json) 的 `response_text`；[events.jsonl:105](C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/tools/rep2/events.jsonl:105) | [metrics.json](C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/runs/tools/rep2/metrics.json) |
| Splash raw | [result.json](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/runs/raw/rep2/result.json) 的 `response_text`；[events.jsonl:93](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/runs/raw/rep2/events.jsonl:93) | [metrics.json](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/runs/raw/rep2/metrics.json) |
| Splash tools | [result.json](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/runs/tools/rep2/result.json) 的 `response_text`；[events.jsonl:186](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/runs/tools/rep2/events.jsonl:186) | [metrics.json](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/runs/tools/rep2/metrics.json) |

四次均记录实际模型 `gpt-5.6-sol`、effort `medium`，冻结工具源码为 `source-1ccefe5`，source digest 为 `5f1d314ea2ff37d5ec7f08a5f7902f997daf6af16f564aaca19d3f0fc8321566`。各自 metrics 的 `integrity_after` 均报告 pool/source/task unchanged，`recording_complete=true`。这些是完整性信息，不是语义正确性认证。

事后参照为 [reference-evidence.json](reference-evidence.json) 和 [说明](reference-evidence.md)，不是旧模型答案或账本标签。此次将全部 58 个定位重新对到 V1 冻结池的 8 份 JSONL：原行 SHA256、解码字段 SHA256、摘录偏移均匹配，0 项失败。另回读了下述构建、主题及资源查询的原始请求/返回。代码修改和成功回执可确认；平台机制、视觉效果和设备回归不因此自动确认。参照包的六 Splash／二 Dice 类别是已核事项集合，不是穷尽金标或根因总数。

## 2. 不能略去的共同任务歧义

[Splash common-task.md:5](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/common-task.md:5) 原句：

> 只读调查，不修改、删除或创建池内文件，不访问池外原工程、其他会话、实验报告或评审证据。

“其他会话”没有明确限定为“池外”。同时列出“当前根转录”，容易被理解成只允许该根及其子树，而不是整个冻结池。

这不是猜测模型的私有思路：Splash raw 的公开进度消息 [events.jsonl:9](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/runs/raw/rep2/events.jsonl:9) 明确说，池中有两份根，但“按约束”只进入 `ff019…`，不读取另一根 `9b310…`。最终回答又把“主动未读”写成“原始迁移生成会话未收入本池”。实际上 [case.json 的 roots](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/case.json) 同时列出：

- `pool/9b3105a2-85ec-4889-9786-b3c220f06754.jsonl` 及其生成/装配子转录。
- `pool/ff019d8a-5172-4cdd-8ce3-77a21682c1b6.jsonl` 及其修复子转录。

tools 回答则实际引用了 `9b310…` 的生成证据。因此，两组虽有相同 pool digest 和 common-task hash，实际遵循的可查范围并不相同。Splash raw 的生成输入缺项不能被当作“原始 JSONL 工具能力差”的公平证据；其“池内不存在”的表述本身也必须纠正。Dice raw 实际进入了多个池内根，进一步显示这条约束并未被一致理解。

## 3. 按真实事项对账，而非按答案分组数计分

下表评价的是结果中是否交代相应事项以及重要归因边界，不是准确率评分。Splash raw 将 BACK 与协议返回复位合并为一组，所以它的“五组”覆盖了参照的六类；tools 的 A–D 只有四类。

| 原始事项 | raw rep2 | tools rep2 | 事后核验与边界 |
| --- | --- | --- | --- |
| Splash：BACK | 找到 `onWillDismiss` 变更与 D-020 注释，但因排除生成根，不能恢复实际生成者输入和移除者 | 区分初版 converter 已拦返回、entry-setup 改外壳、Slice 11 新建 controller 的 `isModal` 假设 | S02–S17、S19–S20 支持这条分阶段时间线。不能把初版说成从未实现，也不能把 D-020 当成全部隐私行为豁免；“finding 证明平台断言为假”仍不是本次独立设备/API 核验 |
| Splash：协议页返回复位 | 找到 L352/353 的重开兜底；不把后来暴露的失败直接归责初版 | B 找到相同变化，并把局部进入点指向 Slice 11 | S21–S22 确认代码增量。tools 的“局部因果已确认”强于证据边界：`onPop` 与平台行为仍需独立核验，双方均未给修后设备结果 |
| Splash：进度条 | 正确识别已有 Progress、补 strokeWidth；称 13dp 真值后来才新增/强化 | C 正确追到生成前 Android 布局 13dp，保留默认 4vp 解释未核的限制 | S03 是初始 converter 实际收到的布局返回；S05 已写 height(13)。raw 的后期来源叙述缺了这条早期正向证据。S19–S20 只确认新增 style，不能确认视觉效果 |
| Splash：系统栏 | 找到隐藏/还原两次修改，生成输入留未知 | D 提出早期主题事实进入主会话但未进入 converter 的上下文路由问题 | S23–S26 确认修改。额外回核：9b 根 L402 请求、L404 返回已有 windowFullscreen=true；L1915 派单写通用沉浸式，未写专属隐藏/还原。该发现支持继续检查上下文传递，但“全部可能输入均无此要求”不是由一份派单即可认证 |
| Splash：遮罩 | 找到共享常量、批处理目标一处及后续读回 | 未作为事项交代 | S29–S31：fixer L103/104 实际目标含完整 Splash 路径；L106/107 读回 maskColor。S32 的常量 Edit 在 `DesignTokens.ets`，不能冒充 Splash 版本 |
| Splash：图片尺寸 | 找到批量脚本为 app-name 图片补 185×125，并区分它不是独立 Splash finding | 未作为事项交代 | S27–S28：fixer L233/234 对完整目标成功修改。额外读回 L198/199 确有 `mipmap-xxhdpi 555 375`，L201/202 的该资源 XML 摘录只回显 src；这不单独证明源布局最终显示尺寸或修后对齐 |
| Dice：UI 测试桥 | 找到后续 UI-T 设计、三次 Edit，未倒算成原始转换漏项 | A 同样区分后续模板/设计输入，注明首次观测、零命中的限制 | D08–D17 支持后续测试基础设施增量。两组重要归因均有依据；不存在更早义务仍不能靠搜索零命中证明 |
| Dice：异常观察者 | 找到 ECAT 后续派单、三次 Edit、后置构建与警告；未归为 Android 对等遗漏 | B 同样区分后续平台要求并引用 SDK 返回，但遗漏后置构建 | D18–D26 支持任务、SDK 返回与代码变化；SDK 有接口不证明原始转换时已有普遍强制义务。不能由后续 work-list 自动判初始作者失职 |

生成侧 BACK 的关键原始定位在 `V1/splash/pool/9b310…/subagents/`：conv-splash L9、L26、L71/72；entry-setup L123/124；slice11 L1、L12、L22、L236/237、L250，完整文件名与调用 ID 见参照包 S02–S17。主会话早期主题返回见 [9b 根 L404](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/pool/9b3105a2-85ec-4889-9786-b3c220f06754.jsonl:404)；设计文档分片 L175 已写 windowFullscreen，L188/189 为合并及成功返回，位于 `agent-aref-doc-analyzer-d4e8fbf7e1d0dbac.jsonl`。这些早于 07-24 的页面首次生成。

## 4. 验证状态：双方都不能用写入成功替代运行正确

tools 两案都在后置验证方面留有可查缺项，不能把“调查未读到”写成“整个池没有”：

- Dice 异常观察者修改后，`V1/dice-entry/pool/2f01bcdc…/subagents/agent-a635575c78cd15ff6.jsonl` [L48](C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/pool/2f01bcdc-0a92-4961-a64d-5b181f03b3d3/subagents/agent-a635575c78cd15ff6.jsonl:48) 返回 `BUILD_EXIT_CODE=0`、0 ERROR；L52 回显 EntryAbility:140:5 的 may-throw 警告。raw 引用了它；tools 最后一句“v10 尚无后置编译”不适合作为全池结论。构建并不证明异常回调真实触发或日志可回收。
- Dice 测试桥的后续 UI 跑测，[agent-a52d61ac7ab7033ba.jsonl:L300](C:/Users/hongy/projects/_migloop-eval-20260909/v1/dice-entry/pool/81e0a463-c9d3-4a7a-a671-b7f064830af1/subagents/agent-a52d61ac7ab7033ba.jsonl:300) 同时有 BUILD SUCCESSFUL、`TestFinished-ResultCode: -1`、`App died`。raw 有交代；这支持“端到端未通过”，不单独定位是桥代码还是环境。
- Splash 后置 builder [agent-af0e3d2ae54dbf769.jsonl:L37](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/pool/ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-af0e3d2ae54dbf769.jsonl:37) 直接返回 `EXIT=0`、BUILD SUCCESSFUL。raw 已发现后置构建；tools 的整体说明漏了该证据。raw 引用的 L51/52 检查命令整体其实 `is_error=true`，原因包括临时文件已不存在，不能把它描述为一次全命令成功；编译成功应以 L37 为直接依据。

两组均未给出上述修复后的独立设备行为闭环。本次也未重跑设备。尤其“isModal 吞 BACK”“普通 pop 的回调行为”“默认笔画 4vp”“alpha 视觉等效”等主张，应区分历史作者解释、历史 finding 自述和独立复验。

结构结果另列，不混成质量分：Dice tools 的 `verdict_ok=true` 只代表既有结构校验通过；Splash tools 因 `notes` 写成列表而非字符串，`verdict_ok=false`。其已存 [check.json](C:/Users/hongy/projects/_migloop-eval-20260909/v1/splash/runs/tools/rep2/check.json) 没有产出绑定的结构化缺陷图，不能悄悄修正该历史产物再报通过。raw 不要求该 schema，`verdict_ok=null` 不是质量失败。

## 5. 用量与耗时：只报告观察值

数据均直接取对应 metrics 的 `usage` 和 `wall_s`，墙钟秒保留一位小数。cached 已包含在 input_total 内，不能相加；uncached = input_total − cache_read。output 也已包含报告的 reasoning output，不再次加 thinking。

| 案例／组 | wall_s | input_total | 其中 cache_read | input_uncached | output |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dice raw | 917.5 | 4,101,829 | 3,914,240 | 187,589 | 23,345 |
| Dice tools | 456.5 | 3,080,801 | 2,916,096 | 164,705 | 10,886 |
| Splash raw | 935.8 | 5,429,981 | 5,039,360 | 390,621 | 24,182 |
| Splash tools | 779.3 | 4,006,167 | 3,806,208 | 199,959 | 19,748 |

本次 tools 相对 raw 的观察差值：Dice wall_s 少 50.25%、input_total 少 24.89%、uncached 少 12.20%；Splash 分别少 16.73%、26.22%、48.81%。不能由每格一次、实际调查范围不同、未控制缓存/并发条件的运行推出稳定收益，更不能称“以更少成本达到同等质量”。四次 `cost_usd_total=null`，没有实际美元支出数据；配置中的 `$5`、45 turns 在该后端分别记录 `dollar_limit_enforced=false`、`turn_limit_enforced=false`，不能当成真正执行的等额预算。

字符量也必须保留来源口径：

| 案例／组 | native 调用数 | native 返回字符 | rollout wrapper 数／字符 | 异常记录 |
| --- | ---: | ---: | ---: | --- |
| Dice raw | 36 个 command_execution | 1,029,097 | 36／441,827 | native failed=0 |
| Dice tools | 49 个 MCP leaf | 170,310 | 31／341,221 | rejected=0，failed=0 |
| Splash raw | 43 个 command_execution | 2,301,289 | 43／497,696 | native failed=6 |
| Splash tools | 89 个 MCP leaf | 388,639 | 38／372,557 | rejected=1，failed=0 |

取自 `metrics.native_events` 与 `metrics.transcript`。raw 的 rollout `tool_calls=0` 只是该字段未把 wrapper 当 leaf，不能报告“raw 没调用工具”。native 聚合输出与模型所见 wrapper 文本有截断/包装差别，不是统一的模型可见字符量；wrapper 与 leaf 不能直接相加，也不能拿这些字符数充当 token 或费用。tools 两案完全相同重复调用计数均为 0，但这不认证没有语义上重复的导航/展开。

## 6. 新覆盖量尺及下一次公平比较

当前工作区新增的机械量尺把 Splash 列为 **9 个记录版本（v52–v60）＋15 个候选待核＝24 个需交代项**。这是 v1 结束后的量尺，不是当时模型已被要求完成的表，也不等于 24 个修复、24 个缺陷或 24 个语义 hunk。

这 15 个候选中既有原始材料已核回的遮罩 L103 与图片 L233，也有仍未核的扫描、条件读、报告命令等。当前保守规则暂不新增摘要推断式只读排除。候选只说明精确目标与事件有待交代的关系，不确认作者或修复事实；同一事件按稳定 event_id＋完整目标去重，且不新增正式版本。遮罩为 `candidate:240cbc9029eac419ffac`，图片为 `candidate:c16793c7c964a604c1ca`。它们不是 v52/v53：当前那两版来自 L346 的关闭行为修订。

联合 coverage 只填 9 个版本会缺 15 个候选；但把全部填为 unresolved 也能“机械交代完成”，不代表调查解释正确、问题解决或验收通过。原始六事项核验与版本/候选结构对账应并列保留，不能相互替代，更不能从 A 的 v51→v54 区间或散文引用自动补出遗漏事项。

下一次运行前至少做到：

1. 共同提示词明确：“允许读取冻结池内全部根转录及其子转录，包括列出的历史会话；当前根仅用于定位，不限制历史调查范围。禁止访问池外会话、池外原工程和任何实验/评审报告。”两组收到同一份完整根清单。
2. 冻结新的 prompt、源码、pool digest 与判据；重新运行双方，旧 rep2 原样保留并标注本报告的公平性缺陷。不能仅给 raw 补一段说明后续跑，或让任一组接触本事后证据包。
3. 预先分开“事项交代”“归因有据”“结构可解析”“构建”“设备验证”和用量；若引入 coverage，向两组明确相同调查范围与交代要求，不用 tools 私有可见的分母事后给 raw 扣分。增加独立重复后再讨论稳定性。

结果文件 SHA256（防止后续把新跑结果混回 v1）：

- Dice raw：`9106114382248e530cc5f87ed106a2710f8c57e354fb966594067da2fb1152f6`
- Dice tools：`c87e456221fc1e71ec8de4715148a0574ad7b7d446b068642010d9c16979a5ba`
- Splash raw：`87b862fe56635aae0e5f0beaa911f4b70fee7ef9c4ef5b4976cc71266310d912`
- Splash tools：`dee57ebf57b0073815b9236f13a4b198eb20d7a1f7bfdea3d0179c8d12225453`
