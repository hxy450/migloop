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


@pytest.mark.parametrize("args", [{"at": ts(10), "v": 1}, {"at": ts(10), "changed": True}])
def test_temporal_blame_never_silently_ignores_old_selectors(args):
    with pytest.raises(ValueError):
        atom_queries.parameters("blame", {"path": "/p/A.ets", **args})
