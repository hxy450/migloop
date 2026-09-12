# i22 开跑前记录

- 新增分组/排序反例先4项红，再通过；最终180项inquiry回归通过（14.34秒），Ruff通过。覆盖真实MCP文本、未知actor不发null查询、未知时间与分页、同范围导航、索引查询计划。
- 独立Luna只读审查未发现阻断性逻辑问题；指出的unknown-owner null提示已修并补测试。其本地pytest受临时目录ACL阻断，主流程指定_scratch后测试通过，不把该阻断记作代码失败。
- `_migloop-scratch/inquiry-i22-preflight/replay.py/result.json` 保存原i21两项批量请求重放：同样156条/20actor，原先不可见的UI actor样例及收窄query都在首批native文本，收窄后187/184回执排前两项且实际返回。旧frames/effects逐条未变。不是新模型分数。
- 首次宽查询约12.25秒，引出独立性能检查；cProfile主要落在SQLite逐行反向查请求，分组统计本身约0.36–0.73秒。一次同时对同个诊断SQLite启动两版计时，旧版因BEGIN IMMEDIATE锁失败；该次不算比较数据，未影响任何模型实验。
- 随后的串行同副本索引实验 `_migloop-scratch/inquiry-i22-preflight/pair-index.json`：10.35→2.21秒，完整query结果相等。EXPLAIN由每条返回从record_time扫描早期事件，变为pairs_by_result按b直达。新索引加在新建库schema，不覆盖旧冻结实验库；这不是整轮模型耗时改善的证明。
- 浏览器 `_migloop-scratch/inquiry-i22-groups-ui` 全部通过：原六项Member图文/原稿/边保持、手动轨迹隔离、原文请求配对、同时间池返回、actor分组点击、排序选择、查看全部分组。预览用i20库的独立副本加物理索引，8878链接及Member原report_id保留；旧i20/i21实验SQLite不加索引、不迁移。
- i21正式核分见i21-high-pilot-scores.json：两题核心4/4、重大额外错误1，未跑余八文件。新一轮必须独立冻结，不能将诊断结果混入调查员原稿或题干。
