import hashlib
import json
from datetime import datetime, timezone

import pytest

from migloop import adapters
from migloop.adapters import deveco, deveco_source
from migloop.render import build_html


def _iso_ms(value):
    if type(value) not in (int, float):
        return None
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()


def events(document):
    """DevEco 冻结投影(request / result / message 三种 phase 的 deveco_part 行)的写出器。

    格式的生产方是 a2h-memory fixchain 的 ``migloop.inquiry.source_adapters.export.events``(冻结
    DevEco 会话树给调查索引用);这里照抄一份只为造夹具,测的是会话解析层 deveco_source 读投影。"""
    info = document["info"]
    sid = info["id"]
    session = {"id": sid, "directory": info.get("directory"),
               "parentID": info.get("parentID", info.get("parent_id"))}
    yield {"format": deveco_source.FORMAT, "type": "deveco_session", "session": session,
           "timestamp": _iso_ms((info.get("time") or {}).get("created", info.get("time_created"))),
           "info": info, "origin": {"session": sid}}
    projected = []
    for message in document["messages"]:
        mi = message["info"]
        mid = mi["id"]
        for part in message.get("parts", []):
            encoded = json.dumps(part, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            origin = {"session": sid, "message": mid, "part": part["id"],
                      "part_sha256": hashlib.sha256(encoded.encode()).hexdigest()}
            base = {"format": deveco_source.FORMAT, "type": "deveco_part", "session": session, "origin": origin}
            state = part.get("state") or {}
            times = state.get("time") or {}
            if part.get("type") == "tool":
                req = {k: v for k, v in part.items() if k != "state"}
                req["state"] = {"input": state.get("input"), "time": {"start": times.get("start")}}
                projected.append(dict(base, phase="request", timestamp=_iso_ms(times.get("start")),
                                      message={"id": mid, "role": mi.get("role")}, part=req))
                if state.get("status") in ("completed", "error"):
                    projected.append(dict(base, phase="result", timestamp=_iso_ms(times.get("end")),
                                          message=mi, part=part))
            else:
                time = (part.get("time") or {}).get("end")
                if time is None:
                    time = (mi.get("time") or {}).get("completed" if mi.get("role") == "assistant" else "created")
                projected.append(dict(base, phase="message", timestamp=_iso_ms(time), message=mi, part=part))
    yield from sorted(projected, key=lambda p: (p["timestamp"] or "", p["origin"]["message"],
                      p["origin"]["part"], {"request": 0, "result": 1, "message": 2}[p["phase"]]))


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
