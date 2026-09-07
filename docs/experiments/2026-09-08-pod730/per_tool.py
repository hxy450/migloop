"""某 label 下每根的按工具返回字数与次数。用法: python per_tool.py label [label…]"""
from __future__ import annotations

import glob
import json
import os
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
for lab in sys.argv[1:]:
    for p in sorted(glob.glob(os.path.join(EXP, "runs", lab, "chain*", "rep1", "metrics.json"))):
        m = json.load(open(p, encoding="utf-8"))
        tr = m.get("transcript") or {}
        root = os.path.basename(os.path.dirname(os.path.dirname(p)))
        parts = sorted(((v["chars"], v["n"], k) for k, v in (tr.get("per_tool") or {}).items()), reverse=True)
        print(f"== {lab} {root}: 调用 {tr.get('tool_calls')} 返回 {tr.get('tool_chars')} 字 · $ {m.get('cost_usd'):.2f}")
        print("   " + " · ".join(f"{k} {n}次/{c}字" for c, n, k in parts))
        big = sorted(((s["chars"], s["tool"], {k: v for k, v in s["input"].items() if k != 'sid'}) for s in tr.get("seq") or []),
                     key=lambda x: -x[0])[:4]
        for c, t, inp in big:
            print(f"     最大: {t} {c} 字 {json.dumps(inp, ensure_ascii=False)[:120]}")
