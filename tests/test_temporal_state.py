import pytest

from migloop import atom_queries, atoms, temporal_state
from migloop.evidence import FileProof
from migloop.filestory import Ev
from tests.test_temporal import ts

PROOF = FileProof("native_tool", "confirmed", "content", "full")


def call(seq, minute, end, kind, **kw):
    ev = Ev(ts(minute), seq * 10, kind, "/p/A.ets", "a", proof=PROOF, **kw)
    op = "read" if kind == "read" else "write"
    return atoms.Action(ts(minute), seq, "Read" if op == "read" else "Write", op,
                        done_ts=ts(end) if end is not None else None,
                        files=[atoms.FileRef(op, "/p/A.ets", ev)])


def ledger(actions):
    return atoms.build_ledger({"a": atoms.AgentRec("a", "s", actions=actions)})


def test_later_snapshot_cannot_close_earlier_time_query():
    led = ledger([call(1, 0, 1, "wopaque"), call(2, 15, 16, "read", content="LATE\n", full=True)])
    # Old final ledger has sealed the write. As-of replay must not reuse it.
    assert led.stories["/p/A.ets"].versions[0].content == "LATE\n"
    earlier = temporal_state.query(led, "blame", "/p/A.ets", ts(10))
    assert not earlier["known"] and not earlier["rows"] and "LATE" not in str(earlier)
    later = temporal_state.query(led, "blame", "/p/A.ets", ts(20))
    assert later["known"] and later["rows"][0]["agent"] is None
    interval = temporal_state.query(led, "diff", "/p/A.ets", ts(20), since_ts=ts(10))
    assert interval["total"] == 1
    assert interval["rows"][0]["ts"] == "2026-09-10T10:16:00.000000Z"
    assert interval["rows"][0]["agent"] is None
    assert interval["rows"][0]["event_id"] is None


def test_candidate_between_versions_invalidates_state_at_read_cutoff():
    acts = [call(1, 0, 1, "wfull", content="before\n", created=True),
            atoms.Action(ts(5), 2, "Bash", "other", done_ts=ts(6),
                         detail={"touched": ["/p/A.ets"]}),
            call(3, 20, 21, "wfull", content="after\n")]
    led = ledger(acts)
    assert temporal_state.query(led, "blame", "/p/A.ets", ts(4))["known"]
    middle = temporal_state.query(led, "blame", "/p/A.ets", ts(10))
    assert not middle["known"] and not middle["rows"]


def test_pending_write_is_barrier_not_success():
    led = ledger([call(1, 0, 1, "wfull", content="before\n", created=True),
                  call(2, 5, 15, "wfull", content="FUTURE\n")])
    middle = temporal_state.query(led, "blame", "/p/A.ets", ts(10))
    assert not middle["known"] and "FUTURE" not in str(middle)
    after = temporal_state.query(led, "blame", "/p/A.ets", ts(20))
    assert after["known"]


def test_native_edits_keep_diff_and_time_based_text_origin():
    led = ledger([call(1, 0, 1, "wfull", content="a\nb\n", created=True),
                  call(2, 5, 6, "edit", old="b", new="c")])
    diff = atom_queries.json_data(led, "diff", {"path": "/p/A.ets", "at": ts(10), "since_ts": ts(4)})
    assert diff["total"] == 1 and "-b" in diff["rows"][0]["diff"] and "+c" in diff["rows"][0]["diff"]
    blame = atom_queries.json_data(led, "blame", {"path": "/p/A.ets", "at": ts(10)})
    assert blame["known"] and [r["agent"] for r in blame["rows"]] == ["a", "a"]
    assert [r["introduced_at"] for r in blame["rows"]] == ["2026-09-10T10:01:00.000000Z", "2026-09-10T10:06:00.000000Z"]


def test_overlapping_or_equal_time_writes_do_not_invent_last_writer():
    for end in (6, 10):
        led = ledger([call(1, 0, end, "wfull", content="one\n", created=True),
                      call(2, 5, 10, "wfull", content="two\n")])
        assert not temporal_state.query(led, "blame", "/p/A.ets", ts(12))["known"]


