"""把某次跑的工具调用序列在当前版本的工具上重放,对比每次返回字数(省字改动的实测效果)。
用法: python replay_calls.py <sid> <metrics.json>"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

sid, mpath = sys.argv[1], sys.argv[2]
p = service.locate_session(sid)
m = json.load(open(mpath, encoding="utf-8"))
seq = (m.get("transcript") or {}).get("seq") or []
before: dict[str, int] = {}
after: dict[str, int] = {}
rows = []
for s in seq:
    tool = s["tool"]
    if tool not in ("guide", "sessions", "index", "file", "agent", "search", "blame", "diff", "action"):
        continue
    args = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in s["input"].items() if k != "sid"}
    if "agent" in args and tool == "search":
        pass
    try:
        text = service.atom_text(p, tool, args)
        n = len(text)
    except Exception as e:  # noqa: BLE001
        text, n = f"ERR {type(e).__name__}: {e}", 0
    before[tool] = before.get(tool, 0) + int(s["chars"] or 0)
    after[tool] = after.get(tool, 0) + n
    rows.append((tool, int(s["chars"] or 0), n, json.dumps(args, ensure_ascii=False)[:90]))
print("| 工具 | 次数 | 原返回字 | 现在返回字 |")
print("|---|---|---|---|")
tb = ta = 0
for tool in sorted(before, key=lambda t: -before[t]):
    cnt = sum(1 for r in rows if r[0] == tool)
    print(f"| {tool} | {cnt} | {before[tool]} | {after[tool]} |")
    tb += before[tool]; ta += after[tool]
print(f"| 合计 | {len(rows)} | {tb} | {ta} |")
print("\n最大的几次(原 → 现):")
for tool, b, a, args in sorted(rows, key=lambda r: -r[1])[:8]:
    print(f"- {tool} {b} → {a}  {args}")
