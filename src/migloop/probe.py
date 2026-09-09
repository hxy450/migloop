"""调查覆盖:把一次调查员(模型)的跑叠到探索树上 ——
它每一次工具调用落到哪个节点(文件@版 / agent@版),它报告里每一环指到哪个节点、判成什么(传递 / 错 / 缺)、故障进入点是哪一环。
探索树是给人做调查用的;这里只是把模型做的调查在同一棵树上展开:查过的节点打「第 k 步」,判过的节点按判定上色。

输入是 run 目录:transcript.jsonl 的原始调用/返回与运行时工具事件是访问事实,metrics.json 提供统计。
Codex 缺 rollout 时才读取 events.jsonl,保留 item_id 来源;更老的跑才回退 metrics 调用摘要。
result.json 的 result(Claude)或 response_text(Codex)是报告正文。文件用账本绝对路径,agent 用账本 id。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import datetime
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
    """请求参数中的范围，不认证实际交付正文；未知内容/未命中仍可有正常工具返回。"""
    v = inp.get("v")
    vs = f" v{v}" if v is not None else ""
    if tool == "file":
        if inp.get("diff"):
            window = (f" 窗口 v{inp.get('v_from', 1)}–v{inp.get('v_to', v)}"
                      if inp.get("v_from") is not None or inp.get("v_to") is not None else "")
            return "差分" + vs + window
        if inp.get("content"):
            start = int(inp.get("start") or 1)
            rng = (f" {start}-{start + int(inp['n']) - 1}行" if inp.get("n")
                   else (f" 从{start}行起" if inp.get("start") else ""))
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
        terms = inp.get("q_any")
        return "搜索窗口" + vs + (" · 字面量 OR：" + json.dumps(terms, ensure_ascii=False) if isinstance(terms, list) else "")
    if tool == "action":
        return "原文 " + str(inp.get("ref") or f"#{inp.get('seq')}") + (f" {inp['part']}" if inp.get("part") else "")
    if tool == "sessions":
        return "返修链"
    if tool == "check":
        return "草稿机械核查（不验证语义、不打开节点）"
    return "索引查询"


def _load_run(run_dir: str) -> tuple[dict[str, Any], str]:
    with open(os.path.join(run_dir, "metrics.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as fh:
        r = json.load(fh)
    body = r.get("response_text") if r.get("schema") == "migloop-codex-result/1" else r.get("result")
    return m, str(body or "")


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
    ak = lambda h: ledger.agents.get(via.resolve_key(ledger, "agent", str(h)) or "") if h else None  # noqa: E731
    if tool in ("file", "diff", "blame"):
        return {"kind": "file", "path": fk(inp.get("path")), "v": _int(inp.get("v"))}
    if tool == "agent":
        a = ak(inp.get("id"))
        return {"kind": "agent", "aid": a.id if a else None, "v": _int(inp.get("v")), "since": _int(inp.get("since"))}
    if tool == "action":
        from .action_query import resolve, step
        from .atom_queries import optional_int
        try:
            address = resolve(ledger, id=inp.get("id"), seq=optional_int(inp, "seq"), ref=inp.get("ref"))
        except ValueError:
            return None
        return step(ledger, address)
    if tool == "search":
        if inp.get("agent"):
            a = ak(inp.get("agent"))
            return {"kind": "agent", "aid": a.id if a else None, "v": _int(inp.get("v")), "q": inp.get("q")}
        if inp.get("file"):
            return {"kind": "file", "path": fk(inp.get("file")), "v": _int(inp.get("v")), "q": inp.get("q")}
        return {"kind": "pool", "q": inp.get("q"), "until_ts": inp.get("until_ts"), "since_ts": inp.get("since_ts")}
    if tool == "sessions":
        return {"kind": "chain", "path": fk(inp.get("file") or inp.get("path"))}
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


def probe_payload(ledger: atoms.Ledger, run_dir: str, chain_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    m, report = _load_run(run_dir)
    calls = _transcript_calls(run_dir)
    trace_identity = via.trace_identity(ledger, calls, m)
    seq = calls if calls is not None else ((m.get("transcript") or {}).get("seq") or [])
    steps: list[dict[str, Any]] = []
    for i, s in enumerate(seq, 1):
        inp = {k: v for k, v in (s.get("input") or {}).items() if k != "sid"}
        steps.append({"i": i, "tool": s.get("tool"), "args": inp, "chars": s.get("chars") or 0,
                      "node": None if (s.get("provenance") or {}).get("origin_unverified") else
                              _step_node(ledger, str(s.get("tool")), inp),
                      "ok": not s.get("is_error") and (bool(s.get("has_result")) if calls is not None else True),
                      "result_present": s.get("has_result"), "result_ref": s.get("id"),
                      "call_id": s.get("call_id"), "item_id": s.get("item_id"),
                      "provenance": s.get("provenance"), "parse_error": s.get("parse_error"),
                      "use_line": s.get("use_line"), "result_line": s.get("result_line"),
                      "use_event": s.get("use_event"), "result_event": s.get("result_event"),
                      "use_time_ms": s.get("use_time_ms"), "result_time_ms": s.get("result_time_ms"),
                      "scope": _step_scope(str(s.get("tool")), inp)
                               + (" · 返回截断／非全文" if s.get("delivery_truncated") else ""),
                      "delivery_truncated": bool(s.get("delivery_truncated")),
                      "identity_unbound": trace_identity["bound"] is False,
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
    structured = _structured(ledger, run_dir, report, trace_identity=trace_identity, calls=calls)
    from . import draft_check, findings
    # Bind the document actually displayed (a saved schema-repair result may
    # differ from the original report), not a second hidden interpretation.
    checked_draft = draft_check.final_binding(ledger, calls, None,
        identity_bound=(trace_identity.get("bound") is True
                        and (structured or {}).get("identity", {}).get("bound") is True),
        final_document_sha256=(structured or {}).get("document_sha256"))
    if structured is not None:
        if structured["defects"]:
            defects = {d["id"]: d["title"] for d in structured["defects"]}
        sr = structured.get("root")
        if sr and sr.get("ok") and sr.get("kind") == "file":
            root = sr["key"]
    repair_manifest = coverage_report = manifest_origin = None
    if chain_payload is not None and root:
        from . import coverage as repair_coverage
        from .coverage_snapshot import select_manifest
        current_manifest = repair_coverage.manifest(ledger, chain_payload, root)
        repair_manifest, manifest_origin = select_manifest(
            ledger, current_manifest, (structured or {}).get("recorded_repair_manifest"))
        coverage_report = repair_coverage.reconcile_document(
            ledger, repair_manifest, (structured or {}).get("coverage_rows"),
            (structured or {}).get("defects") or [],
            identity_bound=((structured or {}).get("identity", {}).get("bound") is True
                            and manifest_origin.get("bound") is True),
            schema=(structured or {}).get("schema"))
    trajectory = _trajectory(ledger, run_dir, steps, root, structured, verdicts, calls, trace_identity)
    return {"run": os.path.basename(os.path.dirname(os.path.abspath(run_dir))), "cost": m.get("cost_usd"), "turns": m.get("num_turns"),
            "root": root, "steps": steps, "links": links, "entry": entry_no, "entries": entries, "verdicts": verdicts,
            "bad_refs": sum(len(lk["bad_refs"]) for lk in links), "defects": defects, "report": report,
            "legacy": structured is None, "structured": structured,
            "trace_identity": trace_identity, "repair_manifest": repair_manifest, "coverage": coverage_report,
            "repair_manifest_origin": manifest_origin, "draft_check": checked_draft,
            "roles": (structured or {}).get("roles") or {}, "fixed": (structured or {}).get("fixed") or [],
            "trajectory": trajectory, "evidence_graph": _evidence_graph(ledger, trajectory, trace_identity, structured),
            "findings": findings.project(structured)}


def _structured(ledger: atoms.Ledger, run_dir: str, report: str,
                trace_identity: dict[str, Any] | None = None,
                calls: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Load only a document with original text; cached data is not authorship.

    Legacy schema-repair bodies remain readable with explicit saved provenance.
    A reference submission still requires the same run's authenticated check.
    """
    vp = os.path.join(run_dir, "verdict.json")
    vj: dict[str, Any] = {}
    if os.path.isfile(vp):
        with open(vp, encoding="utf-8") as fh:
            vj = json.load(fh)
    from .submission import load_submission
    from .draft_check import document_hash
    loaded = load_submission(report, ledger, calls if calls is not None else _transcript_calls(run_dir),
                             trace_identity, vj.get("harness_identity"))
    reference_mode = loaded["submission"]["mode"] == "checked_draft_ref"
    saved_submission = vj.get("submission") if isinstance(vj.get("submission"), dict) else {}
    if reference_mode or saved_submission.get("mode") == "checked_draft_ref":
        # A saved data object is not authentication for a reference submission.
        # Reopen only the same run's original check; absent/bad final ref fails.
        errors = list(loaded["errors"])
        if not reference_mode:
            errors.append("已保存引用式结论，但最终回复没有对应的显式提交引用")
        built = verdict.build(ledger, None if errors else loaded["data"], errors, {
            "kind": loaded["kind"], "raw": loaded["raw"], "trace_identity": trace_identity,
            "harness_identity": vj.get("harness_identity"),
            "recorded_repair_manifest": vj.get("repair_manifest")})
        built["submission"] = loaded["submission"]
        built["document_source"] = {
            "kind": "checked_draft_ref", "verified": not errors and loaded["submission"]["status"] == "accepted",
            "semantic_checked": False, "raw_matches_data": True if not errors else None,
            "final_matches_document": None,
            "note": "引用稿来自同 run 的原始 check 输入，按来源与双哈希认证；不是原因或修复语义验证。"
                    if not errors else "引用提交来源认证失败；保留原文与诊断，不使用保存 data 补救。"}
        return built
    if vj:
        data = vj.get("data")
        raw, kind = vj.get("raw"), vj.get("kind")
        previous_errors = list(vj.get("errors") or [])
        errors = verdict.validate(data) if data is not None else []
        revalidated = False
        raw_matches = None
        final_valid = loaded["data"] is not None and not loaded["errors"]
        final_hash = document_hash(loaded["data"]) if final_valid else None
        data_hash = document_hash(data) if data is not None and not errors else None
        if raw is not None:
            if not isinstance(raw, str) or kind not in ("yaml", "json"):
                errors.append("保存稿 raw 必须有可解析的 yaml/json 原文与格式，不能仅信任 data")
            else:
                candidate, parse_errors = verdict.parse_block(kind, raw)
                current_errors = parse_errors or verdict.validate(candidate)
                if current_errors:
                    errors.extend("保存稿 raw 无效: " + error for error in current_errors)
                elif data is None:
                    # Preserve the original body of old notes/schema revalidation.
                    data, data_hash, revalidated = candidate, document_hash(candidate), True
                elif data_hash is not None:
                    raw_matches = document_hash(candidate) == data_hash
                    if not raw_matches:
                        errors.append("保存稿 raw 与 data 文档不一致；不能将缓存解释标成模型原文")
        elif final_valid and (data is None or data_hash == final_hash) and not errors:
            # Missing cached raw may be recovered only from the matching final.
            data, data_hash, raw, kind = loaded["data"], final_hash, loaded["raw"], loaded["kind"]
        elif data is not None:
            errors.append("保存稿没有原文，最终回复也没有与 data 一致的有效文档；主张来源不可核")
        if data is None and raw is None and not vj.get("found", True) and not loaded["found"]:
            return None
        if data is None and not errors:
            errors = list(loaded["errors"] or previous_errors or ["未提供可核验的保存稿原文"])
        final_matches = (data_hash == final_hash) if data_hash is not None and final_valid else None
        if saved_submission.get("mode") == "inline" and final_matches is not True:
            errors.append("显式 inline 提交必须与有效最终正文一致；保存稿不能替代缺失或不同的最终提交")
        source_kind = "invalid_saved" if errors else "final_inline" if final_matches else (
            "saved_schema_repair" if vj.get("repaired") else "legacy_saved")
        if source_kind == "final_inline":
            # The displayed original is now the actual final body, not a cache's
            # equivalent formatting. Raw cache artifacts themselves stay intact.
            raw, kind = loaded["raw"], loaded["kind"]
        meta = {"kind": kind, "raw": raw, "repaired": vj.get("repaired"),
                "harness_identity": vj.get("harness_identity"),
                "recorded_repair_manifest": vj.get("repair_manifest"),
                "trace_identity": trace_identity,
                "revalidated": revalidated, "previous_errors": previous_errors if revalidated else []}
        source = {"kind": source_kind, "verified": source_kind == "final_inline", "semantic_checked": False,
                  "raw_matches_data": raw_matches, "final_matches_document": final_matches,
                  "note": {"final_inline": "当前文档与最终 inline 原文内容一致；只认证正文来源，不认证归因语义。",
                           "saved_schema_repair": "显示历史 schema 修复的保存原文，未认证为最终提交；仍是未验证的历史主张。",
                           "legacy_saved": "显示可解析的历史保存原文，未认证为最终提交；不冒充当前模型最终回复。",
                           "invalid_saved": "保存稿原文、解释或最终提交不一致/不可核；仅保留诊断，不绑定问题主张。"}[source_kind]}
        submitted = loaded["submission"] if source_kind == "final_inline" else {
            "schema": "migloop-submission/1", "mode": "saved_document", "semantic_checked": False,
            "status": "rejected" if errors else "legacy_unverified",
            "final_submission_status": loaded["submission"].get("status")}
        return {**verdict.build(ledger, None if errors else data, errors, meta),
                "submission": submitted, "document_source": source}
    lb = loaded
    if not lb["found"]:
        return None
    return {**verdict.build(ledger, lb["data"], lb["errors"], {"kind": lb["kind"], "raw": lb["raw"],
                                                            "trace_identity": trace_identity}),
            "submission": lb["submission"],
            "document_source": {"kind": "final_inline", "verified": not lb["errors"], "semantic_checked": False,
                                "raw_matches_data": None, "final_matches_document": not lb["errors"],
                                "note": "文档来自最终 inline 原文；正文来源核验不等于归因正确。"
                                        if not lb["errors"] else "最终原文未通过格式核验，主张未绑定。"}}


