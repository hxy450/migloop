"""把六根的两份报告(工具组最新一次 vs 原始组)+ 评委按环结论 + 费用拼成一页 HTML(数据块),给页面模板用。
用法: python build_cases_page.py <tools_label> <tools_dice_label> <out.json>"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
ROOTS = [("DiceRoller EntryAbility.ets", "最多跳(上游 12 跳)", 2, "dice"),
         ("0723 HomeTabComponent.ets", "生成+修复最耗 token", 0, "0723"),
         ("0723 MemberCenterPage.ets", "生成→修复耗时最长(67h)", 8, "0723"),
         ("0723 SplashPage.ets", "生成期改动最多(51 版)", 10, "0723"),
         ("0723 GuidePage.ets", "修复期改动最多(4 次)", 5, "0723"),
         ("0723 EntryAbility.ets", "生成期改 36 次、修复轮没动(问为什么反复)", 90, "0723")]


def load(label: str, chain: int):
    hits = glob.glob(os.path.join(EXP, "runs", label, f"chain{chain:02d}-*", "rep1", "result.json"))
    if not hits:
        return None
    r = json.load(open(hits[0], encoding="utf-8"))
    m = json.load(open(hits[0].replace("result.json", "metrics.json"), encoding="utf-8"))
    text = str(r.get("result") or "").strip()
    text = re.sub(r"^```\n?|\n?```$", "", text)
    tr = m.get("transcript") or {}
    u = tr.get("usage") or {}
    return {"text": text, "cost": m.get("cost_usd"), "turns": m.get("num_turns"), "calls": tr.get("tool_calls"),
            "chars": tr.get("tool_chars"), "wall": m.get("wall_s"), "ctx": (u.get("cache_read") or 0) + (u.get("cache_create") or 0),
            "out": u.get("output")}


def judge(treat: str, control: str, chain: int):
    p = os.path.join(EXP, "runs", "judge", f"{treat}_vs_{control}.chain.json")
    if not os.path.exists(p):
        return None
    for j in json.load(open(p, encoding="utf-8")):
        if j["chain"] == chain:
            v = j["verdict"]
            a = j["treat_is_A"]
            side = lambda k: (v.get(f"a_{k}"), v.get(f"b_{k}")) if a else (v.get(f"b_{k}"), v.get(f"a_{k}"))  # noqa: E731
            return {"links": side("links"), "checkable": side("checkable"), "consistency": side("consistency"),
                    "shared": v.get("shared_links"), "agree": v.get("shared_verdict_agree"), "same_entry": v.get("same_entry"),
                    "entry_note": v.get("entry_note"), "reason": v.get("reason"), "preferred": j["preferred_method"],
                    "actionable": j["actionable_method"], "conflicts": v.get("conflicts") or []}
    return None


tools, tools_dice, out = sys.argv[1], sys.argv[2], sys.argv[3]
data = []
for name, why, chain, kind in ROOTS:
    t_label = tools_dice if kind == "dice" else tools
    r_label = "cases_raw_dice" if kind == "dice" else "cases_raw"
    data.append({"name": name, "why": why, "tools": load(t_label, chain), "raw": load(r_label, chain),
                 "judge": judge(t_label, r_label, chain)})
json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", len(data), out)
