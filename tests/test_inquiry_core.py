"""Black-box invariants for the new independent event index."""

import json
import re
from pathlib import Path

import pytest

from migloop.inquiry import report
from migloop.inquiry.engine import Engine
from migloop.inquiry.store import Source, Store


def ts(second):
    return f"2026-01-01T00:00:{second:02d}Z"


def record(second, *blocks, **extra):
    return {
        "timestamp": ts(second) if second is not None else None,
        "type": "assistant",
        "message": {"content": list(blocks)},
        **extra,
    }


def use(cid, name="Write", **data):
    return {"type": "tool_use", "id": cid, "name": name, "input": data}


def result(cid, text="ok", error=False):
    return {
        "type": "tool_result",
        "tool_use_id": cid,
        "content": text,
        "is_error": error,
    }


def build(tmp_path, rows, second=None):
    sources = []
    for name, agent, data in [
        ("a.jsonl", "a", rows),
        *([("b.jsonl", "b", second)] if second is not None else []),
    ]:
        path = tmp_path / name
        path.write_text(
            "".join(
                (json.dumps(r, ensure_ascii=False) if isinstance(r, dict) else r) + "\n"
                for r in data
            ),
            encoding="utf-8",
        )
        sources.append(Source(str(path), name, agent, "/proj"))
    store = Store.build(tmp_path / "index.sqlite", sources)
    return Engine(store)


@pytest.fixture
def engine(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="first")),
            record(2, result("w")),
            record(3, use("r", "Read", file_path="/proj/spec.md")),
            record(9, result("r", "LATE INPUT")),
            record(10, use("x", "Bash", command="python mystery.py /proj/A.ets")),
            record(11, result("x", "unknown effects")),
            record(None, {"type": "text", "text": "UNDATED A.ets"}),
            "broken A.ets",
        ],
    )
    yield engine
    engine.store.close()


def test_index_queries_and_unknown_tools_are_reachable(engine, monkeypatch):
    monkeypatch.setattr(
        Path,
        "open",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("query reopened a source")
        ),
    )
    data = engine.query({"op": "file", "key": "A.ets", "at": ts(15), "limit": 100})
    assert data["total"] == 4 and data["related_operations"] == 1
    assert any("mystery.py" in r["excerpt"] for r in data["rows"])
    assert all(r["is_full_original"] is False for r in data["rows"])


def test_late_input_and_relation_do_not_leak(engine):
    assert (
        engine.query({"op": "agent", "key": "a", "at": ts(15)})["undated_records"] == 2
    )
    data = engine.query(
        {
            "op": "search",
            "kind": "agent",
            "key": "a",
            "terms": ["LATE INPUT"],
            "at": ts(5),
        }
    )
    assert data["total"] == 0
    rows = engine.query(
        {"op": "file", "key": "/proj/spec.md", "at": ts(5), "view": "relations"}
    )["rows"]
    assert rows[0]["strength"] == "candidate" and rows[0]["result"] is None
    later = engine.query(
        {"op": "file", "key": "/proj/spec.md", "at": ts(10), "view": "relations"}
    )["rows"]
    assert later[0]["strength"] == "confirmed"


def test_full_scope_search_and_pagination(engine):
    request = {"op": "agent", "key": "a", "at": ts(15), "limit": 1, "undated": True}
    refs, offset = [], 0
    while offset is not None:
        page = engine.query({**request, "offset": offset})
        refs.extend(r["ref"] for r in page["rows"])
        offset = page["next"]
    assert len(refs) == len(set(refs)) == 8
    assert (
        engine.query(
            {"op": "search", "at": ts(15), "terms": ["LATE INPUT", "mystery.py"]}
        )["total"]
        == 2
    )
    assert (
        engine.query({"op": "search", "at": ts(15), "terms": ["LATE|mystery"]})["total"]
        == 0
    )


