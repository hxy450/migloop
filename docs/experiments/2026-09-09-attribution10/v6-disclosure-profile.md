# V6 只读披露量与耗时画像

测量日期：2026-09-09。使用冻结源 `4d5db4f`，没有调用模型，也没有读取正在运行的调查结论。通过代码探索技能核对实际查询入口；本仓库未索引，直接使用源码，未建立索引。

## 口径与坐标

- 源目录：`C:/Users/hongy/projects/_migloop-eval-20260909/source-4d5db4f`。实际 Python import 路径已核对到该目录。
- source digest：`76a01f4fae7bf0fe142ade7b2a4f6c5cd6842dc9fc9b3f8dbaa60a8ac88b79cb`（case.json 记录值）。
- 使用 `formal-v6-document/{member-center,codex-c4}/case.json` 的 current_root 与共享 pool，设置 `MIGLOOP_FROZEN_POOL`，禁止字节码写入。
- 通过 `atom_queries.render_text(ledger, root, tool, args)` 直接测量。每项预热一次，然后5次取 `time.perf_counter()` 中位数；同时断言5次返回文本完全一致。此处不含服务建账、HTTP/MCP、模型计算与原生传输截断。
- 字符数为 Python `len(text)`，不是字节、token 或费用。各比较组固定实体、版本与输入窗口；不同组不是等价调查范围，不能拿其比值声称准确率或完整性。

| 比较组 | Member | C4 |
| --- | --- | --- |
| 整段 agent | `agent-aslice8-pay-80bbb1f44b77da0f@v13`，163动作 | `__main__:01a009fe@v249`，2092动作 |
| 单版截止窗口 | 同 agent，`v=12,since=11,until=13670` | 同 agent，`v=249,since=248,until=2400` |
| file | `MemberCenterPage.ets@v7`，1194行、全文已知；本账本共16版 | `LaunchAgreementDialog.ets@v1`，本账本唯一版本、正文未知 |
| action | 同 Member agent，`seq=13670` | 同 C4 agent，`seq=2400` |

这里没有沿用旧事实 epoch 的 C4 file@v2；新账本只有 v1。所有 action 的 `part/offset/max_chars` 比较固定同一个 seq。单版窗口选择写调用发起时的 until，写调用本身作为未完成效应披露，不冒充写后输入。

## 披露量与暖耗时

| 查询 | Member 字符 | Member 中位毫秒 | C4 字符 | C4 中位毫秒 |
| --- | ---: | ---: | ---: | ---: |
| agent 默认 | 28,333 | 36.249 | 339,111 | 23.284 |
| agent reads=True | 28,333 | 35.873 | 351,897 | 23.346 |
| agent reads=True, seen=True | 31,734 | 35.870 | 359,931 | 24.578 |
| 单版 + until 默认 | 2,788 | 36.272 | 19,796 | 67.615 |
| 单版 + until, reads=True | 2,788 | 38.186 | 19,796 | 67.216 |
| 单版 + until, reads=True, seen=True | 2,788 | 38.486 | 20,613 | 64.879 |
| file 默认 | 13,016 | 36.625 | 1,850 | 10.762 |
| file content=True | 64,306 | 37.618 | 1,862 | 10.801 |
| file diff=True | 19,085 | 36.037 | 2,077 | 11.174 |
| action 默认（max_chars=20000） | 20,850 | 9.945 | 1,020 | 19.386 |
| action input 首1200字 | 2,068 | 10.007 | 990 | 19.178 |
| action input offset=1200 | 2,071 | 9.882 | 675 | 20.007 |
| action output 首1200字 | 1,018 | 10.250 | 682 | 19.363 |

主要观察：

- Slice8 只有13版，默认已经展开读取索引，因此 `reads=True` 不再减少/增加字符；`seen=True` 只增加记录中可展开的已见片段，不等于完整原始转录。
- C4整段默认仍返回339,111字符；超过25版的自动折叠只省去部分读清单，并未给整个 agent 设置总字符上限。需使用明确窗口缩小披露范围，不能把本地可生成全文当作模型实际完整收到。原生工具或外层包装仍可能截断，此测量没有认证交付/注意力。
- C4 的 until 窗口虽然文本更短，但中位约65–68ms，高于不带截止的整段约23–25ms；这是实测查询耗时，不含建账，也不能从返回长度推断计算耗时。
- Member file@v7 的 content 展开确实给出已知正文；C4 content 只多12字符并明确“无法复原”，未补造未知源码。Member diff 默认有6000字符展示预算，不代表完整差异全文。

