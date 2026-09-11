# i14：先记录观察，不在整轮中途改工具

两例pilot核心6/6，见i14-high-pilot-scores.json。剩余八文件已按两条串行队列启动，最大同时两名Luna；同一冻结i14-high，没有自动重试、没有复跑raw。不要改冻结代码或iterate.py。

真实可用性问题：F003调查员从submit拿到正确review_query后，附加了其它列表查询惯用的offset/limit。Engine以“unknown operation or parameter; no legacy version/via parameters”拒绝；模型接着错改op，再错改key，三次均失败，最后没打开对账就交稿。

这不是靠再写一段“不要犯错”来解决。下一轮若仍需迭代，应让返回列表的review复用已有offset/limit分页约定，并让参数错误指出具体非法字段/允许字段/示例。不要静默接受未知参数或自动造坐标。该改动先有回归，再冻结新候选；当前整轮先跑完。

另一个仍存在的取证缺口：Dice没有沿生成者的Bash返回找到themes.xml，也没有用其长thinking来核实“已意识到主题但按AC14裁决”。最终已收敛为“不确定是否读过”，不再像i13那样认证“未读事实”，但机制解释仍需区分证据与假设。保留这个限制，不用6/6核心分掩盖它。

提交后前序提示实际返回且Dice读取了一次，但日志前序在第一次提交就已正确，不能说是提示纠正了这一次模型。F003正确的探针时间同样发生在第一次提交，因此收尾时间对账是否有独立收益尚未证明。

## 整轮运行中补充：查询结果ID被当原文引用

会员页第一次submit `faf9b94bedf24e34` 有48处错误，对应25个不同无效引用；只读比对runs表后，21个逐字等于 `e-` + 该调查员实际打开的query result id。进一步核实类型：19个original有准确data.cite可提示，另1个records和1个inputs是聚合，不能猜其原文。原先笔记称“全部original”不准确，已纠正。例：`e-019a7e371f2345de` 实际是查询结果019a7e371f2345de，对应Kotlin原文`e-7bbf87ca6062`。不是“它没看过这些材料”，也不是机械引用成功后才发现语义不支持；是两个ID层混淆。

当前冻结版能拒绝，但只说unknown coordinate；模型第二稿已自行降到1处错误。下一轮的通用诊断可在**精确匹配该调查员自己的original查询结果**时指出：你用了结果ID，原文cite是X，source/line是Y，请核后修稿。不能自动重写、模糊猜ID、从聚合search第一行挑作者，或读另一调查员结果。其它未知引用仍失败。这样沿现有来源元数据给提示，不引入新协议或隐藏归因推断。

## 已结束原稿的人工核对（整轮尚未完成）

- F10-01，`a18bad53f1e34fdc`，6/6。区分数字占位与Slice8真实价格后缀；有Kotlin富文本输入对照。private helper明确归到视觉返修，有后来去private及BUILD SUCCESSFUL。最终引用全核回。155/155帧完整宿主可见，7,038,132 token、836.663秒。
- F10-02，`ac720fb14c534b43`，4/5，back-gate部分完成（不是把其已正确的局部解释说成全错）：仍未恢复初版callback→装配删除。mask/icon/progress/system-bars均找到实际修改，区分后期测量/生成契约/未经本次重测。129/129帧可见，6,410,257 token、638.442秒。机械needs_revision：漏接一条已经引用的原生Read，非伪造边。
- F10-06，`c8bee4504f604573`，3/3。核到两个生成写入沿用错误图片框和轨道形状；早期资源4dp不冒充页面actor收到；确实是宿主Swiper补bottom，不是finding建议的子按钮尺寸修改。96/96帧可见，3,181,789 token、503.112秒。C节点把后期Slice标origin、早期写者标propagated，角色容易让UI读者误解为首次引入；原因已限为输出缺口，并非证明最早作者，保留此可解释性限制。

Splash漏接的读操作：`l-ec4d33e0050d`，请求`e-97ede5a187e2`、返回`e-255a14167055`，Slice11在2026-07-24 15:34:32.693读Splash。引用在finding.reason正文；report.check会验证并列missing_evidence_links，但evidence_graph.attach只收changes/node.evidence，不收正文引用。这是同一来源收集口径分叉，不是没有真实关系。下一轮统一已引用原文集合；只新增可核原生中性端点/关系，不从相邻节点造因果或替模型填原因。

截至上述五个最终稿（含pilot两例）核心19/20；不当成完整十文件结果，也未认证所有机制假设。核原文时已确认Splash初始writer的相关返回仅在元数据里列themes.xml，并未像Dice那样返回主题全文，不能跨case复用相反判断。

- F10-04，`45dee62153b942c9`，核心2/2，但额外major错误成立：正文B称“修正后只有提交说明…没有修正后的成功编译回执”，unexplained又称截止前没有记录。实际根转录L5131（`cf6a999d195dbc27:5131:a4e99bcd2669a466`）在2026-07-25 01:56:28.547，明确`BUILD SUCCESSFUL in 5 s 498 ms`；早于观察截止，也晚于AppTrackConfig修正。这里不是节点截止藏住了它，repair scope实际到完整观察截止；调查员没有做后修阶段的build/success检索。128/128帧可见，4,991,059 token、578.029秒。
- F10-08，`dc797c6e28804a19`，2/2。这次明确恢复entry既有layered_image/background/foreground复制到AppScope、md5对账与配置icon切换；不把复制认证成Android launcher迁移。dev/full契约边界保留，vendor必要性限定未知。58/58帧可见，1,514,493 token、300.153秒。

七文件暂计23/24核心，**已有F04额外major，因此即使剩余核心全对也不能交付**。不把局部命中数当全稿正确率。

后续待研究的实质缺口：项目级构建成功回执未必含目标文件名，不属于file词法列表；当前agent返回渠道可查，但模型没用却写“无回执”。仅再重复GUIDE中的“不许这么断言”不足。考虑在收尾按实际目标写者与最后写入时刻给出同agent后续返回窗口的现成查询（明确只是时间邻近材料，不是目标构建认证/读写边）。先核当前完整轨迹，不在本轮中途改工具或往模型塞正确答案。
