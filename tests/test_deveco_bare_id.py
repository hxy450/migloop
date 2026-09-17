"""DevEco 会话按裸 session id 直读 SQLite 时,id 不是路径:service 层不能把它 abspath 成 <cwd>/ses_...。

回归背景:CLI ``migloop ses_xxx`` 在 2026-09-09 的 HEAD 上报 ``unsupported session transcript: <cwd>\\ses_xxx``,
observation_scope / locate_session 都把裸 id 当相对路径拼了绝对路径;9/3 打的 pyz 还能跑。"""
from __future__ import annotations

import os
from typing import Any

from migloop import adapters, service
from migloop.adapters.base import SessionCandidate

SID = "ses_f7af5baaeffe6O7wX61nFFs0Ad"


def test_observation_scope_keeps_bare_deveco_id(monkeypatch: Any) -> None:
    monkeypatch.delenv("MIGLOOP_FROZEN_POOL", raising=False)
    scope = service.observation_scope(SID)
    assert scope["anchor"] == SID and scope["roots"] == [SID]
    assert scope["mode"] == "live_dynamic"


def test_observation_scope_still_absolutizes_file_paths(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("MIGLOOP_FROZEN_POOL", raising=False)
    p = tmp_path / "abc.jsonl"
    p.write_text("{}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert service.observation_scope("abc.jsonl")["anchor"] == os.path.abspath(str(p))


def test_locate_session_returns_bare_deveco_id(monkeypatch: Any) -> None:
    monkeypatch.delenv("MIGLOOP_FROZEN_POOL", raising=False)
    row = SessionCandidate(mtime=1.0, path=SID, project="game2048", size=10,
                           format="deveco", session_id=SID)
    monkeypatch.setattr(adapters, "discover", lambda roots=None: [row])
    assert service.locate_session("ses_f7af", {}) == SID
    assert adapters.detect(SID).FORMAT == "deveco"