## 原始转录字符基线

以 UTF-8 解码、保留原始换行计数。基线包含 JSONL 元数据、工具封装及重复记录，范围是完整文件，不是上述特定锚点前的等价上下文；仅供体量参照，不换算 token/价格或计算保真率。

| 池 | JSONL文件数 | 全池原始字符 | 所选agent原始转录字符 | 首次 service建账秒 |
| --- | ---: | ---: | ---: | ---: |
| member-center | 146 | 222,306,266 | 2,251,377 | 10.5497 |
| codex-c4 | 2 | 22,324,765 | 12,020,371 | 2.2031 |

- Member 所选转录：`formal-v1/member-center/pool/9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aslice8-pay-80bbb1f44b77da0f.jsonl`。
- C4 所选转录：`formal-v1/codex-c4/pool/rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl`。
- Member ledger：`atoms-2026-09-09-file-evidence5:146:4766238c5ac3d5f22a42d916`；pool digest：`a78b1373045f7558d6da3b76123e30d032635a2a0b4cdd665e7f80c0bdf8b337`。
- C4 ledger：`atoms-2026-09-09-file-evidence5:2:3e2cc0e88d5a7281c66ade63`；pool digest：`5bcd5ed757c468cea95f79591b41a4fb88cea2a6d6f4b5b1505e0026d2dbfc78`。
- 两池和冻结源在测量前后，全文件相对路径/大小/mtime_ns 清单一致。这里做的是只读操作与 stat 清单核对，不将其冒称为重新计算完整内容哈希认证。

## 早期输入索引、分页与边界

单版窗口没有把早期输入沉默地消失：

| 窗口 | 早期读 | 收件 | other | 预览/剩余 | 下一步 |
| --- | ---: | ---: | ---: | --- | --- |
| Member@v12 until13670 | 68 | 1 | 41 | 8 / 60 | `agent(id, v=11, reads=True)` |
| C4@v249 until2400 | 87 | 185 | 1456 | 8 / 79 | `agent(id, v=248, reads=True)` |

这些是已记录动作/读取索引，不认证内容已全部交付或与本缺陷相关。两条展开提示都明确“不继承本次 until”，不是把扩大的查询范围冒充截止前已读。两窗口各延后1个写效应、没有延后读；全部统计都是本次样本，不是全局不存在证明。

已核对的显式分页提示：

- Member action 默认正文预算20,000，但整条返回20,850字符：参数预算针对正文，额外头部/定位不计入预算，不能将 `max_chars` 当整个返回长度硬上限。
- Member action 输入格式化后44,250字符：默认首19,780字并提示“剩余24470字，offset=19780继续”；单独 input 的前两页是1–1200、1201–2400，给出后续 offset。未选择的输出明确“未展开;part=output查看”。
- Member file 默认候选160条未展开，给出 `m_n=40,m_from=1`；所选 action 另有64条候选未展开，同样提供入口。候选计数不等于读写/修复确认。

两项待后续源版本修正（本次没有修改冻结源）：

1. 早期输入 preview 没带 `full/start/n`，`_read_tags` 因缺字段显示“范围未知”。例如 Member `F010-member-pay.md@v2`，原记录的 proof.snapshot=full，却在早期索引得到“范围未知”。应区分“索引未披露范围”与“原始读取范围未知”，或透传已知范围字段。
2. C4 action 的格式化输入只有357字符，请求 `offset=1200` 得到空页，却显示“第358–357字/共357字”，没有明确 EOF/越界提示。没有捏造正文，但分页区间标签不正确。

这些发现不说明调查模型会如何理解，也不直接评价本轮调查结论。真实模型收到的文本与截断仍须另查其原始运行轨迹。

