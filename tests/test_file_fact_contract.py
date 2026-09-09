"""File facts do not inherit execution or body visibility from lexical hints."""
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from migloop import atoms, atoms_collect, verdict
from migloop.evidence import FileProof, read_basis
from tests.test_atoms import CROOT, _call, _cexec, _crec, _ledger, _write_jsonl


TARGET = "/proj/Example.ets"


def script(body):
    return "python3 - <<'PY'\n" + body + "\nPY"


def build(tmp_path, mode, commands, *, seed=False, tail=True):
    commands = list(commands)
    if seed:
        commands.insert(0, ("cat > /proj/Example.ets <<'EOF'\nseed\nEOF", ""))
    if tail:
        commands.append(("cat > /proj/Result.ets <<'EOF'\nresult\nEOF", ""))
    if mode == "cc":
        rows = []
        for i, (command, output) in enumerate(commands):
            rows += _call(f"2026-01-01T00:00:{i * 5:02d}Z", f"call-{i}", "Bash", {"command": command}, output)
        ledger = _ledger(tmp_path, rows)
    else:
        rows = [_crec("2026-01-01T00:00:00Z", "session_meta", {"id": CROOT, "cwd": "/proj", "source": "cli"})]
        for i, (command, output) in enumerate(commands):
            js = "text(await tools.exec_command(" + json.dumps({"cmd": command, "workdir": "/proj"}) + "));"
            pair = _cexec(f"2026-01-01T00:00:{i * 5:02d}Z", f"call-{i}", js, output)
            pair[1]["timestamp"] = f"2026-01-01T00:00:{i * 5 + 1:02d}Z"
            rows += pair
        root = Path(tmp_path) / f"rollout-{CROOT}.jsonl"
        _write_jsonl(str(root), rows)
        ledger = atoms.build_ledger(atoms_collect.collect_codex(str(root), seq=[0], sessions_root=str(tmp_path)))
    owner = next(iter(ledger.agents.values()))
    return ledger, owner


@pytest.mark.parametrize("mode", ["cc", "codex"])
def test_write_keyword_and_printed_path_never_create_a_file_write(tmp_path, mode):
    command = script("def write_text(): pass\nwrite_text()\nprint('Example.ets')")
    ledger, owner = build(tmp_path, mode, [(command, "Example.ets\n")])
    first = owner.actions[0]
    assert not first.files and first.ver is None
    assert TARGET not in ledger.stories or not ledger.stories[TARGET].versions
    assert not first.detail.get("touched") and not first.detail.get("effect_candidates")
    assert any(m.seq == first.seq for m in ledger.mentions[TARGET])
    assert "write_text" in str(atoms.action_raw(ledger, owner.id, first.seq)["input"])


@pytest.mark.parametrize("mode", ["cc", "codex"])
@pytest.mark.parametrize("prefix", ["raise SystemExit(0)", "unknown_control()", "thing.read()",
                                    "def open(*args): return sink\nopen = custom_open"])
def test_unsupported_execution_domain_does_not_publish_later_write_snapshot(tmp_path, mode, prefix):
    command = script(prefix + "\nopen('Example.ets','w').write('bad')")
    ledger, owner = build(tmp_path, mode, [(command, "ok\n")])
    first = owner.actions[0]
    assert not first.files and first.ver is None
    assert TARGET in first.detail["effect_candidates"]
    assert not ledger.stories[TARGET].versions
    assert any(t.seq == first.seq for t in ledger.stories[TARGET].touches)
    assert atoms.action_raw(ledger, owner.id, first.seq) is not None


@pytest.mark.parametrize("mode", ["cc", "codex"])
def test_exists_is_metadata_not_body_read_even_with_known_prior_version(tmp_path, mode):
    command = script("from pathlib import Path\nprint(Path('Example.ets').exists())")
    ledger, owner = build(tmp_path, mode, [(command, "True\n")], seed=True)
    probe_action = owner.actions[1]
    assert TARGET in probe_action.detail["probed"]
    assert not probe_action.files and not ledger.stories[TARGET].reads
    file_node = verdict.resolve_node(ledger, f"file:{TARGET}@v1")
    agent_node = verdict.resolve_node(ledger, f"agent:{owner.id}@v2")
    assert verdict._rel_read(ledger, file_node, agent_node)[0] != "true"


@pytest.mark.parametrize("mode", ["cc", "codex"])
def test_pure_mention_does_not_poison_the_next_real_edit(tmp_path, mode):
    command = script("s=open('Example.ets').read()\ns=s.replace('seed','new')\nopen('Example.ets','w').write(s)")
    ledger, owner = build(tmp_path, mode, [(script("print('Example.ets')"), "Example.ets\n"), (command, "")], seed=True)
    assert not owner.actions[1].detail.get("touched")
    assert not owner.actions[1].detail.get("effect_candidates")
    assert ledger.stories[TARGET].versions[-1].content == "new\n"


