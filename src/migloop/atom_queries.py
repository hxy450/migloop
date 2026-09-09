"""Shared stateless atom queries. Transports own navigation, not evidence semantics.

HTTP and MCP normalize the same query parameters and select the same scoped atom
data. JSON is the structured projection; text adds presentation budgets. No query
here opens a node, issues a search receipt, changes the ledger, or writes a report.
"""
from __future__ import annotations

import re
from typing import Any

from . import atoms, time_scope


_INTS = frozenset({"v", "since", "until", "start", "n", "v_from", "v_to", "diff_chars",
                   "m_from", "m_n", "max_chars", "offset", "seq", "limit", "summary_chars"})
_BOOLS = frozenset({"content", "diff", "readers", "m_all", "reads", "seen", "after", "scope_only", "changed"})
_DEFAULTS: dict[str, dict[str, Any]] = {
    "sessions": {"file": None},
    "index": {"kind": None, "query": None, "limit": 0},
    "file": {"path": None, "v": None, "content": False, "diff": False, "start": None, "n": None,
             "readers": False, "v_from": None, "v_to": None, "diff_chars": None,
             "m_from": 1, "m_n": 0, "m_all": False, "scope_only": False},
    "agent": {"id": None, "v": None, "since": None, "until": None, "reads": None, "seen": False,
              "scope_only": False, "summary_chars": 96},
    "blame": {"path": None, "v": None, "start": None, "n": None, "changed": False},
    "diff": {"path": None, "v": None},
    "search": {"q": "", "agent": None, "v": None, "since": None, "file": None, "after": False,
               "since_ts": None, "until_ts": None, "kind": None, "q_any": None},
    "action": {"id": None, "seq": None, "ref": None, "max_chars": 20000, "offset": 0, "find": "", "part": None,
               "m_n": 0, "m_from": 1},
    "check": {"draft": None, "file": None},
}
_REQUIRED = {"file": ("path",), "agent": ("id",), "blame": ("path",),
             "diff": ("path", "v")}


def optional_int(args: dict[str, Any], key: str) -> int | None:
    value = args.get(key)
    if value is None or value == "":
        return None
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value)
    raise ValueError(f"{key} 必须是整数")


def boolean(value: Any, key: str) -> bool:
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        if value.strip().lower() in ("true", "1"):
            return True
        if value.strip().lower() in ("false", "0", ""):
            return False
    raise ValueError(f"{key} 必须是布尔值(true/false 或 1/0)")


