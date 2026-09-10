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
