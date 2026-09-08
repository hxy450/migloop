"""Independent acceptance counterexamples for migloop aa277bb.

All commands below are synthetic transcript strings. None are executed.
Only pytest fixture transcripts are written; migloop source is not modified.
Run with PYTHONPATH pointing at migloop/src and migloop repository root.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(r"C:\Users\hongy\projects\migloop")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from migloop import atoms, atoms_collect, atoms_text, probe, service
from tests.test_atoms import MAIN_ID, SID, _call, _ledger, _read_call, _rec, _res, _use

A = "/proj/entry/A.ets"
Z = "/proj/entry/Z.ets"


def at(hms: str) -> str:
    return f"2026-01-01T{hms}Z"


def load_experiment(name: str):
    spec = importlib.util.spec_from_file_location(
        f"review_{name}", REPO / "docs/experiments/2026-09-07-six-cases" / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def script_body(path=A, old="a", new="b"):
    return f"p='{path}'\ns=open(p).read()\nopen(p,'w').write(s.replace('{old}','{new}'))\n"


def test_control_unconditional_write_matches_observation(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "c1", "Bash", {"command": f"cat > {A} <<'EOF'\nb\nEOF"}),
        *_read_call(at("00:00:20"), "r1", A, "b\n"),
    ])
    assert [v.content for v in led.stories[A].versions] == ["a\n", "b\n"]
    assert not led.stories[A].breaks


def test_control_single_hex_reference_resolves(tmp_path):
    led = _ledger(tmp_path, [*_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"})])
    action = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Write")
    nodes, bad = probe._link_nodes(led, f"#{action.seq}@L{led.locs[action.seq]}")
    assert not bad and [n["action"] for n in nodes] == [action.seq]


def test_skipped_conditional_write_cannot_create_outband_repair(tmp_path):
    main = [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "c1", "Bash", {
            "command": f"false && cat > {A} <<'EOF'\nb\nEOF\ntrue"
        }),
        *_read_call(at("00:00:20"), "r1", A, "a\n"),
    ]
    led = _ledger(tmp_path, main)
    st = led.stories[A]
    got = [(v.v, v.content, v.source, v.conditional) for v in st.versions]
    assert not any(v.source == "outband" for v in st.versions), got


def test_reference_distinguishes_two_calls_in_one_jsonl_record(tmp_path):
    main = [
        _rec(at("00:00:00"), "assistant", [
            _use("w1", "Write", {"file_path": A, "content": "a\n"}),
            _use("w2", "Write", {"file_path": Z, "content": "z\n"}),
        ]),
        _rec(at("00:00:01"), "user", [_res("w1"), _res("w2")]),
    ]
    led = _ledger(tmp_path, main)
    w1, w2 = [a for a in led.agents[MAIN_ID].actions if a.tool == "Write"]
    citation = f"#{w2.seq}@L{led.locs[w2.seq]}"
    nodes, bad = probe._link_nodes(led, citation)
    cite = load_experiment("cite_check")
    result = cite.check_report(led, cite.Pool([str(tmp_path / f"{SID}.jsonl")]), citation)
    assert [n.get("action") for n in nodes] == [w2.seq], {
        "first_call": w1.seq, "second_call": w2.seq,
        "citation": citation, "resolved": nodes, "bad": bad, "checker": result,
    }


def test_failed_script_write_not_used_as_executed_body(tmp_path):
    main = [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "s1", "Write", {
            "file_path": "/tmp/fix.py", "content": script_body()
        }, out="Permission denied", is_error=True),
        *_call(at("00:00:20"), "c1", "Bash", {"command": "python3 /tmp/fix.py"}),
    ]
    led = _ledger(tmp_path, main)
    assert len(led.stories[A].versions) == 1, [
        (v.content, v.source, v.by) for v in led.stories[A].versions
    ]


def test_generated_reference_accepts_real_named_transcript_tags(tmp_path):
    sub_id = "agent-aconv-apploaddlg-8ea392b08bb155da"
    led = _ledger(tmp_path, [], {sub_id: [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"})
    ]})
    action = next(a for a in led.agents[sub_id].actions if a.tool == "Write")
    citation = f"#{action.seq}@L{led.locs[action.seq]}"
    nodes, bad = probe._link_nodes(led, citation)
    assert not bad and any(n.get("action") == action.seq for n in nodes), {
        "citation": citation, "bad": bad, "resolved": nodes,
    }


def test_short_tag_does_not_alias_distinct_transcripts(tmp_path):
    subs = {}
    for i, sub_id in enumerate(("agent-1234abcd11111111", "agent-1234abcd22222222")):
        subs[sub_id] = [*_call(at(f"00:00:{i * 10:02d}"), f"w{i}", "Write", {
            "file_path": A, "content": f"{i}\n"
        })]
    led = _ledger(tmp_path, [], subs)
    actions = [a for aid in subs for a in led.agents[aid].actions if a.tool == "Write"]
    refs = [led.locs[a.seq] for a in actions]
    assert len(set(refs)) == len(actions), refs


def test_subagent_script_edit_applies_to_later_main_run(tmp_path):
    old, new = script_body(new="b"), script_body(new="c")
    main = [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:02"), "s1", "Write", {"file_path": "/tmp/fix.py", "content": old}),
        *_call(at("00:00:04"), "d1", "Agent", {"name": "editor", "prompt": "edit script"},
               toolUseResult={"agentId": "e"}),
        *_call(at("00:00:20"), "c1", "Bash", {"command": "python3 /tmp/fix.py"}),
    ]
    sub = [*_call(at("00:00:10"), "s2", "Edit", {
        "file_path": "/tmp/fix.py", "old_string": old, "new_string": new
    })]
    led = _ledger(tmp_path, main, {"agent-e": sub})
    assert led.stories[A].versions[-1].content == "c\n", [
        (v.content, v.source) for v in led.stories[A].versions
    ]


def test_script_lookup_prefers_exact_path_over_basename(tmp_path):
    main = [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:02"), "w2", "Write", {"file_path": Z, "content": "z\n"}),
        *_call(at("00:00:04"), "s1", "Write", {
            "file_path": "/tmp/one/fix.py", "content": script_body()
        }),
        *_call(at("00:00:06"), "s2", "Write", {
            "file_path": "/tmp/two/fix.py", "content": script_body(Z, "z", "q")
        }),
        *_call(at("00:00:20"), "c1", "Bash", {"command": "python3 /tmp/one/fix.py"}),
    ]
    led = _ledger(tmp_path, main)
    got = {p: [v.content for v in led.stories[p].versions] for p in (A, Z)}
    assert led.stories[A].versions[-1].content == "b\n", got


@pytest.mark.parametrize("command", [
    "find /proj/entry -name A.ets -delete",
    "git -C /proj restore entry/A.ets",
])
def test_write_capable_commands_not_folded_readonly(tmp_path, command):
    led = _ledger(tmp_path, [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "c1", "Bash", {"command": command}),
    ])
    call = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    classes = [m.cls for m in led.mentions.get(A, []) if m.seq == call.seq]
    rows = atoms.search_window_writes(led, None, at("00:01:00"))["rows"]
    assert classes and "readonly" not in classes and any(r["seq"] == call.seq for r in rows), {
        "command": command, "classes": classes, "write_window": rows,
    }


def test_output_beyond_20k_is_indexed_or_disclosed(tmp_path):
    output = "x" * 20010 + "\n M entry/A.ets\n"
    led = _ledger(tmp_path, [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "c1", "Bash", {"command": "git status --short"}, out=output),
    ])
    call = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    mentions = [m for m in led.mentions.get(A, []) if m.seq == call.seq]
    assert mentions or call.detail.get("mentions_truncated"), call.detail


def test_path_after_40_other_paths_remains_in_file_index(tmp_path):
    command = "inspect " + " ".join(f"/proj/x/f{i}.ets" for i in range(45)) + " " + A
    led = _ledger(tmp_path, [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "c1", "Bash", {"command": command}),
    ])
    call = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    assert any(m.seq == call.seq for m in led.mentions.get(A, [])), {
        "collected": len(call.detail.get("mentions", [])),
        "truncated": call.detail.get("mentions_truncated"),
        "file_mentions": len(led.mentions.get(A, [])),
    }


def test_lexical_coverage_does_not_credit_unrelated_adjacent_record(tmp_path):
    main = [
        {"type": "file-history-snapshot", "timestamp": at("00:00:00"), "path": A},
        *_call(at("00:00:10"), "w1", "Write", {"file_path": A, "content": "a\n"}),
    ]
    led = _ledger(tmp_path, main)
    mod = load_experiment("lexical_gap")
    capture = io.StringIO()
    with patch.object(sys, "argv", ["lexical_gap", SID, "A.ets"]), \
         patch.object(service, "locate_session", return_value=str(tmp_path / f"{SID}.jsonl")), \
         patch.object(service, "session_ledger", return_value=led), \
         patch.object(service, "extract_trace", return_value={"meta": {"cwd": "/proj"}}), \
         patch.object(service, "prior_roots", return_value=[]), \
         contextlib.redirect_stdout(capture):
        mod.main()
    assert "差集 1" in capture.getvalue(), capture.getvalue()


def test_citation_checker_rejects_zero_line_and_zero_version(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"}),
    ])
    mod = load_experiment("cite_check")
    result = mod.check_report(led, mod.Pool([str(tmp_path / f"{SID}.jsonl")]),
                              f"{SID}.jsonl:0 A.ets@v0")
    assert result["invalid"] == 2, result


def test_rebuilt_ledger_search_does_not_use_stale_transcript_cache(tmp_path):
    first = [*_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"})]
    led = _ledger(tmp_path, first)
    atoms.search_agent(led, MAIN_ID, "new_marker_983")
    second = first + [_rec(at("00:00:10"), "assistant", [{"type": "text", "text": "new_marker_983"}])]
    led = _ledger(tmp_path, second)
    result = atoms.search_agent(led, MAIN_ID, "new_marker_983")
    assert result["hits"], result
