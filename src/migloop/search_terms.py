"""Bounded literal-OR query helpers; no ledger effects or navigation authority."""
from __future__ import annotations

import json
from typing import Any

MAX_TERMS = 8
MAX_TERM_CHARS = 256
MAX_QUERY_CHARS = 1024
MAX_ROWS = 24
MAX_BODY_CHARS = 20000
SNIPPET_CHARS = 384


def valid_time(value: Any) -> bool:
    from .time_scope import _time
    # Use the same explicit-timezone rule as the observation overview. Keep
    # surrounding whitespace invalid: existing ts_norm does not strip it.
    return isinstance(value, str) and value == value.strip() and _time(value) is not None


def normalize(q: Any, q_any: Any, *, http_json: bool = False) -> list[str] | None:
    if q_any is None:
        return None
    if http_json and isinstance(q_any, str) and len(q_any) <= MAX_QUERY_CHARS * 8:
        try:
            q_any = json.loads(q_any)
        except (ValueError, TypeError):
            raise ValueError("q_any 必须是 JSON 字符串数组") from None
    if not isinstance(q_any, list) or not 2 <= len(q_any) <= MAX_TERMS:
        raise ValueError("q_any 必须含 2–8 个非空字面量")
    if any(not isinstance(t, str) or not t.strip() or len(t) > MAX_TERM_CHARS for t in q_any) \
            or sum(len(t) for t in q_any) > MAX_QUERY_CHARS:
        raise ValueError("q_any 每项须为非空字符串且不超过 256 字；总计不超过 1024 字")
    if q not in (None, ""):
        raise ValueError("非空 q 与 q_any 互斥")
    if len({t.lower() for t in q_any}) != len(q_any):
        raise ValueError("q_any 字面量不能重复（按 lower 匹配）")
    return list(q_any)


def literal_span(text: str, needle: str, offset: int = 0) -> tuple[int, int] | None:
    """Case-insensitive literal location in ORIGINAL decoded characters, not lower() indices."""
    start = max(0, min(offset, len(text)))
    lowered = text.lower()
    pos = lowered.find(needle.lower(), len(text[:start].lower()))
    if pos < 0:
        return None
    end = pos + len(needle.lower())
    if len(lowered) == len(text):
        return pos, end
    mapping = [i for i, ch in enumerate(text) for _ in ch.lower()]
    return (mapping[pos], mapping[end - 1] + 1) if end > pos else (start, start)


def scan(text: str, terms: list[str]) -> dict[str, Any] | None:
    """One decoded field, one lowercase pass. Excerpts are exact field slices.

    Offsets refer to the decoded field, never to JSONL bytes or file line numbers.
    Unicode lower() can expand a character; map back before slicing original text.
    """
    lowered = text.lower()
    positions = [(term, lowered.find(term.lower())) for term in terms]
    positions = [(term, pos) for term, pos in positions if pos >= 0]
    if not positions:
        return None
    mapping = None
    if len(lowered) != len(text):
        mapping = [i for i, ch in enumerate(text) for _ in ch.lower()]
    excerpts: list[dict[str, Any]] = []
    for term, pos in positions:
        last = pos + len(term.lower())
        start_match = mapping[pos] if mapping is not None else pos
        end_match = mapping[last - 1] + 1 if mapping is not None else last
        start = max(0, start_match - 48)
        end = min(len(text), max(end_match, start + SNIPPET_CHARS))
        if end - start > SNIPPET_CHARS:
            # Defensive: never offer a clipped-away literal as displayed evidence.
            continue
        if any(term in e["matched_terms"] and e["start"] <= start_match and e["end"] >= end_match for e in excerpts):
            continue
        snippet = text[start:end]
        excerpts.append({"text": snippet, "start": start, "end": end,
                         "field_line": text.count("\n", 0, start) + 1,
                         "prefix_omitted": start > 0, "suffix_omitted": end < len(text),
                         "matched_terms": [t for t, _ in positions if t.lower() in snippet.lower()]})
    return {"matched_terms": [t for t, _ in positions], "excerpts": excerpts}


def source(row: dict[str, Any]) -> str:
    if row.get("claim_note") or row.get("kind") in ("say", "think", "inbox", "notify", "compact"):
        return "statement"
    if row.get("kind") in ("instruction", "inject", "system", "prompt"):
        return "instruction"
    return {"output": "tool_output", "input": "tool_input", "content": "file_content"}.get(row.get("field"), "other")


def unique_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate physical source field, not the number of matching literals."""
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row["record_key"])
        if key not in result:
            result[key] = {**row, "matched_terms": list(row["matched_terms"]), "excerpts": list(row["excerpts"])}
        else:
            previous = result[key]
            previous["matched_terms"] = list(dict.fromkeys(previous["matched_terms"] + row["matched_terms"]))
            previous["excerpts"].extend(e for e in row["excerpts"] if e not in previous["excerpts"])
    return list(result.values())


def fair_rows(rows: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
    """Stable round-robin per literal/source, sharing one row budget."""
    sources = ("tool_output", "tool_input", "file_content", "statement", "instruction", "other")
    groups = [[[r for r in rows if term in r["matched_terms"] and source(r) == src]
               for src in sources] for term in terms]
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    while any(any(g) for g in groups) and len(selected) < MAX_ROWS:
        # At most ONE new row per literal per round; six source groups for a
        # common literal must not starve the eighth literal before row 24.
        for term_groups in groups:
            for _ in range(len(term_groups)):
                group = term_groups.pop(0)
                term_groups.append(group)
                while group and tuple(group[0]["record_key"]) in seen:
                    group.pop(0)
                if group:
                    row = group.pop(0)
                    selected.append(row)
                    seen.add(tuple(row["record_key"]))
                    break
            if len(selected) == MAX_ROWS:
                break
    return selected
