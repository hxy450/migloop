"""Smaller query views retain a recoverable evidence surface and exact anchor."""
from __future__ import annotations

from migloop import atoms, atoms_text, service
from tests.test_atoms import MAIN_ID, _call, _ledger


def test_explicit_anchor_diff_range_does_not_change_opened_version(tmp_path):
    path = "/proj/entry/A.ets"
    led = _ledger(tmp_path, [
        *_call("2026-01-01T00:00:00Z", "w", "Write", {"file_path": path, "content": "a\n"}),
        *_call("2026-01-01T00:00:10Z", "e1", "Edit", {"file_path": path, "old_string": "a", "new_string": "b"}),
        *_call("2026-01-01T00:00:20Z", "e2", "Edit", {"file_path": path, "old_string": "b", "new_string": "c"}),
    ])
    text = atoms_text.render_file(led, path, 3, diff=True, v_from=2, v_to=2, m_n=0)
    assert "@v3" in text.splitlines()[0]
    assert "+b" in text and "+c" not in text
    assert atoms_text.render_file(led, path, 1, diff=True, v_from=2, v_to=2).startswith("⛔")
    assert atoms_text.render_file(led, path, 3, diff=True, v_from=3, v_to=2).startswith("⛔")


def test_zero_mentions_is_count_only_and_explicit_expansion_recovers_candidates(tmp_path):
    path = "/proj/entry/A.ets"
    led = _ledger(tmp_path, [
        *_call("2026-01-01T00:00:00Z", "w", "Write", {"file_path": path, "content": "a\n"}),
        *[r for i in range(1, 16) for r in _call(f"2026-01-01T00:00:{i * 2:02d}Z", f"c{i}", "Bash",
                                               {"command": f"unknown_inspector TRACE_CANDIDATE_{i} {path}"})],
    ])
    small = atoms_text.render_file(led, path, 1, m_n=0)
    full = atoms_text.render_file(led, path, 1, m_n=40)
    assert "m_n=40" in small and "未展开" in small
    assert "TRACE_CANDIDATE" not in small
    assert "TRACE_CANDIDATE_1" in full and "TRACE_CANDIDATE_15" in full
    assert len(small) < len(full) * 0.6


def test_http_text_preserves_zero_mentions_and_input_paging(tmp_path, monkeypatch):
    path = "/proj/entry/A.ets"
    led = _ledger(tmp_path, [*_call("2026-01-01T00:00:00Z", "w", "Write", {
        "file_path": path, "content": "prefix " * 1000 + "TAIL_MARKER"
    })])
    monkeypatch.setattr(service, "session_ledger", lambda _: led)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    seq = led.agents[MAIN_ID].actions[0].seq
    text = service.atom_text("ignored", "action", {"id": MAIN_ID, "seq": seq, "part": "input", "find": "TAIL_MARKER", "max_chars": 512})
    assert "TAIL_MARKER" in text
    got = {}
    monkeypatch.setattr(atoms_text, "render_file", lambda *a, **kw: got.update(kw) or "ok")
    service.atom_text("ignored", "file", {"path": path, "v": 1, "m_n": 0})
    assert got["m_n"] == 0


def test_action_candidate_pages_do_not_change_raw_window(tmp_path, monkeypatch):
    led = _ledger(tmp_path, [*_call("2026-01-01T00:00:00Z", "w", "Write", {
        "file_path": "/proj/A.ets", "content": "prefix " * 100 + "EVIDENCE_MARKER" + " tail" * 100
    })])
    seq = led.agents[MAIN_ID].actions[0].seq
    links = atoms.action_links(led, MAIN_ID, seq)
    links["possible"] = [{"path": f"/proj/P{i}.ets", "v": 1, "ambiguous": False,
                           "ctx": "CANDIDATE_" + str(i) + " " + "context " * 30} for i in range(15)]
    monkeypatch.setattr(atoms, "action_links", lambda *args: links)
    args = dict(part="input", find="EVIDENCE_MARKER", max_chars=256)
    small = atoms_text.render_action(led, MAIN_ID, seq, m_n=0, **args)
    full = atoms_text.render_action(led, MAIN_ID, seq, m_n=40, **args)
    assert small.split("## 输入", 1)[1] == full.split("## 输入", 1)[1]
    assert "未展开 15 条" in small and "m_n=40" in small
    assert "CANDIDATE_" not in small and "EVIDENCE_MARKER" in small
    assert "事件 id" in small and "账本记到的读写" in small
    assert len(small) < len(full) * 0.5
    pages = [atoms_text.render_action(led, MAIN_ID, seq, m_n=4, m_from=i, **args) for i in (1, 5, 9, 13)]
    import re
    assert [int(n) for page in pages for n in re.findall(r"CANDIDATE_(\d+) ", page)] == list(range(15))
    assert "还有 11 条" in pages[0] and "还有" not in pages[-1]
    assert "超出 15 条" in atoms_text.render_action(led, MAIN_ID, seq, m_n=4, m_from=99, **args)


def test_http_action_candidate_defaults_and_explicit_page(tmp_path, monkeypatch):
    led = _ledger(tmp_path, [*_call("2026-01-01T00:00:00Z", "w", "Write", {
        "file_path": "/proj/A.ets", "content": "a\n"})])
    monkeypatch.setattr(service, "session_ledger", lambda _: led)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    got = {}
    monkeypatch.setattr(atoms_text, "render_action", lambda *args, **kwargs: got.update(kwargs) or "ok")
    service.atom_text("ignored", "action", {"id": MAIN_ID, "seq": 1})
    assert got["m_n"] == 0 and got["m_from"] == 1
    service.atom_text("ignored", "action", {"id": MAIN_ID, "seq": 1, "m_n": 40, "m_from": 41})
    assert got["m_n"] == 40 and got["m_from"] == 41


def test_manifest_text_keeps_every_version_and_candidate_with_uncertainty(monkeypatch):
    from migloop import coverage
    monkeypatch.setattr(coverage, "manifest", lambda *args: {
        "file": "/proj/A.ets", "errors": [], "candidate_scope": {"window_scope": "actor full window"},
        "items": [{"v": 2, "source": "edit", "content_known": True,
                   "event": {"ref": "#abc:1@L10"}, "change": {"text": "+line"}}],
        "candidates": [{"id": "candidate:" + "a" * 20, "ref": "#abc:2@L20", "agent": "fixer",
                        "ts": "2026-01-01", "reason": "方向未知", "ctx": "possible change"}]})
    text = atoms_text.render_repair_manifest(object(), {}, "A.ets", "/proj")
    assert "file:A.ets@v2" in text and "candidate:" + "a" * 20 in text
    assert "#abc:1@L10" in text and "#abc:2@L20" in text and "actor full window" in text
    assert "候选不等于修复" in text and "已交代不等于已查清" in text
