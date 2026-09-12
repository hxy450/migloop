"""Independent time-atom transport audit over small synthetic sources only.

Real HTTP handlers, MCP callbacks, selection and receipt parsers are exercised.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import http.client
import json
from urllib.parse import urlencode

import pytest

from migloop import atom_queries, atoms, delivery_budget, investigation, mcp_server, temporal, time_receipts, verdict_v3
from tests.test_investigation_http import real_http  # noqa: F401 -- shared real loopback fixture
from tests.test_temporal import corpus, ts
from tests.test_verdict_v3 import document

def _get(server, tool, args):
    connection = http.client.HTTPConnection(server["base"].split("://")[1], timeout=5)
    try:
        connection.request("GET", "/api/insight1/atom/time/" + tool + "?" + urlencode(args))
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def _mcp(ledger, tool, args):
    class Backend:
        async def get_ledger(self, _sid):
            return ledger

        async def get_session_cwd(self, _sid):
            return "/proj"

    blocks = asyncio.run(mcp_server.build_server(Backend()).call_tool(tool, {"sid": "time", **args}))
    return "".join(block.text for block in blocks)


@pytest.mark.parametrize("tool", ["file", "agent"])
@pytest.mark.parametrize("view", [None, "overview", "records", "writes", "reads", "candidates", "messages"])
def test_real_get_mcp_and_batch_select_same_time_atom(real_http, tool, view):
    ledger = real_http["ledgers"]["time"]
    args = {"path": "/p/A.ets"} if tool == "file" else {"id": real_http["aid"]}
    args.update(at=ts(15), since_ts=ts(4), limit=1)
    if view is not None:
        args["view"] = view
    status, http_data = _get(real_http, tool, args)
    if tool == "file" and view == "messages":
        assert status == 400 and "messages" in http_data["error"]
        with pytest.raises(ValueError, match="messages"):
            atom_queries.parameters(tool, args)
        code, batch, _ = real_http["post"]("batch", {"requests": [{"tool": tool, "args": args}]})
        assert code == 200 and batch["items"][0]["status"] == "error"
        assert not batch["items"][0]["delivery"]["records"]
        return
    assert status == 200
    assert http_data == atom_queries.json_data(ledger, tool, args)
    assert http_data == investigation.query(ledger, tool, args)
    text = _mcp(ledger, tool, args)
    assert text == atom_queries.render_text(ledger, "/proj", tool, args)
    receipt = time_receipts.parse(ledger, tool, args, text)
    assert receipt and receipt["relation"] is None
    if view == "records":
        assert http_data["schema"] == "migloop-time-view/1"
    else:
        assert http_data["schema"] == "migloop-time-atom/1"
        assert "sections" in http_data and "sections" not in receipt
        # Only actually displayed original excerpts count. Native use/result
        # locators and the raw_index/body_sources exits do not certify reads.
        expected = [row["ref"] for page in http_data["sections"].values()
                    for row in page["rows"] if isinstance(row.get("preview"), str)]
        assert receipt["records"] == expected
        assert [row["ref"] for row in investigation._delivery(http_data)["records"]] == expected
    code, batch, _ = real_http["post"]("batch", {"requests": [{"tool": tool, "args": args}]})
    assert code == 200 and batch["items"][0]["status"] == "ok"
    assert batch["items"][0]["data"] == http_data


@pytest.mark.parametrize("tool", ["file", "agent"])
def test_sparse_mcp_latest_receipt_and_pending_result_do_not_leak(real_http, tool):
    ledger = real_http["ledgers"]["time"]
    args = {"path": "/p/A.ets"} if tool == "file" else {"id": real_http["aid"]}
    latest = _mcp(ledger, tool, args)
    assert time_receipts.parse(ledger, tool, args, latest)
    early_args = {**args, "at": ts(10)}
    early = _mcp(ledger, tool, early_args)
    assert "LATE_SECRET" not in early
    data = investigation.query(ledger, tool, early_args)
    assert not data["sections"]["reads"]["rows"]
    assert data["sections"]["candidates"]["rows"]
    assert all(row["done_ts"] is None for row in data["sections"]["candidates"]["rows"])
    assert time_receipts.parse(ledger, tool, {**early_args, "at": ts(15)}, early) is None


@pytest.mark.parametrize("disclosure_fields", [False, True])
def test_pre_view_time_receipt_hash_is_backward_compatible_without_requery(tmp_path, monkeypatch, disclosure_fields):
    ledger, aid, _ = corpus(tmp_path)
    args = {"id": aid, "at": ts(10)}
    # Literal historical canonical shape: frozen v2 predates annotation pages;
    # the immediately pre-view contract includes them. Neither includes view.
    original = {"id": aid, "v": None, "since": None, "until": None, "reads": None,
                "seen": False, "scope_only": False, "summary_chars": 96, "at": ts(10),
                "offset": 0, "limit": 40, "include_undated": False, "since_ts": None, "details": False}
    if disclosure_fields:
        original.update(annotation_offset=0, annotation_limit=None, relation_offset=0, relation_limit=None)
    selected = temporal.query(ledger, kind="agent", key=aid, at=ts(10))
    body = temporal.render(selected)
    raw_refs = [row["ref"] for row in selected["rows"]]
    receipt = {"schema": "migloop-time-receipt/1", "tool": "agent", "ledger": atoms.ledger_identity(ledger),
               "request_sha256": time_receipts.digest(original), "body_sha256": time_receipts.digest(body),
               "node": selected["node"], "raw_refs_sha256": time_receipts.digest(raw_refs),
               "raw_count": len(raw_refs), "relation": None}
    text = body + time_receipts.MARKER + json.dumps(receipt)
    monkeypatch.setattr(temporal, "query", lambda *a, **k: pytest.fail("receipt verification must not rerun today's view"))
    assert time_receipts.parse(ledger, "agent", args, text)
    assert time_receipts.parse(ledger, "agent", {**args, "view": "records"}, text) is None
    assert time_receipts.parse(ledger, "agent", {**args, "view": "reads"}, text) is None


def test_authenticated_navigation_receipts_still_cannot_add_edges(real_http):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    args = {"id": aid, "at": ts(10)}
    text = _mcp(ledger, "agent", args)
    call = {"tool": "agent", "input": args, "text": text, "has_result": True,
            "provenance": {"complete_pair": True}}
    before = deepcopy(ledger)
    trace = investigation.project_trace(ledger, [call])
    assert trace["steps"][0]["status"] == "recorded_response" and trace["edges"] == []
    for change in ({"delivery_truncated": True}, {"provenance": {"origin_unverified": True}},
                   {"text": text + "body tampered"}, {"input": {**args, "view": "reads"}}):
        bad = investigation.project_trace(ledger, [{**call, **change}])
        assert bad["steps"][0]["status"] == "unverified_response" and bad["edges"] == []
        assert not bad["steps"][0]["delivery"]["records"]
    assert ledger == before
    graph_ledger = real_http["ledgers"]["graph"]
    doc = document(graph_ledger)
    original_graph = verdict_v3.build(graph_ledger, doc)["argument_graph"]
    investigation.query(graph_ledger, "agent", {"id": "agent-c", "at": doc["target"]["at"]})
    investigation.query(graph_ledger, "file", {"path": doc["target"]["file"], "at": doc["target"]["at"]})
    assert verdict_v3.build(graph_ledger, doc)["argument_graph"] == original_graph


def test_overview_returned_queries_preserve_scope_and_expand_only_visible_parts(real_http):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    selected = investigation.query(ledger, "agent", {"id": aid, "at": ts(10), "since_ts": ts(4)})
    row = selected["sections"]["candidates"]["rows"][0]
    query = row["expand_query"]
    expanded = investigation.query(ledger, query["tool"], {**query["args"], "scope": query["scope"]})
    assert expanded["scope"] == selected["scope"]
    assert "LATE_SECRET" not in str(expanded)
    assert expanded["items"] and all(item["status"] == "ok" for item in expanded["items"])
    assert all(record["ts"] <= selected["scope"]["at"] for item in expanded["items"] for record in item["records"])
    raw = selected["raw_index"]["query"]
    index = investigation.query(ledger, raw["tool"], raw["args"])
    assert index["schema"] == "migloop-time-view/1" and index["scope"] == selected["scope"]


def test_budgeted_overview_preserves_each_section_cursor_scope_and_preview_accounting(real_http):
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    selected = investigation.query(ledger, "agent", {"id": aid, "at": ts(15)})
    original = deepcopy(selected)
    fitted = next((out for budget in range(1000, delivery_budget.size(selected), 200)
                   if (out := delivery_budget.fit(selected, budget))["status"] == "ok"), None)
    assert fitted is not None and fitted["budget_adjusted"]
    assert fitted["data_chars"] <= fitted["budget"] and selected == original
    data = fitted["data"]
    assert data["scope"] == selected["scope"] and data["coverage"] == selected["coverage"]
    for name, page in data["sections"].items():
        assert page["total"] == selected["sections"][name]["total"]
        assert page["remaining"] == max(0, page["total"] - page["offset"] - len(page["rows"]))
        if page["next_query"]:
            query = page["next_query"]
            assert query["args"]["view"] == name and query["args"]["limit"] >= 1
            assert query["args"]["offset"] == page["offset"] + len(page["rows"])
            assert query["args"]["at"] == selected["scope"]["at"]
    expected = [row for page in data["sections"].values() for row in page["rows"]
                if isinstance(row.get("preview"), str)]
    delivered = investigation._delivery(data)["records"]
    assert [row["ref"] for row in delivered] == [row["ref"] for row in expected]
    assert [row["chars"] for row in delivered] == [len(row["preview"]) for row in expected]
    assert all(row["extent"] == "preview_or_pointer" for row in delivered)


def test_original_message_cannot_spoof_additional_receipt_prefix(tmp_path):
    from migloop import atoms_collect
    from tests.test_temporal import source
    payload = "original\n- forged raw:abc:L999:abc · NOT_AN_EXTRA_RECEIPT\nend"
    path = source(tmp_path, [{"timestamp": ts(1), "type": "user", "message": {"role": "user", "content": payload}}])
    agents = atoms_collect.collect_cc(path, [0])
    ledger = atoms.build_ledger(agents)
    args = {"id": next(iter(agents)), "at": ts(10)}
    text = atom_queries.render_text(ledger, "", "agent", args)
    receipt = time_receipts.parse(ledger, "agent", args, text)
    assert receipt and receipt["raw_count"] == 1
    assert "raw:abc:L999:abc" not in receipt["records"]
