"""按环盲评:同一根的两份链报告(工具组 vs 原始组)随机成 A/B 交给 Opus,比的是链本身,不是结论一句话。
用法: python judge_chain.py <label_treat> <label_control> [chain...]  → runs/judge/<treat>_vs_<control>.chain.json"""
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

JUDGE_PROMPT = """你是迁移返修归因报告的评审。下面是关于**同一个被修文件**的两份链报告 A 和 B,出自两种不同的调查方法,
你不知道哪份来自哪种方法,也不要猜。只依据报告本身判断。两份报告都被要求:从被改的代码往回追,每环写「谁、凭什么、判定
(传递 / 错 / 缺)」,追到池外输入 / 批量生成脚本 / 技能定义为止,指出故障进入点和修复侧多看到的。

逐项回答:
1. 各找到几环、追到了什么叶子(池外输入 / 脚本 / 技能定义 / 停在中间)。
2. 两份报告在哪些环指向同一个节点(同一个 agent 的同一次写、同一份 spec 的同一处)?在这些共同环上判定是否一致?
3. 故障进入点是否同一环?若不同,哪份的进入点更站得住(理由要引报告里的证据)。
4. 坐标可核性(1–5):每个断言是否指向具体、可回查的位置(文件 / 版本 / 记录号 / 行号 / 时间);泛泛而谈算低。
5. 内部一致性(1–5):有没有自相矛盾、结论超出证据、把范围有限的零命中说成全局否定。
6. 事实冲突:两份在事实层面互相矛盾之处,逐条列(没有就空)。
7. 哪份更可信(A / B / tie),一句话理由;哪份对「生成期该改什么流程」更有用(A / B / tie)。

只输出一个 JSON 对象,不要别的文字:
{"a_links": n, "b_links": n, "a_leaf": "...", "b_leaf": "...", "shared_links": n, "shared_verdict_agree": n,
 "same_entry": true|false, "entry_note": "...", "a_checkable": n, "b_checkable": n, "a_consistency": n, "b_consistency": n,
 "conflicts": ["..."], "preferred": "A"|"B"|"tie", "reason": "...", "more_actionable": "A"|"B"|"tie"}

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


def side(v: dict, key: str, treat_is_a: bool) -> tuple:
    a, b = v.get(f"a_{key}"), v.get(f"b_{key}")
    return (a, b) if treat_is_a else (b, a)


def main() -> None:
    treat, control = sys.argv[1], sys.argv[2]
    chains = [int(x) for x in sys.argv[3:]] or sorted(
        int(os.path.basename(p)[5:7]) for p in glob.glob(os.path.join(EXP, "runs", treat, "chain*")))
    rng = random.Random(20260908)
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
        act = v.get("more_actionable")
        act_method = ("treat" if (act == "A") == treat_is_a else "control") if act in ("A", "B") else "tie"
        row = {"chain": ch, "file": t[1]["file"].rsplit("/", 1)[-1], "treat_is_A": treat_is_a, "verdict": v,
               "preferred_method": pref_method, "actionable_method": act_method,
               "treat": {k: t[1].get(k) for k in ("cost_usd", "num_turns", "wall_s")}
               | {"calls": (t[1].get("transcript") or {}).get("tool_calls")},
               "control": {k: c[1].get(k) for k in ("cost_usd", "num_turns", "wall_s")}
               | {"calls": (c[1].get("transcript") or {}).get("tool_calls")}}
        out.append(row)
        links, chk, cons = side(v, "links", treat_is_a), side(v, "checkable", treat_is_a), side(v, "consistency", treat_is_a)
        print(f"chain {ch} {row['file']}: 环数 工具={links[0]} 原始={links[1]} · 共同环 {v.get('shared_links')} 判定一致 "
              f"{v.get('shared_verdict_agree')} · 进入点同环={v.get('same_entry')} · 可核 工具={chk[0]} 原始={chk[1]} · "
              f"一致性 工具={cons[0]} 原始={cons[1]} · 更可信={pref_method} · 更可行动={act_method} · 冲突 {len(v.get('conflicts') or [])}")
        print("   ", str(v.get("entry_note") or "")[:240])
        print("   ", str(v.get("reason") or "")[:240])
    os.makedirs(os.path.join(EXP, "runs", "judge"), exist_ok=True)
    path = os.path.join(EXP, "runs", "judge", f"{treat}_vs_{control}.chain.json")
    # 分批评的结果合并进同一个文件(同一根以最新一次为准)
    prev = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    done = {r["chain"] for r in out}
    merged = [r for r in prev if r["chain"] not in done] + out
    json.dump(sorted(merged, key=lambda r: r["chain"]), open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
