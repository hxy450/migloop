# V10 冻结与复测记录

- 调查候选：`80c099e`，已经 push 到 `dev/fixchain`，不在 main。
- 冻结目录：`_migloop-eval-20260909/source-80c099e`。
- src digest：`b47380bd789929d3181eae024e4dee12709d8878615ebe7bd85e0271a37a35ed`。
- 实际 runner SHA-256：`4874a8064f0cf69e2d94b60b4c765c9c7841194163b3f793f5672bdc8e7e6a19`。
- 七个新 case 在 `attribution10/formal-v10`，从 V9 原样继承共同任务、目标和冻结池；不重写旧运行。
- 已通过1477项整库 Python 测试，另补的无时区拒绝回归与冻结范围组合15项通过；浏览器范围展示版170项通过。后续查看器 `13924fc` 的版本号不被长名称遮住改动另有172项浏览器通过，不替换调查候选。
- C2离线摘要对比的动作引用存在集合完全一致：2,002 个可见动作引用，118个读动作仍按请求 `reads=False` 折成计数；有序可见引用SHA为 `c7db73b97d29ce429c43eb6b99df3c63b6d86a7a105ef46fcad9b4f9315fcf8a`。这不认证模型读懂了这些条目。
- 首跑2026-09-09 21:31:39 UTC开始，GPT-5.5 / medium / native MCP / reference，1800秒超时。其后按 [预先记录顺序](v10-scope-plan.md) 跑全14次，与 [成本计划](v10-metrics-plan.json) 对账，不选最好重复。

V9开发重复和预选holdout不因本候选而取消或换版本；holdout原始组及工具组各10次已全部完成，独立语义评分仍按固定oracle收尾。本候选仅是开发迭代，不能把已看过的题目称为新的盲测。
