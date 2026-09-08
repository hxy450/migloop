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

from . import atoms, filestory, verdict

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
                      "ok": not s.get("is_error"), "scope": _step_scope(str(s.get("tool")), inp)})
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


# ═══════════════ 调查轨迹树:树 = 模型走过的路 ═══════════════
# 节点只有 agent@版本 / file@版本 两种,只收模型真的查过的和结论块点名的;每个节点一次,挂在它第一次出现在
# 返回文本里的那一步的落点下。返回文本来自 harness 存的 transcript.jsonl,是实录,不是推断。

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
                    texts[str(b.get("tool_use_id"))] = txt
    return [texts.get(t, "") for t in order]


def _sight(text: str, kind: str, key: str, v: int | None, ledger: atoms.Ledger | None) -> tuple[bool, bool]:
    """返回文本里有没有这个节点 → (看见了这个键, 版本也对上了)。文件按最长能匹配的路径后缀;agent 按 id / 尾段 / 主会话号 / 名字。"""
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


def _trajectory(ledger: atoms.Ledger, run_dir: str, steps: list[dict[str, Any]], root: str | None,
                structured: dict[str, Any] | None, verdicts: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    texts = _transcript_results(run_dir)
    if texts is None or not root:
        return None
    if len(texts) < len(steps):
        texts = texts + [""] * (len(steps) - len(texts))
    # 根:被修文件的修复前版本(结论块 repair.before),没有就整个文件
    root_v: int | None = None
    if structured:
        for d in structured.get("defects") or []:
            b = (d.get("repair") or {}).get("before")
            if b and b.get("ok") and b.get("kind") == "file" and b.get("key") == root:
                root_v = int(b["v"])
                break
    nodes: dict[str, dict[str, Any]] = {}

    def add(kind: str, key: str, v: int | None, source: str) -> dict[str, Any]:
        nid = _traj_id(kind, key, v)
        n = nodes.get(nid)
        if n is None:
            n = nodes[nid] = {"id": nid, "kind": kind, "key": key, "v": v, "label": _traj_label(ledger, kind, key, v),
                              "source": source, "opened": [], "seen_step": None, "seen_tool": None, "seen_exact": False,
                              "seen_count": 0, "parent": None, "edge_kind": "none", "unseen": 0, "ledger": None,
                              "fixed": False}
        return n

    if root_v is None:                                         # 没有修复锚点:结论点名的这个文件的最早一版当根
        cands = [int(r["v"]) for r in ((structured or {}).get("roles") or {}).get(root, []) if r.get("v") is not None]
        cands += [int(r["v"]) for r in verdicts.get(root, []) if r.get("v") is not None]
        root_v = min(cands) if cands else None
    root_node = add("file", root, root_v, "任务")
    root_node["edge_kind"] = "task"
    # 结论块点名的(精确版本)
    if structured and not structured.get("errors"):
        for key, rows in (structured.get("roles") or {}).items():
            for r in rows:
                add(str(r["kind"]), key, r["v"], "结论")
        for f in structured.get("fixed") or []:
            add(str(f["kind"]), str(f["key"]), f["v"], "修复落点")["fixed"] = True
    elif verdicts:                                             # 旧散文报告:环的主语
        for key, rows in verdicts.items():
            for r in rows:
                if r.get("v") is not None:
                    add(str(r["kind"]), key, r["v"], "结论")
    # 查过的落点;不带版本的索引查询并进同键已有的版本节点
    for s in steps:
        land = _step_landing(s)
        if land is None or s.get("ok") is False:
            continue
        kind, key, v = land
        same = [n for n in nodes.values() if n["kind"] == kind and n["key"] == key and n["v"] is not None]
        if v is None and same:
            for n in same:
                n["opened"].append(s["i"])
            continue
        n = add(kind, key, v, "查过")
        n["opened"].append(s["i"])
    # 同键的整段节点被后来出现的版本节点吸收(先查了 file(A) 再点名 A@v3 的顺序)
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
            n["source"] = "查过"                                   # 查过的就是查过的,结论点名只是附加信息(角色徽标另给)
        elif n["source"] == "查过":
            n["source"] = "结论"
    # 每一步返回文本里的动作引用 → 所属 agent@版本(精确视见)
    ref_hits: list[set[tuple[str, int | None]]] = []
    for text in texts:
        hits: set[tuple[str, int | None]] = set()
        for mm in _ACTION.finditer(text):
            tag = mm.group(1) or mm.group(5)
            hit, _status = atoms.resolve_ref(ledger, int(mm.group(2)), int(mm.group(3)),
                                             int(mm.group(4)) if mm.group(4) is not None else None, tag)
            if hit is not None:
                owner, over = _seq_owner(ledger, hit)
                if owner:
                    hits.add((owner, over))
        ref_hits.append(hits)
    # 第一次看见:只算「第一次打开它之前」的步(打开它那一步的返回当然有它,不算);结论点名没查过的看全程
    landing_by_step = {s["i"]: _step_landing(s) for s in steps}

    def landing_node(i: int) -> dict[str, Any] | None:
        land = landing_by_step.get(i)
        if land is None:
            return None
        kind, key, v = land
        exact = nodes.get(_traj_id(kind, key, v))
        if exact is not None:
            return exact
        same = [n for n in nodes.values() if n["kind"] == kind and n["key"] == key]
        return same[0] if same else None

    for n in nodes.values():
        if n is root_node:
            continue
        limit = n["opened"][0] if n["opened"] else len(steps) + 1
        first: int | None = None
        for s in steps:
            i = int(s["i"])
            land = landing_by_step.get(i)
            if land is not None and land[0] == n["kind"] and land[1] == n["key"]:
                continue                                       # 打开它自己(任一版本)的那一步不算「看到」
            seen, exact = _sight(texts[i - 1], n["kind"], n["key"], n["v"], ledger)
            if n["kind"] == "agent" and not (seen and exact):
                if (n["key"], n["v"]) in ref_hits[i - 1]:
                    seen, exact = True, True
                elif any(k == n["key"] for k, _v in ref_hits[i - 1]):
                    seen = True
            if not seen:
                continue
            n["seen_count"] += 1                                   # 出现次数全程计,打开之后再出现也算
            if first is None and i < limit:                        # 进入边只认打开它之前的那一次
                first = i
                n["seen_step"] = i
                n["seen_tool"] = str(s.get("tool") or "")
                n["seen_exact"] = bool(exact)
        if first is None:
            n["parent"] = root_node["id"]
            n["edge_kind"] = "none"
            continue
        parent = landing_node(first)
        if parent is None or parent is n:
            n["parent"] = root_node["id"]
            n["edge_kind"] = "search"                          # sessions / 全池 search 这类不落节点的步带进来的
        else:
            n["parent"] = parent["id"]
            n["edge_kind"] = "seen"
    # 账本关系(两端版本都精确才核)与没查过的邻居数
    present = {(n["kind"], n["key"], n["v"]) for n in nodes.values()}
    for n in nodes.values():
        n["unseen"] = len([x for x in _upstream_neighbors(ledger, n["kind"], n["key"], n["v"]) if x not in present])
        if n["parent"] is None:
            continue
        p = nodes[n["parent"]]
        if n["v"] is None or p["v"] is None:
            continue
        a = verdict.resolve_node(ledger, f"{p['kind']}:{p['key']}@v{p['v']}")
        b = verdict.resolve_node(ledger, f"{n['kind']}:{n['key']}@v{n['v']}")
        st, rel, _note = verdict.check_edge(ledger, b, a, None)
        if st != "true":
            st, rel, _note = verdict.check_edge(ledger, a, b, None)
        if st in ("true", "unknown"):
            n["ledger"] = {"relation": rel, "status": st}
    # 输出顺序:父在子前(按父链深度,再按第一次出现 / 打开的步)
    def depth(n: dict[str, Any]) -> int:
        d = 0
        while n["parent"] is not None:
            n = nodes[n["parent"]]
            d += 1
        return d

    def order_key(n: dict[str, Any]) -> tuple[int, int]:
        first = n["seen_step"] if n["seen_step"] is not None else (n["opened"][0] if n["opened"] else 10 ** 6)
        return depth(n), first

    ordered = sorted(nodes.values(), key=order_key)
    return {"root": root_node["id"], "nodes": ordered}
