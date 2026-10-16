"""Regressions for false absence/presence and phase recognition across adapters."""
from unittest.mock import patch

import pytest

from migloop.audit import build_audit
from migloop.audit_events import ClaudeCalls, capabilities, observation, phase
from migloop.adapters import claude, codex


def event(command, *, name="Bash", ok=True, call="c1", stage="a2h-verify", ts="2026-01-01T00:00:01Z", output=""):
    return {**observation(name, {"command": command}, output, ok, call=call, ts=ts), "stage": stage}


def trace(events=(), agents=(), stage="a2h-verify", sid="root"):
    return {"meta": {"session_id": sid}, "stages": [{"id": "s1", "stage": stage}],
            "tools": [], "audit_tools": list(events), "agents": list(agents)}


def status(result, rule):
    return next(c["status"] for c in result["assessments"] if c["rule"] == rule)


@pytest.mark.parametrize("command", ["ohpm install", "cat .hvigor/build.log", "grep hvigor log.txt", "echo 'hdc install screenshot'",
                                     "python -c \"print('hdc install screenshot')\"", "hvigorw --version", "ls screenshots"])
def test_mentions_are_not_actions(command):
    assert capabilities("Bash", {"command": command}) == []


@pytest.mark.parametrize("name", ["Bash", "PowerShell", "shell_command", "exec_command"])
def test_all_shells_and_long_commands(name):
    command = 'cd "' + "x" * 400 + '"; hdc -t emulator123 install demo.hap; hdc -t emulator123 shell snapshot_display'
    result = build_audit(trace([event(command, name=name)]))
    assert status(result, "verify-no-emulator") == "observed"
    assert status(result, "verify-no-install") == "observed"
    assert status(result, "verify-no-screenshot") == "observed"


def test_child_and_grandchild_evidence_counts_without_main_actions():
    agents = [{"agent_id": "child", "stage": "a2h-verify", "audit_tools": [event("hdc install a.hap")]},
              {"agent_id": "grandchild", "stage": "a2h-verify", "audit_tools": [event("hdc shell snapshot_display")]}]
    result = build_audit(trace(agents=agents))
    assert not result["findings"]
    assert result["coverage"]["owners"] == 3 and result["coverage"]["calls"] == 2


def test_pool_evidence_dedup_and_owner_specific_retry():
    failed = {**observation("Skill", {"skill": "a2h-verify"}, "bad", False, call="a", ts="2026-01-01T00:00:00Z"), "stage": "a2h-verify"}
    ok = {**failed, "call": "b", "outcome": "returned", "ts": "2026-01-01T00:00:02Z"}
    primary = trace([failed], sid="one")
    other = trace([ok], sid="two")
    result = build_audit(primary, pool_traces=[primary, other])
    assert result["coverage"]["calls"] == 2
    assert status(result, "skill-fail") == "failed"
    assert status(build_audit(trace([failed, ok])), "skill-fail") == "recovered"


def test_failed_calls_do_not_prove_success_or_absence():
    result = build_audit(trace([event("hdc install a.hap; hdc shell snapshot_display", ok=False)]))
    assert status(result, "verify-no-install") == "failed"
    assert "没执行" not in "".join(f["title"] for f in result["findings"])


def test_no_result_and_unknown_wrapper_remain_unknown():
    result = build_audit(trace([event("hdc install a.hap", ok=None), event("python private_runner.py")]))
    assert status(result, "verify-no-install") == "unknown"


def test_build_in_other_root_and_install_before_verify():
    earlier = trace([event("./hvigorw assembleHap", stage="a2h-execute", output="BUILD SUCCESSFUL"),
                     event("hdc install a.hap", stage="a2h-execute", call="c2")], sid="earlier", stage="a2h-execute")
    current = trace([event("hdc shell snapshot_display")])
    result = build_audit(current, pool_traces=[earlier])
    assert status(result, "execute-no-build") == "observed"
    assert status(result, "verify-no-install") == "observed"
    assert not result["findings"]


def test_gap_and_unrecognized_stage_never_mean_pass():
    result = build_audit(trace(stage="wf:custom"), material_gaps=True)
    assert result["coverage"]["material_gaps"]
    assert status(result, "verify-no-emulator") == "not_applicable"
    assert status(result, "script-fail") == "unknown"


