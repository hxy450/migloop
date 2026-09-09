# 文件事实契约审查：操作、执行、观测与版本绑定分离

基线：main `6ffb74c`。本提案在修改生产代码之前完成；审查只读源码，使用内存合成 FileOp→Ev→FileRef→ledger→verdict 回归，没有执行示例里的历史命令、调用模型或修改冻结实验/参考。按 GitNexus 调试技能回溯调用链；仓库没有索引，直接查源码。

结论：最重要的三个问题不是缺少某个命令关键字，而是事实入账缺少分层契约。`via=script` 同时承载 AST 识别和纯词法猜测；`conditional=False` 的默认值被当成已执行；`certain=True` 只证明版本就近绑定，却被当成正文读取事实。错误可一路升级成正式版本、作者和 true 关系。

## 1. 词法提及被升成操作；改成 touched 也仍会污染状态

### 已复现

把以下 Bash 请求与合成成功 stdout `Example.ets\n` 传给 `_file_ops`，cwd 为 `/proj`：

```sh
python3 - <<'PY'
def write_text(): pass
write_text()
print('Example.ets')
PY
```

返回 `FileOp(op='write', path='/proj/Example.ets', via='script', content=None, conditional=False)`。建账得到 agent v1 和 `Example.ets@v1(source=opaque, by=agent-test)`；`verdict._rel_write` 返回 true。该例没有文件写语法，方向完全来自小脚本的全文倾向。

另一分支同样重要：仅 `print('Example.ets')` 不含写关键词时，detail 变成 `unresolved='脚本黑盒', touched=['/proj/Example.ets']`。在真实 `Write('seed\n')` 与 `Edit('seed'→'new')` 之间插入此调用，后续 Edit 的 content 从可恢复的 `new\n` 变成 None。原因是所有 touched 都被投入 candidate 写屏障。纯路径提及不是可能改写该路径的证据；不能只把 `_literal_ops` 的读写全部改名为 touched。

### 来源与丢失点

- `atoms_collect.py:667–710` `_literal_ops`：紧邻模式识别和全文倾向都产出相同 FileOp；`_TENDENCY_MAX_LITERALS` 只是阈值，不是事实证明。
- `atoms_collect.py:1045–1050,1064–1071,1094–1101`：AST 与字面量操作直接合并，只按路径排重，未保存各自产生规则/证明级别。
- `atoms_collect.py:1377–1400` `_kind_of/_to_ev`：任何 write/edit 路径升为写动作和 wopaque/wfull；没有 admission 门禁。
- `atoms.py:377–390`：conditional 与 touched 合并为 candidate；`filestory.py:282–287` 无条件清除已知状态。
- `verdict.py:453–460`：作者及版本吻合即 true，不再知道最初只是词法方向猜测。

### 最小边界

`_literal_ops` 仅给 mentions/probes，永不直接产正式 FileOp。只提到路径、列目录、存在性探测不增加 agent 版本、不清除文件状态。只有可指出写/删语法或真实不透明执行写能力及目标线索的 unknown effect 才进入 effect_candidates；保留每条来源和原文导航。动态 mask 脚本含真实写语法、stdout 点名目标时仍须保留待核候选，不能与纯 print 混同。

## 2. 语法识别不等于到达执行；字面内容不等于执行后快照

### 已复现

以下 Python heredoc 的合成成功 stdout 为 `ok\n`：

```python
print('ok')
raise SystemExit(0)
open('Example.ets', 'w').write('bad')
```

解析仍得到 `write/content='bad'/conditional=False`，随后建成 full v1，作者关系 true。与问题 1 不同，这里确有文件写语法，但该语句不可达，不能由整个进程成功来认证它执行过。即使不求值 SystemExit，正确下界也是“此执行域不支持，后续效应未知”，不是确定写。

### 来源与丢失点