def test_open_original_scope_digest_and_field(engine):
    ref = engine.store.locate("a.jsonl", 4)
    with pytest.raises(ValueError, match="outside"):
        engine.query({"op": "open", "ref": ref, "at": ts(8)})
    opened = engine.query(
        {
            "op": "open",
            "ref": ref,
            "at": ts(10),
            "pointer": "/message/content/0/content",
        }
    )
    assert opened["text"] == "LATE INPUT" and opened["complete_selected_text"]
    path = Path(engine.store.rows("SELECT path FROM sources")[0]["path"])
    path.write_bytes(path.read_bytes().replace(b"LATE INPUT", b"FAKE INPUT"))
    with pytest.raises(ValueError, match="bytes changed"):
        engine.query({"op": "open", "ref": ref, "at": ts(10)})


def test_record_identity_independent_of_other_sources(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("a", file_path="/proj/a.ets", content="a")),
            record(2, result("a")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 1)
    sources = [Source(str(tmp_path / "a.jsonl"), "a.jsonl", "a", "/proj")]
    second = tmp_path / "other.jsonl"
    second.write_text("{}\n", encoding="utf-8")
    rebuilt = Store.build(
        tmp_path / "other.sqlite", [Source(str(second), "new.jsonl"), *sources]
    )
    assert rebuilt.locate("a.jsonl", 1) == ref
    rebuilt.close()
    engine.store.close()


@pytest.mark.parametrize(
    "tail,expected",
    [
        ([], "candidate"),
        ([record(2, result("w", error=True))], "candidate"),
        ([record(2, result("w")), record(3, result("w"))], "candidate"),
        ([record(0, result("w"))], "candidate"),
        ([record(2, result("w"))], "confirmed"),
    ],
)
def test_failed_pending_duplicate_reverse_are_not_facts(tmp_path, tail, expected):
    engine = build(
        tmp_path, [record(1, use("w", file_path="/proj/a.ets", content="a")), *tail]
    )
    assert (
        engine.query({"op": "file", "key": "a.ets", "at": ts(10), "view": "relations"})[
            "rows"
        ][0]["strength"]
        == expected
    )
    engine.store.close()


def test_never_pair_across_sources_or_parse_nested_code(tmp_path):
    nested = json.dumps(record(2, use("invented", file_path="/proj/invented.ets")))
    engine = build(
        tmp_path,
        [
            record(1, use("same", file_path="/proj/a.ets")),
            record(3, use("shell", "Bash", command=nested)),
        ],
        [record(2, result("same"))],
    )
    rows = engine.store.rows("SELECT * FROM effects")
    assert len(rows) == 1 and rows[0]["strength"] == "candidate"
    assert (
        engine.query({"op": "file", "key": "invented.ets", "at": ts(10)})["total"] == 1
    )
    engine.store.close()


def test_codex_patch_independent_of_wrapper(tmp_path):
    def cx(second, kind, payload):
        return {"timestamp": ts(second), "type": kind, "payload": payload}

    engine = build(
        tmp_path,
        [
            cx(
                1,
                "response_item",
                {
                    "type": "custom_tool_call",
                    "call_id": "x",
                    "name": "exec",
                    "input": "tools.apply_patch(...)",
                },
            ),
            cx(
                2,
                "event_msg",
                {
                    "type": "patch_apply_end",
                    "call_id": "x",
                    "success": True,
                    "changes": {
                        "/proj/A.ets": {"type": "update", "unified_diff": "-a\n+b"}
                    },
                },
            ),
            cx(
                3,
                "response_item",
                {"type": "custom_tool_call_output", "call_id": "x", "output": "done"},
            ),
        ],
    )
    rows = engine.query(
        {"op": "file", "key": "A.ets", "at": ts(10), "view": "relations"}
    )["rows"]
    assert (
        len(rows) == 1
        and rows[0]["basis"] == "patch_apply_end"
        and rows[0]["request"] is None
    )
    engine.store.close()


