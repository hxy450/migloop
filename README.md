# MigLoop Trace Viewer (PoC)

把 Claude Code / Codex / DevEco / DeepSeek Harness(dsh)迁移会话的记录一键变成可交互的轨迹页面:
执行拓扑 / Git 式执行流(主干=主会话,分支=子代理)/ 主线上下文占用曲线 / 阶段对比 / 阶段明细 + 点击详情抽屉 /
风险点审计 / 数据血缘 / 会话总览(同工程全部会话与 ECAT 各轮)。

> 返修链路(两原子账本、返修链页、两原子端点、MCP、调查技能)已移到 fuxi-ailabs/a2h-memory 的 `fixchain/`。
> 那边带一份本仓会话解析层的副本,按提交号同步。制卡与归并用的 memory skills 也在 a2h-memory。

## 这个仓库负责什么

只做**会话解析**:把会话记录读成统一的 trace,在上面跑审计规则,画成页面。

```text
Claude / Codex / DevEco / dsh session
        ↓ adapters(发现、识别、解析、归一化)
统一 trace:阶段、工具调用、子代理、用量、文件血缘
        ↓ audit(「02 风险点」规则)
        ↓ render / live
自包含 HTML、对比页、live 页、会话总览
```

| 层 | 入口 | 作用 |
|---|---|---|
| 来源适配 | `src/migloop/adapters/` | 各来源的会话发现、识别与解析,输出同一份 trace |
| 审计 | `audit.py`、`audit_review.py`、`audit_events.py`、`ecat.py` | 「02 风险点」规则;ECAT 角色会话的补注与 run 级审计 |
| 页面 | `render/`、`chain.py`、`followups.py` | 静态报告、对比页、会话总览、执行拓扑的后续节点 |
| 运行方式 | `cli.py`、`live/`、`chat/`、`service.py` | 命令行、增量 live(盯整次迁移)、分析助手、报告 trace |

### 当前适配范围

- Claude Code、Codex:离线 HTML、`--compare`、`--live`(含 ECAT 角色会话)。
- DevEco:离线 HTML 与 `--compare`;可按 session id 直读 `deveco.db`,也能读导出 JSON 与冻结投影。`--live` 总览里列出、标「不支持实时」。
- dsh:离线 HTML 与 `--compare`;`--live` 总览里列出、标「不支持实时」。

## 文档

- [MigLoop 设计说明](./docs/design.md):目标、证据口径、数据结构和实现方式
- [开发与架构指南](./docs/development.md):目录分层、adapter 契约、测试和扩展方式
- [MigLoop 与 CANNBot-Insight 对比](./docs/comparison-cannbot.md):定位、能力、优缺点与演进建议

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
2. session-id 前缀(自动在 `~/.claude/projects`、`~/.codex/sessions`、DevEco 数据目录与 dsh 会话目录下查找)
3. 项目目录名片段(取该项目最新 session)

输出为**完全自包含**的 HTML(字体、数据全部内嵌),可以直接发给任何人用浏览器打开,不需要网络。

多会话对比页:`py migloop-lineage.pyz arch6 arch7 arch9 --compare`。

### 实时盯一次迁移(`--live`)

```bash
py migloop-lineage.pyz C:\path\to\harmony-project --live --interval 60 --open   # 盯迁移工程目录
py migloop-lineage.pyz <session-id 前缀 | jsonl 路径> --live                        # 盯这个会话所在的迁移
```

目标可以是鸿蒙迁移工程目录,也可以是其中任意一个会话(取它的 cwd 当迁移目录)。监听 `127.0.0.1`,首页是
**会话总览**:这次迁移的全部会话一页列出 —— Claude 主迁移与中途新开的会话(所有 `~/.claude*/projects`
根下该目录对应的子目录)、cwd 落在目录里的 Codex rollout、`.ecat` 下的 ECAT 角色会话(按
`.migbot/ecat_runs` 的 run 与轮次挂上)。每个会话显示状态、当前阶段、阶段历史、用量、工具与输入原文,点
「详情」进入它的完整分析页(右下角有实时条和分析助手)。

