"""Native historical body navigation, independent of reconstructed file state.

A Write request contains the proposed full body even if it failed. A Read
response is an observation, not a unique writer or proof of current disk state.
Only exact native targets are indexed here; code-host literals, shell effects,
and basename mentions remain accessible through the ordinary raw corpus.
"""
from __future__ import annotations

import json
import ntpath
import posixpath
from collections import Counter
from copy import deepcopy
from typing import Any

from . import raw_events, temporal


def _target(supplied, canonical):
    if not isinstance(supplied, str) or not supplied:
        return False
    # Query hints may resolve by suffix, native targets must NOT. In particular
    # /A.ets is a different absolute file from /project/A.ets. A relative target
    # without a recorded working-directory binding is not guessed here.
    source = posixpath.normpath(supplied.replace("\\", "/"))
    target = posixpath.normpath(canonical.replace("\\", "/"))
    source_absolute = source.startswith("/") or bool(ntpath.splitdrive(source)[0] and ntpath.isabs(source))
    target_absolute = target.startswith("/") or bool(ntpath.splitdrive(target)[0] and ntpath.isabs(target))
    return source_absolute and target_absolute and source == target


def _read_field(part, canonical):
    """Use structured Read text only when its outer envelope has one result.

    Multiple tool-result blocks cannot borrow one another's toolUseResult. The
    native block is still expandable, but its extent then remains unknown.
    """
    row = part.record.value
    blocks = row.get("message", {}).get("content", [])
    result_count = sum(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks) if isinstance(blocks, list) else 0
    response = row.get("toolUseResult")
    file = response.get("file") if isinstance(response, dict) else None
    if (result_count == 1 and isinstance(file, dict) and
            _target(file.get("filePath"), canonical)):
        key = "content" if isinstance(file.get("content"), str) else "text"
        if isinstance(file.get(key), str):
            full = (type(file.get("startLine")) is int and file["startLine"] == 1
                    and type(file.get("numLines")) is int and type(file.get("totalLines")) is int
                    and file["numLines"] == file["totalLines"] >= 0
                    and not response.get("truncated") and not file.get("truncated"))
            return "/toolUseResult/file/" + key, file[key], "reported_full_read" if full else "partial_or_unknown_read"
    content = part.payload.get("content")
    return part.pointer + "/content", content, "unknown_read_extent"


def _collect(ledger, path, at, since_ts=None):
    window = temporal.Window.parse(at, since_ts)
    canonical = temporal.resolve_file(ledger, path)
    # This is deliberately not replay/current_content/snapshot_ref.
    native = raw_events._scan(ledger)
    scope = {"kind": "file", "key": canonical, "at": window.at, "since_ts": window.since}
    rows, undated = [], 0
    for event in native["events"]:
        if event.protocol != "cc":
            continue
        known = [p for p in event.parts if p.record.ts and window.ended(p.record.ts)]
        undated_parts = [p for p in event.parts if p.record.ts is None]
        uses = [p for p in known if p.direction == "use"]
        projected = raw_events._project(event, known, scoped=True) if known else None
        relevant = any(p.direction == "use" and p.payload.get("name") in ("Read", "Write")
                       and isinstance(p.payload.get("input"), dict)
                       and _target(p.payload["input"].get("file_path"), canonical) for p in event.parts)
        if relevant:
            undated += len(undated_parts)
        if projected is not None and undated_parts:
            projected = {**projected, "status": "ambiguous_unknown_time",
                         "anomalies": [*projected["anomalies"], "undated_native_part"]}
        if projected is not None and (not event.call_id or not event.call_id.strip()):
            projected = {**projected, "status": "ambiguous_missing_call_id",
                         "anomalies": [*projected["anomalies"], "missing_nonblank_call_id"]}
        # Original Write bodies can be read despite duplicate invocation IDs;
        # duplication invalidates execution attribution, not the recorded text.
        for part in event.parts:
            tool = part.payload.get("name") if part.direction == "use" else None
            request = part.payload.get("input")
            if tool != "Write" or not isinstance(request, dict) or not _target(request.get("file_path"), canonical):
                continue
            if not isinstance(request.get("content"), str):
                continue
            if part.record.ts is not None and window.contains(part.record.ts):
                rows.append(_entry(event, projected, part, part.pointer + "/input/content",
                                   request["content"], "write_request", "complete_requested_body", scope))
        # Read target association is allowed only with an unambiguous earlier
        # native request. A later/future request never locates an earlier result.
        if (len(uses) != 1 or not event.call_id or not event.call_id.strip() or not event.addressable or projected is None
                or undated_parts
                or any(a in projected["anomalies"] for a in ("duplicate_use", "duplicate_result", "out_of_order"))):
            continue
        use = uses[0]
        request = use.payload.get("input")
        if use.payload.get("name") != "Read" or not isinstance(request, dict) or not _target(request.get("file_path"), canonical):
            continue
        for part in event.parts:
            if part.direction != "result" or "content" not in part.payload:
                continue
            if part.record.ts is None:
                continue
            if not window.contains(part.record.ts) or part.record.ts < use.record.ts:
                continue
            pointer, value, extent = _read_field(part, canonical)
            if raw_events._failed(part.payload):
                extent = "failed_read_response_not_file_content"
            rows.append(_entry(event, projected, part, pointer, value, "read_response", extent, scope))
    rows.sort(key=lambda r: (r["record_ts"], r["source"], r["line"], r["pointer"]))
    return rows, undated, native, scope


