"""本地服务层:会话定位、trace / 两原子账本缓存、返修链载荷、两原子 JSON 与文本。

``migloop <目标> --serve``(stdlib HTTP)与 ``python -m migloop.mcp_server`` 共用这一层。逻辑与
migbot-server 的 ``services/migloop_report.py`` 同构,这里去掉 web 框架与数据库:池子 = 同工程
磁盘上的兄弟会话(crosschain 的 root 发现),账本按 (转录 mtime, size) 整包缓存。

返修链路只支持 claude / codex 会话(两原子收集器只有这两个);别的来源报告页照出,链页与原子端点
返回明确错误,不猜。
"""

from __future__ import annotations

import glob
import json
import os
import threading
from typing import Any

from . import adapters, atoms, atoms_collect, atoms_text, audit, crosschain, filestory
from .render import build_html, load_asset, load_template


class SessionLookupError(Exception):
    """目标解析不到唯一会话,或该来源不支持这项能力。"""


_LOCK = threading.RLock()
_TRACE_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}
_LEDGER_CACHE: dict[str, tuple[Any, Any]] = {}
_FIXCHAIN_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}
_CACHE_MAX = 3
_ATOM_FORMATS = ("claude", "codex")


# ═══════════════ 会话定位 ═══════════════

def locate_session(target: str, roots: dict[str, str] | None = None) -> str:
    """jsonl 路径 | session-id 前缀 | 项目名片段 → 唯一 root 转录路径(最新者优先)。"""
    if os.path.isfile(target):
        return os.path.abspath(target)
    rows = list(adapters.discover(roots or {}))
    want = str(target or "").strip()
    hits = [r for r in rows if want and str(r.session_id or "").startswith(want)]
    if not hits:
        hits = [r for r in rows if want and want.lower() in str(r.project or "").lower()]
    if not hits:
        raise SessionLookupError(f"找不到会话: {target}")
    return os.path.abspath(hits[0].path)          # discover 已按 mtime 新→旧


def _stat_key(paths: list[str]) -> list[Any]:
    out: list[Any] = []
    for p in paths:
        try:
            st = os.stat(p)
            out.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((p, None, None))
    return out


def _put(cache: dict[str, Any], key: str, value: Any) -> None:
    if len(cache) >= _CACHE_MAX and key not in cache:
        cache.pop(next(iter(cache)))
    cache[key] = value


# ═══════════════ trace(旧提取层:报告页 / 名片 / 兜底修复方映射) ═══════════════

def extract_trace(path: str, storage_root: str | None = None) -> dict[str, Any]:
    key = _stat_key([path])
    with _LOCK:
        hit = _TRACE_CACHE.get(path)
        if hit is not None and hit[0] == key:
            return hit[1]
        adapter: Any = adapters.detect(path)
        if adapter.FORMAT == "deveco":                 # 只有 DevEco 需要数据目录定位子代理库
            data = dict(adapter.extract(path, storage_root=storage_root))
        else:
            data = dict(adapter.extract(path))
        _put(_TRACE_CACHE, path, (key, data))
        return data


def _fmt_of(trace: dict[str, Any]) -> str:
    return str((trace.get("meta") or {}).get("session_format") or "claude")


def prior_roots(fmt: str, path: str, cwd: str) -> list[str]:
    """同工程的前序 root 会话全部入池:一次迁移 run 里 Driver 直接起的会话(reviewer、ECAT 判别器 / 修复方、
    loop engine 续接的 worker)都是 root,DiceRoller 0903 一个 run 就有 17 个,默认只取 3 个会把返修链切断。"""
    if fmt == "codex":
        return crosschain.find_prior_codex_roots(path, cwd, limit=64)
    if fmt == "claude":
        return crosschain.find_prior_claude_roots(path, limit=64)
    return []


def later_roots(fmt: str, path: str, cwd: str) -> list[str]:
    if fmt == "codex":
        return crosschain.find_later_codex_roots(path, cwd, 1)
    if fmt == "claude":
        return crosschain.find_later_claude_roots(path, 1)
    return []