- 每隔 `--interval` 秒(默认 10)刷新一次:先重新列一遍目录找新会话(只列目录、读新文件的首行认身份),
  再让各会话只读新追加的内容;总览数据来自各会话的增量状态,不整份重新解析。
- **首次打开会比之后的刷新慢**:第一次要把已有的会话从头读一遍(大会话要几秒到十几秒),之后每次刷新只读
  新增内容,通常在 1 秒以内。增量状态存在 `~/.migloop/cache/`,重启后接着读。
- 某个会话的完整分析页在点进去时才生成;有新记录时右下角提示,点「刷新完整分析」再重建。
- DevEco、dsh 会话这一版没有实时:目录里有就在总览里列出,标「不支持实时」。
- `Ctrl+C` 停止时写出 `-o` 指定的最终页面(默认 `migloop-<目录名>-live.html`):总览数据内嵌、自包含,
  每个会话的完整分析页放在同名 `.sessions/` 目录里,总览里的「详情」链到它们。

Workflow 会话按每次 Workflow 调用形成确定性阶段。血缘区逐阶段展示:
`读 Spec / 分析文档 + 读 Android 源码 → Agent → 产 Spec / 分析文档 + 产鸿蒙代码 / 资源 / 配置`。
Canonical `spec/` 与 Workflow 常用的 `.migration/analysis/` 都会作为契约文档进入血缘。

实时页右下角的“Agent 分析”可以围绕完整 session 连续提问。主线程 JSONL、subagents 和 Workflow
记录是事实源,血缘摘要只是定位索引:Codex 以只读方式按需追查原始记录;HTTP provider 由服务端
在完整记录中检索相关原始片段。浏览器只发送对话文本,API key 不会进入 HTML。默认调用本机已登录的 Codex CLI:

```bash
py migloop-lineage.pyz <迁移目录> --live --open                       # Codex 默认模型
py migloop-lineage.pyz dynamic1 --live --chat-model <model>          # 指定 Codex 模型
py migloop-lineage.pyz dynamic1 --live --chat-provider anthropic \
  --chat-model <model>                                                # 读取 ANTHROPIC_API_KEY
py migloop-lineage.pyz dynamic1 --live --chat-provider openai-compatible \
  --chat-model <model> --chat-base-url http://localhost:1234/v1      # 本地/兼容 API
py migloop-lineage.pyz dynamic1 --live --chat-provider off           # 关闭分析助手
```

Anthropic/OpenAI-compatible 可用 `--chat-api-key-env <环境变量名>` 改 key 来源。聊天是 live server
能力;导出的自包含 HTML 仍然是纯静态报告,不包含凭据或模型调用。

常用参数:

```bash
--interval 60           # 刷新间隔(找新会话 + 读新增内容);默认 10 秒
--port 8765             # 固定本地端口;默认自动选空闲端口
--reset-live-cache      # 丢弃 checkpoint,从头重放一次
--no-final              # 停止时不生成最终静态页面
```

增量 checkpoint 默认按会话保存在 `~/.migloop/cache/<session-id>.live.json`。MigLoop 重启后会从保存的
offset 继续;若检测到 transcript 被截断或替换,则自动丢弃旧聚合状态并重放。

## Codex session

Codex 主线程与子 Agent 分别落在按日期分区的 rollout 文件中:

```
~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
```

给出主 rollout 的完整路径、session-id 前缀或项目目录名即可。MigLoop 会根据
`session_meta.source.subagent.thread_spawn.parent_thread_id` 递归回链同一 session 的子 Agent,
并把 `response_item` / `event_msg`、`function_call` / `custom_tool_call`、token 用量和
`functions.exec` 内的 `shell_command` / `apply_patch` 归一到现有 trace。

## 跨机器分享 session

