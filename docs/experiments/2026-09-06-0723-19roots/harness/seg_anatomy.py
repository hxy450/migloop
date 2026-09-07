"""19 根两组的费用解剖:
工具组 —— agent 调用带不带 since、整段体量;sessions 带不带 file;每根最大的三次返回。
原始组 —— 打开修复方转录之前的「找人」调用数与字数;每根最大的三次返回。
两组 —— 每轮平均上下文(cache_read / turns)。
用法: python seg_anatomy.py seg_tools seg_raw"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
FIXER = "a68daf720e780b4c2"


def runs(label: str):
    for mp in sorted(glob.glob(os.path.join(EXP, "runs", label, "chain*", "rep1", "metrics.json"))):
        m = json.load(open(mp, encoding="utf-8"))
        yield m["chain"], str(m["file"]).rsplit("/", 1)[-1], m, os.path.dirname(mp)


def touched_section_len(run_dir: str) -> int:
    """sessions 输出里「修复期被脚本碰过」那一节的字数(从转录里的 tool_result 原文量)。"""
    best = 0
    for line in open(os.path.join(run_dir, "transcript.jsonl"), encoding="utf-8"):
        if "修复期被脚本碰过" not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        for blk in (d.get("message") or {}).get("content") or []:
            if isinstance(blk, dict) and blk.get("type") == "tool_result":
                c = blk.get("content")
                text = c if isinstance(c, str) else "".join(x.get("text", "") for x in c if isinstance(x, dict))
                i = text.find("## 修复期被脚本碰过")
                if i >= 0:
                    best = max(best, len(text) - i)
    return best


a, b = sys.argv[1], sys.argv[2]
print(f"=== {a}(工具组)")
print(f"{'根':<3}{'文件':<20}{'轮':>3}{'次':>3}{'字':>7}{'$':>6}{'每轮ctx':>8} | agent无since 次/字 | agent带since 次/字 | sessions 字(碰过节) | 最大三次")
tot = {"nos_n": 0, "nos_c": 0, "s_n": 0, "s_c": 0, "sess": 0, "touch": 0, "chars": 0, "cr": 0, "turns": 0}
for chain, f, m, d in runs(a):
    tr = m["transcript"]; u = tr["usage"]; seq = tr["seq"]
    nos = [s for s in seq if s["tool"] == "agent" and "since" not in (s.get("input") or {})]
    ws = [s for s in seq if s["tool"] == "agent" and "since" in (s.get("input") or {})]
    sess = [s for s in seq if s["tool"] == "sessions"]
    sess_c = sum(s["chars"] for s in sess)
    touch = touched_section_len(d)
    top = sorted(seq, key=lambda s: -s["chars"])[:3]
    tops = " ".join(f"{s['tool']}{s['chars'] // 1000}K" for s in top)
    ctx = u["cache_read"] // max(m["num_turns"], 1)
    print(f"{chain:<3}{f[:20]:<20}{m['num_turns']:>3}{tr['tool_calls']:>3}{tr['tool_chars']:>7}{m['cost_usd']:>6.2f}{ctx:>8} | "
          f"{len(nos):>2}/{sum(s['chars'] for s in nos):>6} | {len(ws):>2}/{sum(s['chars'] for s in ws):>6} | "
          f"{sess_c:>5}({touch:>4}) | {tops}")
    tot["nos_n"] += len(nos); tot["nos_c"] += sum(s["chars"] for s in nos)
    tot["s_n"] += len(ws); tot["s_c"] += sum(s["chars"] for s in ws)
    tot["sess"] += sess_c; tot["touch"] += touch; tot["chars"] += tr["tool_chars"]
    tot["cr"] += u["cache_read"]; tot["turns"] += m["num_turns"]
print(f"合计: 返回 {tot['chars']} 字;agent 无 since {tot['nos_n']} 次 {tot['nos_c']} 字({tot['nos_c'] * 100 // tot['chars']}%),"
      f"带 since {tot['s_n']} 次 {tot['s_c']} 字;sessions {tot['sess']} 字,其中碰过节 {tot['touch']} 字({tot['touch'] * 100 // tot['chars']}%);"
      f"每轮平均 ctx {tot['cr'] // tot['turns']} token")

print(f"\n=== {b}(原始组)")
print(f"{'根':<3}{'文件':<20}{'轮':>3}{'次':>3}{'字':>7}{'$':>6}{'每轮ctx':>8} | 找人阶段 次/字 | 最大三次")
tot = {"disc_n": 0, "disc_c": 0, "chars": 0, "cr": 0, "turns": 0}
for chain, f, m, d in runs(b):
    tr = m["transcript"]; u = tr["usage"]; seq = tr["seq"]
    disc_n = disc_c = 0
    for s in seq:
        cmd = str((s.get("input") or {}).get("command", ""))
        if FIXER in cmd:
            break
        disc_n += 1; disc_c += s["chars"]
    top = sorted(seq, key=lambda s: -s["chars"])[:3]
    tops = " ".join(f"{s['chars'] // 1000}K" for s in top)
    ctx = u["cache_read"] // max(m["num_turns"], 1)
    print(f"{chain:<3}{f[:20]:<20}{m['num_turns']:>3}{tr['tool_calls']:>3}{tr['tool_chars']:>7}{m['cost_usd']:>6.2f}{ctx:>8} | "
          f"{disc_n:>2}/{disc_c:>6} | {tops}")
    tot["disc_n"] += disc_n; tot["disc_c"] += disc_c; tot["chars"] += tr["tool_chars"]
    tot["cr"] += u["cache_read"]; tot["turns"] += m["num_turns"]
print(f"合计: 返回 {tot['chars']} 字;找人阶段 {tot['disc_n']} 次 {tot['disc_c']} 字({tot['disc_c'] * 100 // tot['chars']}%);"
      f"每轮平均 ctx {tot['cr'] // tot['turns']} token")

# 09-06 三组基线(同一根 AboutUsPage)
print("\n=== 09-06 AboutUsPage 基线")
for lab in ("legacy_about", "cur_about", "raw_about"):
    for mp in sorted(glob.glob(os.path.join(EXP, "runs", lab, "chain*", "rep*", "metrics.json"))):
        m = json.load(open(mp, encoding="utf-8")); tr = m["transcript"]; u = tr["usage"]
        seq = tr["seq"]
        disc_n = disc_c = 0
        for s in seq:
            cmd = str((s.get("input") or {}).get("command", ""))
            if lab != "raw_about" or FIXER in cmd:
                break
            disc_n += 1; disc_c += s["chars"]
        print(f"{lab:<13} rep{m['rep']}: 轮 {m['num_turns']:>2} 次 {tr['tool_calls']:>2} 字 {tr['tool_chars']:>6} ${m['cost_usd']:.2f} "
              f"每轮ctx {u['cache_read'] // max(m['num_turns'], 1):>6} out {u['output']:>5}"
              + (f" 找人 {disc_n}/{disc_c}" if lab == "raw_about" else ""))