- `atoms_collect.py:463–605` `_py_script_ops` 逐个处理 top-level stmt，遇不支持的语句通常直接不产操作，但继续处理后续语句。它没有 supported/unsupported execution 域。
- `atoms_collect.py:606–635` `_replace_helpers` 用函数里“存在读/写/replace”判帮助函数，未证明三者的数据流、到达性和被调用对象身份。
- `atoms_collect.py:946–965,1100–1111` 的 conditional 防护针对 shell 分段；Python 内部控制流与名字 shadow 不进入此状态。
- `atoms_collect.py:1389–1400` 只要写带字符串 content 就成为 wfull；`filestory.py:230–253` 直接产生带作者的状态快照。

### 最小边界

不实现全 Python 解释器。为已支持的 straight-line 语法维护有限执行域：受支持的字面量赋值、明确的标准 open/Path 读写、可靠 replace 模式可保留；不支持的控制流、未知调用、被 shadow 的 open/Path 或不能认证的数据流使相关操作退为候选。`raise` 等不应被当成“忽略这行，后续仍必然执行”。未知/失败也不等于未执行，已确认前段操作与后段未知应分开。

同时保留三个互不蕴含的判断：识别出 write 语法、确认它执行、知道写后整个文件内容。不透明但已确认的写允许有真实作者而 snapshot unknown；未确认执行的字面写内容只能是 proposed payload，不能成为文件状态。不要因无法恢复快照就否认有充分记录支持的实际执行。

## 3. `certain` 的版本意义被误当成正文读取事实

### 已复现

先有真实 `Example.ets@v1='seed\n'`，再传入仅输出 `True\n` 的脚本：

```python
from pathlib import Path
print(Path('Example.ets').exists())
```

后面安排一个真实效应 v2，使该探测处于有效喂养窗口。结果为 `FileOp(read, via=script, dep=False, content=None, seen=None, full=False)`；因为文件状态已知，ReadRec/FileRef.certain=True，`_rel_read` 返回 true“读到 v1，喂 v2”。实际只观测到存在性，正文没有进入上下文。

### 来源与丢失点

- `atoms_collect.py:691–695` 将 `.exists/.is_file/.iterdir/.glob/.open` 与内容读放进同一 read 分支；FileOp.dep 默认 False。
- `filestory.py:361,430–446` 在已有状态上，无正文/无 seen 的 read 也可 certain=True。这个布尔只回答绑定哪版，不证明 read 识别可靠或正文返回。
- `atoms.py:46–52,393–431` FileRef 的 certain 由 ReadRec 回填；缺条目时还默认 True，无法说明哪层没有检查。
- `verdict.py:462–480` 只组合 certain、dep、observation_uncertain；没有内容观测种类和操作/执行依据。

### 最小边界

保留 `certain` 的兼容意义“版本绑定确定”，新增明确的 operation/execution/delivery proof。exists/stat/glob 等归 metadata probe，不是内容 read；文件名清单或依赖读不证明正文可见。关系 true 必须同时满足实际内容读取/返回和精确版本绑定，不能从全池已有快照逆推模型读过。真实 Read 的局部返回也可证明所示范围，无须一律要求全文；空文件全文返回与未知/未返回须分开。

## 最小统一数据流接口

保留两类原子，不新增第三种图节点。以下是内部证据载体，不允许模型自设 proof：

```text
ScriptAnalysis
  ops: list[FileOp]                  # 原生工具/语法建立了方向与目标
  effect_candidates: list[Candidate] # 有可能效应的具体依据，执行或目标待核
  mentions: list[Mention]            # 纯词法，不是操作，不是状态屏障
  probes: list[Probe]                # 存在性/元数据，可导航原文
  unsupported: list[SpanReason]      # 不支持的执行域及原因

FileOp.proof / Ev.proof / FileRef.proof / Version.proof
  operation_basis: native_tool | supported_shell | supported_python | legacy
  execution: confirmed | unknown | not_executed
  delivery: content | dependency | metadata | none | unknown
  rule: str                         # 哪条受支持规则建立了这个判断
  source_span / input_ref / output_ref  # 对应真实事件字段，不猜 locator

版本绑定（与 proof 分开）
  v: int | None
  binding: exact | nearest | ambiguous | none
  certain: bool                     # 兼容别名，仅表示 binding=exact
  observation_uncertain: bool       # 读写采集窗口冲突，不能被其他字段覆盖

快照（与 execution 分开）
  snapshot: full | partial | unknown
  snapshot_basis: returned_content | confirmed_write | derived | none
  proposed_payload                  # 未确认执行时不能当成 snapshot
```

