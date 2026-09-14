"""Explicit shell path mentions unlock identity, never confirmed file effects."""

import copy
import json

import pytest

from migloop.inquiry.card import CardError
from migloop.inquiry.command_shape import literal_path_mentions
from migloop.inquiry.report import check, load_report
from migloop.inquiry.store import Store, timestamp
from tests.test_inquiry_core import build, record, result, ts, use


XML = "/source/app/src/main/res/drawable/seekbar_horizontal_style.xml"
RELATIVE = "app/src/main/res/drawable/seekbar_horizontal_style.xml"
COMMAND = (
    "cd /source && for f in " + RELATIVE + " app/other.xml; "
    'do echo "=== $f ==="; cat "$f"; echo; done'
)
RECEIPT = "=== " + RELATIVE + ' ===\n<size android:height="4dp" />'


@pytest.mark.parametrize("tool,key", [("Bash", "command"), ("functions.exec_command", "cmd"), ("run_shell_command", "command")])
def test_only_literal_relative_paths_use_the_explicit_directory(tool, key):
    assert literal_path_mentions(tool, {key: COMMAND}) == ["/source/app/other.xml", XML]
    assert literal_path_mentions(tool, {key: "cd '/source path' && cat ./app/one.xml"}) == ["/source path/app/one.xml"]


@pytest.mark.parametrize("command", [
    "cat app/one.xml", "cd relative && cat app/one.xml",
    "cd $SOURCE && cat app/one.xml", "cd /source/$part && cat app/one.xml",
    "cd /source && cat $part/one.xml", "cd /source && cat app/${part}.xml",
    "cd $(pwd) && cat app/one.xml", "cd /source && cat $(echo app/one.xml)",
    "cd /source && cat `echo app/one.xml`", "cd /source && cat app/*.xml",
    "cd /source && cat app/one.xml > output.xml", "cd /source && cat app/one.xml # comment",
    "cd /source && cd /other && cat app/one.xml", "cd /source && builtin cd /other; cat app/one.xml",
    "cd /source && pushd /other; cat app/one.xml", "cd /source && source helper.sh; cat app/one.xml",
    "cd /source && . helper.sh; cat app/one.xml", "cd /source && eval 'cd /other'; cat app/one.xml",
    "cd /source && env -C /other cat app/one.xml", "cd /source && git -C /other show app/one.xml",
    "cd /source && alias hop='cd /other'; hop; cat app/one.xml",
    "cd /source && (cd /other; cat app/one.xml)", 'cd /source "&&" cat app/one.xml',
    "cd /source && cat '../app/one.xml'", "cd /source/link/.. && cat app/one.xml",
    "cd /source && cat 'app/one.xml", "cd /source; cat app/one.xml",
])
def test_uncertain_directory_expansions_and_shell_shapes_yield_no_hint(command):
    assert literal_path_mentions("Bash", {"command": command}) == []


def test_non_shell_payloads_do_not_create_lexical_file_identities(tmp_path):
    engine = build(tmp_path, [
        record(1, {"type": "text", "text": COMMAND}),
        record(2, result("not-a-call", COMMAND)),
        record(3, use("x", "OtherTool", command=COMMAND)),
    ])
    try:
        assert not engine.query({"op": "catalog", "kind": "file", "q": "one.xml"})["rows"]
        assert not engine.store.rows("SELECT * FROM files")
    finally:
        engine.store.close()


@pytest.fixture
def shell_input(tmp_path):
    engine = build(tmp_path, [
        record(1, use("read", "Bash", command=COMMAND)),
        record(2, result("read", RECEIPT)),
        record(3, use("write", file_path="/proj/Target.ets", content="generated page")),
        record(4, result("write")),
    ])
    source, actor = {"key": XML, "at": ts(2)}, {"key": "a", "at": ts(4)}
    target = {"key": "/proj/Target.ets", "at": ts(9)}
    card = {"target": target, "summary": "Source input and generated output", "recommendations": [],
            "nodes": [{**source, "reason": "XML received in the loop output"}, {**actor, "reason": "Resource consumer"}],
            "edges": [{"from": source, "to": actor}, {"from": actor, "to": target}]}
    try:
        yield engine, card
    finally:
        engine.store.close()