# ═══════════════ 调查路径与账本关系分层 ═══════════════
# visits 按实际调用/返回核版本坐标;transitions 保留每次声明的 via,包括回访、自环和多来处。
# via 的源节点必须在该次调用开始前已返回;声明转移的账本关系另核为写/读/派发或未知。
# 布局节点按 agent@版本 / file@版本 去重,布局父只在首次访问时设置,不吞掉其余转移记录。
# 旧跑没有 via 时保留账本关系树,明确标未验证,不称作模型路线。账本树根是被修文件最终版。
# 「出现于 #j」只说明第 j 次返回文本含精确坐标,不推出模型为何选择下一跳。


_MIGLOOP_TOOLS = frozenset(("guide", "sessions", "index", "file", "agent", "search", "blame", "diff", "action", "check"))


def _tool_origin(name: Any, namespace: Any = None, server: Any = None) -> dict[str, Any]:
    """A bare tool name is not a server identity; preserve every explicit provider."""
    raw = str(name or "")
    qualified = re.fullmatch(r"mcp__(.+?)__(.+)", raw)
    leaf = qualified[2] if qualified else raw.removeprefix("functions.")
    providers = [qualified[1]] if qualified else []
    if namespace is not None:
        providers.append(namespace.removeprefix("mcp__").removesuffix("__")
                         if isinstance(namespace, str) and namespace.startswith("mcp__") else "namespace:" + str(namespace))
    if server is not None:
        providers.append(str(server))
    errors = ["conflicting explicit tool providers"] if len(set(providers)) > 1 else []
    provider = providers[0] if providers else None
    tool = leaf if provider in (None, "migloop") or provider.startswith("namespace:") else f"mcp__{provider}__{leaf}"
    return {"name": raw, "namespace": namespace, "server": server, "provider": provider, "leaf": leaf,
            "tool": tool, "verified": provider == "migloop" and not errors, "errors": errors}


def _merge_tool_origins(a: dict[str, Any], b: dict[str, Any], left: Any, right: Any) -> dict[str, Any]:
    errors = list(dict.fromkeys([*a["errors"], *b["errors"]]))
    if a["provider"] is not None and b["provider"] is not None and a["provider"] != b["provider"]:
        errors.append("same ID has conflicting tool providers")
    if a["leaf"] != b["leaf"]:
        errors.append("same ID has conflicting tool names")
    if json.dumps(left, sort_keys=True, ensure_ascii=False) != json.dumps(right, sort_keys=True, ensure_ascii=False):
        errors.append("same ID has conflicting arguments")
    chosen = b if a["provider"] is None else a
    return {**chosen, "verified": bool((a["verified"] or b["verified"]) and not errors), "errors": errors,
            "representations": [a, b]}


def _origin_guard(call: dict[str, Any], origin: dict[str, Any]) -> None:
    call["tool"] = origin["tool"]
    call["provenance"]["tool_origin"] = origin
    if origin["errors"] or (origin["leaf"] in _MIGLOOP_TOOLS and not origin["verified"]):
        call["provenance"]["complete_pair"] = False
        call["provenance"]["origin_unverified"] = True


