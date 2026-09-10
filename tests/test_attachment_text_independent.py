"""Independent attachment/source checks; synthetic bytes only, no real pools."""
import hashlib
import json
import os

import pytest

from migloop import atoms, atoms_collect, cc_sources, investigation, raw_events, transcript_store as store


AT = "2026-09-10T12:00:00Z"


def fixture(tmp_path, body, filename="captured.txt"):
    root = tmp_path / "abcdef12-root.jsonl"
    row = {"type": "user", "timestamp": "2026-09-10T10:00:00Z",
           "message": {"role": "user", "content": "Synthetic input, no operation."}}
    root.write_text(json.dumps(row) + "\n", encoding="utf-8")
    attached = tmp_path / root.stem / "tool-results" / filename
    attached.parent.mkdir(parents=True)
    attached.write_bytes(body)
    found = cc_sources.discover([str(root)])
    agents = atoms_collect.collect_cc_pool([str(root)], [0], sources=found)
    ledger = atoms.build_ledger(agents, auxiliary_sources=found.auxiliary_sources,
                               source_metadata=found.source_metadata)
    return ledger, attached


@pytest.mark.parametrize("filename", ["captured.txt", "captured.json", "script.js", "README.MD", "extensionless"])
def test_non_jsonl_never_decodes_json_like_text_or_borrows_timestamp(tmp_path, filename):
    line = '{"timestamp":"2099-01-01T00:00:00Z","payload":{"text":"literal\\n雪"},"type":"tool_use"}'
    ledger, attached = fixture(tmp_path, line.encode("utf-8"), filename)
    spec = store.source_spec(ledger, str(attached))
    record, = store.records(str(attached), source=spec)
    assert record.raw == record.text == line
    assert record.value is None and record.textual and not record.malformed
    assert record.kind == "attachment_text" and record.ts is None
    direct = store.read_record(str(attached), 1, source=spec)
    assert direct == record
    search = investigation.query(ledger, "search", {"q": "literal\\n雪", "at": AT, "include_undated": True})
    match, = search["undated"]["rows"]
    assert match["ref"] == record.ref and match["agents"] == [] and match["ts"] is None
    assert line in match["preview"]
    no_unknown = investigation.query(ledger, "search", {"q": "literal\\n雪", "at": AT})
    assert not no_unknown["rows"] and not no_unknown["undated"]["rows"]
    with pytest.raises(ValueError, match="include_undated"):
        investigation.query(ledger, "record", {"ref": record.ref, "at": AT})
    for pointer in ("", "/payload", "/payload/text"):
        expansion = investigation.query(ledger, "expand", {"refs": [{"ref": record.ref, "pointer": pointer}],
                                                           "at": AT, "include_undated": True})
        item, = expansion["items"]
        assert item["status"] == "error" and item["records"] == []
    assert not raw_events.inventory(ledger)["events"]


def test_legacy_and_qualified_refs_bind_identical_payload_and_complete_record_pages(tmp_path):
    text_lines = ['  first /p/A.ets \\ literal 雪🙂', '', '{"a": "' + '测🙂' * 50 + '"}', 'last']
    body = b"\xef\xbb\xbf" + ("\r\n".join(text_lines) + "\r\n").encode("utf-8")
    ledger, attached = fixture(tmp_path, body)
    spec = store.source_spec(ledger, str(attached))
    records = list(store.records(str(attached), source=spec))
    assert [record.raw for record in records] == text_lines
    source20 = hashlib.sha256(attached.name.encode()).hexdigest()[:20]
    source40 = hashlib.sha256(json.dumps(["registered-source/1", spec.logical_name], ensure_ascii=True,
                                       separators=(",", ":")).encode("ascii")).hexdigest()[:40]
    for line, record in zip(text_lines, records):
        payload_hash = hashlib.sha256(line.encode("utf-8")).hexdigest()[:20]
        for source_id in (source20, source40):
            ref = f"raw:{source_id}:L{record.line}:{payload_hash}"
            resolved = store.resolve(ledger, ref)
            assert resolved.ref == ref and resolved.raw == line and resolved.text == line
            chunks, offset = [], 0
            while True:
                result = investigation.query(ledger, "record", {"ref": ref, "at": AT,
                    "include_undated": True, "offset": offset, "max_chars": 7})
                assert result["ref"] == ref and result["offset"] == offset and result["chars"] == len(line)
                assert result["ts"] is None and result["kind"] == "attachment_text"
                chunks.append(result["text"])
                if result["next_offset"] is None:
                    break
                offset = result["next_offset"]
            assert "".join(chunks) == line
        assert store.read_record(str(attached), record.line, source=spec).raw == line
    assert attached.read_bytes() == body