def test_first_observed_overwrite_is_not_origin_proof():
    led = ledger([call(1, 0, 1, "wfull", content="preexisting_code\n")])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(10))
    assert got["known"] and got["rows"][0]["agent"] is None


@pytest.mark.parametrize("field", ["conditional", "effect_candidates", "touched"])
def test_undated_possible_write_is_not_lost_before_candidate_collection(field):
    led = ledger([call(1, 0, 1, "wfull", content="before\n", created=True),
                  atoms.Action("", 2, "Bash", "other", detail={field: ["/p/A.ets"]})])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(10))
    assert not got["known"] and not got["rows"]
    assert any("/p/A.ets" in gap["paths"] for gap in got["gaps"])


@pytest.mark.parametrize("args", [{"at": ts(10), "v": 1}, {"at": ts(10), "changed": True}])
def test_temporal_blame_never_silently_ignores_old_selectors(args):
    with pytest.raises(ValueError):
        atom_queries.parameters("blame", {"path": "/p/A.ets", **args})


def native_patch(minute=5, *, success=True, path="/proj/A.ets"):
    return {"timestamp": ts(minute) if minute is not None else None, "type": "event_msg", "payload": {
        "type": "patch_apply_end", "call_id": "independent", "success": success,
        "changes": {path: {"type": "update", "unified_diff": "@@ -1 +1 @@\n-old\n+new\n"}}}}


def source_ledger(tmp_path, *, success=True, recovery=False, undated=False):
    from tests.test_atoms import _call, _ledger, _read_call
    rows = _call(ts(0), "initial", "Write", {"file_path": "/proj/A.ets", "content": "old\n"},
                 out="File created successfully at: /proj/A.ets")
    rows.append(native_patch(None if undated else 5, success=success))
    if recovery:
        rows.extend(_read_call(ts(15), "observe", "/proj/A.ets", "new\n"))
    return _ledger(tmp_path, rows)


@pytest.mark.parametrize("success", [True, False])
def test_unparsed_native_patch_is_observation_time_barrier_not_old_known_state(tmp_path, success):
    led = source_ledger(tmp_path, success=success)
    before = temporal_state.query(led, "blame", "/proj/A.ets", ts(4))
    assert before["known"] and before["rows"][0]["text"] == "old"
    assert before["native_effect_barriers"] == []
    after = temporal_state.query(led, "blame", "/proj/A.ets", ts(10))
    assert not after["known"] and after["rows"] == []
    barrier, = after["native_effect_barriers"]
    assert barrier["use_ts"] is None and barrier["agent"] is None and barrier["changed_time_unknown"]
    assert barrier["observation_ts"].startswith(ts(5)[:-1])
    assert barrier["status"] == ("confirmed_change" if success else "candidate_effect")


def test_later_reliable_read_recovers_observed_content_but_not_patch_author(tmp_path):
    led = source_ledger(tmp_path, recovery=True)
    middle = temporal_state.query(led, "blame", "/proj/A.ets", ts(10))
    assert not middle["known"] and "new" not in str(middle["rows"])
    after = temporal_state.query(led, "blame", "/proj/A.ets", ts(20))
    assert after["known"] and after["rows"][0]["text"] == "new"
    assert after["rows"][0]["agent"] is None and after["rows"][0]["introduced_at"] is None
    assert after["rows"][0]["status"] == "unknown_origin"
    assert after["rows"][0]["event_id"] is None


def test_undated_native_effect_is_path_scoped_unknown_not_keyerror(tmp_path):
    led = source_ledger(tmp_path, undated=True)
    got = temporal_state.query(led, "blame", "/proj/A.ets", ts(10))
    assert not got["known"] and got["rows"] == []
    assert any(g.get("reason") == "undated_native_effect" and g["paths"] == ["/proj/A.ets"] for g in got["gaps"])


