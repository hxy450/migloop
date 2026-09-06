"""不经模型,直接从 insight 后端拿 0723 的返修链清单(抽样用),并落一份 JSON。"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migbot-elite/.claude/worktrees/filestory/src")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from migbot.insight import atoms_text, routes  # noqa: E402

SID = sys.argv[1] if len(sys.argv) > 1 else "9b3105a2"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"chains-{SID}.json")


async def main() -> None:
    payload = await routes.get_fixchain(SID)
    cwd = await routes.get_session_cwd(SID)
    chains = payload.get("chains") or []
    rows = []
    for i, c in enumerate(chains):
        g, f = c.get("generator") or {}, c.get("fixer") or {}
        rows.append({
            "i": i, "file": c.get("file"), "file_abs": c.get("file_abs"),
            "gen_id": g.get("id"), "gen_desc": g.get("desc"), "gen_stage": g.get("stage"),
            "fix_id": f.get("id"), "fix_desc": f.get("desc"), "fix_stage": f.get("stage"),
            "fix_versions": c.get("fix_versions"), "lines": c.get("lines"),
            "gen_session": c.get("gen_session"), "fix_session": c.get("fix_session"),
            "n_fixers": len(c.get("fixers_all") or []),
            "reason": (c.get("reason") or c.get("why") or "")[:120],
        })
    json.dump({"sid": SID, "cwd": cwd, "cross": payload.get("cross"), "t0": payload.get("t0"),
               "chains": rows}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("chains:", len(rows), "->", OUT)
    print("cross:", payload.get("cross"))
    for r in rows:
        print(f"{r['i']:>2} {str(r['file']).rsplit('/', 1)[-1]:<34} lines={r['lines']!s:<12} "
              f"gen={str(r['gen_desc'])[:22]:<22} [{r['gen_stage']}] fix={str(r['fix_desc'])[:22]:<22} "
              f"[{r['fix_stage']}] v={r['fix_versions']} "
              f"{'跨会话' if r['gen_session'] or r['fix_session'] else ''}")
    text = atoms_text.render_chains(payload, root=cwd)
    open(os.path.join(os.path.dirname(OUT), f"sessions-{SID}.txt"), "w", encoding="utf-8").write(text)
    print("sessions text chars:", len(text))


asyncio.run(main())
