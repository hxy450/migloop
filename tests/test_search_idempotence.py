"""Post-v3 regression: case-duplicate literals must not abort a pool search."""
from migloop import atom_queries, atoms, investigation, search_terms, time_receipts
from tests.test_temporal import source, ts


def test_or_normalization_is_idempotent_and_keeps_first_spelling():
    value = search_terms.normalize("", ["Back", "BACK", "onBackPressed", "back"])
    assert value == ["Back", "onBackPressed"]
    assert search_terms.normalize("", value) == value
    assert search_terms.normalize("", ["Back", "BACK"]) == ["Back"]
    assert search_terms.normalize("", ["Back"]) == ["Back"]


def test_duplicate_pool_query_runs_and_does_not_duplicate_or_leak_records(tmp_path):
    path = source(tmp_path, [
        {"timestamp": ts(1), "text": "Back callback"},
        {"timestamp": ts(2), "text": "BACK callback"},
        {"timestamp": ts(20), "text": "Back AFTER_CUTOFF"},
    ])
    ledger = atoms.build_ledger({"a": atoms.AgentRec("a", "s", sources=[path])})
    args = {"q_any": ["Back", "BACK"], "at": ts(10)}
    batch = investigation.batch(ledger, [{"tool": "search", "args": args}])
    item, = batch["items"]
    assert item["status"] == "ok"
    assert item["data"]["total"] == 2
    assert [r["line"] for r in item["data"]["rows"]] == [1, 2]
    assert "AFTER_CUTOFF" not in str(item["data"])
    assert all(r["matched"] == ["Back"] for r in item["data"]["rows"])
    scalar = atom_queries.render_text(ledger, "", "search", args)
    assert time_receipts.parse(ledger, "search", args, scalar)
    assert search_terms.normalize("", '["Back","BACK"]', http_json=True) == ["Back"]
