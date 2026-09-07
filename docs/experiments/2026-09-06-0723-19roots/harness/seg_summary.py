"""按根汇总一组:费用 / 时间 / 调用 / 输出 token,并从报告里抠「生成时为什么没做好」「是否必要」两行。
用法: python seg_summary.py <label> [<label> ...]  → 打印表 + 合计,并写 runs/<label>/summary.json"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

EXP = os.path.dirname(os.path.abspath(__file__))


def field(text: str, key: str) -> str:
    m = re.search(rf"{key}[::]\s*(.+)", text)
    return m.group(1).strip() if m else ""


for label in sys.argv[1:]:
    rows = []
    for mp in sorted(glob.glob(os.path.join(EXP, "runs", label, "chain*", "rep1", "metrics.json"))):
        m = json.load(open(mp, encoding="utf-8"))
        res = json.load(open(mp.replace("metrics.json", "result.json"), encoding="utf-8"))
        text = str(res.get("result") or "")
        open(mp.replace("metrics.json", "report.md"), "w", encoding="utf-8").write(text)
        tr = m.get("transcript") or {}
        u = tr.get("usage") or {}
        rows.append({
            "chain": m["chain"], "file": str(m["file"]).rsplit("/", 1)[-1], "cost": m.get("cost_usd") or 0,
            "wall_s": m.get("wall_s") or 0, "calls": tr.get("tool_calls") or 0, "out": u.get("output") or 0,
            "cache_read": u.get("cache_read") or 0, "error": bool(m.get("is_error")),
            "why": field(text, "生成时为什么没做好"), "need": field(text, "是否必要"),
            "conf": field(text, "置信"), "chars": len(text),
        })
    rows.sort(key=lambda r: r["chain"])
    print(f"\n=== {label}: {len(rows)} 根")
    for r in rows:
        print(f"{r['chain']:>2} {r['file'][:22]:<22} ${r['cost']:.2f} {r['wall_s']:>5.0f}s {r['calls']:>3}次 out{r['out']:>6} "
              f"{'ERR ' if r['error'] else ''}| {r['why'][:110]}")
    tot = {"cost": sum(r["cost"] for r in rows), "wall_s": sum(r["wall_s"] for r in rows),
           "calls": sum(r["calls"] for r in rows), "out": sum(r["out"] for r in rows),
           "cache_read": sum(r["cache_read"] for r in rows), "errors": sum(r["error"] for r in rows)}
    print(f"合计: ${tot['cost']:.2f} · {tot['wall_s']/60:.1f} 分 · {tot['calls']} 次调用 · 输出 {tot['out']} token"
          f" · cache 读 {tot['cache_read']} · 出错 {tot['errors']}")
    json.dump({"rows": rows, "total": tot}, open(os.path.join(EXP, "runs", label, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
