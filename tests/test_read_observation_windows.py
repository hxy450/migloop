"""Read completion makes input available, but does not timestamp the file snapshot."""
from __future__ import annotations

from pathlib import Path

import pytest

from migloop import atoms, atoms_collect, filestory
from tests.test_atoms import CROOT, _call, _cexec, _crec, _ledger, _rec, _res, _use, _write_jsonl

PATH = "/proj/A.ets"


def at(second: int) -> str:
    return f"2026-01-01T00:00:{second:02d}Z"


def collected(tmp_path: Path, backend: str, *, partial: bool = False, read_start: int = 5,
              candidate: bool = False) -> atoms.Ledger:
    old, new = "old\nsuffix\n", "new\nsuffix\n"
    if backend == "cc":
        records = [*_call(at(0), "initial", "Write", {"file_path": PATH, "content": old}),
                   _rec(at(read_start), "assistant", [_use("read", "Read", {"file_path": PATH})]),
                   _rec(at(20), "user", [_res("read", "old" if partial else old)],
                        toolUseResult={"type": "text", "file": {"filePath": PATH,
                            "content": "old\n" if partial else old, "startLine": 1,
                            "numLines": 1 if partial else 2, "totalLines": 2}})]
        records += (_call(at(10), "write", "Bash", {"command": f"false && printf 'maybe\\n' > {PATH}; true"}, out="")
                    if candidate else _call(at(10), "write", "Write", {"file_path": PATH, "content": new}))
        return _ledger(tmp_path, sorted(records, key=lambda r: r["timestamp"]))
    records = [_crec(at(0), "session_meta", {"id": CROOT, "session_id": CROOT, "cwd": "/proj", "source": "cli"})]
    calls = [(0, 1, "initial", f"cat > {PATH} <<'EOF'\n{old}EOF", ""),
             (read_start, 20, "read", f"head -n 1 {PATH}" if partial else f"cat {PATH}", "old\n" if partial else old),
             (10, 11, "write", f"false && printf 'maybe\\n' > {PATH}; true" if candidate else f"cat > {PATH} <<'EOF'\n{new}EOF", "")]
    import json
    for use, done, cid, command, output in calls:
        js = "const r=await tools.exec_command(" + json.dumps({"cmd": command, "workdir": "/proj"}) + ");text(JSON.stringify(r));"
        pair = _cexec(at(use), cid, js, output)
        pair[1]["timestamp"] = at(done)
        records.extend(pair)
    root = tmp_path / f"rollout-{CROOT}.jsonl"
    _write_jsonl(str(root), sorted(records, key=lambda r: r["timestamp"]))
    return atoms.build_ledger(atoms_collect.collect_codex(str(root), seq=[0], sessions_root=str(tmp_path)))


@pytest.mark.parametrize("backend", ["cc", "codex"])
@pytest.mark.parametrize("partial", [False, True])
def test_read_started_before_write_does_not_reanchor_at_result_time(tmp_path: Path, backend: str, partial: bool) -> None:
    ledger = collected(tmp_path, backend, partial=partial)
    story = ledger.stories[PATH]
    assert [v.content for v in story.versions] == ["old\nsuffix\n", "new\nsuffix\n"]
    assert not story.breaks
    assert story.reads[-1].certain is False
    assert story.reads[-1].observation_uncertain is True and story.reads[-1].use_ts == at(5)
    read = next(action for agent in ledger.agents.values() for action in agent.actions if action.tuid == "read")
    assert read.done_ts == at(20) and read.at == 3  # Input still cannot feed the concurrent write v2.
    assert read.files[0].ev.ts == read.files[0].ev.done_ts == at(20)
    assert read.files[0].ev.use_ts == at(5)
    writes = [ref.ev for agent in ledger.agents.values() for action in agent.actions
              for ref in action.files if ref.op == "write"]
    assert [(ev.ts, ev.use_ts, ev.done_ts) for ev in writes] == [(at(0), at(0), at(1)), (at(10), at(10), at(11))]


