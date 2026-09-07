"""逐调用并排看几组 run:工具、参数、返回字数、累计字数、用量。用法: python seq_dump.py <run_dir> [<run_dir> ...]"""
from __future__ import annotations

import json
import os
import sys


def short(inp: object) -> str:
    if not isinstance(inp, dict):
        return ""
    if "command" in inp:
        return str(inp["command"]).replace("\n", " ")[:170]
    return json.dumps({k: v for k, v in inp.items() if k != "sid"}, ensure_ascii=False)[:120]


for d in sys.argv[1:]:
    m = json.load(open(os.path.join(d, "metrics.json"), encoding="utf-8"))
    tr = m["transcript"]
    u = tr["usage"]
    print(f"\n##### {d}: turns={m['num_turns']} calls={tr['tool_calls']} chars={tr['tool_chars']} "
          f"cost=${m['cost_usd']:.2f} wall={m['wall_s']:.0f}s cache_read={u.get('cache_read')} "
          f"cache_create={u.get('cache_create')} out={u.get('output')} result_chars={m['result_chars']} at={m['at']}")
    cum = 0
    for i, s in enumerate(tr["seq"]):
        cum += s["chars"]
        print(f"  {i + 1:>2} {s['tool']:<10} {s['chars']:>6} (累 {cum:>6}) {short(s.get('input'))}")
