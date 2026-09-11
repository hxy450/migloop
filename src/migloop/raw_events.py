"""Native call inventory over registered raw sources, independent of Actions.

Pairing is source-local and uses explicit native IDs, never proximity or a
script's nested IDs. ``patch_apply_end`` is an independent runtime observation.
Payloads remain accessible through raw refs and JSON pointers; inventory output
does not copy potentially enormous commands, patches or returns.

``complete`` describes reading/classifying the registered sources, not complete
pool discovery, script-effect recovery, successful execution or causal truth.
Native source indexes have a bounded LRU cache, keyed by source signatures and
the registered source/owner mapping. Oversized indexes are served but not cached.
Each access checks signatures; each raw ref authenticates decoded line content.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import asyncio
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from functools import wraps
from threading import RLock, get_ident
from typing import Any

from . import atoms, transcript_store as store

SCHEMA = "migloop-raw-events/1"
_CACHE_BUDGET = 32 * 1024 * 1024
_MAX_SOURCE_CACHE_BYTES = 8 * 1024 * 1024
_CACHE: OrderedDict[str, tuple[Any, tuple[int, int], dict[str, Any], int]] = OrderedDict()
_CACHE_LOCK = RLock()
_CACHE_BYTES = 0
# Request-local source indexes use admission without LRU eviction, so repeated
# full scans cannot evict every useful entry in the same request. This budget
# is released at request exit and is not a persistent increase of the LRU.
_REQUEST_SCAN_BUDGET = 128 * 1024 * 1024
_SCAN_REUSE: ContextVar[dict | None] = ContextVar("migloop_native_scan_reuse", default=None)


def _execution_owner():
    try:
        task = asyncio.current_task()
    except RuntimeError:  # Ordinary synchronous/worker-thread queries.
        task = None
    return get_ident(), id(task) if task is not None else None


def _request_state():
    state = _SCAN_REUSE.get()
    return state if state and state.get("owner") == _execution_owner() else None


@contextmanager
def scan_scope():
    """Reuse source parsing within one execution; never freeze file state.

    Registry ownership and file signatures are still checked on every access.
    Native events, target/time projections and ledger relations are not cached.
    Nested calls in the same task/thread share; inherited contexts in another
    task/thread cannot access or refill their parent's state after it exits.
    """
    if _request_state() is not None:
        yield
        return
    state = {"owner": _execution_owner(), "registry_key": None, "indexes": {},
             "skipped": {}, "retained_bytes": 0}
    token = _SCAN_REUSE.set(state)
    try:
        yield
    finally:
        state.clear()
        _SCAN_REUSE.reset(token)


def reuse_scans(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with scan_scope():
            return function(*args, **kwargs)
    return wrapped


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


def _access(record: store.Record, pointer: str, value: Any) -> dict[str, Any]:
    return {"ref": record.ref, "pointer": pointer, "chars": len(store.readable(value))}


def _failed(payload: dict[str, Any]) -> bool:
    # Only structured status, never a quoted "failed" or "exit code" in text.
    candidates = [payload]
    if isinstance(payload.get("output"), dict):
        candidates.append(payload["output"])
    return any(p.get("is_error") is True or p.get("success") is False or
               (type(p.get("exit_code")) is int and p["exit_code"] != 0)
               for p in candidates)


@dataclass
class _Part:
    record: store.Record
    block: int | None
    pointer: str
    payload: dict[str, Any]
    direction: str
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)

    def address(self) -> dict[str, Any]:
        return {**self.record.address(), "block": self.block, "pointer": self.pointer,
                "fields": {name: dict(value) for name, value in self.fields.items()},
                "failed": _failed(self.payload) if self.direction != "use" else None}


@dataclass
class _Event:
    source: str
    agents: set[str]
    protocol: str
    call_id: str | None
    parts: list[_Part] = field(default_factory=list)
    addressable: bool = True


def _native(record: store.Record) -> tuple[list[tuple[str, str | None, _Part]], list[str]]:
    """Recognize native envelopes, not JSON/text nested inside their payloads."""
    row = record.value
    if not isinstance(row, dict):
        return [], [""]
    found, other = [], []
    message = row.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), list):
        for index, block in enumerate(message["content"]):
            pointer = f"/message/content/{index}"
            if not isinstance(block, dict) or block.get("type") not in ("tool_use", "tool_result"):
                other.append(pointer)
                continue
            direction = "use" if block["type"] == "tool_use" else "result"
            identity = block.get("id" if direction == "use" else "tool_use_id")
            identity = identity if isinstance(identity, str) and identity else None
            part = _Part(record, index, pointer, block, direction)
            name = "input" if direction == "use" else "content"
            if name in block:
                part.fields["input" if direction == "use" else "output"] = _access(
                    record, pointer + "/" + name, block[name])
            found.append(("cc", identity, part))
    payload = row.get("payload")
    if row.get("type") == "response_item" and isinstance(payload, dict):
        kind = payload.get("type")
        if kind in ("function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output"):
            direction = "result" if kind.endswith("_output") else "use"
            identity = payload.get("call_id")
            identity = identity if isinstance(identity, str) and identity else None
            part = _Part(record, None, "/payload", payload, direction)
            name = ("arguments" if "arguments" in payload else "input") if direction == "use" else "output"
            if name in payload:
                part.fields["input" if direction == "use" else "output"] = _access(
                    record, "/payload/" + name, payload[name])
            found.append(("codex", identity, part))
    if row.get("type") == "event_msg" and isinstance(payload, dict) and payload.get("type") == "patch_apply_end":
        identity = payload.get("call_id")
        identity = identity if isinstance(identity, str) and identity else None
        part = _Part(record, None, "/payload", payload, "independent")
        for name in ("stdout", "stderr", "changes"):
            if name in payload:
                part.fields[name] = _access(record, "/payload/" + name, payload[name])
        found.append(("codex_patch", identity, part))
    return found, other or ([""] if not found else [])


def _signature(path: str) -> tuple[int, int]:
    stat = os.stat(path)
    return stat.st_mtime_ns, stat.st_size


def _retained_size(value: Any, ceiling: int) -> int:
    """Conservative object-graph accounting, stopping once caching is excluded.

    Includes decoded dictionaries, raw strings and dataclass storage. Shared
    objects are counted once within an entry, but separately across entries.
    This bounds retained Python objects, not allocator/process RSS.
    """
    pending, seen, total = [value], set(), 256
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        total += sys.getsizeof(current)
        if total > ceiling:
            return total
        if isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset)):
            pending.extend(current)
        elif isinstance(current, (_Part, _Event, store.Record, store.SourceSpec)):
            pending.append(vars(current))
    return total


def _evict(path: str) -> None:
    global _CACHE_BYTES
    previous = _CACHE.pop(path, None)
    if previous is not None:
        _CACHE_BYTES -= previous[3]


def _drop_request_entry(state, path):
    for name in ("indexes", "skipped"):
        previous = state[name].pop(path, None)
        if previous is not None:
            state["retained_bytes"] -= previous[-1]


def _source_index(path: str, registry_key: str, source: store.SourceSpec | None = None) -> tuple[dict[str, Any], tuple[int, int], str]:
    state = _request_state()
    if state is None:
        return _source_index_global(path, registry_key, source)
    if state["registry_key"] != registry_key:
        state["indexes"].clear()
        state["skipped"].clear()
        state.update(registry_key=registry_key, retained_bytes=0)
    try:
        before = _signature(path)
    except OSError:
        _drop_request_entry(state, path)
        raise
    held = state["indexes"].get(path)
    if held is not None:
        if held[0] == before and held[2] == source and _signature(path) == before:
            return held[1], before, "request_hit"
        _drop_request_entry(state, path)
    skipped = state["skipped"].get(path)
    if skipped is not None and skipped[0] != before:
        _drop_request_entry(state, path)
        skipped = None
    index, signature, cache_status = _source_index_global(path, registry_key, source)
    if skipped is None and _signature(path) == signature:
        remaining = max(0, _REQUEST_SCAN_BUDGET - state["retained_bytes"])
        # Global admission has already weighed this immutable index, including
        # a wrapper that contains every object retained by the request entry.
        # A known lower bound is enough to reject admission; don't traverse all
        # decoded bodies again merely to decide whether to keep the same data.
        size, measured_to = index.get("_retained_bytes"), index.get("_weighed_to")
        if (type(size) is not int or type(measured_to) is not int
                or size > measured_to and remaining > measured_to):
            size = _retained_size((path, signature, index, source), remaining)
        if size <= remaining:
            state["indexes"][path] = (signature, index, source, size)
            state["retained_bytes"] += size
        else:
            # Remember an uncacheable stable source without repeatedly walking
            # its entire object graph. Guard bookkeeping is itself budgeted.
            guard_size = _retained_size((path, signature), remaining)
            if guard_size <= remaining:
                state["skipped"][path] = (signature, guard_size)
                state["retained_bytes"] += guard_size
    return index, signature, cache_status


def _source_index_global(path: str, registry_key: str, source: store.SourceSpec | None = None) -> tuple[dict[str, Any], tuple[int, int], str]:
    """Cached data is private and treated as immutable after construction."""
    global _CACHE_BYTES
    registry_key = (registry_key, source)
    before = _signature(path)
    with _CACHE_LOCK:
        while _CACHE and _CACHE_BYTES > _CACHE_BUDGET:
            _evict(next(iter(_CACHE)))
        cached = _CACHE.get(path)
        if cached is not None and cached[:2] == (registry_key, before):
            _CACHE.move_to_end(path)
            index = cached[2]
        else:
            _evict(path)
            index = None
    if index is not None:
        if _signature(path) != before:
            with _CACHE_LOCK:
                _evict(path)
            raise ValueError("source changed during inventory; retry with a stable source")
        return index, before, "hit"

    native, unknown, gaps = [], [], []
    for record in store.records(path, source=source):
        # A saved attachment can quote native-looking envelopes. It is not a
        # tool execution, and its own JSON timestamp is not arrival evidence.
        recognized, other = ([], [""]) if source and source.timestamp_policy == "unknown" else _native(record)
        native.extend(recognized)
        if record.malformed:
            gaps.append({**record.address(), "source_path": path, "error": "malformed JSON record"})
        if other:
            unknown.append({**record.address(), "fields": [] if record.textual else other, "_record": record})
    if _signature(path) != before:
        raise ValueError("source changed during inventory; retry with a stable source")
    # Private, not part of any returned inventory or evidence. The accounting
    # walker includes these slots before their values are installed; its fixed
    # overhead covers the two newly allocated small integer values.
    index = {"native": native, "unknown": unknown, "gaps": gaps,
             "_retained_bytes": None, "_weighed_to": None}
    ceiling = min(_CACHE_BUDGET, _MAX_SOURCE_CACHE_BYTES)
    state = _request_state()
    request_remaining = max(0, _REQUEST_SCAN_BUDGET - state["retained_bytes"]) if state else 0
    measured_to = max(ceiling, request_remaining)
    size = _retained_size((registry_key, before, path, index), measured_to)
    index.update(_retained_bytes=size, _weighed_to=measured_to)
    if size > ceiling:
        return index, before, "oversize_not_cached"
    with _CACHE_LOCK:
        # Another concurrent reader may have installed the same source. Replace
        # it under the lock; a future access still rechecks its exact signature.
        _evict(path)
        while _CACHE and _CACHE_BYTES + size > _CACHE_BUDGET:
            _evict(next(iter(_CACHE)))
        _CACHE[path] = (registry_key, before, index, size)
        _CACHE_BYTES += size
    return index, before, "miss"


def _scan(ledger: atoms.Ledger, agent: str | None = None) -> dict[str, Any]:
    return _scan_uncached(ledger, agent)


def _scan_uncached(ledger: atoms.Ledger, agent: str | None = None) -> dict[str, Any]:
    all_sources = store.sources(ledger)
    source_specs = {path: store.source_spec(ledger, path) for path in all_sources}
    # Derive the selected registry from the same owner snapshot. A second
    # lookup could admit a new source absent from source_keys below, producing
    # a KeyError rather than the explicit end-of-scan registry retry.
    registry = ({path: {agent} for path, owners in all_sources.items() if agent in owners}
                if agent is not None else all_sources)
    groups: dict[tuple[Any, ...], _Event] = {}
    unknown, gaps, signatures = [], [], {}
    source_keys: dict[str, int] = {}
    registry_key = _digest([(path, sorted(owners), source_specs[path].logical_name, source_specs[path].timestamp_policy)
                            for path, owners in sorted(all_sources.items())])
    cache_counts = {"hit": 0, "miss": 0, "oversize_not_cached": 0, "request_hit": 0}
    for path in all_sources:
        key = store.source_key(path, source_specs[path])
        source_keys[key] = source_keys.get(key, 0) + 1
    for path, agents in sorted(registry.items()):
        try:
            index, signature, cache_status = _source_index(path, registry_key, source_specs[path])
            signatures[path] = list(signature)
            cache_counts[cache_status] += 1
        except (OSError, UnicodeError, ValueError) as exc:
            with _CACHE_LOCK:
                _evict(path)
            gaps.append({"source": os.path.basename(path), "source_path": path, "error": str(exc)})
            continue
        ambiguous_source = source_keys[store.source_key(path, source_specs[path])] > 1
        if ambiguous_source:
            gaps.append({"source": os.path.basename(path), "source_path": path,
                         "error": "duplicate source identity: raw references are ambiguous"})
        gaps.extend(dict(gap) for gap in index["gaps"])
        unknown.extend({**row, "source_path": path, "agents": sorted(agents),
                        "reference_status": "ambiguous_source" if ambiguous_source else "addressable"}
                       for row in index["unknown"])
        for protocol, identity, part in index["native"]:
            # Missing IDs and independent patch observations never join a call.
            discriminator = ((part.record.line, part.block) if identity is None or protocol == "codex_patch" else None)
            key = (path, protocol, identity, discriminator)
            event = groups.setdefault(key, _Event(path, agents, protocol, identity))
            event.addressable = not ambiguous_source
            event.parts.append(part)
    # A source already visited may change while another source is decoded. Do
    # not deliver a mixed-signature inventory for that changed source.
    changed = set()
    for path, signature in signatures.items():
        try:
            if list(_signature(path)) == signature:
                continue
        except OSError:
            pass
        changed.add(path)
        with _CACHE_LOCK:
            _evict(path)
        gaps.append({"source": os.path.basename(path), "source_path": path,
                     "error": "source changed during inventory; retry with a stable source"})
    if changed:
        groups = {key: event for key, event in groups.items() if event.source not in changed}
        unknown = [row for row in unknown if row["source_path"] not in changed]
    if (store.sources(ledger) != all_sources or
            {path: store.source_spec(ledger, path) for path in all_sources} != source_specs):
        raise ValueError("registered source/owner mapping changed during native inventory; retry with a stable registry")
    return {"events": list(groups.values()), "unknown": unknown, "gaps": gaps,
            "source_count": len(registry), "source_signatures": signatures,
            "cache": {**cache_counts, "budget_bytes": _CACHE_BUDGET,
                      "max_source_bytes": _MAX_SOURCE_CACHE_BYTES,
                      "request_budget_bytes": _REQUEST_SCAN_BUDGET,
                      "note": "bounded native source indexes; optional request-local admission does not evict earlier entries and is released on exit; oversized sources are still served"}}


def _project(event: _Event, parts: list[_Part], *, scoped: bool = False) -> dict[str, Any]:
    uses = [p for p in parts if p.direction == "use"]
    results = [p for p in parts if p.direction != "use"]
    anomalies = []
    if event.call_id is None:
        anomalies.append("missing_call_id")
    if len(uses) > 1:
        anomalies.append("duplicate_use")
    if len(results) > 1:
        anomalies.append("duplicate_result")
    if len(uses) == len(results) == 1:
        use, result = uses[0], results[0]
        if ((result.record.line, result.block or 0) <= (use.record.line, use.block or 0) or
                (use.record.ts is not None and result.record.ts is not None and result.record.ts < use.record.ts)):
            anomalies.append("out_of_order")
    if event.protocol == "codex_patch":
        status = "failed" if any(_failed(p.payload) for p in results) else "independent"
    elif event.call_id is None:
        status = "missing_call_id"
    elif len(uses) > 1 or len(results) > 1:
        status = "ambiguous"
    elif "out_of_order" in anomalies:
        status = "out_of_order"
    elif not uses:
        # A range projection cannot prove the request was absent from all history.
        status = "result_only" if scoped else "orphan_result"
    elif not results:
        status = "pending_or_unknown" if scoped else "pending"
    else:
        status = "failed" if _failed(results[0].payload) else "returned"
    first = min(event.parts, key=lambda p: (p.record.line, p.block or 0))
    identity = [first.record.ref.split(":")[1], event.protocol, event.call_id]
    if event.call_id is None or event.protocol == "codex_patch":
        identity += [first.record.ref, first.block]
    # Portable source identity survives moving a frozen pool and later appends.
    # Duplicate basenames deliberately collide and are marked ambiguous, rather
    # than gaining apparently unique identities from machine-local paths.
    # Raw refs, not this event handle, authenticate payload bytes.
    return {"id": "native:" + _digest(identity), "source": os.path.basename(event.source),
            "source_path": event.source, "agents": sorted(event.agents), "protocol": event.protocol,
            "call_id": event.call_id, "tool": (deepcopy(uses[0].payload.get("name")) if len(uses) == 1 else
                                                  "patch_apply_end" if event.protocol == "codex_patch" else None),
            "reference_status": "addressable" if event.addressable else "ambiguous_source",
            "id_unique_in_registry": event.addressable,
            "use": uses[0].address() if len(uses) == 1 else None,
            "uses": [p.address() for p in uses], "results": [p.address() for p in results],
            "status": status, "anomalies": anomalies, "relation": None,
            "note": "native identity/pairing only; returned is not execution or script-effect proof"}


def _unknown_public(row: dict[str, Any]) -> dict[str, Any]:
    return deepcopy({key: value for key, value in row.items() if not key.startswith("_")})


def _unknown_payload(row: dict[str, Any]) -> Any:
    record = row["_record"]
    if record.malformed or record.textual:
        return record.raw
    values = []
    for pointer in row["fields"]:
        value = record.value
        for token in pointer.split("/")[1:]:
            token = token.replace("~1", "/").replace("~0", "~")
            value = value[int(token)] if isinstance(value, list) else value[token]
        values.append(value)
    return values


def inventory(ledger: atoms.Ledger) -> dict[str, Any]:
    """Inventory all registered source records without consulting parsed Actions."""
    data = _scan(ledger)
    return {"schema": SCHEMA, "events": [_project(e, e.parts) for e in data["events"]],
            "gaps": data["gaps"], "unknown_records": [_unknown_public(r) for r in data["unknown"]],
            "source_count": data["source_count"], "source_signatures": data["source_signatures"],
            "cache": data["cache"],
            "complete": bool(data["source_count"]) and not data["gaps"],
            "scope": "registered_raw_sources", "causal_complete": False,
            "note": "unknown_records include ordinary messages and unclassified records/blocks; "
                    "payloads are opened by raw ref plus JSON pointer; no history is executed"}


def query(ledger: atoms.Ledger, at: str, since_ts: str | None = None, path: str | None = None,
          agent: str | None = None, offset: int = 0, limit: int = 40,
          view: str = "events") -> dict[str, Any]:
    """Select native *record* times inclusively; never leak later return status.

    Parts outside the window are not delivered. A result with its request outside
    the window is ``result_only``, not proof of an orphan. Unknown-time parts are
    quarantined as locator-only entries. Path matching is lexical, not a write
    assertion, and only inspects parts actually inside the selected time window.
    """
    from .temporal import Window, _page
    window = Window.parse(at, since_ts)
    _page([], offset, limit)
    if view not in ("events", "sources", "bodies"):
        raise ValueError("view 必须是 events/sources/bodies")
    if path is not None and (not isinstance(path, str) or not path):
        raise ValueError("path must be a nonempty string")
    owner = atoms.resolve_agent(ledger, agent) if agent is not None else None
    if agent is not None and owner is None:
        raise ValueError("unknown or ambiguous agent")
    if path is not None and agent is not None:
        raise ValueError("path and agent scopes are mutually exclusive")
    if view == "bodies":
        if path is None:
            raise ValueError("view=bodies 需要path文件范围")
        from . import body_sources
        return body_sources.query(ledger, path, at, since_ts, offset, limit)
    normalized = path.replace("\\", "/").casefold() if path else None
    basename = normalized.rsplit("/", 1)[-1] if normalized else None

    def matches(payload: Any) -> bool:
        if normalized is None:
            return True
        text = store.readable(payload).replace("\\", "/").casefold()
        return normalized in text or bool(basename and basename in text)

    data = _scan(ledger, owner.id if owner else None)
    source_args = {"at": window.at, "since_ts": window.since, "view": "sources", "offset": 0, "limit": 40}
    if path is not None:
        source_args["path"] = path
    if owner is not None:
        source_args["agent"] = owner.id
    source_query = {"tool": "events", "args": source_args}
    signatures = {"count": len(data["source_signatures"]),
                  "digest": _digest(sorted(data["source_signatures"].items())),
                  "observation": "current_registry_not_historical_cutoff",
                  "query": source_query,
                  "note": "签名为本次registry的mtime_ns/size，不是历史截点已知来源；不证明文件内容或历史因果。"}
    if view == "sources":
        source_rows = [{"source_path": source, "signature": list(signature)}
                       for source, signature in sorted(data["source_signatures"].items())]
        source_page = _page(source_rows, offset, limit)
        request = {"tool": "events", "args": {**source_args, "offset": offset, "limit": limit}}
        return {"schema": "migloop-raw-event-query/1", "view": "sources", "events": [],
                "source_rows": source_page.pop("rows"), **source_page,
                "scope": {"at": window.at, "since_ts": window.since, "path": path,
                          "agent": owner.id if owner else None, "bounds": "inclusive"},
                "source_signatures": signatures, "source_count": data["source_count"],
                "gaps": data["gaps"], "cache": data["cache"],
                "complete": bool(data["source_count"]) and not data["gaps"], "causal_complete": False,
                "query": request,
                "next_query": {"tool": "events", "args": {**request["args"], "offset": source_page["next_offset"]}}
                              if source_page["next_offset"] is not None else None,
                "note": signatures["note"]}
    events, unknown, undated = [], [], []
    for event in data["events"]:
        if owner is not None and owner.id not in event.agents:
            continue
        visible = [p for p in event.parts if p.record.ts is not None and window.contains(p.record.ts)]
        unknown_time = [p for p in event.parts if p.record.ts is None]
        for part in unknown_time:
            if matches(part.payload):
                undated.append({**part.address(), "source_path": event.source, "agents": sorted(event.agents),
                                "kind": "native_part", "direction": part.direction})
        if not visible or not any(matches(p.payload) for p in visible):
            continue
        projected = _project(event, visible, scoped=True)
        projected["association"] = "lexical_mention_not_effect" if path else "native_record"
        projected["matched_parts"] = [p.address() for p in visible if matches(p.payload)] if path else []
        events.append(projected)
    for row in data["unknown"]:
        if owner is not None and owner.id not in row["agents"]:
            continue
        record = row["_record"]
        if not matches(_unknown_payload(row)):
            continue
        public = _unknown_public(row)
        if record.ts is None:
            undated.append({**public, "kind": "unclassified_record"})
        elif window.contains(record.ts):
            unknown.append(public)

    def order(event: dict[str, Any]) -> tuple[Any, ...]:
        parts = event["uses"] + event["results"]
        return min((p["ts"], event["source_path"], p["line"], p["block"] or 0) for p in parts)

    events.sort(key=order)
    unknown.sort(key=lambda r: (r["ts"], r["source_path"], r["line"]))
    page = _page(events, offset, limit)
    return {"schema": "migloop-raw-event-query/1", "view": "events", "events": page.pop("rows"), **page,
            "scope": {"at": window.at, "since_ts": window.since, "path": path,
                      "agent": owner.id if owner else None, "bounds": "inclusive",
                      "path_match": "full_path_or_basename_lexical" if path else None},
            "unknown_records": _page(unknown, offset, limit), "undated": _page(undated, offset, limit),
            "gaps": data["gaps"], "source_count": data["source_count"],
            "source_signatures": signatures,
            "cache": data["cache"],
            "complete": bool(data["source_count"]) and not data["gaps"],
            "causal_complete": False,
            "note": "native parts are filtered separately by recorded time; future results/status are hidden; "
                    "undated locators are not cutoff evidence; path mentions are not confirmed accesses"}