@pytest.mark.parametrize("backend", ["cc", "codex"])
def test_read_really_started_after_write_can_reanchor(tmp_path: Path, backend: str) -> None:
    ledger = collected(tmp_path, backend, read_start=15)
    story = ledger.stories[PATH]
    assert story.versions[-1].source == "outband" and story.versions[-1].content == "old\nsuffix\n"
    assert story.reads[-1].certain is True
    assert story.reads[-1].observation_uncertain is False


@pytest.mark.parametrize("backend", ["cc", "codex"])
def test_candidate_write_overlapping_read_does_not_seal_old_snapshot(tmp_path: Path, backend: str) -> None:
    ledger = collected(tmp_path, backend, candidate=True)
    story = ledger.stories[PATH]
    assert len(story.versions) == 1 and story.versions[0].content == "old\nsuffix\n"
    assert story.reads[-1].certain is False
    assert story.touches


def event(second: int, seq: int, kind: str, *, path: str = PATH, **fields: object) -> filestory.Ev:
    return filestory.Ev(at(second), seq, kind, path, "agent-a", **fields)


def initial() -> filestory.Ev:
    return event(0, 1, "wfull", content="old\n", use_ts=at(0), done_ts=at(1))


@pytest.mark.parametrize("kind", ["wfull", "wopaque", "delete", "candidate"])
def test_effect_started_before_read_and_completed_after_read_is_still_overlap(kind: str) -> None:
    effect = event(3, 2, kind, content="new\n" if kind == "wfull" else None, use_ts=at(3), done_ts=at(30))
    read = event(20, 3, "read", content="old\n", full=True, use_ts=at(5), done_ts=at(20))
    story = filestory.build_stories([initial(), effect, read])[PATH]
    assert len(story.versions) == (1 if kind == "candidate" else 2)
    assert not story.breaks
    assert not story.reads[-1].certain and story.reads[-1].observation_uncertain
    if kind == "wopaque":
        assert story.versions[-1].content is None and not story.versions[-1].sealed


def test_old_candidate_endpoint_pair_is_one_continuous_uncertainty_window() -> None:
    events = [initial(), event(3, 2, "candidate"), event(30, 2, "candidate"),
              event(20, 3, "read", content="old\n", full=True, use_ts=at(5), done_ts=at(20))]
    story = filestory.build_stories(events)[PATH]
    assert len(story.versions) == 1
    assert not story.reads[0].certain and story.reads[0].observation_uncertain


def test_even_matching_full_snapshot_does_not_prove_observation_time() -> None:
    story = filestory.build_stories([initial(), event(10, 2, "wfull", content="new\n", use_ts=at(10), done_ts=at(11)),
        event(20, 3, "read", content="new\n", full=True, use_ts=at(5), done_ts=at(20))])[PATH]
    assert story.versions[-1].content == "new\n" and len(story.versions) == 2
    assert not story.reads[0].certain and story.reads[0].full and story.reads[0].observation_uncertain


def test_partial_read_preserves_seen_lines_but_not_exact_version_certainty() -> None:
    seen = ((1, "old"),)
    story = filestory.build_stories([initial(), event(10, 2, "wfull", content="new\n"),
        event(20, 3, "read", start=1, n=1, seen=seen, use_ts=at(5), done_ts=at(20))])[PATH]
    read = story.reads[0]
    assert (read.start, read.n, read.seen, read.full) == (1, 1, seen, False)
    assert not read.certain and read.observation_uncertain


def test_later_nonoverlapping_snapshot_can_seal_opaque_state() -> None:
    story = filestory.build_stories([initial(), event(10, 2, "wopaque", use_ts=at(10), done_ts=at(11)),
        event(20, 3, "read", content="old\n", full=True, use_ts=at(5), done_ts=at(20)),
        event(26, 4, "read", content="actual-after\n", full=True, use_ts=at(25), done_ts=at(26))])[PATH]
    assert len(story.versions) == 2 and story.versions[-1].content == "actual-after\n"
    assert story.versions[-1].sealed
    assert [(r.certain, r.observation_uncertain) for r in story.reads] == [(False, True), (True, False)]