@pytest.mark.parametrize("mode", ["cc", "codex"])
def test_reliable_straightline_keeps_author_content_and_proof(tmp_path, mode):
    command = script("from pathlib import Path\np='Example.ets'\nPath(p).write_text('known')")
    ledger, owner = build(tmp_path, mode, [(command, "")])
    action = owner.actions[0]
    ref = next(f for f in action.files if f.path == TARGET)
    version = ledger.stories[TARGET].versions[0]
    assert version.content == "known" and version.by == owner.id and action.ver == 1
    assert ref.ev.proof.execution == version.proof.execution == "confirmed"
    assert ref.ev.proof.operation_basis == "supported_python"
    payload = atoms.file_ref_payload(ref)
    assert payload["proof"]["execution"] == "confirmed"
    assert verdict._rel_write(ledger, verdict.resolve_node(ledger, f"agent:{owner.id}@v1"),
                              verdict.resolve_node(ledger, f"file:{TARGET}@v1"))[0] == "true"


@pytest.mark.parametrize("mode", ["cc", "codex"])
def test_helper_keyword_shape_is_not_proof_of_reached_same_file_edit(tmp_path, mode):
    command = script("def rep(p, pairs):\n    return\n    s=open(p).read()\n    for old,new in pairs:\n"
                     "        s=s.replace(old,new)\n    open(p,'w').write(s)\nrep('Example.ets',[('seed','bad')])")
    ledger, owner = build(tmp_path, mode, [(command, "")], seed=True)
    action = owner.actions[1]
    assert not action.files and action.ver is None
    assert ledger.stories[TARGET].versions[-1].content == "seed\n"


def test_unversioned_dependency_read_never_becomes_an_agent_write(tmp_path):
    ledger, owner = build(tmp_path, "cc", [(script("s=open('Example.ets').read()\nprint(len(s))"), "4")])
    assert owner.actions[0].files[0].op == "read" and owner.actions[0].files[0].v is None
    payload = atoms.agent_atom(ledger, owner.id)
    assert all(row["op"] != "read" for row in payload["writes"])


@pytest.mark.parametrize("mode", ["cc", "codex"])
@pytest.mark.parametrize("body", [
    "open('Example.ets','a').write('tail')",
    "open('Example.ets','r+').write('prefix')",
    "with open('Example.ets','w') as f:\n    f.write('a')\n    f.write('b')",
    "s=open('Example.ets').read()\ns=s.replace('seed','new',0)\nopen('Example.ets','w').write(s)",
    "s=open('Example.ets').read()\ns=s.replace('seed','new',2)\nopen('Example.ets','w').write(s)",
])
def test_unsupported_snapshot_semantics_keep_write_but_not_fabricated_full_state(tmp_path, mode, body):
    ledger, owner = build(tmp_path, mode, [(script(body), "")], seed=True)
    versions = ledger.stories[TARGET].versions
    assert len(versions) == 2
    assert versions[-1].content is None
    assert versions[-1].proof.execution == "confirmed"
    assert owner.actions[1].ver == 2
    assert verdict._rel_write(ledger, verdict.resolve_node(ledger, f"agent:{owner.id}@v2"),
                              verdict.resolve_node(ledger, f"file:{TARGET}@v2"))[0] == "true"


@pytest.mark.parametrize("updates,expected", [
    ({}, "read"), ({"dep": True}, "dependency_read"),
    ({"observation_uncertain": True}, "overlapping_read"),
    ({"certain": False}, "uncertain_version"),
    ({"proof": None}, "unverified_read"),
    ({"proof": {"operation_basis": "supported_python", "execution": "unknown", "delivery": "content"}}, "unverified_read"),
    ({"proof": {"operation_basis": "native_tool", "execution": "confirmed", "delivery": "metadata"}}, "unverified_read"),
])
def test_read_basis_keeps_operation_observation_and_binding_independent(updates, expected):
    payload = {"certain": True, "dep": False, "observation_uncertain": False,
               "proof": {"operation_basis": "native_tool", "execution": "confirmed", "delivery": "content"}}
    payload.update(updates)
    assert read_basis(payload) == expected


def test_file_fact_proof_is_identity_bearing(tmp_path):
    original, owner = build(tmp_path, "cc", [(script("open('Example.ets','w').write('known')"), "")])
    left = atoms.Ledger(deepcopy(original.stories), deepcopy(original.agents))
    right = atoms.Ledger(deepcopy(original.stories), deepcopy(original.agents))
    ref = right.agents[owner.id].actions[0].files[0]
    ref.ev = replace(ref.ev, proof=replace(ref.proof, execution="unknown"))
    assert atoms.ledger_identity(left) != atoms.ledger_identity(right)
    assert atoms.ledger_identity(left).startswith("atoms-2026-09-09-file-evidence5:")


