"""Versioned, lossless removal of redundant batch *outer* fields.

No query, truncation, alias state or receipt authentication happens here. A
caller must authenticate the actual provider/call/returned bytes separately.
Only explicit omission markers authorize restoration from the original request
or visible data. Raw strings, data internals and continuations stay unchanged.
"""
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from typing import Any

SCHEMA = "migloop-batch-wire/1"
BATCH_SCHEMA = "migloop-investigation-batch/1"
DEFAULT_MAX_CHARS = 8_000_000
DEFAULT_MAX_DEPTH = 64
DEFAULT_MAX_NODES = 200_000
_ITEM_FIELDS = frozenset({"args", "scope", "delivery"})
_DATA_SCHEMAS_V1 = frozenset({
    "migloop-time-view/1", "migloop-time-changes/1", "migloop-time-state/1",
    "migloop-raw-event-query/1", "migloop-time-atom/1", "migloop-raw-record/1",
    "migloop-raw-field/1", "migloop-evidence-expansion/1",
})


def _limits(max_chars, max_depth, max_nodes):
    for name, value in (("max_chars", max_chars), ("max_depth", max_depth), ("max_nodes", max_nodes)):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if max_depth > 128:
        raise ValueError("max_depth must not exceed 128")
    return max_chars, max_depth, max_nodes


def _json(value: Any, limits) -> str:
    """Strict finite JSON types, bounded before serialization, no coercion."""
    max_chars, max_depth, max_nodes = limits
    stack, active = [(value, 0, False)], set()
    nodes, characters = 0, 0
    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(current))
            continue
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            raise ValueError("JSON exceeds node/depth limit")
        kind = type(current)
        if kind in (dict, list):
            if len(current) > max_nodes - nodes:
                raise ValueError("JSON exceeds node limit")
            if id(current) in active:
                raise ValueError("cyclic value is not JSON")
            active.add(id(current))
            stack.append((current, depth, True))
            if kind is dict:
                if any(type(key) is not str for key in current):
                    raise ValueError("JSON object keys must be strings")
                characters += sum(len(key) for key in current)
                stack.extend((item, depth + 1, False) for item in current.values())
            else:
                stack.extend((item, depth + 1, False) for item in current)
        elif kind is str:
            characters += len(current)
        elif kind is float:
            if not math.isfinite(current):
                raise ValueError("non-finite numbers are not JSON")
        elif current is not None and kind not in (int, bool):
            raise ValueError("unsupported non-JSON value")
        if characters > max_chars:
            raise ValueError("JSON exceeds character limit")
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        text.encode("utf-8")  # Reject lone surrogates rather than silently replacing raw content.
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError("value cannot be encoded as bounded UTF-8 JSON") from exc
    if len(text) > max_chars:
        raise ValueError("JSON exceeds character limit")
    return text


def _equal(left, right, limits):
    # Python's False == 0 and 1 == 1.0 are not exact JSON type/value equality.
    return _json(left, limits) == _json(right, limits)


def _requests(requests, limits):
    text = _json(requests, limits)
    if type(requests) is not list or not 1 <= len(requests) <= 24:
        raise ValueError("requests must be the original 1..24 item JSON array")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _batch_shape(batch, requests, limits, *, canonical):
    if type(batch) is not dict or batch.get("schema") != BATCH_SCHEMA:
        raise ValueError("unsupported canonical batch schema")
    if type(batch.get("ledger")) is not str or not batch["ledger"]:
        raise ValueError("batch ledger must be a nonempty string")
    items = batch.get("items")
    if type(items) is not list or len(items) != len(requests):
        raise ValueError("batch items must match original request count")
    for index, item in enumerate(items):
        if type(item) is not dict or type(item.get("item_index")) is not int or item["item_index"] != index:
            raise ValueError("item_index must be unique, ordered and match its original request")
        request = requests[index]
        expected_tool = request.get("tool") if type(request) is dict else None
        if "tool" not in item or not _equal(item["tool"], expected_tool, limits):
            raise ValueError("item tool differs from original request")
        if type(item.get("status")) is not str or item["status"] not in {"ok", "error", "deferred"}:
            raise ValueError("item has an invalid status")
        if "data" in item and type(item["data"]) is not dict:
            raise ValueError("item data must be a mapping when present")
        if canonical and ("args" not in item or type(item.get("delivery")) is not dict):
            raise ValueError("canonical item is missing args or delivery")


def _request_args(request):
    # Also preserve batch's error results for malformed, but valid-JSON, requests.
    return request.get("args", {}) if type(request) is dict else {}


def _delivery_v1(data):
    """Pinned wire-v1 extraction, intentionally not imported from investigation.

    Unknown root schemas and unsupported body shapes keep explicit delivery.
    This algorithm/version must not silently expand when query schemas evolve.
    """
    if (type(data) is not dict or type(data.get("schema")) is not str
            or data["schema"] not in _DATA_SCHEMAS_V1):
        return None
    records = []

    def visit(value):
        if type(value) is not dict:
            return
        ref = value.get("ref")
        if type(ref) is str and ref.startswith(("raw:", "#")) and any(k in value for k in ("text", "preview", "diff")):
            body = value.get("text", value.get("preview", value.get("diff", "")))
            if type(body) is not str:
                raise ValueError("unsupported delivery body shape")
            records.append({
                "ref": ref,
                "extent": ("derived_diff" if "diff" in value else
                           "derived_line" if "line" in value and ref.startswith("#") else
                           "raw_field_segment" if "text" in value and value.get("pointer") is not None else
                           "raw_segment" if "text" in value else "preview_or_pointer"),
                "pointer": value.get("pointer"), "offset": value.get("offset"),
                "chars": len(body), "next_offset": value.get("next_offset"),
            })
        for name in ("rows", "items", "records", "requests", "results", "pointers", "events"):
            children = value.get(name)
            if type(children) is list:
                for item in children:
                    visit(item)
        for name in ("unclassified_related", "undated", "unknown_records", "native_io"):
            if type(value.get(name)) is dict:
                visit(value[name])
        if value.get("schema") == "migloop-time-atom/1":
            if type(value.get("sections", {})) is not dict:
                raise ValueError("unsupported atom sections shape")
            for section in value.get("sections", {}).values():
                visit(section)

    try:
        visit(data)
    except ValueError:
        return None
    return {"records": records, "scope": data.get("scope"), "data_schema": data.get("schema"),
            "semantic_checked": False, "navigation_is_relation": False}


