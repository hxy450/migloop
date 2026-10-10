"""Windows drive paths name one file regardless of case (a writer typed Entry/ for entry/)."""

import json

from migloop.inquiry.engine import Engine
from migloop.inquiry.native_text import change_payloads
from migloop.inquiry.store import Source, Store, same_path


def ts(second):
    return f"2026-01-01T00:00:{second:02d}Z"


def use(second, cid, name, **data):
    return {"timestamp": ts(second), "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": cid, "name": name, "input": data}]}}


def result(second, cid):
    return {"timestamp": ts(second), "type": "user",
            "message": {"content": [{"type": "tool_result", "tool_use_id": cid, "content": "ok"}]}}


def build(tmp_path, agents, cwd):
    sources = []
    for agent, rows in agents.items():
        path = tmp_path / f"{agent}.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        sources.append(Source(str(path), path.name, agent, cwd))
    return Engine(Store.build(tmp_path / "index.sqlite", sources))


def test_drive_path_spellings_fold_into_one_file(tmp_path):
    engine = build(tmp_path, {
        "a": [use(1, "w", "Write", file_path="C:/proj/entry/m.json5", content="{}"), result(2, "w"),
              use(3, "r", "Read", file_path="C:\\proj\\entry\\m.json5"), result(4, "r")],
        "b": [use(5, "e", "Edit", file_path="C:/proj/Entry/m.json5", old_string="{}", new_string="{x}"),
              result(6, "e")],
    }, "C:/proj")
    store = engine.store
    canonical = "C:/proj/entry/m.json5"
    assert [r["path"] for r in store.rows("SELECT path FROM files")] == [canonical]
    assert {r["path"] for r in store.rows("SELECT path FROM effects")} == {canonical}
    assert store.rows("SELECT alias, path FROM file_aliases") == [{"alias": "C:/proj/Entry/m.json5", "path": canonical}]
    for key in ("C:/proj/Entry/m.json5", "c:\\PROJ\\ENTRY\\M.JSON5", "Entry/m.json5"):
        assert store.resolve_file(key) == canonical
    edit = store.rows("SELECT * FROM effects WHERE agent='b'")
    assert [e["op"] for e in edit] == ["write"]
    assert change_payloads(store, edit[0])[0]["body"]["new_string"] == "{x}"
    assert store.has_records("file", "C:/proj/Entry/m.json5", ts(10))
    store.close()


def test_posix_paths_stay_case_sensitive(tmp_path):
    engine = build(tmp_path, {
        "a": [use(1, "w", "Write", file_path="/proj/A.ets", content="1"), result(2, "w"),
              use(3, "v", "Write", file_path="/proj/a.ets", content="2"), result(4, "v")],
    }, "/proj")
    assert sorted(r["path"] for r in engine.store.rows("SELECT path FROM files")) == ["/proj/A.ets", "/proj/a.ets"]
    assert engine.store.rows("SELECT * FROM file_aliases") == []
    assert not same_path("/proj/A.ets", "/proj/a.ets") and same_path("C:/p/A.ets", "c:/P/a.ets")
    engine.store.close()
