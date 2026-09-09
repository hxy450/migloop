# V7 冻结与回归记录

- 代码：`84bfcf8`，已 push `origin/dev/fixchain`；冻结目录 `C:/Users/hongy/projects/_migloop-eval-20260909/source-84bfcf8`。归档包含 src、pyproject.toml 和此次 run_pair.py，后续模型队列使用归档内 runner，不受工作树后续修改影响。
- 源清单摘要：`acb1522d9851039174e4ac99f3620e197afd8999113226e50bb137df0e593fa6`。
- 七个新 case 在 `C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v7/`，全部沿用 formal-v1 的精确中性题目与共享只读池，未刷新任务、未重写旧结果。
- 单测：1259 passed（19.37秒）；浏览器：122条断言通过，无页面异常。独立只读复核确认完整 GUIDE 原文未删改，topic 分区无丢失/重复；未知 blame 恢复不产生行归属。
- 首批启动约18:40 UTC：队列一 C4 rep1→Member rep2，队列二 Member rep1→C4 rep2，全部 GPT-5.5 medium/native/reference。这只是运行记录，不预示成功。

## 独立题目包

`C:/Users/hongy/projects/_migloop-eval-20260909/holdout-v3/` 新题目包已于18:40:35 UTC冻结；原有同目录旧子任务不修改。公共 questions.json 摘要 `460bd9e1415f426f6e44b3eafef0ab4d753557590119bdceee4990f1849d6fe7`；manifest 摘要 `3da40027c5448566dfc757baf583026294a3a4f48d09ba75a3d35d34b7cb441b`。

5个新目标文件（0723两题、Dice一题、Codex两题），29项正向事实、10项边界/反证、69个源引用已经独立核验。主线程只查看清单/公共元数据，未读私有 oracle，不将答案送入模型输入池或源码。它仍是同已知项目的 question-level holdout，不能冒充跨项目泛化。
