"""A result-to-request lookup must not scan the whole earlier event pool."""

from migloop.inquiry.store import timestamp
from tests.test_inquiry_core import build, record, result, ts, use


def test_return_pair_lookup_uses_reverse_index_without_changing_identity(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("r", "Bash", command="probe")),
            record(2, result("r", "actual output")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 2)
    sql = "SELECT c.tool FROM pairs p JOIN calls c ON p.a=c.record JOIN records a ON a.ref=p.a WHERE p.b=? AND a.at<=?"
    args = (ref, timestamp(ts(3)))
    plans = engine.store.rows("EXPLAIN QUERY PLAN " + sql, args)
    assert any("pairs_by_result" in row["detail"] for row in plans)
    assert not any("record_time" in row["detail"] for row in plans)
    assert engine.store.rows(sql, args) == [{"tool": "Bash"}]
    assert engine.store.rows(sql, (ref, timestamp(ts(0)))) == []
    assert (
        engine.query({"op": "agent", "key": "a", "at": ts(3), "view": "returns"})[
            "rows"
        ][0]["ref"]
        == ref
    )
    engine.store.close()