def root_sid8(fmt: str, path: str) -> str:
    """root 转录 → 8 位会话号:codex 读首行 meta 的 id,CC 取文件名。"""
    if fmt == "codex":
        cx: Any = adapters.get("codex")
        return str((cx.session_summary(path) or {}).get("id") or "")[:8]
    return os.path.splitext(os.path.basename(path))[0][:8]


# ═══════════════ 两原子账本 ═══════════════

def run_stage_intervals(path: str, cwd: str) -> list[dict[str, Any]]:
    """run 级阶段区间:工程里 Go 运行时写的 .migbot/metrics/<run_id>/facts/stage-marks.json,或转录同目录
    的 stage-marks.json(导出包 / 离线分析摆放)。多份时取起点不晚于本会话首条记录的最新那份。
    没有归属戳的会话(ECAT 对抗循环、reviewer、loop engine 续接的 worker)靠它落阶段,execute 结束时刻也从它来。"""
    from .filestory import ts_norm

    cands: list[str] = []
    if cwd:
        cands += glob.glob(os.path.join(cwd, ".migbot", "metrics", "*", "facts", "stage-marks.json"))
    cands += glob.glob(os.path.join(os.path.dirname(os.path.abspath(path)), "stage-marks.json"))
    first_ts = ts_norm(crosschain._first_record_ts(path))
    best: tuple[str, list[dict[str, Any]]] | None = None
    fallback: tuple[str, list[dict[str, Any]]] | None = None
    for p in cands:
        try:
            with open(p, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        marks = doc.get("marks") if isinstance(doc, dict) else doc
        iv = atoms_collect.stage_intervals_from_marks(marks if isinstance(marks, list) else [])
        if not iv:
            continue
        start = ts_norm(iv[0]["start_ts"])
        if start <= first_ts and (best is None or start > best[0]):
            best = (start, iv)
        if fallback is None or start < fallback[0]:
            fallback = (start, iv)
    return (best or fallback or ("", []))[1]


def _collect(fmt: str, roots: list[str], stage_intervals: list[dict[str, Any]] | None = None) -> Any:
    seq = [0]
    agents: dict[str, Any] = {}
    for p in roots:
        if fmt == "codex":
            agents.update(atoms_collect.collect_codex(p, seq))
        else:
            agents.update(atoms_collect.collect_cc(p, seq, stage_intervals=stage_intervals))
    ledger = atoms.build_ledger(agents)
    ledger.fix_after = atoms_collect.fix_boundary(stage_intervals or [])
    return ledger


def session_ledger(path: str) -> Any:
    """当前会话 + 同工程前序会话的账本(跨会话同一本史书)。"""
    data = extract_trace(path)
    fmt = _fmt_of(data)
    if fmt not in _ATOM_FORMATS:
        raise SessionLookupError(f"返修链路 / 两原子暂不支持 {fmt} 会话")
    cwd = str((data.get("meta") or {}).get("cwd") or "")
    roots = [*prior_roots(fmt, path, cwd), path]           # 时间正序:前序在前
    intervals = run_stage_intervals(path, cwd)
    key = [*_stat_key(roots), tuple((iv["stage"], iv["start_ts"]) for iv in intervals)]
    with _LOCK:
        hit = _LEDGER_CACHE.get(path)
        if hit is not None and hit[0] == key:
            return hit[1]
        ledger = _collect(fmt, roots, intervals)
        _put(_LEDGER_CACHE, path, (key, ledger))
        return ledger


def session_cwd(path: str) -> str:
    return str((extract_trace(path).get("meta") or {}).get("cwd") or "")


def ledger_main_sid8(ledger: Any, path: str, fmt: str, meta_sid8: str) -> str:
    """账本里当前会话的会话号:CC 取转录文件名前 8 位,codex 取 meta;resume 快照这类
    文件名≠记录 sessionId 的情况以账本实际存在的主会话为准。"""
    want = meta_sid8 if fmt == "codex" else os.path.splitext(os.path.basename(path))[0][:8]
    mains = [k.split(":", 1)[-1] for k in ledger.agents if k.startswith("__main__")]
    if want in mains or not mains:
        return want
    return meta_sid8 if meta_sid8 in mains else mains[-1]


def agent_meta_maps(data: dict[str, Any], prior_traces: list[dict[str, Any]],
                    ) -> tuple[dict[str, dict[str, Any]], dict[str, bool], dict[str, str]]:
    """血缘层的 agent 名片 + 兜底修复方映射(账本里没有阶段的版本才用到)+ 归属会话。全会话收。"""
    meta_map: dict[str, dict[str, Any]] = {}
    sid_of: dict[str, str] = {}
    fixer_map: dict[str, bool] = {}
    for tr in [*prior_traces, data]:
        sid8 = str((tr.get("meta") or {}).get("session_id") or "")[:8]
        for a in (tr.get("lineage") or {}).get("agents") or []:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("agent_id"))
            meta_map[aid] = {"desc": a.get("desc"), "stage": a.get("stage"),
                             "prompt": str(a.get("prompt_excerpt") or "")[:200],
                             "note": str(a.get("result") or "")[:280]}
            sid_of.setdefault(aid, sid8)
            fixer_map[aid] = audit.agent_is_fixer(a)
    return meta_map, fixer_map, sid_of


