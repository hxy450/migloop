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

from . import atoms, filestory, verdict, via

_VERDICT = re.compile(r"判定[::]\s*(传递|错|缺)")
_LINK = re.compile(r"^环\s*(\d+)[A-Za-z\']?\s*(.*)$")
_ENTRY = re.compile(r"故障进入点[::]")
_RING = re.compile(r"环\s*(\d+)")
_ENTRY_ALSO = re.compile(r"进入点是\s*环\s*(\d+)")     # 几条缺陷各自进入时,报告会逐条说「…的进入点是环 N」
_FILE_AT = re.compile(r"([\w./-]+\.[A-Za-z0-9]+)@v(\d+)")
_AGENT_ID = re.compile(r"agent-[0-9a-f]+")        # 账本 id 是 16 位 hex,测试里的短 id 也认
_ACTION = atoms.REF_RE
_DEFECT = re.compile(r"【([A-Za-z0-9])\s*([^】]*)】")     # 【A 返回键】【B 进度条】【C 上游】:字母是缺陷,后面是说明
_MAIN_AT = re.compile(r"主会话[·:]?\s*([0-9a-f]{6,})?\s*@?v(\d+)")   # 报告写主会话不用 agent- id:「主会话·9b3105a2 @v83」
_RANK = {"错": 3, "缺": 2, "传递": 1}


def _step_scope(tool: str, inp: dict[str, Any]) -> str:
    """这一步看到了什么范围:索引 / 正文 vN / 差分 / 搜索窗口 / 原文 —— 蓝框只说明查过这个键,范围在这里。"""
    v = inp.get("v")
    vs = f" v{v}" if v is not None else ""
    if tool == "file":
        if inp.get("diff"):
            return "差分" + vs
        if inp.get("content"):
            rng = f" {inp['start']}-{int(inp['start']) + int(inp.get('n') or 0)}行" if inp.get("start") else ""
            return f"正文{vs}{rng}"
        return "索引" + vs
    if tool == "diff":
        return "差分" + vs
    if tool == "blame":
        return "归属" + vs + ("(只看改动行)" if inp.get("changed") else "")
    if tool == "agent":
        win = f"v{inp['since']}→{v}" if inp.get("since") is not None and v is not None else (vs.strip() or "全程")
        return win + (" 到 " + str(inp["until"]) if inp.get("until") else "") + (" 不含读取" if inp.get("reads") is False else "")
    if tool == "search":
        return "搜索窗口" + vs
    if tool == "action":
        return f"原文 #{inp.get('seq')}" + (f" {inp['part']}" if inp.get("part") else "")
    if tool == "sessions":
        return "返修链"
    return "索引查询"


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


