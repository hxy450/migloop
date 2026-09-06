"""run 级盲评:同一次迁移的两份返修调查报告(工具组 vs 原始组),随机打乱成 A/B 交给 Opus 判,评委不知来源。
用法: python judge_run.py <label_treat> <label_control> [--reps k]   输出 runs/judge/run_<treat>_vs_<control>.json
两种引用坐标系(工具坐标 path@v / agent vK / #n;原文坐标 文件:行 / uuid+时刻)在评审里同等对待。"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import shutil
import subprocess

EXP = os.path.dirname(os.path.abspath(__file__))
CLAUDE = shutil.which("claude") or "claude"

JUDGE_PROMPT = """你是返修调查报告的评审。下面是关于**同一次 Android→HarmonyOS 迁移**(同一份实录)的两份调查报告 A 和 B,
出自两种不同的调查方法,你不知道哪份来自哪种方法,也不要猜。只依据报告本身判断。

背景口径:生成期结束时刻之后对 entry/src/main/**/*.ets 的所有写入都是修复;一个文件可被几拨修复方分段改,每段单独归因。
两种引用坐标系同等有效、都算"可回查":工具坐标(path@v / agent vK / #n)与原文坐标(文件名:行号 / uuid + 时间戳)。
不要因为坐标形式不同而给分不同,只看是否具体到一个能回查的位置。

评审维度:
1. 覆盖:各自列出了哪些修复段(文件 + 修复方 + 时段);A 有 B 没有的、B 有 A 没有的,逐条列出。
2. 共同段的归因是否一致(定性与事实分析指向同一根因算一致;主标签不同但事实一致也算,请说明)。
3. 证据具体度(1–5):证据是否具体到可回查的位置,还是泛泛而谈。
4. 内部一致性(1–5):有没有自相矛盾、结论超出证据、明显无法核实的断言。
5. 事实冲突:两份在事实层面互相矛盾之处,逐条列出(没有就空)。
6. 根因归并质量(1–5):是否把各段归到真正的上游根因、"管线该改哪一环"是否具体可落地。
7. 哪份更可信、更有用(A / B / tie),一句话理由。

只输出一个 JSON 对象,不要别的文字:
{"a_segments": ["..."], "b_segments": ["..."], "only_a": ["..."], "only_b": ["..."],
 "agree_on_shared": true|false, "agree_note": "...",
 "a_specificity": n, "b_specificity": n, "a_consistency": n, "b_consistency": n,
 "a_rootcause": n, "b_rootcause": n, "conflicts": ["..."], "preferred": "A"|"B"|"tie", "reason": "..."}

===== 报告 A =====
{A}

===== 报告 B =====
{B}
"""


def load_result(label: str, rep: int) -> tuple[str, dict] | None:
    hits = glob.glob(os.path.join(EXP, "runs", label, "chain00-RUN", f"rep{rep}", "result.json"))
    if not hits:
        return None
    r = json.load(open(hits[0], encoding="utf-8"))
    m = json.load(open(hits[0].replace("result.json", "metrics.json"), encoding="utf-8"))
    return str(r.get("result") or ""), m


def judge_one(a: str, b: str) -> dict:
    prompt = JUDGE_PROMPT.replace("{A}", a).replace("{B}", b)
    proc = subprocess.run([CLAUDE, "-p", "--model", "opus", "--max-turns", "2", "--output-format", "json"],
                          input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=1200)
    res = json.loads(proc.stdout)
    txt = str(res.get("result") or "")
    m = re.search(r"\{.*\}", txt, re.S)
    verdict = json.loads(m.group(0)) if m else {"error": txt[:300]}
    verdict["_cost"] = res.get("total_cost_usd")
    return verdict


def _side(m: dict) -> dict:
    tr = m.get("transcript") or {}
    return {k: m.get(k) for k in ("cost_usd", "num_turns", "wall_s")} | {
        "usage": tr.get("usage"), "calls": tr.get("tool_calls"), "per_tool": tr.get("per_tool")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("treat")
    ap.add_argument("control")
    ap.add_argument("--reps", type=int, default=1)
    args = ap.parse_args()
    rng = random.Random(20260904)
    out = []
    for rep in range(1, args.reps + 1):
        t, c = load_result(args.treat, rep), load_result(args.control, rep)
        if not t or not c or t[1].get("is_error") or c[1].get("is_error"):
            print(f"rep {rep}: missing or errored result, skip")
            continue
        treat_is_a = rng.random() < 0.5
        a, b = (t[0], c[0]) if treat_is_a else (c[0], t[0])
        v = judge_one(a, b)
        pref = v.get("preferred")
        pref_method = ("treat" if (pref == "A") == treat_is_a else "control") if pref in ("A", "B") else "tie"
        row = {"rep": rep, "treat_is_A": treat_is_a, "verdict": v, "preferred_method": pref_method,
               "treat": _side(t[1]), "control": _side(c[1])}
        out.append(row)

        def pick(key: str) -> tuple:
            av, bv = v.get(f"a_{key}"), v.get(f"b_{key}")
            return (av, bv) if treat_is_a else (bv, av)
        spec, cons, rc = pick("specificity"), pick("consistency"), pick("rootcause")
        only_t, only_c = (v.get("only_a"), v.get("only_b")) if treat_is_a else (v.get("only_b"), v.get("only_a"))
        print(f"rep {rep}: 共同段一致={v.get('agree_on_shared')} 具体度 工具={spec[0]} 原始={spec[1]} "
              f"一致性 工具={cons[0]} 原始={cons[1]} 根因 工具={rc[0]} 原始={rc[1]} 更可信={pref_method} "
              f"| 冲突 {len(v.get('conflicts') or [])} | 只有工具组: {len(only_t or [])} 只有原始组: {len(only_c or [])}")
        print("   ", str(v.get("agree_note") or "")[:300])
        print("   ", str(v.get("reason") or "")[:300])
        for cf in (v.get("conflicts") or [])[:5]:
            print("    冲突:", str(cf)[:200])
        for s in (only_t or [])[:5]:
            print("    只有工具组:", str(s)[:160])
        for s in (only_c or [])[:5]:
            print("    只有原始组:", str(s)[:160])
    os.makedirs(os.path.join(EXP, "runs", "judge"), exist_ok=True)
    json.dump(out, open(os.path.join(EXP, "runs", "judge", f"run_{args.treat}_vs_{args.control}.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
