"""Free investigation with immutable scopes and transport-independent delivery.

Query receipts bind returned bytes, not causal truth. They become evidence of a
visit only when the run recorder authenticates a complete real call/return pair.
"""
from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from typing import Any

from . import atoms, raw_events, temporal
from . import transcript_store as store
from .time_receipts import digest

SCHEMA = "migloop-investigation-batch/1"
MARKER = "\nMIGLOOP_INVESTIGATION_RECEIPT "
WIRE_MARKER = "\nMIGLOOP_BATCH_WIRE_RECEIPT "
WIRE_RECEIPT = "migloop-batch-wire-receipt/1"
TOOLS = frozenset({"file", "agent", "search", "record", "expand", "diff", "blame", "changes", "events"})
_LATEST: OrderedDict[tuple, str] = OrderedDict()


def _latest(ledger: atoms.Ledger) -> str:
    registry = store.sources(ledger)
    source_specs = {path: store.source_spec(ledger, path) for path in registry}
    signature = []
    for path in sorted(registry):
        try:
            st = os.stat(path)
            signature.append((path, st.st_mtime_ns, st.st_size, source_specs[path]))
        except OSError:
            signature.append((path, None, None, source_specs[path]))
    key = tuple(signature)
    if key in _LATEST:
        return _LATEST[key]
    times = []
    for path in registry:
        try:
            times.extend(r.ts for r in store.records(path, source=source_specs[path]) if r.ts)
        except (OSError, UnicodeError, ValueError):
            continue  # Actual query reports source gaps, not a silent all-clear.
    value = max(times, default="latest")
    _LATEST[key] = value
    while len(_LATEST) > 4:
        _LATEST.popitem(last=False)
    return value


def scope(ledger: atoms.Ledger, kind: str = "pool", key: str | None = None,
          at: str = "latest", since_ts: str | None = None) -> dict[str, Any]:
    if kind not in ("file", "agent", "pool"):
        raise ValueError("scope.kind 必须是 file/agent/pool")
    window = temporal.Window.parse(at, since_ts)
    if kind == "file":
        if not isinstance(key, str) or not key.strip():
            raise ValueError("文件scope缺key")
        key = temporal.resolve_file(ledger, key)
    elif kind == "agent":
        owner = atoms.resolve_agent(ledger, key or "")
        if owner is None:
            raise ValueError("agent scope不存在或有歧义")
        key = owner.id
    elif key is not None:
        raise ValueError("pool scope不接受key")
    resolved = _latest(ledger) if window.at == "latest" else window.at
    temporal.Window.parse(resolved, window.since)
    out = {"kind": kind, "key": key, "at": resolved,
           "since_ts": window.since}
    return {**out, "id": "scope:" + digest([atoms.ledger_identity(ledger), out])[:20]}