def _link_nodes(ledger: atoms.Ledger, body: str) -> tuple[list[dict[str, Any]], list[str]]:
    """环正文里的坐标按出现位置排:第一个是这一环的主语(判定落在它身上),其余只是「提到」。
    #n@L 要能核回原文:L 与账本记的转录行号对不上的引用不落节点,记进 bad_refs(伪造行号校验失败)。"""
    bad: list[str] = []
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
        tag = m.group(1) or m.group(5)
        hit, status = atoms.resolve_ref(ledger, int(m.group(2)), int(m.group(3)),
                                        int(m.group(4)) if m.group(4) is not None else None, tag)
        if hit is None:
            bad.append(m.group(0) + ("(歧义)" if status == "ambiguous" else ""))
            continue
        no = hit
        owner, ver = _seq_owner(ledger, no)
        if owner:
            found.append((m.start(), {"kind": "agent", "aid": owner, "v": ver, "action": no}))
    found.sort(key=lambda x: x[0])
    return [n for _pos, n in found], bad


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
                      "node": _step_node(ledger, str(s.get("tool")), inp),
                      "ok": not s.get("is_error"), "scope": _step_scope(str(s.get("tool")), inp),
                      "via": str(inp.get("via") or "")})
    entries = _entries(report)
    entry_no = entries[0] if entries else None
    links: list[dict[str, Any]] = []
    defects: dict[str, str] = {}
    for ln in report.split("\n"):
        mm = _LINK.match(ln)
        if not mm:
            continue
        no, body = int(mm.group(1)), mm.group(2)
        vd = _VERDICT.search(body)
        nodes, bad = _link_nodes(ledger, body)
        dm = _DEFECT.search(body)
        defect: str | None = None
        if dm:
            defect = str(dm.group(1))
            desc = str(dm.group(2) or "").strip()
            generic = any(w in desc for w in ("上游", "池外", "入口"))
            if defect not in defects or (not defects[defect] and not generic):
                defects[defect] = "" if generic else desc
        links.append({"no": no, "verdict": vd.group(1) if vd else None, "entry": no in entries,
                      "text": body[:400], "nodes": nodes, "bad_refs": bad, "defect": defect})
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
    structured = _structured(ledger, run_dir, report)
    if structured is not None:
        if structured["defects"]:
            defects = {d["id"]: d["title"] for d in structured["defects"]}
        sr = structured.get("root")
        if sr and sr.get("ok") and sr.get("kind") == "file":
            root = sr["key"]
    return {"run": os.path.basename(os.path.dirname(os.path.abspath(run_dir))), "cost": m.get("cost_usd"), "turns": m.get("num_turns"),
            "root": root, "steps": steps, "links": links, "entry": entry_no, "entries": entries, "verdicts": verdicts,
            "bad_refs": sum(len(lk["bad_refs"]) for lk in links), "defects": defects, "report": report,
            "legacy": structured is None, "structured": structured,
            "roles": (structured or {}).get("roles") or {}, "fixed": (structured or {}).get("fixed") or [],
            "trajectory": _trajectory(ledger, run_dir, steps, root, structured, verdicts)}


def _structured(ledger: atoms.Ledger, run_dir: str, report: str) -> dict[str, Any] | None:
    """harness 落的 verdict.json(带 harness 算的账本身份、修复重试记录)优先;没有就从报告正文里抽结论块。
    没有结论块 → None(legacy 散文);有块但校验失败 → 只带原文与错误,主张不猜。"""
    vp = os.path.join(run_dir, "verdict.json")
    if os.path.isfile(vp):
        with open(vp, encoding="utf-8") as fh:
            vj = json.load(fh)
        data = vj.get("data")
        errors = list(vj.get("errors") or [])
        if data is not None:
            errors = verdict.validate(data)                      # 以当前 schema 再核一遍,不信 harness 的旧结论
            if errors:
                data = None
        if data is None and not vj.get("raw") and not vj.get("found", True):
            return None
        meta = {"kind": vj.get("kind"), "raw": vj.get("raw"), "repaired": vj.get("repaired"),
                "harness_identity": vj.get("harness_identity")}
        return verdict.build(ledger, data, errors, meta)
    lb = verdict.load_block(report)
    if not lb["found"]:
        return None
    return verdict.build(ledger, lb["data"], lb["errors"], {"kind": lb["kind"], "raw": lb["raw"]})


# ═══════════════ 调查树:账本边 + 步号,零推断 ═══════════════
# 节点只有 agent@版本 / file@版本 两种:模型真的查过的 + 结论块点名的,每个一次。
# 结构只用账本里核得出来的关系:写(agent@vK → file@vN)、读(file@vN → agent@vK)、派发(agent → agent)、
# 前一版(同一文件相邻两个在场版本,中间跳过的版本数标出来)。模型的路线只有一种诚实表示:节点上的步号。
# 「出现于 #j」= 那一步的返回文本里含这个坐标,是事实;「模型因为它才走过去」不是事实,所以不画边。
# 根 = 被修文件的最终版本,生成 / 修复的一切都在它上游(左);不在根的上下游锥里的节点单独一列(有账本边照画)。