def parameters(tool: str, supplied: dict[str, Any], *, validate_search_scope: bool = True) -> dict[str, Any]:
    if tool not in _DEFAULTS:
        raise ValueError(f"未知工具: {tool}")
    values = dict(supplied)
    # Retain documented HTTP aliases while the canonical core has one name.
    aliases = {"sessions": {"path": "file"}, "search": {"id": "agent", "path": "file"}}.get(tool, {})
    for alias, canonical in aliases.items():
        if alias in values:
            if canonical in values and values[canonical] not in (None, "") and values[canonical] != values[alias]:
                raise ValueError(f"{canonical} 与别名 {alias} 冲突")
            if values.get(canonical) in (None, ""):
                values[canonical] = values[alias]
            del values[alias]
    unknown = set(values) - set(_DEFAULTS[tool])
    if unknown:
        raise ValueError("未知查询参数: " + ", ".join(sorted(unknown)))
    out = dict(_DEFAULTS[tool])
    for key, value in values.items():
        if tool == "search" and key == "q_any":
            from .search_terms import normalize
            out[key] = normalize(values.get("q", ""), value, http_json=True)
        elif key in _INTS:
            parsed = optional_int(values, key)
            out[key] = out[key] if parsed is None else parsed
        elif key in _BOOLS:
            out[key] = None if key == "reads" and value is None else boolean(value, key)
        else:
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} 必须是字符串")
            out[key] = value if value is not None else out[key]
    for key in _REQUIRED.get(tool, ()):
        if out[key] is None or out[key] == "":
            raise ValueError(key)
    if tool == "agent" and not 32 <= out["summary_chars"] <= 600:
        raise ValueError("summary_chars 必须在 32–600 之间；完整原文用 action")
    if tool == "search" and validate_search_scope:
        from .search_terms import normalize, valid_time
        out["q_any"] = normalize(out["q"], out["q_any"])
        if any(out[k] is not None and not valid_time(out[k]) for k in ("since_ts", "until_ts")):
            raise ValueError("since_ts/until_ts 必须是带明确时区的 ISO 时刻")
        if out["since_ts"] and out["until_ts"] and atoms.ts_norm(out["since_ts"]) > atoms.ts_norm(out["until_ts"]):
            raise ValueError("since_ts 不能晚于 until_ts")
        if out["agent"] and out["file"]:
            raise ValueError("search 的 agent 与 file 范围互斥")
        if out["kind"] not in (None, "write"):
            raise ValueError("仅支持普通 search 或 kind=write")
        if out["file"] and any(out[k] not in (None, False) for k in ("since", "after", "since_ts", "until_ts", "kind")):
            raise ValueError("file search 只支持 v 窗口；时间范围请用 agent 或全池查询")
        version_window = out["v"] is not None or out["since"] is not None
        if out["kind"] == "write" and (out["agent"] or out["file"] or version_window or out["after"]):
            raise ValueError("kind=write 只支持全池时间窗口")
        if not out["agent"] and not out["file"] and version_window:
            raise ValueError("全池 search 只支持时间窗口；v/since 需要指定 agent")
        if out["agent"] and (out["since_ts"] or out["until_ts"]) and version_window:
            raise ValueError("agent search 的时间窗口与 v/since 版本窗口不能混用；请明确选择范围")
    if tool == "action":
        if out["ref"] is not None:
            if out["id"] is not None or out["seq"] is not None:
                raise ValueError("action 的 ref 与 id/seq 必须二选一")
        elif not out["id"] or out["seq"] is None:
            raise ValueError("action 需要 ref=完整原文引用，或同时给 id 和 seq")
    return out


