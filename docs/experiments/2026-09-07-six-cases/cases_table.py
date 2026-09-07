"""案例对照表:summary.jsonl 里每根两组并排(费用 / 轮 / 调用 / 返回字 / 时长)+ 该组对的按环盲评结果。
用法: python cases_table.py [--treat cases_tools2] [--treat-dice cases_tools2_dice]"""
from __future__ import annotations

import json
import os
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
treat = args[args.index("--treat") + 1] if "--treat" in args else "cases_tools"
treat_dice = args[args.index("--treat-dice") + 1] if "--treat-dice" in args else "cases_tools_dice"
pairs = {treat: "cases_raw", treat_dice: "cases_raw_dice"}
rows = [json.loads(l) for l in open(os.path.join(EXP, "runs", "summary.jsonl"), encoding="utf-8") if l.strip()]
latest: dict[tuple[str, str], dict] = {}
for r in rows:
    if r["label"] in pairs or r["label"] in pairs.values():
        latest[(r["label"], r["file"])] = r          # 同根重跑取最后一次
judge: dict[str, dict] = {}
for t, c in pairs.items():
    p = os.path.join(EXP, "runs", "judge", f"{t}_vs_{c}.chain.json")
    if os.path.exists(p):
        for j in json.load(open(p, encoding="utf-8")):
            judge[f"{j['file']}@{j['chain']}"] = j
print("| 根 | 组 | 费用 $ | 轮 | 调用 | 返回字 | 时长 s | 错误 |")
print("|---|---|---|---|---|---|---|---|")
tot = {"tools": [0.0, 0, 0, 0.0], "raw": [0.0, 0, 0, 0.0]}
for t_label, r_label in pairs.items():
    files = sorted({f for (lab, f) in latest if lab == t_label})
    for f in files:
        for lab, name in ((t_label, "tools"), (r_label, "raw")):
            r = latest.get((lab, f))
            if not r:
                print(f"| {f} | {name} | (缺) | | | | | |")
                continue
            print(f"| {f} | {name} | {r['cost']:.2f} | {r['turns']} | {r['calls']} | {r['tool_chars']} | {r['wall_s']:.0f} | {'是' if r['error'] else ''} |")
            tot[name][0] += r["cost"] or 0; tot[name][1] += r["turns"] or 0; tot[name][2] += r["calls"] or 0; tot[name][3] += r["wall_s"] or 0
for name, (c, t, n, w) in tot.items():
    print(f"| 合计 | {name} | {c:.2f} | {t} | {n} | | {w:.0f} | |")
if judge:
    print("\n| 根 | 环数 工具/原始 | 共同环 / 判定一致 | 进入点同环 | 可核 工具/原始 | 一致性 工具/原始 | 更可信 | 更可行动 | 冲突 |")
    print("|---|---|---|---|---|---|---|---|---|")
    tally = {"treat": 0, "control": 0, "tie": 0}
    same = 0
    for key, j in judge.items():
        v, a = j["verdict"], j["treat_is_A"]
        def side(k: str) -> str:
            x, y = v.get(f"a_{k}"), v.get(f"b_{k}")
            return f"{x}/{y}" if a else f"{y}/{x}"
        tally[j["preferred_method"]] = tally.get(j["preferred_method"], 0) + 1
        same += 1 if v.get("same_entry") else 0
        print(f"| {key} | {side('links')} | {v.get('shared_links')} / {v.get('shared_verdict_agree')} | {v.get('same_entry')} | "
              f"{side('checkable')} | {side('consistency')} | {j['preferred_method']} | {j['actionable_method']} | {len(v.get('conflicts') or [])} |")
    print(f"| 合计 | | | {same}/{len(judge)} | | | 工具 {tally['treat']} : 原始 {tally['control']} : 平 {tally.get('tie', 0)} | | |")
