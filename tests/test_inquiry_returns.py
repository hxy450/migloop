"""All native tool-return packets remain an input channel, without file edges."""

from pathlib import Path

from tests.test_inquiry_core import build, record, result, ts, use


def test_returns_include_shell_failed_unpaired_and_respect_completion(
    tmp_path, monkeypatch
):
    engine = build(
        tmp_path,
        [
            record(1, use("shell", "Bash", command="cat themes.xml")),
            record(3, result("shell", "Material theme from themes.xml")),
            record(4, result("missing-request", "partial output", error=True)),
            record(5, use("read", "Read", file_path="spec.md")),
            record(8, result("read", "later specification")),
            record(None, result("unknown-time", "unknown-time result")),
        ],
    )
    monkeypatch.setattr(
        Path,
        "open",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("query reopened originals")
        ),
    )
    q = {"op": "agent", "key": "a", "at": ts(6), "view": "returns"}
    data = engine.query(q)
    assert data["total"] == 2 and data["undated_records"] == 1
    assert [r["line"] for r in data["rows"]] == [2, 3]
    assert data["rows"][0]["tools"] == ["Bash"]
    assert data["rows"][1]["return_blocks"][0]["success"] == 0
    assert engine.query({**q, "since": ts(4)})["total"] == 1
    assert engine.query({**q, "undated": True})["total"] == 3
    assert engine.query({**q, "terms": ["themes.xml"]})["total"] == 1
    inputs = engine.query({**q, "view": "inputs"})
    assert inputs["total"] == 0 and inputs["tool_return_total"] == 2
    assert inputs["tool_return_undated"] == 1
    assert engine.query(inputs["tool_return_query"])["total"] == 2
    assert not [
        r
        for r in engine.relations("agent", "a", 10**18)
        if r["path"].endswith("themes.xml")
    ]
    engine.store.close()


def test_codex_unpaired_output_is_not_a_certified_file_read(tmp_path):
    engine = build(
        tmp_path,
        [
            {
                "type": "response_item",
                "timestamp": ts(3),
                "payload": {
                    "type": "function_call_output",
                    "call_id": "missing",
                    "output": "Read A.ets failed",
                },
            }
        ],
    )
    data = engine.query({"op": "agent", "key": "a", "at": ts(4), "view": "returns"})
    assert data["total"] == 1
    assert data["rows"][0]["return_blocks"][0]["success"] is None
    assert engine.relations("pool", None, 10**18) == []
    engine.store.close()
