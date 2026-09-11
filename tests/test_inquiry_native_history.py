"""Native operation boundaries, not guessed file-state or causal authors."""

import json
import re

import pytest

from migloop.inquiry.native_text import term_deltas
from migloop.inquiry.report import check
from migloop.inquiry.store import encode, literal_any, timestamp
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


def test_pool_does_not_silently_ignore_an_agent_key(tmp_path):
    engine = build(tmp_path, [record(1, use("s", "Bash", command="echo needle"))])
    with pytest.raises(ValueError, match="pool search does not accept key"):
        engine.query({"op": "search", "kind": "pool", "key": "a", "at": ts(2)})
    assert (
        engine.query({"op": "search", "kind": "agent", "key": "a", "at": ts(2)})[
            "total"
        ]
        == 1
    )
    engine.store.close()


def test_call_terms_include_returned_output_but_not_future_output(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("s", "Bash", command="python mystery.py A.ets")),
            record(4, result("s", "updated mask in A.ets")),
        ],
    )
    query = {
        "op": "file",
        "key": "A.ets",
        "at": ts(2),
        "view": "calls",
        "terms": ["mask"],
    }
    assert engine.query(query)["total"] == 0
    assert engine.query({**query, "at": ts(5)})["total"] == 1
    assert engine.store.rows("SELECT * FROM effects") == []
    assert engine.query({**query, "op": "agent", "key": "a", "at": ts(5)})["total"] == 1
    engine.store.close()


def test_native_node_presence_does_not_scan_text_and_keeps_time_boundaries(tmp_path):
    engine = build(
        tmp_path,
        [
            record(2, use("r", "Read", file_path="A.ets")),
            record(5, result("r", "late observation")),
        ],
    )

    def no_text_scan(*_):
        raise AssertionError("native existence must not scan transcript text")

    engine.store.db.create_function("literal_contains", 2, no_text_scan)
    assert not engine.store.has_records("file", "/proj/A.ets", timestamp(ts(1)))
    assert engine.store.has_records("file", "/proj/A.ets", timestamp(ts(3)))
    assert engine.store.has_records("agent", "a", timestamp(ts(3)))
    assert not engine.store.has_records("agent", "a", timestamp(ts(1)))
    engine.store.close()


def test_lexical_presence_requires_full_path_and_does_not_include_future(tmp_path):
    engine = build(
        tmp_path, [record(2, use("s", "Bash", command="python unknown.py /real/B.ets"))]
    )
    assert engine.store.has_records("file", "/real/B.ets", timestamp(ts(3)))
    assert not engine.store.has_records("file", "/wrong/B.ets", timestamp(ts(3)))
    assert not engine.store.has_records("file", "/real/B.ets", timestamp(ts(1)))
    assert engine.store.rows("SELECT * FROM effects") == []
    engine.store.close()


def test_reused_offset_cannot_masquerade_as_a_zero_match_search(tmp_path):
    engine = build(tmp_path, [record(1, {"type": "text", "text": "needle"})])
    with pytest.raises(ValueError, match="restart at offset=0"):
        engine.query({"op": "search", "at": ts(2), "terms": ["needle"], "offset": 100})
    assert (
        engine.query({"op": "search", "at": ts(2), "terms": ["absent"]})["total"] == 0
    )
    engine.store.close()


def test_continuation_repeats_the_actual_record_identity_and_time(tmp_path):
    engine = build(
        tmp_path, [record(1, use("w", file_path="A.ets", content="x" * 30000))]
    )
    ref = engine.store.locate("a.jsonl", 1)
    frame = engine.investigate([{"op": "open", "ref": ref, "at": ts(5)}])
    identity = re.search(r"RESULT (\w+)", frame)[1]
    offset = int(re.search(r"END FRAME next=(\d+)", frame)[1])
    context = json.loads(frame.rsplit("; CONTEXT ", 1)[1])
    assert context["record_owner"] == "a" and context["source"] == "a.jsonl"
    assert timestamp(context["at"]) == timestamp(ts(1))
    second = engine.page(identity, offset)
    assert json.loads(second.rsplit("; CONTEXT ", 1)[1]) == context
    engine.store.close()


