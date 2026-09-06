"""不经模型直接调 MCP 同款渲染:python tool_text.py <sid> <tool> [k=v ...]
tool ∈ sessions(file=) | index(kind=,query=) | file(path=,v=,content=1,diff=1,start=,n=) | agent(id=,v=,since=)
       | blame(path=,v=,changed=1) | diff(path=,v=) | action(id=,seq=)"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migbot-elite/.claude/worktrees/filestory/src")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from migbot.insight import atoms_text, routes  # noqa: E402


def _int(x: str | None) -> int | None:
    return int(x) if x not in (None, "") else None


async def main() -> None:
    sid, tool = sys.argv[1], sys.argv[2]
    kw = dict(a.split("=", 1) for a in sys.argv[3:])
    ledger = await routes.get_ledger(sid)
    cwd = await routes.get_session_cwd(sid)
    if tool == "sessions":
        out = atoms_text.render_chains(await routes.get_fixchain(sid), root=cwd, file=kw.get("file"))
    elif tool == "index":
        out = atoms_text.render_index(ledger, kw.get("kind"), kw.get("query"), root=cwd,
                                      limit=_int(kw.get("limit")) or 300)
    elif tool == "file":
        out = atoms_text.render_file(ledger, kw["path"], _int(kw.get("v")), root=cwd,
                                     content=bool(_int(kw.get("content"))), diff=bool(_int(kw.get("diff"))),
                                     start=_int(kw.get("start")), n=_int(kw.get("n")))
    elif tool == "agent":
        out = atoms_text.render_agent(ledger, kw["id"], _int(kw.get("v")), root=cwd, since=_int(kw.get("since")))
    elif tool == "blame":
        out = atoms_text.render_blame(ledger, kw["path"], _int(kw.get("v")), _int(kw.get("start")),
                                      _int(kw.get("n")), root=cwd, changed=bool(_int(kw.get("changed"))))
    elif tool == "diff":
        out = atoms_text.render_diff(ledger, kw["path"], int(kw["v"]), root=cwd)
    elif tool == "action":
        out = atoms_text.render_action(ledger, kw["id"], int(kw["seq"]), max_chars=_int(kw.get("max")) or 20000)
    else:
        raise SystemExit("unknown tool " + tool)
    sys.stdout.write(out)
    sys.stdout.write(f"\n\n[chars={len(out)}]\n")


asyncio.run(main())
