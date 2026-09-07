"""打印某几个 label 下每根报告的「故障进入点」与「置信」原句。用法: python entry_lines.py label1 label2 …"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
for lab in sys.argv[1:]:
    for p in sorted(glob.glob(os.path.join(EXP, "runs", lab, "chain*", "rep1", "result.json"))):
        t = str(json.load(open(p, encoding="utf-8")).get("result") or "")
        root = os.path.basename(os.path.dirname(os.path.dirname(p)))
        e = re.search(r"故障进入点[::]\s*(.+)", t)
        c = re.search(r"置信[::]\s*(.+)", t)
        links = len(re.findall(r"^环\s*\d+", t, re.M))
        print(f"== {lab} {root} · {links} 环 · 置信 {(c.group(1)[:30] if c else '')}")
        print("   ", (e.group(1)[:260] if e else t[:200]))
