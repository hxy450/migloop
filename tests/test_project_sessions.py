"""同工程 root 会话的前后查找(project_sessions):报告页跨会话提示与冻结池以外的 prior / later 都走这里。

用例照 tests/test_crosschain.py 的发现部分改写(crosschain 随返修链路移到 a2h-memory 的 fixchain/);
另加一条:首条时刻跳过 api-request-blob 行。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from migloop import project_sessions
from migloop.adapters import codex


def _mk(tmp_path, name: str) -> str:
    f = tmp_path / name
    f.write_text("{}", encoding="utf-8")
    return str(f)


def test_prior_codex_roots_same_tree_and_earlier_only(monkeypatch, tmp_path) -> None:
    """前序发现:同工程树(含父子 cwd) + 文件名时间早于当前;其他工程不掺。"""
    cur = _mk(tmp_path, "rollout-2026-08-21T09-18-20-cur.jsonl")
    early_parent = _mk(tmp_path, "rollout-2026-08-16T17-54-23-gen.jsonl")
    early_other = _mk(tmp_path, "rollout-2026-08-15T10-00-00-other.jsonl")
    later_same = _mk(tmp_path, "rollout-2026-08-22T10-00-00-late.jsonl")
    cwds = {early_parent: "/Users/x", early_other: "/Users/elsewhere",
            later_same: "/Users/x/proj", cur: "/Users/x/proj"}
    monkeypatch.setattr(codex, "iter_sessions", lambda root: [
        SimpleNamespace(path=p) for p in (cur, early_parent, early_other, later_same)])
    monkeypatch.setattr(codex, "session_summary", lambda p: {"cwd": cwds.get(p, "")})
    assert project_sessions.find_prior_codex_roots(cur, "/Users/x/proj") == [early_parent]


def test_later_codex_roots_mirror(monkeypatch, tmp_path) -> None:
    cur = _mk(tmp_path, "rollout-2026-08-16T17-54-23-gen.jsonl")
    later_same = _mk(tmp_path, "rollout-2026-08-21T09-18-20-fix.jsonl")
    earlier = _mk(tmp_path, "rollout-2026-08-15T10-00-00-old.jsonl")
    cwds = {later_same: "/Users/x/proj", earlier: "/Users/x/proj", cur: "/Users/x"}
    monkeypatch.setattr(codex, "iter_sessions", lambda root: [
        SimpleNamespace(path=p) for p in (cur, later_same, earlier)])
    monkeypatch.setattr(codex, "session_summary", lambda p: {"cwd": cwds.get(p, "")})
    assert project_sessions.find_later_codex_roots(cur, "/Users/x") == [later_same]


def _mk_cc(dirp, sid, ts, blob_ts=None):
    f = dirp / f"{sid}.jsonl"
    rows = []
    if blob_ts:
        rows.append({"type": "api-request-blob", "timestamp": blob_ts})
    rows.append({"type": "user", "timestamp": ts, "cwd": "C:/p", "sessionId": sid, "message": {"content": "x"}})
    f.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(f)


def test_claude_prior_and_later_roots_by_first_ts(tmp_path) -> None:
    """CC 同工程 = 同 transcript 目录;时间序用首条记录 timestamp(文件 mtime 在拷贝/归档后不可靠)。"""
    a = _mk_cc(tmp_path, "aaaa1111-0000-4000-8000-000000000001", "2026-08-16T09:00:00Z")
    b = _mk_cc(tmp_path, "bbbb2222-0000-4000-8000-000000000002", "2026-08-20T09:00:00Z")
    c = _mk_cc(tmp_path, "cccc3333-0000-4000-8000-000000000003", "2026-08-22T09:00:00Z")
    (tmp_path / "bbbb2222-0000-4000-8000-000000000002").mkdir()  # 子代理目录不算会话
    assert project_sessions.find_prior_claude_roots(b) == [a]
    assert project_sessions.find_later_claude_roots(b) == [c]
    assert project_sessions.claude_project_roots(b) == [a, b, c]


def test_first_record_ts_skips_request_blob_rows(tmp_path) -> None:
    """api-request-blob 行是请求的再存一份,它的时刻不是会话开始时刻。"""
    a = _mk_cc(tmp_path, "aaaa1111-0000-4000-8000-000000000001", "2026-08-16T09:00:00Z",
               blob_ts="2026-08-25T00:00:00Z")
    b = _mk_cc(tmp_path, "bbbb2222-0000-4000-8000-000000000002", "2026-08-20T09:00:00Z")
    assert project_sessions.first_record_ts(a) == "2026-08-16T09:00:00Z"
    assert project_sessions.find_prior_claude_roots(b) == [a]
