"""A bounded lexical result must never certify historical absence."""
from migloop import atoms_text
from tests.test_atoms import MAIN_ID, _call, _ledger


def test_zero_hits_never_certify_nobody_saw_the_requirement(tmp_path):
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:00Z", "w", "Write",
                                   {"file_path": "/proj/A.ets", "content": "known\n"}))
    texts = [atoms_text.render_search(ledger, "not-recorded", agent=MAIN_ID),
             atoms_text.render_search(ledger, "not-recorded", until_ts="2026-01-02T00:00:00Z")]
    for text in texts:
        assert "此范围内未检索到" in text
        assert "不证明" in text
        assert "那一刻之前没人见过" not in text
        assert "它在这个范围内没见过" not in text