def test_registered_missing_source_gap_is_global_but_sourceless_fixture_stays_known(tmp_path):
    led = source_ledger(tmp_path)
    led.agents["missing"] = atoms.AgentRec("missing", "s", sources=[str(tmp_path / "unavailable.jsonl")])
    got = temporal_state.query(led, "blame", "/proj/A.ets", ts(4))
    assert not got["known"]
    assert any(g.get("scope") == "pool" and g.get("paths") == [] for g in got["gaps"])
    synthetic = ledger([call(1, 0, 1, "wfull", content="known\n", created=True)])
    assert temporal_state.query(synthetic, "blame", "/p/A.ets", ts(10))["known"]


def test_pool_native_effects_are_read_once_per_replay(tmp_path, monkeypatch):
    led = source_ledger(tmp_path)
    original = temporal_state.change_inventory.native_effects
    calls = []
    def native(*args):
        calls.append(args[1])
        return original(*args)
    monkeypatch.setattr(temporal_state.change_inventory, "native_effects", native)
    temporal_state.replay(led, ts(10))
    assert len(calls) == 1 and calls[0]["kind"] == "pool"


def test_action_covered_native_patch_is_not_a_duplicate_unknown_barrier(tmp_path):
    led = source_ledger(tmp_path)
    owner = next(iter(led.agents.values()))
    source = owner.sources[0]
    action = atoms.Action(ts(5), 100, "apply_patch", "write", done_ts=ts(5),
                          src=(source, 2, 2), tuid="independent",
                          files=[atoms.FileRef("write", "/proj/A.ets", Ev(ts(5), 100, "edit", "/proj/A.ets",
                              owner.id, old="old", new="new", proof=PROOF))])
    owner.actions.append(action)
    led = atoms.build_ledger(led.agents)
    got = temporal_state.query(led, "blame", "/proj/A.ets", ts(10))
    assert got["known"] and got["rows"][0]["text"] == "new"
    assert got["native_effect_barriers"] == []


def test_action_candidate_covered_native_patch_still_invalidates_state(tmp_path):
    led = source_ledger(tmp_path)
    owner = next(iter(led.agents.values()))
    source = owner.sources[0]
    owner.actions.append(atoms.Action(ts(5), 100, "apply_patch", "write", done_ts=ts(5),
        src=(source, 2, 2), ok=False, files=[atoms.FileRef("write", "/proj/A.ets",
            Ev(ts(5), 100, "edit", "/proj/A.ets", owner.id, old="old", new="new", proof=PROOF))]))
    led = atoms.build_ledger(led.agents)
    got = temporal_state.query(led, "blame", "/proj/A.ets", ts(10))
    assert not got["known"] and not got["rows"]
    assert got["native_effect_barriers"] == []  # The parsed candidate already owns the barrier.


def test_read_overlapping_native_observation_cannot_restore_state(tmp_path):
    from tests.test_atoms import _call, _ledger, _read_call
    reading = _read_call(ts(4), "overlap", "/proj/A.ets", "new\n")
    reading[1]["timestamp"] = ts(6)
    led = _ledger(tmp_path, [*_call(ts(0), "initial", "Write",
        {"file_path": "/proj/A.ets", "content": "old\n"}, out="File created successfully at: /proj/A.ets"),
        reading[0], native_patch(), reading[1]])
    got = temporal_state.query(led, "blame", "/proj/A.ets", ts(10))
    assert not got["known"] and not got["rows"]


def opaque(seq=2, start=5, end=6, *, tool="Bash", signal="unsupported_execution", ok=True):
    return atoms.Action(ts(start) if start is not None else "", seq, tool, "other", ok=ok,
                        done_ts=ts(end) if end is not None else None,
                        detail={signal: ["execution domain not reconstructed"]})