def test_nonoverlapping_candidate_does_not_permanently_prevent_reanchoring() -> None:
    story = filestory.build_stories([initial(), event(3, 2, "candidate", use_ts=at(3), done_ts=at(4)),
        event(20, 3, "read", content="actual-after\n", full=True, use_ts=at(15), done_ts=at(20))])[PATH]
    assert story.versions[-1].source == "outband" and story.versions[-1].content == "actual-after\n"
    assert story.reads[-1].certain and not story.reads[-1].observation_uncertain


def test_legacy_read_without_use_ts_keeps_old_event_contract() -> None:
    story = filestory.build_stories([initial(), event(10, 2, "wfull", content="new\n"),
        event(20, 3, "read", content="old\n", full=True)])[PATH]
    assert story.versions[-1].source == "outband" and story.versions[-1].content == "old\n"
    assert story.reads[-1].certain and story.reads[-1].use_ts is None
    assert not story.reads[-1].observation_uncertain


def test_other_file_effect_does_not_make_this_read_uncertain() -> None:
    story = filestory.build_stories([initial(), event(10, 2, "wfull", path="/proj/B.ets", content="other\n"),
        event(20, 3, "read", content="old\n", full=True, use_ts=at(5), done_ts=at(20))])[PATH]
    assert len(story.versions) == 1 and story.reads[-1].certain


def test_unfinished_candidate_has_no_known_end_for_observation_binding() -> None:
    story = filestory.build_stories([initial(), event(3, 2, "candidate", use_ts=at(3)),
        event(20, 3, "read", content="old\n", full=True, use_ts=at(15), done_ts=at(20))])[PATH]
    assert len(story.versions) == 1 and not story.reads[-1].certain


def test_first_observation_inside_candidate_window_does_not_invent_known_state() -> None:
    story = filestory.build_stories([event(3, 1, "candidate", use_ts=at(3), done_ts=at(30)),
        event(20, 2, "read", content="sample\n", full=True, use_ts=at(5), done_ts=at(20))])[PATH]
    assert len(story.versions) == 1 and story.versions[0].source == "external" and story.versions[0].content is None
    assert not story.breaks and not story.reads[0].certain and story.reads[0].observation_uncertain


def test_interval_comparison_normalizes_offsets_without_changing_event_timestamps() -> None:
    read = event(20, 3, "read", content="old\n", full=True,
                 use_ts="2025-12-31T19:00:05-05:00", done_ts=at(20))
    story = filestory.build_stories([initial(), event(10, 2, "wfull", content="new\n"), read])[PATH]
    assert not story.reads[0].certain
    assert story.reads[0].ts == at(20) and story.reads[0].use_ts == "2025-12-31T19:00:05-05:00"


@pytest.mark.parametrize("backend", ["cc", "codex"])
@pytest.mark.parametrize("command", ["printf changed > /proj/A.ets", "false && printf changed > /proj/A.ets"])
def test_unfinished_shell_call_reaches_the_ledger_as_an_open_candidate_window(tmp_path: Path, backend: str, command: str) -> None:
    if backend == "cc":
        records = [*_call(at(0), "initial", "Write", {"file_path": PATH, "content": "old\n"}),
                   _rec(at(3), "assistant", [_use("pending", "Bash", {"command": command})]),
                   *_call(at(15), "read", "Bash", {"command": f"cat {PATH}"}, "old\n")]
        ledger = _ledger(tmp_path, records)
    else:
        import json
        records = [_crec(at(0), "session_meta", {"id": CROOT, "cwd": "/proj", "source": "cli"})]
        for second, cid, cmd, output in [(0, "initial", f"cat > {PATH} <<'EOF'\nold\nEOF", ""),
                                         (3, "pending", command, ""), (15, "read", f"cat {PATH}", "old\n")]:
            js = "const r=await tools.exec_command(" + json.dumps({"cmd": cmd, "workdir": "/proj"}) + ");text(JSON.stringify(r));"
            pair = _cexec(at(second), cid, js, output)
            pair[1]["timestamp"] = at(second + 1)
            records.extend(pair[:1] if cid == "pending" else pair)
        root = tmp_path / f"rollout-{CROOT}.jsonl"
        _write_jsonl(str(root), records)
        ledger = atoms.build_ledger(atoms_collect.collect_codex(str(root), seq=[0], sessions_root=str(tmp_path)))
    pending = next(a for ag in ledger.agents.values() for a in ag.actions if a.tuid == "pending")
    assert pending.ok is None and pending.done_ts is None and pending.src is not None and not pending.files
    assert PATH in pending.detail["touched"] and pending.detail["unfinished"]
    story = ledger.stories[PATH]
    assert len(story.versions) == 1 and story.versions[0].content == "old\n"
    assert any(t.seq == pending.seq for t in story.touches)
    assert not story.reads[-1].certain and story.reads[-1].observation_uncertain


