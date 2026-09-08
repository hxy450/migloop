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
_ENTRY = re.compile(r"故障进入点[::]")
_RING = re.compile(r"环\s*(\d+)")
_ENTRY_ALSO = re.compile(r"进入点是\s*环\s*(\d+)")     # 几条缺陷各自进入时,报告会逐条说「…的进入点是环 N」
_FILE_AT = re.compile(r"([\w./-]+\.[A-Za-z0-9]+)@v(\d+)")
_AGENT_ID = re.compile(r"agent-[0-9a-f]+")        # 账本 id 是 16 位 hex,测试里的短 id 也认
_ACTION = re.compile(r"#(\d+)@L\d+")
_MAIN_AT = re.compile(r"主会话[·:]?\s*([0-9a-f]{6,})?\s*@?v(\d+)")   # 报告写主会话不用 agent- id:「主会话·9b3105a2 @v83」
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


def _main_id(ledger: atoms.Ledger, sid: str | None) -> str | None:
    """「主会话·9b3105a2」→ 账本 id __main__:<sid8>;不带会话号只在池子里只有一个主会话时认。"""
    mains = [k for k in ledger.agents if k.startswith("__main__")]
    if sid:
        hit = [k for k in mains if k.split(":", 1)[-1].startswith(sid) or sid.startswith(k.split(":", 1)[-1])]
        return hit[0] if len(hit) == 1 else None
    return mains[0] if len(mains) == 1 else None


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
    for m in _MAIN_AT.finditer(body):
        mid = _main_id(ledger, m.group(1))
        if mid:
            found.append((m.start(), {"kind": "agent", "aid": mid, "v": int(m.group(2))}))
    for m in _ACTION.finditer(body):
        owner, ver = _seq_owner(ledger, int(m.group(1)))
        if owner:
            found.append((m.start(), {"kind": "agent", "aid": owner, "v": ver, "action": int(m.group(1))}))
    found.sort(key=lambda x: x[0])
    return [n for _pos, n in found]


def _entries(report: str) -> list[int]:
    """故障进入点:「故障进入点:」之后(可跨行)第一个环号是主进入点;正文里「进入点是环 N」再补几个。"""
    nos: list[int] = []
    m = _ENTRY.search(report)
    if m:
        r = _RING.search(report[m.end():m.end() + 400])
        if r:
            nos.append(int(r.group(1)))
    for a in _ENTRY_ALSO.finditer(report):
        if int(a.group(1)) not in nos:
            nos.append(int(a.group(1)))
    return nos


def probe_payload(ledger: atoms.Ledger, run_dir: str) -> dict[str, Any]:
    m, report = _load_run(run_dir)
    seq = (m.get("transcript") or {}).get("seq") or []
    steps: list[dict[str, Any]] = []
    for i, s in enumerate(seq, 1):
        inp = {k: v for k, v in (s.get("input") or {}).items() if k != "sid"}
        steps.append({"i": i, "tool": s.get("tool"), "args": inp, "chars": s.get("chars") or 0,
                      "node": _step_node(ledger, str(s.get("tool")), inp)})
    entries = _entries(report)
    entry_no = entries[0] if entries else None
    links: list[dict[str, Any]] = []
    for ln in report.split("\n"):
        mm = _LINK.match(ln)
        if not mm:
            continue
        no, body = int(mm.group(1)), mm.group(2)
        vd = _VERDICT.search(body)
        links.append({"no": no, "verdict": vd.group(1) if vd else None, "entry": no in entries,
                      "text": body[:400], "nodes": _link_nodes(ledger, body)})
    # 节点 → 判定:只算它当主语的环(正文第一个坐标),按「节点 + 版本」记,不按 id 连坐(主会话在树上到处出现,
    # 环 9 判的是它 v83 的派发词,v1 / v60 不该跟着红);同一节点同一版被几环判过取最重(错 > 缺 > 传递)
    verdicts: dict[str, list[dict[str, Any]]] = {}
    for lk in links:
        lk_nodes: list[dict[str, Any]] = list(lk["nodes"])
        subject: dict[str, Any] | None = lk_nodes[0] if lk_nodes else None
        verdict: str | None = str(lk["verdict"]) if lk["verdict"] else None
        if subject is None or verdict is None:
            continue
        key = str(subject.get("path") or subject.get("aid") or "")
        if not key:
            continue
        bucket = verdicts.setdefault(key, [])
        cur = next((x for x in bucket if x["v"] == subject.get("v")), None)
        if cur is None:
            bucket.append({"kind": subject["kind"], "v": subject.get("v"), "verdict": verdict, "links": [lk["no"]], "entry": bool(lk["entry"])})
            continue
        if _RANK[verdict] > _RANK[str(cur["verdict"])]:
            cur["verdict"] = verdict
        if lk["no"] not in cur["links"]:
            cur["links"].append(lk["no"])
        cur["entry"] = bool(cur["entry"] or lk["entry"])
    root = next((s["node"].get("path") for s in steps if s["node"] and s["node"].get("kind") == "chain" and s["node"].get("path")), None)
    fm = re.search(r"文件[::]\s*([^\s(（]+)", report)
    if not root and fm:
        root = filestory.find_story_path(ledger.stories, fm.group(1))
    return {"run": os.path.basename(os.path.dirname(os.path.abspath(run_dir))), "cost": m.get("cost_usd"), "turns": m.get("num_turns"),
            "root": root, "steps": steps, "links": links, "entry": entry_no, "entries": entries, "verdicts": verdicts,
            "report": report}
