"""Free jumps are permitted; immutable disclosure bounds and proof are not optional."""
import asyncio
import json

import pytest

from migloop import investigation, service, temporal
from tests.test_atoms import _call, _ledger
from tests.test_temporal import corpus, ts


def test_batch_independent_scopes_and_partial_failure(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    data = investigation.batch(ledger, [
        {"tool": "agent", "args": {"id": aid, "at": ts(10)}},
        {"tool": "agent", "args": {"id": "absent", "at": ts(10)}},
        {"tool": "search", "args": {"q": "LATE_SECRET", "at": ts(15)}},
    ])
    assert [r["status"] for r in data["items"]] == ["ok", "error", "ok"]
    assert "LATE_SECRET" not in str(data["items"][0])
    assert data["items"][2]["data"]["total"] == 1
    assert "edges" not in data


def test_expansion_inherits_lower_and_upper_bounds(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    rows = temporal.query(ledger, kind="agent", key=aid, at=ts(17))["rows"]
    current = investigation.scope(ledger, "agent", aid, ts(10), ts(4))
    data = investigation.query(ledger, "expand", {"scope": current, "refs": [rows[i]["ref"] for i in (0, 1, 3)]})
    assert [r["status"] for r in data["items"]] == ["error", "ok", "error"]
    assert "LONGTAIL" in str(data) and "LATE_SECRET" not in str(data)
    assert "数值应该为42" not in str(data)


def test_scope_conflict_is_rejected_but_independent_lookup_is_allowed(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    current = investigation.scope(ledger, "agent", aid, ts(10))
    with pytest.raises(ValueError, match="冲突"):
        investigation.query(ledger, "search", {"scope": current, "at": ts(15), "q": "LATE_SECRET"})
    assert investigation.query(ledger, "search", {"at": ts(15), "q": "LATE_SECRET"})["total"] == 1


def test_explicit_scope_prevents_cross_agent_or_file_expansion(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    row = temporal.query(ledger, kind="agent", key=aid, at=ts(10))["rows"][0]
    scoped = investigation.scope(ledger, "file", "/p/unrelated.ets", ts(10))
    data = investigation.query(ledger, "expand", {"scope": scoped, "refs": [row["ref"]]})
    assert data["items"][0]["status"] == "error"
    independent = investigation.query(ledger, "record", {"ref": row["ref"], "at": ts(10)})
    assert "数值应该为42" in independent["text"]


def test_latest_freezes_actual_record_time_not_last_action(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    current = investigation.scope(ledger, "agent", aid)
    assert current["at"].startswith("2026-09-10T10:16:00")
    with pytest.raises(ValueError, match="不能晚于"):
        investigation.scope(ledger, "agent", aid, "latest", ts(17))
    with pytest.raises(ValueError, match="漂移"):
        investigation.query(ledger, "search", {"scope": {**current, "at": ts(10)}, "q": "x"})


def test_budget_does_not_mark_undelivered_data_as_read(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    data = investigation.batch(ledger, [{"tool": "agent", "args": {"id": aid, "at": ts(17)}}], max_chars=1000)
    assert data["items"][0]["status"] == "deferred"
    assert data["items"][0]["delivery"]["records"] == []
    assert "data" not in data["items"][0]


def test_scope_does_not_carry_implicit_current_node(tmp_path):
    ledger, _aid, _ = corpus(tmp_path)
    data = investigation.batch(ledger, [
        {"tool": "file", "args": {"path": "A.ets", "at": ts(10)}},
        {"tool": "search", "args": {"q": "LONGTAIL", "at": ts(10)}},
    ])
    assert data["items"][0]["scope"]["kind"] == "file"
    assert data["items"][1]["scope"]["kind"] == "pool"
    assert data["items"][1]["data"]["total"] == 1


def test_changes_and_diff_provide_time_safe_expandable_sources(tmp_path):
    ledger = _ledger(tmp_path, [
        *_call(ts(0), "w", "Write", {"file_path": "/proj/A.ets", "content": "old\n"}, "ok"),
        *_call(ts(5), "e", "Edit", {"file_path": "/proj/A.ets", "old_string": "old", "new_string": "new"}, "ok"),
    ])
    data = investigation.changes(ledger, "/proj/A.ets", ts(10), since_ts=ts(1))
    assert data["total"] == 1
    assert data["rows"][0]["status"] == "confirmed_change"
    assert data["rows"][0]["id"] and data["rows"][0]["evidence"]
    out = investigation.query(ledger, "expand", {"scope": data["scope"], "refs": [data["rows"][0]["legacy_ref"]]})
    assert out["items"][0]["status"] == "ok"
    assert "new_string" in str(out)
    diff = investigation.query(ledger, "diff", {"scope": data["scope"]})
    assert investigation._delivery(diff)["records"]
    assert investigation._delivery(diff)["records"][0]["extent"] == "derived_diff"
    assert investigation._delivery(diff)["records"][0]["chars"] > 0


def test_batch_receipt_rejects_forgery_and_partial_delivery(tmp_path):
    ledger, _aid, _ = corpus(tmp_path)
    requests = [{"tool": "search", "args": {"q": "LONGTAIL", "at": ts(10)}}]
    text = investigation.render_batch(ledger, requests)
    call = {"tool": "batch", "input": {"sid": "test", "requests": requests}, "text": text,
            "has_result": True, "provenance": {"complete_pair": True}}
    result = investigation.project_trace(ledger, [call])
    assert result["steps"][0]["status"] == "recorded_response"
    assert result["steps"][0]["items"][0]["delivery"]["records"]
    assert result["edges"] == []
    for changed in ({"delivery_truncated": True}, {"text": text.replace("LONGTAIL", "FORGED")},
                    {"provenance": {"origin_unverified": True}}):
        assert investigation.project_trace(ledger, [{**call, **changed}])["steps"][0]["status"] == "unverified_response"


def test_mcp_and_http_batch_share_data_and_text(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from migloop import mcp_server
    ledger, aid, _ = corpus(tmp_path)
    class Backend:
        async def get_ledger(self, sid): return ledger
        async def get_session_cwd(self, sid): return "/p"
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/p")
    args = {"requests": [{"tool": "agent", "args": {"id": aid, "at": ts(10), "limit": 1}}]}
    response = asyncio.run(mcp_server.build_server(Backend()).call_tool("batch", {"sid": "x", **args}))[0].text
    assert response == service.atom_text("x", "batch", args)
    body = json.loads(response.split(investigation.MARKER)[0])
    assert body == service.atom_json("x", "batch", args)


def test_single_expand_receipt_uses_exact_args_and_scope(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    ref = temporal.query(ledger, kind="agent", key=aid, at=ts(10))["rows"][0]["ref"]
    args = {"refs": [ref], "scope": investigation.scope(ledger, "agent", aid, ts(10)),
            "offset": 0, "max_chars": 12000, "include_undated": False}
    text = investigation.render_query(ledger, "expand", args)
    call = {"tool": "expand", "input": {"sid": "x", **args}, "text": text, "has_result": True}
    row = investigation.project_trace(ledger, [call])["steps"][0]
    assert row["status"] == "recorded_response" and row["scope"]["at"] == args["scope"]["at"]
    assert row["delivery"]["records"][0]["extent"] == "raw_segment"


def test_field_expansion_is_time_scoped_paged_and_explicit(tmp_path):
    from migloop import transcript_store as store
    ledger = _ledger(tmp_path, [
        *_call(ts(0), "w", "Write", {"file_path": "/proj/A.ets", "content": "旧内容\n新内容\n"}, "ok"),
    ])
    agent = next(iter(ledger.agents))
    source = next(iter(store.sources(ledger)))
    record = store.read_record(source, 1)
    args = {"scope": investigation.scope(ledger, "agent", agent, ts(1)),
            "refs": [{"ref": record.ref, "pointer": "/message/content/0/input/content"}], "max_chars": 3}
    result = investigation.query(ledger, "expand", args)
    body = result["items"][0]["records"][0]
    assert body["text"] == "旧内容" and body["next_offset"] == 3
    assert body["ref"] == record.ref and body["representation"] == "decoded_string"
    delivery = investigation._delivery(result)["records"][0]
    assert delivery["extent"] == "raw_field_segment" and delivery["pointer"] == args["refs"][0]["pointer"]
    missing = investigation.query(ledger, "expand", {**args, "refs": [{"ref": record.ref, "pointer": "/absent"}]})
    assert missing["items"][0]["status"] == "error"
    assert "旧内容" not in str(missing)
    later = investigation.query(ledger, "expand", {**args, "scope": investigation.scope(ledger, "pool", at="2026-09-09T00:00:00Z")})
    assert later["items"][0]["status"] == "error" and "旧内容" not in str(later)


def test_related_locator_preview_is_not_certified_as_a_raw_field_segment():
    data = {"unclassified_related": {"rows": [{"pointers": [
        {"ref": "raw:source:L1:hash", "pointer": "/payload", "preview": "short excerpt"}
    ]}]}}
    row, = investigation._delivery(data)["records"]
    assert row["extent"] == "preview_or_pointer" and row["offset"] is None


@pytest.mark.parametrize("pointer,expected", [("", {"a/b": {"~": ["x", "y"]}}), ("/a~1b/~0/1", "y")])
def test_json_pointer_selection(pointer, expected):
    assert investigation._field({"a/b": {"~": ["x", "y"]}}, pointer) == expected


@pytest.mark.parametrize("pointer", ["bad", "/~2", "/a/01", "/a/-1", "/a/-", "/a/9", "/absent"])
def test_json_pointer_does_not_guess(pointer):
    with pytest.raises(ValueError):
        investigation._field({"a": ["x", "y"]}, pointer)


def test_batch_delivers_prefixes_fairly_and_receipt_mentions_only_delivered_rows(tmp_path):
    from migloop import atoms
    from tests.test_temporal import source
    path = source(tmp_path, [{"timestamp": ts(i), "text": "payload " + "x" * 600} for i in range(30)])
    ledger = atoms.build_ledger({"a": atoms.AgentRec("a", "s", sources=[path])})
    requests = [{"tool": "agent", "args": {"id": "a", "at": ts(29), "view": "records"}} for _ in range(2)]
    data = investigation.batch(ledger, requests, max_chars=12000)
    assert data["data_chars"] <= 12000
    for item in data["items"]:
        assert item["status"] == "ok" and item["budget_adjusted"]
        page = item["data"]
        assert 0 < len(page["rows"]) < page["total"] == 30
        assert page["next_offset"] == len(page["rows"])
        assert [r["ref"] for r in item["delivery"]["records"]] == [r["ref"] for r in page["rows"]]
        assert item["continuations"][0]["offset"] == page["next_offset"]


def test_original_changes_receipt_survives_new_optional_pagination_defaults(tmp_path):
    from migloop import atoms
    ledger, _, _ = corpus(tmp_path)
    args = {"path": "A.ets", "at": ts(10)}
    body = json.dumps({"ledger": atoms.ledger_identity(ledger), "rows": [], "schema": "migloop-time-changes/1"})
    old = {"at": "latest", "since_ts": None, "offset": 0, "limit": 40, **args}
    receipt = {"schema": "migloop-investigation-receipt/1", "ledger": atoms.ledger_identity(ledger),
               "tool": "changes", "request_sha256": investigation.digest(old), "body_sha256": investigation.digest(body)}
    text = body + investigation.MARKER + json.dumps(receipt)
    assert investigation.parse_receipt("changes", args, text)
    assert investigation.parse_receipt("changes", {**args, "related_offset": 8}, text) is None