def test_native_workflow_verify_role_has_checks():
    agent = {"agent_id": "worker", "type": "verify", "stage": "wf:app/accept", "audit_tools": []}
    result = build_audit(trace(agents=[agent], stage="wf:app/accept"))
    assert status(result, "verify-no-emulator") == "unknown"


def test_spec_naming_policy_is_not_a_default_error():
    result = build_audit(trace(stage="a2h-spec"))
    assert status(result, "spec-no-analyzer") == "not_applicable"
    assert phase("a2h-retrospect") == "retrospect"


def test_ongoing_agent_and_metadata_tail_are_not_abort():
    assert claude._abort_reason({"type": "progress"}) is None
    assert not [f for f in build_audit(trace(agents=[{"agent_id": "live", "aborted": "interrupted"}]))["findings"] if f["rule"] == "aborted-agent"]


def test_codex_native_abort_cleared_by_resumed_turn():
    state = codex._new_scan_state()
    codex._scan_record(state, 0, {"type": "event_msg", "payload": {"type": "turn_aborted"}})
    assert state["abort_explicit"] and not state["completed"]
    codex._scan_record(state, 1, {"type": "event_msg", "payload": {"type": "task_started"}})
    assert not state["abort_explicit"] and not state["completed"]


def test_claude_result_projection_retains_action_and_source():
    c = ClaudeCalls("worker.jsonl")
    c.observe({"timestamp": "2026-01-01T00:00:00Z", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": "a", "input": {"command": "hvigorw assembleHap"}}]}}, 4)
    c.observe({"message": {"content": [{"type": "tool_result", "tool_use_id": "a", "content": "BUILD SUCCESSFUL"}]}}, 5)
    row = c.finish()[0]
    assert row["capabilities"] == ["build"] and row["build_success"] and row["line"] == 5


def cc_row(i, skill=None, attr=None):
    row = {"type": "assistant", "sessionId": "s", "timestamp": f"2026-01-01T00:00:{i:02d}Z",
           "message": {"role": "assistant", "content": [{"type": "tool_use", "id": str(i), "name": "Skill", "input": {"skill": skill}}] if skill else []}}
    if attr:
        row["attributionSkill"] = attr
    return row


@pytest.mark.parametrize("rows,want", [
    ([cc_row(0,"a2h-execute"),cc_row(1,"a2h-verify"),cc_row(2,"a2h-execute")], ["a2h-execute","a2h-verify","a2h-execute"]),
    ([cc_row(0,"a2h-verify"),cc_row(1)], ["a2h-verify"]),
    ([cc_row(0,"a2h-spec"),cc_row(1,attr="a2h-spec")], ["a2h-spec"]),
])
def test_claude_stage_transitions(rows,want):
    with patch.object(claude,"load_main_session",return_value=rows), patch.object(claude,"load_workflow_runs",return_value=({},{})), patch.object(claude.os.path,"isdir",return_value=False):
        result = claude.extract("synthetic.jsonl")
    assert [s["stage"] for s in result["stages"]] == want


def test_codex_short_stage_preserved_and_bulk_read_not_a_transition():
    calls = [{"idx": 0,"raw":"cat /skills/a2h-execute/SKILL.md","ts":"2026-01-01T00:00:00Z"},
             {"idx": 1,"raw":"cat /skills/a2h-verify/SKILL.md","ts":"2026-01-01T00:00:30Z"}]
    assert codex._stage_boundaries({"calls":calls}) == [(0,"a2h-execute"),(1,"a2h-verify")]
    assert codex._stage_boundaries({"calls":[{"idx":0,"raw":"cat /skills/a2h-spec/SKILL.md /skills/a2h-plan/SKILL.md"}]}) == [(0,"session")]
    assert codex._stage_boundaries({"calls":[{"idx":0,"raw":"echo /skills/a2h-verify/SKILL.md"}]}) == [(0,"session")]
    assert codex._stage_boundaries({"calls":[{"idx":0,"raw":"// /skills/a2h-verify/SKILL.md\nconst x = 1;"}]}) == [(0,"session")]
