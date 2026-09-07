"""一组 run 的按工具用量:次数、返回字数、均次;以及 agent 调用带不带 since。用法: python tool_mix.py <label> [chains…]"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
label = sys.argv[1]
only = {int(x) for x in sys.argv[2:]} if len(sys.argv) > 2 else None
per: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
n = 0
cost = wall = 0.0
calls = 0
agent_since = agent_whole = 0
for mp in sorted(glob.glob(os.path.join(EXP, "runs", label, "chain*", "rep1", "metrics.json"))):
    m = json.load(open(mp, encoding="utf-8"))
    if only is not None and m["chain"] not in only:
        continue
    n += 1
    cost += m["cost_usd"]
    wall += m["wall_s"]
    tr = m["transcript"]
    calls += tr["tool_calls"]
    for s in tr["seq"]:
        per[s["tool"]][0] += 1
        per[s["tool"]][1] += s["chars"]
        if s["tool"] == "agent":
            if "since" in (s.get("input") or {}):
                agent_since += 1
            else:
                agent_whole += 1
print(f"{label}: {n} 根 · ${cost:.2f}(均 {cost / n:.2f}) · {wall / 60:.1f} 分 · {calls} 次(均 {calls / n:.1f}) · "
      f"agent 带 since {agent_since} / 不带 {agent_whole}")
for k, (c, ch) in sorted(per.items(), key=lambda kv: -kv[1][1]):
    print(f"   {k:<10} {c:>3} 次 {ch:>7} 字 均 {ch // max(c, 1):>6}")
