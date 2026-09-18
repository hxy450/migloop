# 0723 单问题、多目标制卡：运行前人工预分析

本轮仅检查历史材料、确定下一次制卡试验的对象；没有启动 Luna/Sol，没有修改内核、UI 或 skill。此文是审查员底稿，不交给后续调查模型，不预填其结论。

## 范围

来源：`C:/Users/hongy/projects/_migloop-repair-triage-trial-20260916/sol-0723-minimal-v1/repair-tasks.yaml`。

材料池：`C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/member-center/pool`。

沿用该拆分任务的生成结束 `2026-07-24T22:15:00.897Z`、观察结束 `2026-07-26T21:48:57.793Z`。不是 i14 的整会员页六项任务，也不采用那次整文件评分分母。

下文 G 表示生成会话 `9b3105a2-85ec-4889-9786-b3c220f06754`，R 表示后续会话 `ff019d8a-5172-4cdd-8ce3-77a21682c1b6`。子转录均在相应会话的 `subagents/` 下。行号是 JSONL 物理行号。

| 任务 | 清单目标数 | 当前确认 |
| --- | ---: | --- |
| 第3项：图片固有尺寸／比例 | 19个文件 | 原生 Edit 与多个 Bash/Python 批次混合；内部包含不同布局偏差 |
| 第6项：普通／loading 弹窗遮罩 | 25个文件 | 24个控制器所在文件，另加公共 DesignTokens；脚本回执为51处插入 |

目标数不是根因数，也不是全部文件都应标红。25个遮罩目标包含新增公共常量的辅助文件，不能认定 DesignTokens 的原作者制造了全部遮罩问题。

## 一、图片任务可作一张问题卡，但不是一个统一原因

已打开 R 的 `agent-a68daf720e780b4c2.jsonl` 中真实修改及紧随回执：L130/131、152/153、168/169、192/193、211/212、216/217、228/229、233/234。没有执行这些历史脚本。

实际修改至少包括：

| 分支 | 举例 | 修复内容 |
| --- | --- | --- |
| 未指定固有宽高 | Mine、ManageRenew 的图标／插画 | 增加资源尺寸对应的 width/height；不同资源目录有不同倍率 |
| 只有一条轴的约束 | GuideInit、HomeTab、MemberCenter 等 | 增加 aspectRatio 或另一轴的高度 |
| 内容框与 padding 混淆 | GuidePage 返回图、部分弹窗关闭图、MemberCenter 挽留图 | 按内容尺寸加 padding 计算外框，不能套同一固定尺寸 |
| 容器或组件参数边界 | MinePage 装饰图、AppTipsDialog 动态标题图 | 同批还涉及容器约束或向调用方暴露尺寸参数，不只是逐个补常数 |

因此可共享主题“图像尺寸语义迁移”，但 when/recommendations 需要写适用条件；不能提炼成“所有 Image 固定加宽高”或“资源一律除3”。

### 已核到的输入—偏差—保留—修复链

`GuideInitComponent.ets`：

1. G `agent-aconv-guideinit-91062be71f3ce4ac.jsonl:L21`：02:27:08 收到 Android `fragment_guide_init.xml`，气泡图有 `adjustViewBounds=true`。
2. 同转录 L50/51：02:31:04 的 Bash 读取映射参考，实际返回明确列出 `android:adjustViewBounds | 无直接对应 | 需自定义实现 | 使用尺寸约束`。它不是仓库现版本，也不是仅在全池存在。
3. 同转录 L54：02:35:09 实际 Write 的气泡图只有 `objectFit(Contain)`、`layoutWeight(1)` 等，注释却把 adjustViewBounds 也归为 Contain，并声称高度按比例自适应。这里有可核的局部输出偏差；具体资源比例是否已交付另作限定。
4. G `agent-aslice15-guide-a061e53a1d9503b4.jsonl:L41/42`：18:20:26 读取旧组件，原文仍是上述写法；L229–266 是多次接线编辑，L267/268 在18:42:03读回，相关图像片段仍未形成比例约束。
5. R fixer L211/212：脚本明确把该片段补为 `.aspectRatio(741 / 267)`，返回该文件 `ok`。

可表述为“正确的源布局与约束映射输入 → aconv-guideinit 输出偏离 → 文件中间态 → Slice15 读取并保留 → 该文件修复”。中间保留不自动意味着 Slice15 对本项负有明确复验职责；角色与责任要分别表达。不认证期间所有文件状态都连续已知。

### 另有不同的成因线索，不能套用上述作者

