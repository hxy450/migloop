# MigLoop Trace Viewer (PoC)

把 Claude Code / Codex / DevEco 迁移会话的记录一键变成可交互的轨迹页面:
执行拓扑 / Git 式执行流(主干=主会话,分支=子代理)/ 主线上下文占用曲线 / 阶段对比 / 阶段明细 + 点击详情抽屉 /
风险点审计 / 数据血缘 / **返修链路**(哪个文件被谁修了、被修的行是谁写的、当时读了什么)。

## 文档

- [MigLoop 设计说明](./docs/design.md)：目标、证据口径、数据结构和实现方式
- [开发与架构指南](./docs/development.md)：目录分层、adapter 契约、测试和扩展方式
- [MigLoop 与 CANNBot-Insight 对比](./docs/comparison-cannbot.md)：定位、能力、优缺点与演进建议
- [返修链路调查:我们在做什么、为什么、做到了哪一步](./docs/fixchain-research.md):目的、两原子账本与 MCP 工具、数据在哪、实验与结论、决策日志、下一步(2026-09-06 起工具主干在本仓 dev/fixchain)
- [实验产物](./docs/experiments/README.md):prompt、报告、盲评、覆盖对账、harness 脚本

## 使用(推荐:单文件 `dist/migloop-lineage.pyz`)

**要求**:Python ≥ 3.9,无任何第三方依赖。Windows / macOS / Linux 通用。

```bash
# Windows
py migloop-lineage.pyz                 # 列出本机最近的 session
py migloop-lineage.pyz f3bb027a        # 按 session-id 前缀生成
py migloop-lineage.pyz arch9 --open    # 按项目名片段生成并在浏览器打开
py migloop-lineage.pyz 01a0048b        # Codex session-id 前缀同样可用

# macOS / Linux
python3 migloop-lineage.pyz <目标> [-o out.html] [--open]
```

`<目标>` 三种写法任选:
1. `.jsonl` 文件完整路径(拿到别人分享的文件时用这个)
2. session-id 前缀(自动在 `~/.claude/projects` 与 `~/.codex/sessions` 下查找)
3. 项目目录名片段(取该项目最新 session)

输出为**完全自包含**的 HTML(字体、数据全部内嵌),可以直接发给任何人用浏览器打开,不需要网络。

### 实时查看仍在运行的 session

```bash
py migloop-lineage.pyz dynamic1 --live --open
```

`--live` 当前用于 Claude Code session，启动仅监听 `127.0.0.1` 的本地页面。主会话与每个子 agent 的 JSONL 都按 byte offset
增量续读；没有新记录时不会重新解析历史内容。默认首页就是完整分析页面，右下角 live 控件每
10 秒读取一次小型聚合状态。发现新记录时只提示“分析快照已过期”，不会在后台反复重算全部图；
右下角会明确显示快照版本、记录数和生成时间；点击“刷新完整分析”才执行一次一致性重建，点击
“导出 HTML”会下载当前一致性分析的自包含页面。轻量状态页保留在 `/status.html`。按 `Ctrl+C` 停止后
还会用离线提取器做一次最终一致性校验，并写出 `-o` 指定的自包含 HTML。

Workflow 会话按每次 Workflow 调用形成确定性阶段。血缘区逐阶段展示：
`读 Spec / 分析文档 + 读 Android 源码 → Agent → 产 Spec / 分析文档 + 产鸿蒙代码 / 资源 / 配置`。
Canonical `spec/` 与 Workflow 常用的 `.migration/analysis/` 都会作为契约文档进入血缘。

实时页右下角的“Agent 分析”可以围绕完整 session 连续提问。主线程 JSONL、subagents 和 Workflow
记录是事实源，血缘摘要只是定位索引：Codex 以只读方式按需追查原始记录；HTTP provider 由服务端
在完整记录中检索相关原始片段。浏览器只发送对话文本，API key 不会进入 HTML。默认调用本机已登录的 Codex CLI：