@pytest.mark.parametrize("backend", ["cc", "codex"])
def test_concat_with_concurrently_written_source_does_not_invent_target_content(tmp_path: Path, backend: str) -> None:
    target = "/proj/B.ets"
    if backend == "cc":
        records = [*_call(at(0), "initial", "Write", {"file_path": PATH, "content": "old\n"}),
                   _rec(at(5), "assistant", [_use("concat", "Bash", {"command": f"cat {PATH} > {target}"})]),
                   *_call(at(10), "change", "Write", {"file_path": PATH, "content": "new\n"}),
                   _rec(at(30), "user", [_res("concat", "")])]
        ledger = _ledger(tmp_path, records)
    else:
        import json
        records = [_crec(at(0), "session_meta", {"id": CROOT, "cwd": "/proj", "source": "cli"})]
        for second, done, cid, cmd in [(0, 1, "initial", f"cat > {PATH} <<'EOF'\nold\nEOF"),
                                       (5, 30, "concat", f"cat {PATH} > {target}"),
                                       (10, 11, "change", f"cat > {PATH} <<'EOF'\nnew\nEOF")]:
            js = "const r=await tools.exec_command(" + json.dumps({"cmd": cmd, "workdir": "/proj"}) + ");text(JSON.stringify(r));"
            pair = _cexec(at(second), cid, js, "")
            pair[1]["timestamp"] = at(done)
            records.extend(pair)
        root = tmp_path / f"rollout-{CROOT}.jsonl"
        _write_jsonl(str(root), sorted(records, key=lambda r: r["timestamp"]))
        ledger = atoms.build_ledger(atoms_collect.collect_codex(str(root), seq=[0], sessions_root=str(tmp_path)))
    ver = ledger.stories[target].versions[0]
    writer = next(a for ag in ledger.agents.values() for a in ag.actions if a.tuid == "concat")
    assert ver.content is None and ver.source == "derived" and ver.act_seq == writer.seq
    assert writer.ok is True and ver.by_ver == writer.ver  # 动作/作者成立不等于内容值可确定
    assert any(r.dep and r.observation_uncertain for r in ledger.stories[PATH].reads)


@pytest.mark.parametrize("kind", ["wderived", "wconcat"])
@pytest.mark.parametrize("overlap", [True, False])
def test_derived_source_window_controls_content_not_writer_identity(kind: str, overlap: bool) -> None:
    target = "/proj/B.ets"
    copy = event(5, 2, kind, path=target, use_ts=at(5), done_ts=at(30 if overlap else 6),
                 aver=2, **({"src": PATH} if kind == "wderived" else {"sources": (PATH,)}))
    stories = filestory.build_stories([initial(), copy, event(10, 3, "wfull", content="new\n", use_ts=at(10), done_ts=at(11))])
    ver = stories[target].versions[0]
    assert ver.content == (None if overlap else "old\n")
    assert ver.by == "agent-a" and ver.by_ver == 2 and ver.source == "derived"


