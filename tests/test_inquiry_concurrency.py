"""Concurrent investigators share facts, not a long exclusive writer lock."""

import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from migloop.inquiry.card import force_review
from migloop.inquiry.engine import Engine, content_text
from migloop.inquiry.report import check
from migloop.inquiry.store import Store
from migloop.inquiry.tree import reviewed_edge
from tests.test_inquiry_compact_card import compact_document
from tests.test_inquiry_force_submission import opaque


def endpoints(engine, doc):
    origin, destination = copy.deepcopy(doc["findings"][0]["nodes"])
    origin.update(key="a", exists=True)
    destination.update(exists=True)
    return origin, destination


def test_force_quote_reads_do_not_expand_ui_or_write_handles(opaque, monkeypatch):
    engine, doc = opaque
    origin, destination = endpoints(engine, doc)
    ref = engine.store.locate("a.jsonl", 1)
    text = content_text(engine.store.source_record(ref)[1])
    before = engine.store.db.total_changes

    def no_navigation(*args, **kwargs):
        raise AssertionError("force validation must not run a UI query")

    monkeypatch.setattr(engine, "query", no_navigation)
    edge = {"relation": "write", "evidence": [{"source": "a.jsonl", "line": 1}]}
    review, = force_review(engine, edge, origin, destination)
    assert review["review"]["quotes"][0]["text"] == text[:1000]
    bound = reviewed_edge(engine, {**edge, **review}, origin, destination, "A")
    assert bound["source"] == "model_review"
    assert engine.store.db.total_changes == before


def test_review_still_rejects_quote_from_after_cutoff(opaque):
    engine, doc = opaque
    origin, destination = endpoints(engine, doc)
    origin["at"] = "2026-01-01T00:00:01Z"
    ref = engine.store.locate("a.jsonl", 2)
    edge = {"relation": "write", "evidence": [ref],
            "review": {"at": origin["at"], "quotes": [{"ref": ref, "text": "wrote /proj/A.ets"}]}}
    with pytest.raises(ValueError, match="outside requested time scope"):
        reviewed_edge(engine, edge, origin, destination, "A")


def test_long_reader_does_not_block_query_coordinate_commit(opaque):
    engine, _ = opaque
    reader = sqlite3.connect(engine.store.path)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM records").fetchone()
    engine.store.db.execute("PRAGMA busy_timeout=100")
    try:
        opened = engine.query({"op": "open", "source": "a.jsonl", "line": 1,
                               "at": "2026-01-01T00:00:05Z"})
        assert "python patch.py" in opened["text"]
        assert not engine.store.db.in_transaction
    finally:
        reader.rollback()
        reader.close()


def test_existing_delete_journal_index_is_upgraded_without_reimport(opaque):
    engine, _ = opaque
    path = engine.store.path
    expected = engine.store.rows("SELECT * FROM records ORDER BY ref")
    engine.store.close()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=DELETE")
    store = Store(path)
    try:
        assert store.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert store.rows("SELECT * FROM records ORDER BY ref") == expected
    finally:
        store.close()


def test_six_investigators_can_save_force_feedback_with_a_reader(opaque):
    engine, old = opaque
    path = engine.store.path
    draft = compact_document(old)
    barrier = Barrier(6)
    reader = sqlite3.connect(path)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM records").fetchone()

    def investigate(number):
        store = Store(path)
        store.db.execute("PRAGMA busy_timeout=1000")
        try:
            worker = Engine(store, session=f"worker-{number}", origin="memory-skill")
            barrier.wait(timeout=10)
            first = check(worker, json.dumps(draft), save=True)
            assert first["unverified_edges"][0]["force_eligible"]
            forced = copy.deepcopy(draft)
            forced["edges"][0].update(force=True, reason="script writes this file",
                                      evidence=[{"source": "a.jsonl", "line": 1}])
            final = check(worker, json.dumps(forced), save=True)
            assert final["mechanical_status"] == "valid"
            assert final["path_status"] == "complete"
            return final["report_id"]
        finally:
            store.close()

    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            identities = list(pool.map(investigate, range(6)))
        assert len(set(identities)) == 6
        assert engine.store.db.execute("SELECT count(*) FROM runs WHERE kind='report'").fetchone()[0] == 12
        assert engine.store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reader.rollback()
        reader.close()
