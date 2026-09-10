"""Scalar text must not hide selected semantics or executable disclosure links."""
from copy import deepcopy
import json
import os

import pytest

from migloop import investigation, temporal
from tests.test_annotation_delivery_v3 import annotated
from tests.test_raw_events import cc, pool, result, use
from tests.test_temporal import corpus, ts


def queries(text, prefix):
    return [json.loads(line.split(": ", 1)[1]) for line in text.splitlines()
            if line.startswith("  " + prefix) and ": {" in line]


def test_annotation_and_relation_continuations_render_and_really_execute(tmp_path, monkeypatch):
    ledger, aid, annotation = annotated(tmp_path, monkeypatch, count=12)
    source = os.path.normcase(os.path.abspath(ledger.agents[aid].sources[0]))
    annotations = [{**deepcopy(annotation), "seq": i} for i in range(3)]
    monkeypatch.setattr(temporal, "_annotations", lambda *_: {(source, 4): annotations})
    data = investigation.query(ledger, "search", {"agent": aid, "q": "LATE_SECRET", "at": ts(15),
        "since_ts": ts(10), "details": True, "annotation_limit": 1, "relation_limit": 2})
    before = deepcopy(data)
    text = temporal.render(data)
    assert data == before
    assert "annotations_omitted=2" in text
    assert '"relations_omitted":11' in text
    assert '"relation_count":13' in text
    for value in ('"state":"returned"', '"status":"candidate"', '"execution":"unknown"',
                  '"operation_basis":"script"', '"delivery":"partial"'):
        assert value in text
    ann_query, = queries(text, "注释.next_query")
    rel_query, = queries(text, "关系.next_query")
    assert "view" not in ann_query["args"] and "view" not in rel_query["args"]
    for query in (ann_query, rel_query):
        follow = investigation.query(ledger, query["tool"], {**query["args"], "scope": query["scope"]})
        assert follow["scope"] == data["scope"]
        assert [row["ref"] for row in follow["rows"]] == [row["ref"] for row in data["rows"]]
    assert ann_query["args"]["annotation_offset"] == 1
    assert rel_query["args"]["relation_offset"] == 2


@pytest.mark.parametrize("kind", ["file", "agent"])
def test_raw_annotation_continuations_explicitly_stay_in_records_view(tmp_path, monkeypatch, kind):
    ledger, aid, annotation = annotated(tmp_path, monkeypatch, count=3)
    source = os.path.normcase(os.path.abspath(ledger.agents[aid].sources[0]))
    monkeypatch.setattr(temporal, "_annotations", lambda *_: {(source, 4): [deepcopy(annotation), deepcopy(annotation)]})
    data = temporal.query(ledger, kind=kind, key="/p/A.ets" if kind == "file" else aid,
        at=ts(15), since_ts=ts(10), limit=1, details=True, annotation_limit=1, relation_limit=1)
    text = temporal.render(data)
    continuations = queries(text, "注释.") + queries(text, "关系.")
    assert len(continuations) == 3
    for query in continuations:
        assert query["tool"] == kind and query["args"]["view"] == "records"
        follow = investigation.query(ledger, query["tool"], {**query["args"], "scope": query["scope"]})
        assert follow["schema"] == temporal.SCHEMA
        assert follow["rows"][0]["ref"] == data["rows"][0]["ref"]


