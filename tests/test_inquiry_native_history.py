"""Native operation boundaries, not guessed file-state or causal authors."""

import json

import pytest

from migloop.inquiry.native_text import term_deltas
from migloop.inquiry.report import check
from tests.test_inquiry_core import build, record, result, ts, use


def test_two_same_file_calls_in_one_record_keep_their_own_outcomes(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "ok",
                    "Edit",
                    file_path="/proj/A.ets",
                    old_string="a",
                    new_string="b",
                ),
                use(
                    "bad",
                    "Edit",
                    file_path="/proj/A.ets",
                    old_string="b",
                    new_string="c",
                ),
            ),
            record(2, result("ok"), result("bad", "no match", error=True)),
        ],
    )
    data = engine.query({"op": "file", "key": "A.ets", "at": ts(3), "view": "changes"})
    assert data["total"] == 2
    by_text = {row["payloads"][0]["body"]["new_string"]: row for row in data["rows"]}
    assert by_text["b"]["strength"] == "confirmed"
    assert by_text["c"]["strength"] == "candidate"
    assert all(len(row["payloads"]) == 1 for row in data["rows"])
    assert by_text["b"]["link"] != by_text["c"]["link"]
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "since": ts(0), "at": ts(3)},
        "findings": [
            {
                "id": "A",
                "title": "two calls",
                "reason": "One succeeds, one fails.",
                "changes": [by_text["b"]["request"]],
                "nodes": [],
            }
        ],
    }
    graph = check(engine, json.dumps(doc))
    assert len(graph["edges"]) == 2
    assert {r["strength"] for r in graph["edges"]} == {"confirmed", "candidate"}
    assert len({r["operation"] for r in graph["edges"]}) == 2
    assert {row["request_slot"] for row in data["rows"]} == {0, 1}
    engine.store.close()


def test_literal_history_retains_context_and_does_not_claim_a_write_is_birth(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1, use("w", file_path="/proj/A.ets", content="export class Dice {}")
            ),
            record(2, result("w")),
            record(
                3,
                use(
                    "e",
                    "Edit",
                    file_path="/proj/A.ets",
                    old_string="export class Dice {}",
                    new_string="export class Dice {}\nconsole.error('x')",
                ),
            ),
            record(4, result("e")),
            record(
                5,
                use(
                    "f",
                    "Edit",
                    file_path="/proj/A.ets",
                    old_string="console.error('x')",
                    new_string="hilog.error('x')",
                ),
            ),
            record(8, result("f")),
        ],
    )
    q = {
        "op": "blame",
        "key": "A.ets",
        "at": ts(9),
        "terms": ["console", "export class"],
        "limit": 2,
    }
    first = engine.query(q)
    assert first["total"] == 3 and first["next"] == 2
    assert first["rows"][0]["term_deltas"][0]["delta"] == "write_contains_not_birth"
    deltas = {h["term"]: h["delta"] for h in first["rows"][1]["term_deltas"]}
    assert deltas == {
        "console": "added_in_payload",
        "export class": "unchanged_matching_lines",
    }
    second = engine.query({**q, "offset": 2})
    assert second["rows"][0]["term_deltas"][0]["delta"] == "removed_in_payload"
    assert second["next"] is None and second["status"] == "not_proven"
    pending = engine.query({**q, "at": ts(6), "offset": 2})["rows"][0]
    assert pending["strength"] == "candidate" and pending["result"] is None
    absent = engine.query({**q, "terms": ["unseen"]})
    assert absent["total"] == 0 and "cannot prove absence" in absent["note"]
    agent = engine.query({"op": "agent", "key": "a", "at": ts(9)})
    with pytest.raises(ValueError, match="file scope"):
        engine.query({"op": "blame", "scope": agent["scope_id"]})
    engine.store.close()


def test_patch_context_is_not_a_removal_and_multiedit_steps_remain_separate():
    patch = [
        {
            "block": 0,
            "tool": "apply_patch",
            "body": {
                "unified_diff": "--- a/A.ets\n+++ b/A.ets\n@@ -1,2 +1,2 @@\n export class Dice\n-console.error('x')\n+hilog.error('x')"
            },
        }
    ]
    hits = term_deltas(patch, ["export", "console", "hilog"])
    assert [h["delta"] for h in hits] == [
        "unchanged_matching_lines",
        "removed_in_payload",
        "added_in_payload",
    ]
    edits = [
        {
            "block": 1,
            "tool": "MultiEdit",
            "body": {
                "edits": [
                    {"old_string": "x", "new_string": "token"},
                    {"old_string": "token", "new_string": "z"},
                ]
            },
        }
    ]
    hits = term_deltas(edits, ["token"])
    assert [h["step"] for h in hits] == [0, 1]
    assert [h["delta"] for h in hits] == ["added_in_payload", "removed_in_payload"]
