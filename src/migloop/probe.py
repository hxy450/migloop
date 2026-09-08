"""调查覆盖:把一次调查员(模型)的跑叠到探索树上 ——
它每一次工具调用落到哪个节点(文件@版 / agent@版),它报告里每一环指到哪个节点、判成什么(传递 / 错 / 缺)、故障进入点是哪一环。
探索树是给人做调查用的;这里只是把模型做的调查在同一棵树上展开:查过的节点打「第 k 步」,判过的节点按判定上色。

输入是 run 目录(run_probe.py 落的 rep1/):metrics.json 里 transcript.seq 是逐次调用(工具名、参数、返回字数),
result.json 里 result 是报告正文。节点键与页面一致:文件用账本里的绝对路径,agent 用账本 id。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from . import atoms, filestory

_VERDICT = re.compile(r"判定[::]\s*(传递|错|缺)")
_LINK = re.compile(r"^环\s*(\d+)[A-Za-z\']?\s*(.*)$")
_ENTRY = re.compile(r"故障进入点[::][^\n]*?环\s*(\d+)")
_FILE_AT = re.compile(r"([\w./-]+\.[A-Za-z0-9]+)@v(\d+)")
_AGENT_ID = re.compile(r"agent-[0-9a-f]+")        # 账本 id 是 16 位 hex,测试里的短 id 也认
_ACTION = re.compile(r"#(\d+)@L\d+")
_RANK = {"错": 3, "缺": 2, "传递": 1}


def _load_run(run_dir: str) -> tuple[dict[str, Any], str]:
    with open(os.path.join(run_dir, "metrics.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as fh:
        r = json.load(fh)
    return m, str(r.get("result") or "")


def _seq_owner(ledger: atoms.Ledger, seq_no: int, aid: str | None = None) -> tuple[str | None, int | None]:
    """动作号 → (agent id, 它喂养或产生的版本)。"""
    for a in ledger.agents.values():
        if aid and a.id != aid:
            continue
        for act in a.actions:
            if act.seq == seq_no:
                return a.id, act.ver if act.ver is not None else act.at
    return None, None


def _int(x: Any) -> int | None:
    try:
        return int(x) if x is not None and str(x).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _step_node(ledger: atoms.Ledger, tool: str, inp: dict[str, Any]) -> dict[str, Any] | None:
    fk = lambda h: filestory.find_story_path(ledger.stories, str(h)) if h else None  # noqa: E731
    ak = lambda h: (atoms.resolve_agent(ledger, str(h)) or None) if h else None  # noqa: E731
    if tool in ("file", "diff", "blame"):
        return {"kind": "file", "path": fk(inp.get("path")), "v": _int(inp.get("v"))}
    if tool == "agent":
        a = ak(inp.get("id"))
        return {"kind": "agent", "aid": a.id if a else None, "v": _int(inp.get("v")), "since": _int(inp.get("since"))}
    if tool == "action":
        a = ak(inp.get("id"))
        aid, ver = _seq_owner(ledger, _int(inp.get("seq")) or -1, a.id if a else None)
        return {"kind": "agent", "aid": aid, "v": ver, "action": _int(inp.get("seq"))}
    if tool == "search":
        if inp.get("agent"):
            a = ak(inp.get("agent"))
            return {"kind": "agent", "aid": a.id if a else None, "v": _int(inp.get("v")), "q": inp.get("q")}
        if inp.get("file"):
            return {"kind": "file", "path": fk(inp.get("file")), "v": _int(inp.get("v")), "q": inp.get("q")}
        return {"kind": "pool", "q": inp.get("q"), "until_ts": inp.get("until_ts"), "since_ts": inp.get("since_ts")}
    if tool == "sessions":
        return {"kind": "chain", "path": fk(inp.get("path")) if inp.get("path") else None}
    return None


def _link_nodes(ledger: atoms.Ledger, body: str) -> list[dict[str, Any]]:
    """环正文里的坐标按出现位置排:第一个是这一环的主语(判定落在它身上),其余只是「提到」。"""
    found: list[tuple[int, dict[str, Any]]] = []
    for m in _FILE_AT.finditer(body):
        k = filestory.find_story_path(ledger.stories, m.group(1))
        if k:
            found.append((m.start(), {"kind": "file", "path": k, "v": int(m.group(2))}))
    seen_agents: set[str] = set()
    for m in _AGENT_ID.finditer(body):
        aid = m.group(0)
        if aid in seen_agents:
            continue
        seen_agents.add(aid)
        a = atoms.resolve_agent(ledger, aid)
        vm = re.search(re.escape(aid) + r"\)?\s*v(\d+)", body)
        if a:
            found.append((m.start(), {"kind": "agent", "aid": a.id, "v": int(vm.group(1)) if vm else None}))
    for m in _ACTION.finditer(body):
        owner, ver = _seq_owner(ledger, int(m.group(1)))
        if owner:
            found.append((m.start(), {"kind": "agent", "aid": owner, "v": ver, "action": int(m.group(1))}))
    found.sort(key=lambda x: x[0])
    return [n for _pos, n in found]


def probe_payload(ledger: atoms.Ledger, run_dir: str) -> dict[str, Any]:
    m, report = _load_run(run_dir)
    seq = (m.get("transcript") or {}).get("seq") or []
    steps: list[dict[str, Any]] = []
    for i, s in enumerate(seq, 1):
        inp = {k: v for k, v in (s.get("input") or {}).items() if k != "sid"}
        steps.append({"i": i, "tool": s.get("tool"), "args": inp, "chars": s.get("chars") or 0,
                      "node": _step_node(ledger, str(s.get("tool")), inp)})
    entry = _ENTRY.search(report)
    entry_no = int(entry.group(1)) if entry else None
    links: list[dict[str, Any]] = []
    for ln in report.split("\n"):
        mm = _LINK.match(ln)
        if not mm:
            continue
        no, body = int(mm.group(1)), mm.group(2)
        vd = _VERDICT.search(body)
        links.append({"no": no, "verdict": vd.group(1) if vd else None, "entry": no == entry_no,
                      "text": body[:400], "nodes": _link_nodes(ledger, body)})
    # 节点 → 判定:只算它当主语的环(正文第一个坐标);同一节点被几环判过取最重(错 > 缺 > 传递)
    verdicts: dict[str, dict[str, Any]] = {}
    for lk in links:
        lk_nodes: list[dict[str, Any]] = list(lk["nodes"])
        subject: dict[str, Any] | None = lk_nodes[0] if lk_nodes else None
        verdict: str | None = str(lk["verdict"]) if lk["verdict"] else None
        if subject is None or verdict is None:
            continue
        key = str(subject.get("path") or subject.get("aid") or "")
        if not key:
            continue
        cur = verdicts.get(key)
        if cur is None or _RANK[verdict] > _RANK[str(cur["verdict"])]:
            verdicts[key] = {"kind": subject["kind"], "verdict": verdict, "links": [lk["no"]], "entry": bool(lk["entry"]), "v": subject.get("v")}
        elif lk["no"] not in cur["links"]:
            cur["links"].append(lk["no"])
            cur["entry"] = bool(cur["entry"] or lk["entry"])
    root = next((s["node"].get("path") for s in steps if s["node"] and s["node"].get("kind") == "chain" and s["node"].get("path")), None)
    fm = re.search(r"文件[::]\s*([^\s(（]+)", report)
    if not root and fm:
        root = filestory.find_story_path(ledger.stories, fm.group(1))
    return {"run": os.path.basename(os.path.dirname(os.path.abspath(run_dir))), "cost": m.get("cost_usd"), "turns": m.get("num_turns"),
            "root": root, "steps": steps, "links": links, "entry": entry_no, "verdicts": verdicts, "report": report}
