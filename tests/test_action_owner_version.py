"""Action provenance survives when its feeding slot is not an agent version."""
import pytest

from migloop import atoms, atoms_text, verdict
from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call, _rec


def _history(tmp_path, *, effects=True):
    rows = _read_call("2026-01-01T00:00:00Z", "read-before", "/proj/input.md", "before evidence\n")
    if effects:
        rows += _call("2026-01-01T00:00:10Z", "write-first", "Write",
                      {"file_path": "/proj/output.md", "content": "first\n"})
        rows += _read_call("2026-01-01T00:00:20Z", "read-middle", "/proj/input.md", "middle evidence\n")
        rows += _call("2026-01-01T00:00:30Z", "write-last", "Write",
                      {"file_path": "/proj/output.md", "content": "last\n"})
    rows += _call("2026-01-01T00:00:40Z", "read-tail", "Read", {"file_path": "/proj/input.md"}, "TAIL_READ_EVIDENCE\n")
    rows += [_rec("2026-01-01T00:00:50Z", "assistant", [{"type": "text", "text": "TAIL_SUMMARY_EVIDENCE"}])]
    return _ledger(tmp_path, rows)


@pytest.mark.parametrize("name,version,is_effect", [
    ("read-before", 1, False), ("write-first", 1, True),
    ("read-middle", 2, False), ("write-last", 2, True),
])
def test_actions_keep_real_effect_or_next_effect_navigation(tmp_path, name, version, is_effect):
    ledger = _history(tmp_path)
    action = next(a for a in ledger.agents[MAIN_ID].actions if a.tuid == name)
    links = atoms.action_links(ledger, MAIN_ID, action.seq)
    assert links["ver"] == links["agent_v"] == version
    assert links["feeding_slot"] == action.at
    assert links["n_versions"] == 2 and links["after_last_effect"] is False
    assert links["is_effect"] is is_effect
    text = atoms_text.render_action(ledger, MAIN_ID, action.seq)
    assert f"→ agent({MAIN_ID}, v={version})" in text


@pytest.mark.parametrize("kind,marker", [("read", "TAIL_READ_EVIDENCE"), ("say", "TAIL_SUMMARY_EVIDENCE")])
def test_tail_actions_retain_raw_source_without_fabricating_or_rebinding_version(tmp_path, kind, marker):
    ledger = _history(tmp_path)
    action = next(a for a in ledger.agents[MAIN_ID].actions
                  if (a.tuid == "read-tail" if kind == "read" else a.kind == "say"))
    assert action.ver is None and action.at == 3
    raw_before = atoms.action_raw(ledger, MAIN_ID, action.seq)
    links = atoms.action_links(ledger, MAIN_ID, action.seq)
    assert links["ver"] is None and links["agent_v"] is None
    assert links["feeding_slot"] == 3 and links["n_versions"] == 2
    assert links["after_last_effect"] is True and links["is_effect"] is False
    text = atoms_text.render_action(ledger, MAIN_ID, action.seq, max_chars=5000)
    assert "收尾后" in text and "喂 v3" not in text
    assert f"→ agent({MAIN_ID}, v=" not in text  # Not silently rebound to v2, either.
    assert marker in text and "事件 id " in text
    assert atoms.action_raw(ledger, MAIN_ID, action.seq) == raw_before
    assert action.src is not None and action.at == 3


def test_zero_effect_agent_has_raw_actions_but_no_v1_navigation(tmp_path):
    ledger = _history(tmp_path, effects=False)
    owner = ledger.agents[MAIN_ID]
    assert owner.n_versions == 0
    for action in owner.actions:
        links = atoms.action_links(ledger, MAIN_ID, action.seq)
        assert links["ver"] is None and links["agent_v"] is None
        assert links["feeding_slot"] == 1 and links["n_versions"] == 0
        assert links["after_last_effect"] is True
        text = atoms_text.render_action(ledger, MAIN_ID, action.seq, max_chars=5000)
        assert "未形成" in text and "喂 v1" not in text
        assert f"→ agent({MAIN_ID}, v=" not in text
    assert "TAIL_SUMMARY_EVIDENCE" in text


def test_action_owner_unknown_still_returns_no_links(tmp_path):
    ledger = _history(tmp_path)
    assert atoms.action_links(ledger, "missing", 1) == {}
    assert atoms.action_links(ledger, MAIN_ID, -99) == {}


def test_tail_action_supplies_resolvable_canonical_reference_not_only_event_id(tmp_path):
    ledger = _history(tmp_path)
    action = next(a for a in ledger.agents[MAIN_ID].actions if a.kind == "say")
    text = atoms_text.render_action(ledger, MAIN_ID, action.seq)
    reference = next(line.removeprefix("原文引用: ") for line in text.splitlines() if line.startswith("原文引用: "))
    resolved = verdict.resolve_evidence(ledger, reference)
    assert resolved["status"] == "ok" and resolved["seq"] == action.seq
    assert reference == atoms_text._core(action.seq, ledger.locs[action.seq])
    assert atoms.event_id(ledger, MAIN_ID, action.seq) in text


def test_missing_locator_is_disclosed_without_inventing_a_canonical_reference(tmp_path):
    ledger = _history(tmp_path)
    action = next(a for a in ledger.agents[MAIN_ID].actions if a.kind == "say")
    ledger.locs.pop(action.seq, None)
    text = atoms_text.render_action(ledger, MAIN_ID, action.seq)
    reference = next(line for line in text.splitlines() if line.startswith("原文引用: "))
    assert "未知" in reference and "#" not in reference and "@L" not in reference
    assert "TAIL_SUMMARY_EVIDENCE" in text and "事件 id " in text
