"""费用分解:同四根三组,轮数 × 每轮上下文 × 输出 token;每次调用返回均字。用法: python cost_decomp.py"""
from __future__ import annotations

import glob
import json
import os

EXP = os.path.dirname(os.path.abspath(__file__))
ROOTS = {1, 3, 4, 6}
for label in ("seg3_tools", "seg2_tools", "seg2_raw"):
    turns = cr = out = cost = wall = calls = chars = 0
    n = 0
    for mp in glob.glob(os.path.join(EXP, "runs", label, "chain*", "rep1", "metrics.json")):
        m = json.load(open(mp, encoding="utf-8"))
        if m["chain"] not in ROOTS:
            continue
        n += 1
        turns += m["num_turns"]
        cr += m["transcript"]["usage"]["cache_read"]
        out += m["transcript"]["usage"]["output"]
        cost += m["cost_usd"]
        wall += m["wall_s"]
        calls += m["transcript"]["tool_calls"]
        chars += m["transcript"]["tool_chars"]
    print(f"{label:<11} 每根: 轮 {turns / n:4.1f} · 每轮上下文 {cr // turns // 1000:>3}K token · 输出 {out // n // 1000:>2}K token"
          f" · 每轮 {wall / turns:4.1f} 秒 · 每次调用返回 {chars // calls:>5} 字 · ${cost / n:.2f}")
