"""MigLoop —— 迁移会话的轨迹、数据血缘与返修链路(两原子账本)分析工具。

上游是 migbot-server 的 ``src/vendor/migloop``(2026-09 起,server 为准);本包从那里同步
adapters / audit / blame / crosschain / 两原子(filestory / atoms / atoms_collect / atoms_text)/
shellparse / mcp_server / render 模板,并加上独立工具自己的 cli / live / chat / service / serve。
"""

__version__ = "0.4.0"