```bash
py migloop-lineage.pyz dynamic1 --live --open                         # Codex 默认模型
py migloop-lineage.pyz dynamic1 --live --chat-model <model>          # 指定 Codex 模型
py migloop-lineage.pyz dynamic1 --live --chat-provider anthropic \
  --chat-model <model>                                                # 读取 ANTHROPIC_API_KEY
py migloop-lineage.pyz dynamic1 --live --chat-provider openai-compatible \
  --chat-model <model> --chat-base-url http://localhost:1234/v1      # 本地/兼容 API
py migloop-lineage.pyz dynamic1 --live --chat-provider off           # 关闭分析助手
```

Anthropic/OpenAI-compatible 可用 `--chat-api-key-env <环境变量名>` 改 key 来源。聊天是 live server
能力；导出的自包含 HTML 仍然是纯静态报告，不包含凭据或模型调用。

常用参数：

```bash
--interval 5            # 文件变化和页面刷新间隔；默认 10 秒
--port 8765             # 固定本地端口；默认自动选空闲端口
--reset-live-cache      # 丢弃 checkpoint，从头重放一次
--no-final              # 停止时不生成最终静态页面
```

增量 checkpoint 默认保存在 `~/.migloop/cache/<session-id>.live.json`。MigLoop 重启后会从保存的
offset 继续；若检测到 transcript 被截断或替换，则自动丢弃旧聚合状态并重放。

## Codex session

Codex 主线程与子 Agent 分别落在按日期分区的 rollout 文件中：

```
~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
```

给出主 rollout 的完整路径、session-id 前缀或项目目录名即可。MigLoop 会根据
`session_meta.source.subagent.thread_spawn.parent_thread_id` 递归回链同一 session 的子 Agent，
并把 `response_item` / `event_msg`、`function_call` / `custom_tool_call`、token 用量和
`functions.exec` 内的 `shell_command` / `apply_patch` 归一到现有 trace。Codex 目前支持离线 HTML
和 `--compare`；增量 `--live` reducer 仍只支持 Claude Code。

## 返修链路(`--serve`)

报告页「02 风险点」里有一张**返修追溯**卡:哪些鸿蒙文件在 execute 之后被改过、谁生成的、谁修的、
修了哪些行、被修行的原作者是谁。它从**两原子账本**算出来:

- **版本文件**:每个文件的写者脊柱,每一版记(写者 agent、它的版本号、来路、diff、内容)
- **版本 agent**:每个 agent 的每个对外效应(写 / 删 / 派发 / 发消息)+1 版;读等输入归到它喂养的下一版

修复方的判定只有一处(`filestory.build_fix_chains`):按逐笔版本的**阶段**(a2h-execute 之后的写 = 修复,
主会话在 verify 阶段亲手改的也算);没有阶段戳的旧记录退回血缘层的 agent 级判定。跨会话同一工程的前序
会话会并进同一本账,前序轮回合内的返修也在链里。

导出的自包含 HTML 只带这张卡;要点进链页、逐行 blame、展开某一次工具调用的原文,起本机服务:

```bash
py migloop-lineage.pyz <目标> --serve --open     # 报告页 + 返修链路页 + 两原子端点
```

端点全部 GET,与 hmigbot 同名:`/api/insight1/report/<sid>`、`/api/insight1/fixchain/<sid>`、
`/api/insight1/fixchain-data/<sid>`、`/api/insight1/atom/<sid>/text/<tool>`(`guide` / `sessions` /
`index` / `file` / `agent` / `blame` / `diff` / `action`,纯文本,给调查 agent 用,先读 `guide`)。
目前支持 Claude Code 与 Codex 会话;DevEco 会话只有报告页。

### 让 agent 做返修归因

[`docs/skills/migloop-investigate/SKILL.md`](./docs/skills/migloop-investigate/SKILL.md) 是给 Claude Code /
Codex 的调查技能:从修复 diff 出发逐行溯源到写者 agent 的输入(派发词、读过的 spec 与源码及其版本),
定性(spec 写错 / 读了旧版 / 漏读 / 转换错 …)并给带 `path@v` 引用的证据。两条接法:

- HTTP:起 `--serve`,把技能里的 `BASE` 换成启动时打印的地址
- MCP:`claude mcp add migloop -- python -m migloop.mcp_server`(需要 `pip install mcp`;`sid` 给会话 id 前缀或 jsonl 路径)

## 跨机器分享 session

Claude Code 的一个 session 由两部分组成,分享时要一起拷:

```
~/.claude/projects/<项目>/<session-id>.jsonl      ← 主会话
~/.claude/projects/<项目>/<session-id>/subagents/ ← 子代理 transcript(缺了泳道为空)
```

对方拿到后:`py migloop-lineage.pyz 路径/到/<session-id>.jsonl`。

## 开发

上游是 [migbot-server](https://github.com/hxy450/migbot-server) 的 `src/vendor/migloop`(2026-09 起以 server 为准),
本仓同步 adapters / audit / 两原子 / 模板,并加上自己的 cli / live / chat / service / serve。

项目采用标准 `src` layout。建议使用 editable install：

```bash
python -m pip install -e .
migloop 01a0048b --open
python -m pip install pytest
python -m pytest tests -q
```

不安装也可以运行：

```bash
# PowerShell
$env:PYTHONPATH="src"; python -m migloop 01a0048b

# macOS / Linux
PYTHONPATH=src python -m migloop 01a0048b
```

### 从源码构建 pyz

```bash
python scripts/build_pyz.py
```

构建脚本会从 `src/migloop/` 创建临时 staging 目录并原子替换
`dist/migloop-lineage.pyz`，不会在仓库中留下 `_stage`。

## 已知边界

- JSONL 格式属于 Claude Code / Codex 内部实现,官方不保证稳定;Claude 已在 v2.1.170 ~ v2.1.220、Codex 已在 rollout schema `session_meta` / `response_item` / `event_msg` 上验证
- 阶段切分针对 a2h 管线 skill(mig-arch / a2h-spec / plan / execute / verify / retrospect);
  未调用管线 skill 的通用会话会整体作为单一 "Session" 阶段展示
- token 统计按 message.id 去重、过滤 `<synthetic>` 本地合成记录（细节见 `adapters/claude.py` 注释）
- 两原子收集器对 shell 读写做静态解析(变量、for 循环、grep/head 输出对账都覆盖);脚本黑盒、`$(…)` 命令替换、
  通配路径标为「未解析读写」而不猜,`index` 里能看到每个 agent 的未解析计数
- 运行时把主会话快照当子代理上传的记录(agent-snapshot)在「02 风险点」标出,页面忠实呈现不去重;账本里去重

## 代码结构

| 目录 | 说明 |
|---|---|
| `src/migloop/adapters/` | Claude、Codex、DevEco 输入格式 → 统一 trace；registry 也在这里 |
| `src/migloop/atoms*.py` `filestory*.py` `shellparse.py` | 两原子账本:收集(含 shell 读写静态解析)、版本文件 × 版本 agent、返修链、文本渲染 |
| `src/migloop/audit.py` `blame.py` `crosschain.py` | 风险点审计、行级 blame、同工程前序 / 后续会话发现 |
| `src/migloop/service.py` `serve.py` `mcp_server.py` | 会话定位与账本缓存、`--serve` 本机 HTTP、MCP 工具面(同一份文本输出) |
| `src/migloop/render/` | 静态 HTML、对比页面和模板，完全不关心输入来源 |
| `src/migloop/live/` | 增量 cursor、checkpoint 和本地 live server |
| `src/migloop/chat/` | Codex / Anthropic / OpenAI-compatible 分析助手 |
| `src/migloop/cli.py` | session 定位、adapter dispatch 与命令行编排 |
| `tests/` | adapter、源码视野、live 与 chat 回归测试 |
| `scripts/` | pyz 打包与开发期 trace/HTML 工具 |
| `docs/` | 设计、开发、竞品对比文档;`docs/skills/` 是给 agent 的返修归因技能 |
| `dist/migloop-lineage.pyz` | 分发用单文件 |
