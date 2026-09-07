"""一组 run 的详细 token 账(按根、按工具、agent 各段、search 问了什么),可与别的组同根对比。
用法: python token_report.py seg4_tools [seg3_tools seg2_tools seg2_raw]"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
MARKS = ["## 派发指令", "## 收件箱", "## 逐版时间线", "## 收尾输出"]


def est(s: str) -> int:
    cjk = sum(1 for ch in s if "一" <= ch <= "鿿")
    return cjk + (len(s) - cjk) // 4


def load(label: str) -> dict[int, dict]:
    out = {}
    for mp in glob.glob(os.path.join(EXP, "runs", label, "chain*", "rep1", "metrics.json")):
        m = json.load(open(mp, encoding="utf-8"))
        m["_dir"] = os.path.dirname(mp)
        out[m["chain"]] = m
    return out


def results(d: str):
    uses: dict[str, tuple[str, dict]] = {}
    for line in open(os.path.join(d, "transcript.jsonl"), encoding="utf-8"):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        for blk in (rec.get("message") or {}).get("content") or []:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "tool_use":
                uses[blk["id"]] = (blk["name"].replace("mcp__migloop__", ""), blk.get("input") or {})
            elif blk.get("type") == "tool_result" and blk.get("tool_use_id") in uses:
                tool, inp = uses[blk["tool_use_id"]]
                c = blk.get("content")
                text = c if isinstance(c, str) else "".join(x.get("text", "") for x in (c or []) if isinstance(x, dict))
                try:
                    text = json.loads(text).get("result", text)
                except Exception:
                    pass
                yield tool, inp, text


main = sys.argv[1]
others = sys.argv[2:]
roots = sorted(load(main))
print(f"===== {main}  根 {roots}")
print(f"{'根':<3}{'文件':<20}{'轮':>3}{'次':>3}{'cache_read':>11}{'cache_new':>10}{'output':>7}{'返回字':>7}{'秒':>5}{'$':>6}")
tot = collections.Counter()
for ch, m in sorted(load(main).items()):
    u = m["transcript"]["usage"]
    print(f"{ch:<3}{str(m['file']).rsplit('/', 1)[-1][:20]:<20}{m['num_turns']:>3}{m['transcript']['tool_calls']:>3}"
          f"{u['cache_read']:>11,}{u['cache_create']:>10,}{u['output']:>7,}{m['transcript']['tool_chars']:>7}"
          f"{m['wall_s']:>5.0f}{m['cost_usd']:>6.2f}")
    for k in ("cache_read", "cache_create", "output"):
        tot[k] += u[k]
    tot["turns"] += m["num_turns"]
    tot["calls"] += m["transcript"]["tool_calls"]
    tot["chars"] += m["transcript"]["tool_chars"]
    tot["wall"] += m["wall_s"]
    tot["cost"] += m["cost_usd"]
n = len(roots)
print(f"合计 轮 {tot['turns']} · 调用 {tot['calls']} · cache_read {tot['cache_read']:,} · cache_new {tot['cache_create']:,} · output {tot['output']:,}"
      f" · 返回 {tot['chars']:,} 字 · {tot['wall'] / 60:.1f} 分 · ${tot['cost']:.2f}")
print(f"每根:轮 {tot['turns'] / n:.1f} · 每轮 cache_read {tot['cache_read'] // tot['turns'] // 1000}K · output {tot['output'] // n // 1000}K · ${tot['cost'] / n:.2f}")

per: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
parts: collections.Counter[str] = collections.Counter()
searches = []
agents = []
for ch, m in load(main).items():
    for tool, inp, text in results(m["_dir"]):
        per[tool][0] += 1
        per[tool][1] += len(text)
        if tool == "search":
            searches.append((ch, {k: v for k, v in inp.items() if k != "sid"}, len(text)))
        if tool == "agent":
            agents.append((ch, {k: v for k, v in inp.items() if k != "sid"}, len(text)))
            pos = {mk: text.find("\n" + mk) for mk in MARKS}
            cuts = sorted((v, mk) for mk, v in pos.items() if v >= 0)
            parts["头部"] += cuts[0][0] if cuts else len(text)
            for i, (v, mk) in enumerate(cuts):
                end = cuts[i + 1][0] if i + 1 < len(cuts) else len(text)
                parts[mk[3:]] += end - v
print(f"\n按工具:{'工具':<9}{'次':>4}{'字':>8}{'≈token':>8}{'均字':>6}")
for tool, (c, ch_) in sorted(per.items(), key=lambda kv: -kv[1][1]):
    print(f"        {tool:<9}{c:>4}{ch_:>8}{int(ch_ / 2.4):>8}{ch_ // max(c, 1):>6}")
s = sum(parts.values()) or 1
print("agent 各段:", {k: f"{v} ({v * 100 // s}%)" for k, v in parts.most_common()})
print("agent 调用:")
for ch, inp, ln in agents:
    print(f"   根{ch} agent({inp.get('id', '')[-18:]}, v={inp.get('v')}, since={inp.get('since')}) {ln} 字")
print("search 调用:")
for ch, inp, ln in searches:
    print(f"   根{ch} {json.dumps(inp, ensure_ascii=False)} → {ln} 字")

for lab in others:
    ms = load(lab)
    c = w = cr = out = turns = calls = chars = 0
    k = 0
    for ch in roots:
        if ch not in ms:
            continue
        m = ms[ch]
        k += 1
        c += m["cost_usd"]
        w += m["wall_s"]
        cr += m["transcript"]["usage"]["cache_read"]
        out += m["transcript"]["usage"]["output"]
        turns += m["num_turns"]
        calls += m["transcript"]["tool_calls"]
        chars += m["transcript"]["tool_chars"]
    if k:
        print(f"\n对比 {lab}(同 {k} 根): ${c:.2f} · {w / 60:.1f} 分 · 轮 {turns} · 调用 {calls} · 每轮 cache_read {cr // turns // 1000}K"
              f" · output {out:,} · 返回 {chars:,} 字")