Claude Code 的一个 session 由两部分组成,分享时要一起拷:

```
~/.claude/projects/<项目>/<session-id>.jsonl      ← 主会话
~/.claude/projects/<项目>/<session-id>/subagents/ ← 子代理 transcript(缺了泳道为空)
```

对方拿到后:`py migloop-lineage.pyz 路径/到/<session-id>.jsonl`。

## 开发

migbot-server 的 `src/vendor/migloop` 另有一份 adapters / audit / 模板(2026-09 起曾以 server 为准同步);
a2h-memory 的 `fixchain/src/migloop/` 是本仓会话解析层的副本。

项目采用标准 `src` layout,运行时只用标准库。建议使用 editable install:

```bash
python -m pip install -e .
migloop 01a0048b --open
python -m pip install pytest
python -m pytest tests -q
```

不安装也可以运行:

```bash
# PowerShell
$env:PYTHONPATH="src"; python -m migloop 01a0048b

# macOS / Linux
PYTHONPATH=src python -m migloop 01a0048b
```

`tests/test_package_boundary.py` 守住两条边界:会话解析层不 import 返修链路模块,源码按 Python 3.9 语法解析。
a2h-memory 的 `fixchain/scripts/sync_from_migloop.py` 从本仓的一份检出同步会话解析层副本;改了解析层,
那边按新提交号重同步。

### 从源码构建 pyz

```bash
python scripts/build_pyz.py
```

构建脚本会从 `src/migloop/` 创建临时 staging 目录并原子替换
`dist/migloop-lineage.pyz`,不会在仓库中留下 `_stage`。

## 已知边界

- JSONL 格式属于 Claude Code / Codex 内部实现,官方不保证稳定;Claude 已在 v2.1.170 ~ v2.1.220、Codex 已在 rollout schema `session_meta` / `response_item` / `event_msg` 上验证
- 阶段切分针对 a2h 管线 skill(mig-arch / a2h-spec / plan / execute / verify / retrospect);
  未调用管线 skill 的会话按任务清单分段,都没有时整体作为单一 "Session" 阶段展示
- token 统计按 message.id 去重、过滤 `<synthetic>` 本地合成记录、跳过 Claude Code 的 `api-request-blob` 行(细节见 `adapters/claude.py`、`cc_records.py`)
- 运行时把主会话快照当子代理上传的记录(agent-snapshot)在「02 风险点」标出,页面忠实呈现不去重

## 代码结构

| 目录 | 说明 |
|---|---|
| `src/migloop/adapters/` | Claude、Codex、DevEco、dsh 输入格式 → 统一 trace;registry 也在这里 |
| `src/migloop/audit*.py` `ecat.py` | 「02 风险点」审计规则;ECAT 角色会话补注与 run 级审计 |
| `src/migloop/shellparse.py` `stage_signals.py` `cc_records.py` `line_blame.py` | shell 命令读写解析、阶段信号、对话行过滤、`.ets` 行级归属重放 |
| `src/migloop/project_sessions.py` `followups.py` `chain.py` | 同工程前后会话、执行拓扑后续节点、会话总览 |
| `src/migloop/service.py` | 会话定位(含冻结池观察范围)、trace 缓存、报告 trace |
| `src/migloop/render/` | 静态 HTML、对比页面、会话总览模板,完全不关心输入来源 |
| `src/migloop/live/` | 增量 cursor、checkpoint 和本地 live server(Claude、Codex) |
| `src/migloop/chat/` | Codex / Anthropic / OpenAI-compatible 分析助手 |
| `src/migloop/cli.py` | session 定位、adapter dispatch 与命令行编排 |
| `tests/` | adapter、审计、页面、live 与 chat 回归测试,包边界检查 |
| `scripts/` | pyz 打包与开发期 trace/HTML 工具 |
| `docs/` | 设计、开发、竞品对比文档 |
| `dist/migloop-lineage.pyz` | 分发用单文件 |
