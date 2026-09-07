# 实验产物

背景、目的与结论见 [../fixchain-research.md](../fixchain-research.md)。这里只说每个文件是什么。会话本体不在仓里,位置见那份文档 §3。

## 2026-09-04-diceroller-run-level/ —— run 级双盲(极简 prompt)

- `prompts/prompt_run_common.md`:两组共用的任务段(原样);`prompt_run_tools.md` / `prompt_run_raw.md`:两组各自的「你手里有什么」;`run_tools.as-sent.md` / `run_raw.as-sent.md`:实际发给模型的拼好的全文。
- `reports/run_tools.md` / `reports/run_raw.md`:两组的最终报告原文(模型输出,一字未改)。
- `metrics/*.json`:费用、轮次、token、工具调用序列(来自 `claude -p --output-format json` 与转录)。
- `judge/run_tools_vs_run_raw.json`:Opus 盲评结果(A/B 随机,treat_is_A 记录了谁是谁)。
- `ledger/`:工具在这个 run 上的状态快照:`status-49d451b1.json`(4 条链、8 段、修复方名片)、`sessions-49d451b1.txt`(sessions 工具原文)、`chains-49d451b1.json`、`stage-marks.json`(run 级阶段时刻,execute 结束 16:46:29)、`version_ledger.txt`(28 个修复版本逐版 diff 摘要,人工对账用)、`coverage.txt`(机械对账输出)。
- `harness/`:`run_probe.py`(跑一组:`--run-level --template ... --raw-dir <转录目录> [--hybrid]`)、`judge_run.py`(盲评)、`coverage.py`(段 / 版本覆盖对账)、`dice_status.py`(链与段快照)、`tool_text.py`(不经模型直接调工具渲染)、`version_ledger.py`、`scope_probe.py`(链范围探针)、`show_call.py`(看某次调用原文)、`list_chains.py`、`mcp-migloop.json`(MCP 配置,指向本仓 src)。脚本里有本机绝对路径,换机器要改。

## 2026-09-06-aboutuspage-three-arms/ —— 同一条链,legacy 工具 / 现在的工具 / 原始转录各 2 次

- `prompts/*.as-sent.md`:三组实际发出的 prompt;`harness/prompt_template_legacy.md`(09-02 七步路径,MCP 版)、`prompt_template_A.md`(现在的工具,变体 A)、`prompt_template_raw0723.md`(09-02 对照组原话的模板版)、`mcp-legacy.json`(MCP 指到 legacy 分支)。
- `reports/<组>-rep<k>.md`:六份报告原文。`metrics/runs.json`:费用、时间、调用序列、每工具字符。
- `judge/`:三对盲评(现在 vs 原始、legacy vs 原始、现在 vs legacy)的 JSON 与摘要。
- `harness/measure_tool_text.py`:同一会话同一组调用在两版代码下的文本体量对比脚本。

## 2026-09-03-per-chain/ —— 按链调查(给链坐标)

- `prompt_template.md`(baseline)、`_A.md`(sessions file= + blame changed)、`_B.md`(折叠窗口,已否决)、`_raw.md`(原始组)、`_H.md`(超集组)。
- `judge/*.json`:DiceRoller 4 条链的三组两两盲评。
- `runs-summary.jsonl`:所有按链运行的一行摘要(0723 与 DiceRoller)。
- `judge.py`、`analyze_runs.py`:按链的评委与用量画像脚本。

## 2026-09-06-0723-19roots/ —— 0723 全部 19 根,纯工具 vs 原始转录,两组都只给文件名

- `prompts/prompt_template_seg_tools0.md` / `prompt_template_seg_raw0.md`:正式两组的模板(只有 `{sid}` `{file}` 两个占位符);`prompt_template_seg.md` / `prompt_template_seg_raw.md`:作废第一轮的模板(原始组被给了修复方 / 转录路径 / 时间)。
- `hint-free/`:正式一轮。`reports/<tools|raw>/chainNN-<文件>.md` 38 份报告原文;`prompts-as-sent/` 实发提示词;`metrics-<arm>.json` 逐根费用、轮次、token、调用序列;`summary-<arm>.json` 汇总。
- `hinted-invalid/`:作废的第一轮,同样布局,只作记录。
- `judge/hint-free_tools_vs_raw.json`:19 根盲评(A/B 随机,`treat_is_A` 记录谁是谁)。
- `harness/`:`run_probe.py`(`--chains 0,1,2 --label X --template T [--raw-dir 转录目录]`)、`judge.py`、`seg_summary.py`(汇总一组)、`seg_compare.py`(两组并排)、`seg_anatomy.py`(逐调用解剖:agent 带不带 since、sessions 碰过节、原始组找人阶段、每轮上下文)、`seq_dump.py`(逐调用序列)、`judge_tally.py`(解盲汇总)、`chains-ff019d8a.json`(19 根)。脚本里有本机绝对路径。

## 2026-09-07-four-roots-after-optim/ —— 五步优化落地后四根验收(新工具 vs §4.8 的旧工具与原始组)

- `reports/`、`prompts-as-sent/`:MineComponent / DesignTokens / AboutUsPage / HomePage 的新工具报告与实发提示词(模板 `harness/prompt_template_seg_tools1.md`,只比 §4.8 的多一个 search 名字)。
- `metrics-tools-after.json`:逐根费用、轮次、token、调用序列。`judge/tools-after_vs_raw.json`:与 §4.8 原始组报告的盲评。
- `harness/`:`tool_mix.py`(按工具用量)、`size_probe.py`(agent 视图体量)、`search_probe.py`(0723 四个带起点查找)、
  `index_gap.py`(转录 vs 账本覆盖对账)、`fake_v1.py` / `external_probe4.py` / `external_pointers.py`(假 v1 / 幽灵路径 / 外部输入指针)、`run_probe.py`。脚本里有本机绝对路径。