@pytest.mark.parametrize("signal", ["unresolved", "unknown_scripts", "unsupported_execution"])
@pytest.mark.parametrize("tool", ["Bash", "PowerShell", "exec", "exec_command"])
def test_opaque_execution_without_target_invalidates_old_content(signal, tool):
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(tool=tool, signal=signal)])
    before = temporal_state.query(led, "blame", "/p/A.ets", ts(4))
    assert before["known"] and before["unclassified_execution_windows"] == []
    after = temporal_state.query(led, "blame", "/p/A.ets", ts(10))
    assert not after["known"] and after["rows"] == []
    assert after["current_state_certified"] is False
    window, = after["unclassified_execution_windows"]
    assert window["scope"] == "pool" and window["agent"] is None
    assert window["author_status"] == "unknown" and window["effect_status"] == "unclassified"
    assert window["use_ts"].startswith(ts(5)[:-1]) and window["done_ts"].startswith(ts(6)[:-1])
    diff = temporal_state.query(led, "diff", "/p/A.ets", ts(10), since_ts=ts(4))
    assert diff["rows"] == []  # Uncertainty is not a newly invented modification.


@pytest.mark.parametrize("tool", ["Read", "Grep", "Glob", "Agent", "inbox"])
def test_non_shell_signals_and_pure_lexical_mentions_do_not_create_pool_barriers(tool):
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(tool=tool),
                  atoms.Action(ts(7), 3, "Bash", "other", done_ts=ts(8),
                               detail={"cmd": "echo /p/A.ets", "mentions": ["/p/A.ets"]})])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(10))
    assert got["known"] and got["unclassified_execution_windows"] == []
    assert got["current_state_certified"] is False


@pytest.mark.parametrize("content", ["old\n", "observed\n"])
def test_full_read_after_opaque_window_recovers_content_not_old_author(content):
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(),
                  call(3, 10, 11, "read", content=content, full=True)])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(12))
    assert got["known"] and got["rows"][0]["text"] == content.strip()
    assert got["rows"][0]["agent"] is None and got["rows"][0]["introduced_at"] is None
    assert got["snapshot_at"].startswith(ts(11)[:-1])
    assert got["unclassified_execution_windows"]  # Recovery does not erase audit history.


def test_full_write_after_opaque_window_recovers_content_without_old_origin():
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(),
                  call(3, 10, 11, "wfull", content="old\n")])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(12))
    assert got["known"] and got["rows"][0]["text"] == "old"
    assert got["rows"][0]["introduced_at"] != "2026-09-10T10:01:00.000000Z"
    assert got["snapshot_at"].startswith(ts(11)[:-1])


@pytest.mark.parametrize("start,end,opaque_end,at", [(10, 11, 20, 12), (10, 11, 20, 25), (4, 7, 6, 12)])
def test_full_write_overlapping_unknown_execution_is_not_recovery(start, end, opaque_end, at):
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(end=opaque_end),
                  call(3, start, end, "wfull", content="racy\n")])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(at))
    assert not got["known"] and not got["rows"]


@pytest.mark.parametrize("read_start,expected", [(6, False), (7, True)])
def test_failed_unknown_window_can_recover_only_after_its_end(read_start, expected):
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(ok=False),
                  call(3, read_start, read_start + 1, "read", content="fresh\n", full=True)])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(12))
    assert got["known"] is expected
    assert got["unclassified_execution_windows"][0]["status"] == "failed_or_unknown"


def test_new_edit_after_observed_recovery_does_not_restore_old_line_authors():
    led = ledger([call(1, 0, 1, "wfull", content="keep\nreplace\n", created=True), opaque(),
                  call(3, 10, 11, "read", content="keep\nreplace\n", full=True),
                  call(4, 13, 14, "edit", old="replace", new="new")])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(15))
    assert got["known"] and got["rows"][0]["agent"] is None
    assert got["rows"][1]["introduced_at"].startswith(ts(14)[:-1])


@pytest.mark.parametrize("end,at,ok", [(None, 12, None), (20, 12, True), (20, 25, True), (20, 25, False)])
def test_read_inside_pending_failed_or_completed_opaque_window_cannot_restore(end, at, ok):
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(end=end, ok=ok),
                  call(3, 10, 11, "read", content="racy\n", full=True)])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(at))
    assert not got["known"] and got["rows"] == []
    if end is None or end > at:
        assert got["unclassified_execution_windows"][0]["done_ts"] is None


