import asyncio
import http.client
import json
import re
import threading

import pytest

from migloop.inquiry import interfaces, report
from migloop.inquiry.engine import Engine
from migloop.inquiry.store import Source, Store
from tests.test_inquiry_core import build, record, result, ts, use, valid_report


def test_mcp_continuations_batch_without_rewriting_frames_or_queries(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, {"type": "text", "text": "A" * 20000}),
            record(2, {"type": "text", "text": "B" * 20000}),
        ],
    )
    path = engine.store.path
    engine.store.close()
    server = interfaces.build_mcp(path)

    async def run():
        first = await server.call_tool(
            "investigate",
            {
                "requests": [
                    {"op": "open", "source": "a.jsonl", "line": line, "at": ts(3)}
                    for line in (1, 2)
                ]
            },
        )
        ids = re.findall(r"RESULT ([0-9a-f]+) chars=\d+ range=0:(\d+)", first[0].text)
        requests = [
            {"result_id": identity, "offset": int(offset)} for identity, offset in ids
        ]
        assert len(requests) == 2
        batch = await server.call_tool("page", {"requests": requests})
        singles = [await server.call_tool("page", item) for item in requests]
        assert batch[0].text == "\n\n".join(item[0].text for item in singles)
        assert batch[0].text.count("; CONTEXT ") == 2
        assert "A" * 1000 in batch[0].text and "B" * 1000 in batch[0].text
        invalid = await server.call_tool(
            "page",
            {
                "requests": [
                    {"result_id": "not-owned", "offset": 0},
                    requests[1],
                ]
            },
        )
        assert "PAGE ERROR" in invalid[0].text and singles[1][0].text in invalid[0].text
        with pytest.raises(Exception, match="either"):
            await server.call_tool(
                "page", {"result_id": ids[0][0], "requests": requests}
            )

    asyncio.run(run())
    reopened = Store(path)
    assert len(Engine(reopened).trace()) == 2  # continuations are not new searches
    reopened.close()


def test_mcp_emits_one_readable_body_and_owns_its_trace_session(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="a")),
            record(2, result("w")),
        ],
    )
    path = engine.store.path
    engine.store.close()
    server = interfaces.build_mcp(path)

    async def run():
        tool_names = [tool.name for tool in await server.list_tools()]
        assert tool_names == ["investigate", "page", "submit"]
        blocks = await server.call_tool(
            "investigate", {"requests": [{"op": "file", "key": "A.ets", "at": ts(5)}]}
        )
        assert len(blocks) == 1 and blocks[0].text.startswith("RESULT ")
        assert "END FRAME" in blocks[0].text and "server_sent_only" in blocks[0].text

    asyncio.run(run())
    reopened = Store(path)
    trace = Engine(reopened).trace()
    assert (
        len(trace) == 1 and trace[0]["origin"] == "mcp" and trace[0]["visibility"] == []
    )
    assert trace[0]["session"] != "diagnostic"
    reopened.close()


@pytest.fixture
def http_server(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="a")),
            record(2, result("w")),
        ],
    )
    server = interfaces.make_http(engine.store.path)
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    worker.start()

    def call(path, data=None, origin=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=10
        )
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        try:
            connection.request(
                "GET" if data is None else "POST",
                path,
                body=None if data is None else json.dumps(data).encode(),
                headers=headers,
            )
            response = connection.getresponse()
            body = response.read().decode()
            return response.status, body if path.split("?", 1)[
                0
            ] in ("/", "/tree.js") else json.loads(body)
        finally:
            connection.close()

    yield engine, call
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)
    engine.store.close()
    assert not worker.is_alive()


def test_http_uses_same_kernel_and_manual_queries_do_not_forge_model_visits(
    http_server,
):
    engine, call = http_server
    q = {"op": "file", "key": "A.ets", "at": ts(5)}
    status, data = call("/api/query", q)
    assert status == 200 and data == engine.query(q)
    assert call("/api/trace")[1] == []
    status, page = call("/")
    assert status == 200 and "原因仍是模型主张" in page
    assert "__INQUIRY_CONFIG__" not in page and 'src="/tree.js"' in page
    assert call("/tree.js")[0] == 200
    assert call("/?report=example")[0] == 200
    assert call("/api/query", q, "https://not-the-local-page.example")[0] == 403
    assert call("/api/query", [q])[0] == 400


def test_http_report_original_and_graph_retain_node_causes(http_server):
    engine, call = http_server
    doc = valid_report(engine)
    status, checked = call("/api/report", {"document": json.dumps(doc)})
    assert status == 200 and len(checked["edges"]) == 1
    stored = call("/api/report?id=" + checked["report_id"])[1]
    assert stored["document"] == doc and stored["nodes"][0]["reason"] == "actor claim"
    assert call("/api/trace")[1] == []
    assert call("/api/report", {"document": "schema: ["})[0] == 400


