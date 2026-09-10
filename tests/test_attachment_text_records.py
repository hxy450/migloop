"""Readable text attachments are not thousands of broken JSONL events."""
import json

import pytest

from migloop import atoms, atoms_collect, cc_sources, investigation, raw_events, transcript_store as store
from tests.test_temporal_atom import call, message, result, ts


def build(tmp_path, text, suffix="txt"):
    root = tmp_path / "abcd1234-root.jsonl"
    root.write_text("\n".join(json.dumps(r) for r in [message(0, "task"),
                    call(1, "write", "Write", file_path="/p/A.ets", content="ok"), result(2, "write")]) + "\n", encoding="utf-8")
    attached = tmp_path / root.stem / "tool-results" / ("output." + suffix)
    attached.parent.mkdir(parents=True)
    attached.write_text(text, encoding="utf-8", newline="")
    found = cc_sources.discover([str(root)])
    ledger = atoms.build_ledger(atoms_collect.collect_cc_pool([str(root)], [0], sources=found),
                               auxiliary_sources=found.auxiliary_sources, source_metadata=found.source_metadata)
    return ledger, attached


@pytest.mark.parametrize("suffix", ["txt", "js", "json", "md", "unknown"])
def test_attachment_physical_lines_stay_exact_searchable_and_not_malformed(tmp_path, suffix):
    text = 'const x = "A.ets 中文";\r\n{"timestamp":"2099-01-01T00:00:00Z","message":{"role":"assistant","content":[]}}\r\n'
    ledger, path = build(tmp_path, text, suffix)
    source = store.source_spec(ledger, str(path))
    records = list(store.records(str(path), source=source))
    assert [r.raw for r in records] == text.splitlines()
    assert [r.text for r in records] == text.splitlines()
    assert all(not r.malformed and r.ts is None and r.kind == "attachment_text" for r in records)
    data = raw_events.inventory(ledger)
    assert not data["gaps"]
    assert len(data["events"]) == 1  # Only the real root Write, not quoted source text.
    query = investigation.query(ledger, "search", {"q": "中文", "at": ts(5), "include_undated": True})
    assert len(query["undated"]["rows"]) == 1
    ref = records[0].ref
    raw = investigation.query(ledger, "record", {"ref": ref, "at": ts(5), "include_undated": True})
    assert raw["text"] == text.splitlines()[0]
    expanded = investigation.query(ledger, "expand", {"refs": [{"ref": ref, "pointer": ""}], "at": ts(5), "include_undated": True})
    item, = expanded["items"]
    assert item["status"] == "error" and item["records"] == []
    assert len(item["withheld"]) == 1 and "原文" in item["withheld"][0]["reason"]


def test_large_plain_output_does_not_make_file_overview_undeliverable(tmp_path):
    ledger, path = build(tmp_path, "a readable status line, not a JSON event\n" * 1200)
    requests = [{"tool": "file", "args": {"path": "/p/A.ets", "at": ts(5), "limit": 1}}]
    result = investigation.batch(ledger, requests, max_chars=100000)
    item, = result["items"]
    assert item["status"] == "ok"
    assert not item["data"]["body_sources"]["gaps"]
    assert not item["data"]["coverage"]["native_source_gaps"]
    assert path.read_text(encoding="utf-8").count("\n") == 1200


def test_malformed_jsonl_and_undecodable_attachment_still_disclose_real_gaps(tmp_path):
    ledger, path = build(tmp_path, "not valid JSONL\n", "jsonl")
    data = raw_events.inventory(ledger)
    assert any(g["error"] == "malformed JSON record" for g in data["gaps"])
    path.write_bytes(b"\xff\n")
    assert raw_events.inventory(ledger)["gaps"]