@pytest.mark.parametrize("mode", ["partial", "failed", "conditional", "observation_uncertain"])
def test_unreliable_read_after_opaque_window_does_not_restore(mode):
    reading = call(3, 10, 11, "read", content="racy\n", full=mode != "partial", conditional=mode == "conditional")
    if mode == "failed": reading.ok = False
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(), reading])
    if mode == "observation_uncertain": reading.files[0].observation_uncertain = True
    assert not temporal_state.query(led, "blame", "/p/A.ets", ts(12))["known"]


def test_undated_opaque_execution_is_gap_not_a_fabricated_time():
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(start=None),
                  call(3, 10, 11, "read", content="new\n", full=True)])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(12))
    assert not got["known"]
    window, = got["unclassified_execution_windows"]
    assert window["use_ts"] is None and window["time_status"] == "unknown"


def dependency_action(seq, start, end, path, kind, **kwargs):
    event = Ev(ts(start), seq * 10, kind, path, "a", proof=PROOF, **kwargs)
    return atoms.Action(ts(start), seq, "Write", "write", done_ts=ts(end),
                        files=[atoms.FileRef("write", path, event)])


@pytest.mark.parametrize("kind", ["wderived", "wconcat"])
def test_target_projection_includes_source_dependency_closure(kind):
    led = ledger([dependency_action(1, 0, 1, "/p/C.ets", "wfull", content="stale\n", created=True),
                  dependency_action(2, 2, 3, "/p/B.ets", "wderived", src="/p/C.ets"),
                  opaque(seq=3),
                  dependency_action(4, 8, 9, "/p/A.ets", kind,
                                    **({"src": "/p/B.ets"} if kind == "wderived" else {"sources": ("/p/B.ets", "/p/C.ets")})),
                  dependency_action(5, 0, 1, "/unrelated/Z.ets", "wfull", content="unrelated\n", created=True)])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(12))
    assert not got["known"] and got["rows"] == []
    stories, _, _ = temporal_state.replay(led, ts(12), path="/p/A.ets")
    assert set(stories) == {"/p/A.ets", "/p/B.ets", "/p/C.ets"}


def test_dependency_fresh_full_source_recovers_copy_after_opaque_window():
    led = ledger([dependency_action(1, 0, 1, "/p/B.ets", "wfull", content="stale\n", created=True),
                  opaque(), dependency_action(3, 7, 8, "/p/B.ets", "wfull", content="fresh\n"),
                  dependency_action(4, 10, 11, "/p/A.ets", "wderived", src="/p/B.ets")])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(12))
    assert got["known"] and got["rows"][0]["text"] == "fresh"


def test_unrelated_candidate_does_not_replace_requested_projection_path():
    led = ledger([call(1, 0, 1, "wfull", content="target\n", created=True),
                  dependency_action(2, 0, 1, "/other/B.ets", "wfull", content="other\n", created=True),
                  atoms.Action(ts(5), 3, "Bash", "other", done_ts=ts(6),
                               detail={"touched": ["/other/B.ets"]})])
    got = temporal_state.query(led, "blame", "/p/A.ets", ts(12))
    assert got["known"] and got["rows"][0]["text"] == "target"
    stories, _, _ = temporal_state.replay(led, ts(12), path="/p/A.ets")
    assert set(stories) == {"/p/A.ets"}


def test_real_collector_dynamic_script_signal_invalidates_old_state_without_reexecution(tmp_path):
    from tests.test_atoms import _call, _ledger
    command = 'python -c "from pathlib import Path; [p.write_text(\'new\') for p in Path(\'/proj\').glob(\'*.ets\')]"'
    led = _ledger(tmp_path, [*_call(ts(0), "initial", "Write", {"file_path": "/proj/A.ets", "content": "old\n"}),
                            *_call(ts(5), "opaque", "Bash", {"command": command}, out="/proj/A.ets")])
    got = temporal_state.query(led, "blame", "/proj/A.ets", ts(12))
    assert not got["known"] and got["unclassified_execution_windows"]


