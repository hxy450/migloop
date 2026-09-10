"""Disclosure regression: large metadata must not hide a small raw body."""
from copy import deepcopy
import asyncio
import json
import os

import pytest

from migloop import atom_queries, delivery_budget, investigation, raw_events, temporal
from tests.test_temporal import corpus, ts
from tests.test_raw_events import pool, cc, use, result
from tests.test_investigation_http import real_http


def annotated(tmp_path, monkeypatch, count=260):
    ledger, aid, path = corpus(tmp_path)
    annotation = {"agent": aid, "seq": 77, "tool": "Bash", "state": "returned",
                  "use_ts": ts(9), "done_ts": ts(15), "legacy_ref": "#owner:77@L3",
                  "relations": [{"kind": "write", "path": f"/p/long-directory-{i}/file.ets",
                                 "status": "candidate", "execution": "unknown",
                                 "operation_basis": "script", "delivery": "partial"}
                                for i in range(count)]}
    annotation["relations"].append({"path": "/p/A.ets", "kind": "read", "status": "confirmed",
                                    "execution": "confirmed", "operation_basis": "native"})
    address = (os.path.normcase(os.path.abspath(path)), 4)
    monkeypatch.setattr(temporal, "_annotations", lambda *_: {address: [annotation]})
    return ledger, aid, annotation


def test_large_annotation_keeps_body_and_candidate_state_with_executable_continuation(tmp_path, monkeypatch):
    ledger, aid, annotation = annotated(tmp_path, monkeypatch)
    data = investigation.query(ledger, "search", {"agent": aid, "q": "LATE_SECRET", "at": ts(15), "details": True})
    original = deepcopy(data)
    fitted = delivery_budget.fit(data, 6000)
    assert fitted["status"] == "ok", fitted["reason"]
    row, = fitted["data"]["rows"]
    assert "LATE_SECRET" in row["preview"]
    shown, = row["annotations"]
    assert shown["agent"] == aid and shown["state"] == "returned"
    assert shown["relation_count"] == 261 and shown["relations_omitted"] > 0
    assert shown["relation_status_counts"] == {"candidate": 260, "confirmed": 1}
    assert all(r["status"] == "candidate" for r in shown["relations"])
    continuation = shown["relation_page"]["next_query"]
    more = investigation.query(ledger, continuation["tool"], {**continuation["args"], "scope": continuation["scope"]})
    assert more["scope"] == data["scope"]
    assert more["rows"][0]["annotations"][0]["relation_page"]["offset"] == len(shown["relations"])
    assert data == original
    assert fitted["data_chars"] <= 6000


def test_annotation_and_relation_pages_exhaust_without_changing_raw_admission(tmp_path, monkeypatch):
    ledger, aid, a = annotated(tmp_path, monkeypatch, count=12)
    path = os.path.normcase(os.path.abspath(ledger.agents[aid].sources[0]))
    annotations = [{**deepcopy(a), "seq": i} for i in range(3)]
    monkeypatch.setattr(temporal, "_annotations", lambda *_: {(path, 4): annotations})
    args = {"agent": aid, "q": "LATE_SECRET", "at": ts(15), "since_ts": ts(10), "details": True,
            "annotation_limit": 1, "relation_limit": 3}
    data = investigation.query(ledger, "search", args)
    refs = [r["ref"] for r in data["rows"]]
    all_sequences, all_paths = [], []
    while True:
        row = data["rows"][0]
        ann = row["annotations"][0]
        all_sequences.append(ann["seq"])
        paths = [r["path"] for r in ann["relations"]]
        nxt = ann["relation_page"]["next_query"]
        while nxt:
            follow = investigation.query(ledger, nxt["tool"], {**nxt["args"], "scope": nxt["scope"]})
            assert [r["ref"] for r in follow["rows"]] == refs
            assert follow["scope"] == data["scope"]
            current = follow["rows"][0]["annotations"][0]
            paths.extend(r["path"] for r in current["relations"])
            nxt = current["relation_page"]["next_query"]
        all_paths.append(paths)
        nxt = row["annotation_page"]["next_query"]
        if not nxt:
            break
        data = investigation.query(ledger, nxt["tool"], {**nxt["args"], "scope": nxt["scope"]})
    assert all_sequences == [0, 1, 2]
    assert all(paths == [r["path"] for r in a["relations"]] for paths in all_paths)


def test_annotation_cursor_normalization_and_scalar_json_share_core(tmp_path, monkeypatch):
    ledger, aid, _ = annotated(tmp_path, monkeypatch)
    supplied = {"id": aid, "at": ts(15), "details": "true", "annotation_offset": "0",
                "annotation_limit": "1", "relation_offset": "7", "relation_limit": "2"}
    normalized = atom_queries.parameters("agent", supplied)
    data = atom_queries.json_data(ledger, "agent", supplied)
    direct = investigation.query(ledger, "agent", normalized)
    assert data == direct
    row = next(r for r in data["rows"] if r["annotations"])
    assert row["annotations"][0]["relation_page"]["offset"] == 7
    assert len(row["annotations"][0]["relations"]) == 2
    before = investigation.query(ledger, "agent", {**normalized, "at": ts(10)})
    assert "LATE_SECRET" not in str(before)


@pytest.mark.parametrize("field,value", [("annotation_offset", -1), ("annotation_limit", 0),
    ("relation_offset", True), ("relation_limit", 201)])