具体模块边界：

1. `_literal_ops` 改为纯线索扫描；`_py_script_ops` 返回 ScriptAnalysis 和局部执行域。只做有限支持集；超出支持集有明确原因并保留原文，不叠名字关键字补丁。已有可靠 straight-line 能力不能一刀切全部退化。
2. `_shell_analyze` 组合各分析结果，不再把 ops、touched、probed 混成一种“碰过”。相同目标的多个依据可以合并，但不得靠另一条较强依据把所有分支都认证。未知 runner 的可写能力与对应目标依据分开记录。
3. `_file_ops` 作为唯一 admission：confirmed 写/删才进入正式 Ev；unknown effect 进入候选写屏障；纯 mention/probe 不进入屏障。原生失败写保留候选，不能当没有效应。CC/Codex 共用，不各自猜一次。
4. `_to_ev` / `build_stories` / `build_ledger` 只透传和消费上述类别，不再补造操作可信度。所有会影响事实的 proof 字段参与 ledger identity；启用新 admission 时更新事实 epoch，旧冻结 run 按旧身份保留，不以新图偷偷绑定旧报告。
5. `_rel_write` 只在真实写依据和精确作者版本下 true，允许内容 unknown；unknown effect 返回 unknown/candidate。`_rel_read` 另核 delivery/content 和 binding，metadata/dep 不升级正文读取。返回 note 和来源依据，不只一个无上下文布尔。

新字段缺失表示 legacy/unverified，不能默认为已核；内部合成 Ev 和已有适配器需明确迁移其既有断言强度。`via` 继续保留传输/识别来源标签，不复用成所有轴的总分。身份绑定也只认证坐标所属账本，不认证模型因果主张。

## 实施顺序与验收

第一阶段只覆盖本提案边界：先用三条核心反例及纯 print 不毒化 Edit 做 collector→ledger→verdict 红测；再落实 admission/proof，补 CC/Codex 同源回归。候选可经原始事件引用/action 找回，不为了清除红边删除原文或搜索提及。

必须保留的阳性/边界对照：

- 原生成功 Read/Write/Edit 和可靠 straight-line AST：操作、作者、已知内容能力保留。
- 同一个有效路径分别作为纯字符串、probe、依赖读、正文读、已确认写、未知执行写；各层 payload 与关系用相同解释。
- 原生失败/未完成/条件效应仍为候选，候选可打断状态；纯提及不能打断。
- 真实写内容未知与未执行写的字面内容不同：前者可有作者，后者不能立正式状态。
- 写前/写后读取窗口、并发 overlap、created 与真实正文冲突、derived/concat 源状态未知等现有防护不回归。
- 所有来源保留真实 action/event ID、字段与分页入口；接口不宣称已穷尽文件修改、全部 Python 语义或模型私有思考。

不在第一阶段做：通用 Python 控制流模拟、任意函数执行、修复全部 shell 长尾、设备/模型试验、旧报告重写，以及由候选记录直接自动认定作者或修复事实。

## 第一阶段落地记录（2026-09-09，工作树，未进入既有冻结实验）

上述接口是审查时的建议；本阶段实际最小字段如下，未实现的建议字段不应当成已有输出：

