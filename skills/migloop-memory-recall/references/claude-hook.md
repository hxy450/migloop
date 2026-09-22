# Claude Code 首次修改提醒

维护者接入时读取。运行中的迁移代理只需要 SKILL.md 和经验 index.md。

1. 用 maintain 的 export 生成应用阅读包（不加 --link-cards），建议放在项目 `.claude/migloop-memory/v1`。
2. 在包含本脚本的维护版 skill 中运行：

```text
python scripts/claude_hook.py install --project PROJECT --memory READING_DIRECTORY
```

首次安装复制轻量召回 skill 与 hook 到项目，合并 `.claude/settings.local.json`，保留已有设置并备份旧设置文件。不改迁移 skills、源码、权限策略或全局配置。已存在的安装会拒绝覆盖；调试时在新目录验证，升级需显式备份旧安装。这里的安装器与四 skill 的 install_bundle 不是同一用途。

3. 在项目目录启动新的 Claude Code 会话；正常接受该项目的工作区信任。`--safe-mode`、`--bare`、`disableAllHooks` 或组织策略可能禁止项目 hook。不要用这些模式跑需要召回的迁移。

## 行为

- `PreToolUse` 在当前会话/代理首次原生 Write、Edit、MultiEdit、NotebookEdit 或常见 shell 写操作之前返回 deny；这只暂停工具，把理由交给模型，不向用户索要批准。
- 模型用 Read 完整读取项目内召回 skill 和根 index，按任务选择经验后重试。PostToolUse 记录入口已读，后续写入回到原有权限流程；hook 从不返回 allow。
- 主代理和所有类型子代理都参与，用 session_id + agent_id 隔离，跨会话不会复用已读状态。纯只读代理不提醒；主动读过两个入口的代理不重复暂停。
- 日志位于 `.claude/migloop-runtime/`，记录提醒、索引/经验读取、恢复与首次成功修改的时间和工具调用 ID，不复制源码或工具正文。读取记录不是采用或理解的证明；采用理由留在代理原本的结果里。
- Bash/PowerShell 的 Python/Node/shell 等脚本保守触发，可能早于实际写入；不承诺任意 MCP、任意可执行程序的副作用识别。目标是写前提醒，不是安全沙箱。
- 当前以完整 Read 观察入口阅读。用 Bash cat 或 Skill 工具读取后若仍收到提醒，按提示 Read 两个短入口即可。
- 入口或状态损坏会返回具体错误。要暂时停用本功能，将 `.claude/migloop-memory.json` 的 enabled 设为 false；无需删除配置，也不影响其他 hook。

只有入口读取是机械门槛，经验选择交给模型；没有相关经验可立即继续，不要求写报告、强制加载某条经验或核查历史卡片。

此适配器用于 Claude Code 当前支持 agent_id 的工具 hook，Codex/DevEco 尚未接入。官方协议：[Hooks reference](https://code.claude.com/docs/en/hooks)。