def _bound(ledger, tool, supplied):
    args = dict(supplied)
    if tool in ("events", "search") and "path" in args:
        alias = args.pop("path")
        if args.get("file") and alias and temporal.resolve_file(ledger, args["file"]) != temporal.resolve_file(ledger, alias):
            raise ValueError("file与path别名冲突；未执行查询")
        if not args.get("file"):
            args["file"] = alias
    declared = args.pop("scope", None)
    if any(args.get(k) is not None for k in ("v", "since", "until", "v_from", "v_to", "until_ts")) or args.get("via"):
        raise ValueError("新调查仅用时间scope，不接受版本窗口或via；旧报告请用兼容接口")
    if declared is not None and not isinstance(declared, dict):
        raise ValueError("scope必须是返回的时间范围对象")
    if declared is not None:
        allowed = {"kind", "key", "at", "since_ts", "id"}
        if set(declared) - allowed:
            raise ValueError("scope含未知字段")
        current = scope(ledger, **{k: v for k, v in declared.items() if k != "id"})
        if declared.get("id") and current["id"] != declared["id"]:
            raise ValueError("scope身份/内容漂移；请重新打开范围")
        for field in ("at", "since_ts"):
            if field in args and args[field] is not None:
                test = temporal.Window.parse(args.get("at", current["at"]), args.get("since_ts", current["since_ts"]))
                if test.at != current["at"] or test.since != current["since_ts"]:
                    raise ValueError("查询与继承scope时间冲突；独立查阅请另开scope")
    else:
        kind = (tool if tool in ("file", "agent") else "file" if args.get("path") or args.get("file")
                else "agent" if args.get("agent") else "pool")
        key = args.get("path") or args.get("file") if kind == "file" else args.get("id") or args.get("agent")
        current = scope(ledger, kind, key, args.get("at") or "latest", args.get("since_ts"))
    args.update(at=current["at"], since_ts=current["since_ts"])
    expected = "file" if tool in ("file", "diff", "blame", "changes") else "agent" if tool == "agent" else None
    if expected and current["kind"] != expected:
        raise ValueError(f"{tool}需要{expected} scope")
    if expected:
        field = "path" if expected == "file" else "id"
        if args.get(field):
            requested = scope(ledger, expected, args[field], current["at"], current["since_ts"])
            if requested["key"] != current["key"]:
                raise ValueError("目标与继承scope不一致")
        args[field] = current["key"]
    if tool in ("search", "events"):
        for name in ("file", "agent"):
            if args.get(name) and (current["kind"] != name or scope(ledger, name, args[name], current["at"], current["since_ts"])["key"] != current["key"]):
                raise ValueError("搜索目标与scope不一致")
        args.pop("file", None)
        args.pop("agent", None)
        if current["kind"] in ("file", "agent"):
            args[current["kind"]] = current["key"]
    return current, args


def _field(value, pointer):
    """RFC 6901 selection, never an expression or best-effort substring."""
    if not isinstance(pointer, str) or pointer and not pointer.startswith("/"):
        raise ValueError("pointer必须是JSON Pointer；空串表示整个JSON值")
    if not pointer:
        return value
    for raw in pointer[1:].split("/"):
        if re.search(r"~(?![01])", raw):
            raise ValueError("JSON Pointer转义无效")
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and (key == "0" or key.isascii() and key.isdigit() and not key.startswith("0")) and int(key) < len(value):
            value = value[int(key)]
        else:
            raise ValueError("JSON Pointer未定位到字段；未返回其他字段代替")
    return value


def _record(ledger, ref, current, *, offset=0, max_chars=12000, include_undated=False, pointer=None):
    record = store.resolve(ledger, ref)
    window = temporal.Window.parse(current["at"], current["since_ts"])
    if record.ts is not None and not window.contains(record.ts):
        raise ValueError("记录不在继承时间范围内")
    if current["kind"] == "agent" and record.path not in store.sources(ledger, current["key"]):
        raise ValueError("记录不在继承agent的转录中")
    if current["kind"] == "file":
        # A parsed relation OR lexical association admits evidence, never a writer.
        annotations = temporal._annotations(ledger, window).get((record.path, record.line), [])
        exact = any(r["path"] == current["key"] for a in annotations for r in a["relations"])
        name = current["key"].rsplit("/", 1)[-1].casefold()
        if not exact and name not in record.text.replace("\\", "/").casefold():
            from . import body_sources
            if not body_sources.admits_record(ledger, current, record.ref):
                raise ValueError("记录不在继承文件的已索引/原生正文/词法范围；可独立打开pool范围核实")
    data = temporal.record_data(ledger, ref, at=current["at"], offset=offset,
                                max_chars=max_chars, include_undated=include_undated)
    if pointer is not None:
        if record.malformed:
            raise ValueError("原始记录不是有效JSON；只能展开原文")
        value = _field(record.value, pointer)
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        data.update(schema="migloop-raw-field/1", pointer=pointer, text=text[offset:offset + max_chars],
                    chars=len(text), next_offset=offset + max_chars if offset + max_chars < len(text) else None,
                    representation="decoded_string" if isinstance(value, str) else "json_value",
                    field_sha256=digest(text))
    return data


