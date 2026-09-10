"""Synthetic direct native command receipts; no claim that wrapper-only pools contain these."""
import json
from copy import deepcopy

import pytest

from migloop import atoms, atoms_collect
from tests.test_atoms import CROOT, _ccommand, _crec, _write_jsonl

PATH = "/proj/A.ets"
WRITE = "cat > A.ets <<'EOF'\nknown\nEOF"


def at(second):
    return f"2026-01-01T00:00:{second:02d}Z"


def collect(tmp_path, records):
    root = tmp_path / f"rollout-{CROOT}.jsonl"
    _write_jsonl(str(root), [_crec(at(0), "session_meta", {"id": CROOT, "cwd": "/unrelated", "source": "cli"}), *records])
    ledger = atoms.build_ledger(atoms_collect.collect_codex(str(root), seq=[0], sessions_root=str(tmp_path)))
    return ledger, next(iter(ledger.agents.values()))


@pytest.mark.parametrize("name", ["exec_command", "shell_command", "functions.exec_command", "functions.shell_command"])
def test_unique_direct_native_commands_share_shell_facts_not_wrapper_inference(tmp_path, name):
    ledger, owner = collect(tmp_path, [*_ccommand(at(1), "write", WRITE, name=name),
                                      *_ccommand(at(3), "read", "cat A.ets", "known\n", name=name)])
    write, read = owner.actions
    assert write.ok is True and read.ok is True
    assert write.detail["pairing"] == read.detail["pairing"] == "unique_call_id"
    assert write.files[0].path == read.files[0].path == PATH
    assert write.files[0].proof.execution == read.files[0].proof.execution == "confirmed"
    assert read.files[0].ev.content == "known\n" and read.files[0].ev.full
    assert ledger.stories[PATH].versions[0].content == "known\n"
    assert not write.detail.get("code_host_intents")
    assert read.ts == at(3) and read.done_ts == at(4)
    raw = atoms.action_raw(ledger, owner.id, read.seq)
    assert raw is not None and "known" in raw["output"]


@pytest.mark.parametrize("shape", ["object", "json", "single_text"])
def test_only_explicit_structured_exit_and_output_shapes_authenticate(tmp_path, shape):
    records = _ccommand(at(1), "write", WRITE)
    value = {"exit_code": 0, "output": ""}
    records[1]["payload"]["output"] = (value if shape == "object" else json.dumps(value) if shape == "json"
                                         else [{"type": "input_text", "text": json.dumps(value)}])
    _, owner = collect(tmp_path, records)
    assert owner.actions[0].ok is True and owner.actions[0].files


@pytest.mark.parametrize("output", ["", "Script completed\nOutput:\n{}", "Exception: command failed",
    '{"exit_code":0,"output":"cut', {}, {"exit_code": 0}, {"exit_code": True, "output": ""},
    {"exit_code": "0", "output": ""}, {"exit_code": 0, "output": []},
    {"exit_code": None, "session_id": 3, "output": ""},
    {"exit_code": 0, "session_id": 3, "output": ""},
    [{"type": "input_text", "text": '{"exit_code":0,'}, {"type": "input_text", "text": '"output":""}'}]])
def test_empty_running_and_unknown_result_formats_remain_candidates(tmp_path, output):
    records = _ccommand(at(1), "write", WRITE)
    records[1]["payload"]["output"] = output
    _, owner = collect(tmp_path, records)
    action, = owner.actions
    assert action.ok is None and not action.files and action.src
    assert PATH in action.detail["effect_candidates"] and action.detail["unresolved"]


@pytest.mark.parametrize("flag", [{"is_error": True}, {"isError": True}, {"error": "failed"}, {"success": False}])
@pytest.mark.parametrize("location", ["body", "envelope"])
def test_error_flags_override_exit_zero_in_body_and_outer_result_envelope(tmp_path, flag, location):
    records = _ccommand(at(1), "write", WRITE)
    if location == "body":
        records[1]["payload"]["output"] = {"exit_code": 0, "output": "", **flag}
    else:
        records[1]["payload"].update(flag)
    _, owner = collect(tmp_path, records)
    action, = owner.actions
    assert action.ok is False and not action.files and PATH in action.detail["effect_candidates"]