- `FileProof(operation_basis, execution, delivery, snapshot, rule)` 定义于 `evidence.py`。FileOp → Ev → Version/ReadRec 透传；FileRef 的 proof 直接来自 Ev，file/agent/action 共用 `proof_payload` / `file_ref_payload`，没有另一套确定性推断。
- `operation_basis` 当前为 `native_tool / supported_shell / supported_python / output_locator / legacy`；admission 只有前三类且调用成功、操作非条件候选时才标 execution=confirmed。其余为 unknown。`snapshot` 说明该操作提供了全文、局部还是未知，不自动等同后来由其他观测封存的 `Version.content`；`content_known` 仍须独立判断。
- `ScriptAnalysis` 的 ops/effect_candidates/mentions/probes/unsupported 分开。路径线索不生版本或作者；纯 mention/probe 不进入候选写屏障。未确认写进入 `effect_candidates`（兼容别名 touched/conditional），未确认读进入 `read_candidates`，保留 path/seen/proof；所有源事件仍保留 action 原文引用。当前候选目标数组不是新的正式 FileOp，也不是每个脚本语句的完整源映射。
- `certain` 仍只表示版本绑定；缺绑定记录默认 false。共享 `read_basis` 依次区分 overlapping_read、dependency_read、uncertain_version、unverified_read、read；true 正文读须同时有受支持执行、content delivery、非依赖及无观测重叠。write 作者关系可 true 且内容 unknown，但旧无 proof 记录不默认为已核。
- epoch 改为 `atoms-2026-09-09-file-evidence5`；proof 进入 ref/version 身份摘要，新 evidence 模块进入 builder 指纹。新旧事实合同不偷换绑定；冻结 source/run/reference 均未改。

有限语法域的明确范围：

- 保留单名字字面量赋值、已知路径标准 open/io.open/codecs.open、Path.write_text / Path.open、单个 with 句柄写、规整同文件 read→replace→write 和严格完整模板 helper。赋值/定义统一清除旧 const/read_path/edits/dirty/path/helper 能力，先保存 RHS 的有限抽象值，再替换 LHS。后续重新 read 不携带另一文件的 edits；helper 被赋值或重定义即失效。
- 任意用户函数、未知接收者、控制流/异常、动态别名、装饰器/默认值、推导式、解包/链式/属性赋值等不做通用语义求值。遇未支持语句后不再将其后的语法操作认证为执行事实；可定位效应保留候选，其余保留提及/原文。仅支持无别名标准模块 import 和 `from pathlib import Path`。
- append/r+ 等非截断模式、同句柄多次 write、replace 次数不是缺省全替换或明确 1：保留已确认写操作，但不伪造全文或单次替换快照。尚不做任意累积写、运行时容器、动态路径、复杂 helper 解释。
- shell 的 `||`、`;`、换行复合、管道或未知控制结构，即使整体成功也不能证明各子段成功；相关操作退候选。成功的简单纯 `&&` 链保留确认。目录/行号 stdout 作为定位及所示内容线索保留，不因打印出路径就证实历史读取。原生 Read 无 sidecar 的跳号/截断返回保留 seen，不能把删去的行拼成全文。

验收覆盖新增 60 个合成用例（CC/Codex 同源），包括最初三例、纯 print 不毒化 Edit、append/r+/多写/count、重读 lineage、helper 重绑定、Path.open、解包/链式赋值、复合 shell 成功掩盖、Read 跳号、缺绑定默认未知、epoch/proof 和阳性 straight-line / 纯 && 对照。代码只解析合成命令，从未执行这些命令。独立交叉审查重放六族反例已确认不再造假事实。

可观察的召回代价不隐藏：父线程的真实池只读 dry-run 中，C4 LaunchAgreementDialog 从旧正文读生成的前版退化为候选观测，现仅保留一个内容未知的实际 patch 版本；对应 JS for-of + nl/sed 的正文仍可在 read_candidates/action 原文找到，但本阶段不解释该 JS 执行域来造前版。Member dry-run 也改变版本/读/候选数量。它们是事实合同变化，不是模型准确率或性能收益实验；下一轮调查需绑定新账本，不用旧版本号硬套。
