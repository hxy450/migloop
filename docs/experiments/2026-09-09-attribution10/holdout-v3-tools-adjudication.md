# Holdout-v3：tools 组原文裁决

快照 2026-09-09T21:35:29Z：已评分 10/10；pending 0。

固定候选 `0be4164`，不按得分更换源码；raw 独立评分不改。正向事实/边界/额外错误/标注纠正分别计算，core=not_preregistered。H3-P1 为 partial_pre_freeze_exposure，仅附录。未完成子集不能用作整体比较。

## 计划状态

| case | rep | 状态 | 正向事实 | 边界 | 范围 |
|---|---:|---|---:|---:|---|
| H3-P1 | 1 | scored_final_submission (completed) | 6.5/7 | 1.5/2 | partial_pre_freeze_exposure |
| H3-P1 | 2 | scored_final_submission (completed) | 7/7 | 2/2 | partial_pre_freeze_exposure |
| H3-P2 | 1 | scored_final_submission (completed) | 6/7 | 2/2 | strict_unexposed_subset |
| H3-P2 | 2 | scored_final_submission (completed) | 4/7 | 0.5/2 | strict_unexposed_subset |
| H3-D1 | 1 | scored_final_submission (completed) | 4.5/8 | 1.5/2 | strict_unexposed_subset |
| H3-D1 | 2 | scored_final_submission (completed) | 6/8 | 1.5/2 | strict_unexposed_subset |
| H3-C1 | 1 | scored_final_submission (completed) | 7/7 | 2/2 | strict_unexposed_subset |
| H3-C1 | 2 | scored_final_submission (completed) | 5.5/7 | 2/2 | strict_unexposed_subset |
| H3-C2 | 1 | scored_final_submission (completed) | 6/7 | 1.5/2 | strict_unexposed_subset |
| H3-C2 | 2 | scored_final_submission (completed) | 7/7 | 1.5/2 | strict_unexposed_subset |

## 汇总边界

- 严格四题：8/8 已评；正向 46/58，边界 12.5/16。
- 五题附录：10/10 已评；正向 59.5/72，边界 16/20。

## 逐项裁决

0/.5/1 是未乘权重的等级。每条沿用 frozen minimum_pass；没有为 tools 增加或删除必答点。原稿引用行、原始 record SHA 与独立 final-ref 配对在 JSON。

### H3-P1 rep1

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| P1-F1 | 1 | 1 | 明确生成时要求真实宿主回调、业务留 Slice16，未把阶段分工归为遗漏。 |
| P1-F2 | 1 | 1 | 两按钮同分支、dismiss 后 filePath/FROM_FILE_IMPORT 参数正确。 |
| P1-F3 | 1 | 0.5 | 知道初版占位与共同关闭/回调；没有恢复原生成者在写前已实际收到 BaseDialogFragment 埋点原文，仍把它留作需结合的解释。与 raw 使用同一部分分规则。 |
| P1-F4 | 2 | 1 | 曝光、两种点击调用及埋点先于确认次序齐全。 |
| P1-F5 | 1 | 1 | 宿主 Router 参数、handleDismiss→confirmOperate 与 dismissOperate→controller.close 的实际顺序均恢复。 |
| P1-F6 | 1 | 1 | 结合两个按钮共同业务分支，准确体现宿主只用 filePath；没有把 bool 维度当不同生成策略。 |
| P1-B1 | 1 | 1 | 明确代码/静态回执不是实机与后端成功。 |
| P1-B2 | 1 | 0.5 | 不把零命中当不存在，未虚构作者心理；但缺原始 BaseDialog 埋点已被生成者读取的反证。 |

额外错误条目 0；必须纠正标注 未发现；缺项仍按上表保留，不等于全文语义认证。