@pytest.mark.parametrize("corruption", ["duplicate_use", "duplicate_result", "missing_id", "empty_id", "numeric_id", "orphan", "result_before_use"])
def test_pairing_requires_nonempty_string_id_and_one_original_use_and_result(tmp_path, corruption):
    records = _ccommand(at(1), "write", WRITE)
    if corruption == "duplicate_use":
        records.insert(1, deepcopy(records[0]))
    elif corruption == "duplicate_result":
        records.append(deepcopy(records[1]))
    elif corruption in {"missing_id", "empty_id", "numeric_id"}:
        for record in records:
            if corruption == "missing_id":
                record["payload"].pop("call_id")
            else:
                record["payload"]["call_id"] = "" if corruption == "empty_id" else 12
    elif corruption == "orphan":
        records = records[1:]
    else:
        records.reverse()
    _, owner = collect(tmp_path, records)
    assert all(not action.files and action.ok is None for action in owner.actions)
    if corruption != "orphan":
        assert any(PATH in a.detail.get("effect_candidates", []) for a in owner.actions)
        assert all(a.src for a in owner.actions)


def test_failed_read_output_does_not_become_an_observed_file_body(tmp_path):
    _, owner = collect(tmp_path, _ccommand(at(1), "read", "cat A.ets", "not authenticated\n", exit_code=1))
    action, = owner.actions
    assert action.ok is False and not action.files
    candidate, = action.detail["read_candidates"]
    assert candidate["path"] == PATH and candidate["seen"] is None
    assert candidate["proof"]["execution"] == "unknown"
    assert "not authenticated" not in json.dumps(action.detail)
    assert "not authenticated" in atoms.action_raw(atoms.build_ledger({owner.id: owner}), owner.id, action.seq)["output"]


def test_pending_native_preserves_candidate_and_original_pointer(tmp_path):
    ledger, owner = collect(tmp_path, _ccommand(at(1), "write", WRITE)[:1])
    action, = owner.actions
    assert action.ok is None and action.done_ts is None and action.detail["unfinished"]
    assert not action.files and PATH in action.detail["effect_candidates"]
    assert atoms.action_raw(ledger, owner.id, action.seq)["output"] == ""


@pytest.mark.parametrize("where", ["body_flag", "envelope_flag", "text_warning", "text_marker"])
def test_truncated_body_does_not_become_a_full_native_read_snapshot(tmp_path, where):
    records = _ccommand(at(1), "read", "cat A.ets", "prefix")
    result = {"exit_code": 0, "output": "prefix"}
    if where == "body_flag": result["truncated"] = True
    elif where == "envelope_flag": records[1]["payload"]["truncated"] = True
    elif where == "text_warning": result["output"] = "Warning: truncated output (original token count: 300)\nprefix"
    else: result["output"] = "prefix\n…".replace("…", "... 200 tokens truncated ...")
    records[1]["payload"]["output"] = result
    _, owner = collect(tmp_path, records)
    action, = owner.actions
    assert action.ok is True and action.files[0].proof.execution == "confirmed"
    assert action.files[0].ev.content is None and not action.files[0].ev.full
    assert action.detail["output_delivery"] == "truncated_body_unbound"


@pytest.mark.parametrize("name", ["mcp.evil.exec_command", "other.exec_command", "exec"])
def test_similar_provider_names_or_wrapper_are_not_native_command_proof(tmp_path, name):
    _, owner = collect(tmp_path, _ccommand(at(1), "write", WRITE, name=name))
    assert all(not action.files for action in owner.actions)


def test_native_exit_zero_still_cannot_prove_a_conditional_shell_branch(tmp_path):
    _, owner = collect(tmp_path, _ccommand(at(1), "write", "false && printf changed > A.ets; true"))
    action, = owner.actions
    assert action.ok is True and not action.files and PATH in action.detail["effect_candidates"]
