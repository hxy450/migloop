"""Lossless, bounded-cache access to owned JSONL sources, independent of parsers.

Records, not classified Actions, are the search corpus. Source/line/content
addresses survive collector upgrades and appends. Duplicate source names are
ambiguous (never guessed); changed cited lines fail their digest check.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any, Iterator

from .time_scope import _time, _iso

_CACHE: OrderedDict[str, tuple[tuple[int, int], tuple[str, ...], int]] = OrderedDict()
_LOCK = RLock()
_BUDGET = 32 * 1024 * 1024
_REF = re.compile(r"raw:([0-9a-f]{20}):L([1-9][0-9]*):([0-9a-f]{20})\Z")


def source_key(path: str) -> str:
    # Basename is portable across frozen pools. Registry checks collisions.
    return hashlib.sha256(os.path.basename(path).encode("utf-8")).hexdigest()[:20]


def sources(ledger: Any, agent: str | None = None) -> dict[str, set[str]]:
    registry: dict[str, set[str]] = {}
    agents = [ledger.agents[agent]] if agent is not None else ledger.agents.values()
    for rec in agents:
        for path in [*rec.sources, *(a.src[0] for a in rec.actions if a.src)]:
            registry.setdefault(os.path.normcase(os.path.abspath(path)), set()).add(rec.id)
    return registry


def lines(path: str) -> tuple[str, ...]:
    stat = os.stat(path)
    signature = (stat.st_mtime_ns, stat.st_size)
    with _LOCK:
        cached = _CACHE.get(path)
        if cached and cached[0] == signature:
            _CACHE.move_to_end(path)
            return cached[1]
    # Strict UTF-8: report a source gap instead of silently throwing away bytes.
    with open(path, encoding="utf-8-sig", newline="") as fh:
        data = tuple(line.rstrip("\r\n") for line in fh)
    end = os.stat(path)
    if (end.st_mtime_ns, end.st_size) != signature:
        raise ValueError("source changed during read; retry with a stable source")
    size = sum(len(line) * 4 for line in data)
    with _LOCK:
        _CACHE.pop(path, None)
        if size <= _BUDGET:
            _CACHE[path] = (signature, data, size)
        while sum(v[2] for v in _CACHE.values()) > _BUDGET:
            _CACHE.popitem(last=False)
    return data


def readable(value: Any) -> str:
    """Search decoded values AND keys, including unfamiliar record/block types."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(str(k) + "\n" + readable(v) for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(readable(v) for v in value)
    return json.dumps(value, ensure_ascii=False)


@dataclass(frozen=True)
class Record:
    path: str
    line: int
    raw: str
    value: Any
    ts: str | None
    malformed: bool

    @property
    def ref(self) -> str:
        digest = hashlib.sha256(self.raw.encode("utf-8")).hexdigest()[:20]
        return f"raw:{source_key(self.path)}:L{self.line}:{digest}"

    @property
    def text(self) -> str:
        return self.raw if self.malformed else readable(self.value)

    @property
    def kind(self) -> str:
        if not isinstance(self.value, dict):
            return "malformed" if self.malformed else "unclassified"
        return str(self.value.get("type") or "unclassified")

    def address(self) -> dict[str, Any]:
        return {"ref": self.ref, "source": os.path.basename(self.path), "line": self.line,
                "ts": self.ts, "kind": self.kind, "malformed": self.malformed,
                "time_status": "recorded" if self.ts else "undated"}


def records(path: str) -> Iterator[Record]:
    for number, raw in enumerate(lines(path), 1):
        try:
            value = json.loads(raw)
            malformed = False
        except (ValueError, RecursionError):
            value, malformed = None, True
        ts = _iso(_time(value.get("timestamp"))) if isinstance(value, dict) else None
        yield Record(path, number, raw, value, ts, malformed)


def resolve(ledger: Any, ref: str) -> Record:
    match = _REF.fullmatch(ref)
    if not match:
        raise ValueError("invalid raw reference")
    key, line, _digest = match.groups()
    paths = [p for p in sources(ledger) if source_key(p) == key]
    if len(paths) != 1:
        raise ValueError("raw reference source is ambiguous or missing")
    for record in records(paths[0]):
        if record.line == int(line):
            if record.ref != ref:
                raise ValueError("raw reference content changed; refusing stale evidence")
            return record
    raise ValueError("raw reference line is missing")
