"""同一会话、同一组工具调用,在指定代码版本下渲染,打印每次输出的字符数(比 legacy 与现在的工具文本体量)。
用法: python measure_tool_text.py <src 目录> <sid> [<sid> ...]"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, sys.argv[1])
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from migbot.insight import atoms_text, routes  # noqa: E402

CALLS = {
    "ff019d8a": [("sessions", {}), ("index", {"kind": "agent"}),
                 ("file", {"path": "AboutUsPage.ets"}),
                 ("diff", {"path": "AboutUsPage.ets", "v": 11}),
                 ("blame", {"path": "AboutUsPage.ets", "v": 11}),
                 ("blame_changed", {"path": "AboutUsPage.ets", "v": 12}),
                 ("agent", {"id": "agent-aconv-aboutus-fcd0d52d4f7bcd0b"}),
                 ("agent", {"id": "agent-aslice6-risk-d4a26e5b9d8d7364"}),
                 ("agent_main", {"id": "__main__:ff019d8a"}),
                 ("agent_main_since", {"id": "__main__:ff019d8a", "v": 12, "since": 11})],
    "49d451b1": [("sessions", {}), ("index", {"kind": "agent"}),
                 ("file", {"path": "pages/Index.ets"}),
                 ("diff", {"path": "pages/Index.ets", "v": 5}),
                 ("blame", {"path": "pages/Index.ets", "v": 5}),
                 ("blame_changed", {"path": "pages/Index.ets", "v": 5}),
                 ("agent", {"id": "agent-a349784d2663f1f0a"}),
                 ("agent", {"id": "agent-a4874344c8fb6228d"}),
                 ("agent_main", {"id": "__main__:81e0a463"}),
                 ("agent_main_since", {"id": "__main__:81e0a463", "v": 74, "since": 73})],
}


def call(tool: str, a: dict, ledger, payload, cwd) -> str | None:
    try:
        if tool == "sessions":
            return atoms_text.render_chains(payload, root=cwd)
        if tool == "index":
            return atoms_text.render_index(ledger, a.get("kind"), None, root=cwd)
        if tool == "file":
            return atoms_text.render_file(ledger, a["path"], None, root=cwd)
        if tool == "diff":
            return atoms_text.render_diff(ledger, a["path"], a["v"], root=cwd)
        if tool == "blame":
            return atoms_text.render_blame(ledger, a["path"], a["v"], None, None, root=cwd)
        if tool == "blame_changed":
            return atoms_text.render_blame(ledger, a["path"], a["v"], None, None, root=cwd, changed=True)
        if tool in ("agent", "agent_main"):
            return atoms_text.render_agent(ledger, a["id"], None, root=cwd)
        if tool == "agent_main_since":
            return atoms_text.render_agent(ledger, a["id"], a["v"], root=cwd, since=a["since"])
    except TypeError as e:          # 这一版没有这个参数
        return None
    except Exception as e:          # 找不到 id / 路径等
        return f"ERR {type(e).__name__}: {e}"[:60]
    return None


async def main() -> None:
    for sid in sys.argv[2:]:
        t0 = time.time()
        ledger = await routes.get_ledger(sid)
        payload = await routes.get_fixchain(sid)
        cwd = await routes.get_session_cwd(sid)
        print(f"\n== {sid}: 建账 {time.time() - t0:.1f}s, 链 {len(payload.get('chains') or [])}, agent {len(ledger.agents)}")
        for tool, a in CALLS[sid]:
            out = call(tool, a, ledger, payload, cwd)
            arg = a.get("path") or a.get("id") or a.get("kind") or ""
            if out is None:
                print(f"  {tool:<18} {arg[:34]:<34} (此版本无此参数)")
            elif out.startswith("ERR"):
                print(f"  {tool:<18} {arg[:34]:<34} {out}")
            else:
                print(f"  {tool:<18} {arg[:34]:<34} {len(out):>7} 字符 / {out.count(chr(10)) + 1:>5} 行")


asyncio.run(main())
