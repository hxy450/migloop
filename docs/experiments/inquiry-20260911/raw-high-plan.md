# raw-high：补齐与i20相同深度、相同文件题目的原始组

2026-09-12，用户明确要求把原始组提升到high试验。这是新授权的独立对照，不覆盖或改写旧medium原始组，也不自动反复重跑raw。

- 固定10文件/28核心、三池和全部时间边界，原稿/原文评分标准不变。
- 模型gpt-5.6-luna，high。按OpenAI Docs核实[官方Luna说明](https://developers.openai.com/api/docs/models/gpt-5.6-luna)支持high；实际型号/effort仍以原生turn_context核对，不靠配置字面值认证。
- 每文件一次，共10次；同最多两并发，每次1800秒；不按成绩提前选择或替换样本。首批1/2，随后按剩余ID推进；身份/宿主指令/录制异常则暂停新任务，保留失败。
- 文件级题目逐字取i20工具prompt在MCP补充之前的部分，核等于原始冻结任务（Member等于既有longchain原始题目）。其余设置取i20配置，仅清空mcp_servers。原始组可以rg/解析JSONL，中文散文输出，不因缺YAML/节点坐标扣语义分。
- 不给工具GUIDE、参考答案、MCP、第二模型或外网。无新的归因关键词、预设缺陷或图连通要求；不执行历史命令。工具组GUIDE和结构化自查仍是两种调查系统之间的处理差异，并非只有两原子数据结构不同。
- 新目录`C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/raw-high-i20-match-20260912`；prepare/verify不调用模型，run才调用。新薄运行器复用旧raw启动/录制/超时逻辑，不修改旧run_raw10.py/iterate.py、全局Codex设置或生产inquiry。
- 比较i20-high现有完整十跑，不拼i21—24不同轮的正确答案。报告文件等权、核心单元等权、额外重大错误、全文件通过及每文件成本。仍是开发者按原文核验、历史非同期对照，不能证明总体泛化或某一机制独立收益。相对旧medium的Member变化不只effort，必须注明。

开跑前核10题前缀、三池完整哈希、核心合同、high/no-MCP配置、CLI二进制及新目录防覆盖。每次运行后复核，不能因录制失败就当归因失败或成功。所有结果包括超时保留；无自动重试、修稿模型或格式修复轮。统计两并发队列墙钟与各模型耗时之和，不把缓存/推理重复累加。

预检：一个离线组合回归覆盖同题/配置、原稿防覆盖和题干漂移拒绝，通过；Ruff通过；prepare/verify的10题与完整池核验通过、模型调用0。初次冻结后发现import排序格式问题，在任何runs目录出现前修正并把旧driver哈希保存在manifest.prelaunch_driver_revision；没有模型中途换代码。最终driver SHA256为`caa94822399ffabb934c58033314a939f13b08d30f1d5b0c975e27896c2703e1`。

新manifest外部锚点：SHA256 `7bc5b0b536421f242dbe633ab9996924a0a24a1f2a24fc8dd142359ad9e7bda5`。独立只读Luna审查确认十题、完整池、高深度配置和无MCP相符，前两份实际native turn_context为Luna/high。初始skip_host_skill_discovery消息是各轮已有的实验功能告警，不能当语义错误，也不隐藏。冻结校验不等于每份报告未被改过；裁决时另核metrics中的native转录SHA、最终原文及报告SHA。没有改变运行中的代码或设置。

完成记录（2026-09-12）：预定10/10一次跑完，无重试/超时/身份失败；代码、题目、配置、核心和池校验仍通过。最终原稿/型号核验、逐条裁决与同深度成本见[raw-high-results.md](raw-high-results.md)。本段是结果链接，不回写预登记或模型原稿。
