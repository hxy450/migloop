"""A use-time cutoff must not turn a later tool result into earlier input."""
from copy import deepcopy

import pytest

from migloop import atom_scope, atoms
from migloop.filestory import Ev


AID = "__main__:scope"
PATH = "/proj/A.ets"


def ts(second):
    return f"2026-01-01T00:00:{second:02d}Z"


def action(seq, use, done, *, kind="other", ver=None, files=(), detail=None):
    return atoms.Action(ts(use), seq, "tool", kind, ver=ver, at=ver or 2,
                        done_ts=ts(done) if done is not None else None,
                        files=list(files), detail=detail or {},
                        src=("/not-opened/root.jsonl", seq * 2, seq * 2 + 1))


def ref(seq, *, use=5, done=20, op="read", via="tool", dep=False, v=1):
    event = Ev(ts(done or use), seq, "read" if op == "read" else "wfull", PATH, AID,
               via=via, dep=dep, full=op == "read", seen=((1, "SECRET_RETURN"),) if op == "read" else None,
               use_ts=ts(use), done_ts=ts(done) if done is not None else None)
    return atoms.FileRef(op, PATH, event, v=v)


def fixture(*, done=20, dep=False, via="tool", read_kind="read"):
    acts = [action(1, 0, 1, kind="write", ver=1, files=[ref(1, use=0, done=1, op="write")]),
            action(2, 5, done, kind=read_kind, files=[ref(2, done=done, dep=dep, via=via)],
                   detail={"cmd": "cat /proj/A.ets", "output": "SECRET_RETURN", "result": "SECRET_RETURN",
                           "mentions": [("future", "SECRET_RETURN", PATH, "out", "out")]}),
            action(3, 10, 11),
            action(4, 30, 31, kind="write", ver=2,
                   files=[ref(4, use=30, done=31, op="write", v=2)]),
            action(5, 40, 41, kind="dispatch", ver=3, detail={"child": "agent-later"})]
    owner = atoms.AgentRec(AID, "scope", actions=acts, result="FUTURE_SUMMARY")
    ledger = atoms.Ledger({}, {AID: owner})
    payload = atoms.agent_atom(ledger, AID, v=3)
    return ledger, payload


def test_late_read_and_derived_collections_do_not_cross_cutoff():
    ledger, payload = fixture()
    # self_written means this agent wrote the path somewhere in its lifetime,
    # not that this Read result was already present in its invocation input.
    assert payload["reads"][0]["self_written"] is True
    original, old_ledger = deepcopy(payload), deepcopy(ledger)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert result["reads"] == []
    assert [r["seq"] for r in result["actions"]] == [1, 2, 3]
    read = result["actions"][1]
    assert read["completion_state"] == "pending" and read["ok"] is None
    assert read["files"] == [] and read["detail"] == {"cmd": "cat /proj/A.ets"}
    assert [r["v"] for r in result["writes"]] == [1]
    assert result["children"] == [] and result["result"] is None
    deferred = result["cutoff"]["deferred_reads"]
    assert len(deferred) == 1 and deferred[0]["seq"] == 2
    assert deferred[0]["done_ts"] == ts(20)
    assert "seen" not in deferred[0] and "full" not in deferred[0]
    assert "SECRET_RETURN" not in str(result) and "FUTURE_SUMMARY" not in str(result)
    assert result["cutoff"]["excluded"]["actions"] == 2
    assert result["cutoff"]["excluded"]["writes"] == 1
    assert payload == original and ledger == old_ledger
    result["actions"][0]["files"][0]["path"] = "changed"
    assert payload == original and ledger == old_ledger


@pytest.mark.parametrize("done", [None, 20])
def test_incomplete_write_and_dispatch_are_candidates_not_effects(done):
    ledger, payload = fixture()
    owner = ledger.agents[AID]
    owner.actions[1] = action(2, 5, done, kind="write", ver=2,
        files=[ref(2, op="write", v=2)], detail={"args": "INPUT_BODY", "output": "SECRET_RETURN"})
    owner.actions[2] = action(3, 10, done, kind="dispatch", ver=3,
        detail={"name": "worker", "prompt": "INPUT_PROMPT", "child": "agent-result", "result": "SECRET_RETURN"})
    owner.actions = owner.actions[:3]
    payload = atoms.agent_atom(ledger, AID, v=3)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert [r["v"] for r in result["writes"]] == [1]
    assert result["children"] == []
    assert len(result["cutoff"]["deferred_effects"]) == 2
    assert all(r["completion_state"] == ("unknown" if done is None else "pending")
               and r["ok"] is None and not r["files"] for r in result["actions"][1:])
    assert "SECRET_RETURN" not in str(result) and "agent-result" not in str(result)
    assert "INPUT_BODY" in str(result) and "worker" in str(result)
    # agent_atom already indexes dispatch prompts by action; cutoff must not
    # expand that historical disclosure just because the ledger has the prompt.
    assert "INPUT_PROMPT" not in str(result)


