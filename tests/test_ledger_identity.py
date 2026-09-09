"""账本身份由建账快照决定,不随查询时磁盘元数据变化。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from migloop import atoms
from tests.test_atoms import MAIN_ID, _call, _ledger


def _records(content: str = "a") -> list[dict[str, Any]]:
    return _call("2026-01-01T00:00:00Z", "w1", "Write", {"file_path": "/proj/A.ets", "content": content})


def test_identity_is_frozen_and_same_content_survives_copy_and_mtime(tmp_path: Path) -> None:
    first = _ledger(tmp_path / "a", _records())
    original = atoms.ledger_identity(first)
    source = Path(next(iter(first.tag_paths.values())))
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    copied = _ledger(tmp_path / "b", _records())
    assert atoms.ledger_identity(copied) == original
    assert atoms.ledger_identity(first) == original
    rebuilt = _ledger(tmp_path / "a", _records("b"))
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert atoms.ledger_identity(first) == original
    assert atoms.ledger_identity(rebuilt) != original


def test_identity_distinguishes_materialized_coordinates_and_builder(tmp_path: Path, monkeypatch: Any) -> None:
    original = _ledger(tmp_path / "a", _records())
    changed = _ledger(tmp_path / "b", _records())
    changed.agents[MAIN_ID].actions[0].at = 7
    changed._identity = None
    assert atoms.ledger_identity(changed) != atoms.ledger_identity(original)
    monkeypatch.setattr(atoms, "_builder_fingerprint", lambda: "different-builder")
    rebuilt = _ledger(tmp_path / "c", _records())
    assert atoms.ledger_identity(rebuilt) != atoms.ledger_identity(original)