def test_annotation_cursor_errors_name_the_field(field, value):
    with pytest.raises(ValueError, match=field):
        atom_queries.parameters("file", {"path": "/p/A.ets", "at": ts(15), field: value})


def test_current_source_manifest_is_compact_and_exhaustively_pageable(tmp_path, monkeypatch):
    ledger, _ = pool(tmp_path, [cc(1, use(name="Read", file_path="/p/A.ets")), cc(2, result(text="body"))])
    scanned = raw_events._scan(ledger)
    signatures = {f"/registered/long-source-directory/{i:04d}/source.jsonl": [1000 + i, 2000 + i] for i in range(240)}
    scanned.update(source_count=240, source_signatures=signatures)
    monkeypatch.setattr(raw_events, "_scan", lambda *_: deepcopy(scanned))
    data = raw_events.query(ledger, ts(3), limit=1)
    assert data["source_signatures"]["count"] == 240
    assert data["source_signatures"]["observation"] == "current_registry_not_historical_cutoff"
    assert delivery_budget.fit(data, 6000)["status"] == "ok"
    first = raw_events.query(ledger, ts(3), view="sources", limit=7)
    assert first["events"] == [] and first["total"] == 240
    assert first["source_signatures"]["digest"] == data["source_signatures"]["digest"]
    rows = []
    while True:
        rows.extend(first["source_rows"])
        if first["next_offset"] is None:
            break
        first = raw_events.query(ledger, ts(3), view="sources", offset=first["next_offset"], limit=7)
    assert {r["source_path"]: r["signature"] for r in rows} == signatures
    fitted = delivery_budget.fit(raw_events.query(ledger, ts(3), view="sources", limit=200), 2600)
    assert fitted["data"] and 0 < len(fitted["data"]["source_rows"]) < 200
    assert fitted["data"]["events"] == [] and fitted["data"]["total"] == 240
    assert fitted["continuations"][0]["page"] == "source_rows"
    assert data["complete"] == bool(scanned["source_count"]) and not data["causal_complete"]


def test_body_navigation_folds_without_claiming_its_raw_text_was_delivered():
    from tests.test_delivery_budget import view, SCOPE
    data = view(1)
    data["body_sources"] = {"total": 2, "kind_counts": {"write_request": 2}, "unknown_time_count": 0,
        "source_count": 1, "gaps": [], "current_state_certified": False,
        "entries": [{"ref": "raw:source:L91:hash", "source_agents": ["owner"], "long": "x" * 5000}],
        "remaining": 1, "query": {"tool": "events", "scope": SCOPE, "args": {"view": "bodies", "limit": 40}}}
    result = delivery_budget.fit(data, 2400)
    assert result["data"] and result["data"]["rows"]
    nav = result["data"]["body_sources"]
    assert nav["entries"] == [] and nav["total"] == nav["remaining"] == 2
    assert nav["query"] == data["body_sources"]["query"]
    assert any(c["kind"] == "body_navigation" for c in result["continuations"])
    assert "raw:source:L91:hash" not in str(investigation._delivery(result["data"]))


def test_real_http_mcp_and_core_share_annotation_and_source_pages(real_http, monkeypatch):
    pytest.importorskip("mcp")
    from migloop import mcp_server
    ledger, aid = real_http["ledgers"]["time"], real_http["aid"]
    path = os.path.normcase(os.path.abspath(real_http["paths"]["time"]))
    annotation = {"agent": aid, "seq": 1, "tool": "Bash", "state": "returned", "relations": [
        {"path": f"/p/{i}.ets", "kind": "write", "status": "candidate"} for i in range(30)]}
    monkeypatch.setattr(temporal, "_annotations", lambda *_: {(path, 4): [annotation]})
    raw_events.inventory(ledger)  # Operational cache counts now agree across repeated transports.
    requests = [{"tool": "search", "args": {"agent": aid, "q": "LATE_SECRET", "at": ts(15),
        "since_ts": ts(10), "details": True, "annotation_limit": 1, "relation_offset": 3, "relation_limit": 2}},
        {"tool": "events", "args": {"view": "sources", "at": ts(10), "limit": 1}}]
    args = {"requests": requests, "max_chars": 14000}

    class Backend:
        async def get_ledger(self, sid):
            assert sid == "time"
            return ledger

        async def get_session_cwd(self, sid):
            return "/proj"

    blocks = asyncio.run(mcp_server.build_server(Backend()).call_tool("batch", {"sid": "time", **args}))
    mcp_data = json.loads("".join(block.text for block in blocks).rpartition(investigation.MARKER)[0])
    status, http_data, _ = real_http["post"]("batch", args)
    assert status == 200
    assert http_data == mcp_data == atom_queries.json_data(ledger, "batch", args)
    row = http_data["items"][0]["data"]["rows"][0]
    ann = row["annotations"][0]
    assert [r["path"] for r in ann["relations"]] == ["/p/3.ets", "/p/4.ets"]
    nxt = ann["relation_page"]["next_query"]
    status, next_data, _ = real_http["post"]("batch", {"requests": [nxt], "max_chars": 10000})
    assert status == 200 and next_data["items"][0]["scope"] == http_data["items"][0]["scope"]
    assert next_data["items"][0]["data"]["rows"][0]["annotations"][0]["relation_page"]["offset"] == 5
    sources = http_data["items"][1]["data"]
    assert sources["view"] == "sources" and sources["events"] == [] and len(sources["source_rows"]) == 1
    assert sources["source_signatures"]["observation"] == "current_registry_not_historical_cutoff"