### H3-P1 rep2

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| P1-F1 | 1 | 1 | 准确保留真实回调/关闭与 Slice16 阶段性业务接线分工，没有指为擅自遗漏。 |
| P1-F2 | 1 | 1 | Android 共同分支、dismiss→CreateOutLinePage 合同和后文 filePath/FROM_FILE_IMPORT 目的相符，不发明扩写算法分支。 |
| P1-F3 | 1 | 1 | 明确生成者当时已读 BaseDialogFragment（L31/L32）、初版 no-op 与已实现关闭/回调；补齐 raw 和 tools rep1 均欠缺的前置读取事实。 |
| P1-F4 | 2 | 1 | 曝光及两种 tag 调用、先埋点后共同 handleConfirm 顺序完整。 |
| P1-F5 | 1 | 1 | 真实宿主接线、Router 和 handleDismiss→confirmOperate 顺序正确；无把注释意图当端到端成功。 |
| P1-F6 | 1 | 1 | 结合宿主 gotoCreateOutline(filePath) 与共同 handleConfirm，区分 bool/tag 身份和实际共同业务目的。 |
| P1-B1 | 1 | 1 | 静态/构建/后置设备发现各自分层，不以调用存在替代上报与完整导入验证。 |
| P1-B2 | 1 | 1 | 既承认生成者实际读到 BaseDialog 合同，又不从零命中虚构依赖不存在或作者心理。 |

额外错误条目 1；必须纠正标注 是；缺项仍按上表保留，不等于全文语义认证。

- 初版 v1 应写 P-S16-040/041/042（041出现于两按钮），后续 Slice16 任务才写040..043范围；两个时点不要合并。

- initial_placeholder_id_range：初始原始 Write L73 的唯一 forward-ref 编号为040/041/042（两按钮重复041），没有043。040..043是后续Slice16派发范围，不能回填为初版编号。主体阶段分工和行为恢复仍正确，故独立记录该局部错标。

### H3-P2 rep1

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| P2-F1 | 1 | 1 | 真实本地解析/路由与明确允许的 SDK placeholder 分开。 |
| P2-F2 | 1 | 0.5 | 恢复初版注释中的空表保留项且不把灌表当漏修；未明确恢复 Android 空初始化与后续 Edit 保持同一初始化不变这一前后事实。注释需源码支持的边界也保留。 |
| P2-F3 | 1 | 1 | 实际日志替身到 SDK 门面调用的变化准确，没有升级为 SDK 上线。 |
| P2-F4 | 1 | 1 | 独立恢复本地 payload 日志到 EventUpload 副作用出口，与 SDK 回执门面清楚区分。 |
| P2-F5 | 1 | 0.5 | 最终宿主同级分流正确；没有说明曾提议的旧哨兵方案被取消，按与 raw rep2 相同口径记半分。 |
| P2-F6 | 2 | 1 | 明确互斥、PUSH/SHORTCUT/NONE 和 URI→推送 extras→shortcut extras 顺序；因此推送 extras 排在 shortcut 前，恢复了最低要求的重叠优先级。 |
| P2-B1 | 1 | 1 | 门面接线不等于 SDK 实现体或服务端回执成功。 |
| P2-B2 | 1 | 1 | 限定在读取的源码片段，并说明注释/全仓零调用需要范围证明，不扩大为全系统/所有未来版本无入口。 |

额外错误条目 0；必须纠正标注 未发现；缺项仍按上表保留，不等于全文语义认证。

### H3-P2 rep2

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| P2-F1 | 1 | 0.5 | 恢复初版路由主体与后续宿主接线分工；没有恢复初次派发明确允许 SDK placeholder、要求本地解析真实实现的完整合同。 |
| P2-F2 | 1 | 0.5 | 保持空表不作为漏修的方向正确；没有原 Android 空初始化及后续 Edit 保持同一初始化的前后证据。 |
| P2-F3 | 1 | 0 | 只有代理报告的泛称，没有恢复 pushClick 从 skipped 日志到 PushSdkService.pushClick(want) 的真实调用变化。 |
| P2-F4 | 1 | 0 | 最终稿没有恢复 TrackParams/EventUpload 的实际埋点出口变化；即使调查过程或旧草稿曾打开，不能替代最终提交内容给分。 |
| P2-F5 | 1 | 1 | 明确旧哨兵提议与后续取消、宿主层同级分流，前后结构变化完整。 |
| P2-F6 | 2 | 1 | 优先级顺序与互斥分流同时明确；满足重叠时推送先于快捷方式的最低行为要求，不强制逐字列示例键。 |
| P2-B1 | 1 | 0 | 未交代后置 F014PushService.impl 仍为 null/待注册及门面不等于 SDK/实际上报。一般设备未知不能替代本条具体 SDK 分层边界。 |
| P2-B2 | 1 | 0.5 | 保留不以零命中证明需求不存在及新需求才能改变 D0 的一般边界；未恢复 Android createShortCut 注释块的具体限制。 |