def validate_target(ledger: atoms.Ledger, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Carry the validated canonical key into the renderer, not just validation.

    MCP already supplies the canonical navigation target. HTTP must not accept
    the same alias and then hand its unresolved spelling to a narrower lookup.
    """
    if tool in ("file", "agent") and args.get("v") is not None:
        from .via import target
        field = "path" if tool == "file" else "id"
        node, error = target(ledger, tool, str(args[field]), args["v"])
        if error:
            raise ValueError(error)
        return {**args, field: node[1]}
    return args


def validate_file_window(anchor: int, v_from: int | None, v_to: int | None) -> None:
    if ((v_from is not None and (v_from < 1 or v_from > anchor))
            or (v_to is not None and (v_to < 1 or v_to > anchor))
            or (v_from is not None and v_to is not None and v_from > v_to)):
        raise ValueError(f"⛔ diff 窗口必须满足 1 ≤ v_from ≤ v_to ≤ 查询锚点 v{anchor};未执行查询。")


def file_data(ledger: atoms.Ledger, path: str, v: int | None = None, *,
              content: bool = False, diff: bool = False) -> dict[str, Any] | None:
    data = atoms.file_atom(ledger, path, v, with_content=content, with_diff=diff)
    if data is not None:
        data = {**data, "time_scope": time_scope.for_atom(ledger, "file", data)}
    return data


def agent_data(ledger: atoms.Ledger, aid: str, v: int | None = None, *,
               since: int | None = None, until: int | None = None) -> dict[str, Any] | None:
    # Apply the authenticated completion-time boundary before the version-window
    # projection. Earlier inputs remain an index, not an inference of relevance.
    data = atoms.agent_atom(ledger, aid, v)
    if data is None:
        return None
    if until is not None:
        from .atom_scope import agent_until
        data = agent_until(ledger, data, until)
    prior = [a for a in data["actions"] if since is not None and
             (a["ver"] if a["ver"] is not None else a["at"]) <= since]
    prior_seqs = {a["seq"] for a in prior}
    prior_reads = [r for r in data["reads"] if r["seq"] in prior_seqs]
    counts = {"reads": len(prior_reads), "inbox": 0, "inject": 0, "instruction": 0, "other": 0}
    for action in prior:
        if action["ver"] is None and action["kind"] != "read":
            key = action["kind"] if action["kind"] in ("inbox", "inject", "instruction") else "other"
            counts[key] += 1
    data["input_scope"] = {
        "schema": "migloop-input-scope/1", "anchor": f"agent:{data['id']}@v{data['v']}",
        "since": since, "until": until, "omitted_prior": counts,
        "prior_read_preview": [
            {**{key: r.get(key) for key in ("path", "v", "seq", "at", "via", "dep", "certain", "proof",
                                           "start", "n", "full", "observation_uncertain", "availability_basis",
                                           "completion_state", "stale", "latest_v", "self_written")},
             "seen_n": len(r.get("seen") or [])}
            for r in prior_reads[:8]],
        "prior_read_remaining": max(0, len(prior_reads) - 8),
        "prior_query": {"id": data["id"], "v": min(since, data["v"]), "reads": True}
                       if since is not None and since > 0 and prior else None,
        "prompt_chars": len(data.get("prompt") or ""),
        "prompt_in_body": since is None,
        "scope_complete": False,
        "note": "仅索引已记录且通过当前时间截止的输入；早期输入不因本窗口省略而不存在，"
                "也不因此被证明与当前缺陷有关。展开早期窗口不继承本次 until，须另核完成时刻。",
    }
    if since is not None:
        data = {**data, "since": since,
                "actions": [a for a in data["actions"] if a["seq"] not in prior_seqs],
                "reads": [r for r in data["reads"] if r["seq"] not in prior_seqs],
                "writes": [w for w in data["writes"] if w.get("ver") is None or w["ver"] > since],
                "children": [c for c in data["children"] if c["ver"] > since],
                "inbox": [m for m in data["inbox"] if m["seq"] not in prior_seqs]}
    return {**data, "time_scope": data.get("time_scope") or time_scope.for_atom(ledger, "agent", data, until=until)}


def render_text(ledger: atoms.Ledger, root: str, tool: str, supplied: dict[str, Any], *,
                chains: dict[str, Any] | None = None, navigation_hits: list[dict[str, Any]] | None = None) -> str:
    from . import atoms_text, draft_check
    args = validate_target(ledger, tool, parameters(tool, supplied))
    if tool == "sessions":
        if chains is None:
            raise ValueError("sessions 需要链清单")
        out = atoms_text.render_chains(chains, root=root, file=args["file"], identity=atoms.ledger_identity(ledger))
        scope_text = atoms_text.render_observation_scope(chains.get("observation_scope"))
        if scope_text:
            out += "\n\n" + scope_text
        out += "\n\n" + atoms_text.render_time_scope(time_scope.overview(ledger))
        if args["file"]:
            out += "\n\n" + atoms_text.render_repair_manifest(ledger, chains, args["file"], root=root)
        return out
    if tool == "index":
        return atoms_text.render_index(ledger, args["kind"], args["query"], root=root,
                                       limit=args["limit"] or (300 if args["query"] else 80))
    if tool == "file":
        if args.pop("scope_only"):
            data = file_data(ledger, args["path"], args["v"])
            return atoms_text.render_time_scope(data["time_scope"]) if data else "账本里没有该文件"
        return atoms_text.render_file(ledger, args.pop("path"), root=root, **args)
    if tool == "agent":
        if args.pop("scope_only"):
            data = agent_data(ledger, args["id"], args["v"], since=args["since"], until=args["until"])
            return atoms_text.render_time_scope(data["time_scope"]) if data else "账本里没有该 agent"
        return atoms_text.render_agent(ledger, args.pop("id"), root=root, **args)
    if tool == "blame":
        return atoms_text.render_blame(ledger, args.pop("path"), root=root, **args)
    if tool == "diff":
        return atoms_text.render_diff(ledger, args["path"], args["v"], root=root)
    if tool == "search":
        text = atoms_text.render_search(ledger, root=root, navigation_hits=navigation_hits, **args)
        if args["after"] and (not args["agent"] or args["since_ts"] or args["until_ts"]):
            text += "\nafter 仅控制 agent 版本锚点后的命中；本次按上列时间范围，after=True 不扩大时间范围。"
        return text
    if tool == "action":
        from .action_query import resolve
        address = resolve(ledger, id=args.pop("id"), seq=args.pop("seq"), ref=args.pop("ref"))
        text = atoms_text.render_action(ledger, address.agent, address.seq, **args)
        if address.status == "drifted":
            text = f"引用序号已漂移；按唯一转录位置定位到 #{address.seq}，未按旧序号猜测。\n" + text
        elif address.status == "legacy_alias":
            text = f"旧代理别名 {address.requested_id!r} 唯一解析为 id={address.agent}；只在此代理内定位 #{address.seq}。\n" + text
        return text
    if tool == "check":
        return draft_check.render(ledger, args["draft"], chains, args["file"])
    raise ValueError(f"未知文本投影: {tool}")


def json_data(ledger: atoms.Ledger, tool: str, supplied: dict[str, Any], *,
              chains: dict[str, Any] | None = None) -> dict[str, Any] | None:
    args = validate_target(ledger, tool, parameters(tool, supplied))
    # JSON exposes raw structured collections, not text pagination. Never accept
    # a text window and then quietly send a larger raw body to its caller.
    supported = {
        "index": {"kind"}, "file": {"path", "v", "content", "diff", "scope_only"},
        "agent": {"id", "v", "since", "until", "scope_only"},
        "blame": {"path", "v", "start", "n", "changed"},
        "action": {"id", "seq", "ref"}, "check": {"draft", "file"},
    }
    unsupported = set(supplied) - supported.get(tool, set())
    if unsupported:
        raise ValueError("JSON 投影不支持这些展示参数，请用文本投影: " + ", ".join(sorted(unsupported)))
    if tool == "index":
        if args["kind"] not in (None, "", "time"):
            raise ValueError("JSON index 只支持完整目录或 kind=time，分类/检索请用文本投影")
        scope = time_scope.overview(ledger)
        return {"time_scope": scope} if args["kind"] == "time" else {**atoms.ledger_index(ledger), "time_scope": scope}
    if tool == "file":
        data = file_data(ledger, args["path"], args["v"], content=args["content"] and not args["scope_only"],
                         diff=args["diff"] and not args["scope_only"])
        return {"time_scope": data["time_scope"]} if data and args["scope_only"] else data
    if tool == "agent":
        data = agent_data(ledger, args["id"], args["v"], since=args["since"], until=args["until"])
        return {"time_scope": data["time_scope"]} if data and args["scope_only"] else data
    if tool == "blame":
        return atoms.blame(ledger, args["path"], args["v"], args["start"], args["n"], changed=args["changed"])
    if tool == "action":
        from .action_query import resolve
        address = resolve(ledger, id=args["id"], seq=args["seq"], ref=args["ref"])
        data = atoms.action_raw(ledger, address.agent, address.seq)
        if data is not None and address.requested_ref is not None:
            data = {**data, "query_reference": {"ref": address.requested_ref,
                    "status": address.status, "agent": address.agent, "seq": address.seq}}
        elif data is not None and address.status == "legacy_alias":
            data = {**data, "query_address": {"requested_id": address.requested_id,
                    "status": address.status, "agent": address.agent, "seq": address.seq}}
        return data
    if tool == "check":
        from . import draft_check
        return draft_check.evaluate(ledger, args["draft"], chains, args["file"])
    raise ValueError(f"工具无 JSON 投影: {tool}")
