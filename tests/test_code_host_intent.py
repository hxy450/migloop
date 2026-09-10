"""Outer code-host completion never authenticates regex-extracted nested calls."""
import json

import pytest

from migloop import (
    atoms,
    atoms_collect,
    change_inventory,
    investigation,
    temporal_state,
    transcript_store,
)
from migloop.evidence import FileProof
from migloop.filestory import Ev

PATH = "/proj/A.ets"
ROOT_ID = "11111111-2222-3333-4444-555555555555"
PATCH = "*** Begin Patch\n*** Update File: /proj/A.ets\n@@\n-old\n+new\n*** End Patch"
APPLY = "await tools.apply_patch(" + json.dumps(PATCH) + ");"


def ts(second):
    return f"2026-01-01T00:00:{second:02d}Z"


def shell(command):
    return "text(await tools.exec_command(" + json.dumps({"cmd": command, "workdir": "/proj"}) + "));"


def parse(js, output="Script completed\nOutput:\n{}", *, completed=True):
    return atoms_collect._codex_exec_ops(js, output, "/proj", {}, completed=completed, ts=ts(1))


@pytest.mark.parametrize("js", [APPLY, "if (false) {" + APPLY + "}", "async function unused() {" + APPLY + "}",
    shell("cat /proj/A.ets"), "if (false) {" + shell("cat /proj/A.ets") + "}",
    "async function unused() {" + shell("printf x > /proj/A.ets") + "}"])
def test_direct_dead_branch_and_uncalled_function_are_only_unknown_intent(js):
    ops, detail, ok = parse(js)
    assert ok and ops == [] and detail["operation_basis"] == "code_host_intent"
    assert detail["execution"] == "unknown" and detail["output_association"] == "unverified_outer_output"
    assert "code_host_nested_execution_unverified" in detail["unsupported_execution"]
    assert detail["code_host_intents"]
    for intent in detail["code_host_intents"]:
        assert intent["proof"]["operation_basis"] == "code_host_intent"
        assert intent["proof"]["execution"] == intent["proof"]["delivery"] == intent["proof"]["snapshot"] == "unknown"
        assert intent["execution_observed"] is False and intent["author_status"] == "unknown"


@pytest.mark.parametrize("output", ["Script completed\nOutput:\n{}", "Script completed\nOutput:\n{\"isError\":true}",
    "Script completed\nOutput:\n{\"exit_code\":0,\"output\":\"FAKE FILE CONTENT\"}",
    "Script failed\nOutput:\ninner error"])
def test_multiple_nested_calls_and_failure_output_never_authenticate_a_read_or_write(output):
    ops, detail, _ok = parse(shell("cat /proj/A.ets") + shell("printf x > /proj/B.ets") + APPLY, output)
    assert ops == []
    assert PATH in detail["effect_candidates"] and "/proj/B.ets" in detail["effect_candidates"]
    assert all(row["seen"] is None and row["proof"]["execution"] == "unknown" for row in detail["read_candidates"])
    assert "FAKE FILE CONTENT" not in json.dumps(detail)


def test_conditional_nested_reads_have_no_duplicate_old_receipts_seen_or_snapshot():
    js = shell("cat /proj/A.ets") + shell("false && cat /proj/B.ets") + APPLY
    ops, detail, _ = parse(js, 'Script completed\nOutput:\n{"exit_code":1,"output":"1:FAKE FILE CONTENT"}')
    assert ops == []
    reads = detail["read_candidates"]
    assert [r["path"] for r in reads] == ["/proj/A.ets", "/proj/B.ets"]
    assert len([i for i in detail["code_host_intents"] if i["op"] == "read"]) == len(reads)
    assert all(r["seen"] is None and "full" not in r and "content" not in r for r in reads)
    assert all(r["proof"]["operation_basis"] == "code_host_intent" and
               r["proof"]["execution"] == r["proof"]["delivery"] == r["proof"]["snapshot"] == "unknown" for r in reads)
    assert "FAKE FILE CONTENT" not in json.dumps(detail)


def test_pending_code_host_retains_unknown_breakpoint_not_a_completed_operation():
    ops, detail, ok = parse(APPLY, completed=False)
    assert ops == [] and ok is False and detail["effect_candidates"] == [PATH]
    assert "未完成" in detail["unresolved"]
    assert detail["code_host_intents"][0]["proof"]["execution"] == "unknown"


