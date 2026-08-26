"""跨会话返修链 —— 多个 root 会话的 blame 事件接力,正式链在此成立。

真实迁移是多轮的:生成会话产码,后续会话(visual verify 等)修复。单会话
血缘里被修文件的 writers 只剩修复方,链接不上;把同一文件的写事件跨会话
按时间串成一条序列交给 blame 重放,生成会话的终态就是修复会话的
baseline —— no-baseline 断链消失,"被修行的原作者"跨会话精确归因。

零推断原则不变:事件全部来自实录,接力只是把两段实录拼成完整时间线;
拼不上(实录外改动,如人工 vibe coding)照旧诚实断链并标注原因。
"""

from __future__ import annotations

from typing import Any

from migloop.audit import agent_is_fixer
from migloop.blame import replay_file

# (ts, abs_path, agent_id, op, payload) —— codex.collect_blame_events 的输出形状
BlameEvent = tuple[str, str, str, str, Any]


def _lineage_agents(trace: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lin = trace.get("lineage") or {}
    return {str(a.get("agent_id")): a for a in lin.get("agents") or []}


def _rel(path: str, cwd: str) -> str:
    p = path.replace("\\", "/")
    c = (cwd or "").replace("\\", "/").rstrip("/")
    if c and p.lower().startswith(c.lower() + "/"):
        return p[len(c) + 1:]
    return p


def build_cross_chains(
    cur_trace: dict[str, Any],
    prior_traces: list[dict[str, Any]],
    events: list[BlameEvent],
) -> list[dict[str, Any]]:
    """当前会话的 fixer × 前序会话的生成方 → 跨会话链(与 audit chain 同形状)。

    events 必须已含当前会话与全部前序会话的 blame 事件;按文件分组、时间序
    接力重放。成链条件:文件写手里同时有「本会话 fixer」与「别的写手」。
    """
    cur_sid = str((cur_trace.get("meta") or {}).get("session_id") or "")
    cur_cwd = str((cur_trace.get("meta") or {}).get("cwd") or "")
    cur_by_id = _lineage_agents(cur_trace)
    cur_da = {str(a.get("agent_id")): a for a in cur_trace.get("agents") or []}

    # 生成方信息跨全部前序会话查:agent_id(=codex rollout id)全局唯一
    gen_by_id: dict[str, dict[str, Any]] = {}
    gen_da: dict[str, dict[str, Any]] = {}
    gen_session: dict[str, str] = {}
    spec_authors: dict[str, dict[str, Any]] = {}
    for tr in prior_traces:
        sid8 = str((tr.get("meta") or {}).get("session_id") or "")[:8]
        by_id = _lineage_agents(tr)
        gen_by_id.update(by_id)
        for aid in by_id:
            gen_session[aid] = sid8
        gen_da.update({str(a.get("agent_id")): a for a in tr.get("agents") or []})
        for sp in (tr.get("lineage") or {}).get("specs") or []:
            spec_authors.setdefault(str(sp.get("path")), sp)

    def spec_pages_of(paths: list[str], by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        pages = []
        for sp in paths:
            authors = []
            for aid in (spec_authors.get(sp) or {}).get("authors") or []:
                aa = by_id.get(str(aid))
                if aa is None:
                    continue
                authors.append({
                    "id": str(aid), "desc": str(aa.get("desc") or aid)[:40],
                    "stage": aa.get("stage"),
                    "android_reads": [str(x) for x in (aa.get("android_reads") or [])[:8]],
                    "n_android": aa.get("n_android") or 0,
                })
            pages.append({"path": sp, "authors": authors})
        return pages

    by_file: dict[str, list[BlameEvent]] = {}
    for ev in events:
        by_file.setdefault(ev[1], []).append(ev)

    chains: list[dict[str, Any]] = []
    for path, evs in sorted(by_file.items()):
        evs.sort(key=lambda e: e[0])
        writer_ids = list(dict.fromkeys(e[2] for e in evs))
        fixers = [w for w in writer_ids
                  if w in cur_by_id and agent_is_fixer(cur_by_id[w])]
        gens = [w for w in writer_ids if w not in fixers]
        if not (fixers and gens):
            continue
        r = replay_file([(e[2], e[3], e[4]) for e in evs])
        fid = fixers[0]
        gid = gens[0]
        lines_info: dict[str, Any] | None = None
        if r["broken"] is None:
            tk = next((t for t in r["takeovers"]
                       if str(t.get("by")) == fid and t.get("from")), None)
            if tk:
                origins = {str(k): int(v) for k, v in dict(tk["from"]).items()
                           if str(k) != fid}
                if origins:
                    gid = max(origins, key=lambda k: origins[k])
                    lines_info = {
                        "touched": sum(origins.values()),
                        "from": [{"id": k,
                                  "desc": str((gen_by_id.get(k) or cur_by_id.get(k)
                                               or {}).get("desc") or k)[:40],
                                  "n": origins[k]}
                                 for k in sorted(origins, key=lambda k: -origins[k])[:4]],
                    }
        g = gen_by_id.get(gid) or cur_by_id.get(gid) \
            or {"desc": "主会话(编排/直接写盘)", "stage": None}
        fx = cur_by_id[fid]
        chains.append({
            "file": _rel(path, cur_cwd),
            "file_abs": path.replace("\\", "/"),
            "gen_session": gen_session.get(gid, cur_sid[:8]),
            "generator": {
                "id": gid,
                "desc": str(g.get("desc") or gid)[:40],
                "stage": g.get("stage"),
                "spec_reads": [str(x) for x in (g.get("spec_reads") or [])[:5]],
                "shared_reads": [str(x) for x in (g.get("shared_reads") or [])[:3]],
                "android_reads": [str(x) for x in (g.get("android_reads") or [])[:4]],
                "n_android": g.get("n_android") or 0,
                "prompt": str((gen_da.get(gid) or cur_da.get(gid) or {})
                              .get("prompt_excerpt") or "")[:200],
            },
            "spec_pages": spec_pages_of(
                [str(x) for x in (g.get("spec_reads") or [])[:5]], gen_by_id),
            "fixer": {
                "id": fid,
                "desc": str(fx.get("desc") or fid)[:40],
                "stage": fx.get("stage"),
                "note": str((cur_da.get(fid) or {}).get("result") or "")[:280],
            },
            "lines": lines_info,
            "blame_broken": r["broken"],
            # 多方不共享文案:每个生成方有自己的派发指令,每轮修复方有自己的修因。
            # 行级 trim:写过文件 ≠ 写过被改的行 —— 有行级归因时只保留被修行的
            # 原作者(断链时退回文件级全写手,诚实降级)
            "generators": [
                {"id": w, "desc": str((gen_by_id.get(w) or cur_by_id.get(w)
                                       or {}).get("desc") or w)[:40],
                 "stage": (gen_by_id.get(w) or cur_by_id.get(w) or {}).get("stage"),
                 "prompt": str((gen_da.get(w) or cur_da.get(w) or {})
                               .get("prompt_excerpt") or "")[:200]}
                for w in (
                    [g0 for g0 in gens
                     if g0 in {x["id"] for x in (lines_info or {}).get("from", [])}]
                    if lines_info else gens) or gens],
            "fixers_all": [
                {"id": f0, "desc": str((cur_by_id.get(f0) or {}).get("desc") or f0)[:40],
                 "stage": (cur_by_id.get(f0) or {}).get("stage"),
                 "note": str((cur_da.get(f0) or {}).get("result") or "")[:280]}
                for f0 in fixers],
            "diff": [dict(c, by_desc=str((cur_by_id.get(c.get("by"))
                                          or gen_by_id.get(c.get("by"))
                                          or {}).get("desc") or c.get("by"))[:40])
                     for c in r.get("changes") or []
                     if c.get("by") in fixers][:6],
        })
    return chains[:40]


def _same_project(cwd_a: str, cwd_b: str) -> bool:
    a = cwd_a.replace("\\", "/").rstrip("/").lower()
    b = cwd_b.replace("\\", "/").rstrip("/").lower()
    return bool(a and b) and (a == b or a.startswith(b + "/") or b.startswith(a + "/"))


def find_prior_codex_roots(cur_path: str, cur_cwd: str, limit: int = 3) -> list[str]:
    """同一工程树里、时间早于当前会话的 codex 主会话(rollout 文件名即时间序)。

    工程同树 = 两个 cwd 相等或一方是另一方的父目录(真实案例:生成会话 cwd 在
    工程父目录,verify 会话 cwd 在工程根)。子代理 rollout 由 iter_sessions 排除。
    """
    import os

    from migloop import adapters

    codex: Any = adapters.get("codex")
    cur_abs = os.path.abspath(cur_path)
    cur_base = os.path.basename(cur_path)
    out = []
    for cand in codex.iter_sessions(codex.default_root()):
        if os.path.abspath(cand.path) == cur_abs:
            continue
        if os.path.basename(cand.path) >= cur_base:
            continue
        summary = codex.session_summary(cand.path) or {}
        if _same_project(str(summary.get("cwd") or ""), cur_cwd):
            out.append(cand.path)
    out.sort(key=lambda x: str(x).rsplit("rollout-", 1)[-1], reverse=True)
    return out[:limit]


def find_later_codex_roots(cur_path: str, cur_cwd: str, limit: int = 3) -> list[str]:
    """镜像方向:同工程树里时间晚于当前会话的主会话 —— 生成轮反查
    "我的产出后来被谁修了"用(fixchain 无链时重定向到后继链页)。"""
    import os

    from migloop import adapters

    codex: Any = adapters.get("codex")
    cur_abs = os.path.abspath(cur_path)
    cur_base = os.path.basename(cur_path)
    out = []
    for cand in codex.iter_sessions(codex.default_root()):
        if os.path.abspath(cand.path) == cur_abs:
            continue
        if os.path.basename(cand.path) <= cur_base:
            continue
        summary = codex.session_summary(cand.path) or {}
        if _same_project(str(summary.get("cwd") or ""), cur_cwd):
            out.append(cand.path)
    out.sort(key=lambda x: str(x).rsplit("rollout-", 1)[-1])
    return out[:limit]


def collect_project_roots(cur_path: str, cur_cwd: str, limit: int = 8) -> list[str]:
    """同工程树的全部主会话(含当前),按 rollout 文件名时间序 —— 迁移全程视图用。"""
    import os

    from migloop import adapters

    codex: Any = adapters.get("codex")
    cur_abs = os.path.abspath(cur_path)
    out = [cur_abs]
    for cand in codex.iter_sessions(codex.default_root()):
        cand_abs = os.path.abspath(cand.path)
        if cand_abs == cur_abs:
            continue
        summary = codex.session_summary(cand.path) or {}
        if _same_project(str(summary.get("cwd") or ""), cur_cwd):
            out.append(cand_abs)
    out.sort(key=lambda x: str(os.path.basename(x)))
    return out[:limit]


def journey_rounds(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """多轮 trace(时间序) → 轮卡数据:每轮的阶段构成/规模/修复方数量。"""
    rounds = []
    for tr in traces:
        meta = tr.get("meta") or {}
        cwd = str(meta.get("cwd") or "")
        agents = tr.get("agents") or []
        fixers = [a for a in agents
                  if any(m in str(a.get("type") or "").lower()
                         for m in ("fixer", "visual"))]
        files = (tr.get("lineage") or {}).get("files") or []
        rounds.append({
            "sid8": str(meta.get("session_id") or "")[:8],
            "project": next((x for x in reversed(cwd.replace("\\", "/").split("/")) if x), ""),
            "started_at": meta.get("started_at"),
            "ended_at": meta.get("ended_at"),
            "stages": [{"label": st.get("label") or st.get("stage"),
                        "duration_ms": st.get("duration_ms") or 0}
                       for st in tr.get("stages") or []],
            "agents": (tr.get("totals") or {}).get("subagent_transcripts") or 0,
            "ets_files": sum(1 for f in files if f.get("kind") == "ets" and f.get("writers")),
            "fixers": len(fixers),
        })
    return rounds


def _abs_key(path: str, cwd: str) -> str:
    p = str(path).replace("\\", "/")
    if p.startswith("/") or (len(p) > 1 and p[1] == ":"):
        return p
    return (cwd or "").replace("\\", "/").rstrip("/") + "/" + p


def build_trace_graph(cur_trace: dict[str, Any],
                      prior_traces: list[dict[str, Any]]) -> dict[str, Any]:
    """全量调用图 —— 页面吃它,不吃摘要投影。

    节点 = agents(含主线分段) + 文件(绝对路径归一,跨会话同文件即同节点);
    边 = 台账读写实录,数据流方向:输入文件→agent,agent→输出文件。
    specs/android/files 台账是全量双向的(不截断),la 条目只当 agent 元数据。
    fixer 身份按当前会话的正式口径(agent_is_fixer)标注。
    """
    nodes: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str]] = set()

    def file_node(key: str, kind: str, label: str) -> None:
        node = nodes.setdefault(key, {"kind": kind, "label": label})
        if kind != "proj" and node["kind"] == "proj":
            node["kind"] = kind

    for tr in [*prior_traces, cur_trace]:
        meta = tr.get("meta") or {}
        cwd = str(meta.get("cwd") or "")
        sid8 = str(meta.get("session_id") or "")[:8]
        is_cur = tr is cur_trace
        da = {str(a.get("agent_id")): a for a in tr.get("agents") or []}
        lin = tr.get("lineage") or {}
        for a in lin.get("agents") or []:
            aid = str(a.get("agent_id"))
            fixer = is_cur and agent_is_fixer(a)
            nodes[aid] = {
                "kind": "fixer" if fixer else "agent",
                "label": str(a.get("desc") or aid)[:60],
                "stage": a.get("stage"), "type": a.get("type"),
                "session": sid8,
                "prompt": str((da.get(aid) or {}).get("prompt_excerpt") or "")[:200],
                "note": str((da.get(aid) or {}).get("result") or "")[:280],
            }
        for sp in lin.get("specs") or []:
            key = _abs_key(sp.get("path"), cwd)
            file_node(key, "spec", str(sp.get("path")).replace("\\", "/").rsplit("/", 1)[-1])
            for aid in sp.get("authors") or []:
                edges.add((str(aid), key))
            for aid in sp.get("read_by") or []:
                edges.add((key, str(aid)))
        for an in lin.get("android") or []:
            key = _abs_key(an.get("path"), cwd)
            file_node(key, "src", str(an.get("path")).replace("\\", "/").rsplit("/", 1)[-1])
            for aid in an.get("readers") or []:
                edges.add((key, str(aid)))
        for f in lin.get("files") or []:
            key = _abs_key(f.get("path"), cwd)
            kind = "ets" if f.get("kind") == "ets" else "proj"
            file_node(key, kind, str(f.get("path")).replace("\\", "/").rsplit("/", 1)[-1])
            for aid in f.get("writers") or []:
                edges.add((str(aid), key))
            for aid in f.get("readers") or []:
                edges.add((key, str(aid)))
    return {"nodes": nodes, "edges": sorted(edges)}


def _first_record_ts(path: str) -> str:
    """首条带 timestamp 的记录 —— CC transcript 的会话开始时间。
    文件 mtime 在拷贝/归档后不可靠,时间序一律以内容为准。"""
    import json

    try:
        with open(path, encoding="utf-8", errors="ignore") as stream:
            for line in stream:
                try:
                    ts = json.loads(line).get("timestamp")
                except Exception:
                    continue
                if ts:
                    return str(ts)
    except OSError:
        pass
    return ""


def collect_claude_project_roots(cur_path: str, limit: int = 8) -> list[str]:
    """CC 同工程 = 同 transcript 目录(projects/<cwd-slug>/);全部主会话时间序。"""
    import glob
    import os

    d = os.path.dirname(os.path.abspath(cur_path))
    rows = []
    for f in glob.glob(os.path.join(d, "*.jsonl")):
        ts = _first_record_ts(f)
        if ts:
            rows.append((ts, os.path.abspath(f)))
    rows.sort()
    return [f for _, f in rows][:limit]


def find_prior_claude_roots(cur_path: str, limit: int = 3) -> list[str]:
    import os

    cur_abs = os.path.abspath(cur_path)
    cur_ts = _first_record_ts(cur_path)
    out = [f for f in collect_claude_project_roots(cur_path, 64)
           if f != cur_abs and _first_record_ts(f) < cur_ts]
    return out[-limit:][::-1]


def find_later_claude_roots(cur_path: str, limit: int = 3) -> list[str]:
    import os

    cur_abs = os.path.abspath(cur_path)
    cur_ts = _first_record_ts(cur_path)
    out = [f for f in collect_claude_project_roots(cur_path, 64)
           if f != cur_abs and _first_record_ts(f) > cur_ts]
    return out[:limit]
