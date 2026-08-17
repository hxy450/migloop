# MigLoop 开发与架构指南

把一次 Android → HarmonyOS 迁移会话回放成两张血缘图,用来回答:

> **生成 Spec 时,最终有哪些源码行进入了 agent 上下文?去重之后看到了多少?**

离线只读:不改工作流、不装钩子、不联网,拿到会话记录才开始工作,对正在跑的任务零影响。

---

## 项目分层

```text
src/migloop/
├── adapters/       # 来源专属：发现、识别、解析并归一化 session
│   ├── base.py     # SourceAdapter / SessionCandidate 契约
│   ├── claude.py
│   └── codex.py
├── render/         # 来源无关：静态报告、compare、HTML templates
├── live/           # 增量 cursor、checkpoint、本地 HTTP server
├── chat/           # 页面分析助手 provider
├── cli.py          # 命令行编排，只通过 adapter registry 接触来源
└── __main__.py     # python -m migloop
tests/              # 与运行时代码分离的回归测试
scripts/            # 开发工具和 pyz 打包
docs/               # 设计与维护文档
dist/               # 可直接分发的单文件 pyz
```

### Adapter 契约

新来源只负责四件事：`default_root()`、`is_session(path)`、`iter_sessions(root)` 和
`extract(path)`。`extract()` 必须返回统一的 `meta / totals / stages / tools / agents /
prompts / billing / lineage / workflows` trace。实现完成后在
`src/migloop/adapters/__init__.py` 的 `ADAPTERS` 注册即可；render、compare 和静态页面无需修改。

实时模式还需要该来源自己的增量 reducer，因此通过 `SUPPORTS_LIVE` 单独声明，不能把“能离线解析”
误当成“能安全增量续读”。

---

## 运行

**单文件版**(推荐,零第三方依赖,Python ≥ 3.9)

```bash
py migloop-lineage.pyz <Claude或Codex会话.jsonl> -o 输出.html
```

mac / Linux 换成:

```bash
python3 migloop-lineage.pyz <会话.jsonl> -o 输出.html
```

> 请显式用 `py` / `python3` 调用,不要给 pyz 加执行权限直接跑。

**源码版**（要改代码时用）

```bash
python -m pip install -e .
migloop <会话.jsonl> -o 输出.html
python scripts/build_viewer.py trace.json --out 输出.html
python -m unittest discover -s tests -t . -p "test_*.py"
python scripts/build_pyz.py
```

产出是**自包含单文件 HTML**:数据与字体全部内嵌,无外部资源与网络请求,双击即看,断网可用,可直接转发。

### Live：增量查看正在运行的会话

```bash
py migloop-lineage.pyz <session-id或项目名> --live --open
```

Live 页面默认启用本机 Codex CLI 作为只读“Agent 分析”助手。完整 session 是事实源，血缘图只是
导航索引；需要具体证据时会追查主线程与子 Agent transcript。模型调用与页面解耦，可通过
`--chat-provider anthropic|openai-compatible|off`、`--chat-model`、`--chat-base-url` 和
`--chat-api-key-env` 切换，不会把 API key 写入 HTML。

Live 模式不是定时从头重跑 extractor。它为主会话和每个子 agent transcript 分别保存 byte cursor，
只解析上次 offset 之后新追加的完整 JSONL 行；末尾尚未写完的半行保留到下一次拼接。Workflow JSON
体积很小且采用覆盖写，只有 mtime 变化时才整份重读。Android 源码分母首次扫描后也进入 checkpoint，
不会随每次刷新重复遍历仓库。

浏览器连接本机 `127.0.0.1` 服务，默认首页复用完整离线 viewer。右下角 live 控件每 10 秒请求
小型聚合状态，ETag 未变化时返回 `304`；有新增时提示快照过期，只有用户点击“刷新完整分析”才
重建全部图。控件显示快照版本、记录数和生成时间，并提供自包含 HTML 下载；`/status.html` 是
可选的轻量状态页。按 `Ctrl+C` 停止时也会做一次最终全量校验并生成可分享的静态页面。

对 Workflow 会话，`wf:<workflowName>` 直接作为阶段边界。血缘不再把所有 Workflow 合并成一张图，
而是每阶段分列展示输入 Spec、输入 Android 源码、参与 Agent、输出 Spec 和输出工程文件；Workflow
常用的 `.migration/analysis/*.md` 与 canonical `spec/` 使用同一条确定性读写边口径。

```bash
--interval 5            # 文件变化和页面刷新间隔，默认 10 秒
--port 8765             # 默认 0，自动选择空闲端口
--cache-dir <dir>       # 默认 ~/.migloop/cache
--reset-live-cache      # 忽略 checkpoint，从头重放
--no-final              # 停止时不生成最终静态页面
```

