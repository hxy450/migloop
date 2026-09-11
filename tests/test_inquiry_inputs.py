from tests.test_inquiry_core import build, record, result, ts, use


def message(second, text):
    return {
        "timestamp": ts(second),
        "type": "user",
        "message": {"role": "user", "content": text},
    }


def test_input_view_keeps_task_channel_separate_from_native_read_files(tmp_path):
    reply = record(3, result("r", "read input"))
    reply["type"] = "user"
    reply["message"]["role"] = "user"
    engine = build(
        tmp_path,
        [
            message(1, "Task: implement the input contract"),
            record(2, use("r", "Read", file_path="/proj/spec.md")),
            reply,
            record(4, use("w", file_path="/proj/A.ets", content="new")),
            record(5, result("w")),
            message(8, "Later task"),
        ],
    )
    actor = engine.query({"op": "file", "key": "A.ets", "at": ts(9)})["participants"][0]
    data = engine.query(
        {"op": "agent", "scope": actor["input_scope"], "view": "inputs"}
    )
    assert data["total"] == 1 and data["input_message_total"] == 1
    assert "input contract" in data["input_messages"][0]["excerpt"]
    full = engine.query({"op": "agent", "scope": actor["scope"], "view": "messages"})
    assert full["total"] == 2 and "Later task" in full["rows"][0]["excerpt"]
    assert len(engine.store.rows("SELECT * FROM input_messages")) == 2
    engine.store.close()


def test_empty_native_read_list_does_not_hide_task_inputs(tmp_path):
    engine = build(
        tmp_path,
        [
            message(1, "Later quality check requests a comment-only change"),
            record(2, use("w", file_path="A.ets", content="new")),
            record(3, result("w")),
        ],
    )
    data = engine.query({"op": "agent", "key": "a", "at": ts(3), "view": "inputs"})
    assert data["total"] == 0 and data["input_message_total"] == 1
    opened = engine.query(
        {"op": "open", "ref": data["input_messages"][0]["cite"], "at": ts(3)}
    )
    assert opened["text"] == "Later quality check requests a comment-only change"
    engine.store.close()
