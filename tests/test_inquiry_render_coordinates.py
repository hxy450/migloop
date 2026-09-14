"""Rendered actor and operation coordinates remain directly usable by callers."""

import json

import pytest

from migloop.inquiry.engine import Engine
from migloop.inquiry.store import Source, Store
from tests.test_inquiry_core import build, record, result, ts, use
from tests.test_inquiry_response_budget import frames, size


@pytest.fixture
def actors(tmp_path):
    sources = []
    for prefix, start in (("first", 1), ("second", 5)):
        path = tmp_path / f"{prefix}.jsonl"
        rows = [
            record(start, use("r", "Read", file_path="/proj/Spec.md")),
            record(start + 1, result("r", "INPUT CONTENT")),
            record(
                start + 2,
                use("w", file_path="/proj/A.ets", content="OUTPUT CONTENT"),
            ),
            record(start + 3, result("w")),
        ]
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        sources.append(Source(str(path), path.name, f"{prefix}:worker", "/proj"))
    engine = Engine(Store.build(tmp_path / "index.sqlite", sources))
    try:
        yield engine
    finally:
        engine.store.close()


def test_participant_coordinates_distinguish_reused_local_actor_names(actors):
    query = {"op": "file", "key": "A.ets", "at": ts(9), "view": "calls"}
    data = actors.query(query)
    text = Engine.render(1, {"ok": True, "query": query, "data": data})
    for participant, completed in zip(data["participants"], (4, 8)):
        line = next(
            line
            for line in text.splitlines()
            if line.startswith(f"WRITER {participant['agent']} ")
        )
        assert f"write_scope={participant['write_scope']}" in line
        assert f"input_scope={participant['input_scope']}" in line
        scoped = actors.query(
            {"op": "agent", "scope": participant["write_scope"], "view": "records"}
        )["scope"]
        assert scoped["key"] == participant["agent"]
        assert scoped["at"].startswith(ts(completed)[:-1])
    # Native records still precede participant navigation.
    assert text.index(data["rows"][0]["cite"]) < text.index("WRITER ")

    query = {"op": "file", "key": "Spec.md", "at": ts(9), "view": "records"}
    data = actors.query(query)
    text = Engine.render(1, {"ok": True, "query": query, "data": data})
    assert "READER first:worker " in text and "READER second:worker " in text


@pytest.mark.parametrize(
    "line,op,completed",
    [(1, "read", 2), (2, "read", 2), (3, "write", 4), (4, "write", 4)],
)
def test_open_native_links_show_complete_reusable_operation_coordinates(
    actors, line, op, completed
):
    query = {"op": "open", "source": "first.jsonl", "line": line, "at": ts(9)}
    data = actors.query(query)
    text = Engine.render(1, {"ok": True, "query": query, "data": data})
    link = json.loads(
        next(
            row.removeprefix("NATIVE_LINK ")
            for row in text.splitlines()
            if row.startswith("NATIVE_LINK ")
        )
    )
    assert link["agent"] == "first:worker" and link["op"] == op
    assert link["at"].startswith(ts(completed)[:-1])
    assert link["at"] != data["at"] or line in (2, 4)
    for field, expected_line in (("request", completed - 1), ("result", completed)):
        opened = actors.query({"op": "open", "ref": link[field], "at": ts(9)})
        assert opened["line"] == expected_line
        assert opened["record_owner"] == link["agent"]
    assert text.index(data["text"]) < text.index("NATIVE_LINK ")


def test_large_original_keeps_native_coordinates_after_lossless_paging(tmp_path):
    content = '原始内容😀\\"\n' * 3000
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content=content)),
            record(2, result("w")),
        ],
    )
    try:
        query = {"op": "open", "source": "a.jsonl", "line": 1, "at": ts(9)}
        expected = engine.query(query)
        text = engine.investigate([query])
        first = text
        body = ""
        pages = 0
        while True:
            assert size(text) <= 9000
            identity, total, start, end, chunk = next(frames(text))
            assert start == len(body)
            body += chunk
            pages += 1
            if end == total:
                break
            text = engine.page(identity, end)
        assert pages > 1
        assert body == engine.store.rows(
            "SELECT body FROM runs WHERE id=?", (identity,)
        )[0]["body"]
        assert expected["text"] in body
        assert body.index("SELECTED HISTORICAL CONTENT") < body.index("NATIVE_LINK ")
        link = json.loads(
            next(
                line.removeprefix("NATIVE_LINK ")
                for line in body.splitlines()
                if line.startswith("NATIVE_LINK ")
            )
        )
        assert link["at"].startswith(ts(2)[:-1])
        assert link["request"] and link["result"] and link["agent"] == "a"
        assert engine.page(identity, 0) == first
    finally:
        engine.store.close()
