import json

import pytest

from migloop import adapters
from migloop.adapters import deveco, deveco_source
from migloop.inquiry.source_adapters.export import events
from migloop.render import build_html


def document(sid, parent=None, output=12):
    start = 1767225600000
    return {"info": {"id": sid, "parentID": parent, "directory": "/app", "model": {"id": sid + "-model"},
                     "title": "implement: " + sid, "time": {"created": start, "updated": start + 5000}},
            "messages": [{"info": {"id": "m1", "role": "assistant", "time": {"created": start, "completed": start + 4000},
                                   "tokens": {"input": 40, "output": output, "reasoning": 3, "cache": {"read": 20}}},
                          "parts": [{"id": "p1", "type": "tool", "tool": "write", "callID": "c1",
                                     "state": {"status": "completed", "input": {"filePath": "/app/entry/src/main/ets/Index.ets", "content": "struct Index {}"},
                                               "output": "ok", "time": {"start": start + 1000, "end": start + 2000}}}]}]}


def save(path, doc, projection):
    raw = "\n".join(json.dumps(e) for e in events(doc)) if projection else json.dumps(doc, indent=2)
    path.write_text(raw, encoding="utf-8")


@pytest.mark.parametrize("projection", [False, True])
def test_portable_tree_report_without_local_database(tmp_path, monkeypatch, projection):
    root = tmp_path / "root.jsonl"
    save(root, document("ses_root"), projection)
    save(tmp_path / "child.jsonl", document("ses_child", "ses_root", 21), projection)
    save(tmp_path / "grandchild.jsonl", document("ses_grandchild", "ses_child", 30), projection)
    save(tmp_path / "unrelated.jsonl", document("ses_other", "ses_else", 999), projection)
    monkeypatch.setattr(deveco, "_find_db", lambda *_: pytest.fail("portable report consulted local DB"))
    assert adapters.detect(str(root)).FORMAT == "deveco"
    trace = adapters.detect(str(root)).extract(str(root))
    assert trace["totals"]["tool_calls"] == 1  # request/result projections are one tool
    assert trace["totals"]["main_output_tokens"] == 15
    assert trace["totals"]["subagent_output_tokens"] == 57
    assert trace["totals"]["agent_calls"] == 2
    assert trace["totals"]["active_ms"] == 1000
    assert trace["billing"]["ses_child-model"]["out"] == 24
    assert "ses_other-model" not in trace["billing"]
    assert all(a["tool_uses"] == 1 for a in trace["agents"])
    html = build_html(trace)
    assert "ses_grandchild" in html and "__TRACE_JSON__" not in html


def test_flat_database_metadata_and_projection_roundtrip(tmp_path):
    doc = document("ses_root")
    doc["info"].update(model='{"id":"db-model"}', time_created=1, time_updated=2,
                       tokens_input=40, tokens_output=12, tokens_reasoning=3, tokens_cache_read=20)
    del doc["info"]["time"]
    path = tmp_path / "root.jsonl"
    save(path, doc, True)
    actual = deveco_source.load(path)
    assert actual["info"]["time"] == {"created": 1, "updated": 2}
    assert actual["info"]["model"]["id"] == "db-model"
    assert actual["info"]["tokens"]["cache"]["read"] == 20
    assert actual["messages"] == doc["messages"]


def test_mixed_projection_is_rejected(tmp_path):
    rows = list(events(document("ses_root"))) + list(events(document("ses_other")))
    path = tmp_path / "mixed.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in rows), encoding="utf-8")
    with pytest.raises(ValueError, match="mixed"):
        deveco_source.load(path)


def test_lineage_classifier_is_scoped_even_on_error(tmp_path, monkeypatch):
    path = tmp_path / "root.json"
    save(path, document("ses_root"), False)
    original = deveco.common._spec_kind

    def fail(*args, **kwargs):
        assert deveco.common._spec_kind is original
        assert kwargs["spec_kind"](".deveco/workflows/explore/plan.md") == "analysis"
        raise RuntimeError("test renderer failure")

    monkeypatch.setattr(deveco.common, "build_lineage", fail)
    with pytest.raises(RuntimeError, match="renderer"):
        deveco.extract(str(path))
    assert deveco.common._spec_kind is original