@pytest.mark.parametrize("success", [True, False])
def test_independent_native_patch_diff_survives_without_outer_parsed_write(tmp_path, success):
    led = source_ledger(tmp_path, success=success)
    got = temporal_state.query(led, "diff", "/proj/A.ets", ts(10), since_ts=ts(4), max_chars=12)
    row, = got["rows"]
    assert row["basis"] == "native_effect_observation" and row["agent"] is None
    assert row["effect_ts"] is None and row["ts"].startswith(ts(5)[:-1])
    assert row["effect_status"] == ("confirmed_change" if success else "candidate_effect")
    assert row["truncated"] and len(row["diff"]) == 12
    assert row["ref"].startswith("raw:") and not got["known"]
    assert temporal_state.query(led, "diff", "/proj/A.ets", ts(4))["total"] == 1  # Initial Write only.
    assert temporal_state.query(led, "diff", "/proj/A.ets", ts(10), since_ts=ts(6))["total"] == 0


def test_source_dependency_cycle_has_finite_projection():
    led = ledger([dependency_action(1, 0, 1, "/p/B.ets", "wfull", content="old\n", created=True),
                  dependency_action(2, 2, 3, "/p/A.ets", "wderived", src="/p/B.ets"),
                  dependency_action(3, 4, 5, "/p/B.ets", "wderived", src="/p/A.ets"), opaque(seq=4, start=6, end=7)])
    stories, _, _ = temporal_state.replay(led, ts(12), path="/p/A.ets")
    assert set(stories) == {"/p/A.ets", "/p/B.ets"}
    assert not temporal_state.query(led, "blame", "/p/A.ets", ts(12))["known"]


def test_execution_window_pagination_is_recent_bounded_and_independent_of_rows():
    actions = [call(1, 0, 1, "wfull", content="old\n", created=True)]
    actions.extend(opaque(seq=number + 2, start=number + 2, end=number + 3) for number in range(9))
    actions.append(call(20, 20, 21, "read", content="old\n", full=True))
    led = ledger(actions)
    first = temporal_state.query(led, "blame", "/p/A.ets", ts(25), offset=0, limit=1)
    page = first["unclassified_execution_window_page"]
    assert page["total"] == 9 and page["limit"] == 4 and page["omitted"] == 5 and page["next_offset"] == 4
    assert [w["use_ts"] for w in first["unclassified_execution_windows"]] == [
        "2026-09-10T10:" + str(m).zfill(2) + ":00.000000Z" for m in range(7, 11)]
    next_query = page["next_query"]
    assert next_query["tool"] == "blame" and "since_ts" not in next_query["args"]
    assert next_query["args"]["at"] == ts(25) and next_query["args"]["offset"] == 0
    second = temporal_state.query(led, next_query["tool"], **next_query["args"])
    assert second["rows"] == first["rows"] and second["known"] is True
    assert second["rows"][0]["agent"] is None
    assert [w["use_ts"] for w in second["unclassified_execution_windows"]] == [
        "2026-09-10T10:" + str(m).zfill(2) + ":00.000000Z" for m in range(3, 7)]
    empty = temporal_state.query(led, "blame", "/p/A.ets", ts(25), window_offset=99)
    assert empty["unclassified_execution_windows"] == [] and empty["known"] is True
    assert empty["rows"][0]["agent"] is None  # Omitted windows still block old origins.


def test_diff_window_continuation_preserves_time_and_does_not_filter_internal_windows():
    led = ledger([call(1, 0, 1, "wfull", content="old\n", created=True), opaque(),
                  opaque(seq=3, start=7, end=8)])
    got = temporal_state.query(led, "diff", "/p/A.ets", ts(12), since_ts=ts(9), window_limit=1, offset=3)
    next_query = got["unclassified_execution_window_page"]["next_query"]
    assert next_query["args"]["since_ts"] == ts(9) and next_query["args"]["at"] == ts(12)
    assert next_query["args"]["offset"] == 3 and next_query["args"]["window_offset"] == 1
    assert not got["known"]  # State-affecting pre-since windows were not dropped.


@pytest.mark.parametrize("kwargs", [{"window_offset": -1}, {"window_offset": True},
                                    {"window_limit": 0}, {"window_limit": 201}])
def test_execution_window_pagination_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        temporal_state.query(ledger([]), "blame", "/p/A.ets", ts(10), **kwargs)