def _action_refs(ledger, ref):
    from .action_query import resolve
    address = resolve(ledger, ref=ref)
    action = next(a for a in ledger.agents[address.agent].actions if a.seq == address.seq)
    if not action.src:
        raise ValueError("动作没有可展开的原文指针")
    path, first, last = action.src
    wanted = {n + 1 for n in (first, last) if n is not None and n >= 0}
    return [store.read_record(path, line, source=store.source_spec(ledger, path)).ref for line in sorted(wanted)]


def expand(ledger, refs, current, *, offset=0, max_chars=12000, include_undated=False):
    if not isinstance(refs, list) or not 1 <= len(refs) <= 24:
        raise ValueError("refs必须是1–24个引用或{ref,pointer}；可以混合raw和已给出的旧动作引用")
    items = []
    for i, supplied in enumerate(refs):
        ref, pointer = supplied, None
        try:
            if isinstance(supplied, dict) and set(supplied) == {"ref", "pointer"}:
                ref, pointer = supplied["ref"], supplied["pointer"]
                if not isinstance(pointer, str):
                    raise ValueError("pointer必须是JSON Pointer字符串")
            if not isinstance(ref, str):
                raise ValueError("引用必须是字符串或{ref,pointer}")  # noqa: TRY004 -- query validation maps to HTTP 400
            originals = [ref] if ref.startswith("raw:") else _action_refs(ledger, ref)
            parts = []
            withheld = []
            for original in originals:
                try:
                    parts.append(_record(ledger, original, current, offset=offset,
                                         max_chars=max_chars, include_undated=include_undated, pointer=pointer))
                except ValueError as exc:
                    withheld.append({"ref": original, "reason": str(exc)})
            items.append({"item_index": i, "ref": ref, "pointer": pointer, "status": "ok" if parts else "error",
                          "records": parts, "withheld": withheld})
        except (ValueError, OSError, UnicodeError) as exc:
            items.append({"item_index": i, "ref": ref, "pointer": pointer, "status": "error", "error": str(exc)})
    return {"schema": "migloop-evidence-expansion/1", "scope": current, "items": items,
            "note": "部分返回不等于整次调用已读；拒绝的另一侧不泄漏正文。"}


def changes(ledger, path, at, since_ts=None, offset=0, limit=40, related_offset=0, related_limit=8):
    from . import change_inventory
    current = scope(ledger, "file", path, at, since_ts)
    return change_inventory.build(ledger, current, offset, limit,
                                  related_offset=related_offset, related_limit=related_limit)


@raw_events.reuse_scans
def query(ledger, tool, supplied):
    from . import atom_queries
    if tool not in TOOLS or not isinstance(supplied, dict):
        raise ValueError("未知调查操作或args不是映射")
    current, args = _bound(ledger, tool, supplied)
    # Presentation is one contract, independent of the selected evidence query.
    # Diff/record already expand their selected material. A request for more
    # annotation detail must not make those otherwise valid queries fail.
    details = atom_queries.boolean(args.pop("details", False), "details")
    if tool == "changes":
        data = changes(ledger, **args)
    elif tool == "events":
        from . import raw_events
        args["path"] = args.pop("file", None)
        data = raw_events.query(ledger, **args)
    elif tool == "expand":
        args.pop("at", None)
        args.pop("since_ts", None)
        data = expand(ledger, current=current, **args)
    elif tool == "record":
        args.pop("at", None)
        args.pop("since_ts", None)
        data = _record(ledger, current=current, **args)
    else:
        if tool in ("file", "agent", "search"):
            args["details"] = details
        normalized = atom_queries.parameters(tool, args)
        data = atom_queries.temporal_data_core(ledger, tool, normalized)
    if details and tool not in ("file", "agent", "search"):
        data = {**data, "details": True,
                "details_effect": "此查询没有折叠的关系注释；正文及分页不因details改变，原始记录用expand展开。"}
    if tool == "file" and data.get("schema") != "migloop-time-atom/1":
        from . import body_sources
        data = {**data, "body_sources": body_sources.navigation(ledger, current["key"], current["at"],
            current["since_ts"], show=args.get("offset", 0) == 0)}
    return {**data, "scope": current}