def test_multiterm_search_folds_once_and_retains_unicode_literal_semantics(tmp_path):
    class CountedText(str):
        folds = 0

        def casefold(self):
            self.folds += 1
            return super().casefold()

    text = CountedText("Straße has 100% literal _ marks")
    assert literal_any(text, encode(["absent", "strasse", "100%", "_"]))
    assert text.folds == 1
    engine = build(
        tmp_path,
        [
            record(1, {"type": "text", "text": text}),
            record(2, {"type": "text", "text": "other"}),
        ],
    )
    result = engine.query(
        {"op": "search", "at": ts(3), "terms": ["STRASSE", "never", "100%", "_"]}
    )
    assert result["total"] == 1
    assert (
        engine.query({"op": "search", "at": ts(3), "terms": ["100_", "%absent%"]})[
            "total"
        ]
        == 0
    )
    engine.store.close()


def test_agent_search_does_not_filter_other_agents_text(tmp_path):
    engine = build(
        tmp_path,
        [record(1, {"type": "text", "text": "irrelevant " * 100}) for _ in range(100)],
        [record(1, {"type": "text", "text": "needle"})],
    )
    calls = []

    def counted(body, terms):
        calls.append(body)
        return literal_any(body, terms)

    engine.store.db.create_function("literal_any", 2, counted, deterministic=True)
    data = engine.query(
        {
            "op": "search",
            "kind": "agent",
            "key": "b",
            "at": ts(2),
            "terms": ["needle", "absent"],
        }
    )
    assert data["total"] == 1
    assert all("irrelevant" not in body for body in calls)
    engine.store.close()


def test_file_search_filters_its_indexed_candidates_before_matching_text(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use(f"other-{i}", "Bash", command="python script.py Other.ets"))
            for i in range(100)
        ]
        + [record(1, use("target", "Bash", command="python script.py A.ets"))],
    )
    calls = []

    def counted(body, terms):
        calls.append(body)
        return literal_any(body, terms)

    engine.store.db.create_function("literal_any", 2, counted, deterministic=True)
    data = engine.query(
        {
            "op": "file",
            "key": "A.ets",
            "at": ts(2),
            "view": "calls",
            "terms": ["script.py"],
        }
    )
    assert data["total"] == 1
    assert all("Other.ets" not in body for body in calls)
    engine.store.close()


def test_command_window_does_not_hide_a_second_change_in_the_same_packet(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "s",
                    "Bash",
                    command="python - <<'PY'\nfirst = 'needleA'\nsecond = 'collateralB'\nPY",
                ),
            ),
            record(2, result("s", "needleA\nother output\ncollateralB")),
        ],
    )
    data = engine.query(
        {
            "op": "open",
            "ref": engine.store.locate("a.jsonl", 1),
            "at": ts(3),
            "terms": ["needleA"],
            "context": 0,
        }
    )
    assert "needleA" in data["text"] and "collateralB" in data["text"]
    assert data["selection"].startswith("whole_argument_packet")
    assert data["requested_window_ranges"] != data["content_line_ranges"]
    output = engine.query(
        {
            "op": "open",
            "ref": engine.store.locate("a.jsonl", 2),
            "at": ts(3),
            "terms": ["needleA"],
            "context": 0,
        }
    )
    assert "collateralB" not in output["text"]
    assert engine.store.rows("SELECT * FROM effects") == []
    engine.store.close()


def test_multiedit_parameters_remain_complete_but_pointer_stays_explicit(tmp_path):
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
                        {"old_string": "one", "new_string": "needle"},
                        {"old_string": "two", "new_string": "collateral"},
                    ],
                ),
            )
        ],
    )
    q = {
        "op": "open",
        "ref": engine.store.locate("a.jsonl", 1),
        "at": ts(2),
        "terms": ["needle"],
        "context": 0,
    }
    assert "collateral" in engine.query(q)["text"]
    explicit = engine.query(
        {**q, "pointer": "/message/content/0/input/edits/0/new_string"}
    )
    assert explicit["text"] == "needle" and explicit["projection"] == "json_pointer"
    engine.store.close()