def query(ledger, path: str, at: str, since_ts: str | None = None,
          offset: int = 0, limit: int = 40) -> dict[str, Any]:
    temporal._page([], offset, limit)
    rows, undated, native, scope = _collect(ledger, path, at, since_ts)
    page = temporal._page(rows, offset, limit)
    def next_query(start):
        return {"tool": "events", "args": {"view": "bodies", "offset": start, "limit": limit}, "scope": deepcopy(scope)}
    return {"schema": "migloop-raw-event-query/1", "view": "bodies", "scope": scope,
            "events": page.pop("rows"), **page, "kind_counts": dict(Counter(row["kind"] for row in rows)),
            "unknown_time_count": undated, "unknown_time_count_unit": "native_parts",
            "source_count": native["source_count"], "gaps": deepcopy(native["gaps"]),
            "query": next_query(offset), "next_query": next_query(page["next_offset"]) if page["next_offset"] is not None else None,
            "current_state_certified": False, "causal_complete": False,
            "note": "原生Write请求正文/Read返回入口，不受当前状态known影响。请求全文不证明写入成功；Read只是观察。"
                    "本导航不涵盖shell/脚本/所有原生格式，零项不代表没有历史正文；仍可搜全量转录。"}


def _entry(event, projected, part, pointer, value, kind, extent, scope):
    # Match investigation._record's JSON-Pointer representation and cursor.
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return {"kind": kind, "ref": part.record.ref, "pointer": pointer, "source": part.record.address()["source"],
            "line": part.record.line, "record_ts": part.record.ts, "chars": len(text), "body_extent": extent,
            "representation": "decoded_string" if isinstance(value, str) else "json_value",
            "call_id": event.call_id, "call_state": projected["status"] if projected else "unknown",
            "anomalies": deepcopy(projected["anomalies"]) if projected else [],
            "source_agents": sorted(event.agents), "author_certified": False, "current_state_certified": False,
            "reference_status": "addressable" if event.addressable else "ambiguous_source",
            "query": {"tool": "expand", "scope": deepcopy(scope),
                      "args": {"refs": [{"ref": part.record.ref, "pointer": pointer}]}}
                     if event.addressable else None}


def navigation(ledger, path, at, since_ts=None, *, show=True):
    data = query(ledger, path, at, since_ts, limit=2)
    page = {key: deepcopy(data[key]) for key in ("total", "kind_counts", "unknown_time_count", "source_count", "gaps", "note")}
    page["entries"] = data["events"] if show else []
    page["remaining"] = data["total"] - len(page["entries"])
    page["query"] = {"tool": "events", "scope": deepcopy(data["scope"]), "args": {"view": "bodies", "limit": 40}}
    page["current_state_certified"] = False
    if data["scope"]["since_ts"] is not None:
        # Project again at the earlier cutoff. A request's later receipt must
        # not change its status in this independent pre-window navigation.
        rows, undated, native, prior_scope = _collect(ledger, path, data["scope"]["since_ts"])
        entries = []
        for kind in ("write_request", "read_response"):
            candidates = [row for row in rows if row["kind"] == kind]
            if candidates and show:
                latest = candidates[-1]
                ties = sum(row["record_ts"] == latest["record_ts"] for row in candidates)
                entries.append({**deepcopy(latest), "timestamp_tie_count": ties,
                                "selection_is_unique": ties == 1})
        page["before_window"] = {
            "scope": prior_scope, "total": len(rows), "remaining": len(rows) - len(entries),
            "entries": entries, "kind_counts": dict(Counter(row["kind"] for row in rows)),
            "unknown_time_count": undated, "source_count": native["source_count"],
            "gaps": deepcopy(native["gaps"]),
            "query": {"tool": "events", "args": {"view": "bodies", "limit": 40}, "scope": deepcopy(prior_scope)},
            "selection": "latest_per_kind_at_or_before_window_start",
            "navigation_is_relation": False, "current_state_certified": False,
            "note": "独立的起点及之前正文导航，正文尚未交付；最多各取一个最新Write请求/Read返回。"
                    "同刻多条只取稳定排序代表，selection_is_unique不是作者或磁盘状态认证。"
                    "失败请求仍是请求，Read仍是观察；全部并列/更早入口沿query展开。"
                    "本导航不涵盖shell/脚本/所有原生格式，零项不代表此前没有写入或正文。"}
    return page


def admits_record(ledger, scope, ref):
    """An explicit native Read target can locate its filename-free response.

    This admission never supplies the request's earlier content or a later
    result, nor does it promote a mention/candidate into a historical writer.
    """
    rows, _, _, _ = _collect(ledger, scope["key"], scope["at"], scope.get("since_ts"))
    return any(row["ref"] == ref for row in rows)
