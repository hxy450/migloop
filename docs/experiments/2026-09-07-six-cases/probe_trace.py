"""调查轨迹:一次工具组跑的转录(每次 MCP 调用)+ 报告(每环的坐标与判定)→ 探索树能吃的 probe JSON。
节点键与 fixchain.html 一致:文件 = 绝对路径 + 版本(空 = 整个生命周期),agent = 账本 id + 版本。
用法: python probe_trace.py <sid> <run_dir> <out.json>"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import atoms, filestory, service  # noqa: E402

sid, run, out = sys.argv[1], sys.argv[2], sys.argv[3]
p = service.locate_session(sid)
led = service.session_ledger(p)
m = json.load(open(os.path.join(run, "metrics.json"), encoding="utf-8"))
r = json.load(open(os.path.join(run, "result.json"), encoding="utf-8"))
seq = (m.get("transcript") or {}).get("seq") or []


def file_key(hint: str | None) -> str | None:
    if not hint:
        return None
    return filestory.find_story_path(led.stories, str(hint))


def agent_key(hint: str | None) -> str | None:
    if not hint:
        return None
    a = atoms.resolve_agent(led, str(hint))
    return a.id if a else None


def seq_agent_ver(aid: str | None, seq_no: int | None) -> tuple[str | None, int | None]:
    """动作号 → 它属于哪个 agent 的第几版(效应号或喂养的版本)。"""
    if seq_no is None:
        return None, None
    for a in led.agents.values():
        if aid and a.id != aid:
            continue
        for act in a.actions:
            if act.seq == seq_no:
                return a.id, act.ver if act.ver is not None else act.at
    return None, None


steps = []
for i, s in enumerate(seq, 1):
    t, inp = s["tool"], s["input"]
    node = None
    if t in ("file", "diff", "blame"):
        node = {"kind": "file", "path": file_key(inp.get("path")), "v": inp.get("v")}
    elif t == "agent":
        node = {"kind": "agent", "aid": agent_key(inp.get("id")), "v": inp.get("v"), "since": inp.get("since")}
    elif t == "action":
        aid, ver = seq_agent_ver(agent_key(inp.get("id")), int(inp["seq"]) if str(inp.get("seq", "")).isdigit() else None)
        node = {"kind": "agent", "aid": aid, "v": ver, "action": inp.get("seq")}
    elif t == "search":
        if inp.get("agent"):
            node = {"kind": "agent", "aid": agent_key(inp.get("agent")), "v": inp.get("v"), "q": inp.get("q")}
        elif inp.get("file"):
            node = {"kind": "file", "path": file_key(inp.get("file")), "v": inp.get("v"), "q": inp.get("q")}
        else:
            node = {"kind": "pool", "q": inp.get("q"), "until_ts": inp.get("until_ts")}
    elif t == "sessions":
        node = {"kind": "chain", "path": file_key(inp.get("path")) if inp.get("path") else None}
    steps.append({"i": i, "tool": t, "args": {k: v for k, v in inp.items() if k != "sid"}, "chars": s.get("chars"), "node": node})

# 报告的环 → 节点 + 判定
text = str(r.get("result") or "")
links = []
entry = re.search(r"故障进入点[::]\s*环\s*(\d+)", text)
entry_no = int(entry.group(1)) if entry else None
for ln in text.split("\n"):
    mm = re.match(r"^环\s*(\d+)[A-Za-z']?\s*(.*)$", ln)
    if not mm:
        continue
    no, body = int(mm.group(1)), mm.group(2)
    verdict = re.search(r"判定[::]\s*(传递|错|缺)", body)
    nodes = []
    for path, v in re.findall(r"([\w./-]+\.[A-Za-z0-9]+)@v(\d+)", body):
        k = file_key(path)
        if k:
            nodes.append({"kind": "file", "path": k, "v": int(v)})
    for aid in set(re.findall(r"agent-[0-9a-f]{12,}", body)):
        vm = re.search(re.escape(aid) + r"\)?\s*v(\d+)", body)
        nodes.append({"kind": "agent", "aid": agent_key(aid), "v": int(vm.group(1)) if vm else None})
    for seq_no in re.findall(r"#(\d+)@L\d+", body):
        aid, ver = seq_agent_ver(None, int(seq_no))
        if aid:
            nodes.append({"kind": "agent", "aid": aid, "v": ver, "action": int(seq_no)})
    links.append({"no": no, "verdict": verdict.group(1) if verdict else None, "entry": no == entry_no,
                  "text": body[:300], "nodes": nodes})
probe = {"sid": sid, "run": os.path.basename(os.path.dirname(run)), "cost": m.get("cost_usd"), "turns": m.get("num_turns"),
         "steps": steps, "links": links, "entry": entry_no}
json.dump(probe, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
anchored = sum(1 for s in steps if s["node"] and s["node"].get("kind") in ("file", "agent") and (s["node"].get("path") or s["node"].get("aid")))
print(f"steps {len(steps)} 落到节点 {anchored};links {len(links)} 带节点 {sum(1 for l in links if l['nodes'])} 带判定 {sum(1 for l in links if l['verdict'])};进入点 环 {entry_no}")