def _transcript_results(run_dir: str) -> list[str] | None:
    """transcript.jsonl 里按 tool_use 出现顺序的返回文本(与 metrics.transcript.seq 同序);没有转录 → None。"""
    p = os.path.join(run_dir, "transcript.jsonl")
    if not os.path.isfile(p):
        return None
    order: list[str] = []
    texts: dict[str, str] = {}
    with open(p, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            m = r.get("message") if isinstance(r.get("message"), dict) else {}
            content = m.get("content")
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                if r.get("type") == "assistant" and b.get("type") == "tool_use":
                    order.append(str(b.get("id")))
                elif r.get("type") == "user" and b.get("type") == "tool_result":
                    c = b.get("content")
                    if isinstance(c, list):
                        txt = "".join(str(x.get("text") or "") for x in c if isinstance(x, dict))
                    else:
                        txt = c if isinstance(c, str) else ""
                    texts[str(b.get("tool_use_id"))] = _unwrap_result(txt)
    return [texts.get(t, "") for t in order]


def _unwrap_result(txt: str) -> str:
    """MCP 客户端把工具的字符串返回包成 {"result": "..."} 写进转录;拆出来才是模型看到的正文。"""
    if txt.lstrip().startswith('{"result"'):
        try:
            obj = json.loads(txt)
        except json.JSONDecodeError:
            return txt
        if isinstance(obj, dict) and isinstance(obj.get("result"), str):
            return obj["result"]
    return txt


def _sight(text: str, kind: str, key: str, v: int | None, ledger: atoms.Ledger | None) -> tuple[bool, bool]:
    """返回文本里有没有这个节点 → (有这个键, 版本也对上了)。文件按最长能匹配的路径后缀;agent 按 id / 尾段 / 主会话号 / 名字。"""
    if kind == "file":
        parts = [x for x in key.replace("\\", "/").split("/") if x]
        for i in range(len(parts)):
            suf = "/".join(parts[i:])
            if suf in text:
                return True, v is None or f"{suf}@v{v}" in text
        return False, False
    forms: list[str] = []
    if key.startswith("__main__"):
        sid = key.split(":", 1)[1]
        forms = [key, f"主会话·{sid}", sid]
    else:
        forms = [key]
        if key.startswith("agent-") and len(key) >= 14:
            forms.append(key[6:])                          # 尾段够长才单独认,短 id 会撞到别的词
        a = ledger.agents.get(key) if ledger else None
        if a and a.name and len(a.name) >= 4:
            forms.append(a.name)
    for f in forms:
        if f and f in text:
            exact = v is None or re.search(re.escape(f) + r"[^\n]{0,60}?\bv" + str(v) + r"\b", text) is not None
            return True, exact
    return False, False


def _traj_id(kind: str, key: str, v: int | None) -> str:
    return f"{kind}:{key}@{v if v is not None else '-'}"


def _step_landing(s: dict[str, Any]) -> tuple[str, str, int | None] | None:
    n = s.get("node") or {}
    if n.get("kind") == "file" and n.get("path"):
        return "file", str(n["path"]), n.get("v")
    if n.get("kind") == "agent" and n.get("aid"):
        return "agent", str(n["aid"]), n.get("v")
    return None


def _traj_label(ledger: atoms.Ledger, kind: str, key: str, v: int | None) -> str:
    if kind == "file":
        base = key.replace("\\", "/").rsplit("/", 1)[-1]
        return f"{base}@v{v}" if v is not None else f"{base}(索引)"
    name = atoms._agent_label(ledger.agents, key) or key
    return f"{name} v{v}" if v is not None else f"{name}(全程)"


def _n_versions(ledger: atoms.Ledger, kind: str, key: str) -> int:
    if kind == "file":
        st = ledger.stories.get(key)
        return len(st.versions) if st else 0
    a = ledger.agents.get(key)
    return sum(1 for act in a.actions if act.ver is not None) if a else 0


def _upstream_neighbors(ledger: atoms.Ledger, kind: str, key: str, v: int | None) -> set[tuple[str, str, int | None]]:
    """账本里这个节点的上游邻居(精确版本才算):file@v → 写者@写者版本;agent@v → 喂养 ≤v 的确定读取 + 派发者。"""
    out: set[tuple[str, str, int | None]] = set()
    if v is None:
        return out
    if kind == "file":
        st = ledger.stories.get(key)
        if st and 1 <= v <= len(st.versions):
            ver = st.versions[v - 1]
            if ver.by in ledger.agents:
                out.add(("agent", ver.by, ver.by_ver))
        return out
    a = ledger.agents.get(key)
    if a is None:
        return out
    for act in a.actions:
        feed = act.ver if act.ver is not None else act.at
        if feed > v:
            continue
        for ref in act.files:
            if ref.op == "read" and ref.v is not None and ref.certain and not ref.ev.dep:
                out.add(("file", ref.path, ref.v))
    if a.parent and a.parent in ledger.agents:
        out.add(("agent", a.parent, a.parent_ver))
    return out


def _ledger_relation(ledger: atoms.Ledger, a: dict[str, Any], b: dict[str, Any]) -> str | None:
    """a → b 在账本里是不是一条 写 / 读 / 派发 边(只认核成 true 的;候选不算结构)。"""
    if a["v"] is None or b["v"] is None:
        return None
    ra = verdict.resolve_node(ledger, f"{a['kind']}:{a['key']}@v{a['v']}")
    rb = verdict.resolve_node(ledger, f"{b['kind']}:{b['key']}@v{b['v']}")
    if not (ra["ok"] and rb["ok"]):
        return None
    if a["kind"] == "agent" and b["kind"] == "file":
        rel = "写"
    elif a["kind"] == "file" and b["kind"] == "agent":
        rel = "读"
    elif a["kind"] == "agent" and b["kind"] == "agent":
        rel = "派发"
    else:
        return None
    st, _rel, _note = verdict.check_edge(ledger, ra, rb, rel)
    return rel if st == "true" else None


def _trajectory_ledger(ledger: atoms.Ledger, run_dir: str, steps: list[dict[str, Any]], root: str | None,
                structured: dict[str, Any] | None, verdicts: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    texts = _transcript_results(run_dir)
    if texts is None or not root:
        return None
    if len(texts) < len(steps):
        texts = texts + [""] * (len(steps) - len(texts))
    nodes: dict[str, dict[str, Any]] = {}

    def add(kind: str, key: str, v: int | None, source: str) -> dict[str, Any]:
        if v is None and _n_versions(ledger, kind, key) == 1:
            v = 1                                              # 只有一版的键,索引 / 全程查询就是那一版(事实,不是猜)
        nid = _traj_id(kind, key, v)
        n = nodes.get(nid)
        if n is None:
            n = nodes[nid] = {"id": nid, "kind": kind, "key": key, "v": v, "label": _traj_label(ledger, kind, key, v),
                              "source": source, "fixed": False, "opened": [], "appears": [],
                              "parent": None, "edge": None, "skipped": 0, "side": "up", "depth": 0,
                              "unseen": 0}
        return n

    # 根 = 被修文件的最终版本:一切生成 / 修复都在它上游
    st = ledger.stories.get(root)
    root_node = add("file", root, len(st.versions) if st and st.versions else None, "任务")
    # 结论块点名的(精确版本)
    if structured and not structured.get("errors"):
        for key, rows in (structured.get("roles") or {}).items():
            for r in rows:
                add(str(r["kind"]), key, r["v"], "结论")
        for d in structured.get("defects") or []:
            before = (d.get("repair") or {}).get("before")
            if before and before.get("ok"):
                add(str(before["kind"]), str(before["key"]), before["v"], "修复前")
            for e in d.get("edges") or []:                      # 模型自己写的边,两端也是它点名的坐标
                for end in (e.get("from"), e.get("to")):
                    if end and end.get("ok"):
                        add(str(end["kind"]), str(end["key"]), end["v"], "结论")
            for nd in d.get("nodes") or []:
                for ev in nd.get("evidence") or []:
                    en = ev.get("node") if ev.get("type") == "node" else None
                    if en and en.get("ok"):
                        add(str(en["kind"]), str(en["key"]), en["v"], "结论")
        for f in structured.get("fixed") or []:
            add(str(f["kind"]), str(f["key"]), f["v"], "修复落点")["fixed"] = True
    elif verdicts:                                             # 旧散文报告:环的主语
        for key, rows in verdicts.items():
            for r in rows:
                if r.get("v") is not None:
                    add(str(r["kind"]), key, r["v"], "结论")
    # 查过的落点;不带版本的索引 / 全程查询并进同键已有的版本节点
    for s in steps:
        land = _step_landing(s)
        if land is None or s.get("ok") is False:
            continue
        kind, key, v = land
        same = [n for n in nodes.values() if n["kind"] == kind and n["key"] == key and n["v"] is not None]
        if v is None and same and _n_versions(ledger, kind, key) != 1:
            for n in same:
                n["opened"].append(s["i"])
            continue
        add(kind, key, v, "查过")["opened"].append(s["i"])
    for nid in list(nodes):
        n = nodes[nid]
        if n["v"] is None and n is not root_node:
            same = [m for m in nodes.values() if m["kind"] == n["kind"] and m["key"] == n["key"] and m["v"] is not None]
            if same:
                for m in same:
                    m["opened"] = sorted(set(m["opened"]) | set(n["opened"]))
                del nodes[nid]
    for n in nodes.values():
        n["opened"] = sorted(set(n["opened"]))
        if n["opened"] and n is not root_node:
            n["source"] = "查过"
        elif n["source"] == "查过":
            n["source"] = "结论"
    # 出现于哪些步的返回(事实标注,不画边):打开它这个键的步不算
    landing_by_step = {s["i"]: _step_landing(s) for s in steps}
    for n in nodes.values():
        for s in steps:
            i = int(s["i"])
            land = landing_by_step.get(i)
            if land is not None and land[0] == n["kind"] and land[1] == n["key"]:
                continue
            if _sight(texts[i - 1], n["kind"], n["key"], n["v"], ledger)[0]:
                n["appears"].append(i)
    # 账本边:写 / 读 / 派发(核成 true 的)+ 同一文件相邻在场版本的「前一版」
    order = list(nodes.values())
    edges: list[dict[str, Any]] = []
    for a in order:
        for b in order:
            if a is b:
                continue
            rel = _ledger_relation(ledger, a, b)
            if rel:
                edges.append({"from": a["id"], "to": b["id"], "relation": rel, "skipped": 0})
    by_file: dict[str, list[dict[str, Any]]] = {}
    for n in order:
        if n["kind"] == "file" and n["v"] is not None:
            by_file.setdefault(n["key"], []).append(n)
    for vs in by_file.values():
        vs.sort(key=lambda x: int(x["v"]))
        for lo, hi in zip(vs, vs[1:]):
            edges.append({"from": lo["id"], "to": hi["id"], "relation": "前一版", "skipped": int(hi["v"]) - int(lo["v"]) - 1})
    # 布局:从根沿账本边向上游 BFS 定层;每个节点只有一个布局父(层数最小的下游邻居,同层取先出现的),其余边照画
    down_of: dict[str, list[dict[str, Any]]] = {}
    up_of: dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        down_of.setdefault(e["from"], []).append(e)          # from 的下游是 to
        up_of.setdefault(e["to"], []).append(e)              # to 的上游是 from
    depth: dict[str, int] = {root_node["id"]: 0}

    def bfs(allow_succ: bool) -> None:
        queue = sorted(depth, key=lambda k: depth[k])
        while queue:
            cur = queue.pop(0)
            for e in up_of.get(cur, []):
                if e["from"] not in depth and (allow_succ or e["relation"] != "前一版"):
                    depth[e["from"]] = depth[cur] + 1
                    queue.append(e["from"])

    bfs(False)                                                 # 先沿 写 / 读 / 派发 走:agent → file → agent 交替
    bfs(True)                                                  # 只靠「前一版」才够得着的(touch / 黑盒写断了读写链)再接上
    pos = {n["id"]: i for i, n in enumerate(order)}
    for n in order:
        if n is root_node:
            n["depth"] = 0
            continue
        if n["id"] in depth:
            cands = [e for e in down_of.get(n["id"], []) if e["to"] in depth and depth[e["to"]] == depth[n["id"]] - 1]
            cands.sort(key=lambda e: (e["relation"] == "前一版", pos[e["to"]]))
            e = cands[0]
            n["parent"], n["edge"], n["skipped"], n["side"], n["depth"] = e["to"], e["relation"], e["skipped"], "up", depth[n["id"]]
            continue
        # 根的下游(读了最终版的、之后的版本)放右边;不在根的上下游锥里的单独一列(它们可能仍有账本边,照画)
        seen_down: set[str] = set()
        stack = [root_node["id"]]
        while stack:
            cur = stack.pop()
            for e in down_of.get(cur, []):
                if e["to"] not in seen_down:
                    seen_down.add(e["to"])
                    stack.append(e["to"])
        if n["id"] in seen_down:
            e2 = next(e for e in up_of[n["id"]] if e["from"] == root_node["id"] or e["from"] in seen_down)
            n["parent"], n["edge"], n["skipped"], n["side"] = e2["from"], e2["relation"], e2["skipped"], "down"
        else:
            n["parent"], n["edge"], n["side"] = root_node["id"], None, "unlinked"
    present = {(n["kind"], n["key"], n["v"]) for n in order}
    for n in order:
        n["unseen"] = len([x for x in _upstream_neighbors(ledger, n["kind"], n["key"], n["v"]) if x not in present])
    ordered = sorted(order, key=lambda n: (0 if n is root_node else 1, n["depth"] if n["side"] == "up" else 10 ** 6, pos[n["id"]]))
    return {"mode": "ledger", "root": root_node["id"], "nodes": ordered, "edges": edges, "declared": [],
            "side_title": "查过 · 不在根的上下游"}


# ═══════════════ 按 via 走的树:打开了什么,从什么跳 ═══════════════
# 有 via 的 run 用这个:节点 = 模型用 file / agent 打开的节点(打开索引就是「整个」,打开某版就是那一版),每个一次;
# 父 = 它声明的来处(必须是之前打开过的节点,服务端已校验);每一跳再按账本标这两个节点之间有没有写 / 读 / 派发。
# 不是推断:节点是它打开的,边是它说的,账本关系是核出来的。via 不合规的(老 run)和结论点名没打开的放侧列。


def _vrange(vs: list[int]) -> str:
    vs = sorted(set(vs))
    if not vs:
        return ""
    if len(vs) == 1:
        return f"v{vs[0]}"
    if vs == list(range(vs[0], vs[-1] + 1)):
        return f"v{vs[0]}–v{vs[-1]}"
    return ",".join(f"v{x}" for x in vs[:4]) + ("…" if len(vs) > 4 else "")


def _file_versions(ledger: atoms.Ledger, key: str, v: int | None) -> list[int]:
    st = ledger.stories.get(key)
    if st is None:
        return []
    return [v] if v is not None else list(range(1, len(st.versions) + 1))


def _agent_versions(ledger: atoms.Ledger, key: str, v: int | None) -> list[int]:
    a = ledger.agents.get(key)
    if a is None:
        return []
    return [v] if v is not None else sorted({act.ver for act in a.actions if act.ver is not None})


def _relation_any(ledger: atoms.Ledger, a: dict[str, Any], b: dict[str, Any]) -> str | None:
    """a → b(模型从 a 跳到 b)在账本里对应哪种关系;节点不带版本 = 那个键的全部版本。
    返回 '写 v8–v10' / '写者 v8' / '读 v7' / '读者 v3' / '派发 v5' / '派发自 v5' / None。"""
    if a["kind"] == "file" and b["kind"] == "agent":
        fv, av = set(_file_versions(ledger, a["key"], a["v"])), set(_agent_versions(ledger, b["key"], b["v"]))
        st = ledger.stories.get(a["key"])
        wrote = [ver.v for ver in (st.versions if st else []) if ver.by == b["key"] and ver.by_ver in av and ver.v in fv]
        if wrote:
            return "写者 " + _vrange(wrote)
        ag = ledger.agents.get(b["key"])
        read = [ref.v for act in (ag.actions if ag else []) for ref in act.files
                if ref.op == "read" and ref.path == a["key"] and ref.v in fv and ref.certain and not ref.ev.dep
                and (b["v"] is None or (act.ver if act.ver is not None else act.at) <= b["v"])]
        return ("读者 " + _vrange(read)) if read else None
    if a["kind"] == "agent" and b["kind"] == "file":
        av, fv = set(_agent_versions(ledger, a["key"], a["v"])), set(_file_versions(ledger, b["key"], b["v"]))
        st = ledger.stories.get(b["key"])
        wrote = [ver.v for ver in (st.versions if st else []) if ver.by == a["key"] and ver.by_ver in av and ver.v in fv]
        if wrote:
            return "写 " + _vrange(wrote)
        ag = ledger.agents.get(a["key"])
        read = [ref.v for act in (ag.actions if ag else []) for ref in act.files
                if ref.op == "read" and ref.path == b["key"] and ref.v in fv and ref.certain and not ref.ev.dep
                and (a["v"] is None or (act.ver if act.ver is not None else act.at) <= a["v"])]
        return ("读 " + _vrange(read)) if read else None
    if a["kind"] == "agent" and b["kind"] == "agent":
        child = ledger.agents.get(b["key"])
        if child and child.parent == a["key"] and (a["v"] is None or child.parent_ver == a["v"]):
            return "派发" + (f" v{child.parent_ver}" if child.parent_ver is not None else "")
        me = ledger.agents.get(a["key"])
        if me and me.parent == b["key"] and (b["v"] is None or me.parent_ver == b["v"]):
            return "派发自" + (f" v{me.parent_ver}" if me.parent_ver is not None else "")
        return None
    return None


def _rejected(text: str) -> bool:
    """服务端拒了这次 file / agent(via 不合规):新版以 ⛔ 开头;更早一跑的错误文本没有前缀,按开头词认。"""
    t = text.lstrip()
    return t.startswith(via.REJECT) or (t.startswith("via") and "已打开:" in t[:400])


def _trajectory_walk(ledger: atoms.Ledger, steps: list[dict[str, Any]], texts: list[str],
                     structured: dict[str, Any] | None, verdicts: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    order: list[dict[str, Any]] = []

    def add(kind: str, key: str, v: int | None, source: str) -> dict[str, Any]:
        nid = _traj_id(kind, key, v)
        n = nodes.get(nid)
        if n is None:
            n = nodes[nid] = {"id": nid, "kind": kind, "key": key, "v": v, "label": _traj_label(ledger, kind, key, v),
                              "source": source, "fixed": False, "opened": [], "appears": [], "parent": None,
                              "edge": None, "skipped": 0, "side": "up", "depth": 0, "unseen": 0, "note": None,
                              "via": None}
            order.append(n)
        return n

    root: dict[str, Any] | None = None
    declared: list[dict[str, Any]] = []
    for s in steps:
        if s.get("tool") not in ("file", "agent") or s.get("ok") is False:
            continue
        land = _step_landing(s)
        if land is None:
            continue
        i = int(s["i"])
        kind, key, v = land
        pv = via.parse(ledger, str(s.get("via") or ""))
        if i - 1 < len(texts) and _rejected(texts[i - 1]):
            declared.append({"step": i, "text": pv["text"], "from": None, "to": None, "match": "被拒(via 不合规,没打开)"})
            continue                                           # 服务端没执行:这一步不算打开
        n = add(kind, key, v, "查过")
        n["opened"].append(i)
        if len(n["opened"]) > 1:
            continue                                           # 再次打开同一节点:只记步号,不换父
        n["via"] = pv["text"] or None
        row: dict[str, Any] = {"step": i, "text": pv["text"], "from": None, "to": n["id"], "match": None}
        if root is None:
            root = n
            n["side"] = "root"
            row["match"] = "入口" if pv["first"] else ("入口(via 不是 sessions)" if pv["text"] else "入口(没填 via)")
            if not pv["first"]:
                n["note"] = "第一跳没写 sessions"
        elif pv["first"]:
            n["parent"], n["side"], n["note"] = root["id"], "unlinked", "sessions 只能当第一跳"
            row["match"] = "跳"
        elif pv["ok"] and _traj_id(str(pv["kind"]), str(pv["key"]), pv["v"]) in nodes \
                and nodes[_traj_id(str(pv["kind"]), str(pv["key"]), pv["v"])]["opened"]:
            src = nodes[_traj_id(str(pv["kind"]), str(pv["key"]), pv["v"])]
            n["parent"], n["side"] = src["id"], "up"
            n["edge"] = _relation_any(ledger, src, n)
            row["from"], row["match"] = src["id"], ("账本有边" if n["edge"] else "账本无此边")
        else:
            n["parent"], n["side"] = root["id"], "unlinked"
            n["note"] = "via 解析不了" if not pv["ok"] else "via 指向没打开过的节点"
            row["match"] = n["note"]
        declared.append(row)
    if root is None:
        return {"mode": "via", "root": None, "nodes": [], "edges": [], "declared": [], "side_title": "查过 · 不在路线上"}
    # 结论点名但没打开的:同一个键已经在路线上(整个 / 别的版本)就不另列,角色徽标会落在那个节点上;键都不在路线上的进侧列
    on_route_keys = {(n["kind"], n["key"]) for n in order}

    def side_add(kind: str, key: str, v: int | None, source: str, note: str) -> dict[str, Any] | None:
        if (kind, key) in on_route_keys or _traj_id(kind, key, v) in nodes:
            return nodes.get(_traj_id(kind, key, v))
        m = add(kind, key, v, source)
        m["parent"], m["side"], m["note"] = root["id"], "unlinked", note
        return m

    if structured and not structured.get("errors"):
        for key, rows in (structured.get("roles") or {}).items():
            for r in rows:
                side_add(str(r["kind"]), key, r["v"], "结论", "结论点名,没打开")
        for f in structured.get("fixed") or []:
            m = side_add(str(f["kind"]), str(f["key"]), f["v"], "修复落点", "修复落点,没打开")
            if m is not None:
                m["fixed"] = True
    elif verdicts:
        for key, rows in verdicts.items():
            for r in rows:
                if r.get("v") is not None:
                    side_add(str(r["kind"]), key, r["v"], "结论", "结论点名,没打开")
    # 出现于(事实标注)、深度、没查的上游邻居数
    landing_by_step = {s["i"]: _step_landing(s) for s in steps}
    for n in order:
        for s in steps:
            i = int(s["i"])
            land = landing_by_step.get(i)
            if land is not None and land[0] == n["kind"] and land[1] == n["key"]:
                continue
            if i - 1 < len(texts) and _sight(texts[i - 1], n["kind"], n["key"], n["v"], ledger)[0]:
                n["appears"].append(i)
        d = 0
        cur = n
        while cur["parent"] is not None and cur["side"] == "up":
            cur = nodes[cur["parent"]]
            d += 1
        n["depth"] = d
    present = {(n["kind"], n["key"], n["v"]) for n in order}
    for n in order:
        n["unseen"] = len([x for x in _upstream_neighbors(ledger, n["kind"], n["key"], n["v"]) if x not in present])
    edges = [{"from": n["parent"], "to": n["id"], "relation": n["edge"] or "无", "skipped": 0}
             for n in order if n["parent"] and n["side"] == "up"]
    return {"mode": "via", "root": root["id"], "nodes": order, "edges": edges, "declared": declared,
            "side_title": "查过 · 不在路线上"}


def _trajectory(ledger: atoms.Ledger, run_dir: str, steps: list[dict[str, Any]], root: str | None,
                structured: dict[str, Any] | None, verdicts: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    """有 via 的 run:按 via 走的树;没有的老 run:账本边树;没有转录:None。"""
    texts = _transcript_results(run_dir)
    if texts is None:
        return None
    if any(s.get("via") for s in steps if s.get("tool") in ("file", "agent")):
        if len(texts) < len(steps):
            texts = texts + [""] * (len(steps) - len(texts))
        return _trajectory_walk(ledger, steps, texts, structured, verdicts)
    return _trajectory_ledger(ledger, run_dir, steps, root, structured, verdicts)