def test_unknown_legacy_proof_cannot_certify_a_write(tmp_path):
    ledger, owner = build(tmp_path, "cc", [(script("open('Example.ets','w').write('known')"), "")])
    ledger.stories[TARGET].versions[0].proof = None
    result = verdict._rel_write(ledger, verdict.resolve_node(ledger, f"agent:{owner.id}@v1"),
                                verdict.resolve_node(ledger, f"file:{TARGET}@v1"))
    assert result[0] == "unknown"


@pytest.mark.parametrize("mode", ["cc", "codex"])
def test_reread_clears_previous_file_edit_lineage(tmp_path, mode):
    body = "s=open('Example.ets').read()\ns=s.replace('seed','bad')\ns=open('Other.ets').read()\nopen('Other.ets','w').write(s)"
    ledger, owner = build(tmp_path, mode, [(script(body), "")], seed=True)
    assert not any(ref.op == "write" and ref.path == "/proj/Other.ets" for ref in owner.actions[1].files)
    assert not ledger.stories["/proj/Other.ets"].versions
    parsed = atoms_collect._py_script_ops(body, "/proj").ops
    assert not any(op.op == "edit" or op.old is not None or op.new is not None for op in parsed)


@pytest.mark.parametrize("mode", ["cc", "codex"])
@pytest.mark.parametrize("binding", ["rep=print", "def rep(*args): pass"])
def test_helper_capability_expires_when_name_rebound(tmp_path, mode, binding):
    body = ("def rep(p,pairs):\n    s=open(p).read()\n    for old,new in pairs:\n"
            "        s=s.replace(old,new)\n    open(p,'w').write(s)\n" + binding
            + "\nrep('Example.ets',[('seed','bad')])")
    ledger, owner = build(tmp_path, mode, [(script(body), "")], seed=True)
    assert not owner.actions[1].files
    assert ledger.stories[TARGET].versions[-1].content == "seed\n"


@pytest.mark.parametrize("mode", ["cc", "codex"])
@pytest.mark.parametrize("assignment", ["(p,)=('Other.ets',)", "p=q='Other.ets'"])
def test_unsupported_assignment_never_reuses_previous_path_binding(tmp_path, mode, assignment):
    body = "p='Example.ets'\n" + assignment + "\nopen(p,'w').write('bad')"
    ledger, owner = build(tmp_path, mode, [(script(body), "")], seed=True)
    assert not owner.actions[1].files
    assert ledger.stories[TARGET].versions[-1].content == "seed\n"


@pytest.mark.parametrize("mode", ["cc", "codex"])
def test_path_instance_open_uses_receiver_path_and_mode(tmp_path, mode):
    ledger, owner = build(tmp_path, mode, [(script("from pathlib import Path\nPath('Example.ets').open('w').write('known')"), "")])
    assert "/proj/w" not in ledger.stories
    assert ledger.stories[TARGET].versions[0].content == "known"


@pytest.mark.parametrize("separator", [" || ", " | ", "; "])
@pytest.mark.parametrize("mode", ["cc", "codex"])
def test_composite_shell_success_does_not_certify_masked_prior_effect(tmp_path, mode, separator):
    ledger, owner = build(tmp_path, mode, [("cp missing.txt Example.ets" + separator + "true", "")])
    assert not owner.actions[0].files
    assert TARGET in owner.actions[0].detail["effect_candidates"]


def test_no_sidecar_read_gaps_are_partial_observations_not_full_snapshot(tmp_path):
    rows = _call("2026-01-01T00:00:00Z", "read", "Read", {"file_path": TARGET}, "1\tone\n3\tthree\n... truncated ...")
    ledger = _ledger(tmp_path, rows)
    ref = next(iter(ledger.agents.values())).actions[0].files[0]
    assert ref.proof.snapshot == "partial" and not ref.ev.full
    assert ref.ev.seen == ((1, "one"), (3, "three"))
    assert all(v.content is None for v in ledger.stories[TARGET].versions)


def test_missing_read_binding_record_defaults_to_uncertain(tmp_path, monkeypatch):
    original = atoms.build_stories

    def without_read_binding(events):
        stories = original(events)
        for story in stories.values():
            story.reads.clear()
        return stories

    monkeypatch.setattr(atoms, "build_stories", without_read_binding)
    rows = _call("2026-01-01T00:00:00Z", "read", "Read", {"file_path": TARGET}, "1\tone")
    ledger = _ledger(tmp_path, rows)
    ref = next(iter(ledger.agents.values())).actions[0].files[0]
    assert ref.certain is False


@pytest.mark.parametrize("mode", ["cc", "codex"])
def test_pure_and_success_still_confirms_every_simple_segment(tmp_path, mode):
    ledger, owner = build(tmp_path, mode, [("cp existing.txt Example.ets && true", "")])
    assert ledger.stories[TARGET].versions[0].proof.execution == "confirmed"
    assert any(ref.op == "write" for ref in owner.actions[0].files)