def _delivery(data):
    records = []
    def visit(value):
        if not isinstance(value, dict):
            return
        ref = value.get("ref")
        if isinstance(ref, str) and ref.startswith(("raw:", "#")) and any(k in value for k in ("text", "preview", "diff")):
            records.append({"ref": ref, "extent": ("derived_diff" if "diff" in value else "derived_line" if "line" in value and ref.startswith("#")
                                                    else "raw_field_segment" if "text" in value and value.get("pointer") is not None
                                                    else "raw_segment" if "text" in value else "preview_or_pointer"),
                            "pointer": value.get("pointer"),
                            "offset": value.get("offset"), "chars": len(value.get("text", value.get("preview", value.get("diff", "")))),
                            "next_offset": value.get("next_offset")})
        for name in ("rows", "items", "records", "requests", "results", "pointers", "events"):
            for item in value.get(name, []) if isinstance(value.get(name), list) else []:
                visit(item)
        for name in ("unclassified_related", "undated", "unknown_records", "native_io"):
            if isinstance(value.get(name), dict):
                visit(value[name])
        if value.get("schema") == "migloop-time-atom/1":
            for section in value.get("sections", {}).values():
                visit(section)
    visit(data)
    return {"records": records, "scope": data.get("scope"), "data_schema": data.get("schema"),
            "semantic_checked": False, "navigation_is_relation": False}


