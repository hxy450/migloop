"""Whole MCP responses must fit, and paging must reconstruct the exact body."""

import asyncio
import json
import os
import re
import runpy
import sys
from pathlib import Path

import pytest

from migloop.inquiry.engine import Engine
from migloop.inquiry.interfaces import build_mcp
from migloop.inquiry.store import Store
from tests.test_inquiry_core import build, record, result, ts, use


def size(text):
    return len(json.dumps(text, ensure_ascii=False).encode("utf-8"))


def frames(text):
    pattern = r"RESULT ([a-f0-9]{16}) chars=(\d+) range=(\d+):(\d+)\n"
    for match in re.finditer(pattern, text):
        identity, total, start, end = match.groups()
        chunk = text[match.end() : match.end() + int(end) - int(start)]
        yield identity, int(total), int(start), int(end), chunk


def test_audit_script_pages_large_details_and_rejects_hash_drift():
    script = (
        Path(__file__).resolve().parents[1]
        / "docs/skills/migloop-investigate/scripts/check_card.py"
    )
    page = runpy.run_path(str(script))["console_page"]
    result = {
        "report_id": "r",
        "status": "draft",
        "loadable": True,
        "semantic_verified": False,
        "issues": ['完整错误😀\\"\n' * 10000],
    }
    text = page(result)
    body = ""
    while True:
        assert size(text) <= 9000
        envelope = json.loads(text)
        assert envelope["status"] == "draft" and not envelope["semantic_verified"]
        current = envelope["audit_page"]
        assert current["start"] == len(body)
        body += current["text"]
        if current["next"] is None:
            break
        text = page(result, current["next"], current["body_sha256"])
    assert json.loads(body) == result
    with pytest.raises(ValueError, match="changed"):
        page({**result, "status": "changed"}, 1, current["body_sha256"])
    with pytest.raises(ValueError, match="expect-sha256"):
        page(result, 1)


def test_four_large_unicode_continuations_fit_and_reconstruct(tmp_path):
    engine = build(
        tmp_path,
        [
            record(n, {"type": "text", "text": ('汉字😀\\"\n' + str(n)) * 5000})
            for n in range(1, 5)
        ],
    )
    path = engine.store.path
    engine.store.close()
    asyncio.run(collect_four(build_mcp(path), path))


def test_long_request_context_keeps_identity_and_complete_body(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1, use("read", "Bash", command="cat /" + "长路径" * 1000 + "/Spec.md")
            ),
            record(2, result("read", "完整规格" * 10000)),
        ],
    )
    ref = engine.store.locate("a.jsonl", 2)
    first = engine.investigate([{"op": "open", "ref": ref, "at": ts(9)}])
    context = json.loads(first.rsplit("; CONTEXT ", 1)[1])
    assert (
        context["cite"] == engine.query({"op": "open", "ref": ref, "at": ts(9)})["cite"]
    )
    assert context["record_owner"] == "a"
    assert "details_in_result" in context
    identity = next(frames(first))[0]
    parts, text = [], first
    while True:
        assert size(text) <= 9000
        _, total, start, end, chunk = next(frames(text))
        assert start == sum(map(len, parts))
        parts.append(chunk)
        if end == total:
            break
        text = engine.page(identity, end)
    original = engine.store.rows("SELECT body FROM runs WHERE id=?", (identity,))[0][
        "body"
    ]
    assert "".join(parts) == original and "长路径" in original
    engine.store.close()


def test_actual_stdio_mcp_roundtrip_preserves_large_unicode_body(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    engine = build(
        tmp_path, [record(1, {"type": "text", "text": '中文😀\\"\n' * 10000})]
    )
    path = engine.store.path
    engine.store.close()
    params = StdioServerParameters(
        command=sys.executable,
        args=["-B", "-X", "utf8", "-m", "migloop.inquiry", "--db", str(path), "mcp"],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        },
    )

    async def run():
        with (tmp_path / "mcp-stderr.log").open("w", encoding="utf-8") as log:
            async with stdio_client(params, errlog=log) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    reply = await session.call_tool(
                        "investigate",
                        {
                            "requests": [
                                {
                                    "op": "open",
                                    "source": "a.jsonl",
                                    "line": 1,
                                    "at": ts(9),
                                }
                            ]
                        },
                    )
                    body = ""
                    while True:
                        assert not reply.isError and len(reply.content) == 1
                        assert len(reply.model_dump_json().encode("utf-8")) < 10000
                        text = reply.content[0].text
                        assert size(text) <= 9000
                        identity, total, start, end, chunk = next(frames(text))
                        assert start == len(body)
                        body += chunk
                        if end == total:
                            break
                        reply = await session.call_tool(
                            "page", {"result_id": identity, "offset": end}
                        )
                    store = Store(path)
                    assert (
                        body
                        == store.rows("SELECT body FROM runs WHERE id=?", (identity,))[
                            0
                        ]["body"]
                    )
                    store.close()

    asyncio.run(run())