复杂度：冷启动一次为 `O(已有记录)`；随后每次为 `O(新增字节 + 新增事件)`，而不是
`O(当前 session 总大小)`。checkpoint 使进程重启后也无需重读历史。若文件缩短或头部签名变化，
工具会认为 transcript 被替换，自动执行一次确定性重放。

---

## 输入:会话文件在哪

```
~/.claude/projects/<工程名转义>/<session-id>.jsonl
~/.claude/projects/<工程名转义>/<session-id>/subagents/                    ← 必须存在
~/.claude/projects/<工程名转义>/<session-id>/subagents/workflows/<runId>/  ← workflow 模式
~/.claude/projects/<工程名转义>/<session-id>/workflows/wf_<runId>.json     ← workflow 编排元数据
```

**子代理目录不能缺**。缺了它只能看到"派了个任务",无法还原每个 agent 读了什么、写了什么,
血缘图会是空的。转发会话给别人分析时,这几部分要一起打包。

### 两种派发形态都支持

| | Task 派发(管线) | Workflow 派发 |
| --- | --- | --- |
| transcript | `subagents/agent-*.jsonl` | `subagents/workflows/<runId>/agent-*.jsonl` |
| 阶段来源 | 管线 skill 边界(a2h-spec / a2h-execute…) | 每次 `Workflow` 调用一段,名字取脚本 `meta.name` |
| agent 身份 | meta 里的 description | 编排里的 `label`(如 `audit:template`)+ phase |
| 收尾判定 | transcript 是否正常收尾 | 编排状态 `state`(权威) |

Codex 离线报告使用 `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`。主线程与子 Agent 是独立
rollout，通过 `parent_thread_id` 回链；当前支持静态 HTML 与跨 session 对比，暂不支持 `--live`。

> Workflow 子代理的 transcript **不写 `toolUseResult`**,读取行数从结果正文的 `N⇥内容`
> 行号前缀还原;末条记录是 tool_result 而非 assistant,所以收尾**必须**看编排状态——
> 按 transcript 启发式判会把整批正常完成的 agent 误判成中断。

---

## 第 06 节「阶段明细」的首图 = 全程总览

阶段一多,一段一张卡就得来回翻。这一节最上面先给一张**所有阶段压在同一条时间轴**的总览:
阶段用底色带标出边界,主线工具流与子代理甘特按全程绝对时间对位,泳道跨阶段统一分配 ——
跨阶段的并行、空档、返工在一屏里直接可见。往下才是按阶段放大。

**时间轴会压缩空档。** 直接按墙钟画,一个跨夜等待就能吃掉七成宽度(实测某会话 15h 挂起
把其余阶段压成看不见的细条)。所以「整段没有任何活动」的空隙每个只给固定一小格并打上斜纹,
悬停显示真实时长;其余时间严格等比,阶段内的节奏与并行关系不失真。

> 阶段边界由**记录下标**定义,而主线 jsonl 的时间戳并非严格按下标递增(并行子代理的完成
> 通知会乱序落盘)。所以阶段起止取区间内的最早/最晚时间,色带再按下一段起点截断,
> 避免画出「两个阶段同时进行」的假象。

---

## 输出:看第 07 节「数据血缘」

这一节按阶段边界拆成**两张图**(spec 阶段结束前 = 图 A,其余 = 图 B)。
没有名为 spec 的阶段时(通用会话 / workflow 模式)退回通用规则:**在第一个有子代理产出
`.ets` 的阶段处切开**,前面是上游(读源码、出结论),后面是下游(写鸿蒙码)。
判据只看子代理——主会话横跨全程,理解阶段就在搭工程脚手架,拿它定边界会把上游整段吞掉。

**图 A · Spec 阶段**
```
Android 源码  →  产 Spec 的 Agent  →  Spec 文件 + 其它产物
```

**图 B · Execute 阶段**
```
Spec 契约 + Android 源码  →  产码 Agent  →  .ets + 资源 + 配置
```

交互:**单击**任意节点高亮整条血缘链,**双击**开详情抽屉,**悬停**看摘要。
连线含义:**紫线 = 读 Android**、**蓝线 = 读 Spec**、**橙线 = 产出**。

### 每张图上方的「视野条」

| 指标 | 含义 |
| --- | --- |
| **视野** | 这一阶段打开过多少个源文件,占全工程多少 |
| **去重读取** | 真正被看过的代码行数——同一段代码被多个 agent 读、或分页重读,**只算一次**(区间并集) |
| **└ 仅逻辑代码** | 同上,但分子分母同时收紧到 `.kt/.java/.kts`,剔除布局 xml 与 gradle 脚本 |
| **读取深度** | 已打开的那些文件读了多深——读完整份,还是只扫了几行 |
| **重复阅读** | 累计读取 − 去重,即并行 worker 重复读同一批代码的量 |
| **参与 agent** | 这一阶段有多少 agent 实际读了源码 |