额外错误条目 0；必须纠正标注 未发现；缺项仍按上表保留，不等于全文语义认证。

### H3-D1 rep1

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| D1-F1 | 1 | 1 | 明确未修源码、未显式类型/圆角/阴影，并恢复字号/资源等初始属性。 |
| D1-F2 | 2 | 0.5 | 恢复主题/资源与显式 Roll 规格，但遗漏写前实际返回的通用 allCaps 映射及 F001-AC14 的确切冲突。按同一冻结标准记半分，不把“未显式要求”升级为从未有任何依据。 |
| D1-F3 | 1 | 0.5 | 恢复两项后期派修及 finding 层的 ROLL/shape；未恢复独立 Android dump 原始输出与初始写入的时间关系。 |
| D1-F4 | 1 | 1 | 资源读取→大写→rollLabel→Button 接线准确，并明确资源原串不改。 |
| D1-F5 | 2 | 0.5 | 三个实际补丁效果齐全；未说明颜色、字号、minWidth/间距等主要保持不变，按与 raw rep2 相同 minimum_pass 记半分。 |
| D1-F6 | 1 | 0 | 只有原先 UI TDD 阻断记录，没有恢复后置独立 root 的实际 replay：ROLL、10/10、21/21 与 7 不可观测。该 TDD 历史记录本身真实，未将“无像素复验”误判为错误。 |
| D1-B1 | 1 | 0.5 | 承认生成者已有主题等信息、避免用后期 finding 直接指控明知遗漏；仍漏实际 allCaps 映射及其与后置 dump 的边界。 |
| D1-B2 | 1 | 1 | 明确阴影近似、finding/参与者读图自述与像素独立复验不同，不把构建或静态代码当全视觉通过。 |

额外错误条目 0；必须纠正标注 未发现；缺项仍按上表保留，不等于全文语义认证。

### H3-D1 rep2

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| D1-F1 | 1 | 1 | 初版实际 Button 及其未加大写/类型/圆角/阴影的状态明确，原资源 Roll 未被误说成 ROLL。 |
| D1-F2 | 2 | 0.5 | 恢复主题及具体页面规格不足，但仍遗漏原生成者写前收到的 allCaps 通用映射和功能规格 AC14 明确 Roll 的冲突。 |
| D1-F3 | 1 | 0.5 | 恢复两项后置 visual finding 及其层次；未直接恢复初版写入之后 Android dump 的原始 ROLL 输出/时刻。 |
| D1-F4 | 1 | 1 | getStringSync→toUpperCase→rollLabel→Button 的显示层变化准确。 |
| D1-F5 | 2 | 1 | before basis 明列字号/颜色/背景/minWidth/间距等已有属性，后续限定为 rollLabel/转换/按钮类型圆角阴影三组增量，完整区分主要既有属性与新增效果；不要求逐字重复每个数值。 |
| D1-F6 | 1 | 0.5 | 恢复后续 shell 通道、ROLL 与 10/21 的限定结果，明显超过仅有 ROLL 摘要；仍未交代 7 项不可观测，引用的是 L291/L310 报告写入而非 L256/L260 实际 replay 返回，故该冻结完整事实记半分。不是把报告真实内容判错。 |
| D1-B1 | 1 | 0.5 | 避免后置依据倒灌且承认主题可用；遗漏前置 allCaps 映射，边界只部分满足。 |
| D1-B2 | 1 | 1 | 正确区分 shell 文本/有限 UI 观察、canonical 通道仍 DEFERRED 与独立像素复验，未把局部通过升级为全验证。 |

