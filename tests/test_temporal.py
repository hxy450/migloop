"""Temporal corpus correctness, independent of inference coverage and rendering."""
import json

import pytest

from migloop import atom_queries, atoms, atoms_collect, temporal, transcript_store


def ts(minute):
    return f"2026-09-10T10:{minute:02d}:00Z"


def source(tmp_path, rows, name="agent-ab0123456789abcdef.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) if not isinstance(row, str) else row
                              for row in rows) + "\n", encoding="utf-8")
    return str(path)


def corpus(tmp_path):
    path = source(tmp_path, [
        {"timestamp": ts(0), "type": "user", "message": {"role": "user", "content": "spec: 数值应该为42"}},
        {"timestamp": ts(5), "type": "future_type", "payload": {"unparsed": "LONGTAIL needle"}},
        {"timestamp": ts(9), "type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "r1", "name": "Read", "input": {"file_path": "/p/A.ets"}}]}},
        {"timestamp": ts(15), "type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "r1", "content": "LATE_SECRET"}]},
         "toolUseResult": {"type": "text", "file": {"filePath": "/p/A.ets", "content": "LATE_SECRET",
                            "startLine": 1, "numLines": 1, "totalLines": 1}}},
        {"type": "system", "saved": "UNDATED needle"},
        "{broken needle",
        {"timestamp": ts(16), "type": "compact", "saved_summary": "COMPACT needle"},
    ])
    agents = atoms_collect.collect_cc(path, [0])
    ledger = atoms.build_ledger(agents)
    return ledger, next(iter(agents)), path


def test_sources_exist_even_when_no_actions_are_recognized(tmp_path):
    path = source(tmp_path, [{"timestamp": ts(1), "type": "unknown_record", "unparsed": "needle"}])
    agents = atoms_collect.collect_cc(path, [0])
    ledger = atoms.build_ledger(agents)
    agent = next(iter(agents))
    assert not agents[agent].actions and agents[agent].sources == [path]
    result = temporal.query(ledger, kind="agent", key=agent, at=ts(10), q="needle")
    assert result["total"] == 1 and result["raw_scan_complete"]


def test_agent_time_searches_raw_not_only_actions(tmp_path):
    ledger, agent, _ = corpus(tmp_path)
    result = temporal.query(ledger, kind="agent", key=agent, at=ts(10), q="needle")
    assert result["total"] == 1
    assert result["rows"][0]["line"] == 2
    assert result["counts"]["undated"] == 2 and result["counts"]["malformed"] == 1
    assert not result["undated"]["rows"] and not result["causal_complete"]


def test_late_return_is_not_available_at_call_time(tmp_path):
    ledger, agent, _ = corpus(tmp_path)
    result = temporal.query(ledger, kind="agent", key=agent, at=ts(10))
    assert [r["line"] for r in result["rows"]] == [1, 2, 3]
    assert "LATE_SECRET" not in str(result)
    annotation = result["rows"][2]["annotations"][0]
    assert annotation["state"] == "pending_or_unknown" and annotation["done_ts"] is None
    assert all(r["execution"] == "unknown" and r["legacy_v"] is None for r in annotation["relations"])
    assert temporal.query(ledger, kind="agent", key=agent, at=ts(10), q="LATE_SECRET")["total"] == 0
    later = temporal.query(ledger, kind="agent", key=agent, at=ts(15), q="LATE_SECRET")
    assert later["total"] == 1
    with pytest.raises(ValueError, match="晚于"):
        temporal.record_data(ledger, later["rows"][0]["ref"], at=ts(10))


def test_unknown_time_is_quarantined_and_expansion_requires_opt_in(tmp_path):
    ledger, agent, _ = corpus(tmp_path)
    result = temporal.query(ledger, kind="agent", key=agent, at=ts(10), q="needle", include_undated=True)
    assert result["total"] == 1 and result["undated"]["total"] == 2
    ref = result["undated"]["rows"][0]["ref"]
    with pytest.raises(ValueError, match="未知"):
        temporal.record_data(ledger, ref, at=ts(10))
    assert temporal.record_data(ledger, ref, at=ts(10), include_undated=True)["time_status"] == "undated"


def test_same_timestamp_is_included_but_never_proves_order_or_edges(tmp_path):
    ledger, agent, _ = corpus(tmp_path)
    result = temporal.query(ledger, kind="agent", key=agent, at="2026-09-10T06:05:00-04:00")
    assert result["total"] == 2
    assert result["node"]["at"] == "2026-09-10T10:05:00.000000Z"
    assert result["receipt"]["navigation_is_relation"] is False


def test_pagination_never_limits_search_corpus(tmp_path):
    ledger, agent, _ = corpus(tmp_path)
    page = temporal.query(ledger, kind="agent", key=agent, at="latest", limit=1)
    assert page["total"] == 5 and page["remaining"] == 4
    hit = temporal.query(ledger, kind="agent", key=agent, at="latest", q="COMPACT", limit=1)
    assert hit["total"] == 1 and hit["rows"][0]["line"] == 7
    text = temporal.record_data(ledger, hit["rows"][0]["ref"], max_chars=5)
    assert len(text["text"]) == 5 and text["next_offset"] == 5


def test_relation_summary_keeps_target_and_expands_without_changing_corpus(tmp_path, monkeypatch):
    ledger, agent, path = corpus(tmp_path)
    import os
    path = os.path.normcase(os.path.abspath(path))
    annotation = {"agent": agent, "tool": "Bash", "state": "returned", "relations": [
        {"path": f"/p/file-{n}.ets", "kind": "write", "status": "candidate"} for n in range(100)]}
    annotation["relations"].append({"path": "/p/A.ets", "kind": "read", "status": "confirmed"})
    monkeypatch.setattr(temporal, "_annotations", lambda *_: {(path, 3): [annotation]})
    small = temporal.query(ledger, kind="file", key="/p/A.ets", at=ts(15))
    full = temporal.query(ledger, kind="file", key="/p/A.ets", at=ts(15), details=True)
    assert small["total"] == full["total"]
    assert [r["ref"] for r in small["rows"]] == [r["ref"] for r in full["rows"]]
    shown = next(r["annotations"][0] for r in small["rows"] if r["annotations"])
    assert [r["path"] for r in shown["relations"]] == ["/p/A.ets"]
    assert shown["relations_omitted"] == 100
    assert len(next(r["annotations"][0] for r in full["rows"] if r["annotations"])["relations"]) == 101
    # The search can still match an undisplayed path in the original corpus;
    # annotations are not a replacement corpus or an admission filter.
    assert temporal.query(ledger, kind="file", key="/p/A.ets", at=ts(15), q="LATE_SECRET")["total"] == 1


def test_agent_annotation_fold_has_count_and_full_expansion():
    annotations = [{"relations": [{"path": str(n)} for n in range(25)]} for _ in range(9)]
    shown, hidden = temporal._annotation_view(annotations, "agent", "a", False)
    assert len(shown) == 4 and hidden == 5
    assert all(len(a["relations"]) == 6 and a["relations_omitted"] == 19 for a in shown)
    expanded, hidden = temporal._annotation_view(annotations, "agent", "a", True)
    assert expanded == annotations and hidden == 0


def test_raw_ids_survive_parser_upgrade_and_append_but_not_content_change(tmp_path):
    ledger, agent, path = corpus(tmp_path)
    before = temporal.query(ledger, kind="agent", key=agent, q="LONGTAIL")["rows"][0]["ref"]
    ledger.agents[agent].actions.clear()  # Collector capability is not identity.
    from pathlib import Path
    p = Path(path)
    saved = p.read_text(encoding="utf-8")
    p.write_text(saved + json.dumps({"timestamp": ts(17), "message": "new"}) + "\n", encoding="utf-8")
    assert temporal.query(ledger, kind="agent", key=agent, q="LONGTAIL")["rows"][0]["ref"] == before
    p.write_text(saved.replace("LONGTAIL", "REPLACED"), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        temporal.record_data(ledger, before)


def test_duplicate_source_names_fail_closed(tmp_path):
    ledger, agent, path = corpus(tmp_path)
    ref = temporal.query(ledger, kind="agent", key=agent)["rows"][0]["ref"]
    other = tmp_path / "other"
    other.mkdir()
    same_name = source(other, [{"timestamp": ts(1), "text": "different"}])
    ledger.agents["second"] = atoms.AgentRec(id="second", session="s", sources=[same_name])
    with pytest.raises(ValueError, match="ambiguous"):
        transcript_store.resolve(ledger, ref)


def test_file_includes_unparsed_candidate_between_versions(tmp_path):
    ledger, agent, path = corpus(tmp_path)
    from pathlib import Path
    p = Path(path)
    p.write_text(p.read_text(encoding="utf-8") + json.dumps({"timestamp": ts(8), "type": "custom",
                 "command": "opaque-script A.ets"}) + "\n", encoding="utf-8")
    result = temporal.query(ledger, kind="file", key="/p/A.ets", at=ts(10))
    assert {r["line"] for r in result["rows"]} == {3, 8}
    opaque = next(r for r in result["rows"] if r["line"] == 8)
    assert opaque["annotations"] == []  # Lexical lookup did not invent RW.
    assert not result["causal_complete"]


def test_shared_time_json_and_text_selection(tmp_path):
    ledger, agent, _ = corpus(tmp_path)
    args = {"id": agent, "at": ts(10), "limit": 2}
    data = atom_queries.json_data(ledger, "agent", args)
    from migloop import time_receipts
    text = atom_queries.render_text(ledger, "/p", "agent", args)
    assert text.split(time_receipts.MARKER)[0] == temporal.render(data)
    assert time_receipts.parse(ledger, "agent", args, text)["node"] == data["node"]
    args = {"file": "/p/A.ets", "at": ts(10), "q": "file_path"}
    assert atom_queries.json_data(ledger, "search", args)["total"] == 1


@pytest.mark.parametrize("args", [{"at": ts(10), "v": 1}, {"at": ts(10), "until": 3},
                                  {"at": "2026-09-10T10:00:00"}, {"at": ts(1), "since_ts": ts(2)}])
def test_time_and_legacy_windows_never_mix(args):
    with pytest.raises(ValueError):
        atom_queries.parameters("agent", {"id": "a", **args})


def test_missing_source_is_visible_gap(tmp_path):
    ledger = atoms.Ledger({}, {"a": atoms.AgentRec("a", "s", sources=[str(tmp_path / "gone.jsonl")])})
    result = temporal.query(ledger, kind="agent", key="a", at=ts(10))
    assert result["gaps"] and not result["raw_scan_complete"]


def test_codex_source_keeps_unclassified_and_non_object_records(tmp_path):
    path = source(tmp_path, [{"timestamp": ts(1), "type": "session_meta", "payload": {"id": "abcd"}},
                            {"timestamp": ts(2), "type": "custom_runtime", "payload": "unknown needle"},
                            ["saved array needle"]])
    rec = atoms_collect._walk_codex(path, "a", "s", [0], {}, set())
    led = atoms.build_ledger({"a": rec})
    result = temporal.query(led, kind="agent", key="a", at=ts(3), q="needle", include_undated=True)
    assert result["total"] == 1 and result["undated"]["total"] == 1


def test_legacy_search_preserves_uncertain_read_binding(tmp_path):
    from migloop import atoms_text
    ledger, agent, _ = corpus(tmp_path)
    ref = next(r for a in ledger.agents[agent].actions for r in a.files if r.op == "read")
    ref.certain = False
    results = atoms.search_agent(ledger, agent, "LATE_SECRET", until_ts=ts(20))
    hit = next(h for h in results["hits"] if h.get("target"))
    assert hit["target_certain"] == ref.certain and hit["target_proof"]
    assert "看这一版是谁写的" not in atoms_text._next_hint(hit, "/p")


def test_stale_raw_sources_disable_inferred_annotations(tmp_path):
    from pathlib import Path
    ledger, agent, path = corpus(tmp_path)
    p = Path(path)
    p.write_text(p.read_text(encoding="utf-8").replace("LATE_SECRET", "DIFFERENT_BODY"), encoding="utf-8")
    result = temporal.query(ledger, kind="agent", key=agent)
    assert result["stale_annotation_sources"]
    assert all(not row["annotations"] for row in result["rows"])


def test_ambiguous_file_is_not_resolved_by_largest_history(tmp_path):
    from migloop.filestory import FileStory
    ledger, _, _ = corpus(tmp_path)
    ledger.stories["/another/A.ets"] = FileStory("/another/A.ets")
    with pytest.raises(ValueError, match="歧义"):
        temporal.query(ledger, kind="file", key="A.ets")
    assert temporal.query(ledger, kind="file", key="/p/A.ets")["node"]["key"] == "/p/A.ets"
    assert temporal.query(ledger, kind="file", key="unknown.ets")["node"]["identity_status"] == "unresolved_lexical_scope"