def pool(tmp_path, *, success=True, late=False, failed_outer=False):
    source = tmp_path / ("rollout-" + ROOT_ID + ".jsonl")
    native = {"timestamp": ts(4 if late else 2), "type": "event_msg", "payload": {
        "type": "patch_apply_end", "call_id": "independent-inner-id", "success": success,
        "changes": {PATH: {"type": "update", "unified_diff": "@@ -1 +1 @@\n-old\n+new\n"}}}}
    records = [
        {"timestamp": ts(0), "type": "session_meta", "payload": {"id": ROOT_ID, "cwd": "/proj", "source": "cli"}},
        {"timestamp": ts(1), "type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "outer-id", "name": "exec", "input": APPLY}},
        {"timestamp": ts(3), "type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "outer-id",
            "output": "Script failed\nOutput:\nerror" if failed_outer else "Script completed\nOutput:\n{}"}}]
    records.insert(3 if late else 2, native)
    source.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    ledger = atoms.build_ledger(atoms_collect.collect_codex(str(source), seq=[0], sessions_root=str(tmp_path)))
    return ledger, source


def test_different_id_native_effect_is_the_only_confirmed_change_without_author(tmp_path):
    ledger, _source = pool(tmp_path)
    action, = [a for owner in ledger.agents.values() for a in owner.actions if a.tool == "exec"]
    assert action.ok and action.files == [] and action.detail["code_host_intents"]
    output = change_inventory.build(ledger, {"kind": "file", "key": PATH, "at": ts(5)})
    confirmed = [r for r in output["rows"] if r["status"] == "confirmed_change"]
    assert len(confirmed) == 1 and confirmed[0]["agent"] is None and confirmed[0]["author_status"] == "unknown"
    assert confirmed[0]["native"]["call_id"] == "independent-inner-id" and confirmed[0]["raw_only"]
    assert all(r["status"] == "candidate_effect" for r in output["rows"] if r not in confirmed)
    diff = temporal_state.query(ledger, "diff", PATH, ts(5))
    assert not diff["known"]
    delta, = diff["rows"]  # Only the independent native diff, not wrapper intent.
    assert delta["agent"] is None and delta["author_status"] == "unknown"
    assert delta["ref"] in confirmed[0]["evidence"]
    assert delta["ts"].startswith(ts(2)[:-1]) and delta["changed_time_unknown"]


@pytest.mark.parametrize("failed_outer", [False, True])
def test_failed_native_or_wrapper_keeps_uncertainty_without_an_extra_confirmed_write(tmp_path, failed_outer):
    ledger, _ = pool(tmp_path, success=False, failed_outer=failed_outer)
    output = change_inventory.build(ledger, {"kind": "file", "key": PATH, "at": ts(5)})
    assert output["rows"] and all(r["status"] == "candidate_effect" for r in output["rows"])
    assert temporal_state.query(ledger, "blame", PATH, ts(5))["known"] is False


def test_late_native_event_is_not_pulled_back_to_outer_completion(tmp_path):
    ledger, _ = pool(tmp_path, late=True)
    before = change_inventory.build(ledger, {"kind": "file", "key": PATH, "at": ts(3)})
    assert not any(r["status"] == "confirmed_change" for r in before["rows"])
    assert temporal_state.query(ledger, "blame", PATH, ts(3))["native_effect_barriers"] == []
    after = change_inventory.build(ledger, {"kind": "file", "key": PATH, "at": ts(4)})
    confirmed, = [r for r in after["rows"] if r["status"] == "confirmed_change"]
    assert confirmed["agent"] is None and confirmed["observation_ts"].startswith(ts(4)[:-1])


def test_explicit_fault_breakpoint_invalidates_known_state_without_fake_actor(tmp_path):
    ledger, _ = pool(tmp_path, success=False, failed_outer=True)
    owner = next(iter(ledger.agents.values()))
    initial = Ev(ts(0), 100, "wfull", PATH, owner.id, content="old\n", created=True,
                 proof=FileProof("native_tool", "confirmed", "none", "full"))
    owner.actions.insert(0, atoms.Action(ts(0), 99, "Write", "write", done_ts=ts(0), files=[atoms.FileRef("write", PATH, initial)]))
    ledger = atoms.build_ledger(ledger.agents)
    assert temporal_state.query(ledger, "blame", PATH, ts(0))["known"]
    after = temporal_state.query(ledger, "blame", PATH, ts(5))
    assert not after["known"] and not after["rows"]
    assert all(r["agent"] is None for r in after["native_effect_barriers"])


def test_wrapper_raw_stdout_remains_expandable_without_file_input_binding(tmp_path):
    ledger, source = pool(tmp_path)
    raw = transcript_store.read_record(str(source), 4)
    output = investigation.query(ledger, "expand", {"scope": {"kind": "pool", "at": ts(5)},
        "refs": [{"ref": raw.ref, "pointer": "/payload/output"}]})
    assert output["items"][0]["status"] == "ok"
    assert output["items"][0]["records"][0]["text"] == "Script completed\nOutput:\n{}"
    assert all(not a.files for owner in ledger.agents.values() for a in owner.actions if a.tool == "exec")
