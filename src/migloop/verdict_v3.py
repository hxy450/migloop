"""Post-investigation arguments over file/agent time scopes, never a truth judge.

Model declarations, source/coordinate bindings and operation evidence are separate.
No query visit, version, author, missing link or causal conclusion is synthesized.
"""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from typing import Any

from . import atoms, temporal, transcript_store
from .evidence import CONFIRMED_BASES, proof_payload
from .time_scope import _iso, _time

SCHEMA = "migloop-verdict/3"
GRAPH_SCHEMA = "migloop-argument-graph/1"
STATUSES = {"explained", "unknown", "not_generation_error"}
ROLES = {"origin", "propagated", "context", "repaired"}
RELATIONS = {"read", "write", "possible_read", "possible_write"}
MAX_CHANGE_ROWS = 10000
_TOP = {"schema", "ledger", "target", "findings", "coverage"}
_FINDING = {"id", "title", "reason", "status", "nodes", "edges", "changes",
            "hypothesis", "recommendation", "validation", "unknown"}
_NODE = {"id", "kind", "key", "at", "role", "reason", "evidence", "counterevidence"}
_EDGE = {"from", "to", "relation", "evidence", "claim"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _choice(value: Any, choices: Any) -> bool:
    return isinstance(value, str) and value in choices


def validate(data: Any) -> list[str]:
    """Validate only author-owned fields. Missing links are diagnostic, not invented."""
    from . import verdict
    if not isinstance(data, dict):
        return ["顶层必须是映射"]
    errors: list[str] = []

    def keys(row, allowed, where):
        verdict._check_keys(row, allowed, where, errors)

    def text(row, key, where):
        if not _text(row.get(key)):
            errors.append(f"{where}.{key}: 必须是非空字符串")

    def refs(value, where):
        if not isinstance(value, list) or not all(_text(x) for x in value):
            errors.append(f"{where}: 必须是引用字符串列表")

    def stamp(value, where):
        if _time(value) is None:
            errors.append(f"{where}: 必须是带时区的明确 ISO 时刻，不接受 latest 或版本")

    keys(data, _TOP, "顶层")
    if data.get("schema") != SCHEMA:
        errors.append("schema 必须是 " + SCHEMA)
    text(data, "ledger", "顶层")
    target = data.get("target")
    if not isinstance(target, dict):
        errors.append("target 必须是映射")
    else:
        keys(target, {"file", "since_ts", "at"}, "target")
        text(target, "file", "target")
        stamp(target.get("at"), "target.at")
        if target.get("since_ts") is not None:
            stamp(target["since_ts"], "target.since_ts")
            if _time(target["since_ts"]) and _time(target.get("at")) and _time(target["since_ts"]) > _time(target["at"]):
                errors.append("target.since_ts 不能晚于 at")
    findings = data.get("findings")
    if not isinstance(findings, list):
        return errors + ["findings 必须是列表"]
    ids: set[str] = set()
    for i, finding in enumerate(findings):
        where = f"findings[{i}]"
        if not isinstance(finding, dict):
            errors.append(where + ": 必须是映射")
            continue
        keys(finding, _FINDING, where)
        for key in ("id", "title", "reason"):
            text(finding, key, where)
        ident = finding.get("id")
        if _text(ident):
            if ident in ids:
                errors.append(where + ".id: 重复")
            ids.add(ident)
        if not _choice(finding.get("status"), STATUSES):
            errors.append(where + ".status: 必须是 explained/unknown/not_generation_error")
        for field in ("hypothesis", "recommendation", "validation"):
            if field in finding:
                text(finding, field, where)
        for field in ("changes", "unknown"):
            if field in finding:
                refs(finding[field], where + "." + field)
        nodes = finding.get("nodes", [])
        if not isinstance(nodes, list):
            errors.append(where + ".nodes: 必须是列表")
            nodes = []
        node_ids: set[str] = set()
        for j, node in enumerate(nodes):
            at = f"{where}.nodes[{j}]"
            if not isinstance(node, dict):
                errors.append(at + ": 必须是映射")
                continue
            keys(node, _NODE, at)
            for field in ("id", "key", "reason"):
                text(node, field, at)
            if _text(node.get("id")):
                if node["id"] in node_ids:
                    errors.append(at + ".id: 重复")
                node_ids.add(node["id"])
            if not _choice(node.get("kind"), ("file", "agent")):
                errors.append(at + ".kind: 只允许 file/agent，不创造事件或未知作者节点")
            if not _choice(node.get("role"), ROLES):
                errors.append(at + ".role: 必须是 origin/propagated/context/repaired")
            stamp(node.get("at"), at + ".at")
            for field in ("evidence", "counterevidence"):
                refs(node.get(field, []), at + "." + field)
        edges = finding.get("edges", [])
        if not isinstance(edges, list):
            errors.append(where + ".edges: 必须是列表")
            edges = []
        for j, edge in enumerate(edges):
            at = f"{where}.edges[{j}]"
            if not isinstance(edge, dict):
                errors.append(at + ": 必须是映射")
                continue
            keys(edge, _EDGE, at)
            for field in ("from", "to", "claim"):
                text(edge, field, at)
            if not _choice(edge.get("relation"), RELATIONS):
                errors.append(at + ".relation: 必须是 read/write/possible_read/possible_write")
            refs(edge.get("evidence", []), at + ".evidence")
    coverage = data.get("coverage", [])
    if not isinstance(coverage, list):
        errors.append("coverage 必须是列表")
    else:
        seen = set()
        for i, row in enumerate(coverage):
            where = f"coverage[{i}]"
            if not isinstance(row, dict):
                errors.append(where + ": 必须是映射")
                continue
            keys(row, {"event", "status", "finding", "reason"}, where)
            text(row, "event", where)
            text(row, "reason", where)
            if _text(row.get("event")):
                if row["event"] in seen:
                    errors.append(where + ".event: 重复")
                seen.add(row["event"])
            if not _choice(row.get("status"), ("explained", "unresolved", "not_repair")):
                errors.append(where + ".status: 必须是 explained/unresolved/not_repair")
            if row.get("finding") is not None and not _choice(row.get("finding"), ids):
                errors.append(where + ".finding: 必须指向本稿 finding id")
    return errors


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _scope(kind: str, key: str | None, at: str, since_ts: str | None = None) -> dict[str, Any]:
    return {"kind": kind, "key": key, "at": _iso(_time(at)), "since_ts": _iso(_time(since_ts))}


def _qualified(finding: str, local: str) -> str:
    # JSON-pointer escaping makes arbitrary model IDs injective without imposing
    # an ASCII-only naming convention or merging claims from different findings.
    def escape(value):
        return value.replace("~", "~0").replace("/", "~1")
    return escape(finding) + "/" + escape(local)


def _action_lines(src: Any) -> set[int]:
    """Available physical lines only; an absent result is not a bad citation."""
    if not isinstance(src, (tuple, list)):
        return set()
    return {line + 1 for line in src[1:3] if type(line) is int and line >= 0}


def resolve_evidence(ledger: atoms.Ledger, ref: str, *, scope: dict[str, Any], bound: bool = True) -> dict[str, Any]:
    """Resolve raw/legacy source locations; a real citation is not semantic support."""
    from . import verdict
    out = {"ref": ref, "original_ref": ref, "status": "unbound", "source": None, "line": None,
           "ts": None, "type": "raw" if ref.startswith("raw:") else "legacy", "scope": deepcopy(scope),
           "textual_only": None, "semantic_checked": False, "diag": "账本身份未绑定"}
    if not bound:
        return out
    try:
        if ref.startswith("raw:"):
            record = transcript_store.resolve(ledger, ref)
        else:
            match = atoms.REF_RE.fullmatch(ref.strip())
            if not match or not (match.group(1) or match.group(5)):
                raise ValueError("需要完整 raw: 引用或 #转录标识:n@L行[/块]，不接受版本或散文")
            old = verdict.resolve_evidence(ledger, ref)
            if old.get("status") not in ("ok", "drifted"):
                raise ValueError("旧引用不可唯一定位: " + str(old.get("status")))
            action = next((a for agent in ledger.agents.values() for a in agent.actions
                           if a.seq == old.get("seq")), None)
            if action is None or not action.src:
                raise ValueError("旧动作没有原始记录指针")
            out.update(action_seq=action.seq, action_agent=old.get("aid"), action_block=action.blk)
            requested_line = int(match.group(3))
            record = transcript_store.read_record(action.src[0], requested_line)
            out["legacy_status"] = old["status"]
        out.update(record.address(), ref=ref, raw_ref=record.ref, source_path=record.path,
                   status="ok", diag="原文位置/内容摘要可核；不认证主张或操作执行")
        related = [a for owner in ledger.agents.values() for a in owner.actions
                   if a.src and _norm(a.src[0]) == _norm(record.path)
                   and record.line in _action_lines(a.src)]
        out["textual_only"] = False if any(a.tuid for a in related) else True if related and all(
            a.kind in ("say", "think", "message", "instruction", "inject", "system", "notify", "inbox", "compact")
            for a in related) else None
        if record.ts is None:
            out.update(status="undated", diag="原文时间未知；不认证它是截止前输入")
        elif not temporal.Window.parse(scope["at"], scope.get("since_ts")).contains(record.ts):
            out.update(status="outside_scope", diag="原文不在声明的时间窗口内；保留引用但不认证输入可用")
    except (ValueError, OSError, UnicodeError, StopIteration, TypeError) as exc:
        out.update(status="invalid", diag=str(exc))
    return out


def _node_binding(ledger: atoms.Ledger, node: dict[str, Any], bound: bool, cutoff: str) -> dict[str, Any]:
    out = {"status": "unbound", "canonical_key": None, "at": _iso(_time(node["at"])),
           "view": "evidence_history", "semantic_checked": False, "diag": "账本身份未绑定"}
    if not bound:
        return out
    try:
        if "@v" in node["key"] or any(x == ".." for x in node["key"].replace("\\", "/").split("/")):
            raise ValueError("key 不接受版本后缀或父路径跳转")
        if _time(node["at"]) > _time(cutoff):
            raise ValueError("节点时间晚于本稿 target.at")
        if node["kind"] == "agent":
            actor = atoms.resolve_agent(ledger, node["key"])
            if actor is None:
                out.update(status="unlocated", diag="agent 不在当前账本或别名不唯一；不补造作者")
                return out
            key = actor.id
        else:
            key = temporal.resolve_file(ledger, node["key"])
            if key not in ledger.stories:
                out.update(status="unlocated", canonical_key=key,
                           diag="仅声明文件范围；没有确定文件身份，不用词法提及补造状态")
                return out
        out.update(status="matched", canonical_key=key, diag="身份与时间范围可核；不是磁盘/上下文快照")
    except (ValueError, TypeError) as exc:
        out.update(status="ambiguous" if "歧义" in str(exc) else "invalid", diag=str(exc))
    return out


def _edge_binding(ledger: atoms.Ledger, edge: dict[str, Any], left: dict[str, Any] | None,
                  right: dict[str, Any] | None, refs: list[dict[str, Any]], bound: bool) -> dict[str, Any]:
    out = {"status": "unbound" if not bound else "not_observed", "evidence": [],
           "state_binding": "not_proven", "semantic_checked": False,
           "diag": "账本身份未绑定" if not bound else "引用未核出声明的读写；不等于证明未发生"}
    if not bound:
        return out
    if not left or not right:
        return {**out, "status": "invalid", "diag": "端点缺失；保留断点，不创建节点或连线"}
    if any(n["binding"]["status"] != "matched" for n in (left, right)):
        return {**out, "status": "invalid", "diag": "端点身份/时间未绑定"}
    operation = edge["relation"].removeprefix("possible_")
    expected = ("file", "agent") if operation == "read" else ("agent", "file")
    if (left["kind"], right["kind"]) != expected:
        return {**out, "status": "conflicting", "diag": "读为 file→agent，写为 agent→file；声明方向不符"}
    file_node, agent_node = (left, right) if operation == "read" else (right, left)
    path, aid = file_node["binding"]["canonical_key"], agent_node["binding"]["canonical_key"]
    cutoff = min(left["binding"]["at"], right["binding"]["at"])
    supports = []
    source_stats = {_norm(key): value for key, value in ledger.source_stats.items()}
    for action in ledger.agents[aid].actions:
        if not action.src:
            continue
        cited = [r for r in refs if r["status"] == "ok" and _norm(r.get("source_path") or "") == _norm(action.src[0])
                 and r["line"] in _action_lines(action.src)
                 and (r["type"] != "legacy" or r.get("action_seq") == action.seq)]
        if not cited:
            continue
        try:
            stat = os.stat(action.src[0])
            recorded = source_stats.get(_norm(action.src[0]))
            if recorded is None or recorded != (stat.st_mtime_ns, stat.st_size):
                return {**out, "status": "unbound", "diag": "源统计缺失或已变化；原文可读不认证陈旧推断关系"}
        except OSError:
            return {**out, "status": "unbound", "diag": "原始源不可读取；不认证推断关系"}
        use, done = _iso(_time(action.ts)), _iso(_time(action.done_ts))
        completed = bool(use and done and use <= done <= cutoff and action.ok is True)
        if not completed:
            # FileRefs can be discovered only in the eventual result. Do not
            # leak their path association into a pre-return time scope.
            continue
        for file_ref in action.files:
            if file_ref.path != path or file_ref.op != operation:
                continue
            proof = proof_payload(file_ref.proof)
            confirmed = (proof["execution"] == "confirmed" and proof["operation_basis"] in CONFIRMED_BASES
                         and not getattr(file_ref.ev, "conditional", False))
            if operation == "read":
                confirmed = confirmed and proof["delivery"] == "content" and not getattr(file_ref, "observation_uncertain", False)
                confirmed = confirmed and not getattr(getattr(file_ref, "ev", None), "dep", False)
            supports.append({"status": "confirmed" if confirmed else "candidate", "agent": aid,
                             "event_id": atoms.event_id(ledger, aid, action.seq), "use_ts": use,
                             "done_ts": done if completed else None, "operation": operation,
                             "proof": proof, "evidence": deepcopy(cited)})
        candidates = (action.detail.get("conditional_reads") or []) if operation == "read" else (
            list(action.detail.get("conditional") or []) + list(action.detail.get("effect_candidates") or []))
        candidate_rows = action.detail.get("read_candidates") or [] if operation == "read" else []
        if path in candidates or any(isinstance(r, dict) and r.get("path") == path for r in candidate_rows):
            supports.append({"status": "candidate", "agent": aid, "operation": operation,
                             "event_id": atoms.event_id(ledger, aid, action.seq), "evidence": deepcopy(cited)})
    if supports:
        status = "confirmed" if any(s["status"] == "confirmed" for s in supports) else "candidate"
        out.update(status=status, evidence=supports,
                   diag="只核两节点截止前曾发生的路径级读写；不证明精确文件状态传递、问题被消费或传播")
    return out


def check(ledger: atoms.Ledger, data: dict[str, Any], draft: str, *, with_graph: bool = False) -> dict[str, Any]:
    """Bounded mechanical feedback; no graph traversal or semantic adjudication."""
    built = build(ledger, data)
    issues = [{"code": row["code"], "severity": "error" if row["code"] in
               ("schema", "identity_unbound", "evidence_unbound") else "warning",
               "where": row.get("node") or row.get("edge") or row.get("finding") or "",
               "detail": str(row.get("detail") or "")[:650]} for row in built["diagnostics"]]
    result = {"schema": "migloop-draft-check/1", "source_schema": SCHEMA,
            "draft_sha256": hashlib.sha256(draft.encode("utf-8")).hexdigest(),
            "document_sha256": built["document_sha256"], "ledger": atoms.ledger_identity(ledger),
            "identity_bound": built["identity"]["bound"], "semantic_checked": False,
            "status": "needs_review" if issues else "mechanical_clear", "issues": issues[:40],
            "omitted_issues": max(0, len(issues) - 40),
            "counts": {"errors": sum(r["severity"] == "error" for r in issues),
                       "warnings": sum(r["severity"] == "warning" for r in issues), "total": len(issues)},
            "coverage": deepcopy(built["coverage"]),
            "scope": "只核身份、坐标、时间、原文及声明关系；不认证原因、实际看过或因果完备",
            "next": "保留无法确认的链和反证；机械核验通过不证明问题传播成立。"}
    if with_graph:
        result["argument_graph"] = built["argument_graph"]
    return result


def _changes(ledger: atoms.Ledger, target: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read every page up to an explicit safety bound, never call one page complete."""
    from . import investigation
    rows, diagnostics, offset = [], [], 0
    while True:
        page = investigation.changes(ledger, target["file"], target["at"], target.get("since_ts"), offset=offset, limit=200)
        rows.extend(page.get("rows") or [])
        diagnostics.extend({"code": "change_source_gap", "detail": gap} for gap in page.get("gaps") or [])
        next_offset = page.get("next_offset")
        if next_offset is None:
            break
        if len(rows) >= MAX_CHANGE_ROWS or not isinstance(next_offset, int) or next_offset <= offset:
            diagnostics.append({"code": "change_inventory_incomplete", "detail": "分页达到安全上限或返回异常；未宣称完整覆盖"})
            break
        offset = next_offset
    return rows, diagnostics


def build(ledger: atoms.Ledger, data: dict[str, Any] | None, errors: list[str] | None = None,
          meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Project submitted claims losslessly; no requirement to have opened endpoints."""
    meta = meta or {}
    errors = list(errors or []) + (validate(data) if data is not None and not errors else [])
    current = atoms.ledger_identity(ledger)
    source = data if isinstance(data, dict) else {}
    claimed = source.get("ledger")
    conflict = claimed != current or (meta.get("harness_identity") not in (None, current))
    conflict = conflict or (meta.get("trace_identity") or {}).get("bound") is False
    bound = bool(claimed == current and not conflict and not errors)
    diagnostics: list[dict[str, Any]] = [{"code": "schema", "detail": e} for e in errors]
    identity = {"current": current, "claimed": claimed, "bound": bound,
                "status": "matched" if bound else "mismatch" if conflict else "invalid"}
    if not bound:
        diagnostics.append({"code": "identity_unbound", "detail": "声明未绑定当前账本；不核当前节点或关系"})
    digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest() if data is not None and not errors else None
    target = deepcopy(source.get("target") or {})
    if not errors:
        target["at"] = _iso(_time(target.get("at")))
        target["since_ts"] = _iso(_time(target.get("since_ts")))
    graph: dict[str, Any] = {"schema": GRAPH_SCHEMA, "target": target, "nodes": [], "edges": [],
        "findings": [], "coverage": [], "diagnostics": diagnostics, "semantic_checked": False,
        "identity": identity, "complete": False, "document_sha256": digest}
    out = {"schema": SCHEMA, "document_sha256": digest, "identity": identity, "target": target,
           "raw": meta.get("raw"), "errors": errors, "argument_graph": graph, "diagnostics": diagnostics,
           "findings": graph["findings"], "coverage": graph["coverage"], "source": "model", "semantic_checked": False}
    if errors or data is None:
        return out
    for finding in data["findings"]:
        built = {**deepcopy(finding), "source": "model", "semantic_checked": False, "nodes": [], "edges": []}
        nodes = {}
        for declared in finding.get("nodes", []):
            node = {**deepcopy(declared), "local_id": declared["id"], "finding": finding["id"],
                    "id": _qualified(finding["id"], declared["id"]), "source": "model", "semantic_checked": False,
                    "binding": _node_binding(ledger, declared, bound, target["at"])}
            scope = _scope(node["kind"], node["binding"]["canonical_key"] or node["key"], node["at"])
            for field in ("evidence", "counterevidence"):
                node[field] = [resolve_evidence(ledger, ref, scope=scope, bound=bound) for ref in declared.get(field, [])]
            if node["binding"]["status"] != "matched":
                diagnostics.append({"code": "node_unbound", "finding": finding["id"], "node": node["id"], "detail": node["binding"]["diag"]})
            for ref in node["evidence"] + node["counterevidence"]:
                if ref["status"] != "ok":
                    diagnostics.append({"code": "evidence_unbound", "node": node["id"], "ref": ref["ref"], "detail": ref["diag"]})
            nodes[declared["id"]] = node
            built["nodes"].append(node)
            graph["nodes"].append(node)
        for index, declared in enumerate(finding.get("edges", [])):
            left, right = nodes.get(declared["from"]), nodes.get(declared["to"])
            file_node = next((n for n in (left, right) if n and n["kind"] == "file"), None)
            cutoff = min([n["binding"]["at"] for n in (left, right) if n] or [target["at"]])
            scope = _scope("file", (file_node["binding"]["canonical_key"] or file_node["key"]) if file_node else target["file"], cutoff)
            refs = [resolve_evidence(ledger, ref, scope=scope, bound=bound) for ref in declared.get("evidence", [])]
            edge = {**deepcopy(declared), "id": "edge:" + _qualified(finding["id"], str(index + 1)), "finding": finding["id"],
                    "from": _qualified(finding["id"], declared["from"]), "to": _qualified(finding["id"], declared["to"]),
                    "evidence": refs, "source": "model", "semantic_checked": False,
                    "binding": _edge_binding(ledger, declared, left, right, refs, bound),
                    "propagation": {"claim": declared["claim"], "source": "model", "semantic_checked": False}}
            if edge["binding"]["status"] != "confirmed":
                diagnostics.append({"code": "relation_unconfirmed", "edge": edge["id"], "detail": edge["binding"]["diag"]})
            built["edges"].append(edge)
            graph["edges"].append(edge)
        graph["findings"].append(built)
    inventory = []
    if bound:
        try:
            inventory, issues = _changes(ledger, target)
            diagnostics.extend(issues)
        except (ImportError, AttributeError, ValueError, OSError) as exc:
            diagnostics.append({"code": "change_inventory_unavailable", "detail": str(exc)})
    by_id = {r.get("id") or r.get("event_id"): r for r in inventory}
    declared_coverage = {r["event"]: r for r in data.get("coverage", [])}
    for event in list(dict.fromkeys([*by_id, *declared_coverage])):
        row = deepcopy(declared_coverage.get(event) or {"event": event, "status": "unresolved", "reason": "清单事件未声明结论"})
        row.update(declared=event in declared_coverage, source="model" if event in declared_coverage else "system",
                   semantic_checked=False, binding={"status": "matched" if event in by_id else "unlocated", "event": deepcopy(by_id.get(event))})
        graph["coverage"].append(row)
        if event not in by_id:
            diagnostics.append({"code": "coverage_event_unlocated", "event": event,
                                "detail": "对账声明未匹配目标时间区间清单；不认证其状态"})
    for finding in graph["findings"]:
        finding["change_bindings"] = [{"event": event, "status": "matched" if event in by_id else "unlocated"}
                                      for event in finding.get("changes", [])]
        for row in finding["change_bindings"]:
            if row["status"] != "matched":
                diagnostics.append({"code": "change_unlocated", "finding": finding["id"], "event": row["event"], "detail": "未匹配本次目标区间修改清单；保留声明"})
    return out
