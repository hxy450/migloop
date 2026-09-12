"""Opaque output must retain the native request that produced it."""

from migloop.inquiry.engine import Engine
from tests.test_inquiry_core import build, record, result, ts, use


def test_open_receipt_carries_other_file_command_without_inventing_a_read(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "r",
                    "Bash",
                    command="grep -n controller OtherPage.ets",
                    description="Inspect another page",
                ),
            ),
            record(2, result("r", "controller: transparent")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 2)
    before = engine.store.rows("SELECT * FROM effects")
    data = engine.query({"op": "open", "ref": ref, "at": ts(3), "pointer": ""})
    context = data["request_context"]["requests"]
    assert len(context) == 1 and "OtherPage.ets" in context[0]["argument_preview"]
    assert context[0]["tool"] == "Bash" and context[0]["result_block"] == 0
    assert context[0]["request_block"] == 0
    assert context[0]["not_effect_proof"]
    assert engine.store.rows("SELECT * FROM effects") == before
    Engine(engine.store, session="model", origin="mcp").investigate(
        [{"op": "open", "ref": ref, "at": ts(3)}]
    )
    trace = engine.trace("model")
    assert "OtherPage.ets" in str(trace[0]["context"]["request_context"])
    engine.store.close()


def test_receipt_selects_exact_native_block_not_all_sibling_calls(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use("one", "Bash", command="cat One.ets"),
                use("two", "Bash", command="cat Two.ets"),
            ),
            record(2, result("two", "text without a path")),
        ],
    )
    data = engine.query(
        {"op": "open", "ref": engine.store.locate("a.jsonl", 2), "at": ts(3)}
    )
    rows = data["request_context"]["requests"]
    assert len(rows) == 1 and rows[0]["request_block"] == 1
    assert rows[0]["argument_preview"] == "cat Two.ets"
    engine.store.close()


def test_future_request_context_is_not_leaked_and_changed_parent_is_not_trusted(
    tmp_path,
):
    engine = build(
        tmp_path,
        [
            record(8, use("future", "Bash", command="cat Future.ets")),
            record(2, result("future", "old-looking result")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 2)
    data = engine.query({"op": "open", "ref": ref, "at": ts(3)})
    assert not data["request_context"]["requests"]
    assert data["request_context"]["unavailable"]
    assert "Future.ets" not in str(data["request_context"])
    engine.store.close()


def test_parent_bytes_must_still_match_before_showing_its_command(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("r", "Bash", command="cat One.ets")),
            record(2, result("r", "a result")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 2)
    path = tmp_path / "a.jsonl"
    path.write_bytes(path.read_bytes().replace(b"One.ets", b"Two.ets"))
    data = engine.query({"op": "open", "ref": ref, "at": ts(3)})
    assert not data["request_context"]["requests"]
    assert "changed" in str(data["request_context"]["unavailable"])
    engine.store.close()


def test_record_pair_cannot_lend_certainty_to_an_ambiguous_sibling_slot(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use("ok", "Bash", command="cat One.ets"),
                use("dup", "Bash", command="cat Wrong.ets"),
            ),
            record(2, use("dup", "Bash", command="cat Other.ets")),
            record(3, result("ok", "one"), result("dup", "unbound")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 3)
    data = engine.query({"op": "open", "ref": ref, "at": ts(4)})
    context = data["request_context"]
    assert len(context["requests"]) == 1
    assert context["requests"][0]["argument_preview"] == "cat One.ets"
    assert context["unavailable"][0]["result_block"] == 1
    assert "Wrong.ets" not in str(context) and "Other.ets" not in str(context)
    engine.store.close()


def test_codex_receipt_pair_survives_reopen_and_marks_long_preview(tmp_path):
    import json

    from migloop.inquiry.store import Store

    command = "cat Begin.ets " + "x" * 500 + " End.ets"
    engine = build(
        tmp_path,
        [
            {
                "type": "response_item",
                "timestamp": ts(1),
                "payload": {
                    "type": "function_call",
                    "call_id": "c",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": command}),
                },
            },
            {
                "type": "response_item",
                "timestamp": ts(2),
                "payload": {
                    "type": "function_call_output",
                    "call_id": "c",
                    "output": "text only",
                },
            },
        ],
    )
    ref = engine.store.locate("a.jsonl", 2)
    engine.store.close()
    engine = Engine(Store(tmp_path / "index.sqlite"))
    data = engine.query({"op": "open", "ref": ref, "at": ts(3)})
    request = data["request_context"]["requests"][0]
    assert request["argument_truncated"] and request["argument_chars"] == len(command)
    assert request["argument_preview"].startswith("cat Begin.ets")
    assert request["argument_preview"].endswith("End.ets")
    assert (
        command
        in engine.query({"op": "open", "ref": request["cite"], "at": ts(3)})["text"]
    )
    engine.store.close()