def _merge_ledger_meta(meta_map: dict[str, dict[str, Any]], ledger: Any) -> dict[str, dict[str, Any]]:
    """链的名片以血缘层为准,空着的字段用账本的名片补(主会话不补,build_fix_chains 按版本阶段自己给)。
    血缘层给 visual-verify 期间主会话派的 visual-fixer / ID 注入子代理的名片是空的(desc None),
    被修行原作者与修复方显示成裸 id,账本目录里却有名字;整卡覆盖会把名字盖回去,所以按字段补。"""
    merged: dict[str, dict[str, Any]] = {k: dict(v) for k, v in meta_map.items()}
    for aid, a in ledger.agents.items():
        if aid.startswith("__main__"):
            continue
        key = aid[6:] if aid.startswith("agent-") else aid
        card = {"desc": atoms.agent_label(ledger, aid), "stage": a.stage,
                "prompt": str(a.prompt or "")[:200], "note": str(a.result or "")[:280]}
        cur = merged.get(key)
        merged[key] = card if cur is None else {**card, **{k: v for k, v in cur.items() if v not in (None, "")}}
    return merged


def fixchain_payload(path: str) -> dict[str, Any]:
    """chains + cross + t0 —— 全部从两原子账本算;修复方判定只在 filestory.build_fix_chains。"""
    data = extract_trace(path)
    fmt = _fmt_of(data)
    meta = data.get("meta") or {}
    cwd = str(meta.get("cwd") or "")
    priors = prior_roots(fmt, path, cwd) if fmt in _ATOM_FORMATS else []
    key = _stat_key([path, *priors])
    with _LOCK:
        hit = _FIXCHAIN_CACHE.get(path)
        if hit is not None and hit[0] == key:
            return hit[1]
        ledger = session_ledger(path)
        prior_traces = [extract_trace(p) for p in priors]
        meta_map, fixer_map, sid_of = agent_meta_maps(data, prior_traces)
        meta_map = _merge_ledger_meta(meta_map, ledger)
        # 修复方按 execute 结束时刻判(run 级 stage-marks 给的 fix_after),链根只认工程根目录下的代码与配置
        chains = filestory.build_fix_chains(ledger.stories, meta_map, fixer_map,
                                            root=cwd or None, fix_after=ledger.fix_after)
        session_of = {k: a.session for k, a in ledger.agents.items()}
        cur_sid8 = str(meta.get("session_id") or "")[:8]
        cur_ledger_sid = ledger_main_sid8(ledger, path, fmt, cur_sid8)
        n_cross = 0
        for c in chains:
            gid = str(c["generator"]["id"])
            gkey = gid[6:] if gid.startswith("agent-") else gid
            gsid = sid_of.get(gkey)
            if gsid and gsid != cur_sid8:
                c["gen_session"] = gsid
                n_cross += 1
            fsid = session_of.get(str(c["fixer"]["id"]))
            if fsid and fsid != cur_ledger_sid:
                c["fix_session"] = fsid          # 前序轮回合内的返修:修复方不在当前会话
        cross: dict[str, Any] | None = None
        if priors:
            cross = {"priors": [str((t.get("meta") or {}).get("session_id") or "")[:8]
                                for t in prior_traces],
                     "n_cross": n_cross}
        payload = {"chains": chains, "cross": cross, "t0": ledger.t0}
        _put(_FIXCHAIN_CACHE, path, (key, payload))
        return payload