@pytest.mark.parametrize("observation", ["full", "partial", "seen", "empty"])
def test_created_at_read_endpoint_never_erases_actually_returned_content(observation: str) -> None:
    fields = ({"content": "old\n", "full": True} if observation == "full" else
              {"content": "old", "start": 1, "n": 1} if observation == "partial" else
              {"seen": ((1, "old"),)} if observation == "seen" else {})
    read = event(10, 1, "read", use_ts=at(5), done_ts=at(10), **fields)
    created = event(10, 2, "wfull", content="new\n", created=True, use_ts=at(10), done_ts=at(11))
    story = filestory.build_stories([read, created])[PATH]
    if observation == "empty":
        assert len(story.versions) == 1 and not story.reads and story.touches
    else:
        assert len(story.versions) == 2 and len(story.reads) == 1
        assert story.reads[0].observation_uncertain and not story.reads[0].certain
        assert story.breaks[0].kind == "create-conflict"
        assert not any("内容未进上下文" in t.reason for t in story.touches)


@pytest.mark.parametrize("kind", ["read", "patch"])
def test_codex_pending_call_preserves_raw_pointer_without_inventing_effects(tmp_path: Path, kind: str) -> None:
    import json
    records = [_crec(at(0), "session_meta", {"id": CROOT, "cwd": "/proj", "source": "cli"})]
    initial_js = "text(await tools.exec_command(" + json.dumps({"cmd": f"cat > {PATH} <<'EOF'\nold\nEOF", "workdir": "/proj"}) + "));"
    records += _cexec(at(0), "initial", initial_js, "")
    if kind == "read":
        js = "text(await tools.exec_command(" + json.dumps({"cmd": f"cat {PATH}", "workdir": "/proj"}) + "));"
    else:
        patch = "*** Begin Patch\n*** Update File: /proj/A.ets\n@@\n-old\n+new\n*** End Patch"
        js = "text(await tools.apply_patch(" + json.dumps(patch) + "));"
    records += _cexec(at(3), "pending", js, "")[:1]
    root = tmp_path / f"rollout-{CROOT}.jsonl"
    _write_jsonl(str(root), records)
    ledger = atoms.build_ledger(atoms_collect.collect_codex(str(root), seq=[0], sessions_root=str(tmp_path)))
    owner = next(ag for ag in ledger.agents.values() if any(a.tuid == "pending" for a in ag.actions))
    pending = next(a for a in owner.actions if a.tuid == "pending")
    assert pending.ok is None and pending.files == [] and len(ledger.stories[PATH].versions) == 1
    assert (PATH in (pending.detail.get("touched") or [])) == (kind == "patch")
    raw = atoms.action_raw(ledger, owner.id, pending.seq)
    assert raw is not None and raw["input"] == js and raw["output"] == ""


@pytest.mark.parametrize("boundary", ["before", "touching", "after"])
def test_derived_source_endpoint_overlap_is_conservative(boundary: str) -> None:
    target = "/proj/B.ets"
    done = {"before": 9, "touching": 10, "after": 11}[boundary]
    copied = event(5, 2, "wconcat", path=target, sources=(PATH,), use_ts=at(5), done_ts=at(done))
    story = filestory.build_stories([initial(), copied, event(10, 3, "wfull", content="new\n", use_ts=at(10), done_ts=at(12))])[target]
    assert story.versions[0].content == ("old\n" if boundary == "before" else None)


def test_later_observation_can_seal_derived_value_after_source_overlap() -> None:
    target = "/proj/B.ets"
    copied = event(5, 2, "wconcat", path=target, sources=(PATH,), use_ts=at(5), done_ts=at(20))
    story = filestory.build_stories([initial(), copied,
        event(10, 3, "wfull", content="new\n", use_ts=at(10), done_ts=at(11)),
        event(31, 4, "read", path=target, content="actual copied\n", full=True, use_ts=at(30), done_ts=at(31))])[target]
    assert len(story.versions) == 1 and story.versions[0].source == "derived"
    assert story.versions[0].sealed and story.versions[0].content == "actual copied\n"
