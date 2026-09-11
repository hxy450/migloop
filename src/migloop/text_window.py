"""Explicit original-text selection, independent of transport budgets.

An omitted limit selects all remaining text. A positive limit explicitly asks
for a character page; it never changes source/time admission or proves truth.
"""
from __future__ import annotations


def validate(offset=0, max_chars=None):
    if type(offset) is not int or offset < 0:
        raise ValueError("offset 必须是非负整数")
    if max_chars is not None and (type(max_chars) is not int or not 1 <= max_chars <= 120000):
        raise ValueError("max_chars 省略/null为完整原文；显式分页须为1–120000整数")


def page(text: str, offset=0, max_chars=None):
    validate(offset, max_chars)
    shown = text[offset:None if max_chars is None else offset + max_chars]
    end = offset + len(shown)
    return {"text": shown, "offset": offset, "chars": len(text),
            "next_offset": end if end < len(text) else None,
            "returned_chars": len(shown), "complete": offset == 0 and end == len(text)}