def test_textual_unknown_file_events_preserve_lexical_navigation_not_writes(tmp_path):
    ledger, attached = fixture(tmp_path, b"independent /p/A.ets mention\nother /p/B.ets mention\n")
    spec = store.source_spec(ledger, str(attached))
    records = list(store.records(str(attached), source=spec))
    search = investigation.query(ledger, "search", {"q": "A.ets", "at": AT, "include_undated": True})
    assert [row["ref"] for row in search["undated"]["rows"]] == [records[0].ref]
    data = raw_events.query(ledger, AT, path="/p/A.ets")
    assert not data["events"] and not data["gaps"]
    # Unknown-time attachment navigation must not disappear when invalid
    # JSON Pointers are removed; it remains lexical, not operation evidence.
    assert data["undated"]["total"] == 1
    row, = data["undated"]["rows"]
    assert row["ref"] == records[0].ref and row["fields"] == []
    assert row["agents"] == [] and row["ts"] is None


def test_real_jsonl_parsing_still_decodes_fields_and_marks_bad_json(tmp_path):
    good = {"timestamp": AT, "type": "unclassified", "payload": {"text": "synthetic"}}
    ledger, attached = fixture(tmp_path, (json.dumps(good) + "\n{unfinished\n").encode(), "journal.jsonl")
    source = store.SourceSpec(logical_name="synthetic-jsonl", timestamp_policy="record")
    first, second = store.records(str(attached), source=source)
    assert first.value == good and first.ts is not None and not first.textual
    assert second.malformed and not second.textual and second.raw == "{unfinished"
    assert store.read_record(str(attached), 1, source=source) == first
    assert store.read_record(str(attached), 2, source=source) == second
    assert any(gap["malformed"] for gap in raw_events.inventory(ledger)["gaps"])


def test_unknown_source_policy_does_not_allow_json_shaped_attachment_actor_or_native_call(tmp_path):
    spoof = {"timestamp": AT, "type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "not-an-actual-call", "name": "Write", "input": {
            "file_path": "/p/A.ets", "content": "not an operation"}}]}}
    ledger, attached = fixture(tmp_path, json.dumps(spoof).encode(), "record.json")
    # Even an erroneously permissive SourceSpec cannot timestamp a physical
    # attachment line. Native source membership never supplies an actor.
    record, = store.records(str(attached), source=store.SourceSpec(timestamp_policy="record"))
    assert record.ts is None and record.value is None and record.textual
    registry = store.sources(ledger)
    assert registry[os.path.normcase(os.path.abspath(attached))] == set()
    inventory = raw_events.inventory(ledger)
    assert not inventory["events"] and not inventory["gaps"]
    row = next(row for row in inventory["unknown_records"] if row["source"] == attached.name)
    assert row["fields"] == [] and row["kind"] == "attachment_text"


def test_undecodable_non_jsonl_remains_a_real_gap_not_sanitized_text(tmp_path):
    ledger, attached = fixture(tmp_path, b"readable prefix\n\xffbad UTF-8\n")
    source = store.source_spec(ledger, str(attached))
    with pytest.raises(UnicodeError):
        list(store.records(str(attached), source=source))
    data = raw_events.inventory(ledger)
    assert any(gap["source"] == attached.name for gap in data["gaps"])
    search = investigation.query(ledger, "search", {"q": "readable", "at": AT, "include_undated": True})
    assert search["gaps"] and not search["raw_scan_complete"]
    assert attached.read_bytes() == b"readable prefix\n\xffbad UTF-8\n"
