"""四根重跑里 8 次 agent() 返回,按我们自己的四大段切(派发指令的内部小标题不算段):头部 / 派发指令 / 收件箱 / 逐版时间线 / 收尾。"""
from __future__ import annotations

import collections
import glob
import json
import os

EXP = os.path.dirname(os.path.abspath(__file__))
MARKS = ["## 派发指令", "## 收件箱", "## 逐版时间线", "## 收尾输出"]
tot: collections.Counter[str] = collections.Counter()
rows = []
import sys

LABEL = sys.argv[1] if len(sys.argv) > 1 else "seg3_tools"
for d in sorted(glob.glob(os.path.join(EXP, "runs", LABEL, "chain*", "rep1"))):
    uses: dict[str, dict] = {}
    for line in open(os.path.join(d, "transcript.jsonl"), encoding="utf-8"):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        for blk in (rec.get("message") or {}).get("content") or []:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "tool_use" and blk["name"].endswith("__agent"):
                uses[blk["id"]] = blk["input"]
            elif blk.get("type") == "tool_result" and blk.get("tool_use_id") in uses:
                c = blk.get("content")
                text = c if isinstance(c, str) else "".join(x.get("text", "") for x in (c or []) if isinstance(x, dict))
                try:
                    text = json.loads(text).get("result", text)
                except Exception:
                    pass
                pos = {m: text.find("\n" + m) for m in MARKS}
                cuts = sorted((v, m) for m, v in pos.items() if v >= 0)
                parts = {"头部": cuts[0][0] if cuts else len(text)}
                for i, (v, m) in enumerate(cuts):
                    end = cuts[i + 1][0] if i + 1 < len(cuts) else len(text)
                    parts[m[3:]] = end - v
                inp = uses[blk["tool_use_id"]]
                rows.append((inp.get("id", "")[-16:], inp.get("v"), inp.get("since"), len(text), parts))
                tot.update(parts)
for aid, v, since, n, parts in rows:
    print(f"agent({aid}, v={v}, since={since}) {n:>6} 字: " + ", ".join(f"{k} {c}" for k, c in parts.items()))
s = sum(tot.values())
print("\n合计", s, "字:", {k: f"{c} ({c * 100 // s}%)" for k, c in tot.most_common()})
