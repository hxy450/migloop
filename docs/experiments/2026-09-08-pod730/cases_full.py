"""六根三次跑的全量对照:token(每轮重读 / 输出)、时间、调用、返回字、费用;各组的故障进入点原句;评委按环结论。"""
from __future__ import annotations

import glob
import json
import os
import re

EXP = os.path.dirname(os.path.abspath(__file__))
ROOTS = [("EntryAbility.ets", 2, "dice"), ("HomeTabComponent.ets", 0, "0723"), ("MemberCenterPage.ets", 8, "0723"),
         ("SplashPage.ets", 10, "0723"), ("GuidePage.ets", 5, "0723"), ("EntryAbility.ets", 90, "0723")]
LABELS = {"dice": [("原始", "cases_raw_dice"), ("工具1", "cases_tools_dice"), ("工具2", "cases_tools2_dice")],
          "0723": [("原始", "cases_raw"), ("工具1", "cases_tools"), ("工具2", "cases_tools2"), ("工具3", "cases_tools3")]}


def load(label: str, chain: int):
    hits = glob.glob(os.path.join(EXP, "runs", label, f"chain{chain:02d}-*", "rep1", "metrics.json"))
    if not hits:
        return None
    m = json.load(open(hits[0], encoding="utf-8"))
    r = json.load(open(hits[0].replace("metrics.json", "result.json"), encoding="utf-8"))
    text = str(r.get("result") or "")
    entry = re.search(r"故障进入点[::]\s*(.+)", text)
    conf = re.search(r"置信[::]\s*(.+)", text)
    links = len(re.findall(r"^环\s*\d+", text, re.M))
    return m, (entry.group(1).strip()[:150] if entry else ""), (conf.group(1).strip()[:40] if conf else ""), links


def judge_rows():
    out = {}
    for p in glob.glob(os.path.join(EXP, "runs", "judge", "cases_*.chain.json")):
        treat = os.path.basename(p).split("_vs_")[0]
        for j in json.load(open(p, encoding="utf-8")):
            out[(treat, j["chain"])] = j
    return out


J = judge_rows()
print("## 每根每次:轮 / 调用 / 返回字 / 每轮重读 token(cache_read) / 输出 token / 费用 $ / 时长 s")
print("| 根 | 组 | 轮 | 调用 | 返回字 | 重读 token | 输出 token | 费用 | 时长 | 环数 | 置信 |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
tot: dict[str, list[float]] = {}
for file, chain, kind in ROOTS:
    for name, label in LABELS[kind]:
        got = load(label, chain)
        if not got:
            continue
        m, entry, conf, links = got
        u = (m.get("transcript") or {}).get("usage") or {}
        tr = m.get("transcript") or {}
        row = [m.get("num_turns") or 0, tr.get("tool_calls") or 0, tr.get("tool_chars") or 0, u.get("cache_read") or 0,
               u.get("output") or 0, m.get("cost_usd") or 0.0, m.get("wall_s") or 0.0]
        print(f"| {file}@{chain} | {name} | {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]:.2f} | {row[6]:.0f} | {links} | {conf} |")
        t = tot.setdefault(name, [0.0] * 7 + [0])
        for i, v in enumerate(row):
            t[i] += v
        t[7] += 1
print("\n## 合计(按组;工具3 只跑了三根)")
print("| 组 | 根数 | 轮 | 调用 | 返回字 | 重读 token | 输出 token | 费用 | 时长 |")
print("|---|---|---|---|---|---|---|---|---|")
for name, t in tot.items():
    print(f"| {name} | {t[7]} | {t[0]:.0f} | {t[1]:.0f} | {t[2]:.0f} | {t[3]:.0f} | {t[4]:.0f} | {t[5]:.2f} | {t[6]:.0f} |")

print("\n## 故障进入点(各组原句,截 150 字)")
for file, chain, kind in ROOTS:
    print(f"\n### {file}@{chain}")
    for name, label in LABELS[kind]:
        got = load(label, chain)
        if got:
            print(f"- {name}: {got[1]}")
    for name, label in LABELS[kind]:
        j = J.get((label, chain))
        if j:
            v = j["verdict"]
            print(f"  · 评委({name} vs 原始): 进入点同环={v.get('same_entry')} 更可信={j['preferred_method']} "
                  f"共同环 {v.get('shared_links')} 判定一致 {v.get('shared_verdict_agree')}")
