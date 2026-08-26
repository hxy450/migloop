"""Registry for transcript source adapters.

To add a new source (for example DevEco), implement the contract in
``base.py`` and register its module in ``ADAPTERS``.  The renderer and trace
analysis layers do not need source-specific changes.

契约边界（本文件 + ``base.py``）纳入类型检查；两个大 adapter 实现
（``claude.py`` / ``codex.py``，vendored 的 py3.9 风格代码）在 pyproject 里豁免。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from . import claude, codex
from .base import SessionCandidate, SourceAdapter

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


# More-specific detectors must precede permissive fallbacks.
ADAPTERS: tuple[SourceAdapter, ...] = (
    cast("SourceAdapter", codex),
    cast("SourceAdapter", claude),
)


def get(name: str) -> SourceAdapter:
    for adapter in ADAPTERS:
        if name == adapter.FORMAT:
            return adapter
    raise KeyError(f"unknown session adapter: {name}")


def detect(path: str) -> SourceAdapter:
    for adapter in ADAPTERS:
        if adapter.is_session(path):
            return adapter
    raise ValueError(f"unsupported session transcript: {path}")


def discover(roots: Mapping[str, str] | None = None) -> Sequence[SessionCandidate]:
    roots = roots or {}
    rows: list[SessionCandidate] = []
    for adapter in ADAPTERS:
        root = roots.get(adapter.FORMAT) or adapter.default_root()
        rows.extend(adapter.iter_sessions(root))
    rows.sort(key=lambda row: row.mtime, reverse=True)
    return rows


__all__ = ["ADAPTERS", "SessionCandidate", "SourceAdapter", "detect", "discover", "get"]
