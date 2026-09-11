"""Unfiltered native deltas expose intermediate changes without replay."""

import json

import pytest

from migloop.inquiry.engine import Engine
from migloop.inquiry.native_text import change_outline
from tests.test_inquiry_core import build, record, result, ts, use


@pytest.mark.parametrize(
    "old,new", [("line\n", "line"), ("one\r\ntwo\r\n", "one\ntwo\n")]
)
def test_outline_does_not_erase_line_ending_only_changes(old, new):
    rows = change_outline(
        [{"tool": "Edit", "block": 0, "body": {"old_string": old, "new_string": new}}]
    )
    assert rows[0]["only_line_endings_changed"] and not rows[0]["literal_equal"]
    assert "line endings differ" in rows[0]["text"]


def test_outline_shows_deleted_code_without_needing_the_right_keyword(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="A.ets", content="base\n" * 1000)),
            record(2, result("w")),
            record(
                3,
                use(
                    "e",
                    "Edit",
                    file_path="A.ets",
                    old_string="same\noldCallback()\nsame",
                    new_string="same\n// callback removed\nsame",
                ),
            ),
            record(4, result("e")),
            record(5, use("b", "Bash", command="python mystery.py A.ets")),
            record(6, result("b", "done")),
            record(
                7,
                use(
                    "e2",
                    "Edit",
                    file_path="A.ets",
                    old_string="differentName()",
                    new_string="newName()",
                ),
            ),
            record(8, result("e2", error=True)),
        ],
    )
    q = {"op": "file", "key": "A.ets", "at": ts(9), "view": "outline"}
    data = engine.query(q)
    assert data["total"] == 3
    assert data["rows"][0]["outline"][0]["snapshot_lines"] == 1000
    assert data["rows"][0]["outline"][0]["kind"] == "snapshot_folded"
    text = data["rows"][1]["outline"][0]["text"]
    assert "-oldCallback()" in text and "+// callback removed" in text
    assert "\nsame" not in text  # unchanged context is not repeated
    assert data["rows"][2]["strength"] == "candidate"
    assert "not" in data["note"] and data["opaque_query"]["view"] == "calls"
    rendered = Engine.render(1, {"ok": True, "query": q, "data": data})
    assert "-oldCallback()" in rendered and "base\n" * 100 not in rendered
    assert "END NATIVE" in rendered
    assert any(
        "mystery.py" in r["excerpt"] for r in engine.query(data["opaque_query"])["rows"]
    )
    # Explicit full change payload is unchanged and still contains all 1000 lines.
    full = engine.query({**q, "view": "changes"})
    assert full["rows"][0]["payloads"][0]["body"]["content"] == "base\n" * 1000
    late = engine.query({**q, "since": ts(7)})
    assert late["total"] == 1 and late["rows"][0]["strength"] == "candidate"
    engine.store.close()


def test_outline_preserves_multiedit_steps_and_noop_parameters(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "m",
                    "MultiEdit",
                    file_path="A.ets",
                    edits=[
                        {"old_string": "one", "new_string": "two"},
                        {"old_string": "keep", "new_string": "keep"},
                    ],
                ),
            ),
            record(2, result("m")),
        ],
    )
    data = engine.query({"op": "file", "key": "A.ets", "at": ts(3), "view": "outline"})
    changes = data["rows"][0]["outline"]
    assert [r["step"] for r in changes] == [0, 1]
    assert "+two" in changes[0]["text"]
    assert changes[1]["text"] == "" and changes[1]["kind"] == "edit_delta"
    engine.store.close()


def test_outline_codex_patch_is_native_literal_not_script_effect(tmp_path):
    patch = "@@ -1 +1 @@\n-old\n+new"
    engine = build(
        tmp_path,
        [
            {
                "timestamp": ts(1),
                "type": "event_msg",
                "payload": {
                    "type": "patch_apply_end",
                    "call_id": "p",
                    "success": True,
                    "changes": {
                        "/proj/A.ets": {"type": "update", "unified_diff": patch}
                    },
                },
            }
        ],
    )
    data = engine.query({"op": "file", "key": "A.ets", "at": ts(3), "view": "outline"})
    assert data["rows"][0]["outline"][0]["text"] == patch
    assert data["rows"][0]["strength"] == "confirmed"
    assert json.loads(
        engine.store.rows(
            "SELECT payload FROM handles WHERE id=?", (data["rows"][0]["actor_scope"],)
        )[0]["payload"]
    )["at"].startswith("2026-01-01T00:00:03")
    engine.store.close()