def test_all_selected_text_is_resumable_and_not_self_certified(tmp_path):
    text = "long中文 data\n" * 3000
    engine = build(tmp_path, [record(1, {"type": "text", "text": text})])
    ref = engine.store.locate("a.jsonl", 1)
    frame = engine.investigate(
        [{"op": "open", "ref": ref, "at": ts(2), "pointer": "/message/content/0/text"}]
    )
    identity = re.search(r"RESULT (\w+)", frame)[1]
    emitted = []
    offset = 0
    while True:
        frame = engine.page(identity, offset)
        assert len(frame) < engine.FRAME + 300
        emitted.append(frame.split("\n", 1)[1].rsplit("\nEND FRAME", 1)[0])
        next_value = re.search(r"END FRAME next=(\w+)", frame)[1]
        if next_value == "none":
            break
        offset = int(next_value)
    assert "".join(emitted) == engine.store.rows("SELECT body FROM runs")[0]["body"]
    assert engine.trace()[0]["visibility"] == []
    assert not engine.observe_visibility(identity, 0, "Warning: truncated output")
    assert engine.observe_visibility(identity, 0, engine.page(identity, 0))
    engine.store.close()


def valid_report(engine):
    return {
        "schema": "inquiry/1",
        "target": {"file": "/proj/A.ets", "at": ts(15), "since": ts(1)},
        "findings": [
            {
                "id": "A",
                "title": "Claim",
                "reason": "model reason, not proven",
                "nodes": [
                    {
                        "id": "a",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(2),
                        "role": "origin",
                        "reason": "actor claim",
                        "evidence": [engine.store.locate("a.jsonl", 1)],
                    },
                    {
                        "id": "f",
                        "kind": "file",
                        "key": "/proj/A.ets",
                        "at": ts(2),
                        "role": "propagated",
                        "reason": "file claim",
                        "evidence": [engine.store.locate("a.jsonl", 2)],
                    },
                ],
                "edges": [
                    {
                        "from": "a",
                        "to": "f",
                        "relation": "write",
                        "claim": "claimed propagation",
                        "evidence": [
                            engine.store.locate("a.jsonl", 1),
                            engine.store.locate("a.jsonl", 2),
                        ],
                    }
                ],
            }
        ],
    }


def test_report_keeps_claims_and_checks_real_edges(engine):
    doc = valid_report(engine)
    checked = report.check(engine, json.dumps(doc), save=True)
    assert len(checked["edges"]) == 1 and checked["edges"][0]["strength"] == "confirmed"
    assert checked["document"] == doc and not checked["semantic_verified"]
    assert engine.trace() == []
    doc["findings"][0]["edges"][0]["relation"] = "read"
    wrong = report.check(engine, json.dumps(doc))
    assert not wrong["edges"] and len(wrong["unverified_edges"]) == 1
    assert wrong["nodes"][0]["reason"] == "actor claim"


def test_report_rejects_temporal_drift_and_fabricated_refs(engine):
    doc = valid_report(engine)
    doc["findings"][0]["nodes"][0]["evidence"] = [
        "fake",
        engine.store.locate("a.jsonl", 4),
    ]
    checked = report.check(engine, json.dumps(doc))
    assert len(checked["issues"]) == 2 and not checked["nodes"][0]["valid_refs"]


@pytest.mark.parametrize("extra", [{"v": 2}, {"via": "a"}, {"until": 3}])
def test_no_legacy_query_contract(engine, extra):
    with pytest.raises(ValueError, match="unknown"):
        engine.query({"op": "file", "key": "A.ets", "at": ts(15), **extra})


def test_no_imports_from_legacy_core():
    import ast

    root = Path(__file__).parents[1] / "src/migloop/inquiry"
    forbidden = {
        "atoms",
        "atoms_collect",
        "filestory",
        "probe",
        "verdict",
        "service",
        "raw_events",
        "temporal",
    }
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (set((node.module or "").split(".")) & forbidden)
                assert not ({alias.name for alias in node.names} & forbidden)
