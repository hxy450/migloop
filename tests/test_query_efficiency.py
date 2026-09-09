"""Smaller query views retain a recoverable evidence surface and exact anchor."""
from __future__ import annotations

from migloop import atoms_text, service
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
