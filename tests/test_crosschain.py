"""跨会话 root 发现与迁移全程轮卡。

跨会话返修链本身已由两原子账本接管(filestory.build_fix_chains,见
test_insight1_atoms 的跨会话池用例);这里只剩文件系统层面的事实。
"""

from __future__ import annotations


def test_prior_root_discovery_same_tree_and_earlier_only(monkeypatch, tmp_path) -> None:
    """前序发现:同工程树(含父子 cwd) + 文件名时间早于当前;其他工程不掺。"""
    from types import SimpleNamespace

    from migloop import crosschain
    from migloop.adapters import codex

    def mk(name: str) -> str:
        f = tmp_path / name
        f.write_text("{}", encoding="utf-8")
        return str(f)

    cur = mk("rollout-2026-08-21T09-18-20-cur.jsonl")
    early_parent = mk("rollout-2026-08-16T17-54-23-gen.jsonl")
    early_other = mk("rollout-2026-08-15T10-00-00-other.jsonl")
    later_same = mk("rollout-2026-08-22T10-00-00-late.jsonl")
    cwds = {early_parent: "/Users/x", early_other: "/Users/elsewhere",
            later_same: "/Users/x/proj", cur: "/Users/x/proj"}
    monkeypatch.setattr(codex, "iter_sessions", lambda root: [
        SimpleNamespace(path=p) for p in (cur, early_parent, early_other, later_same)])
    monkeypatch.setattr(codex, "session_summary", lambda p: {"cwd": cwds.get(p, "")})
    got = crosschain.find_prior_codex_roots(cur, "/Users/x/proj")
    assert got == [early_parent], "父目录 cwd 算同树;更晚的、别的工程的都排除"


def test_later_root_discovery_mirror(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from migloop import crosschain
    from migloop.adapters import codex

    def mk(name: str) -> str:
        f = tmp_path / name
        f.write_text("{}", encoding="utf-8")
        return str(f)

    cur = mk("rollout-2026-08-16T17-54-23-gen.jsonl")
    later_same = mk("rollout-2026-08-21T09-18-20-fix.jsonl")
    earlier = mk("rollout-2026-08-15T10-00-00-old.jsonl")
    cwds = {later_same: "/Users/x/proj", earlier: "/Users/x/proj", cur: "/Users/x"}
    monkeypatch.setattr(codex, "iter_sessions", lambda root: [
        SimpleNamespace(path=p) for p in (cur, later_same, earlier)])
    monkeypatch.setattr(codex, "session_summary", lambda p: {"cwd": cwds.get(p, "")})
    assert crosschain.find_later_codex_roots(cur, "/Users/x") == [later_same]


def test_journey_rounds_shape() -> None:
    """迁移全程:多轮 trace(时间序)归约成轮卡数据 —— 阶段/规模/修复方都在。"""
    from migloop.crosschain import journey_rounds

    gen = {
        "meta": {"session_id": "01a009fe-x", "cwd": "/u/x",
                 "started_at": "2026-08-16T09:55:00Z", "ended_at": "2026-08-17T03:12:00Z"},
        "stages": [{"stage": "setup", "label": "Setup", "duration_ms": 60000},
                   {"stage": "a2h-spec", "label": "Spec", "duration_ms": 3600000}],
        "totals": {"subagent_transcripts": 54},
        "agents": [{"agent_id": "g", "type": "a2h-activity-converter"}],
        "lineage": {"agents": [], "specs": [],
                    "files": [{"path": "a.ets", "kind": "ets", "writers": ["g"]}]},
    }
    ver = {
        "meta": {"session_id": "01a021e5-y", "cwd": "/u/x/proj",
                 "started_at": "2026-08-21T01:19:00Z", "ended_at": "2026-08-22T15:24:00Z"},
        "stages": [{"stage": "arkts-visual-verify", "label": "Visual Verify",
                    "duration_ms": 7200000}],
        "totals": {"subagent_transcripts": 60},
        "agents": [{"agent_id": "f", "type": "visual-fixer"}],
        "lineage": {"agents": [], "specs": [], "files": []},
    }
    rounds = journey_rounds([gen, ver])
    assert [r["sid8"] for r in rounds] == ["01a009fe", "01a021e5"]
    assert rounds[0]["stages"] == [{"label": "Setup", "duration_ms": 60000},
                                   {"label": "Spec", "duration_ms": 3600000}]
    assert rounds[0]["agents"] == 54 and rounds[0]["ets_files"] == 1
    assert rounds[0]["fixers"] == 0 and rounds[1]["fixers"] == 1
    assert rounds[0]["started_at"] == "2026-08-16T09:55:00Z"
    assert rounds[1]["project"] == "proj"


def _mk_cc(dirp, sid, ts):
    f = dirp / f"{sid}.jsonl"
    f.write_text('{"type":"user","timestamp":"' + ts + '","cwd":"C:/p","sessionId":"'
                 + sid + '","message":{"content":"x"}}\n', encoding="utf-8")
    return str(f)


def test_claude_prior_and_later_roots_by_first_ts(tmp_path) -> None:
    """CC 同工程 = 同 transcript 目录;时间序用首条记录 timestamp
    (文件 mtime 在拷贝/归档后不可靠)。"""
    from migloop import crosschain

    a = _mk_cc(tmp_path, "aaaa1111-0000-4000-8000-000000000001", "2026-08-16T09:00:00Z")
    b = _mk_cc(tmp_path, "bbbb2222-0000-4000-8000-000000000002", "2026-08-20T09:00:00Z")
    c = _mk_cc(tmp_path, "cccc3333-0000-4000-8000-000000000003", "2026-08-22T09:00:00Z")
    (tmp_path / "bbbb2222-0000-4000-8000-000000000002").mkdir()  # 子代理目录不算会话
    assert crosschain.find_prior_claude_roots(b) == [a]
    assert crosschain.find_later_claude_roots(b) == [c]
    assert crosschain.collect_claude_project_roots(b) == [a, b, c]