额外错误条目 0；必须纠正标注 未发现；缺项仍按上表保留，不等于全文语义认证。

### H3-C1 rep1

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| C1-F1 | 1 | 1 | EntryAbility/main_pages 仍指 Index，Hello World 模板状态明确并来自补丁前读取。 |
| C1-F2 | 1 | 1 | 恢复写前阶段性装配合同，未倒归单页生成者遗漏。 |
| C1-F3 | 1 | 1 | Navigation 壳、provider 共享栈和首次初始路由均恢复；minimum_pass 不强制逐字写 initialRouteInstalled 标识符，故不给命名格式罚分。 |
| C1-F4 | 2 | 1 | 新增 MainPage 与三处入口联动完整。 |
| C1-F5 | 1 | 1 | 25 分支、唯一入口、loadContent 与静态验证范围准确。 |
| C1-F6 | 1 | 1 | 保留后置结构失败与随后复扫的先后，不将入口静态通过当整个工程同时无失败。 |
| C1-B1 | 1 | 1 | 明确规范与分工，不虚构早期作者责任。 |
| C1-B2 | 1 | 1 | 静态、构建安装与真实导航行为分开；结构检查不升级成全运行验证。 |

额外错误条目 0；必须纠正标注 未发现；缺项仍按上表保留，不等于全文语义认证。

### H3-C1 rep2

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| C1-F1 | 1 | 1 | 补丁前真实模板入口和已有25页面清单正确。 |
| C1-F2 | 1 | 1 | 明确写前可用的单入口/同步加载/模板剔除规范与阶段职责。 |
| C1-F3 | 1 | 0.5 | 共享栈、Navigation/pageMap 和初始 Splash 已恢复，但未说明一次性/首次限制或 initialRouteInstalled 守卫；按与 raw 同一规则记半分。 |
| C1-F4 | 2 | 1 | 新增文件、main_pages、EntryAbility、删除Index三联改动全部恢复。 |
| C1-F5 | 1 | 1 | 25分支、单入口、loadContent及未输出missing-route只作为结构检查，范围正确。 |
| C1-F6 | 1 | 0 | 恢复了另一层构建报告，却遗漏更早紧随装配的结构audit FAIL=2。首轮构建资源失败及更晚Base7收敛不能代替此事实。 |
| C1-B1 | 1 | 1 | 阶段分工不归咎单页作者；参与者意图与实际补丁分开。 |
| C1-B2 | 1 | 1 | 静态、后续构建/安装和全导航验证严格分层，未升级证据。 |

额外错误条目 0；必须纠正标注 未发现；缺项仍按上表保留，不等于全文语义认证。

### H3-C2 rep1

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| C2-F1 | 2 | 1 | 后置修复前读取正确区分缺 product 引用与已有 app.signingConfigs 调试材料；不以额外的生成期断言抹去这项正确恢复。 |
| C2-F2 | 1 | 1 | D-019 读取与开发/生产材料边界准确。 |
| C2-F3 | 2 | 1 | 准确恢复一行 product 引用变化，不称修改凭据/业务代码。 |
| C2-F4 | 1 | 1 | E1 与 E6 对 unsigned fallback→signed 的来源明确是代理报告，且先后与补丁分开。 |
| C2-F5 | 1 | 0 | 漏掉主根实际重建/安装工具返回，并错误把后续证明层级概括为仅报告。冻结 c2-later-build/install（L6179）以及原始 L7862/7866 均是反证。 |
| C2-B1 | 1 | 1 | 调试 HAP、业务认证与生产发布就绪严格分层。 |
| C2-B2 | 1 | 0.5 | 保留作者/内部决策未知，但同时确定声称“生成期未改”，把账本未捕获的历史升级为无改动，故该来源边界仅部分满足。 |

