# UI 结论内容完整呈现（与调查实验分开）

等待冻结 i17-high 的两个调查时，发现 page.html 原先只展示 finding.title 和节点 reason/evidence；finding.reason、unknown、hypothesis、recommendation、全局 unexplained 没有独立呈现。用户只看树会漏掉限定语，尤其会看不到 i16 Splash 写在 unexplained 的“最后编译失败”错误。

本次仅补展示，不重写原因或关系：

- 按当前 finding 切换五类可展开原文；假设/建议明确标为未证实或需另验。
- 全局未解释事项始终有单独入口，不冒充选中节点的原因。
- 即使 findings 为空，也仍显示全局未知事项和完整结构化结论；空列表不能让限制消失。浏览器以不落盘的合成展示夹具核过此边界，再还原真实报告。
- 完整 document 只读 JSON 展示，明确不是原始 YAML/JSON 字节；显示原始提交 SHA-256。原始文件仍在 run 产物中。
- 所引 e-ID 可打开原文，只有查阅功能，不创建历史边。原模型轨迹与手动操作保持分离。

真实浏览器验收先红：`C:/Users/hongy/projects/_migloop-scratch/inquiry-report-text-red`，五类内容均缺失。后绿：`inquiry-report-text-splash-green`、`inquiry-report-text-member-green`（同一 scratch 根）；逐 finding 比较所有文本与完整 JSON，同时核节点/边计数、原文展开、输入、outline、时间下界、回执和coverage查询。使用 i16 原稿副本，原稿与图未改，不是新的模型成绩。

i17-high 冻结的是 e25f8e2；本展示修正发生在冻结之后。没有修改它的代码副本、prompt、harness 或运行记录。后续用新版 UI 看冻结报告时必须明确这是同稿重新呈现，不把它说成模型新调查。
