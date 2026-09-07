"""两组按根并排:费用 / 时间 / 调用,以及各自的「生成时为什么没做好」。用法: python seg_compare.py seg_tools seg_raw"""
from __future__ import annotations

import json
import os
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
a, b = sys.argv[1], sys.argv[2]
A = {r["chain"]: r for r in json.load(open(os.path.join(EXP, "runs", a, "summary.json"), encoding="utf-8"))["rows"]}
B = {r["chain"]: r for r in json.load(open(os.path.join(EXP, "runs", b, "summary.json"), encoding="utf-8"))["rows"]}
print(f"{'根':<3}{'文件':<22} {a:>9} {b:>9} | {'秒':>4} {'秒':>4} | {'次':>3} {'次':>3}")
ta = tb = 0.0
for k in sorted(A):
    x, y = A[k], B.get(k)
    if not y:
        continue
    ta += x["cost"]
    tb += y["cost"]
    print(f"{k:<3}{x['file'][:22]:<22} ${x['cost']:>8.2f} ${y['cost']:>8.2f} | {x['wall_s']:>4.0f} {y['wall_s']:>4.0f} | {x['calls']:>3} {y['calls']:>3}")
print(f"合计 ${ta:.2f} vs ${tb:.2f}  ({(ta - tb) / tb * 100:+.0f}%)")
print("\n各根「生成时为什么没做好」(工具 ⇢ 原始):")
for k in sorted(A):
    y = B.get(k)
    if not y:
        continue
    print(f"\n[{k}] {A[k]['file']}\n  工具: {A[k]['why'][:260]}\n  原始: {y['why'][:260]}")
