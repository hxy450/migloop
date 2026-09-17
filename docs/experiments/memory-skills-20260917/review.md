# 单问题制卡实跑审查

任务：0723 已拆出的“会员中心价格数值与后缀样式不一致”。只评这个任务，不评整页全部修复，也不换算为整体准确率。

## 第一轮：v1

独立 Sol/high，零父上下文；实际模型与 effort 由原生 transcript 确认。397.06 秒，两稿。输入累计 2,852,213 tokens，其中缓存 2,672,384、未缓存 179,829；输出 17,612（含平台已计入的 reasoning，不重复加）。不是单次上下文大小。

机械结果：首稿 `needs_revision / needs_path`，终稿 `valid / complete / ready_for_review`。它去掉了没有正确声明历史关系的发现/协调分支，换成可定位的中间文件读取及编译修复，形成可加载图。

语义结果：**未通过归因审查**。终稿仍把 `stripCurrency` 接入后的价格串行为说成最初 aconv-member 的输出，遗漏生成期 aslice8-pay 获得完整动态源码之后的接线写入。另一个已单列的 helper 可见性问题也被带入本卡的独立原因与建议。

### 独立核对的原始位置

| 原始转录位置 | 可观察事实 | 审查用途 |
| --- | --- | --- |
| `9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aconv-member-08b3dcf6deb3c515.jsonl:L20–21` | 读取商品项 XML：基础价格控件 16dp、滚动数字控件 30dp | XML 不足以独立确定非滚动分支的字符串及局部样式语义 |
| 同转录 `L61–62` | 写入 UI 骨架，`priceText` 注释为数字，`productData` 尚待后续填充；没有后来 `stripCurrency(product.showNowPrice)` 的赋值 | 不能把后期接线行为回填给这次写入 |
| `9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aslice8-pay-80bbb1f44b77da0f.jsonl:L24` | 实际收到 Activity 源码；非滚动分支为 `showNowPrice.replaceSpan(Regex("\\d+"))` 和 `AbsoluteSizeSpan(30, true)` | 这是生成期间实际收到的动态语义，不是修复期才出现的要求 |
| 同转录 `L75–76` | 读取已有 MemberCenterPage | 早期骨架到后期接线存在真实交接 |
| 同转录 `L264` | 写入 `stripCurrency(product.showNowPrice)`，普通价格串与动画数字共用整个 30vp Text | 已确认此写入在相关源语义已交付后仍偏离；应进入原因链 |

这些事实不证明初始转换者完全没有职责遗漏；它们直接否定“把后期具体实现当作首次写入内容”的表述，也提供一个实际输入足够却输出偏离的生成期节点。此核对没有反馈给运行中的模型。

### 为什么机械通过仍不足

校验器确认了 aconv-member 确实写过目标、输入文件确实读过。它没有证明那个时刻的输出已包含 summary 所称的业务赋值，也不证明源码入口等于充分语义输入。不能把 `valid` 当作内容归因正确。

## 后续处理

保留 v1 全部材料。只修改制卡 skill 的通用取证步骤：先对账生成期相关写入，核对所归责行为是否出现在当次输出，区分“指向源码的入口”和“实际收到的内容”，不将另一已拆任务混作当前根因。没有加入本题作者、字段名、答案或参考评分。v2 在全新 Sol 会话重跑同一任务，运行配置不变。

本次只检查制卡流程、历史事实与链路展示契约；未检验经验归并、召回率或下一次迁移收益。

## 第二轮：v2

同一原始问题、新建 Sol/high 会话，不继承 v1，也未收到上面核对的答案。原生转录再次确认模型与 effort；host skill catalog 未注入，完整 UTF-8 skill 与制卡约定出现在工具返回中。两轮运行后的原始材料、任务、skill 与内核快照 hash 均未改变。

461.77 秒（7 分 42 秒），两稿。累计输入 2,359,831 tokens，缓存 2,167,424，未缓存 192,407；输出 20,537。总输入变少，但未缓存输入、输出和时间均未下降，不能据此宣传提效。

| 检查项 | 结果 |
| --- | --- |
| 正确输入与偏差环节 | 核心通过：定位到 aslice8-pay 在读取 Activity 动态语义之后，仍把带后缀的价格串放入统一 30vp Text；与 L24、L264–265 对得上 |
| 最终修复 | 描述普通价格 30/16vp 分段及后续保留状态，有脚本正文和回执支持 |
| 图校验 | 首稿 needs_revision/needs_path，终稿 valid/complete/ready_for_review |
| force 流程 | 初稿无 force；收到未解析写边反馈后，以 fixer L592–593 的真实脚本和回执补一条 model_review 虚线边 |
| 正常输入可视化 | 未完全满足：输入依据在 summary/reason 中，没有单独声明关键输入文件节点 |
| 单问题边界 | 未完全满足：仍把另列的 helper 可见性问题放进同卡的 problem 节点和建议 |
| 树的连通与内容传播 | 写关系已核实；输入充分性、错误内容在后续保留仍由调查语义支持，不因图 valid 自动认证 |

v2 没有再把后期 `stripCurrency` 接线说成 aconv-member 最初输出。生成期局部归因改善是这一次可观察的结果，但这不是排除模型随机性的消融证据。两次运行都保留失败/不足，未手工替模型改稿后算成功。

### 原稿和卡片

基目录：`C:/Users/hongy/projects/_migloop-four-skills-trial-20260917/sol-0723-price-v2/`。

- `workspace/draft-1.yaml`、`workspace/draft-2.yaml`：模型填写的两稿。
- `workspace/case-1.json`、`workspace/case-2.json`：自动补充元数据和原始校验回执的卡片。
- `workspace/case-2.views/target-1.json`：旧 inquiry 单目标展示契约的视图；本轮未另启动网页或改 UI。
- `run/prompt.md`、`run/command.json`、`run/transcript.jsonl`、`run/metrics.json`：实际输入、配置、完整过程与用量。
- 最终 report ID：`9881ccc6a89c40ba`，只对应此冻结数据库，不是线上服务器 ID。

下一步只针对未完成项收紧交付检查：让可确认的关键输入落为节点，并避免把已拆到其他任务的问题再次当成本任务根因。无需增加一堆模型必填字段或重新改内核。
