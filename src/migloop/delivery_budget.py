"""Pure, prefix-only projection of already-selected query data.

``fit(data, budget)`` budgets compact UTF-8-decoded JSON *characters* of ``data``;
the returned envelope/continuations are separately accounted transport metadata.
It performs no query, ranking, I/O, causal inference or receipt hashing. Callers
must create delivery receipts from the returned body, never the original body.
Unknown schemas are delivered unchanged if they fit, otherwise deferred.
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

PAGE_SCHEMAS = {"migloop-time-view/1", "migloop-time-changes/1", "migloop-time-state/1",
                "migloop-raw-event-query/1"}
RECORD_SCHEMAS = {"migloop-raw-record/1", "migloop-raw-field/1"}
EXPANSION_SCHEMA = "migloop-evidence-expansion/1"


def size(data: Any) -> int:
    """The same serialized-data-only character accounting as investigation.batch."""
    return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def _integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _pages(data: dict) -> list[tuple[str, dict, str]]:
    main = ("source_rows" if data.get("view") == "sources" else "events") if data.get("schema") == "migloop-raw-event-query/1" else "rows"
    result = [(main, data, main)]
    for name in ("undated", "unknown_records"):
        if name in data:
            result.append((name + ".rows", data[name], "rows"))
    related = data.get("unclassified_related")
    if data.get("schema") == "migloop-time-changes/1" and isinstance(related, dict) and "rows" in related:
        result.append(("unclassified_related.rows", related, "rows"))
        if "undated" in related:
            result.append(("unclassified_related.undated.rows", related["undated"], "rows"))
    for _name, page, key in result:
        if (not isinstance(page, dict) or not isinstance(page.get(key), list)
                or not all(_integer(page.get(k)) for k in ("total", "offset", "limit"))
                or not all(isinstance(row, dict) for row in page[key])
                or len(page[key]) > max(0, page["total"] - page["offset"])):
            raise ValueError("unsupported page shape; no coordinates inferred")
    return result


def _paging_args(name: str, original: dict, offset: int) -> dict:
    related = name.startswith("unclassified_related.")
    size_arg, offset_arg = ("related_limit", "related_offset") if related else ("limit", "offset")
    limit = original.get("requested_limit", original["limit"])
    # An actual_limit=0 receipt is not a legal request limit. In particular,
    # an undelivered first page has a useful offset=0, not a missing cursor.
    limit = min(200, max(1, limit)) if _integer(limit) else 1
    return {offset_arg: offset, size_arg: limit}


def _next_query(original: dict, name: str, offset: int | None) -> dict | None:
    if offset is None:
        return None
    template = original.get("query")
    if not isinstance(template, dict):
        template = original.get("next_query")
    if not isinstance(template, dict) or not isinstance(template.get("args"), dict):
        raise TypeError("page next_query lacks an original query template; refusing to invent its scope")
    query = deepcopy(template)
    query["args"].update(_paging_args(name, original, offset))
    return query


def _set_page(page: dict, key: str, rows: list[dict], original: dict, name: str) -> None:
    count, offset, total = len(rows), original["offset"], original["total"]
    page.update({key: rows, "limit": count, "actual_limit": count,
                 "requested_limit": original.get("requested_limit", original["limit"]),
                 "remaining": max(0, total - offset - count),
                 "next_offset": offset + count if offset + count < total else None})
    if "next_query" in original or "query" in original:
        page["next_query"] = _next_query(original, name, page["next_offset"])


def _receipt(data: dict) -> None:
    receipt = data.get("receipt")
    if receipt is None:
        return
    if not isinstance(receipt, dict) or receipt.get("schema") != "migloop-query-receipt/1":
        raise ValueError("unknown receipt shape; refusing to retain a stale delivery assertion")
    if data.get("schema") in PAGE_SCHEMAS:
        receipt["records"] = [r["ref"] for r in data.get("rows", []) if isinstance(r.get("ref"), str)]
        if "undated_records" in receipt:
            receipt["undated_records"] = [r["ref"] for r in data.get("undated", {}).get("rows", [])
                                          if isinstance(r.get("ref"), str)]


def _record_safe(record: dict) -> bool:
    return (record.get("schema") in RECORD_SCHEMAS and isinstance(record.get("text"), str)
            and isinstance(record.get("ref"), str) and _integer(record.get("offset"))
            and _integer(record.get("chars")) and record["offset"] + len(record["text"]) <= record["chars"])


def _record_prefix(record: dict, count: int) -> dict:
    out = deepcopy(record)
    out["text"] = record["text"][:count]
    end = record["offset"] + count
    out.update(next_offset=end if end < record["chars"] else None,
               delivered_chars=count, budget_truncated=count < len(record["text"]))
    return out


def _row_prefix(row: dict, field: str, count: int) -> dict:
    out = deepcopy(row)
    out[field] = row[field][:count]
    if field == "diff":
        out["truncated"] = bool(row.get("truncated") or count < len(row[field]))
        out["delivered_diff_chars"] = count
    else:
        out["preview_budget_truncated"] = count < len(row[field])
    return out


def _max_prefix(text: str, make, budget: int) -> dict | None:
    """Return a nonempty prefix, accounting for JSON escaping and metadata."""
    low, high, best = 1, len(text) - 1, None
    while low <= high:
        count = (low + high) // 2
        candidate = make(count)
        if size(candidate) <= budget:
            best, low = candidate, count + 1
        else:
            high = count - 1
    return best


def _page_fit(data: dict, budget: int) -> dict | None:
    original_pages = _pages(data)
    output = deepcopy(data)
    output_pages = _pages(output)
    for (name, page, key), (_, original, _) in zip(output_pages, original_pages):
        _set_page(page, key, [], original, name)
    # Small body navigation is not the body itself. Fold its entries before
    # allowing navigation metadata to displace an actual evidence row.
    navigation = output.get("body_sources")
    if isinstance(navigation, dict) and isinstance(navigation.get("entries"), list) and isinstance(navigation.get("query"), dict):
        navigation.update(entries=[], remaining=navigation["total"], budget_folded=True)
    _receipt(output)
    if size(output) > budget:
        return None
    # Independent pages advance independently; rows within each page never skip.
    positions = [0] * len(original_pages)
    blocked = set()
    progress = True
    while progress:
        progress = False
        for index, (_name, original, key) in enumerate(original_pages):
            if index in blocked or positions[index] >= len(original[key]):
                continue
            row = original[key][positions[index]]

            def append(value, base=output, page_index=index, source_page=original):
                candidate = deepcopy(base)
                name, page, row_key = _pages(candidate)[page_index]
                _set_page(page, row_key, [*page[row_key], value], source_page, name)
                _receipt(candidate)
                return candidate

            candidate = append(deepcopy(row))
            if size(candidate) > budget:
                from . import temporal_annotation
                compact = temporal_annotation.compact(row)
                if compact is not None and size(compact) < size(row):
                    row = compact
                    candidate = append(row)
            if size(candidate) > budget:
                field = ("diff" if data["schema"] == "migloop-time-state/1" and data.get("tool") == "diff"
                         and isinstance(row.get("diff"), str) and _integer(row.get("diff_chars")) else
                         "preview" if data["schema"] == "migloop-time-view/1" and isinstance(row.get("preview"), str) else None)
                candidate = _max_prefix(row[field], lambda n, value=row, name=field, include=append:
                                        include(_row_prefix(value, name, n)), budget) if field else None
                blocked.add(index)  # A partial row is the final row of this page.
            if candidate is not None:
                output = candidate
                positions[index] += 1
                progress = True
    return output if any(positions) or not any(p[k] for _, p, k in original_pages) else None


def _expand_fit(data: dict, budget: int) -> dict | None:
    if not isinstance(data.get("items"), list) or not all(isinstance(i, dict) for i in data["items"]):
        raise ValueError("unsupported expansion shape")
    output = deepcopy(data)
    output.update(items=[], items_total=len(data["items"]), items_delivered=0)
    if size(output) > budget:
        return None
    for item in data["items"]:
        candidate = deepcopy(output)
        candidate["items"].append(deepcopy(item))
        candidate["items_delivered"] = len(candidate["items"])
        if size(candidate) <= budget:
            output = candidate
            continue
        records = item.get("records")
        if not isinstance(records, list) or not records or not all(isinstance(r, dict) for r in records):
            break  # An indivisible error/metadata item; do not skip to a later ref.
        shell = deepcopy(item)
        shell.update(records=[], records_total=len(records), records_delivered=0, delivery_status="partial")
        candidate = deepcopy(output)
        candidate["items"].append(shell)
        candidate["items_delivered"] = len(candidate["items"])
        if size(candidate) > budget:
            break
        partial = candidate
        for record in records:
            def append(value, base=partial):
                value_out = deepcopy(base)
                last = value_out["items"][-1]
                last["records"].append(value)
                last["records_delivered"] = len(last["records"])
                return value_out
            candidate = append(deepcopy(record))
            if size(candidate) > budget:
                candidate = _max_prefix(record["text"], lambda n, value=record, include=append:
                                        include(_record_prefix(value, n)), budget) if _record_safe(record) else None
                if candidate is not None:
                    partial = candidate
                break
            partial = candidate
        if partial["items"][-1]["records"]:
            output = partial
        break  # Explicit continuation carries all remaining records and refs.
    return output if output["items"] or not data["items"] else None


def _record_next(record: dict, scope: Any, *, offset: int | None = None, **extra) -> dict:
    return {"kind": "record", "ref": record["ref"], "pointer": record.get("pointer"),
            "offset": record.get("next_offset") if offset is None else offset,
            "scope": deepcopy(scope), **extra}


def _continuations(original: dict, delivered: dict | None) -> list[dict]:
    schema, scope = original.get("schema"), original.get("scope")
    if schema in PAGE_SCHEMAS:
        original_pages = _pages(original)
        actual_pages = _pages(delivered) if delivered is not None else []
        result = []
        for i, (name, page, key) in enumerate(original_pages):
            rows = actual_pages[i][1][key] if actual_pages else []
            next_row = page["offset"] + len(rows)
            if next_row < page["total"]:
                continuation = {"kind": "page", "page": name, "offset": next_row,
                                "remaining": page["total"] - next_row, "scope": deepcopy(scope),
                                "args_patch": _paging_args(name, page, next_row), "select_page": name}
                if "next_query" in page or "query" in page:
                    continuation["next_query"] = _next_query(page, name, next_row)
                    if "scope" in continuation["next_query"]:
                        continuation["scope"] = deepcopy(continuation["next_query"]["scope"])
                result.append(continuation)
            for number, row in enumerate(rows):
                source = page[key][number]
                from . import temporal_annotation
                result.extend(temporal_annotation.continuations(row))
                if isinstance(row.get("diff"), str) and (row.get("truncated") or len(row["diff"]) < source.get("diff_chars", 0)):
                    result.append({"kind": "derived_diff_requery", "page": name, "ref": row.get("ref"),
                        "scope": deepcopy(scope), "delivered_chars": len(row["diff"]), "diff_chars": row.get("diff_chars"),
                        "args_patch": {"offset": page["offset"] + number, "limit": 1,
                                       "max_chars": min(120000, max(1, row["diff_chars"]))},
                        "note": "diff has a row cursor, not a character cursor; requery or open the original ref"})
                if row.get("preview_budget_truncated"):
                    result.append({"kind": "raw_requery", "ref": row.get("ref"), "offset": 0,
                                   "scope": deepcopy(scope), "note": "preview position is not a raw text offset"})
        navigation = delivered.get("body_sources") if delivered else None
        if isinstance(navigation, dict) and navigation.get("budget_folded"):
            result.append({"kind": "body_navigation", "next_query": deepcopy(navigation["query"]),
                           "remaining": navigation["remaining"], "note": "仅导航未交付；没有认证正文已读"})
        return result
    if schema in RECORD_SCHEMAS and _record_safe(original):
        row = delivered or original
        offset = original["offset"] if delivered is None else row.get("next_offset")
        return [_record_next(row, scope, offset=offset)] if offset is not None else []
    if schema == EXPANSION_SCHEMA:
        result = []
        items = delivered.get("items", []) if delivered else []
        for index, item in enumerate(original["items"]):
            shown = items[index] if index < len(items) else None
            records = item.get("records", [])
            parts = shown.get("records", []) if shown else []
            if shown is None:
                result.append({"kind": "expansion_item", "item_index": item.get("item_index", index),
                               "ref": item.get("ref"), "pointer": item.get("pointer"),
                               "scope": deepcopy(scope), "delivery_status": "not_delivered",
                               "repeat_original_item": True})
            for record_index, record in enumerate(records):
                if not _record_safe(record):
                    if record_index >= len(parts):
                        result.append({"kind": "expansion_record", "ref": record.get("ref"),
                            "item_index": item.get("item_index", index), "record_index": record_index,
                            "scope": deepcopy(scope), "repeat_original_item": True})
                    continue
                part = parts[record_index] if record_index < len(parts) else None
                offset = part.get("next_offset") if part else record["offset"]
                if offset is not None:
                    result.append(_record_next(part or record, scope, offset=offset,
                        item_index=item.get("item_index", index), record_index=record_index,
                        delivery_status="partial" if part else "not_delivered"))
        return result
    return [{"kind": "repeat_original_query", "scope": deepcopy(scope),
             "offset": original.get("offset"), "reason": "schema not projected"}] if delivered is None else []


def fit(data: dict[str, Any], budget: int) -> dict[str, Any]:
    """Fit known bodies by sorted prefixes; preserve scope, totals and all gaps.

    Returns ``status/data/budget_adjusted/data_chars/budget/continuations``.
    ``status=ok`` may mean partial delivery: consult all page/record cursors.
    ``deferred`` has ``data=None`` and continuations, and certifies no body read.
    Continuation args_patch is merged into the caller's *original* query; separate
    page selectors are response fields, never invented backend parameters.
    changes.unclassified_related and its undated page advance independently via
    related_offset/related_limit; saved next_query scopes are never rewritten.
    """
    if not isinstance(data, dict) or not _integer(budget):
        raise ValueError("data must be a mapping and budget a nonnegative integer")
    original_size = size(data)
    output, reason = deepcopy(data), None
    if original_size > budget:
        schema = data.get("schema")
        try:
            if schema in PAGE_SCHEMAS:
                output = _page_fit(data, budget)
            elif schema in RECORD_SCHEMAS and _record_safe(data):
                _receipt(data)  # Validates receipt without changing raw records.
                output = _max_prefix(data["text"], lambda n: _record_prefix(data, n), budget)
            elif schema == EXPANSION_SCHEMA:
                output = _expand_fit(data, budget)
            else:
                output, reason = None, "unknown schema or shape: unchanged body exceeds budget"
        except (ValueError, TypeError, KeyError) as exc:
            output, reason = None, str(exc)
    try:
        continuations = _continuations(data, output)
    except (ValueError, TypeError, KeyError):
        continuations = [{"kind": "repeat_original_query", "scope": deepcopy(data.get("scope")),
                          "offset": data.get("offset"), "reason": "unrecognized coordinates"}]
    if output is None and not continuations:
        continuations = [{"kind": "repeat_original_query", "scope": deepcopy(data.get("scope")),
                          "offset": data.get("offset"), "reason": "metadata not delivered"}]
    return {"status": "ok" if output is not None else "deferred", "data": output,
            "budget_adjusted": output != data, "data_chars": size(output) if output is not None else 0,
            "budget": budget, "original_data_chars": original_size, "budget_scope": "serialized_data_only",
            "continuations": continuations,
            "reason": reason or ("first indivisible metadata/body unit does not fit" if output is None else None)}