def test_saved_report_rechecks_bytes_instead_of_reusing_stale_green_edges(http_server):
    from pathlib import Path

    engine, call = http_server
    document = valid_report(engine)
    checked = call("/api/report", {"document": json.dumps(document)})[1]
    path = Path(engine.store.rows("SELECT path FROM sources")[0]["path"])
    path.write_bytes(path.read_bytes().replace(b'"content": "a"', b'"content": "b"'))
    loaded = call("/api/report?id=" + checked["report_id"])[1]
    assert loaded["issues"] and not loaded["edges"]
    assert loaded["document"] == document


def test_fabricated_full_path_is_not_certified_by_another_files_basename(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="a")),
            record(2, result("w")),
        ],
    )
    document = valid_report(engine)
    document["findings"][0]["nodes"][1]["key"] = "/invented/A.ets"
    checked = report.check(engine, json.dumps(document))
    assert not checked["nodes"][1]["exists"] and not checked["edges"]
    engine.store.close()


def test_explicit_native_dispatch_not_directory_or_message_proximity(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("task", "Task", prompt="do work")),
            record(2, result("task"), toolUseResult={"agentId": "b"}),
        ],
        [record(3, {"type": "text", "text": "child"})],
    )
    rows = engine.query({"op": "agent", "key": "a", "at": ts(5)})["dispatches"]
    assert len(rows) == 1 and rows[0]["child"] == "b"
    pending = engine.query({"op": "agent", "key": "a", "at": ts(1)})["dispatches"]
    assert len(pending) == 1 and pending[0]["strength"] == "candidate"
    assert pending[0]["result"] is None and pending[0]["identity_known_at_cutoff"] is False
    assert not engine.query({"op": "agent", "key": "a", "at": ts(0)})["dispatches"]
    engine.store.close()


def test_copied_records_do_not_certify_a_unique_owner(tmp_path):
    same = [
        record(1, use("w", file_path="/proj/A.ets"), uuid="shared"),
        record(2, result("w")),
    ]
    engine = build(tmp_path, same, same)
    assert {
        r["strength"] for r in engine.store.rows("SELECT strength FROM effects")
    } == {"candidate"}
    engine.store.close()


def test_same_basename_requires_disambiguation(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("one", file_path="/proj/a/X.ets")),
            record(2, result("one")),
            record(3, use("two", file_path="/proj/b/X.ets")),
            record(4, result("two")),
        ],
    )
    with pytest.raises(ValueError, match="ambiguous"):
        engine.query({"op": "file", "key": "X.ets", "at": ts(5)})
    assert (
        engine.query(
            {"op": "file", "key": "/proj/a/X.ets", "at": ts(5), "view": "relations"}
        )["total"]
        == 1
    )
    engine.store.close()


def test_plain_attachments_are_searchable_but_not_dated_or_owned(tmp_path):
    path = tmp_path / "skill.md"
    path.write_text(
        "timestamp: 2026-01-01T00:00:00Z\nrequirement Café\n", encoding="utf-8"
    )
    store = Store.build(
        tmp_path / "index.sqlite", [Source(str(path), "skill.md", protocol="text")]
    )
    engine = Engine(store)
    assert engine.query({"op": "search", "terms": ["CAFÉ"], "at": ts(5)})["total"] == 0
    assert (
        engine.query({"op": "search", "terms": ["CAFÉ"], "at": ts(5), "undated": True})[
            "total"
        ]
        == 1
    )
    assert not engine.query({"op": "catalog", "kind": "agent"})["rows"]
    store.close()


def test_report_retains_unknown_node_reason_without_inventing_edges(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="a")),
            record(2, result("w")),
        ],
    )
    doc = valid_report(engine)
    doc["findings"][0]["nodes"][0]["key"] = "invented-agent"
    graph = report.check(engine, json.dumps(doc))
    assert (
        graph["nodes"][0]["reason"] == "actor claim" and not graph["nodes"][0]["exists"]
    )
    assert not graph["edges"] and graph["unverified_edges"]
    engine.store.close()


@pytest.mark.parametrize("pointer", ["/message/content/-1", "/message/content/01"])
def test_expansion_rejects_noncanonical_array_pointers(tmp_path, pointer):
    engine = build(tmp_path, [record(1, {"type": "text", "text": "body"})])
    with pytest.raises(ValueError, match="nonnegative"):
        engine.query(
            {
                "op": "open",
                "source": "a.jsonl",
                "line": 1,
                "pointer": pointer,
                "at": ts(5),
            }
        )
    engine.store.close()


def test_diff_is_explicit_evidence_not_recovered_history(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="before")),
            record(2, use("w2", file_path="/proj/A.ets", content="after")),
        ],
    )
    result = engine.query(
        {
            "op": "diff",
            "before": engine.store.locate("a.jsonl", 1),
            "after": engine.store.locate("a.jsonl", 2),
            "before_pointer": "/message/content/0/input/content",
            "after_pointer": "/message/content/0/input/content",
            "at": ts(5),
        }
    )
    assert "-before" in result["text"] and "+after" in result["text"]
    assert (
        engine.query({"op": "blame", "key": "A.ets", "at": ts(5)})["status"]
        == "not_proven"
    )
    engine.store.close()
