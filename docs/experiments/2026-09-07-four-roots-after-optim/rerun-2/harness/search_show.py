"""打印这次四根里几次真实的 search 返回原文(短的整段,长的前 14 行)。"""
from __future__ import annotations

import glob
import json
import os

EXP = os.path.dirname(os.path.abspath(__file__))
WANT = [("color_home_tab_bg", "__main__:9b3105a2"), ("maskColor", None), ("color_home_tab_bg", "entry/src/main/ets/pages/HomePage.ets")]
for d in sorted(glob.glob(os.path.join(EXP, "runs", "seg4_tools", "chain*", "rep1"))):
    uses: dict[str, dict] = {}
    for line in open(os.path.join(d, "transcript.jsonl"), encoding="utf-8"):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        for blk in (rec.get("message") or {}).get("content") or []:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "tool_use" and blk["name"].endswith("__search"):
                uses[blk["id"]] = blk["input"]
            elif blk.get("type") == "tool_result" and blk.get("tool_use_id") in uses:
                inp = uses[blk["tool_use_id"]]
                key = (inp.get("q"), inp.get("agent") or inp.get("file"))
                if not any(k[0] == key[0] and (k[1] is None or k[1] == key[1]) for k in WANT):
                    continue
                c = blk.get("content")
                text = c if isinstance(c, str) else "".join(x.get("text", "") for x in (c or []) if isinstance(x, dict))
                try:
                    text = json.loads(text).get("result", text)
                except Exception:
                    pass
                print("\n>>> search", json.dumps({k: v for k, v in inp.items() if k != "sid"}, ensure_ascii=False), f"→ {len(text)} 字")
                print("\n".join(ln[:170] for ln in text.splitlines()[:14]))
                WANT[:] = [k for k in WANT if not (k[0] == key[0] and (k[1] is None or k[1] == key[1]))]
