"""A failed historical open is not a successful read or missing evidence."""

import json

import pytest

from tests.test_inquiry_core import build, record, result, ts, use


def test_outside_open_explains_actual_and_requested_time_without_leaking_payload(
    tmp_path,
):
    engine = build(
        tmp_path,
        [
            record(1, use("r", "Read", file_path="Input.kt")),
            record(2, result("r", "PRIVATE_FUTURE_CONTENT")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 2)
    with pytest.raises(ValueError) as error:
        engine.query({"op": "open", "ref": ref, "at": ts(1)})
    message = str(error.value)
    assert "record outside requested time scope" in message
    assert "record_at" in message and ts(2)[:-1] in message
    assert "requested_scope" in message and ts(1)[:-1] in message
    frame = engine.investigate([{"op": "open", "ref": ref, "at": ts(1)}])
    assert "PRIVATE_FUTURE_CONTENT" not in frame
    assert "record_at" in frame and "ERROR" in frame
    engine.store.close()


@pytest.mark.parametrize("kind,key", [("agent", "a"), ("file", "A.ets")])
def test_borrowed_scope_keeps_actual_owner_interval_and_native_relations(
    tmp_path, kind, key
):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="A")),
            record(2, result("w")),
        ],
        [
            record(2, use("r", "Read", file_path="B.kt")),
            record(3, result("r", "B input")),
        ],
    )
    parent = engine.query(
        {"op": kind, "key": key, "at": ts(5), "since": ts(3)}
    )
    before = engine.store.rows("SELECT * FROM effects ORDER BY id")
    data = engine.query(
        {
            "op": "open",
            "ref": engine.store.locate("b.jsonl", 2),
            "scope": parent["scope_id"],
        }
    )
    assert data["record_owner"] == "b" and "B input" in data["text"]
    assert data["at"].startswith(ts(3)[:-1])
    assert engine.store.rows("SELECT * FROM effects ORDER BY id") == before
    with pytest.raises(ValueError) as error:
        engine.query(
            {
                "op": "open",
                "ref": engine.store.locate("b.jsonl", 1),
                "scope": parent["scope_id"],
            }
        )
    diagnostic = json.loads(str(error.value).split("; ", 1)[1])
    assert set(diagnostic) == {"ref", "record_at", "requested_scope", "note"}
    assert diagnostic["requested_scope"]["since"].startswith(ts(3)[:-1])
    assert diagnostic["requested_scope"]["at"].startswith(ts(5)[:-1])
    engine.store.close()


def test_expansion_can_inherit_input_list_scope_instead_of_retyping_time(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("r", "Read", file_path="Input.kt")),
            record(2, result("r", "actual input")),
        ],
    )
    inputs = engine.query({"op": "agent", "key": "a", "at": ts(4), "view": "inputs"})
    ref = inputs["rows"][0]["results"][0]
    data = engine.query({"op": "open", "scope": inputs["scope_id"], "ref": ref})
    assert "actual input" in data["text"] and data["record_owner"] == "a"
    assert data["at"].startswith(
        ts(2)[:-1]
    )  # Actual event time, not the inherited cutoff.
    engine.store.close()
