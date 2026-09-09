"""返修记录版本及候选待核清单的显式对账;不裁定主张是否属实。"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

from . import atoms
from .filestory import ts_norm

SCHEMA = "migloop-repair-manifest/1"
POLICY = "execution-candidates/2"
STATUSES = ("explained", "unresolved", "not_repair", "out_of_scope")
MAX_ROWS = 20_000
DIFF_LINES = 8
DIFF_CHARS = 800
SCOPE = ("仅列当前账本返修链 fix_versions 中的记录版本及同链参与者的可定位候选;"
         "不保证包含所有真实修复或所有语义 hunk。候选不是文件版本、作者认定或修复事实。"
         "返修阶段的新增或改动不自动构成故障。逐项对账只检验显式交代,不验证解释、理由或证据的语义真伪。")
_NODE = re.compile(r"^file:(.+)@v([1-9]\d*)$")
_CANDIDATE = re.compile(r"^candidate:[0-9a-f]{20}$")
_ROW_KEYS = {"node", "candidate", "status", "defects", "reason", "evidence"}
NON_EXEC_TEXT = frozenset({"think", "say", "inbox", "instruction", "inject", "system", "notify", "interrupt"})
_EFFECT_RISKS = ("touched", "conditional", "conditional_reads", "write_capable", "unfinished", "unresolved")
_NONEXECUTION_BOUNDARY = ("仅按采集器的非执行文本事件种类排除强制修复对账,原始提及与全文索引保留。"
                        "排除不证明其自述或报告的修复没有发生,也不自动判为 not_repair。")


def _path(ledger: atoms.Ledger, hint: Any) -> tuple[str | None, str | None]:
    if not isinstance(hint, str) or not hint.strip():
        return None, "文件路径缺失"
    value = hint.strip().replace("\\", "/")
    direct = [p for p in ledger.stories if p.replace("\\", "/") == value]
    if len(direct) == 1:
        return direct[0], None
    suffix = value.lstrip("/")
    matches = [p for p in ledger.stories if p.replace("\\", "/").endswith("/" + suffix)
               or p.replace("\\", "/") == suffix]
    if len(matches) == 1:
        return matches[0], None
    return None, "文件路径有歧义" if matches else "文件不在当前账本"


def _event(ledger: atoms.Ledger, version: Any) -> dict[str, Any]:
    return _action_event(ledger, version.by, version.act_seq)


def _action_event(ledger: atoms.Ledger, agent_id: str, seq: int | None) -> dict[str, Any]:
    agent = ledger.agents.get(agent_id)
    action = next((a for a in agent.actions if a.seq == seq), None) if agent and seq is not None else None
    result: dict[str, Any] = {"status": "unavailable", "id": None, "ref": None, "seq": seq,
                              "path": None, "use_line": None, "result_line": None, "tool_use_id": None}
    if action is None or action.src is None:
        return result
    path, use, returned = action.src
    loc = ledger.locs.get(seq)
    if isinstance(loc, str) and "·" in loc:
        pos, tag = loc.split("·", 1)
        reference = f"#{tag}:{seq}@L{pos}"
    else:
        reference = f"#{seq}@L{use + 1}"
    result.update(status="recorded", id=atoms.event_id(ledger, agent_id, seq), ref=reference,
                  path=path, use_line=use + 1, result_line=returned + 1 if action.ok is not None else None,
                  tool_use_id=action.tuid, tool_status=action.ok, block=action.blk)
    return result


def _nonexecution_text(action: atoms.Action) -> bool:
    """只认采集器自产的文本 Action;不依据正文、命令摘要或“已修改”等自述判断效应。"""
    return (action.tool == action.kind and action.kind in NON_EXEC_TEXT and action.tuid is None
            and action.ok is True and all(ref.op == "read" for ref in action.files)
            and not any(action.detail.get(key) for key in _EFFECT_RISKS))


def _excluded_action(action: atoms.Action, path: str) -> bool:
    """排除非执行文本、确定只读和原生工具的其它目标;Bash 写脚本不证明它没动目标。"""
    if _nonexecution_text(action):
        return True
    if action.tool in {"Read", "Grep", "Glob", "LS"}:
        return True
    changes = [ref for ref in action.files if ref.op != "read"]
    if action.kind == "read" and not changes and not action.detail.get("write_capable"):
        return True
    if action.tool in {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}:
        return bool(changes) and not any(ref.path == path for ref in changes)
    return False


def _exact_mention(ledger: atoms.Ledger, path: str, mention: dict[str, Any], action: atoms.Action) -> bool:
    if mention.get("ambiguous") or _path(ledger, mention.get("token"))[0] != path:
        return False
    # file_atom 保留词法候选;原始记录若给了不同 cwd 下的绝对路径,不能因后缀同名而借来。
    originals = [item for item in action.detail.get("mentions") or []
                 if len(item) > 2 and item[0] == mention.get("token") and item[1] == mention.get("ctx") and item[2]]
    return not originals or any(str(item[2]).replace("\\", "/") == path.replace("\\", "/") for item in originals)


def _candidates(ledger: atoms.Ledger, path: str, actors: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    window = ("仅同链 fixers_all 参与者、时间 >= fix_after 的动作;无上界,不保证动作属于修复"
              if ledger.fix_after else "无明确阶段时间边界:同链 fixers_all 参与者的全动作窗口,不保证动作属于修复阶段")
    scope: dict[str, Any] = {"actors": sorted(actors), "fix_after": ledger.fix_after,
                             "window_scope": window, "unlinked_sources": 0,
                             "excluded_nonexecution": {}, "nonexecution_boundary": _NONEXECUTION_BOUNDARY,
                             "selection": "target.touches + exact unrecorded non-readonly mentions"}
    if not actors:
        return [], scope
    actions = {(aid, action.seq): action for aid in actors if aid in ledger.agents
               for action in ledger.agents[aid].actions}
    represented = {atoms.event_id(ledger, version.by, version.act_seq) for version in ledger.stories[path].versions
                   if version.act_seq is not None}
    candidates: dict[str, dict[str, Any]] = {}
    excluded_events: set[str] = set()
    boundary = ts_norm(ledger.fix_after) if ledger.fix_after else None

    def add(row: dict[str, Any], source: str) -> None:
        action = actions.get((row.get("by"), row.get("seq")))
        if action is None:
            if row.get("by") in actors:
                scope["unlinked_sources"] += 1
            return
        if boundary is not None and ts_norm(action.ts) < boundary:
            return
        if source == "mention" and not _exact_mention(ledger, path, row, action):
            return
        eid = atoms.event_id(ledger, row["by"], action.seq)
        if eid is None or eid in represented:
            return
        if _nonexecution_text(action):
            if eid not in excluded_events:
                excluded_events.add(eid)
                counts = scope["excluded_nonexecution"]
                counts[action.kind] = counts.get(action.kind, 0) + 1
            return
        if _excluded_action(action, path):
            return
        key = "candidate:" + hashlib.sha256((eid + "\0" + path).encode("utf-8")).hexdigest()[:20]
        if key in candidates:
            item = candidates[key]
            if source not in item["sources"]:
                item["sources"].append(source)
            return
        event = _action_event(ledger, row["by"], action.seq)
        candidates[key] = {"id": key, "event_id": eid, "file": path, "ref": event["ref"],
                           "seq": action.seq, "agent": row["by"], "ts": action.ts, "phase": action.stage,
                           "window_scope": window, "source": source, "sources": [source],
                           "reason": row.get("reason") or "精确路径被提及,当前账本未确认该动作对目标的效应",
                           "ctx": str(row.get("ctx") or action.detail.get("cmd") or "")[:280], "event": event,
                           "repair_confirmed": False, "writer_confirmed": False}

    story = ledger.stories[path]
    for touch in story.touches:
        add({"by": touch.by, "seq": touch.seq, "reason": touch.reason}, "touch")
    fa = atoms.file_atom(ledger, path, with_diff=False, with_content=False) or {}
    for mention in fa.get("mentions") or []:
        # touch 段已经处理方向不明;同一事件的 mention 仍记录为去重后的第二来源。
        if mention.get("effect") not in (None, "碰过(方向不明)") or mention.get("cls") == "readonly":
            continue
        add(mention, "mention")
    return sorted(candidates.values(), key=lambda item: (ts_norm(item["ts"]), item["seq"], item["id"])), scope


def _change(version: Any) -> dict[str, Any]:
    if version.diff is None:
        text = "内容未知,无可核原文差分" if version.content is None else "内容可复原,账本未提供该版差分"
        return {"kind": version.diff_kind, "text": text, "literal": False, "truncated": False,
                "semantic_checked": False}
    if not version.diff:
        return {"kind": version.diff_kind, "text": "账本记录空差分;不据此判定是否真实修复", "literal": True,
                "truncated": False, "semantic_checked": False}
    lines = [line for line in version.diff.splitlines() if line.startswith(("+", "-"))
             and not line.startswith(("--- ", "+++ ")) and line not in ("---", "+++")]
    snippet = "\n".join(lines[:DIFF_LINES])
    prefix = "差分变化行摘录(不代表全部语义 hunk):\n"
    suffix = "\n…原文见事件引用"
    truncated = len(lines) > DIFF_LINES or len(prefix) + len(snippet) > DIFF_CHARS
    text = prefix + snippet[:DIFF_CHARS - len(prefix) - (len(suffix) if truncated else 0)] + (suffix if truncated else "")
    if not lines:
        text = "账本差分未列出 +- 变化行;原文见事件引用"
    return {"kind": version.diff_kind, "text": text, "literal": True, "changed_lines": len(lines),
            "truncated": truncated, "semantic_checked": False}


def manifest(ledger: atoms.Ledger, chains_or_payload: Any, file_hint: str) -> dict[str, Any]:
    """复用服务端返修链的 fix_versions,不自行重判阶段、写者、修复类型或版本区间。"""
    path, error = _path(ledger, file_hint)
    out: dict[str, Any] = {"schema": SCHEMA, "policy": POLICY, "ledger": atoms.ledger_identity(ledger), "file": path,
                           "scope": SCOPE, "selection": "chains.fix_versions", "items": [], "candidates": [], "errors": []}
    if error:
        out["errors"].append({"code": "invalid_file", "message": error})
        return out
    if isinstance(chains_or_payload, dict):
        chains = chains_or_payload.get("chains") if "chains" in chains_or_payload else [chains_or_payload]
    else:
        chains = chains_or_payload
    if not isinstance(chains, list):
        out["errors"].append({"code": "invalid_chains", "message": "返修链必须是列表或包含 chains 的载荷"})
        return out
    wanted: set[int] = set()
    actors: set[str] = set()
    for i, chain in enumerate(chains):
        if not isinstance(chain, dict):
            out["errors"].append({"code": "invalid_chain", "chain": i, "message": "返修链条目必须是映射"})
            continue
        chain_path, _ = _path(ledger, chain.get("file_abs") or chain.get("file"))
        if chain_path != path:
            continue
        actors.update(fixer["id"] for fixer in chain.get("fixers_all") or []
                      if isinstance(fixer, dict) and isinstance(fixer.get("id"), str))
        versions = chain.get("fix_versions")
        if not isinstance(versions, list):
            out["errors"].append({"code": "invalid_fix_versions", "chain": i, "message": "fix_versions 必须是列表"})
            continue
        for version in versions:
            if type(version) is not int or version < 1:
                out["errors"].append({"code": "invalid_fix_version", "chain": i, "version": version})
            else:
                wanted.add(version)
    story = ledger.stories[path]
    versions_by_id = {version.v: version for version in story.versions}
    for number in sorted(wanted):
        version = versions_by_id.get(number)
        if version is None:
            out["errors"].append({"code": "missing_ledger_version", "version": number,
                                   "message": "返修链中的版本不在当前账本"})
            continue
        before = number - 1 if number - 1 in versions_by_id else None
        out["items"].append({"node": f"file:{path}@v{number}", "before": f"file:{path}@v{before}" if before else None,
                             "v": number, "ts": version.ts, "source": version.source, "stage": version.stage,
                             "content_known": version.content is not None, "partial_known": version.partial is not None,
                             "conditional": version.conditional, "state_gap": version.state_gap,
                             "writer": {"id": version.by, "v": version.by_ver},
                             "event": _event(ledger, version), "change": _change(version)})
    out["candidates"], out["candidate_scope"] = _candidates(ledger, path, actors)
    return out


def _defect_ids(defects: Any) -> set[str]:
    if isinstance(defects, dict):
        defects = list(defects)
    if not isinstance(defects, (list, tuple, set, frozenset)):
        return set()
    return {str(d.get("id")) if isinstance(d, dict) else d for d in defects
            if (isinstance(d, dict) and isinstance(d.get("id"), str)) or isinstance(d, str)}


def _recorded_changed_lines(item: dict[str, Any]) -> int | None:
    """只用冻结清单的明确字面差分元数据;旧清单缺字段时不从正文补事实。"""
    change = item.get("change")
    if not isinstance(change, dict) or change.get("literal") is not True:
        return None
    count = change.get("changed_lines")
    return count if type(count) is int and count >= 0 else None


def reconcile(ledger: atoms.Ledger, manifest_doc: dict[str, Any], rows: Any, defects: Any,
              *, identity_bound: bool = False) -> dict[str, Any]:
    """complete 仅指清单中每版及每候选有唯一合法声明;延后也算交代,不代表问题已解决。

    identity_bound 由入口核验后显式传入。这里从不读取 repair.before/after、散文或其它引用来猜覆盖。
    模型状态 out_of_scope 汇总为 deferred,与历史 out_of_scope 非法目标错误桶分开。
    unconfirmed 只汇总有效已交代行中的 unresolved/deferred;缺项与无效行仍在各自错误桶。
    advisories 是字面记录与主张的待核提示,不裁决理由真伪,不影响 valid/complete。
    """
    version_items = {item["node"]: item for item in manifest_doc.get("items") or []}
    expected_versions = [item["node"] for item in manifest_doc.get("items") or []]
    expected_candidates = [item["id"] for item in manifest_doc.get("candidates") or []]
    expected = expected_versions + expected_candidates
    expected_set = set(expected)
    out: dict[str, Any] = {"provided": rows is not None, "identity_bound": identity_bound is True,
                           "scope": SCOPE, "semantic_checked": False, "evidence_checked": False,
                           "complete": False, "status": "unprovided", "rows": [], "missing": [], "duplicates": [],
                           "missing_versions": [], "missing_candidates": [],
                           "out_of_scope": [], "invalid_status": [], "empty_reason": [], "unknown_defects": [],
                           "invalid_rows": [], "manifest_errors": list(manifest_doc.get("errors") or []), "errors": [],
                           "unresolved": [], "not_repair": [], "deferred": [], "unconfirmed": [],
                           "advisories": [], "claim_advisories_checked": False}
    if manifest_doc.get("ledger") != atoms.ledger_identity(ledger):
        out["manifest_errors"].append({"code": "ledger_mismatch", "message": "清单身份不属于当前账本"})
    out["claim_advisories_checked"] = out["identity_bound"] and not out["manifest_errors"]
    occurrences: dict[str, list[int]] = defaultdict(list)
    valid: dict[str, list[int]] = defaultdict(list)
    ids = _defect_ids(defects)

    def issue(bucket: str, row: int | None, **detail: Any) -> None:
        item = {"row": row, **detail}
        out[bucket].append(item)
        out["errors"].append({"code": bucket, **item})

    values = rows if isinstance(rows, list) else []
    if rows is not None and not isinstance(rows, list):
        issue("invalid_rows", None, message="coverage 必须是列表")
    if len(values) > MAX_ROWS:
        issue("invalid_rows", None, message=f"coverage 超过 {MAX_ROWS} 条")
        values = values[:MAX_ROWS]
    for i, row in enumerate(values):
        if not isinstance(row, dict):
            issue("invalid_rows", i, message="coverage 条目必须是映射")
            continue
        error_count = len(out["errors"])
        extra = set(row) - _ROW_KEYS
        if extra:
            issue("invalid_rows", i, message="coverage 条目包含未知字段", fields=sorted(str(k) for k in extra))
        target_kind = "candidate" if "candidate" in row else "node"
        spec = row.get(target_kind)
        target = {target_kind: spec}
        canonical = None
        error = None
        if ("node" in row) == ("candidate" in row):
            issue("invalid_rows", i, message="node 与 candidate 必须且只能提供一个")
            error = "node 与 candidate 必须且只能提供一个"
        elif target_kind == "candidate":
            if isinstance(spec, str) and _CANDIDATE.fullmatch(spec.strip()):
                canonical = spec.strip()
            else:
                error = "candidate 必须是清单提供的 candidate:<20位十六进制摘要>"
        else:
            match = _NODE.fullmatch(spec.strip()) if isinstance(spec, str) else None
            if match:
                path, error = _path(ledger, match.group(1))
                if path is not None:
                    canonical = f"file:{path}@v{int(match.group(2))}"
            else:
                error = "node 必须是带版本的 file:<路径>@vN"
        if canonical not in expected_set:
            issue("out_of_scope", i, **target, message=error or "条目不在目标文件的返修版本及候选清单中")
        else:
            occurrences[canonical].append(i)
        status = row.get("status")
        if status not in STATUSES:
            issue("invalid_status", i, **target, status=status)
        reason = row.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            issue("empty_reason", i, **target)
        linked = row.get("defects")
        if not isinstance(linked, list) or any(not isinstance(d, str) or not d.strip() for d in linked):
            issue("invalid_rows", i, **target, message="defects 必须是非空字符串组成的列表(允许空列表)")
        else:
            for defect in linked:
                if defect not in ids:
                    issue("unknown_defects", i, **target, defect=defect)
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or any(not isinstance(ref, str) or not ref.strip() for ref in evidence):
            issue("invalid_rows", i, **target, message="evidence 必须是非空引用字符串组成的列表(允许空列表)")
        okay = len(out["errors"]) == error_count and canonical in expected_set
        claim_checked = out["claim_advisories_checked"] and canonical in expected_set
        manifest_item = version_items.get(canonical, {}) if claim_checked else {}
        changed_lines = _recorded_changed_lines(manifest_item)
        advisories = []
        if status == "not_repair" and changed_lines is not None and changed_lines > 0:
            advisories.append({"code": "recorded_change_needs_basis", "level": "warning", "row": i,
                               "target": canonical, "changed_lines": changed_lines,
                               "event_ref": (manifest_item.get("event") or {}).get("ref"),
                               "message": "清单有字面变化行,not_repair 仍需依据;变化不自动等于缺陷或真实修复。"
                                          "若仅因本题未调查,用 out_of_scope/unresolved,不能据此认定没有修复。"})
            out["advisories"].extend(advisories)
        out["rows"].append({"row": i, "node": row.get("node"), "candidate": row.get("candidate"),
                             "canonical_node": canonical if target_kind == "node" else None,
                             "canonical_candidate": canonical if target_kind == "candidate" else None,
                             "canonical_target": canonical, "status": status,
                             "defects": linked, "reason": reason, "evidence": evidence, "valid": okay,
                             "semantic_checked": False, "evidence_checked": False,
                             "claim_advisories_checked": claim_checked, "recorded_changed_lines": changed_lines,
                             "advisories": advisories})
        if okay:
            valid[canonical].append(i)
    out["missing"] = [node for node in expected if node not in occurrences]
    out["missing_versions"] = [node for node in expected_versions if node not in occurrences]
    out["missing_candidates"] = [candidate for candidate in expected_candidates if candidate not in occurrences]
    for node, found in occurrences.items():
        if len(found) > 1:
            issue("duplicates", None, **{"candidate" if node in expected_candidates else "node": node}, rows=found)
    out["errors"] += [{"code": "missing", "node": node} for node in out["missing_versions"]]
    out["errors"] += [{"code": "missing", "candidate": candidate} for candidate in out["missing_candidates"]]
    out["errors"] += [{"code": "manifest_error", **error} for error in out["manifest_errors"]]
    accounted = {node for node in expected if len(occurrences.get(node, [])) == len(valid.get(node, [])) == 1}
    for row in out["rows"]:
        if row["canonical_target"] in accounted and row["status"] in ("unresolved", "not_repair"):
            out[row["status"]].append(row["canonical_target"])
        if row["canonical_target"] in accounted and row["status"] == "out_of_scope":
            out["deferred"].append(row["canonical_target"])
        if row["canonical_target"] in accounted and row["status"] in ("unresolved", "out_of_scope"):
            out["unconfirmed"].append(row["canonical_target"])
    out["complete"] = out["provided"] and out["identity_bound"] and not out["errors"]
    if out["manifest_errors"]:
        out["status"] = "invalid_manifest"
    elif not out["provided"]:
        out["status"] = "unprovided"
    elif not out["identity_bound"]:
        out["status"] = "unbound"
    elif any(out[key] for key in ("duplicates", "out_of_scope", "invalid_status", "empty_reason", "unknown_defects", "invalid_rows")):
        out["status"] = "invalid"
    else:
        out["status"] = "complete" if out["complete"] else "incomplete"
    out["counts"] = {"expected": len(expected), "provided": len(values), "accounted": len(accounted),
                     "expected_versions": len(expected_versions), "expected_candidates": len(expected_candidates),
                     "missing_versions": len(out["missing_versions"]), "missing_candidates": len(out["missing_candidates"]),
                     "missing": len(out["missing"]), "unresolved": len(out["unresolved"]), "not_repair": len(out["not_repair"]),
                     "deferred": len(out["deferred"]), "unconfirmed": len(out["unconfirmed"]),
                     "advisories": len(out["advisories"]),
                     "advisory_rows": len({advice["row"] for advice in out["advisories"]})}
    return out