@raw_events.reuse_scans
def batch(ledger, requests, max_chars=100000):
    from . import delivery_budget
    if not isinstance(requests, list) or not 1 <= len(requests) <= 24:
        raise ValueError("requests需要1–24项；批量不使用隐式当前节点")
    if type(max_chars) is not int or not 1000 <= max_chars <= 400000:
        raise ValueError("max_chars数据正文预算为1000–400000；查询/凭据封装另计")
    items, selected = [], {}
    for i, request in enumerate(requests):
        item = {"item_index": i, "tool": request.get("tool") if isinstance(request, dict) else None,
                "args": request.get("args", {}) if isinstance(request, dict) else {}}
        try:
            if not isinstance(request, dict) or set(request) - {"tool", "args", "scope"} or not isinstance(item["args"], dict):
                raise ValueError("每项必须为{tool,args,scope?}")
            args = dict(item["args"])
            if "scope" in request:
                if "scope" in args and args["scope"] != request["scope"]:
                    raise ValueError("重复scope冲突")
                args["scope"] = request["scope"]
            data = query(ledger, item["tool"], args)
            item["scope"] = data["scope"]
            selected[i] = data
        except (ValueError, TypeError, KeyError, OSError, UnicodeError) as exc:
            item.update(status="error", error=str(exc), delivery={"records": []})
        items.append(item)
    # First give every successful query a share; then return unused capacity.
    # Query order is not importance, and an early large result must not starve
    # every later source. All receipts describe this projected body only.
    fitted, used = {}, 0
    positions = list(selected)
    for ordinal, i in enumerate(positions):
        result = delivery_budget.fit(selected[i], (max_chars - used) // (len(positions) - ordinal))
        fitted[i] = result
        used += result["data_chars"]
    for i in positions:
        if used >= max_chars:
            break
        old = fitted[i]
        if old["budget_adjusted"]:
            result = delivery_budget.fit(selected[i], old["data_chars"] + max_chars - used)
            if result["data_chars"] >= old["data_chars"]:
                fitted[i] = result
                used += result["data_chars"] - old["data_chars"]
    for i, result in fitted.items():
        item = items[i]
        item.update(status=result["status"], budget_adjusted=result["budget_adjusted"],
                    original_data_chars=result["original_data_chars"], continuations=result["continuations"])
        if result["data"] is not None:
            item.update(data=result["data"], delivery=_delivery(result["data"]))
        else:
            item.update(error="首个不可拆元数据超过交付预算；请用续取入口、较小limit或details=false。" + str(result["reason"] or ""),
                        delivery={"records": []})
    # Put failures ahead of large successful bodies. Partial expansions need
    # separate counts: an outer successful transport is not a successful read.
    summary = {key: sum(item["status"] == key for item in items) for key in ("ok", "error", "deferred")}
    summary["budget_adjusted"] = sum(bool(item.get("budget_adjusted")) for item in items)
    summary["withheld_records"] = sum(len(part.get("withheld", []))
        for item in items for part in item.get("data", {}).get("items", []))
    summary["empty_expansions"] = sum(not part.get("records")
        for item in items if item.get("data", {}).get("schema") == "migloop-evidence-expansion/1"
        for part in item["data"].get("items", []))
    attention = [{"item_index": item["item_index"], "tool": item["tool"], "status": item["status"],
                  "reason": item.get("error")} for item in items if item["status"] != "ok"]
    return {"schema": SCHEMA, "ledger": atoms.ledger_identity(ledger), "delivery_summary": summary,
            "attention": attention, "items": items,
            "data_chars": used, "max_chars": max_chars, "budget_scope": "serialized_data_only",
            "note": "逐项独立取证，不生成历史边。ok也可能部分交付：按next_offset/continuations续读；deferred/error无正文。max_chars计data，封装另计。"}


def render_batch(ledger, requests, max_chars=100000):
    data = batch(ledger, requests, max_chars)
    return render_batch_data(data, requests, max_chars)


def render_batch_data(data, requests, max_chars):
    """Render the same selected data; prefer lossless wire only if shorter.

    No model-visible aliases or hidden handle registry. Old JSON remains a
    valid transport and old receipts retain their original parsing algorithm.
    The codec limits are safety guards, not permission to drop evidence.
    """
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    receipt = {"schema": "migloop-investigation-receipt/1", "ledger": data["ledger"],
               "request_sha256": digest({"requests": requests, "max_chars": max_chars}), "body_sha256": digest(body)}
    original = body + MARKER + json.dumps(receipt, separators=(",", ":"))
    from . import batch_wire
    try:
        packed = batch_wire.pack(data, requests)
        wire_body = json.dumps(packed, ensure_ascii=False, separators=(",", ":"))
        wire_receipt = {"schema": WIRE_RECEIPT, "codec": batch_wire.SCHEMA, "ledger": data["ledger"],
                        "request_sha256": receipt["request_sha256"], "body_sha256": digest(wire_body),
                        "canonical_sha256": digest(data)}
        wire = wire_body + WIRE_MARKER + json.dumps(wire_receipt, separators=(",", ":"))
    except ValueError:
        return original  # Compression may decline; never truncate/coerce to fit it.
    return wire if len(wire) < len(original) else original


def render_query(ledger, tool, args):
    data = {**query(ledger, tool, args), "ledger": atoms.ledger_identity(ledger)}
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    receipt = {"schema": "migloop-investigation-receipt/1", "ledger": atoms.ledger_identity(ledger),
               "argument_normalization": "time-query/2",
               "tool": tool, "request_sha256": digest(_receipt_args(tool, args)), "body_sha256": digest(body)}
    return body + MARKER + json.dumps(receipt, separators=(",", ":"))


def batch_parameters(args):
    if set(args) - {"requests", "max_chars"}:
        raise ValueError("batch只接受requests/max_chars")
    requests = args.get("requests")
    if isinstance(requests, str):
        try:
            requests = json.loads(requests)
        except ValueError as exc:
            raise ValueError("requests必须是JSON数组") from exc
    value = args.get("max_chars", 100000)
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return {"requests": requests, "max_chars": value}


def _receipt_args(tool, supplied):
    args = {k: v for k, v in supplied.items() if k != "sid"}
    if tool == "batch":
        return batch_parameters(args)
    defaults = {
        "changes": {"at": "latest", "since_ts": None, "offset": 0, "limit": 40, "related_offset": 0, "related_limit": 8},
        "expand": {"offset": 0, "max_chars": 12000, "include_undated": False},
    }
    return {**defaults.get(tool, {}), **args}


def parse_receipt(tool, args, text):
    """Authenticate self-consistency before comparing the source ledger identity."""
    if WIRE_MARKER in text:
        return _parse_wire_receipt(tool, args, text)
    body, separator, tail = text.rpartition(MARKER)
    if not separator:
        return None
    try:
        receipt, data = json.loads(tail), json.loads(body)
        normalized = _receipt_args(tool, args)
        normalization = receipt.get("argument_normalization")
        if tool == "changes" and normalization is None:
            # Original receipts predate the optional remainder-page defaults.
            # Do not rewrite recorded requests or invalidate their old hashes.
            for key in ("related_offset", "related_limit"):
                if key not in args:
                    normalized.pop(key, None)
        valid = (receipt["schema"] == "migloop-investigation-receipt/1"
                 and normalization in (None, "time-query/2")
                 and receipt["ledger"] == data["ledger"]
                 and receipt["body_sha256"] == digest(body)
                 and receipt["request_sha256"] == digest(normalized)
                 and (tool == "batch" or receipt.get("tool") == tool))
        return {"receipt": receipt, "data": data} if valid else None
    except (ValueError, TypeError, KeyError):
        return None


def _parse_wire_receipt(tool, args, text):
    """Bind actual wire text before applying the pinned codec reconstruction."""
    from . import batch_wire
    if tool != "batch" or len(text) > batch_wire.DEFAULT_MAX_CHARS + 8192:
        return None
    body, separator, tail = text.rpartition(WIRE_MARKER)
    if not separator or len(tail) > 8192:
        return None
    try:
        receipt = json.loads(tail, object_pairs_hook=batch_wire._unique_object,
                             parse_constant=batch_wire._reject_constant)
        if (type(receipt) is not dict or set(receipt) != {
                "schema", "codec", "ledger", "request_sha256", "body_sha256", "canonical_sha256"}
                or receipt["schema"] != WIRE_RECEIPT or receipt["codec"] != batch_wire.SCHEMA
                or receipt["body_sha256"] != digest(body)
                or receipt["request_sha256"] != digest(_receipt_args(tool, args))):
            return None
        data = batch_wire.unpack(body, batch_parameters({k: v for k, v in args.items() if k != "sid"})["requests"])
        if receipt["ledger"] != data["ledger"] or receipt["canonical_sha256"] != digest(data):
            return None
        return {"receipt": receipt, "data": data}
    except (ValueError, TypeError, KeyError, RecursionError):
        return None


def project_trace(ledger, calls):
    from . import time_receipts
    from .probe import _unwrap_result
    rows = []
    legacy = {r["step"]: r for r in time_receipts.project(ledger, calls)["steps"]}
    for number, call in enumerate(calls, 1):
        args = call.get("input") or {}
        tool = call.get("tool")
        text = _unwrap_result(call.get("text") or "")
        row = {"step": number, "tool": tool, "args": args, "status": "unverified_response",
               "scope": None, "delivery": {"records": []}, "items": [],
               "call_id": call.get("call_id"), "use_line": call.get("use_line"), "result_line": call.get("result_line")}
        provenance = call.get("provenance") or {}
        recorded = bool(call.get("has_result") and not call.get("is_error") and not call.get("delivery_truncated")
                        and not provenance.get("origin_unverified") and provenance.get("complete_pair") is not False)
        if MARKER in text or WIRE_MARKER in text:
            saved = parse_receipt(tool, args, text)
            if recorded and saved and saved["receipt"]["ledger"] == atoms.ledger_identity(ledger):
                data = saved["data"]
                row.update(status="recorded_response")
                if tool == "batch":
                    row["items"] = [{k: v for k, v in item.items() if k != "data"} for item in data["items"]]
                else:
                    row.update(scope=data.get("scope"), delivery=_delivery(data))
        elif number in legacy:
            saved = legacy[number]
            row.update(status=saved["status"], scope=saved.get("node"),
                       delivery={"records": [{"ref": r, "extent": "recorded_pointer"} for r in saved["records"]]})
        rows.append(row)
    return {"schema": "migloop-investigation-trace/1", "steps": rows, "edges": [],
            "note": "真实录制调用；事后文稿不增加访问。相邻查询不是历史读写关系。"}
