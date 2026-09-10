import json
from types import SimpleNamespace

import pytest

from migloop import transcript_store as store


def test_direct_record_matches_stream_with_bom_crlf_and_unicode(tmp_path):
    path = tmp_path / "MixedCase.jsonl"
    path.write_bytes(b"\xef\xbb\xbf" + ('{"timestamp":"2026-01-01T00:00:00Z","text":"中文"}\r\n{broken\r\n42\r\n').encode())
    streamed = list(store.records(str(path)))
    for number, expected in enumerate(streamed, 1):
        actual = store.read_record(str(path), number)
        assert actual == expected
        assert actual.ref == expected.ref
        ledger = SimpleNamespace(agents={"a": SimpleNamespace(id="a", sources=[str(path)], actions=[])})
        assert store.resolve(ledger, actual.ref) == actual


def test_direct_record_does_not_parse_prefix_and_invalidates_offsets(tmp_path, monkeypatch):
    path = tmp_path / "source.jsonl"
    path.write_text('{broken\n{"text":"target"}\n', encoding="utf-8")
    loads = json.loads
    parsed = []
    def load(text):
        parsed.append(text)
        return loads(text)
    monkeypatch.setattr(store.json, "loads", load)
    assert store.read_record(str(path), 2).value == {"text": "target"}
    assert len(parsed) == 1
    path.write_text('{"longer":"changed"}\n{"text":"new"}\n', encoding="utf-8")
    assert store.read_record(str(path), 2).value == {"text": "new"}


@pytest.mark.parametrize("number", [0, -1, True, "1", 3])
def test_invalid_or_missing_physical_line_fails(tmp_path, number):
    path = tmp_path / "s.jsonl"
    path.write_text('{}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        store.read_record(str(path), number)
