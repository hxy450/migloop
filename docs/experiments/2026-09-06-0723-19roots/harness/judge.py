"""盲评:同一条链的两份归因报告(工具组 vs 原始转录组),随机打乱成 A/B 交给 Opus 判,评委不知道来源。
用法: python judge.py <label_treat> <label_control> [chain...]   输出 runs/judge/<treat>_vs_<control>.json 与汇总表。"""
from __future__ import annotations

import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
CLAUDE = shutil.which("claude") or "claude"

JUDGE_PROMPT = """你是归因报告的评审。下面是关于**同一条返修链**(同一个被修文件)的两份归因报告 A 和 B,
出自两种不同的调查方法,你不知道哪份来自哪种方法,也不要猜。请只依据报告本身判断。

评审维度:
1. 定性是否一致(两份的「定性」是否指向同一类根因;主标签不同但事实分析一致也算一致,请说明)。
2. 证据具体度(1–5):证据链是否引用了具体、可回查的位置(文件/版本/记录号/行号/时间),还是泛泛而谈。
3. 内部一致性(1–5):报告内部有没有自相矛盾、结论超出证据、或明显无法核实的断言。
4. 事实冲突:两份报告在事实层面有没有互相矛盾之处,逐条列出(没有就空)。
5. 哪份更可信(A / B / tie),一句话理由。

只输出一个 JSON 对象,不要别的文字:
{"agree": true|false, "agree_note": "...", "a_specificity": n, "b_specificity": n,
 "a_consistency": n, "b_consistency": n, "conflicts": ["..."], "preferred": "A"|"B"|"tie", "reason": "..."}

===== 报告 A =====
{A}

===== 报告 B =====
{B}
"""


def load_result(label: str, chain: int) -> tuple[str, dict] | None:
    hits = glob.glob(os.path.join(EXP, "runs", label, f"chain{chain:02d}-*", "rep1", "result.json"))
    if not hits:
        return None
    r = json.load(open(hits[0], encoding="utf-8"))
    m = json.load(open(hits[0].replace("result.json", "metrics.json"), encoding="utf-8"))
    return str(r.get("result") or ""), m


def judge_one(a: str, b: str) -> dict:
    prompt = JUDGE_PROMPT.replace("{A}", a).replace("{B}", b)
    proc = subprocess.run([CLAUDE, "-p", "--model", "opus", "--max-turns", "2", "--output-format", "json"],
                          input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=900)
    res = json.loads(proc.stdout)
    txt = str(res.get("result") or "")
    m = re.search(r"\{.*\}", txt, re.S)
    verdict = json.loads(m.group(0)) if m else {"error": txt[:300]}
    verdict["_cost"] = res.get("total_cost_usd")
    return verdict


def main() -> None:
    treat, control = sys.argv[1], sys.argv[2]
    chains = [int(x) for x in sys.argv[3:]] or sorted(
        int(os.path.basename(p)[5:7]) for p in glob.glob(os.path.join(EXP, "runs", treat, "chain*")))
    rng = random.Random(20260904)
    out = []
    for ch in chains:
        t, c = load_result(treat, ch), load_result(control, ch)
        if not t or not c or t[1].get("is_error") or c[1].get("is_error"):
            print(f"chain {ch}: missing or errored result, skip")
            continue
        treat_is_a = rng.random() < 0.5
        a, b = (t[0], c[0]) if treat_is_a else (c[0], t[0])
        v = judge_one(a, b)
        pref = v.get("preferred")
        pref_method = ("treat" if (pref == "A") == treat_is_a else "control") if pref in ("A", "B") else "tie"
        row = {"chain": ch, "file": t[1]["file"].rsplit("/", 1)[-1], "treat_is_A": treat_is_a,
               "verdict": v, "preferred_method": pref_method,
               "treat": {k: t[1].get(k) for k in ("cost_usd", "num_turns", "wall_s", "verdict")}
               | {"usage": (t[1].get("transcript") or {}).get("usage"),
                  "calls": (t[1].get("transcript") or {}).get("tool_calls")},
               "control": {k: c[1].get(k) for k in ("cost_usd", "num_turns", "wall_s", "verdict")}
               | {"usage": (c[1].get("transcript") or {}).get("usage"),
                  "calls": (c[1].get("transcript") or {}).get("tool_calls")}}
        out.append(row)
        spec = (v.get("a_specificity"), v.get("b_specificity")) if treat_is_a else (v.get("b_specificity"), v.get("a_specificity"))
        cons = (v.get("a_consistency"), v.get("b_consistency")) if treat_is_a else (v.get("b_consistency"), v.get("a_consistency"))
        print(f"chain {ch} {row['file']}: agree={v.get('agree')} 具体度 工具={spec[0]} 原始={spec[1]} "
              f"一致性 工具={cons[0]} 原始={cons[1]} 更可信={pref_method} | 冲突 {len(v.get('conflicts') or [])}")
        print("   ", str(v.get("agree_note") or "")[:200])
        print("   ", str(v.get("reason") or "")[:200])
        for cf in (v.get("conflicts") or [])[:4]:
            print("    冲突:", str(cf)[:200])
    os.makedirs(os.path.join(EXP, "runs", "judge"), exist_ok=True)
    json.dump(out, open(os.path.join(EXP, "runs", "judge", f"{treat}_vs_{control}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
