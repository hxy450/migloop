"""逐版清单:每条链的每个修复版本,写者 + 时刻 + diff 里前几行改动(给逐版对账用)。用法: python version_ledger.py <sid>"""
from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migbot-elite/.claude/worktrees/filestory/src")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from migbot.insight import atoms, routes  # noqa: E402

SID = sys.argv[1] if len(sys.argv) > 1 else "49d451b1"


def _summ(diff: str | None, n: int = 3) -> str:
    if not diff:
        return "(无 diff 正文)"
    lines = [ln for ln in diff.splitlines() if (ln.startswith("+") or ln.startswith("-"))
             and not ln.startswith(("+++", "---")) and ln[1:].strip()]
    out = []
    for ln in lines[:n]:
        out.append(re.sub(r"\s+", " ", ln)[:110])
    more = f" …(+{len(lines) - n} 行)" if len(lines) > n else ""
    return " | ".join(out) + more


async def main() -> None:
    ledger = await routes.get_ledger(SID)
    payload = await routes.get_fixchain(SID)
    cwd = await routes.get_session_cwd(SID)
    for c in payload["chains"]:
        st = ledger.stories[c["file_abs"]]
        rel = os.path.relpath(c["file_abs"], cwd) if cwd and c["file_abs"].startswith(cwd) else c["file_abs"]
        print(f"\n## {rel}  ({c['kind']}, 修复版本 {len(c['fix_versions'])} 个)")
        for v in c["fix_versions"]:
            ver = st.versions[v - 1]
            who = atoms.agent_label(ledger, ver.by)
            print(f"  v{v:<3} {atoms.rel_time(ver.ts, ledger.t0):<8} {who[:24]:<24} {ver.diff_kind:<9} {_summ(ver.diff)}")


asyncio.run(main())
