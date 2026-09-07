"""找别的带返修链的会话:给定 projects 目录,逐个主会话建账,报链数与根。用法: python scan_sessions.py <dir> [<dir>...]"""
from __future__ import annotations

import glob
import os
import sys
import time

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

for d in sys.argv[1:]:
    files = sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getsize, reverse=True)
    print(f"# {d}: {len(files)} 个主会话")
    for p in files[:4]:
        t0 = time.time()
        try:
            pay = service.fixchain_payload(p)
        except Exception as e:  # noqa: BLE001
            print(f"- {os.path.basename(p)[:8]} {os.path.getsize(p) // 1024} KB: 建账失败 {type(e).__name__}: {str(e)[:120]}")
            continue
        chains = pay.get("chains") or []
        kinds = {}
        for c in chains:
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
        print(f"- {os.path.basename(p)[:8]} {os.path.getsize(p) // 1024} KB · {len(chains)} 条链 {kinds} · {time.time() - t0:.0f}s · cwd={pay.get('cwd')}")
        for c in chains[:12]:
            print(f"    {c['file']} [{c['kind']}] 生成方 {(c.get('generator') or {}).get('desc')} → 修复方 {(c.get('fixer') or {}).get('desc')} 修复版 {c.get('fix_versions')}")