def test_completed_read_remains_a_result_not_semantically_verified():
    ledger, payload = fixture(done=8)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert result["reads"][0]["availability_basis"] == "result"
    assert result["reads"][0]["seen"] == [[1, "SECRET_RETURN"]]
    assert result["actions"][1]["completion_state"] == "completed"
    assert result["cutoff"]["deferred_reads"] == []


def test_input_injection_is_not_held_until_nonexistent_tool_result():
    ledger, payload = fixture(done=None, via="inject", read_kind="inject")
    ledger.agents[AID].actions[1].src = ("/not-opened/root.jsonl", 4, 4)
    payload = atoms.agent_atom(ledger, AID, v=3)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert result["reads"][0]["availability_basis"] == "input"
    assert result["reads"][0]["seen"] == [[1, "SECRET_RETURN"]]
    assert result["actions"][1]["completion_state"] == "observed"


def test_pending_command_dependency_is_not_a_readback_or_completed_version():
    ledger, payload = fixture(dep=True, via="shell")
    result = atom_scope.agent_until(ledger, payload, 3)
    dep = result["reads"][0]
    assert dep["availability_basis"] == "dependency" and dep["dep"] is True
    assert dep["seen"] is None and dep["full"] is False
    assert dep["v"] is None and dep["certain"] is False
    assert "SECRET_RETURN" not in str(result)


@pytest.mark.parametrize("via", ["image", "stdout"])
def test_output_derived_dependencies_cannot_be_early_inputs(via):
    ledger, payload = fixture(dep=True, via=via)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert not result["reads"] and result["cutoff"]["deferred_reads"]


def test_plain_shell_read_without_dependency_flag_is_not_input():
    ledger, payload = fixture(dep=False, via="shell")
    result = atom_scope.agent_until(ledger, payload, 3)
    assert result["reads"] == []
    assert result["cutoff"]["deferred_reads"]


@pytest.mark.parametrize("until", [None, True, "3", -1, 999, 5])
def test_invalid_cutoff_never_returns_apparently_bounded_full_payload(until):
    ledger, payload = fixture()
    payload["v"] = 2
    with pytest.raises(ValueError):
        atom_scope.agent_until(ledger, payload, until)


def test_missing_action_time_withholds_body_and_remains_unknown():
    ledger, payload = fixture(done=None)
    ledger.agents[AID].actions[1].ts = "not-a-time"
    payload = atoms.agent_atom(ledger, AID, v=3)
    result = atom_scope.agent_until(ledger, payload, 3)
    row = result["actions"][1]
    assert row["completion_state"] == "unknown" and row["detail"] == {} and row["files"] == []
    assert not result["reads"] and "SECRET_RETURN" not in str(result)


def test_equal_instant_needs_physical_result_before_cutoff_call():
    ledger, payload = fixture(done=10)
    act = ledger.agents[AID].actions[1]
    act.done_ts = "2025-12-31T19:00:10-05:00"
    # Result is after the cutoff call on the same physical transcript.
    act.src = ("/not-opened/root.jsonl", 4, 8)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert not result["reads"] and result["actions"][1]["completion_state"] == "unknown"
    act.src = ("/not-opened/root.jsonl", 4, 5)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert result["reads"][0]["availability_basis"] == "result"


def test_same_time_message_after_call_is_not_already_available():
    ledger, payload = fixture()
    owner = ledger.agents[AID]
    owner.actions[1] = action(2, 10, None, kind="inbox", detail={"text": "LATE_MESSAGE"})
    owner.actions[1].src = ("/not-opened/root.jsonl", 9, 9)
    payload = atoms.agent_atom(ledger, AID, v=3)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert result["inbox"] == []
    assert result["actions"][1]["completion_state"] == "unknown"
    assert "LATE_MESSAGE" not in str(result)
    owner.actions[1].src = ("/not-opened/root.jsonl", 5, 5)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert result["inbox"][0]["text"] == "LATE_MESSAGE"