额外错误条目 2；必须纠正标注 是；缺项仍按上表保留，不等于全文语义认证。

- 改成“当前账本未捕获生成期写入；缺原始写/删记录，不能确认此前如何演变”，不能以模板/外部标签认证全阶段无改动。

- 保留11:16代理报告限制，但另列更晚主 root 的实际重建/安装输出及其时间，不再将全池后续层级概括为仅报告。

- unsupported_history_absence：由账本 v1 外部/模板标签推出生成期确实未改，缺少原始执行覆盖证明。冻结资料保留引入/删除作者未知；现有后置读取不能证明整个生成阶段未改过。

- false_evidence_level_exclusivity：后续并非只有报告：08-21 主 root L6178/L6179 的 auto_install_artifacts.py --rebuild 返回真实 BUILD SUCCESSFUL 与 signed HAP install bundle successfully；08-22 L7862/L7866 也有直接原始输出。未见子代理体不遮蔽主 root 工具证据。

### H3-C2 rep2

| 项 | 权重 | 评分 | 裁决依据 |
|---|---:|---:|---|
| C2-F1 | 2 | 1 | 修复前 product 缺引用与同文件已有 default 调试签名材料清楚区分。 |
| C2-F2 | 1 | 1 | 恢复修改时已读的开发调试许可、生产材料责任人与 blocked 边界。 |
| C2-F3 | 2 | 1 | 实际一行 product 引用改变、未动材料/业务认证代码的范围准确。 |
| C2-F4 | 1 | 1 | unsigned fallback 与随后 signed 消息都标为代理主张，并与原始检查/补丁区分。 |
| C2-F5 | 1 | 1 | 恢复原始 auto_install_artifacts.py 重建和 signed HAP 安装成功，并与更晚日志检查、代理报告分层。已独立在本 run action 输入/返回核到 #4383→原 pool L6178/L6179，不是从别的模型答案补入。 |
| C2-B1 | 1 | 1 | 不将 HAP 构建安装升级为 ApiClient/登录或生产发布完成。 |
| C2-B2 | 1 | 0.5 | 保留检索和池外未知，但确定声称“生成期外部输入/未改动”仍超出原始历史可证范围；与同题 tools rep1 相同部分分口径。 |

额外错误条目 1；必须纠正标注 是；缺项仍按上表保留，不等于全文语义认证。

- 应写“当前账本将首版标为外部输入/未捕获生成期写入，无法据此确认更早的全部编辑历史”，不要把缺少原始执行证据写成生成期确定未改。

- unsupported_history_absence：账本未捕获生成期写入不能证明整个生成阶段未改动；原始材料不足以确定引入/删除者或全部历史。该句将观测缺口变成确定的无改动状态。

## 最终提交与原文定位

没有把 check 草稿或 checker 清零当语义结果。每份只评分最终 reference 指向且与原生输入逐字一致的 verdict.yaml。

- H3-P1 rep1：原生 final L392；选定 check call_TBrFVHKLB7Z7MNF4S4I5AKH3，输入/返回 L386/389。双 hash 与原稿、原生最终 reference 均匹配。

- H3-P1 rep2：原生 final L305；选定 check call_IbrFOhN8PUR5b4ur8dHTClhX，输入/返回 L297/300。双 hash 与原稿、原生最终 reference 均匹配。

- H3-P2 rep1：原生 final L377；选定 check call_6F5AY3AmcHSzwD18zFsarw7N，输入/返回 L371/374。双 hash 与原稿、原生最终 reference 均匹配。

- H3-P2 rep2：原生 final L252；选定 check call_FsHSsyLk0MB3BCvTG4hRFjtI，输入/返回 L246/249。双 hash 与原稿、原生最终 reference 均匹配。

- H3-D1 rep1：原生 final L255；选定 check call_hbrYInmziDC4gQKMiUdDZLht，输入/返回 L249/252。双 hash 与原稿、原生最终 reference 均匹配。

