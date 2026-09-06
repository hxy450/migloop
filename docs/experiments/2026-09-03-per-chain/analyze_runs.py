"""汇总 runs/ 下的实验:每次运行一行 + 按 label 聚合的 token 画像(钱花在哪个工具、哪几次调用)。
用法: python analyze_runs.py [label ...]   不给 label 就全看。"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict

EXP = os.path.dirname(os.path.abspath(__file__))


def load(labels: list[str]) -> list[dict]:
    rows = []
    for p in glob.glob(os.path.join(EXP, "runs", "*", "*", "*", "metrics.json")):
        m = json.load(open(p, encoding="utf-8"))
        if labels and m.get("label") not in labels:
            continue
        m["_dir"] = os.path.dirname(p)
        rows.append(m)
    rows.sort(key=lambda m: (m.get("label"), m.get("chain"), m.get("rep")))
    return rows


def fmt_k(n) -> str:
    return "-" if n is None else (f"{n / 1000:.1f}k" if n >= 1000 else str(n))


def main() -> None:
    labels = sys.argv[1:]
    rows = load(labels)
    if not rows:
        print("no runs")
        return
    print(f"{'label':<10} {'ch':>2} {'file':<26} {'calls':>5} {'toolK':>6} {'in':>6} {'cacheR':>7} {'cacheC':>7} "
          f"{'out':>6} {'cost$':>6} {'wall':>5} verdict")
    for m in rows:
        tr = m.get("transcript") or {}
        u = tr.get("usage") or {}
        print(f"{m['label']:<10} {m['chain']:>2} {str(m['file']).rsplit('/', 1)[-1][:26]:<26} "
              f"{tr.get('tool_calls', '-')!s:>5} {fmt_k(tr.get('tool_chars')):>6} {fmt_k(u.get('input')):>6} "
              f"{fmt_k(u.get('cache_read')):>7} {fmt_k(u.get('cache_create')):>7} {fmt_k(u.get('output')):>6} "
              f"{(m.get('cost_usd') or 0):>6.2f} {m.get('wall_s', 0):>5.0f} "
              f"{'ERR ' if m.get('is_error') else ''}{(m.get('verdict') or '')[:40]}")

    by_label: dict[str, list[dict]] = defaultdict(list)
    for m in rows:
        by_label[m["label"]].append(m)
    for label, ms in by_label.items():
        print(f"\n== {label}: {len(ms)} runs ==")
        tool_n: dict[str, int] = defaultdict(int)
        tool_chars: dict[str, int] = defaultdict(int)
        top: list[tuple[int, str, dict, str]] = []
        cost = calls = chars = 0
        toks = defaultdict(int)
        agent_main_nosince = 0
        for m in ms:
            tr = m.get("transcript") or {}
            cost += float(m.get("cost_usd") or 0)
            calls += int(tr.get("tool_calls") or 0)
            chars += int(tr.get("tool_chars") or 0)
            for k, v in (tr.get("usage") or {}).items():
                toks[k] += int(v or 0)
            for rec in tr.get("seq") or []:
                tool_n[rec["tool"]] += 1
                tool_chars[rec["tool"]] += rec["chars"]
                top.append((rec["chars"], rec["tool"], rec["input"], str(m["file"]).rsplit("/", 1)[-1]))
                if rec["tool"] == "agent" and str(rec["input"].get("id", "")).startswith("__main__") \
                        and rec["input"].get("since") is None:
                    agent_main_nosince += 1
        print(f"总费用 ${cost:.2f} · 工具调用 {calls} 次 · 工具返回 {fmt_k(chars)} 字符 · "
              f"token in {fmt_k(toks['input'])} cacheR {fmt_k(toks['cache_read'])} cacheC {fmt_k(toks['cache_create'])} "
              f"out {fmt_k(toks['output'])}")
        print(f"{'工具':<10} {'次数':>4} {'字符':>8} {'占比':>6} {'均值':>7}")
        for t, c in sorted(tool_chars.items(), key=lambda kv: -kv[1]):
            print(f"{t:<10} {tool_n[t]:>4} {c:>8} {c / max(chars, 1):>6.0%} {c // max(tool_n[t], 1):>7}")
        print(f"主会话 agent() 不带 since 的调用: {agent_main_nosince}")
        print("最大的 10 次返回:")
        for chars_, tool, inp, f in sorted(top, key=lambda x: -x[0])[:10]:
            print(f"  {chars_:>7} {tool:<8} {f:<24} {json.dumps(inp, ensure_ascii=False)[:90]}")
        verdicts = defaultdict(int)
        for m in ms:
            verdicts[(m.get("verdict") or "?").split("(")[0].split(" ")[0][:12]] += 1
        print("定性分布:", dict(verdicts))


if __name__ == "__main__":
    main()
