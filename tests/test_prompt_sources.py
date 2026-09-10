"""Prompt text keeps its own location; neighboring system reminders are not substitutes."""
from migloop import atom_queries, atoms_text, atoms
from tests.test_atoms import _ledger, _call, _rec


def ledger_with_prompt(tmp_path, body="exact task"):
    child = [_rec("2026-01-01T00:00:01Z", "user", body),
             _rec("2026-01-01T00:00:02Z", "user", "<system-reminder>active agent</system-reminder>"),
             *_call("2026-01-01T00:00:03Z", "w", "Write", {"file_path": "/proj/A.ets", "content": "a"})]
    main = _call("2026-01-01T00:00:00Z", "d", "Agent", {"prompt": body}, "done", toolUseResult={"agentId": "c"})
    return _ledger(tmp_path, main, {"agent-c": child})


def test_prompt_pointer_is_exact_own_record_not_next_system_reminder(tmp_path):
    ledger = ledger_with_prompt(tmp_path)
    before = atoms.ledger_identity(ledger)
    data = atom_queries.agent_data(ledger, "agent-c", 1)
    sources = data["prompt_sources"]
    assert sources["total"] == 1 and sources["omitted"] == 0
    row = sources["matches"][0]
    assert row["loc"].startswith("1·")
    text = atom_queries.render_text(ledger, "/proj", "agent", {"id": "agent-c", "v": 1})
    pointer_line = next(line for line in text.splitlines() if line.startswith("同文原始记录："))
    assert atoms_text._core(row["seq"], row["loc"]) in pointer_line and "@L2" not in pointer_line
    assert atoms.ledger_identity(ledger) == before


def test_long_prompt_is_never_captioned_full_text(tmp_path):
    ledger = ledger_with_prompt(tmp_path, "task " * 3000)
    text = atom_queries.render_text(ledger, "/proj", "agent", {"id": "agent-c", "v": 1})
    assert "派发指令(文字片段" in text and "不是全文" in text
    assert "派发指令(全文)" not in text


def test_no_matching_record_does_not_borrow_a_different_instruction(tmp_path):
    ledger = ledger_with_prompt(tmp_path)
    ledger.agents["agent-c"].prompt = "unlocated prompt"
    data = atom_queries.agent_data(ledger, "agent-c", 1)
    assert data["prompt_sources"]["matches"] == []
    text = atom_queries.render_text(ledger, "/proj", "agent", {"id": "agent-c", "v": 1})
    assert "不要借系统提醒" in text and "同文原始记录：" not in text


def test_version_window_does_not_reintroduce_excluded_prompt_location(tmp_path):
    ledger = ledger_with_prompt(tmp_path)
    data = atom_queries.agent_data(ledger, "agent-c", 1, since=1)
    assert data["prompt_sources"]["matches"] == []