- H3-D1 rep2：原生 final L202；选定 check call_7sqpmtokrIoYBy2XBgXzy3Xz，输入/返回 L196/199。双 hash 与原稿、原生最终 reference 均匹配。

- H3-C1 rep1：原生 final L319；选定 check call_i4D0BeUzUIaKBGOGOa39jVRQ，输入/返回 L313/316。双 hash 与原稿、原生最终 reference 均匹配。

- H3-C1 rep2：原生 final L246；选定 check call_adP7oZOOjnSAC2VBPoZwojFD，输入/返回 L240/243。双 hash 与原稿、原生最终 reference 均匹配。

- H3-C2 rep1：原生 final L221；选定 check call_PRDrVAhVZeKAfCAor4cioCFa，输入/返回 L215/218。双 hash 与原稿、原生最终 reference 均匹配。

- H3-C2 rep2：原生 final L214；选定 check call_wLySMLjify0d2ZncVp5KHnjG，输入/返回 L208/211。双 hash 与原稿、原生最终 reference 均匹配。

当前 117 个逐稿唯一原文引用已按唯一 tag+物理行回读并保存 record SHA。synthetic seq/version 不在原始 JSONL 中，未借其替代语义事实。C2 rep2 正文另用的 #4016/#4383/#4923 已经由同 run 的真实 action 输入/返回补充定位到原始物理行，详见 JSON prose_reference_resolution。

P2 中提到的 persisted-output 账本观测不作修复/作者归因金标。历史构建/测试报告只证明其当时保存的结论，后置回放和不可观测项继续独立核验。

## 快照历史

| 时间 UTC | 已评 | pending |
|---|---:|---:|
| 2026-09-09T20:59:00Z | 2 | 8 |
| 2026-09-09T21:02:34Z | 3 | 7 |
| 2026-09-09T21:04:46Z | 4 | 6 |
| 2026-09-09T21:09:41Z | 5 | 5 |
| 2026-09-09T21:14:53Z | 6 | 4 |
| 2026-09-09T21:19:54Z | 7 | 3 |
| 2026-09-09T21:25:44Z | 8 | 2 |
| 2026-09-09T21:28:38Z | 9 | 1 |
| 2026-09-09T21:35:29Z | 10 | 0 |

原始 run、源码、oracle、raw 评分文件均不改；后续仅追加新 completed 稿的裁决。

## 完整计划与锁定 raw 的分项对照

| 严格四题、各两次 | raw（已锁定） | tools 0be4164 | 差值 |
|---|---:|---:|---:|
| 正向事实恢复 | 42/58 (72.41%) | 46/58 (79.31%) | 6.90 个百分点 |
| 边界恢复 | 13.5/16 (84.38%) | 12.5/16 (78.13%) | -6.25 个百分点 |
| 额外错误条目 | 2 | 3 | 条目分级见各稿，不作任意加减分 |

正向恢复有所提高，但边界恢复下降，且仍有来源层级/历史无改动确定性问题。不能把正向分单独说成总体语义准确率更高或 joint pass；core 未预注册。成本信息没有参与语义给分，原 raw 评分未改。

| case | rep1 正向 | rep2 正向 | 两次均值 | 边界两次 | 额外错误两次 |
|---|---:|---:|---:|---|---|
| H3-P1（仅附录） | 6.5/7 | 7/7 | 6.75/7 | 1.5 / 2 | 0 / 1 |
| H3-P2 | 6/7 | 4/7 | 5/7 | 2 / 0.5 | 0 / 0 |
| H3-D1 | 4.5/8 | 6/8 | 5.25/8 | 1.5 / 1.5 | 0 / 0 |
| H3-C1 | 7/7 | 5.5/7 | 6.25/7 | 2 / 2 | 0 / 0 |
| H3-C2 | 6/7 | 7/7 | 6.5/7 | 1.5 / 1.5 | 2 / 1 |

完整10份已保留全部结果与重复波动，不择优。严格子集按题等权正向恢复率为 79.80%；五题含暴露附录的正向恢复为 59.5/72，边界 16/20；该附录不替代严格子集。
