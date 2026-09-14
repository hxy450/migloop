"""Native entry points and excerpt boundaries precede large historical bodies."""

import copy
import json

import pytest

from migloop.inquiry.engine import Engine
from migloop.inquiry.native_text import render_payloads
from tests.test_inquiry_core import build, record, result, ts, use
from tests.test_inquiry_response_budget import frames, size


def entries(text):
    return [
        json.loads(line.removeprefix("NATIVE ENTRY "))
        for line in text.splitlines()
        if line.startswith("NATIVE ENTRY ")
    ]


def test_all_selected_write_entries_precede_first_large_payload(tmp_path):
    bodies = ['初写😀\\"\r\n' * 597, '后写界面\\"\n' * 1194]
    assert [len(body.splitlines()) for body in bodies] == [597, 1194]
    engine = build(
        tmp_path,
        [
            record(1, use("before", file_path="A.ets", content="BEFORE_WINDOW")),
            record(2, result("before")),
            record(3, use("first", file_path="A.ets", content=bodies[0])),
            record(4, result("first")),
            record(7, use("third", file_path="A.ets", content="NEXT_LIST_PAGE")),
            record(8, result("third")),
            record(10, use("future", file_path="A.ets", content="AFTER_CUTOFF")),
            record(11, result("future")),
        ],
        second=[
            record(5, use("second", file_path="A.ets", content=bodies[1])),
            record(6, result("second")),
        ],
    )
    try:
        query = {
            "op": "file", "key": "A.ets", "since": ts(3), "at": ts(9),
            "view": "changes", "limit": 2,
        }
        data = engine.query(query)
        saved = copy.deepcopy(data)
        text = Engine.render(1, {"ok": True, "query": query, "data": data})
        assert data["total"] == 3 and data["next"] == 2
        assert len(data["rows"]) == 2
        first_body = text.index(bodies[0])
        # Regression: the second request used to follow all 597 initial lines.
        assert all(
            text.index(row[field]) < first_body
            for row in data["rows"] for field in ("request", "result")
        )
        index = entries(text)
        assert len(index) == 2
        for entry, row, body in zip(index, data["rows"], bodies):
            for key in ("at", "agent", "op", "strength", "request", "result"):
                assert entry[key] == row[key]
            assert entry["payloads"][0]["snapshot_lines"] == len(body.splitlines())
            assert entry["payloads"][0]["snapshot_chars"] == len(body)
            assert entry["open"] == {
                "op": "open", "ref": row["request"], "at": data["scope"]["at"],
            }
            assert engine.query(entry["open"])["record_owner"] == row["agent"]
            assert text.count(render_payloads(row["payloads"])) == 1
        assert "selected page only; not complete file history" in text
        assert data == saved  # Rendering must not change selection or scope.
        assert "BEFORE_WINDOW" not in text and "AFTER_CUTOFF" not in text
        assert "NEXT_LIST_PAGE" not in text

        first_frame = engine.investigate([query])
        assert len(entries(first_frame)) == 2
        rebuilt, page = "", first_frame
        while True:
            assert size(page) <= 9000
            identity, total, start, end, chunk = next(frames(page))
            assert start == len(rebuilt)
            rebuilt += chunk
            if end == total:
                break
            page = engine.page(identity, end)
        assert rebuilt == text  # Includes Unicode, quotes and original CRLFs.
        assert engine.page(identity, 0) == first_frame
    finally:
        engine.store.close()


def test_excerpt_metadata_and_open_keep_original_identity_and_cutoff(tmp_path):
    engine = build(tmp_path, [record(1, {"type": "text", "text": "开头" * 500 + "NEEDLE"})])
    try:
        query = {"op": "search", "at": ts(3), "terms": ["NEEDLE"]}
        data = engine.query(query)
        row = data["rows"][0]
        text = Engine.render(1, {"ok": True, "query": query, "data": data})
        metadata = json.loads(text.split("PREVIEW ", 1)[1].split(" | ", 1)[0])
        assert metadata["preview_only"] is True
        assert metadata["original_chars"] == row["chars"]
        assert metadata["excerpt_offset"] == row["excerpt_offset"]
        assert metadata["source"] == row["name"]
        assert metadata["line"] == row["line"]
        assert metadata["open"] == {
            "op": "open", "ref": row["cite"], "at": data["scope"]["at"],
        }
        assert engine.query(metadata["open"])["text"].endswith("NEEDLE")
    finally:
        engine.store.close()


def test_excerpt_does_not_invent_missing_original_metadata():
    row = {"ref": "e-old", "at": ts(1), "agent": "worker", "excerpt": "legacy"}
    text = Engine.render(1, {
        "ok": True, "query": {"op": "agent", "key": "worker", "at": ts(3)},
        "data": {"kind": "records", "rows": [row]},
    })
    metadata = json.loads(text.split("PREVIEW ", 1)[1].split(" | ", 1)[0])
    assert metadata == {"open": {"op": "open", "ref": "e-old", "at": ts(3)}}


@pytest.mark.parametrize("view", ["changes", "outline"])
def test_empty_and_outline_views_do_not_gain_a_payload_directory(tmp_path, view):
    engine = build(tmp_path, [record(1, use("w", file_path="A.ets", content="BODY"))])
    try:
        query = {"op": "file", "key": "A.ets", "at": ts(0), "view": view}
        empty = engine.query(query)
        text = Engine.render(1, {"ok": True, "query": query, "data": empty})
        assert empty["rows"] == [] and "NATIVE ENTRY " not in text
        if view == "outline":
            query["at"] = ts(3)
            data = engine.query(query)
            text = Engine.render(1, {"ok": True, "query": query, "data": data})
            assert "NATIVE ENTRY " not in text
            assert "snapshot_folded" in text and "END NATIVE" in text
            assert "\nBODY\n" not in text
    finally:
        engine.store.close()