def _attention(batch):
    return [{"item_index": item["item_index"], "tool": item["tool"], "status": item["status"],
             "reason": item.get("error")} for item in batch["items"] if item["status"] != "ok"]


def pack(batch: dict, requests: list, *, max_chars=DEFAULT_MAX_CHARS,
         max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES) -> dict:
    """Return a new wire tree; never trim data or enforce a query's text budget.

    Limits bound codec input/output serialized JSON characters, depth and nodes.
    They are safety limits, not token budgets. Receipt/native authentication is
    the caller's responsibility; request_sha256 only binds self-consistency.
    """
    limits = _limits(max_chars, max_depth, max_nodes)
    request_hash = _requests(requests, limits)
    _json(batch, limits)
    _batch_shape(batch, requests, limits, canonical=True)
    result = deepcopy(batch)
    omissions = {"items": [], "top": []}
    for index, item in enumerate(result["items"]):
        fields = []
        candidates = {"args": _request_args(requests[index])}
        data = item.get("data")
        if type(data) is dict:
            if "scope" in data:
                candidates["scope"] = data["scope"]
            delivery = _delivery_v1(data)
            if delivery is not None:
                candidates["delivery"] = delivery
        for key, derived in candidates.items():
            if key in item and _equal(item[key], derived, limits):
                del item[key]
                fields.append(key)
        if fields:
            omissions["items"].append({"item_index": index, "fields": fields})
    if "attention" in result and _equal(result["attention"], _attention(result), limits):
        del result["attention"]
        omissions["top"].append("attention")
    wire = {"schema": SCHEMA, "ledger": result["ledger"], "request_sha256": request_hash,
            "batch": result, "omitted": omissions}
    _json(wire, limits)
    return wire


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def unpack(wire: dict | str, requests: list, *, max_chars=DEFAULT_MAX_CHARS,
           max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES) -> dict:
    """Decode only this explicit version and its declared omissions.

    JSON text input additionally rejects duplicate keys. A pre-parsed mapping
    cannot reveal keys discarded by another parser; callers must safe-parse it.
    This does not authenticate a forged, internally consistent response.
    """
    limits = _limits(max_chars, max_depth, max_nodes)
    request_hash = _requests(requests, limits)
    if type(wire) is str:
        if len(wire) > max_chars:
            raise ValueError("wire text exceeds character limit")
        try:
            wire = json.loads(wire, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        except (ValueError, TypeError, RecursionError) as exc:
            raise ValueError("wire is not strict bounded JSON") from exc
    _json(wire, limits)
    if (type(wire) is not dict or set(wire) != {"schema", "ledger", "request_sha256", "batch", "omitted"}
            or wire.get("schema") != SCHEMA):
        raise ValueError("unsupported wire schema or fields")
    if wire.get("request_sha256") != request_hash:
        raise ValueError("wire does not match the original requests")
    _batch_shape(wire["batch"], requests, limits, canonical=False)
    if type(wire["ledger"]) is not str or wire["ledger"] != wire["batch"]["ledger"]:
        raise ValueError("wire ledger differs from canonical batch ledger")
    omitted = wire["omitted"]
    if type(omitted) is not dict or set(omitted) != {"items", "top"} or type(omitted["items"]) is not list:
        raise ValueError("invalid explicit omission map")
    if type(omitted["top"]) is not list or omitted["top"] not in ([], ["attention"]):
        raise ValueError("invalid top-level omissions")
    result, seen = deepcopy(wire["batch"]), set()
    for entry in omitted["items"]:
        if type(entry) is not dict or set(entry) != {"item_index", "fields"}:
            raise ValueError("invalid item omission entry")
        index, fields = entry["item_index"], entry["fields"]
        if type(index) is not int or not 0 <= index < len(requests) or index in seen:
            raise ValueError("ambiguous omission item_index")
        if type(fields) is not list or not fields or any(type(k) is not str or k not in _ITEM_FIELDS for k in fields) or len(set(fields)) != len(fields):
            raise ValueError("invalid item omission fields")
        seen.add(index)
        item = result["items"][index]
        for key in fields:
            if key in item:
                raise ValueError("omitted field is also explicitly present")
            if key == "args":
                derived = _request_args(requests[index])
            elif key == "scope":
                if type(item.get("data")) is not dict or "scope" not in item["data"]:
                    raise ValueError("omitted scope cannot be derived from visible data")
                derived = item["data"]["scope"]
            else:
                derived = _delivery_v1(item.get("data"))
                if derived is None:
                    raise ValueError("omitted delivery has no supported v1 derivation")
            item[key] = deepcopy(derived)
    if omitted["top"]:
        if "attention" in result:
            raise ValueError("omitted attention is also explicitly present")
        result["attention"] = _attention(result)
    _batch_shape(result, requests, limits, canonical=True)
    _json(result, limits)
    return result
