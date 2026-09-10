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
from dataclasses import dataclass, field, replace
from threading import RLock
from typing import Any, Iterator

from .time_scope import _iso, _time

_CACHE: OrderedDict[str, tuple[tuple[int, int], tuple[str, ...], int]] = OrderedDict()
_LOCK = RLock()
_BUDGET = 32 * 1024 * 1024
_OFFSETS: OrderedDict[str, tuple[tuple[int, int], tuple[int, ...]]] = OrderedDict()
_OFFSET_BUDGET = 8 * 1024 * 1024
_REF = re.compile(r"raw:([0-9a-f]{20}|[0-9a-f]{40}):L([1-9][0-9]*):([0-9a-f]{20})\Z")


def _legacy_source_key(path: str) -> str:
    return hashlib.sha256(os.path.basename(path).encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class SourceSpec:
    """Explicit source identity/time policy, not inferred from host directories."""
    logical_name: str | None = None
    timestamp_policy: str = "record"


def source_spec(ledger: Any, path: str) -> SourceSpec:
    key = os.path.normcase(os.path.abspath(path))
    metadata = getattr(ledger, "source_metadata", {}).get(key)
    if metadata is not None:
        if (not isinstance(metadata, dict) or set(metadata) != {"logical_name", "timestamp_policy"}
                or not isinstance(metadata["logical_name"], str) or not metadata["logical_name"]
                or metadata["timestamp_policy"] not in ("record", "unknown")):
            raise ValueError("invalid registered raw source metadata")
        return SourceSpec(**metadata)
    auxiliary = {os.path.normcase(os.path.abspath(p)) for p in getattr(ledger, "auxiliary_sources", ())}
    return SourceSpec(timestamp_policy="unknown" if key in auxiliary or not key.lower().endswith(".jsonl") else "record")


def source_key(path: str, source: SourceSpec | None = None) -> str:
    """40-hex qualified keys require an explicit portable source contract.

    No absolute path or guessed 'subagents' ancestor is used. Without a source
    contract the old 20-hex basename scheme remains available; ambiguity is
    still checked over the complete registry before resolving either version.
    """
    if source is None or source.logical_name is None:
        return _legacy_source_key(path)
    value = json.dumps(["registered-source/1", source.logical_name], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("ascii")).hexdigest()[:40]


def sources(ledger: Any, agent: str | None = None) -> dict[str, set[str]]:
    registry: dict[str, set[str]] = {}
    agents = [ledger.agents[agent]] if agent is not None else ledger.agents.values()
    for rec in agents:
        for path in [*rec.sources, *(a.src[0] for a in rec.actions if a.src)]:
            registry.setdefault(os.path.normcase(os.path.abspath(path)), set()).add(rec.id)
    if agent is None:
        for path in getattr(ledger, "auxiliary_sources", ()):
            registry.setdefault(os.path.normcase(os.path.abspath(path)), set())
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
    # resolve preserves a supplied legacy reference instead of silently
    # upgrading it during old receipt/field-span replay.
    _reference_key: str | None = field(default=None, repr=False, compare=False)
    textual: bool = False

    @property
    def ref(self) -> str:
        digest = hashlib.sha256(self.raw.encode("utf-8")).hexdigest()[:20]
        return f"raw:{self._reference_key or source_key(self.path)}:L{self.line}:{digest}"

    @property
    def text(self) -> str:
        return self.raw if self.malformed or self.textual else readable(self.value)

    @property
    def kind(self) -> str:
        if self.textual:
            return "attachment_text"
        if not isinstance(self.value, dict):
            return "malformed" if self.malformed else "unclassified"
        return str(self.value.get("type") or "unclassified")

    def address(self) -> dict[str, Any]:
        return {"ref": self.ref, "source": os.path.basename(self.path), "line": self.line,
                "ts": self.ts, "kind": self.kind, "malformed": self.malformed,
                "time_status": "recorded" if self.ts else "undated"}


def _record_timestamp(path: str, value: Any, source: SourceSpec | None) -> str | None:
    policy = source.timestamp_policy if source else "record" if path.lower().endswith(".jsonl") else "unknown"
    return _iso(_time(value.get("timestamp"))) if policy == "record" and isinstance(value, dict) else None


def records(path: str, *, source: SourceSpec | None = None) -> Iterator[Record]:
    path = os.path.normcase(os.path.abspath(path))
    for number, raw in enumerate(lines(path), 1):
        yield _record_line(path, number, raw, source)


def _record_line(path: str, number: int, raw: str, source: SourceSpec | None) -> Record:
    # Attachments are physical text lines, not purported JSONL events. Even a
    # JSON-looking line in a script/output stays original text; it cannot add
    # execution timestamps or pretend to be a decoded JSON Pointer target.
    textual = not path.lower().endswith(".jsonl")
    value, malformed = None, False
    if not textual:
        try:
            value = json.loads(raw)
        except (ValueError, RecursionError):
            malformed = True
    stamp = None if textual else _record_timestamp(path, value, source)
    return Record(path, number, raw, value, stamp, malformed, source_key(path, source), textual)


def read_record(path: str, number: int, *, source: SourceSpec | None = None) -> Record:
    """Read one physical line without JSON-decoding every earlier record.

    A bounded byte-offset index also avoids loading giant uncached transcripts
    afresh for every citation. Offsets are private and source-signature bound.
    """
    if type(number) is not int or number < 1:
        raise ValueError("raw record line must be a positive integer")
    # Match sources()/records() on case-insensitive hosts; direct citation
    # expansion must not manufacture an unresolvable source-key spelling.
    path = os.path.normcase(os.path.abspath(path))
    before = os.stat(path)
    signature = (before.st_mtime_ns, before.st_size)
    with _LOCK:
        cached = _OFFSETS.get(path)
        offsets = cached[1] if cached and cached[0] == signature else None
        if offsets is not None:
            _OFFSETS.move_to_end(path)
    if offsets is None:
        positions, position = [], 0
        with open(path, "rb") as stream:
            for raw in stream:
                positions.append(position)
                position += len(raw)
        after = os.stat(path)
        if (after.st_mtime_ns, after.st_size) != signature:
            raise ValueError("source changed during offset indexing")
        offsets = tuple(positions)
        with _LOCK:
            _OFFSETS.pop(path, None)
            if len(offsets) * 36 <= _OFFSET_BUDGET:
                _OFFSETS[path] = (signature, offsets)
            while sum(len(v[1]) * 36 for v in _OFFSETS.values()) > _OFFSET_BUDGET:
                _OFFSETS.popitem(last=False)
    if number > len(offsets):
        raise ValueError("raw reference line is missing")
    with open(path, "rb") as stream:
        stream.seek(offsets[number - 1])
        raw = stream.readline().rstrip(b"\r\n").decode("utf-8-sig" if number == 1 else "utf-8")
    after = os.stat(path)
    if (after.st_mtime_ns, after.st_size) != signature:
        raise ValueError("source changed during record read")
    return _record_line(path, number, raw, source)


def resolve(ledger: Any, ref: str) -> Record:
    match = _REF.fullmatch(ref)
    if not match:
        raise ValueError("invalid raw reference")
    key, line, _digest = match.groups()
    paths = [p for p in sources(ledger) if (
        _legacy_source_key(p) if len(key) == 20 else source_key(p, source_spec(ledger, p))) == key]
    if len(paths) != 1:
        raise ValueError("raw reference source is ambiguous or missing")
    record = replace(read_record(paths[0], int(line), source=source_spec(ledger, paths[0])), _reference_key=key)
    if record.ref != ref:
        raise ValueError("raw reference content changed; refusing stale evidence")
    return record
