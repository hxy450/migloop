"""盲评结果解盲汇总。用法: python judge_tally.py runs/judge/<file>.json"""
from __future__ import annotations

import collections
import json
import sys

rows = json.load(open(sys.argv[1], encoding="utf-8"))
pref: collections.Counter[str] = collections.Counter()
agree = 0
sp = [0, 0]
co = [0, 0]
for r in rows:
    v = r["verdict"]
    tA = r["treat_is_A"]
    t_s, c_s = (v["a_specificity"], v["b_specificity"]) if tA else (v["b_specificity"], v["a_specificity"])
    t_c, c_c = (v["a_consistency"], v["b_consistency"]) if tA else (v["b_consistency"], v["a_consistency"])
    mc = v.get("preferred")
    who = ("工具" if (mc == "A") == tA else "原始") if mc in ("A", "B") else str(mc)
    pref[who] += 1
    agree += bool(v.get("agree"))
    sp[0] += t_s
    sp[1] += c_s
    co[0] += t_c
    co[1] += c_c
    print(f"{r['chain']:>2} {r['file'][:20]:<20} 一致={str(v.get('agree')):<5} 具体度 工具={t_s} 原始={c_s} "
          f"一致性 工具={t_c} 原始={c_c} 更可信={who}")
print(f"\n一致 {agree}/{len(rows)} · 更可信 {dict(pref)} · 具体度合计 工具 {sp[0]} 原始 {sp[1]} · 一致性合计 工具 {co[0]} 原始 {co[1]}")
print("\nverdict keys:", list(rows[0]["verdict"].keys()))
print("\n--- 不一致的根,评审说法:")
for r in rows:
    v = r["verdict"]
    if not v.get("agree"):
        print(f"[{r['chain']}] {r['file']}: {str(v.get('agree_note', ''))[:420]}\n")
print("--- 每根「更可信」的理由(前 240 字):")
for r in rows:
    v = r["verdict"]
    tA = r["treat_is_A"]
    mc = v.get("preferred")
    who = ("工具" if (mc == "A") == tA else "原始") if mc in ("A", "B") else str(mc)
    reason = v.get("more_credible_note") or v.get("credible_note") or v.get("why") or v.get("reason") or ""
    print(f"[{r['chain']}] {r['file'][:22]} → {who}: {str(reason)[:240]}")