# ═══════════════ 页面 ═══════════════

def report_trace(path: str, *, static: bool = False, with_chains: bool = True,
                 storage_root: str | None = None) -> dict[str, Any]:
    """报告页的 trace:提取层 + 审计(「02 风险点」)+ 返修追溯卡(吃账本的链)+ 跨会话提示。

    static=True 是导出的自包含 HTML / live 快照:没有服务端,页面上的返修链路入口藏起来
    (``urls.fixchain`` 为空);with_chains=False 跳过建账(live 每次刷新都重算太贵)。
    不支持两原子的来源(DevEco)没有返修追溯卡,其余审计照出。"""
    data = dict(extract_trace(path, storage_root))
    fmt = _fmt_of(data)
    chains: list[dict[str, Any]] | None = None
    pool_builds: list[dict[str, Any]] | None = None
    pool_agents: list[dict[str, Any]] | None = None
    cwd = str((data.get("meta") or {}).get("cwd") or "")
    if with_chains and fmt in _ATOM_FORMATS:
        try:
            chains = list(fixchain_payload(path).get("chains") or [])
            # 单 root 会误报的两条规则看整个池子:构建可能在 loop engine 后起的 build 会话里,
            # 分析代理可能起在 spec 开始的那个首启会话里
            pool_builds = atoms.build_evidence(session_ledger(path))
            pool_agents = []
            for pp in prior_roots(fmt, path, cwd):
                tr = extract_trace(pp)
                sid8 = str((tr.get("meta") or {}).get("session_id") or "")[:8]
                pool_agents += [{**a, "sid8": sid8} for a in (tr.get("lineage") or {}).get("agents") or []
                                if isinstance(a, dict)]
        except Exception:
            chains = None                          # 链算不出不拖垮报告
    data["audit"] = audit.build_audit(data, fix_chains=chains, pool_builds=pool_builds,
                                      pool_agents=pool_agents)
    later = later_roots(fmt, path, cwd)
    prior = prior_roots(fmt, path, cwd)[:1]
    hint = {"later": root_sid8(fmt, later[0]) if later else None,
            "prior": root_sid8(fmt, prior[0]) if prior else None}
    if hint["later"] or hint["prior"]:
        data["audit"]["cross_hint"] = hint
    if static or fmt not in _ATOM_FORMATS:
        data["urls"] = {"fixchain": None}
    return data


def report_html(path: str) -> str:
    return build_html(report_trace(path), load_template())


def fixchain_light(path: str) -> dict[str, Any]:
    """链页首屏:入口列表只从链缓存拿(没缓存先空着,页面拿到 fixchain-data 自己填)。"""
    data = extract_trace(path)
    meta = data.get("meta") or {}
    fmt = _fmt_of(data)
    if fmt not in _ATOM_FORMATS:
        raise SessionLookupError(f"返修链路暂不支持 {fmt} 会话")
    cwd = str(meta.get("cwd") or "")
    cwd_norm = cwd.replace("\\", "/").rstrip("/")
    fixes: list[dict[str, Any]] = []
    fixers: list[dict[str, Any]] = []
    with _LOCK:
        hit = _FIXCHAIN_CACHE.get(path)
    if hit is not None:
        fixes, fixers = filestory.chain_entry_lists(list(hit[1].get("chains") or []))
    later_paths = later_roots(fmt, path, cwd)
    later = None
    if later_paths:
        lsid = root_sid8(fmt, later_paths[0])
        if lsid:
            later = {"sid8": lsid, "url": f"/api/insight1/fixchain/{lsid}"}
    sid = str(meta.get("session_id") or root_sid8(fmt, path))
    return {
        "sid8": sid[:8], "sid": sid,
        "project": next((x for x in reversed(cwd_norm.split("/")) if x), ""),
        "fixes": fixes, "fixers": fixers, "later": later,
    }


def fixchain_html(path: str) -> str:
    payload = fixchain_light(path)
    return load_asset("fixchain.html").replace("__FIXCHAIN_JSON__",
                                               json.dumps(payload, ensure_ascii=False))


