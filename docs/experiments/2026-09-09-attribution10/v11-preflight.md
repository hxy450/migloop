# V11 冻结与离线验收

- 调查源码：`cb3682f`；源目录 `C:\Users\hongy\projects\_migloop-eval-20260909\source-cb3682f`。
- source digest：`1f036a60a25376819196c2005bf47ed9dfaa479c95fdd98c06db9c11e77594a1`。
- 冻结 runner SHA256：`4874a8064f0cf69e2d94b60b4c765c9c7841194163b3f793f5672bdc8e7e6a19`，与 V10 相同。
- 七个新 case 均由 V10 variant 生成，共享只读 pool 和共同任务；未刷新任务、未覆盖旧跑。每案 case.json 记录父案哈希。
- 启动前全套 Python：1533 passed（41.33s）；浏览器 fixture：174 PASS，无浏览器异常。40条 OR 测试覆盖参数、实际原文、置信边界、Unicode、总预算、时间、MCP及HTTP、原生记录重放与旧凭据兼容。
- 实验计划见 [V11方案](v11-plan.md) 与 [成本清单](v11-metrics-plan.json)。启动时 V10仍在跑第二轮，保留至多两个付费调查并发。不会用中途结果改变本轮冻结代码或筛选样本。

这些测试证明特定输入下的程序契约，不证明调查准确率、全量信息无损或20–30%成本收益。真实语义和真实页面的复核须在模型交付后单独记录。
