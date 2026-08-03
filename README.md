# MigLoop Trace Viewer (PoC)

把 Claude Code 迁移会话的 JSONL transcript 一键变成可交互的轨迹页面:
执行拓扑 / Git 式执行流(主干=主会话,分支=子代理)/ 主线上下文占用曲线 / 阶段对比 / 阶段明细 + 点击详情抽屉。

## 文档

- [MigLoop 设计说明](./MigLoop-设计说明.md)：目标、证据口径、数据结构和实现方式
- [MigLoop 与 CANNBot-Insight 对比](./MigLoop-vs-CANNBot-Insight.md)：定位、能力、优缺点与演进建议

## 使用(推荐:单文件 `dist/migloop-lineage.pyz`)

**要求**:Python ≥ 3.9,无任何第三方依赖。Windows / macOS / Linux 通用。

```bash
# Windows
py migloop-lineage.pyz                 # 列出本机最近的 session
py migloop-lineage.pyz f3bb027a        # 按 session-id 前缀生成
py migloop-lineage.pyz arch9 --open    # 按项目名片段生成并在浏览器打开

# macOS / Linux
python3 migloop-lineage.pyz <目标> [-o out.html] [--open]
```

`<目标>` 三种写法任选:
1. `.jsonl` 文件完整路径(拿到别人分享的文件时用这个)
2. session-id 前缀(自动在 `~/.claude/projects` 下查找)
3. 项目目录名片段(取该项目最新 session)

输出为**完全自包含**的 HTML(字体、数据全部内嵌),可以直接发给任何人用浏览器打开,不需要网络。

### 实时查看仍在运行的 session

```bash
py migloop-lineage.pyz dynamic1 --live --open
```

`--live` 启动仅监听 `127.0.0.1` 的本地页面。主会话与每个子 agent 的 JSONL 都按 byte offset
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

## 跨机器分享 session

Claude Code 的一个 session 由两部分组成,分享时要一起拷:

```
~/.claude/projects/<项目>/<session-id>.jsonl      ← 主会话
~/.claude/projects/<项目>/<session-id>/subagents/ ← 子代理 transcript(缺了泳道为空)
```

对方拿到后:`py migloop-lineage.pyz 路径/到/<session-id>.jsonl`。

## 从源码构建 pyz

```bash
mkdir _stage
cp lineage2/migloop.py _stage/__main__.py
cp lineage2/extract_session.py lineage2/live_session.py lineage2/chat_provider.py lineage2/viewer_template.html _stage/
cp lineage2/compare_build.py lineage2/compare_template.html _stage/
python -m zipapp _stage -o dist/migloop-lineage.pyz -p "/usr/bin/env python3"
rm -rf _stage
```

## 已知边界

- JSONL 格式属 Claude Code 内部实现,官方不保证稳定;已在 v2.1.170 ~ v2.1.220 上实测核心字段一致
- 阶段切分针对 a2h 管线 skill(mig-arch / a2h-spec / plan / execute / verify / retrospect);
  未调用管线 skill 的通用会话会整体作为单一 "Session" 阶段展示
- token 统计按 message.id 去重、过滤 `<synthetic>` 本地合成记录(细节见 extract_session.py 注释)

## 文件

| 文件 | 说明 |
|---|---|
| `lineage2/migloop.py` | CLI 入口(定位 → 离线抽取或增量 live) |
| `lineage2/extract_session.py` | JSONL → 最终结构化 trace |
| `lineage2/live_session.py` | byte cursor、增量 reducer、checkpoint 与本地 live server |
| `lineage2/chat_provider.py` | 血缘摘要与 Codex / Anthropic / OpenAI-compatible provider |
| `lineage2/viewer_template.html` | 最终离线页面模板 |
| `lineage2/build_viewer.py` | 开发用:trace JSON → HTML |
| `dist/migloop-lineage.pyz` | 分发用单文件 |