def _transcript_calls(run_dir: str) -> list[dict[str, Any]] | None:
    """Claude tool_use_id / Codex rollout call_id 配对;缺返回保持 pending。

    Codex 的 response_item 与事件摘要不是同一种记录,不把 stdout item.id 当成 call_id。
    """
    p = os.path.join(run_dir, "transcript.jsonl")
    if not os.path.isfile(p):
        return _codex_event_calls(run_dir)
    order: list[str] = []
    calls: dict[str, dict[str, Any]] = {}
    results: dict[str, dict[str, Any]] = {}
    event = 0
    record_ms: float | None = None

    def call(tid: Any, name: Any, args: Any, line_no: int, fmt: str,
             parse_error: str | None = None, namespace: Any = None) -> None:
        native_id = tid if isinstance(tid, str) and tid else None
        key = f"{fmt}:{native_id}" if native_id else f"missing-id:{line_no}:{event}"
        origin = _tool_origin(name, namespace)
        if key in calls:
            prior = calls[key]
            _origin_guard(prior, _merge_tool_origins(prior["provenance"]["tool_origin"], origin, prior["input"], args))
            return                                      # 相同 id 的一致流式重放不新增访问
        tool = origin["tool"]
        order.append(key)
        calls[key] = {"id": native_id or key, "call_id": native_id, "item_id": None,
                      "tool": tool, "input": args if isinstance(args, dict) else {},
                      "has_result": False, "text": "", "chars": 0, "is_error": bool(parse_error),
                      "parse_error": parse_error, "use_line": line_no, "use_event": event,
                      "use_time_ms": record_ms, "result_time_ms": None,
                      "result_line": None, "result_event": None,
                      "provenance": {"format": fmt, "path": "transcript.jsonl",
                                     "pairing": "call_id" if fmt == "codex_rollout" else "tool_use_id"}}
        _origin_guard(calls[key], origin)

    def result(tid: Any, output: Any, failed: bool, line_no: int, fmt: str) -> None:
        if not isinstance(tid, str) or not tid:
            return                                      # 无 id 的结果不可与另一个无 id 的调用互猜
        txt, content_error = _tool_output(output)
        raw_chars = len(output) if isinstance(output, str) else len(txt)
        response = {"text": txt, "chars": raw_chars, "has_result": True,
                    "is_error": failed or content_error, "result_line": line_no, "result_event": event,
                    "result_time_ms": record_ms}
        # Observed native Codex format: a separate runtime-header input_text block
        # followed by body blocks. Merely recognizing its shape is not authority
        # to strip it; dedup must corroborate the exact body with a trusted item.
        if fmt == "codex_rollout" and isinstance(output, list) and len(output) >= 2 \
                and all(isinstance(b, dict) and b.get("type") == "input_text" and isinstance(b.get("text"), str) for b in output) \
                and re.fullmatch(r"Wall time: \d+(?:\.\d+)? seconds\nOutput:", output[0]["text"]):
            response["_transport_blocks"] = {"header": output[0]["text"], "body": "\n".join(b["text"] for b in output[1:])}
        results.setdefault(f"{fmt}:{tid}", response)

    with open(p, encoding="utf-8", errors="ignore") as fh:
        for line_no, line in enumerate(fh, 1):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(r, dict):
                continue
            record_ms = _timestamp_ms(r.get("timestamp"))
            payload = r.get("payload")
            if r.get("type") == "event_msg" and isinstance(payload, dict) \
                    and payload.get("type") == "item_completed" \
                    and isinstance(payload.get("item"), dict) and payload["item"].get("type") == "McpToolCall":
                event += 1
                item = payload["item"]
                item_id = item.get("id") if isinstance(item.get("id"), str) else None
                key = f"codex_rollout_item:{item_id}" if item_id else f"missing-item:{line_no}"
                if key not in calls:
                    args, error = _call_arguments(item.get("arguments"))
                    text, failed = _tool_output(item.get("result"))
                    failed = failed or item.get("status") in ("failed", "error") or item.get("error") is not None
                    if not text and item.get("error") is not None:
                        text, _ = _tool_output({"error": item["error"]})
                    start, end = payload.get("started_at_ms"), payload.get("completed_at_ms")
                    complete = isinstance(start, (int, float)) and isinstance(end, (int, float)) and start <= end
                    origin = _tool_origin(item.get("tool") or "McpToolCall", server=item.get("server"))
                    tool = origin["tool"]
                    calls[key] = {"id": None, "call_id": None, "item_id": item_id, "tool": tool, "input": args,
                                  "has_result": item.get("result") is not None or failed, "text": text,
                                  "chars": len(text), "is_error": bool(error) or failed, "parse_error": error,
                                  "use_line": None, "result_line": line_no, "use_event": None, "result_event": event,
                                  "use_time_ms": start if complete else None, "result_time_ms": end if complete else None,
                                  "provenance": {"format": "codex_rollout_event", "path": "transcript.jsonl",
                                                 "pairing": "item_runtime", "complete_pair": bool(item_id and complete),
                                                 "reported_call_id": item.get("call_id")}}
                    _origin_guard(calls[key], origin)
                    order.append(key)
                else:
                    args, _ = _call_arguments(item.get("arguments"))
                    prior = calls[key]
                    _origin_guard(prior, _merge_tool_origins(prior["provenance"]["tool_origin"],
                        _tool_origin(item.get("tool"), server=item.get("server")), prior["input"], args))
                continue
            if r.get("type") == "response_item" and isinstance(payload, dict):
                event += 1
                ptype = payload.get("type")
                if ptype in ("function_call", "custom_tool_call"):
                    raw = payload.get("arguments") if ptype == "function_call" else payload.get("input")
                    if ptype == "custom_tool_call":
                        args, error = {"input": raw}, None
                    else:
                        args, error = _call_arguments(raw)
                    call(payload.get("call_id"), payload.get("name"), args, line_no, "codex_rollout", error, payload.get("namespace"))
                elif ptype in ("function_call_output", "custom_tool_call_output"):
                    result(payload.get("call_id"), payload.get("output"), bool(payload.get("is_error") or
                           payload.get("isError")), line_no, "codex_rollout")
                continue
            m = r.get("message") if isinstance(r.get("message"), dict) else {}
            content = m.get("content")
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                event += 1
                if r.get("type") == "assistant" and b.get("type") == "tool_use":
                    args, error = _call_arguments(b.get("input") or {})
                    call(b.get("id"), b.get("name"), args, line_no, "claude_transcript", error)
                elif r.get("type") == "user" and b.get("type") == "tool_result":
                    result(b.get("tool_use_id"), b.get("content"), bool(b.get("is_error")), line_no, "claude_transcript")
    for tid, response in results.items():
        if tid in calls and response["result_event"] > calls[tid]["use_event"]:
            failed = calls[tid]["is_error"] or response["is_error"]
            calls[tid].update(response, is_error=failed)
    rows = _deduplicate_runtime_calls([calls[t] for t in order])
    if any(c["provenance"]["format"] == "codex_rollout_event" for c in rows) \
            and all(c.get("use_time_ms") is not None for c in rows):
        rows.sort(key=lambda c: c["use_time_ms"])
    return rows


def _partial_delivery(delivered: str, runtime: str) -> dict[str, int] | None:
    """One observed Codex middle-omission marker, with both visible sides exact.

    Token count is only the transport's report; omitted character count is checked.
    The complete first line must be visible, so a cut header never authenticates a node.
    """
    markers = list(re.finditer(r"…([1-9][0-9]{0,8}) tokens truncated…", delivered))
    if len(markers) != 1:
        return None
    marker = markers[0]
    prefix, suffix = delivered[:marker.start()], delivered[marker.end():]
    first_end = runtime.find("\n")
    omitted = len(runtime) - len(prefix) - len(suffix)
    if first_end < 0 or len(prefix) <= first_end or not suffix or omitted <= 0 \
            or not runtime.startswith(prefix) or not runtime.endswith(suffix):
        return None
    return {"visible_chars": len(prefix) + len(suffix), "omitted_chars": omitted,
            "omission_start": len(prefix), "omission_end": len(runtime) - len(suffix),
            "reported_omitted_tokens": int(marker[1])}


