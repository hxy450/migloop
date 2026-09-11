# i15 工程预检（还不是模型成绩）

- 144项独立内核回归通过，Ruff通过。新增回归先4红4绿，再全部通过；后写入回执3项先红后绿，文档中的成功标记不会被认证成实际验证。
- 在新路径复制i14三个索引后，用新代码核十份最终原稿：全部原稿与source_sha256不变、全部机械valid、missing_links全0。保存位置：`C:/Users/hongy/projects/_migloop-scratch/inquiry-i15-recheck-i14/summary.json`。这是重新核图，不是模型改正语义。
- Splash真实Read `l-ec4d33e0050d` 已接回。新增边来自原稿正文中的原生引用，不是BFS凭空补链；旧图26节点12边→新图46节点27边，新增端点不填原因/不标成模型新判断。
- F04后写入候选自动找到根转录L5131/e-7ddd5193b460的`BUILD SUCCESSFUL`，同时也列更晚其它修改后的构建回执。必须由模型核原文与对应命令，不将这些候选直接说成目标验证结论。
- 会员首份失败稿48处错误、25个不同引用中，21个是结果ID误用：19个original可精确提示，另1个records和1个inputs不猜。按ref去重后诊断21759→10352字符，错误位置全保留，没有删掉不合规项。
- 真实Chrome校验：`C:/Users/hongy/projects/_migloop-scratch/inquiry-i15-splash-ui`，所有finding节点/边、原因/原文、review分页呈现、后写入窗口下界、手动与原模型轨迹隔离通过。是i14原稿的新渲染，不算新调查。

没有重新执行迁移/编译，没有改原始池或i14冻结产物，没有重跑raw。语义上的F04错误和Splash历史未全恢复依然属于i14原稿，不能用机械valid把它们洗掉。接下来冻结后才跑i15 Luna。
