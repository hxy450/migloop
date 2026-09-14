"""Content must not be hidden behind long advisory headers in a batch prefix."""

import re

from migloop.inquiry.delivery import allocate
from migloop.inquiry.engine import Engine
from tests.test_inquiry_core import build, record, ts, use


def test_input_rows_precede_long_advisory_metadata():
    data = {
        "kind": "inputs",
        "total": 8,
        "next": None,
        "scope": {"kind": "agent", "key": "worker", "at": ts(9)},
        "note": "LONG_ADVISORY " * 500,
        "input_messages": [
            {"cite": "e-task", "at": ts(1), "excerpt": "Initial historical task"}
        ],
        "rows": [
            {"path": f"/project/Input{i}.kt", "results": [f"e-input{i}"]}
            for i in range(8)
        ],
    }
    text = Engine.render(
        1,
        {
            "ok": True,
            "query": {"op": "agent", "key": "worker", "at": ts(9), "view": "inputs"},
            "data": data,
        },
    )
    assert text.index("e-input3") < 2000
    assert text.index("e-input3") < text.index("LONG_ADVISORY")
    assert "e-task" in text[:2000] and data["note"] in text
    assert all(f"e-input{i}" in text for i in range(8))


def test_original_content_and_source_identity_precede_auxiliary_metadata():
    data = {
        "kind": "original",
        "cite": "e-source",
        "source": "a.jsonl",
        "line": 3,
        "at": ts(3),
        "record_owner": "worker",
        "text": "ACTUAL_CONTENT",
        "note": "LONG_ADVISORY " * 500,
        "request_context": {
            "requests": [
                {
                    "cite": "e-request",
                    "argument_preview": "cat Other.kt",
                    "not_effect_proof": True,
                }
            ],
            "unavailable": [],
        },
    }
    text = Engine.render(
        1,
        {
            "ok": True,
            "query": {"op": "open", "ref": "e-source", "at": ts(9)},
            "data": data,
        },
    )
    assert text.index("e-source") < text.index("ACTUAL_CONTENT") < 1000
    assert text.index("ACTUAL_CONTENT") < text.index("LONG_ADVISORY")
    assert "e-request" in text and "cat Other.kt" in text


def test_batch_completes_short_body_and_retains_each_large_result_prefix(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("big", content="X" * 40000, file_path="Big.ets")),
            record(2, use("small", content="Y" * 3600, file_path="Small.ets")),
        ],
    )
    refs = [engine.store.locate("a.jsonl", n) for n in (1, 2)]
    text = engine.investigate(
        [
            {"op": "open", "ref": refs[0], "at": ts(9)},
            {"op": "open", "ref": refs[1], "at": ts(9)},
            {"op": "search", "at": ts(9), "terms": ["not-present"]},
            {"op": "bogus"},
        ]
    )
    ids = re.findall(r"RESULT ([a-f0-9]+)", text)
    assert len(ids) == 4 and "X" * 100 in text and "ERROR" in text
    short = engine.page(ids[1], 0)
    assert "END FRAME next=none" in short and "Y" * 3600 in short
    large = engine.page(ids[0], 0)
    assert "END FRAME next=none" not in large
    offset = int(re.search(r"END FRAME next=(\d+)", large)[1])
    engine.page(ids[0], offset)
    assert engine.page(ids[0], 0) == large
    assert len(engine.trace()) == 4
    engine.store.close()


def test_allocation_never_starves_an_item_below_the_equal_share():
    for count in range(1, 25):
        for sizes in (
            [5000] + [10000] * (count - 1),
            [80 + i * 1700 for i in range(count)],
            [40000] * count,
        ):
            limits = allocate(sizes, 9000)
            old_floor = 9000 // count
            assert all(
                min(size, old_floor) <= limit <= size
                for size, limit in zip(sizes, limits)
            )
            assert sum(limits) <= 9000
