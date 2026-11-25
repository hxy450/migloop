"""MigLoop —— 迁移会话的轨迹、阶段、数据血缘与自动审计(会话解析层)。

adapters 把 Claude Code / Codex / DevEco / dsh 会话归一化成同一份 trace;audit 在 trace 上跑「02 风险点」
规则;render 出自包含报告页、对比页与会话总览;live / chat / cli / service / serve 是独立工具自己的。
返修链路(两原子账本、返修链页、两原子端点、MCP、调查页)已移到 fuxi-ailabs/a2h-memory 的 ``fixchain/``,
那边带一份本包会话解析层的副本(按提交号与 sha256 同步)。
"""

__version__ = "0.5.0"
