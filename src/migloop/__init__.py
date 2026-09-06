"""MigLoop —— 迁移会话的轨迹、数据血缘与返修链路(两原子账本)分析工具。

2026-09-06 起工具在本仓的 dev/fixchain 分支演进(adapters / audit / blame / crosschain / 两原子:
filestory / atoms / atoms_collect / atoms_text / shellparse / mcp_server / render 模板);
migbot-server 的 ``src/vendor/migloop`` 与 hmigbot 的 ``migbot.insight`` 只做 UI 展示,从这里同步。
cli / live / chat / service / serve 是独立工具自己的。
"""

__version__ = "0.5.0"
