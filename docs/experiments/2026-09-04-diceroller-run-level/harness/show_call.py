"""打印某次运行里第 n 次工具调用的结果原文:python show_call.py <label> <n> [max_chars]"""
from __future__ import annotations

import json
import os
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
label, n = sys.argv[1], int(sys.argv[2])
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 6000
calls: dict[str, dict] = {}
order: list[str] = []
for line in open(os.path.join(EXP, "runs", label, "chain00-RUN", "rep1", "transcript.jsonl"), encoding="utf-8"):
    try:
        r = json.loads(line)
    except json.JSONDecodeError:
        continue
    msg = r.get("message") or {}
    content = msg.get("content") if isinstance(msg.get("content"), list) else []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_use":
            order.append(b["id"])
            calls[b["id"]] = {"in": b.get("input"), "out": ""}
        if b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
            c = b.get("content")
            calls[b["tool_use_id"]]["out"] = c if isinstance(c, str) else "\n".join(
                x.get("text", "") for x in c if isinstance(x, dict))
out = calls[order[n - 1]]["out"]
print(out[:limit])
print("... total chars:", len(out), "lines:", out.count("\n"))
