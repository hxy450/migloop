"""Transcript references use stable IDs, never the shared rollout filename prefix."""
from __future__ import annotations

import re

from migloop import atoms, atoms_collect, atoms_text
from tests.test_atoms import _write_jsonl

NAMES = ["rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl",
         "rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl"]
IDS = ["01a009fe-68e3-7f42-b76b-5e863c555976", "01a021e5-c150-7b12-a610-d40c07816b98"]


def roots(tmp_path, count=2):
    agents, seq = {}, [0]
    for name, sid in zip(NAMES[:count], IDS):
        path = tmp_path / name
        records = [{"timestamp": "2026-08-16T17:54:23Z", "type": "session_meta", "payload": {"id": sid, "cwd": "/proj"}},
                   {"timestamp": "2026-08-16T17:54:24Z", "type": "response_item", "payload": {
                       "type": "message", "id": "msg-" + sid, "role": "user", "content": [{"type": "input_text", "text": "instruction"}]}},
                   {"timestamp": "2026-08-16T17:54:25Z", "type": "response_item", "payload": {
                       "type": "function_call", "call_id": "call-" + sid, "name": "exec_command", "arguments": '{"cmd":"echo observed"}'}},
                   {"timestamp": "2026-08-16T17:54:26Z", "type": "response_item", "payload": {
                       "type": "function_call_output", "call_id": "call-" + sid, "output": "observed"}}]
        _write_jsonl(str(path), records)
        agents.update(atoms_collect.collect_codex(str(path), seq=seq, sessions_root=str(tmp_path)))
    return atoms.build_ledger(agents)


def test_real_rollout_filename_tags_roundtrip_every_action_including_messages(tmp_path):
    led = roots(tmp_path)
    assert set(led.tag_paths) == set(IDS)
    assert atoms.resolve_tag(led, "rollout-") == (None, True)
    kinds = set()
    for owner in led.agents.values():
        for action in owner.actions:
            kinds.add(action.kind)
            rendered = atoms_text._ref(action.seq, None, led.locs[action.seq])
            match = atoms.REF_RE.search(rendered)
            assert match and match[1] in IDS
            assert atoms.resolve_ref(led, int(match[2]), int(match[3]), int(match[4]) if match[4] else None, match[1]) == (action.seq, "ok")
    assert "inbox" in kinds and len(kinds) > 1


def test_legacy_rollout_alias_is_accepted_only_when_unique(tmp_path):
    led = roots(tmp_path, 1)
    assert atoms.resolve_tag(led, "rollout-") == (IDS[0], False)


def test_malformed_rollout_names_have_stable_safe_distinct_tags():
    names = ["rollout-2026-08-16-missing-id", "rollout-2026-08-21-missing-id"]
    tags = [atoms.transcript_tag("/a/" + name + ".jsonl") for name in names]
    assert len(set(tags)) == 2 and "rollout-" not in tags
    assert all(re.fullmatch(r"[\w-]+", tag) for tag in tags)
    assert tags == [atoms.transcript_tag("/b/" + name + ".jsonl") for name in names]
    assert atoms.transcript_tag("/a/49d451b1-more.jsonl") == "49d451b1"
    assert atoms.transcript_tag("/a/agent-a68daf720e780b4c2.jsonl") == "a68daf720e780b4c2"


def test_same_exact_tag_in_different_files_rejects_even_nonoverlapping_lines(tmp_path):
    agents = {}
    for i, name in enumerate(["abcdefgh-one.jsonl", "abcdefgh-two.jsonl"]):
        path = tmp_path / name
        _write_jsonl(str(path), [{"text": "different original source " + str(i)}] * (i + 1))
        agents[str(i)] = atoms.AgentRec(str(i), "s", actions=[atoms.Action("t", i + 1, "say", "say", src=(str(path), i, i))])
    led = atoms.build_ledger(agents)
    assert atoms.resolve_tag(led, "abcdefgh") == (None, True)
    assert atoms.resolve_tag(led, "abcd") == (None, True)
    for owner in agents.values():
        action = owner.actions[0]
        assert atoms.resolve_ref(led, action.seq, action.src[1] + 1, None, "abcdefgh") == (None, "ambiguous")
    assert len(led.tag_conflicts["abcdefgh"]) == 2