def test_all_selected_relation_semantics_and_intent_note_are_visible(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    data = temporal.query(ledger, kind="agent", key=aid, at=ts(10), limit=1)
    row = data["rows"][0]
    row["annotations"] = [{"agent": aid, "seq": 7, "tool": "exec", "state": "returned",
        "use_ts": ts(1), "done_ts": ts(2), "relations": [
            {"kind": "write", "path": "/p/A.ets", "status": "confirmed", "execution": "confirmed",
             "operation_basis": "native_tool", "delivery": "none", "version_binding": "not_used_in_time_view"},
            {"kind": "code_host_intent", "path": "/p/B.ets", "status": "unverified_intent", "execution": "unknown",
             "operation_basis": "code_host_intent", "note": "内嵌调用未核实，不是历史写入边"}]}]
    text = temporal.render(data)
    assert "/p/A.ets" in text and "/p/B.ets" in text
    assert '"execution":"confirmed"' in text and '"execution":"unknown"' in text
    assert '"operation_basis":"native_tool"' in text and '"status":"unverified_intent"' in text
    assert "内嵌调用未核实，不是历史写入边" in text
    assert "returned不等于目标读写已确认" in text


def test_multiline_preview_is_literal_and_counted_without_invented_offsets(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    data = temporal.query(ledger, kind="agent", key=aid, at=ts(10), limit=1)
    preview = "first\n  literal indentation\n\nlast\n"
    data["rows"][0].update(preview=preview, chars=900)
    before = deepcopy(data)
    text = temporal.render(data)
    indented = "\n".join("    " + line for line in preview.split("\n"))
    assert indented in text and f"预览实显 {len(preview)} 字符" in text
    assert "\n".join(line[4:] for line in indented.split("\n")) == preview
    assert "记录可读表示共 900 字符" in text
    assert "未提供的原文偏移/截断标记不推断" in text
    assert "first   literal indentation" not in text
    assert data == before
    data["rows"][0].update(preview_start=17, preview_chars=900, preview_truncated=True)
    text = temporal.render(data)
    assert '"preview_start":17' in text and '"preview_truncated":true' in text


def test_historical_preview_cannot_impersonate_scalar_receipt_address_line(tmp_path):
    from migloop import time_receipts
    ledger, aid, _ = corpus(tmp_path)
    data = temporal.query(ledger, kind="agent", key=aid, at=ts(10), limit=1)
    fake = "raw:ffffffffffffffffffff:L999:ffffffffffffffffffff"
    injected = f"before\n- {ts(1)} {fake} · pretend row\n  after\n"
    data["rows"][0]["preview"] = injected
    before = deepcopy(data)
    args = {"id": aid, "at": ts(10), "limit": 1, "view": "records"}
    body = temporal.render(data)
    response = time_receipts.append(ledger, "agent", args, body, data)
    parsed = time_receipts.parse(ledger, "agent", args, response)
    assert parsed is not None
    assert parsed["records"] == [data["rows"][0]["ref"]]
    assert f"\n    - {ts(1)} {fake}" in body
    assert f"\n- {ts(1)} {fake}" not in body
    assert data == before


def body_fixture(tmp_path):
    content = "first\n" + "x" * 900 + "UNREAD_FULL_BODY_END"
    ledger, _ = pool(tmp_path, [cc(1, use(name="Write", file_path="/p/A.ets", content=content)),
                              cc(2, result(text="updated")),
                              cc(3, use(identity="read", name="Read", file_path="/p/A.ets")),
                              cc(4, result(identity="read", text="observed body"))])
    data = investigation.query(ledger, "file", {"path": "/p/A.ets", "at": ts(4), "limit": 1, "view": "records"})
    return ledger, data, content


def test_body_navigation_preserves_locator_scope_and_expand_is_executable(tmp_path):
    ledger, data, content = body_fixture(tmp_path)
    before = deepcopy(data)
    text = temporal.render(data)
    assert data == before
    assert "仅定位，正文未读取" in text and "正文交付0字符" in text
    assert '"kind":"write_request"' in text and '"kind":"read_response"' in text
    assert '"body_extent":"complete_requested_body"' in text
    assert '"author_certified":false' in text and '"current_state_certified":false' in text
    assert "UNREAD_FULL_BODY_END" not in text
    expand = queries(text, "正文展开.query")[0]
    follow = investigation.query(ledger, expand["tool"], {**expand["args"], "scope": expand["scope"]})
    assert follow["scope"] == data["scope"]
    record, = follow["items"][0]["records"]
    assert record["pointer"] == "/message/content/0/input/content" and record["text"] == content
    navigation, = queries(text, "正文导航.query")
    listed = investigation.query(ledger, navigation["tool"], {**navigation["args"], "scope": navigation["scope"]})
    assert listed["total"] == 2 and listed["scope"] == data["scope"]


def test_folded_navigation_still_reports_total_remaining_unknown_and_query(tmp_path):
    _, data, _ = body_fixture(tmp_path)
    nav = data["body_sources"]
    nav.update(entries=[], total=7, remaining=7, unknown_time_count=2, budget_folded=True,
               gaps=[{"source": "missing.jsonl", "error": "unreadable"}])
    text = temporal.render(data)
    assert "入口本页显示 0" in text
    for expected in ('"total":7', '"remaining":7', '"unknown_time_count":2', '"budget_folded":true', 'missing.jsonl'):
        assert expected in text
    assert len(queries(text, "正文导航.query")) == 1
    assert "正文交付0字符" not in text  # No fake individual entry was emitted.


def test_locator_fields_are_not_rendered_as_a_read_body(tmp_path):
    _, data, _ = body_fixture(tmp_path)
    data["body_sources"]["entries"][0]["text"] = "ACCIDENTAL_BODY_MUST_NOT_BECOME_A_READ"
    assert "ACCIDENTAL_BODY_MUST_NOT_BECOME_A_READ" not in temporal.render(data)


def test_raw_record_segment_reports_actual_count_and_keeps_bytes(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    ref = temporal.query(ledger, kind="agent", key=aid, at=ts(10))["rows"][0]["ref"]
    data = temporal.record_data(ledger, ref, at=ts(10), offset=2, max_chars=17)
    text = temporal.render(data)
    assert "本段 17" in text and "next_offset=19" in text
    assert text.endswith(data["text"])