async def collect_four(server, path):
    blocks = await server.call_tool(
        "investigate",
        {
            "requests": [
                {"op": "open", "source": "a.jsonl", "line": n, "at": ts(9)}
                for n in range(1, 5)
            ]
        },
    )
    rebuilt, pending = {}, []
    for _ in range(1000):
        text = blocks[0].text
        assert size(text) <= 9000
        for identity, total, start, end, chunk in frames(text):
            assert start == len(rebuilt.setdefault(identity, ""))
            rebuilt[identity] += chunk
            if end < total:
                pending.append({"result_id": identity, "offset": end})
        deferred = re.search(r"^DEFERRED (.+)$", text, re.MULTILINE)
        if deferred:
            pending.extend(json.loads(deferred[1])["requests"])
        if not pending:
            break
        batch, pending = pending[:4], pending[4:]
        blocks = await server.call_tool("page", {"requests": batch})
    else:
        raise AssertionError("continuation made no progress")
    store = Store(path)
    try:
        originals = dict(
            store.db.execute("SELECT id,body FROM runs WHERE kind='query'")
        )
        assert rebuilt == originals and len(originals) == 4
    finally:
        store.close()


def test_cached_frames_defer_without_rewriting_or_recording_unsent_data(tmp_path):
    engine = build(
        tmp_path,
        [record(n, {"type": "text", "text": str(n) * 30000}) for n in range(1, 5)],
    )
    saved, requests = {}, []
    for n in range(1, 5):
        text = engine.investigate(
            [{"op": "open", "source": "a.jsonl", "line": n, "at": ts(9)}]
        )
        identity = next(frames(text))[0]
        saved[identity] = text
        requests.append({"result_id": identity, "offset": 0})
    before = engine.store.rows("SELECT * FROM frames ORDER BY run,offset")
    while requests:
        text = engine.pages(requests)
        assert size(text) <= 9000
        assert any(original in text for original in saved.values())
        marker = re.search(r"^DEFERRED (.+)$", text, re.MULTILINE)
        requests = json.loads(marker[1])["requests"] if marker else []
    assert engine.store.rows("SELECT * FROM frames ORDER BY run,offset") == before
    engine.store.close()


def test_large_feedback_is_lossless_owned_and_not_a_fake_investigation(
    tmp_path, monkeypatch
):
    from migloop.inquiry import feedback, interfaces

    engine = build(tmp_path, [record(1, {"type": "text", "text": "body"})])
    path = engine.store.path
    engine.store.close()
    summary = {
        "report_id": "report",
        "source_sha256": "hash",
        "delivery": {"status": "draft"},
        "issues": [{"message": "需核对真实读写，不能改时间迁就结论。" * 1000}],
    }
    monkeypatch.setattr(
        interfaces, "check", lambda *a, **k: {"submission_format": "coordinates/1"}
    )
    monkeypatch.setattr(feedback, "compact_feedback", lambda graph: summary)
    server = build_mcp(path)

    async def run():
        result = (await server.call_tool("submit", {"card": {}}))[0].text
        assert size(result) <= 9000
        receipt = json.loads(result)
        assert receipt["delivery"]["status"] == "draft"
        cursor = {k: receipt["feedback"][k] for k in ("result_id", "offset")}
        body = ""
        while True:
            text = (await server.call_tool("page", cursor))[0].text
            assert size(text) <= 9000
            _, total, start, end, chunk = next(frames(text))
            assert start == len(body)
            body += chunk
            if end == total:
                break
            cursor["offset"] = end
        assert json.loads(body) == summary
        other = build_mcp(path)
        with pytest.raises(Exception, match="different investigator"):
            await other.call_tool("page", {"result_id": cursor["result_id"]})

    asyncio.run(run())
    store = Store(path)
    assert Engine(store).trace() == []
    assert (
        store.db.execute("SELECT count(*) FROM runs WHERE kind='feedback'").fetchone()[
            0
        ]
        == 1
    )
    store.close()


def test_24_queries_long_context_errors_and_duplicates_keep_all_bodies(tmp_path):
    engine = build(tmp_path, [record(1, {"type": "text", "text": "body"})])
    # Large metadata is also saved in the result body, not duplicated in every frame.
    queries = [{"op": "agent", "key": "missing-" + "长路径" * 3000, "at": ts(9)}] * 24
    text = engine.investigate(queries)
    assert size(text) <= 9000
    pending, rebuilt = [], {}
    for _ in range(1000):
        for identity, total, start, end, chunk in frames(text):
            assert start == len(rebuilt.setdefault(identity, ""))
            rebuilt[identity] += chunk
            if end < total:
                pending.append({"result_id": identity, "offset": end})
        marker = re.search(r"^DEFERRED (.+)$", text, re.MULTILINE)
        if marker:
            pending.extend(json.loads(marker[1])["requests"])
        if not pending:
            break
        batch, pending = pending[:4], pending[4:]
        text = engine.pages(batch)
        assert size(text) <= 9000
    else:
        raise AssertionError("did not finish")
    assert rebuilt == dict(
        engine.store.db.execute("SELECT id,body FROM runs WHERE kind='query'")
    )
    request = {"result_id": next(iter(rebuilt)), "offset": 0}
    assert engine.pages([request, request]) == engine.page(request["result_id"])
    invalid = engine.pages([{"result_id": "bad", "offset": 0}, request])
    assert "PAGE ERROR item=1" in invalid and size(invalid) <= 9000
    engine.store.close()
