"""账本索引覆盖对账:一份转录里每种记录多少条,账本里有动作号(可展开)的多少条,漏的是什么。"""
from __future__ import annotations

import collections
import json
import os
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

RAW = "C:/Users/hongy/.claude/projects/-Users-chenjiamin-arkTs-arkts-pilot-project-aippt-version-aippt-0723"
p = service.locate_session("ff019d8a")
led = service.session_ledger(p)

TARGETS = [("agent-a68daf720e780b4c2", "ff019d8a-5172-4cdd-8ce3-77a21682c1b6/subagents/agent-a68daf720e780b4c2.jsonl"),
           ("agent-aconv-aboutus-02480823d9520ea1", "9b3105a2-85ec-4889-9786-b3c220f06754/subagents/agent-aconv-aboutus-02480823d9520ea1.jsonl"),
           ("__main__:9b3105a2", "9b3105a2-85ec-4889-9786-b3c220f06754.jsonl")]
for aid, rel in TARGETS:
    a = led.agents.get(aid)
    covered_lines: set[int] = set()
    for act in a.actions:
        if act.src:
            covered_lines.add(act.src[1])
            if act.src[2]:
                covered_lines.add(act.src[2])
    kinds_led = collections.Counter(act.kind for act in a.actions)
    rec = collections.Counter()
    miss = collections.Counter()
    miss_chars = collections.Counter()
    for i, line in enumerate(open(os.path.join(RAW, rel), encoding="utf-8")):     # src 里的行号是 0 起的
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("type")
        c = (d.get("message") or {}).get("content")
        if t == "assistant" and isinstance(c, list):
            for b in c:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "tool_use":
                    rec["工具调用"] += 1
                    if i not in covered_lines:
                        miss["工具调用"] += 1
                elif bt == "text":
                    rec["assistant 正文"] += 1
                    if i not in covered_lines:
                        miss["assistant 正文"] += 1
                        miss_chars["assistant 正文"] += len(b.get("text") or "")
                elif bt == "thinking":
                    rec["thinking"] += 1
                    if i not in covered_lines:
                        miss["thinking"] += 1
                        miss_chars["thinking"] += len(b.get("thinking") or "")
        elif t == "user":
            if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                rec["工具结果"] += 1
                if i not in covered_lines:
                    miss["工具结果"] += 1
            else:
                s = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                key = "user 消息(派发词/收件/系统提示)"
                rec[key] += 1
                if i not in covered_lines:
                    miss[key] += 1
                    miss_chars[key] += len(s)
        elif t in ("system", "summary", "queue-operation"):
            rec[f"{t} 记录"] += 1
            miss[f"{t} 记录"] += 1
    print(f"\n=== {a.name or aid}  账本动作 {len(a.actions)} 条(种类 {dict(kinds_led)})")
    print(f"  {'记录种类':<28}{'转录里':>7}{'账本无编号':>9}{'漏掉的字数':>10}")
    for k, v in rec.most_common():
        print(f"  {k:<28}{v:>7}{miss[k]:>9}{miss_chars[k]:>10}")
    # user 消息里,账本以 prompt / inbox 形式持有的
    n_inbox = sum(1 for act in a.actions if act.kind == "inbox")
    print(f"  其中账本持有:派发词 {'有' if a.prompt else '无'}({len(a.prompt or '')} 字),收件 {n_inbox} 条,收尾 {len(a.result or '')} 字")