### “看到源码行”的统一口径

工具不再只统计显式 `Read`，而是记录**最终 tool_result 中真实出现的源码行**：

- `Read`：使用工具返回的精确起始行和行数；
- `Grep`：只记录实际返回的命中行和上下文行，不把整个文件算作已读；
- `Bash` / `PowerShell`：将最终输出与命令中明确引用的源码文件逐行核对；
- `cat file | grep x` 只记录最终 grep 输出，`cat file > tmp` 不产生可见源码行；
- `find`、`ls`、`grep -l/-c/-q` 等只给路径或计数的命令，不产生可见源码行。

机器 trace 在每个 lineage agent 下额外输出 `android_visible_lines`：

```json
{
  "path": "app/src/main/java/example/Foo.java",
  "spans": [[12, 30], [88, 88]],
  "lines": 20,
  "via": ["Read", "Bash"]
}
```

`android_reads` 保留用于旧版页面和消费者兼容，其文件集合由上述可见行反推。

### 源文件列:亮 = 本阶段读过,暗 = 没读

Android 源码列画的是**全工程所有源文件**,不只是被读过的那些:

| 状态 | 呈现 |
| --- | --- |
| 本阶段读过 | 正常高亮,右侧显示读它的 agent 数 |
| 本阶段没读 | 压暗 + 斜体,悬停显示「本阶段无人读取 · N 行」 |

分组标题是 `模块 (读过/总数)`,可以直接看出哪个模块整片是暗的。

这样画有三个用处:两个会话的**分母一致**,能横向比;**盲区可见**,全程无人读过的文件不会从图上消失;
还能看到**"上游读过、下游没读"**——同一个文件在图 A 亮、图 B 暗,就是信息断在交接处的直接画面。

---

## 怎么读这些数

**去重读取 ≠ 累计读取。** 并行 worker 常常各自打开同一批文件,累计值会把同一段代码算很多遍。
去重值(区间并集)才是"这一阶段真正看过多少代码",两者的差就是重复阅读量。

**覆盖率低,要先看读取深度再下结论。** 读取深度高(接近 100%)说明打开的文件基本整份读完,
那么覆盖不足的原因是**没打开的文件太多**;读取深度低则说明是**读得浅**。两者的改进方向不同。

**优先看「仅逻辑代码」那一行。** 布局 xml 与 gradle 脚本的阅读成本远低于逻辑代码,
混在一起会高估理解深度。不同工程的非代码文件占比差别很大,两套口径给出的结论有时会相反。

**跨阶段比较时注意分母。** 两张图的分母是同一个全工程清单,所以图 A 与图 B 的覆盖率可以直接比;
但**不要把两个阶段的去重量相加**——它们共读的部分会被重复计一遍(工具内部已按并集处理)。

---

## 覆盖率的分母从哪来

百分比需要"这个工程一共多少文件 / 多少行"这个分母,会话记录里没有,工具按以下顺序取:

1. 从读取路径反推 gradle 工程根(向上找 `settings.gradle` / `gradlew`)
2. 该目录若在本机存在,自动扫描一遍(只算 `src/main`,排除 build / test / spec)
3. 工程不在本机 → 只显示绝对值,不显示百分比,**不会报错**

agent 有时会读到清单之外的文件(`build/` 产物、`test/`、`.idea/`、根级 gradle)。
这些文件照常画进图,但**不进覆盖率分子**——分子含分母没有的项会让百分比穿过 100%。
覆盖率用 `android_files_in_scope` / `lines_android_dedup_in_scope`,
清单外的量单独记在 `android_files_oos`。

> 注意:本机这份源码可能与当时跑迁移的版本不完全一致,所以覆盖率是近似值。

---

## 统计口径

- **阶段划分**按管线自己的阶段边界,不靠"看它写了什么"来猜——spec 阶段里有 agent
  只做分析、审计,不落任何文件;execute 阶段的收尾 agent 也会补写 handoff 之类的 spec。
- **每个阶段 agent 的全部产出都算**,不按目录预筛(构建脚本、状态文件等一并计入)。
- **`spec/` 目录下的文件全算**,不只 page / feature / base 这些标准类型。
- **主线按阶段拆开**统计——主线横跨全程,合成单个节点会让按阶段的筛选整块丢掉它的读写。
- **白跑的分身会被剔除**:判据是会话记录是否正常收尾,而**不是**"有没有写文件"。
  审计 / 检测类 agent 本来就只把结论作为返回值交给主线,不落盘也是有效产出;
  被中断或 API 断连**且**零产出的才排除,因为它们随后会重发一次,留着就是把同一份工作重复计数。

---

## 注意

页面内含完整轨迹:工程路径、用户输入原文、命令摘要、成本数字。团队内分享无碍,
对外发送前请先确认内容是否合适。