- G `agent-aconv-mine-bb78af185c44860a.jsonl:L38` 实际返回源布局；L63 返回资源映射，L82 的生成 Write 明确写“未标注尺寸的图标留固有尺寸交 icon-sizing 自愈”。这支持“作者把一部分尺寸处理留给后续”的输出事实，不能仅凭该注释证明后续已承接或执行。
- G `agent-aconv-managerenew-b9f5799b407aa4aa.jsonl:L18` 返回源布局；L35 返回 xhdpi 资源映射；L80 的 Write 对目标图片写 `wrap_content → 不定尺寸，随图自适应`。修复 L192/193 则按 xhdpi 资源补显式尺寸。这是另一个可独立追踪的映射偏差分支。
- G 根转录 L4744/4745：生成结束前 `run_loop.sh --mode pipeline --target final` 实际报 PermissionError；L4753、4758、4795、4898 可见随后直跑 skeleton/ledger 检查。L4918 的提交文字声明 FV-1 PASS。该失败与降级是原始命令/回执支持的事实。
- G 根转录 L1557 是当时读到的**计划模板**，提及禁止自行替代全量闭环以及后续 icon-sizing 自愈；不是完整已执行计划的证明。L5405 的后置检查又读出日志中只记两类 detector。现阶段将“兜底自愈缺失使问题留到修复”列为有证据的待核机制，不把根会话的检索／事后声明升级为所有子代理都没跑过的全池事实，也不保证该工具若运行必然修好19个目标。

## 二、遮罩任务的修复更统一，但生成来源仍不同

R fixer L68/69 新增 `Palette.DIALOG_MASK = '#8C000000'`。L103 的批量脚本遍历 ETS，跳过已有 maskColor 的块，对 `AppLoadDialog` 加透明值，其他 builder 加公共遮罩；L104 逐文件回执合计24文件、51处。

两个必须保留的边界：

- G `agent-aslice4-update-bcb43d9c6f9611dd.jsonl:L132/133` 真正读到 AppLoadDialog 的“dimAmount=0、调用方设置透明 maskColor”说明；L170/189 写出的 AppUpdateHost 已给 loading 设置透明值，普通 AppTips 控制器则没有。R L104 对该文件只报1处。不能把该文件里的所有控制器都判错。
- G `agent-aslice8-pay-80bbb1f44b77da0f.jsonl:L264` 写出的 MemberCenter 有4个控制器，H5已有透明值；另3个漏显式值，R L104 对该文件报3处。不能把4个控制器数当4处修改。

### 脚本写入揭示的责任差异

LimitedGiftDialog 和 CampaignDialog 最初 converter 的 Write 只有控制器约定注释，不能由文件作者推出后来嵌套支付弹窗的作者。

- G Slice8 L290：Bash 中真实执行读改写，为 LimitedGiftDialog 新增嵌套 PayAgreementDialog 控制器，未配 maskColor。
- L291：整个调用返回 `Exit code 1`，但同时明确打印 `ok dialogs/LimitedGiftDialog.ets`。这是部分成功，不能把失败调用全当无效应。
- L296/297：后续脚本写入 CampaignDialog 等，返回两文件 ok；新增的嵌套控制器同样未配 maskColor。
- R L103/104：后来对两文件各补1处。

这两条生成期 Bash 写不在该索引的原生 write 作者列表里。调查员需要核脚本和回执，图若缺原生边可按既有反馈流程补报告专属虚线，不能把最初 converter 当成本缺陷作者，也不能因索引没有边删掉这两个分支。

上述材料已支持若干局部偏差与修复。尚未为24个文件逐一认证相关正确输入的交付，不能宣称一个共同 spec／skill／agent 已解释全部。AppLoad、H5 的透明输入和普通0.55输入也不能互相替代。

## 三、建议的单次制卡试验

优先选原第3项图片任务，原样保留19个目标和全部转录。它既有已经能核实的正确输入→错误输出，也有把工作留给后续、自愈流程失败等不同层次，适合检查模型能否在同一问题下保留多条成因分支。遮罩作为下一例，重点验证脚本部分成功和已有正确透明分支。

只给调查模型单问题制卡 skill、原任务 job、完整转录路径，不提供本底稿、预定归因或额外提示；继续 Luna/high，独立新会话。此次不再切回整文件 i14 任务，也不要求额外解释本问题以外的价格等修改。

按以下维度分别看效果，不压成未经定义的总准确率：

1. 单问题范围：是否只处理该问题，区分文件内无关修改。
2. 目标覆盖：19个目标分别有有据 graph 或明确 unresolved；未决不算已解释，不能悄悄丢掉。
3. 内容归因：各偏差起点是否有实际输入/输出证据；不同文件不能由一个样本无条件外推。同根因可共享总结，不要求预定卡片数。
4. 图查验：真实交接、时间、脚本虚线、模型主张与机械状态是否分开。不能靠只保留容易连线的分支完成交付。
5. 成本：调查与制卡/返工分段记录，报告输入总量、缓存、未缓存、输出、时间。新成本不能与 i14 的整会员页直接比较。

现有卡片约定已支持一张卡包含多个 graphs；每个 graph 对应一个目标，UI导出为单目标 view。共同输入当前会在多个 graph 内重复声明，可能增加填表成本。这一轮先量实际开销，不为预分析重构内核或增加新格式。

本底稿不是全19/25文件的完成卡或穷尽审计，以上核验范围与未知均保留。
