# 实验产物

背景、目的与结论见 [../fixchain-research.md](../fixchain-research.md)。这里只说每个文件是什么。会话本体不在仓里,位置见那份文档 §3。

## 2026-09-04-diceroller-run-level/ —— run 级双盲(极简 prompt)

- `prompts/prompt_run_common.md`:两组共用的任务段(原样);`prompt_run_tools.md` / `prompt_run_raw.md`:两组各自的「你手里有什么」;`run_tools.as-sent.md` / `run_raw.as-sent.md`:实际发给模型的拼好的全文。
- `reports/run_tools.md` / `reports/run_raw.md`:两组的最终报告原文(模型输出,一字未改)。
- `metrics/*.json`:费用、轮次、token、工具调用序列(来自 `claude -p --output-format json` 与转录)。
- `judge/run_tools_vs_run_raw.json`:Opus 盲评结果(A/B 随机,treat_is_A 记录了谁是谁)。
- `ledger/`:工具在这个 run 上的状态快照:`status-49d451b1.json`(4 条链、8 段、修复方名片)、`sessions-49d451b1.txt`(sessions 工具原文)、`chains-49d451b1.json`、`stage-marks.json`(run 级阶段时刻,execute 结束 16:46:29)、`version_ledger.txt`(28 个修复版本逐版 diff 摘要,人工对账用)、`coverage.txt`(机械对账输出)。
- `harness/`:`run_probe.py`(跑一组:`--run-level --template ... --raw-dir <转录目录> [--hybrid]`)、`judge_run.py`(盲评)、`coverage.py`(段 / 版本覆盖对账)、`dice_status.py`(链与段快照)、`tool_text.py`(不经模型直接调工具渲染)、`version_ledger.py`、`scope_probe.py`(链范围探针)、`show_call.py`(看某次调用原文)、`list_chains.py`、`mcp-migloop.json`(MCP 配置,指向本仓 src)。脚本里有本机绝对路径,换机器要改。

## 2026-09-03-per-chain/ —— 按链调查(给链坐标)

- `prompt_template.md`(baseline)、`_A.md`(sessions file= + blame changed)、`_B.md`(折叠窗口,已否决)、`_raw.md`(原始组)、`_H.md`(超集组)。
- `judge/*.json`:DiceRoller 4 条链的三组两两盲评。
- `runs-summary.jsonl`:所有按链运行的一行摘要(0723 与 DiceRoller)。
- `judge.py`、`analyze_runs.py`:按链的评委与用量画像脚本。