# ═══════════════ 两原子端点(JSON / 文本) ═══════════════

def _opt_int(args: dict[str, Any], key: str) -> int | None:
    v = args.get(key)
    if v is None or v == "":
        return None
    return int(v)


def _flag(args: dict[str, Any], key: str, default: str) -> bool:
    return str(args.get(key, default)) not in ("0", "false", "")


def atom_json(path: str, tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """index / file / agent / blame / action 的 JSON 形态。参数缺失抛 ValueError。"""
    ledger = session_ledger(path)
    if tool == "index":
        return atoms.ledger_index(ledger)
    if tool == "file":
        if not args.get("path"):
            raise ValueError("path")
        return atoms.file_atom(ledger, str(args["path"]), _opt_int(args, "v"),
                               with_diff=_flag(args, "diff", "1"),
                               with_content=_flag(args, "content", "1"))
    if tool == "agent":
        if not args.get("id"):
            raise ValueError("id")
        return atoms.agent_atom(ledger, str(args["id"]), _opt_int(args, "v"),
                                since=_opt_int(args, "since"))
    if tool == "blame":
        if not args.get("path"):
            raise ValueError("path")
        return atoms.blame(ledger, str(args["path"]), _opt_int(args, "v"),
                           _opt_int(args, "start"), _opt_int(args, "n"))
    if tool == "action":
        if not args.get("id") or args.get("seq") is None:
            raise ValueError("id, seq")
        return atoms.action_raw(ledger, str(args["id"]), int(args["seq"]))
    raise ValueError(f"unknown atom tool: {tool}")


def atom_text(path: str, tool: str, args: dict[str, Any]) -> str:
    """MCP 工具的 HTTP 化身:同一套 atoms_text 渲染。"""
    from . import mcp_server

    if tool == "guide":
        return mcp_server.GUIDE
    cwd = session_cwd(path)
    if tool == "sessions":
        return atoms_text.render_chains(fixchain_payload(path), root=cwd, file=args.get("path") or None)
    ledger = session_ledger(path)
    if tool == "index":
        return atoms_text.render_index(ledger, args.get("kind") or None, args.get("query") or None,
                                       root=cwd, limit=_opt_int(args, "limit") or 300)
    if tool == "file" and args.get("path"):
        return atoms_text.render_file(ledger, str(args["path"]), _opt_int(args, "v"), root=cwd,
                                      content=_flag(args, "content", "0"),
                                      diff=_flag(args, "diff", "0"),
                                      start=_opt_int(args, "start"), n=_opt_int(args, "n"))
    if tool == "agent" and args.get("id"):
        return atoms_text.render_agent(ledger, str(args["id"]), _opt_int(args, "v"), root=cwd,
                                       since=_opt_int(args, "since"))
    if tool == "blame" and args.get("path"):
        return atoms_text.render_blame(ledger, str(args["path"]), _opt_int(args, "v"),
                                       _opt_int(args, "start"), _opt_int(args, "n"), root=cwd,
                                       changed=_flag(args, "changed", "0"))
    if tool == "diff" and args.get("path") and args.get("v") is not None:
        return atoms_text.render_diff(ledger, str(args["path"]), int(args["v"]), root=cwd)
    if tool == "action" and args.get("id") and args.get("seq") is not None:
        return atoms_text.render_action(ledger, str(args["id"]), int(args["seq"]))
    raise ValueError(f"未知工具或缺参数: {tool}")


def file_diff(path: str, file: str, v: int) -> dict[str, Any] | None:
    return filestory.diff_payload(session_ledger(path).stories, file, v)


# ═══════════════ MCP 后端 ═══════════════

class McpBackend:
    """mcp_server.build_server 的后端:sid(会话 id / 前缀 / 路径)→ 本地会话,共用上面的缓存。"""

    async def get_ledger(self, sid: str) -> Any:
        return session_ledger(locate_session(sid))

    async def get_session_cwd(self, sid: str) -> str:
        return session_cwd(locate_session(sid))

    async def get_fixchain(self, sid: str) -> dict[str, Any]:
        return fixchain_payload(locate_session(sid))
