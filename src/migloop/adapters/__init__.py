"""Registry for transcript source adapters.

To add a new source (for example DevEco), implement the contract in
``base.py`` and register its module in ``ADAPTERS``.  The renderer and trace
analysis layers do not need source-specific changes.
"""
from . import claude, codex


# More-specific detectors must precede permissive fallbacks.
ADAPTERS = (codex, claude)


def get(name):
    for adapter in ADAPTERS:
        if adapter.FORMAT == name:
            return adapter
    raise KeyError("unknown session adapter: %s" % name)


def detect(path):
    for adapter in ADAPTERS:
        if adapter.is_session(path):
            return adapter
    raise ValueError("unsupported session transcript: %s" % path)


def discover(roots=None):
    roots = roots or {}
    rows = []
    for adapter in ADAPTERS:
        root = roots.get(adapter.FORMAT) or adapter.default_root()
        rows.extend(adapter.iter_sessions(root))
    rows.sort(key=lambda row: row.mtime, reverse=True)
    return rows


__all__ = ["ADAPTERS", "detect", "discover", "get"]

