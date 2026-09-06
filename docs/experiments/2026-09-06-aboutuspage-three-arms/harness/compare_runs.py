"""按 label 汇总各 rep 的费用 / 时间 / 调用 / 每工具字符,并把结论正文落成 report.md。用法: python compare_runs.py <label> [<label> ...]"""
from __future__ import annotations

import glob
import json
import os
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
for label in sys.argv[1:]:
    for mp in sorted(glob.glob(os.path.join(EXP, "runs", label, "chain*", "rep*", "metrics.json"))):
        m = json.load(open(mp, encoding="utf-8"))
        tr = m.get("transcript") or {}
        u = tr.get("usage") or {}
        per = tr.get("per_tool") or {}
        rep_dir = os.path.dirname(mp)
        res = json.load(open(os.path.join(rep_dir, "result.json"), encoding="utf-8"))
        text = str(res.get("result") or "")
        open(os.path.join(rep_dir, "report.md"), "w", encoding="utf-8").write(text)
        print(f"== {label} rep{m['rep']}: ${m.get('cost_usd'):.2f} · {m.get('wall_s')}s · {tr.get('tool_calls')} 次 · "
              f"工具返回 {tr.get('tool_chars')} 字 · cache读 {u.get('cache_read')} · 输出 {u.get('output')} · 定性 {m.get('verdict')}")
        print("   per_tool:", ", ".join(f"{k}×{v['n']}={v['chars']}" for k, v in sorted(per.items(), key=lambda kv: -kv[1]['chars'])))
        seq = [s["tool"] for s in tr.get("seq") or []]
        print("   seq:", " ".join(seq))