def _deduplicate_runtime_calls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一原生调用的两种表示只按明确 id 合并,不按参数或时间相似性猜。"""
    direct = {c["call_id"]: c for c in rows if c.get("call_id") and c["provenance"]["format"] == "codex_rollout"}
    kept = []
    for row in rows:
        provenance = row["provenance"]
        ids = {x for x in (row.get("item_id"), provenance.get("reported_call_id")) if isinstance(x, str)}
        matches = ids & direct.keys() if provenance["format"] == "codex_rollout_event" else set()
        if len(matches) != 1:
            kept.append(row)
            continue
        primary = direct[next(iter(matches))]
        origin = _merge_tool_origins(primary["provenance"]["tool_origin"], provenance["tool_origin"],
                                     primary["input"], row["input"])
        if primary["provenance"].pop("origin_unverified", False) and not origin["errors"] and origin["verified"]:
            primary["provenance"].pop("complete_pair", None)
        _origin_guard(primary, origin)
        primary["item_id"] = row["item_id"]
        primary["provenance"]["runtime_item"] = {"item_id": row["item_id"], "line": row["result_line"],
                                                 "tool_origin": provenance["tool_origin"], "input": row["input"],
                                                 "started_at_ms": row.get("use_time_ms"),
                                                 "completed_at_ms": row.get("result_time_ms")}
        envelope = primary.get("_transport_blocks")
        if envelope:
            trusted = origin["verified"] and provenance.get("complete_pair") is True and row["has_result"]
            matches_body = envelope["body"] == row["text"]
            partial = None if matches_body else _partial_delivery(envelope["body"], row["text"])
            normalization = {"kind": "codex_native_input_text_blocks", "status": "unverified",
                             "header": envelope["header"], "response_result_line": primary["result_line"],
                             "runtime_result_line": row["result_line"], "runtime_item_id": row["item_id"],
                             "exact_body_match": matches_body,
                             "response_body_chars": len(envelope["body"]), "runtime_body_chars": len(row["text"]),
                             "response_body_sha256": hashlib.sha256(envelope["body"].encode("utf-8")).hexdigest(),
                             "runtime_body_sha256": hashlib.sha256(row["text"].encode("utf-8")).hexdigest(),
                             "note": "原生来源/完整配对或正文一致性未核验,保留原始文本"}
            if trusted and (matches_body or partial is not None):
                primary.setdefault("raw_text", primary["text"])
                primary["text"] = envelope["body"]
                primary["delivery_truncated"] = partial is not None
                normalization.update(status="verified", note="独立传输头块已移除;正文与同 ID、来源和参数一致的完整原生返回逐字相同")
                normalization.update(delivery_truncated=partial is not None,
                                     visible_chars=len(envelope["body"]), omitted_chars=0)
                if partial is not None:
                    normalization.update(partial)
                    normalization["note"] = "返回截断／非全文:交付正文的可见前后缀与同 ID 原生返回逐字吻合;保留交付片段,未用完整原生正文替代"
            elif "raw_text" in primary:
                primary["text"] = primary["raw_text"]
                primary["delivery_truncated"] = False
            primary["provenance"]["output_normalization"] = normalization
        if not primary["has_result"] and row["has_result"]:
            for key in ("has_result", "text", "chars", "result_line", "result_event", "result_time_ms"):
                primary[key] = row[key]
        primary["is_error"] = primary["is_error"] or row["is_error"]
    for call in kept:
        provenance = call["provenance"]
        if provenance["format"] in ("claude_transcript", "codex_rollout"):
            # Direct native records establish pairing by their own ID and
            # ordered use/result events, including after runtime deduplication.
            provenance["complete_pair"] = bool(
                call.get("call_id") and call.get("has_result")
                and isinstance(call.get("use_event"), int)
                and isinstance(call.get("result_event"), int)
                and call["use_event"] < call["result_event"]
                and provenance.get("tool_origin", {}).get("verified") is True
                and not provenance.get("origin_unverified"))
        envelope = call.pop("_transport_blocks", None)
        if envelope and "output_normalization" not in call["provenance"]:
            call["provenance"]["output_normalization"] = {
                "kind": "codex_native_input_text_blocks", "status": "unverified", "header": envelope["header"],
                "response_result_line": call["result_line"], "runtime_result_line": None,
                "note": "无同 ID 完整原生返回核对,未剥离疑似传输头"}
    return kept


def _timestamp_ms(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
    except (ValueError, OverflowError, OSError):
        return None


def _codex_event_calls(run_dir: str) -> list[dict[str, Any]] | None:
    """没有 rollout 时保留 codex exec 的 item 事件摘要,明确标为降级证据。"""
    path = os.path.join(run_dir, "events.jsonl")
    if not os.path.isfile(path):
        return None
    calls: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8", errors="ignore") as stream:
        for line_no, line in enumerate(stream, 1):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict) or event.get("type") not in ("item.started", "item.completed"):
                continue
            item = event.get("item")
            if not isinstance(item, dict) or item.get("type") not in (
                    "mcp_tool_call", "command_execution", "web_search", "file_change"):
                continue
            item_id = item.get("id") if isinstance(item.get("id"), str) else None
            key = item_id or f"missing-item-id:{line_no}"
            if key not in calls:
                if item["type"] == "mcp_tool_call":
                    args, parse_error = _call_arguments(item.get("arguments"))
                    origin = _tool_origin(item.get("tool") or "mcp_tool_call", server=item.get("server"))
                    tool = origin["tool"]
                else:
                    tool, args, parse_error = str(item["type"]), {"command": item.get("command")}, None
                calls[key] = {"id": None, "call_id": None, "item_id": item_id, "tool": tool, "input": args,
                              "has_result": False, "text": "", "chars": 0, "is_error": bool(parse_error),
                              "parse_error": parse_error, "use_line": None, "use_event": None,
                              "result_line": None, "result_event": None,
                              "provenance": {"format": "codex_exec_events", "path": "events.jsonl",
                                             "pairing": "item_id" if item_id else "unpaired_summary", "degraded": True,
                                             "complete_pair": False}}
            call = calls[key]
            if item["type"] == "mcp_tool_call":
                origin = _tool_origin(item.get("tool"), server=item.get("server"))
                if "tool_origin" in call["provenance"]:
                    current_args, _ = _call_arguments(item.get("arguments"))
                    origin = _merge_tool_origins(call["provenance"]["tool_origin"], origin, call["input"], current_args)
                _origin_guard(call, origin)
            if event["type"] == "item.started" and call["use_line"] is None:
                call.update(use_line=line_no, use_event=line_no)
            if event["type"] != "item.completed" or call["result_line"] is not None:
                continue
            output = item.get("result") if item["type"] == "mcp_tool_call" else item.get("aggregated_output")
            text, failed = _tool_output(output)
            failed = failed or item.get("status") in ("failed", "error") or item.get("error") is not None \
                or item.get("exit_code") not in (None, 0)
            if not text and item.get("error") is not None:
                text, _ = _tool_output({"error": item["error"]})
            call.update(text=text, chars=len(text), has_result=output is not None or failed,
                        is_error=call["is_error"] or failed, result_line=line_no, result_event=line_no)
            call["provenance"]["complete_pair"] = bool(item_id and call["use_line"] is not None and call["use_line"] < line_no
                                                        and not call["provenance"].get("origin_unverified"))
    return list(calls.values())


def _call_arguments(raw: Any) -> tuple[dict[str, Any], str | None]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, RecursionError):
            return {}, "工具参数不是有效 JSON 映射"
    return (raw, None) if isinstance(raw, dict) else ({}, "工具参数必须是映射")


def _tool_output(output: Any, depth: int = 0) -> tuple[str, bool]:
    """读取记录中的文本与显式错误标记;不把返回正文里提到的 error 当调用失败。"""
    if depth > 8:
        return str(output) if isinstance(output, str) else "", False
    if isinstance(output, str):
        try:
            obj = json.loads(output) if output.lstrip().startswith(("{", "[")) else None
        except (ValueError, RecursionError):
            obj = None
        if isinstance(obj, (dict, list)):
            return _tool_output(obj, depth + 1)
        return output, False
    if isinstance(output, list):
        parts = [_tool_output(part, depth + 1) for part in output]
        return "\n".join(text for text, _ in parts if text), any(error for _, error in parts)
    if isinstance(output, dict):
        failed = bool(output.get("isError") or output.get("is_error"))
        if output.get("type") in ("text", "input_text") and isinstance(output.get("text"), str):
            # An explicit text block is already the payload, not another
            # transport envelope. Preserve JSON-looking bodies byte-for-byte:
            # recursively decoding them changes whitespace or drops fields
            # named content/result/error, breaking native body authentication.
            return output["text"], failed
        for key in ("text", "content", "result", "output"):
            if key in output:
                text, nested_error = _tool_output(output[key], depth + 1)
                return text, failed or nested_error
        if output.get("error"):
            error = output["error"]
            return str(error.get("message") or error) if isinstance(error, dict) else str(error), failed
        if "type" not in output:
            return json.dumps(output, ensure_ascii=False), failed
    return "", False


def _transcript_results(run_dir: str) -> list[str] | None:
    """旧账本视图需要的返回正文;成功/待返回判定必须使用 _transcript_calls 的状态。"""
    calls = _transcript_calls(run_dir)
    return [c["text"] for c in calls] if calls is not None else None


def _unwrap_result(txt: str) -> str:
    """MCP 客户端把工具的字符串返回包成 {"result": "..."} 写进转录;拆出来才是模型看到的正文。"""
    if txt.lstrip().startswith('{'):
        obj, errors = verdict.parse_block("json", txt)
        if not errors and isinstance(obj, dict) and set(obj) == {"result"} and isinstance(obj["result"], str):
            return obj["result"]
    return txt


def _sight(text: str, kind: str, key: str, v: int | None, ledger: atoms.Ledger | None) -> tuple[bool, bool]:
    """返回文本里有没有这个节点 → (有这个键, 版本也对上了)。文件按最长能匹配的路径后缀;agent 按 id / 尾段 / 主会话号 / 名字。"""
    if kind == "file":
        parts = [x for x in key.replace("\\", "/").split("/") if x]
        for i in range(len(parts)):
            suf = "/".join(parts[i:])
            if suf in text:
                exact = (v is None or (re.search(r"(?<![\w/\\.-])" + re.escape(suf) + r"[ \t]*@v" + str(v) + r"\b", text)
                                      is not None and (ledger is None or via.resolve_key(ledger, "file", suf) == key)))
                return True, exact
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
    seen = False
    for f in forms:
        if f and f in text:
            seen = True
            exact = v is None or re.search(r"(?<![\w.-])" + re.escape(f) + r"(?:\)?[ \t]+@?v|\)?@v)" + str(v) + r"\b", text) is not None
            if exact:
                return True, True
    return seen, False


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
    """账本里这个节点的上游邻居:file@v → 写者@写者版本;agent@v → 喂养 ≤v 的确定读取 + 派发者。
    v=None(整个:文件的索引就是最新版视图,agent 的整个逐版都列)→ 全部版本的邻居并起来。"""
    out: set[tuple[str, str, int | None]] = set()
    if kind == "file":
        st = ledger.stories.get(key)
        if st is None:
            return out
        for ver in st.versions if v is None else st.versions[v - 1:v]:
            if ver.by in ledger.agents:
                out.add(("agent", ver.by, ver.by_ver))
        return out
    a = ledger.agents.get(key)
    if a is None:
        return out
    for act in a.actions:
        feed = act.ver if act.ver is not None else act.at
        if v is not None and feed > v:
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
    if texts is None:
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

    # A report-only file has no version node. An explicit valid agent claim may
    # anchor the view, but it is not evidence that the investigator opened it.
    st = ledger.stories.get(root)
    claim_root = (structured or {}).get("root") or {}
    if claim_root.get("ok") and claim_root.get("kind") == "agent":
        root_node = add("agent", claim_root["key"], claim_root["v"], "结论")
    elif st and st.versions:
        root_node = add("file", root, len(st.versions), "任务")
    else:
        return None
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
        i = int(s["i"])
        if land is None or s.get("ok") is False or not s.get("result_present") \
                or (i - 1 < len(texts) and _rejected(texts[i - 1])):
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
    # 出现于哪些步的返回(精确版本事实,不画边):打开该节点本身的步不算
    landing_by_step = {s["i"]: _step_landing(s) for s in steps}
    for n in nodes.values():
        for s in steps:
            i = int(s["i"])
            land = landing_by_step.get(i)
            if land == (n["kind"], n["key"], n["v"]):
                continue
            if s.get("ok") and s.get("result_present") and not _rejected(texts[i - 1]) \
                    and _sight(texts[i - 1], n["kind"], n["key"], n["v"], ledger)[1]:
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
        neighbors = [x for x in _upstream_neighbors(ledger, n["kind"], n["key"], n["v"])
                     if x not in present and x[2] is not None]
        n["unseen_neighbors"] = [{"kind": k, "key": key, "v": v} for k, key, v in sorted(neighbors)]
        n["unseen"] = len(n["unseen_neighbors"])
    ordered = sorted(order, key=lambda n: (0 if n is root_node else 1, n["depth"] if n["side"] == "up" else 10 ** 6, pos[n["id"]]))
    return {"mode": "ledger", "root": root_node["id"], "nodes": ordered, "edges": edges, "declared": [],
            "side_title": "查过 · 不在根的上下游"}


# ═══════════════ 按 via 走的树:打开了什么,从什么跳 ═══════════════
# 实体节点只出现一次;每次访问与每条声明转移单独保存,包括回访、自环、多父。
# parent 只用于首次发现的布局,transitions 才是完整的声明路线;账本关系是独立注记。


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


def _relation_check(ledger: atoms.Ledger, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """查询方向可逆,账本关系方向不变;与 verdict 共用 true/unknown/false 语义。"""
    from .evidence import read_basis
    endpoints = []
    for n in (a, b):
        exact, _ = via.target(ledger, n["kind"], n["key"], n.get("v"))
        endpoints.append({**n, "ok": exact is not None})
    aa, bb = endpoints
    checks = [(verdict.check_edge(ledger, left, right, None), left, right)
              for left, right in ((aa, bb), (bb, aa))]
    # 确定关系优先;读取未知优先于仅词法提及。不会把 unknown 转成实体读写边。
    rank = {"true": 0, "unknown": 1, "false": 2, "not_checked": 3}
    (status, kind, note), left, right = min(checks, key=lambda r: (rank[r[0][0]], r[0][1] == "候选"))
    evidence: list[dict[str, Any]] = []

    def cite(aid: str, seq: int | None, basis: str, ref: atoms.FileRef | None = None) -> None:
        if seq is None or any(e["seq"] == seq and e["basis"] == basis for e in evidence):
            return
        act = next((x for x in ledger.agents[aid].actions if x.seq == seq), None)
        evidence.append({"aid": aid, "seq": seq, "basis": basis, "event_id": atoms.event_id(ledger, aid, seq),
                         "location": ledger.locs.get(seq), "source": act.src[0] if act and act.src else None,
                         "use_ts": act.ts if act else None, "done_ts": act.done_ts if act else None,
                         "observation": atoms.file_ref_payload(ref) if ref is not None else None,
                         "use_line": act.src[1] + 1 if act and act.src and act.src[1] is not None else None,
                         "result_line": act.src[2] + 1 if act and act.src and act.src[2] is not None else None})

    relation = None
    if status in ("true", "unknown"):
        if kind == "写":
            ver = ledger.stories[right["key"]].versions[right["v"] - 1]
            cite(left["key"], ver.act_seq, "write")
            relation = ("写 " if a["kind"] == "agent" else "写者 ") + f"v{right['v']}"
        elif kind == "读":
            for act in ledger.agents[right["key"]].actions:
                if (act.ver if act.ver is not None else act.at) > right["v"]:
                    continue
                for ref in act.files:
                    if ref.op == "read" and ref.path == left["key"] and ref.v == left["v"]:
                        basis = read_basis(ref)
                        if (status == "true") == (basis == "read"):
                            cite(right["key"], act.seq, basis, ref)
                if status == "unknown" and left["key"] in (act.detail.get("conditional_reads") or []):
                    cite(right["key"], act.seq, "conditional_read")
            relation = ("读 " if a["kind"] == "agent" else "读者 ") + f"v{left['v']}"
        elif kind == "派发":
            dispatch = next((act for act in ledger.agents[left["key"]].actions if act.ver == left["v"]), None)
            cite(left["key"], dispatch.seq if dispatch else None, "dispatch")
            relation = ("派发 " if left["key"] == a["key"] else "派发自 ") + f"v{left['v']}"
        elif kind == "候选":
            ag, fl = (aa, bb) if aa["kind"] == "agent" else (bb, aa)
            for act, basis in verdict._read_path_candidates(ledger, ag, fl["key"]):
                cite(ag["key"], act.seq, basis)
            for mention in ledger.mentions.get(fl["key"], []):
                if mention.by == ag["key"] and mention.by_ver == ag["v"]:
                    cite(ag["key"], mention.seq, "lexical_mention")
    bases = list(dict.fromkeys(e["basis"] for e in evidence))
    labels = {"uncertain_version": "读取版本待核", "dependency_read": "依赖读取(内容未进上下文)",
              "unverified_read": "读取执行/内容交付依据待核",
              "conditional_read": "条件读取待核", "lexical_mention": "仅词法提及", "overlapping_read": "读取窗口重叠(快照时刻待核)"}
    label = ("账本·" + str(relation) if status == "true" else
             "候选·" + " / ".join(labels.get(x, x) for x in bases) if status == "unknown" and bases else
             "候选·关系待核" if status == "unknown" else
             "查询导航·未核出直接账本边" if status == "false" else "查询导航·账本关系未核验")
    return {"relation": relation if status == "true" else None, "relation_status": status,
            "relation_kind": kind, "relation_label": label, "relation_note": note,
            "relation_evidence": evidence, "relation_source": "ledger",
            "causal_from": left.get("id") if kind in ("写", "读", "派发") and status in ("true", "unknown") else None,
            "causal_to": right.get("id") if kind in ("写", "读", "派发") and status in ("true", "unknown") else None,
            "match": {"true": "账本有边", "unknown": "账本关系待核", "false": "账本无此边",
                      "not_checked": "账本关系未核验"}[status]}


def _relation_any(ledger: atoms.Ledger, a: dict[str, Any], b: dict[str, Any]) -> str | None:
    """旧内部调用的显示兼容层;unknown 不会冒充确定边。"""
    return _relation_check(ledger, a, b)["relation"]


def _evidence_graph(ledger: atoms.Ledger, trajectory: dict[str, Any] | None,
                    trace_identity: dict[str, Any] | None,
                    structured: dict[str, Any] | None = None) -> dict[str, Any]:
    """Project recorded transitions and authenticated, explicitly selected facts.

    Navigation remains untouched in trajectory. Its edges require authenticated
    visits, exact endpoints and a located underlying read/write observation.
    Model declarations independently select dataflow facts and require a
    confirmed directional fact; they never create a visit or a query step.
    """
    tree = trajectory or {}
    bound = (trace_identity or {}).get("bound")
    nodes = {}
    for n in tree.get("nodes") or []:
        exact, _ = via.target(ledger, n.get("kind"), n.get("key"), n.get("v"))
        if exact is not None and n.get("id") == _traj_id(*exact):
            nodes[n["id"]] = n
    transitions = tree.get("transitions") or []
    visits = tree.get("visits") or []
    opened = {v.get("node") for v in visits if v.get("status") == "opened" and v.get("verified") is True}
    opened_steps = {(v.get("step"), v.get("node")) for v in visits
                    if v.get("status") == "opened" and v.get("verified") is True}
    graph: dict[str, Any] = {
        "schema": "migloop-evidence-graph/1", "scope": "recorded_transitions", "complete": False,
        "status": "identity_unbound" if bound is not True else
                  "projected" if tree.get("mode") == "via" else "legacy_unrecorded",
        "identity_bound": bound, "nodes": list(nodes), "additional_nodes": [], "edges": [], "model_relations": [],
        "semantic_checked": False,
        "note": "仅投影本次已记录转移及已认证文稿显式选择、账本原始动作支持的读写关系，不是全账本图或完整根因图；"
                "模型选边不等于模型主张已验证，不增加查询或已读记录；"
                "候选仍待核，纯搜索/词法提及/派发/版本导航/回访只保留在查询时间线。"
                + (" 未记录可投影的查询转移，不从布局父子线补造关系。" if tree.get("mode") != "via" else "")
                + (" 调查身份未绑定当前账本，不绘制当前读写关系。" if bound is not True else ""),
        "counts": {"transitions": len(transitions), "visits": len(visits), "searches": len(tree.get("searches") or []),
                   "projected_transitions": 0, "excluded_transitions": 0, "edges": 0,
                   "confirmed_read": 0, "confirmed_write": 0, "candidate_read": 0, "candidate_write": 0,
                   "model_relations": 0, "model_edges": 0, "projected_model_edges": 0, "excluded_model_edges": 0,
                   "non_explicit_rows_ignored": 0},
        "relation_counts": {}, "source_counts": {}, "excluded": [], "excluded_model_edges": [], "excluded_nonclaims": [],
    }
    action_cache: dict[str, dict[int, Any]] = {}
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    read_bases = {"read", "uncertain_version", "dependency_read", "conditional_read", "overlapping_read", "unverified_read"}

    def located(e: dict[str, Any], aid: str, kind: str, status: str) -> bool:
        bases = {"write"} if kind == "write" else {"read"} if status == "true" else read_bases - {"read"}
        if not isinstance(e, dict) or e.get("aid") != aid or e.get("basis") not in bases:
            return False
        if aid not in action_cache:
            action_cache[aid] = {act.seq: act for act in ledger.agents[aid].actions}
        act = action_cache[aid].get(e.get("seq"))
        if act is None or not act.src or not act.src[0] or act.src[1] is None:
            return False
        return (e.get("source") == act.src[0] and e.get("use_line") == act.src[1] + 1
                and e.get("result_line") == (act.src[2] + 1 if act.src[2] is not None else None)
                and e.get("event_id") == atoms.event_id(ledger, aid, act.seq))

    def merge(left: str, right: str, kind: str, status: str, relation: str,
              evidence: list[dict[str, Any]], origin: dict[str, Any], notes: list[Any]) -> None:
        key = (left, right, kind, status)
        if key not in merged:
            merged[key] = {"id": "rw-" + str(len(merged) + 1), "from": left, "to": right,
                           "kind": kind, "status": status, "source_of_claim": origin["source_of_claim"],
                           "relation_source": "ledger", "origins": [],
                           "label": ("账本·" if status == "true" else "候选·") + relation,
                           "notes": [], "evidence": [], "steps": [], "query_steps": [], "semantic_checked": False}
        edge = merged[key]
        if origin not in edge["origins"]:
            edge["origins"].append(deepcopy(origin))
        sources = {o["source_of_claim"] for o in edge["origins"]}
        edge["source_of_claim"] = next(iter(sources)) if len(sources) == 1 else "mixed"
        if origin["selection_source"] == "recorded_transition" and origin["step"] not in edge["steps"]:
            edge["steps"].append(origin["step"])
            edge["query_steps"].append(origin["step"])
        for note in notes:
            if note and note not in edge["notes"]:
                edge["notes"].append(note)
        for e in evidence:
            if e not in edge["evidence"]:
                edge["evidence"].append(deepcopy(e))

    for tr in transitions:
        relation = str(tr.get("relation_kind") or "unrecorded")
        source = str(tr.get("source") or "unrecorded")
        graph["relation_counts"][relation] = graph["relation_counts"].get(relation, 0) + 1
        graph["source_counts"][source] = graph["source_counts"].get(source, 0) + 1
        kind = {"读": "read", "写": "write"}.get(relation)
        status = tr.get("relation_status")
        a, b = tr.get("from"), tr.get("to")
        left, right = tr.get("causal_from"), tr.get("causal_to")
        reason = None
        if bound is not True:
            reason = "identity_unbound"
        elif tree.get("mode") != "via":
            reason = "legacy_unrecorded"
        elif source == "search":
            reason = "search"
        elif source != "declared":
            reason = "unverified_source"
        elif a == b:
            reason = "same_node"
        elif kind is None or status not in ("true", "unknown"):
            reason = "non_read_write"
        elif tr.get("relation_source") != "ledger":
            reason = "non_ledger_source"
        elif any(nid not in nodes for nid in (a, b, left, right)):
            reason = "invalid_endpoint"
        elif {a, b} != {left, right} or (nodes[left]["kind"], nodes[right]["kind"]) != (
                ("file", "agent") if kind == "read" else ("agent", "file")):
            reason = "invalid_direction"
        elif a not in opened or (tr.get("step"), b) not in opened_steps:
            reason = "unverified_visit"
        evidence = []
        if reason is None:
            aid = nodes[right if kind == "read" else left]["key"]
            evidence = [e for e in tr.get("relation_evidence") or [] if located(e, aid, kind, status)]
            if not evidence:
                reason = "unlocated_evidence"
        if reason is not None:
            graph["excluded"].append({"step": tr.get("step"), "from": a, "to": b, "reason": reason})
            continue
        merge(left, right, kind, status, relation, evidence,
              {"selection_source": "recorded_transition", "source_of_claim": "ledger", "step": tr.get("step")},
              [tr.get("relation_label"), tr.get("relation_note")])
        graph["counts"]["projected_transitions"] += 1

    doc = structured or {}
    identity = doc.get("identity") or {}
    document_bound = (bound is True and identity.get("bound") is True
                      and identity.get("current") == atoms.ledger_identity(ledger)
                      and (doc.get("document_source") or {}).get("verified") is True
                      and bool(doc.get("document_sha256")) and not doc.get("errors"))
    for defect in doc.get("defects") or []:
        for index, claim in enumerate(defect.get("edges") or []):
            # Adjacencies generated by the legacy projector were never model
            # declarations. Do not count them as rejected model edge claims.
            if claim.get("implicit") is not False:
                graph["counts"]["non_explicit_rows_ignored"] += 1
                graph["excluded_nonclaims"].append({"defect": defect.get("id"), "edge_index": index,
                                                   "reason": "not_explicit"})
                continue
            graph["counts"]["model_edges"] += 1
            reason = None
            endpoints = []
            if not document_bound:
                reason = "document_or_identity_unbound"
            elif claim.get("claimed") not in ("读", "写"):
                reason = "non_read_write"
            if reason is None:
                for side in ("from", "to"):
                    saved = claim.get(side) or {}
                    resolved = verdict.resolve_node(ledger, saved.get("spec"))
                    if not resolved["ok"] or any(resolved.get(k) != saved.get(k) for k in ("kind", "key", "v")):
                        reason = "invalid_endpoint"
                        break
                    endpoints.append(resolved)
            evidence = []
            if reason is None:
                left, right = endpoints
                status, relation, note = verdict.check_edge(ledger, left, right, claim["claimed"])
                if status != "true" or relation != claim["claimed"]:
                    reason = "unconfirmed_directional_relation"
            if reason is None:
                from .evidence import read_basis
                kind = {"读": "read", "写": "write"}[relation]
                aid = right["key"] if kind == "read" else left["key"]
                supports = []
                if kind == "write":
                    version = ledger.stories[right["key"]].versions[right["v"] - 1]
                    supports = [(a, None) for a in ledger.agents[aid].actions if a.seq == version.act_seq]
                else:
                    supports = [(a, ref) for a in ledger.agents[aid].actions
                                if (a.ver if a.ver is not None else a.at) <= right["v"]
                                for ref in a.files if ref.op == "read" and ref.path == left["key"]
                                and ref.v == left["v"] and read_basis(ref) == "read"]
                for act, ref in supports:
                    e = {"aid": aid, "seq": act.seq, "basis": kind,
                         "event_id": atoms.event_id(ledger, aid, act.seq), "location": ledger.locs.get(act.seq),
                         "source": act.src[0] if act.src else None, "use_ts": act.ts, "done_ts": act.done_ts,
                         "observation": atoms.file_ref_payload(ref) if ref is not None else None,
                         "use_line": act.src[1] + 1 if act.src and act.src[1] is not None else None,
                         "result_line": act.src[2] + 1 if act.src and act.src[2] is not None else None}
                    if located(e, aid, kind, status):
                        evidence.append(e)
                if not evidence:
                    reason = "unlocated_evidence"
            if reason is not None:
                graph["excluded_model_edges"].append({"defect": defect.get("id"), "edge_index": index, "reason": reason})
                continue
            ids = []
            for endpoint in endpoints:
                nid = _traj_id(endpoint["kind"], endpoint["key"], endpoint["v"])
                ids.append(nid)
                if nid not in nodes:
                    n = {"id": nid, "kind": endpoint["kind"], "key": endpoint["key"], "v": endpoint["v"],
                         "label": _traj_label(ledger, endpoint["kind"], endpoint["key"], endpoint["v"]),
                         "source": "checked_model_edge", "opened": [], "appears": [], "parent": None,
                         "side": "unlinked", "unseen": 0, "fixed": False}
                    nodes[nid] = n
                    graph["additional_nodes"].append(n)
            merge(*ids, kind, status, relation, evidence,
                  {"selection_source": "checked_model_edge", "source_of_claim": "model", "defect": defect.get("id"),
                   "edge_index": index, "document_sha256": doc["document_sha256"], "model_note": claim.get("model_note")},
                  [note])
            graph["counts"]["projected_model_edges"] += 1
    if graph["counts"]["projected_model_edges"]:
        graph["scope"] = "recorded_transitions_and_checked_model_edges"
        graph["status"] = "projected"
    graph["nodes"] = list(nodes)
    graph["edges"] = list(merged.values())
    graph["counts"].update(edges=len(merged), excluded_transitions=len(graph["excluded"]),
                           excluded_model_edges=len(graph["excluded_model_edges"]))
    for edge in graph["edges"]:
        graph["counts"][("confirmed_" if edge["status"] == "true" else "candidate_") + edge["kind"]] += 1
    return graph


def _rejected(text: str) -> bool:
    """服务端拒了这次 file / agent(via 不合规):新版以 ⛔ 开头;更早一跑的错误文本没有前缀,按开头词认。"""
    t = text.lstrip()
    return t.startswith(via.REJECT) or (t.startswith("via") and "已打开:" in t[:400])


def _trajectory_walk(ledger: atoms.Ledger, steps: list[dict[str, Any]], texts: list[str],
                     structured: dict[str, Any] | None, verdicts: dict[str, list[dict[str, Any]]],
                     trace_identity: dict[str, Any] | None = None) -> dict[str, Any]:
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
    visits: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    searches: list[dict[str, Any]] = []
    search_by_id: dict[str, dict[str, Any] | None] = {}
    received: dict[str, int] = {}
    received_ms: dict[str, float] = {}
    for s in steps:
        if s.get("tool") == "search":
            i = int(s["i"])
            text = texts[i - 1] if i - 1 < len(texts) else ""
            receipt = via.search_receipt(text, s.get("args") or {})
            verified = bool(receipt and s.get("ok") and s.get("result_present") and not s.get("identity_unbound")
                            and (s.get("provenance") or {}).get("complete_pair") is not False
                            and receipt["ledger"] == atoms.ledger_identity(ledger))
            event = {"step": i, "id": receipt["id"] if receipt else None, "args": s.get("args") or {},
                     "status": "verified" if verified else "unverified", "hits": receipt["hits"] if verified else [],
                     "call_id": s.get("call_id"), "item_id": s.get("item_id"), "result_ref": s.get("result_ref"),
                     "use_line": s.get("use_line"), "result_line": s.get("result_line"), "provenance": s.get("provenance"),
                     "result_event": s.get("result_event"), "result_time_ms": s.get("result_time_ms"),
                     "receipt": receipt if verified else None,
                     "note": "凭据只证明原生 search 工具返回了命中;不证明外层执行包装完整转交给模型,也不证明历史读取或因果。"
                             if verified else "搜索返回无有效凭据/身份或调用未核验;保留原始查询,不能充当导航来处。"}
            searches.append(event)
            if verified:
                token = receipt["id"]
                # 同一 token 若出现在不同原始调用,不能猜用的是哪一次返回。
                search_by_id[token] = event if token not in search_by_id else None
            continue
        if s.get("tool") not in ("file", "agent"):
            continue
        land = _step_landing(s)
        i = int(s["i"])
        pv = via.parse(ledger, str(s.get("via") or ""))
        raw_return = texts[i - 1] if i - 1 < len(texts) else ""
        # Interpret the documented legacy single-result wrapper only for atom
        # coordinate parsing. The recorded/compared text remains untouched.
        text = _unwrap_result(raw_return)
        requested = _traj_id(*land) if land is not None else None
        actual = via.returned_node(ledger, str(s["tool"]), text)
        visit: dict[str, Any] = {"step": i, "tool": s["tool"], "node": requested, "requested_node": requested,
                                "actual_node": _traj_id(*actual) if actual else None, "status": "opened",
                                "verified": False, "via": pv["text"], "from": None, "scope": s.get("scope") or "",
                                "delivery_truncated": bool(s.get("delivery_truncated")),
                                "coordinate_envelope": "legacy_single_result" if text != raw_return else None,
                                "args": s.get("args") or {}, "result_ref": s.get("result_ref"),
                                "call_id": s.get("call_id"), "item_id": s.get("item_id"),
                                "provenance": s.get("provenance"),
                                "use_time_ms": s.get("use_time_ms"), "result_time_ms": s.get("result_time_ms"),
                                "use_line": s.get("use_line"), "result_line": s.get("result_line"), "note": None}
        visits.append(visit)
        if s.get("identity_unbound"):
            visit.update(status="unverified", actual_node=None, note="历史调用的账本身份与当前不一致,不绑定当前版本或关系")
        elif s.get("result_present") is not True:
            visit.update(status="pending", note="没有可配对的工具返回,未打开")
        elif _rejected(text):
            visit.update(status="rejected", actual_node=None, note=text.strip().splitlines()[0])
        elif s.get("ok") is False:
            visit.update(status="error", actual_node=None, note=text.strip()[:300] or "工具返回错误,未打开")
        elif (s.get("provenance") or {}).get("origin_unverified"):
            origin = s["provenance"].get("tool_origin") or {}
            visit.update(status="unverified", actual_node=None,
                         note="工具来源未认证或同 ID 表示冲突,不绑定当前节点: " + "; ".join(origin.get("errors") or ["缺少明确 MigLoop 来源"]))
        elif (s.get("provenance") or {}).get("complete_pair") is False:
            visit.update(status="unverified", note="调用事件缺少可配对的开始记录或有效开始/完成时间,未验证")
        elif actual is None:
            visit.update(status="unverified", note="返回没有可核验的版本坐标,未验证")
        elif land != actual:
            visit.update(status="unverified", note="请求与实际返回的版本坐标不一致,未登记打开")
        if visit["status"] != "opened":
            declared.append({"step": i, "text": pv["text"], "from": None, "to": None,
                             "match": {"rejected": "被拒(未打开)", "error": "调用失败(未打开)",
                                       "pending": "待返回(未打开)", "unverified": "返回未验证"}[visit["status"]]})
            continue
        assert actual is not None
        kind, key, v = actual
        # 来处必须在这次调用之前已返回。调用顺序本身不证明模型看到了前一个并行调用的结果。
        src_id = _traj_id(str(pv["kind"]), str(pv["key"]), pv["v"]) if pv["ok"] else None
        src = nodes.get(src_id) if src_id else None
        timing_note = None
        if src:
            if s.get("use_time_ms") is not None and src_id in received_ms:
                if received_ms[src_id] >= s["use_time_ms"]:
                    if received_ms[src_id] == s["use_time_ms"]:
                        timing_note = "来处返回与本次调用开始的毫秒时间相同,时序分辨率不足,先后未确认"
                    src = None
            elif src_id not in received or received[src_id] >= (s.get("use_event") or 0):
                src = None
        search_source = search_by_id.get(pv["search"]) if pv["search"] else None
        if pv["search"]:
            timing_note = "搜索来处未核验:必须引用此前成功返回的真实命中,且目标坐标完全一致"
            if search_source:
                completed = search_source.get("result_time_ms")
                begun = s.get("use_time_ms")
                before = (completed < begun if completed is not None and begun is not None else
                          search_source.get("result_event") is not None and s.get("use_event") is not None
                          and search_source["result_event"] < s["use_event"])
                if not before or via.search_target(search_source["receipt"], pv["hit"]) != actual:
                    search_source = None
        n = add(kind, key, v, "查过")
        first_visit = not n["opened"]
        n["opened"].append(i)
        visit.update(node=n["id"], verified=True)
        row: dict[str, Any] = {"step": i, "text": pv["text"], "from": None, "to": n["id"], "match": None}
        if search_source is not None:
            source = {"id": search_source["id"], "step": search_source["step"], "hit": pv["hit"],
                      "call_id": search_source["call_id"], "item_id": search_source["item_id"],
                      "result_line": search_source["result_line"], "provenance": search_source["provenance"],
                      "target": search_source["hits"][pv["hit"] - 1], "note": search_source["note"]}
            visit["search_source"] = source
            row.update(match="搜索命中导航", search_source=source)
            transitions.append({"step": i, "from": None, "to": n["id"], "source": "search", "search_source": source,
                                "relation": None, "relation_status": "not_checked", "relation_kind": None,
                                "relation_label": f"搜索 #{source['step']} 命中 {source['hit']} · 查询导航",
                                "relation_note": search_source["note"], "relation_evidence": [], "relation_source": None,
                                "causal_from": None, "causal_to": None, "match": "搜索命中导航"})
            if first_visit:
                n.update(parent=root["id"] if root else None, side="unlinked" if root else "root", search_source=source)
        elif src is not None:
            checked = _relation_check(ledger, src, n)
            relation = checked["relation"]
            row.update({"from": src["id"], "match": checked["match"]})
            visit["from"] = src["id"]
            transitions.append({"step": i, "from": src["id"], "to": n["id"], "source": "declared", **checked})
            if first_visit:
                n.update(parent=src["id"], side="up", edge=relation, relation_check=checked)
        elif root is None:
            row["match"] = "入口" if pv["first"] else "入口(来处未验证)"
            if not pv["first"]:
                visit["note"] = timing_note or "第一跳来处未验证"
        else:
            visit["note"] = timing_note or ("sessions 只能当第一跳" if pv["first"] else
                             ("via 解析不了" if not pv["ok"] else "via 指向调用前尚未成功返回的节点"))
            row["match"] = visit["note"]
            if first_visit:
                n.update(parent=root["id"], side="unlinked", note=visit["note"])
        if root is None:
            root = n
            n["side"] = "root"
        if first_visit:
            n["via"] = pv["text"] or None
        if s.get("result_event") is not None:
            received[n["id"]] = min(received.get(n["id"], int(s["result_event"])), int(s["result_event"]))
        if s.get("result_time_ms") is not None:
            received_ms[n["id"]] = min(received_ms.get(n["id"], s["result_time_ms"]), s["result_time_ms"])
        declared.append(row)

    for visit in visits:
        if visit["delivery_truncated"]:
            delivered = (visit.get("provenance") or {}).get("output_normalization") or {}
            note = (f"返回截断／非全文:可见 {delivered.get('visible_chars')} 字,省略 {delivered.get('omitted_chars')} 字;"
                    "只核对已交付片段与版本头,不证明收到完整正文")
            visit["note"] = (visit["note"] + " · " if visit.get("note") else "") + note

    def side_add(kind: str, key: str, v: int | None, source: str, note: str) -> dict[str, Any]:
        nid = _traj_id(kind, key, v)
        if nid in nodes:
            return nodes[nid]
        m = add(kind, key, v, source)
        m["parent"], m["side"], m["note"] = root["id"] if root else None, "unlinked", note
        return m

    bound = not structured or (structured.get("identity") or {}).get("bound") is not False
    if structured and bound and not structured.get("errors"):
        claim_root = structured.get("root") or {}
        if root is None and claim_root.get("ok") and claim_root.get("kind") == "agent":
            root = add("agent", str(claim_root["key"]), claim_root["v"], "结论")
            root.update(side="root", note="结论指定的真实 agent 根,尚未查询")
        for key, rows in (structured.get("roles") or {}).items():
            for r in rows:
                side_add(str(r["kind"]), key, r["v"], "结论", "结论点名,没打开")
        for f in structured.get("fixed") or []:
            m = side_add(str(f["kind"]), str(f["key"]), f["v"], "修复落点", "修复落点,没打开")
            if m is not None:
                m["fixed"] = True
    elif verdicts and not structured:
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
            if land == (n["kind"], n["key"], n["v"]):
                continue
            if s.get("ok") and s.get("result_present") and i - 1 < len(texts) \
                    and not _rejected(texts[i - 1]) and _sight(texts[i - 1], n["kind"], n["key"], n["v"], ledger)[1]:
                n["appears"].append(i)
        d = 0
        cur = n
        while cur["parent"] is not None and cur["side"] == "up":
            cur = nodes[cur["parent"]]
            d += 1
        n["depth"] = d
    present = {(n["kind"], n["key"], n["v"]) for n in order}
    for n in order:
        neighbors = [x for x in _upstream_neighbors(ledger, n["kind"], n["key"], n["v"])
                     if x not in present and x[2] is not None]
        n["unseen_neighbors"] = [{"kind": k, "key": key, "v": v} for k, key, v in sorted(neighbors)]
        n["unseen"] = len(n["unseen_neighbors"])
    edges = [{"from": n["parent"], "to": n["id"], "relation": n["edge"] or "无", "skipped": 0}
             for n in order if n["parent"] and n["side"] == "up"]
    trace_bound = (trace_identity or {}).get("bound")
    verification_note = ("访问按各自返回坐标与状态核验;转移记录声明的 via,账本关系另行标注。" if trace_bound is True else
                         "历史调用的账本身份未绑定;保留返回记录,当前账本坐标与关系未验证。" if trace_bound is False else
                         "查询轨迹身份未记录;按返回坐标保留访问状态,未认证当前账本身份。")
    return {"mode": "via", "root": root["id"] if root else None, "nodes": order, "edges": edges,
            "declared": declared, "visits": visits, "transitions": transitions, "searches": searches,
            "verification": "returned_coordinates" if trace_bound is True else "unverified",
            "verification_note": verification_note,
            "side_title": "搜索入口 / 路线外节点（查询状态见节点）" if any(n.get("search_source") for n in order) else "未接入路线"}


def _trajectory(ledger: atoms.Ledger, run_dir: str, steps: list[dict[str, Any]], root: str | None,
                structured: dict[str, Any] | None, verdicts: dict[str, list[dict[str, Any]]],
                calls: list[dict[str, Any]] | None = None,
                trace_identity: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """有 via 的 run:按 via 走的树;没有的老 run:账本边树;没有转录:None。"""
    if calls is None:
        calls = _transcript_calls(run_dir)
    if calls is None:
        return None
    texts = [c["text"] for c in calls]
    if any((c.get("provenance") or {}).get("degraded") for c in calls):
        tree = _trajectory_walk(ledger, steps, texts, structured, verdicts, trace_identity)
        tree.update(trace_source="codex_exec_events", source_path="events.jsonl")
        tree["verification_note"] += " 原始 rollout 缺失;完整 stdout 开始/完成事件按 item_id 配对,不冒充 call_id。"
        return tree
    if any((s.get("provenance") or {}).get("origin_unverified") for s in steps):
        return _trajectory_walk(ledger, steps, texts, structured, verdicts, trace_identity)
    if any(s.get("via") or (int(s["i"]) <= len(texts) and _rejected(texts[int(s["i"]) - 1]))
           for s in steps if s.get("tool") in ("file", "agent")):
        return _trajectory_walk(ledger, steps, texts, structured, verdicts, trace_identity)
    if any(s.get("identity_unbound") for s in steps):
        # Legacy reports have no structured.identity to consult. Do not first bind
        # old handles to today's ledger and merely add an unverified label.
        return _trajectory_walk(ledger, steps, texts, structured, {}, trace_identity)
    bound = not structured or (structured.get("identity") or {}).get("bound") is not False
    tree = _trajectory_ledger(ledger, run_dir, steps, root if bound else None, structured if bound else None,
                              verdicts if not structured else {})
    walk = _trajectory_walk(ledger, steps, texts, None, {}, trace_identity)
    if tree is None and walk["visits"]:
        tree = walk
    if tree is not None:
        tree["visits"] = walk["visits"]
        tree["transitions"] = []
        tree.update(verification="unverified", verification_note="旧跑未记录 via;账本关系不是调查路线,访问范围未验证。")
    return tree
