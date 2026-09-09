# V12 冻结记录

调查源码 `e67d7d7`，目录 `C:\Users\hongy\projects\_migloop-eval-20260909\source-e67d7d7`；source digest `526e8f61bd30b14b67b742e8c52dbebde933b04d09d9a77eca92434a4188c658`。runner与V10/V11相同，SHA256 `4874a8064f0cf69e2d94b60b4c765c9c7841194163b3f793f5672bdc8e7e6a19`。

启动前全测1583 passed（40.94s）、浏览器175 PASS，无JS异常。反方复核促成希腊词尾lower匹配保护、scope组合拒绝和历史凭据与新请求校验分离。短回执四项测试覆盖原始指针缺失、部分/完整正文、显式其他章节和精确返回节点；UI已标“请求范围”，保留历史参数，不把索引打开当正文交付。

7个新case由V11 variant产生，pool/task哈希不变；全部模型调查尚未开始时源已冻结。计划见 [V12方案](v12-plan.md)、[完整比较清单](v12-metrics-plan.json)。与仍在运行的V11并发，不改任何旧源码/原跑，失败重复照计。

这些是实现契约的验收，不是语义正确率或整体token收益证明。V10成本门槛已跨过，但完整注释仍有实质错误；本轮仍须单独验证是否改善。