def test_future_timestamp_is_excluded_even_with_smaller_sequence_number():
    ledger, payload = fixture()
    ledger.agents[AID].actions[1].ts = ts(15)
    payload = atoms.agent_atom(ledger, AID, v=3)
    result = atom_scope.agent_until(ledger, payload, 3)
    assert [r["seq"] for r in result["actions"]] == [1, 3]
    assert not result["reads"]


@pytest.mark.parametrize("backend", ["cc", "codex"])
def test_collected_read_completion_remains_outside_its_own_invocation_cutoff(tmp_path, backend):
    from tests.test_read_observation_windows import collected

    ledger = collected(tmp_path, backend)
    owner = next(iter(ledger.agents.values()))
    read = next(a for a in owner.actions if a.tuid == "read")
    payload = atoms.agent_atom(ledger, owner.id)
    original, old_ledger = deepcopy(payload), deepcopy(ledger)
    result = atom_scope.agent_until(ledger, payload, read.seq)
    assert result["cutoff"]["use_ts"] == "2026-01-01T00:00:05.000000Z"
    assert result["reads"] == []
    row = next(r for r in result["actions"] if r["seq"] == read.seq)
    assert row["completion_state"] == "pending" and row["ok"] is None
    assert result["cutoff"]["deferred_reads"][0]["source"] == list(read.src)
    assert len(result["writes"]) == 1  # Concurrent write starts only at second 10.
    assert ledger == old_ledger and payload == original


@pytest.mark.parametrize("mutation", ["foreign_action", "duplicate_action", "naive_cutoff"])
def test_ambiguous_or_unverifiable_coordinates_fail_closed(mutation):
    ledger, payload = fixture()
    if mutation == "foreign_action":
        payload["actions"][0]["seq"] = 200
    elif mutation == "duplicate_action":
        ledger.agents[AID].actions.append(deepcopy(ledger.agents[AID].actions[0]))
    else:
        ledger.agents[AID].actions[2].ts = "2026-01-01T00:00:10"
    original, old_ledger = deepcopy(payload), deepcopy(ledger)
    with pytest.raises(ValueError):
        atom_scope.agent_until(ledger, payload, 3)
    assert ledger == old_ledger and payload == original


def test_integrated_text_and_json_do_not_disclose_late_result(monkeypatch):
    from migloop import atoms_text, service

    ledger, payload = fixture()
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    text = atoms_text.render_agent(ledger, AID, v=3, until=3, seen=True)
    assert "SECRET_RETURN" not in text and "FUTURE_SUMMARY" not in text
    assert "尚未返回" in text and "截止时未确认可用的读取" in text
    result = service.atom_json("unused", "agent", {"id": AID, "v": 3, "until": 3})
    assert not result["reads"] and not result["children"]
    assert [row["v"] for row in result["writes"]] == [1]
    assert result["cutoff"]["excluded"]["actions"] == 2
    assert atoms_text.render_agent(ledger, AID, v=3, until=999).startswith("⛔")
    with pytest.raises(ValueError):
        service.atom_json("unused", "agent", {"id": AID, "v": 3, "until": 999})


def test_invalid_mcp_until_does_not_consume_first_open():
    import asyncio

    pytest.importorskip("mcp")
    from migloop import mcp_server, probe

    ledger, _ = fixture()

    class Backend:
        async def get_ledger(self, sid):
            return ledger

        async def get_session_cwd(self, sid):
            return "/proj"

    server = mcp_server.build_server(Backend())

    async def call(until):
        result = await server.call_tool("agent", {"sid": "unused", "id": AID,
            "v": 3, "until": until, "seen": True, "via": "sessions"})
        parts = result[0] if isinstance(result, tuple) else result
        return probe._unwrap_result("".join(getattr(p, "text", "") for p in parts))

    async def check():
        assert (await call(999)).startswith("⛔")
        opened = await call(3)
        assert opened.startswith("# agent")  # Rejection did not register a node.
        assert "SECRET_RETURN" not in opened and "FUTURE_SUMMARY" not in opened

    asyncio.run(check())