def test_mentions_are_queryable_but_do_not_prove_a_read(shell_input):
    engine, _ = shell_input
    assert engine.query({"op": "catalog", "kind": "file", "q": "seekbar_horizontal_style.xml"})["rows"] == [{"key": XML}]
    calls = engine.query({"op": "file", "key": XML, "at": ts(5), "view": "calls"})
    assert len(calls["rows"]) == 1 and calls["rows"][0]["results"]
    opened = engine.query({"op": "open", "ref": calls["rows"][0]["results"][0], "at": ts(5)})
    assert RECEIPT in opened["text"] and opened["request_context"]["requests"][0]["not_effect_proof"]
    assert not engine.query({"op": "file", "key": XML, "at": ts(5), "view": "relations"})["rows"]
    assert not engine.store.rows("SELECT * FROM effects WHERE op='read'")
    assert engine.store.rows("SELECT * FROM mentions WHERE name=?", (XML.casefold(),))
    assert engine.store.rows("SELECT * FROM mentions WHERE name=?", ("seekbar_horizontal_style.xml",))


def test_same_event_force_requires_prior_feedback_and_stays_dashed(shell_input):
    engine, card = shell_input
    forced = copy.deepcopy(card)
    forced["edges"][0].update(force=True, reason="The literal loop path and returned XML were reviewed",
                              evidence=[{"source": "a.jsonl", "line": 1}, {"source": "a.jsonl", "line": 2}])
    initial = check(engine, json.dumps(forced), save=True)
    assert initial["unverified_edges"][0]["code"] == "force_before_feedback"
    ordinary = check(engine, json.dumps(card), save=True)
    assert ordinary["unverified_edges"][0]["force_eligible"]
    effects = engine.store.rows("SELECT * FROM effects")
    final = check(engine, json.dumps(forced), save=True)
    assert final["delivery"]["status"] == "ready_for_review"
    edge, = [e for e in final["edges"] if e["relation"] == "read"]
    assert edge["source"] == "model_review" and edge["strength"] == "candidate" and edge["force"]
    assert not edge["semantic_verified"] and edge["checked_after"] == ordinary["report_id"]
    assert load_report(engine, final["report_id"])["edges"] == final["edges"]
    assert engine.store.rows("SELECT * FROM effects") == effects


@pytest.mark.parametrize("fault", ["wrong_directory", "future_node", "later_window"])
def test_full_identity_and_time_cannot_be_bypassed_by_a_basename(shell_input, fault):
    engine, card = shell_input
    source = card["nodes"][0]
    if fault == "wrong_directory":
        source["key"] = XML.replace("/source/", "/unrelated/")
    elif fault == "future_node":
        source["at"] = ts(0)
    else:
        assert not engine.store.has_records("file", XML, timestamp(ts(9)), since=timestamp(ts(3)))
        return
    card["edges"][0]["from"] = {k: source[k] for k in ("key", "at")}
    with pytest.raises(CardError):
        check(engine, json.dumps(card))


def test_future_receipt_cannot_be_forced_into_an_earlier_node(shell_input):
    engine, card = shell_input
    card["nodes"][0]["at"] = card["edges"][0]["from"]["at"] = ts(1)
    ordinary = check(engine, json.dumps(card), save=True)
    assert ordinary["unverified_edges"][0]["force_eligible"]
    card["edges"][0].update(force=True, reason="Receipt is still outside this cutoff",
                           evidence=[{"source": "a.jsonl", "line": 2}])
    final = check(engine, json.dumps(card))
    assert final["unverified_edges"][0]["code"] == "invalid_force_source"
    assert not any(e["relation"] == "read" for e in final["edges"])


def test_old_index_does_not_gain_hints_on_open(tmp_path, monkeypatch):
    from migloop.inquiry import store

    with monkeypatch.context() as old:
        old.setattr(store, "literal_path_mentions", lambda *_: [])
        engine = build(tmp_path, [record(1, use("r", "Bash", command=COMMAND)), record(2, result("r", RECEIPT))])
    path = engine.store.path
    engine.store.close()
    reopened = Store(path)
    try:
        assert not reopened.rows("SELECT * FROM files")
        assert not reopened.has_records("file", XML, timestamp(ts(5)))
    finally:
        reopened.close()


@pytest.mark.parametrize("shell", ["bash", "/bin/sh", "command /bin/bash", "zsh", "pwsh"])
def test_nested_shell_does_not_assign_its_operands_to_outer_directory(tmp_path, shell):
    command = f'''cd /source && {shell} -c 'cd /other; cat "$1"' _ app/one.xml'''
    assert literal_path_mentions("Bash", {"command": command}) == []
    engine = build(tmp_path, [record(1, use("nested", "Bash", command=command))])
    try:
        assert not engine.store.rows("SELECT * FROM files")
        assert not engine.store.has_records("file", "/source/app/one.xml", timestamp(ts(5)))
        assert not engine.store.rows("SELECT * FROM effects")
        found = engine.query({"op": "search", "kind": "agent", "key": "a", "at": ts(5), "terms": ["app/one.xml"]})
        assert found["total"] == 1  # Original call remains searchable.
    finally:
        engine.store.close()
