"""Follow-up contract checks for c76519b. Commands are inert transcript strings.

This file adds no implementation changes. Fixtures are isolated pytest data.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
from migloop import atoms, atoms_collect, atoms_text, probe
from tests.test_atoms import MAIN_ID, SID, _call, _ledger, _read_call, _rec, _res, _use

A = "/proj/entry/A.ets"
Z = "/proj/entry/Z.ets"


def at(seconds):
    return f"2026-01-01T00:00:{seconds:02d}Z"


def body(path=A, new="b"):
    return f"p='{path}'\ns=open(p).read()\nopen(p,'w').write(s.replace('a','{new}'))\n"


def checker():
    spec = importlib.util.spec_from_file_location(
        "review_c765_cites", REPO / "docs/experiments/2026-09-07-six-cases/cite_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("cmd", [
    f"false && echo skipped && cat > {A} <<'EOF'\nb\nEOF\ntrue",
    "false && python3 <<'PY'\n" + body() + "PY\ntrue",
])
def test_skipped_branch_remains_candidate_across_shell_shapes(tmp_path, cmd):
    led = _ledger(tmp_path, [
        *_call(at(0), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(10), "c1", "Bash", {"command": cmd}, out=""),
    ])
    assert len(led.stories[A].versions) == 1, [
        (v.content, v.source, v.conditional) for v in led.stories[A].versions
    ]


def test_skipped_conditional_cat_does_not_become_input(tmp_path):
    spec = "/proj/spec/not_read.md"
    led = _ledger(tmp_path, [
        *_call(at(0), "c1", "Bash", {"command": f"false && cat {spec}; true"}, out=""),
        *_call(at(10), "w1", "Write", {"file_path": A, "content": "a\n"}),
    ])
    call = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    assert not any(f.op == "read" and f.path == spec for f in call.files), {
        "read_files": [(f.path, f.v, f.certain) for f in call.files],
        "agent": atoms_text.render_agent(led, MAIN_ID, 1, root="/proj"),
    }


@pytest.mark.parametrize("join", [";", "||"])
def test_unattributed_stdout_does_not_prove_a_skipped_read(tmp_path, join):
    led = _ledger(tmp_path, [*_call(at(0), "c", "Bash", {
        "command": f"false && cat {A} {join} echo other_output"
    }, out="other_output\n")])
    action = led.agents[MAIN_ID].actions[0]
    assert not any(f.op == "read" and f.path == A for f in action.files)
    assert A in action.detail["conditional_reads"]


def test_candidate_between_opaque_write_and_snapshot_blocks_old_authorship(tmp_path):
    opaque = "agent-a1111111"
    candidate = "agent-b2222222"
    led = _ledger(tmp_path, [
        *_call(at(0), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_read_call(at(30), "r1", A, "b\n"),
    ], {
        opaque: [*_call(at(10), "o1", "Bash", {"command": f"cp /tmp/unknown.ets {A}"})],
        candidate: [*_call(at(20), "c1", "Bash", {
            "command": f"test -f /tmp/flag && cat > {A} <<'EOF'\nb\nEOF\ntrue"
        })],
    })
    old = led.stories[A].versions[1]
    assert led.stories[A].touches            # 这个案例必须实际产生候选写,不能靠证明分支执行绕过屏障
    assert not (old.sealed and old.by == opaque and old.content == "b\n"), {
        "versions": [(v.v, v.by, v.content, v.sealed) for v in led.stories[A].versions],
        "candidates": [(t.by, t.reason) for t in led.stories[A].touches],
        "read_binding": [(r.version, r.certain) for r in led.stories[A].reads],
    }


def test_script_edit_is_not_applied_twice_by_prescan_and_walk(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(5), "s1", "Write", {"file_path": "/tmp/fix.py", "content": body("/proj/A.ets")}),
        *_call(at(10), "s2", "Edit", {
            "file_path": "/tmp/fix.py", "old_string": "/proj/", "new_string": "/proj/entry/"
        }),
        *_call(at(20), "c1", "Bash", {"command": "python3 /tmp/fix.py"}),
    ])
    assert led.stories[A].versions[-1].content == "b\n", {
        p: [v.content for v in st.versions] for p, st in led.stories.items() if p.endswith(".ets")
    }


def test_opaque_script_overwrite_invalidates_previously_known_body(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(5), "s1", "Write", {"file_path": "/tmp/fix.py", "content": body()}),
        *_call(at(10), "c1", "Bash", {"command": "cp /tmp/new.py /tmp/fix.py"}),
        *_call(at(20), "c2", "Bash", {"command": "python3 /tmp/fix.py"}),
    ])
    assert len(led.stories[A].versions) == 1, [
        (v.content, v.source) for v in led.stories[A].versions
    ]


def test_explicit_unknown_script_path_does_not_borrow_another_file(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(5), "s1", "Write", {"file_path": "/tmp/known/fix.py", "content": body()}),
        *_call(at(20), "c1", "Bash", {"command": "python3 /tmp/other/fix.py"}),
    ])
    assert len(led.stories[A].versions) == 1, [
        (v.content, v.source) for v in led.stories[A].versions
    ]


def test_missing_block_is_not_reinterpreted_as_another_call_drift(tmp_path):
    led = _ledger(tmp_path, [
        _rec(at(0), "assistant", [
            _use("w1", "Write", {"file_path": A, "content": "a\n"}),
            _use("w2", "Write", {"file_path": Z, "content": "z\n"}),
        ]),
        _rec(at(1), "user", [_res("w1"), _res("w2")]),
    ])
    first, second = [a for a in led.agents[MAIN_ID].actions if a.tool == "Write"]
    full = atoms_text._core(second.seq, led.locs[second.seq])
    shortened = full.replace("/1", "")
    nodes, bad = probe._link_nodes(led, shortened)
    mod = checker()
    result = mod.check_report(led, mod.Pool([str(tmp_path / f"{SID}.jsonl")]), shortened)
    assert bad or not nodes, {"full": full, "shortened": shortened, "resolved": nodes,
                              "first_call": first.seq, "second_call": second.seq, "checker": result}


def test_untagged_reference_does_not_get_strong_ok_status(tmp_path):
    led = _ledger(tmp_path, [*_call(at(0), "w1", "Write", {"file_path": A, "content": "a\n"})])
    action = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Write")
    hit, status = atoms.resolve_ref(led, action.seq, led.lines[action.seq], 0, None)
    assert status == "untagged", {"resolved": hit, "status": status}


def test_scan_truncation_of_assistant_text_is_disclosed(tmp_path):
    text = "pad " * (atoms_collect._SCAN_LIMIT // 4 + 3) + A
    led = _ledger(tmp_path, [
        *_call(at(0), "w1", "Write", {"file_path": A, "content": "a\n"}),
        _rec(at(10), "assistant", [{"type": "text", "text": text}]),
    ])
    action = next(a for a in led.agents[MAIN_ID].actions if a.kind == "say")
    assert action.detail.get("mentions_scan_truncated", 0) > 0, {
        "input_chars": len(text), "scan_budget": atoms_collect._SCAN_LIMIT,
        "detail_keys": list(action.detail), "mentions": len(action.detail.get("mentions", [])),
    }


def test_toolu_id_in_non_tool_metadata_is_not_tool_use_definition(tmp_path):
    fake_id = "toolu_NOTAREALCALL1234"
    led = _ledger(tmp_path, [_rec(at(0), "user", "hello", metadata={"id": fake_id})])
    mod = checker()
    result = mod.check_report(led, mod.Pool([str(tmp_path / f"{SID}.jsonl")]), fake_id)
    assert result["invalid"] == 1, result


def test_control_simple_skipped_write_is_only_candidate(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "w1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(10), "c1", "Bash", {"command": f"false && cp /tmp/x.ets {A}; true"}),
        *_read_call(at(20), "r1", A, "a\n"),
    ])
    assert len(led.stories[A].versions) == 1 and not led.stories[A].breaks
    assert led.stories[A].touches


def test_control_complete_block_reference_resolves(tmp_path):
    led = _ledger(tmp_path, [
        _rec(at(0), "assistant", [
            _use("w1", "Write", {"file_path": A, "content": "a\n"}),
            _use("w2", "Write", {"file_path": Z, "content": "z\n"}),
        ]),
        _rec(at(1), "user", [_res("w1"), _res("w2")]),
    ])
    second = [a for a in led.agents[MAIN_ID].actions if a.tool == "Write"][1]
    nodes, bad = probe._link_nodes(led, atoms_text._core(second.seq, led.locs[second.seq]))
    assert not bad and [n["action"] for n in nodes] == [second.seq]


@pytest.mark.parametrize("cmd", [
    f"cd /missing && cat > {A} <<'EOF'\nb\nEOF\ntrue",
    f"false && true && cp /tmp/x.ets {A}; true",
    f"false || false && cp /tmp/x.ets {A}; true",
    f"false && (cp /tmp/x.ets {A}); true",
    f"false && {{ cp /tmp/x.ets {A}; }}; true",
    f"if false; then cp /tmp/x.ets {A}; fi; true",
])
def test_success_of_later_statement_does_not_prove_earlier_branch(tmp_path, cmd):
    led = _ledger(tmp_path, [
        *_call(at(0), "w", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(10), "c", "Bash", {"command": cmd}, out=""),
        *_read_call(at(20), "r", A, "a\n"),
    ])
    assert len(led.stories[A].versions) == 1 and led.stories[A].touches


@pytest.mark.parametrize("failure", [True, False])
def test_failed_or_unfinished_tool_write_also_blocks_old_sealing(tmp_path, failure):
    suspect = _call(at(20), "bad", "Write", {"file_path": A, "content": "b\n"}, is_error=True)
    if not failure:
        suspect = suspect[:1]
    led = _ledger(tmp_path, [
        *_call(at(0), "w", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(10), "opaque", "Bash", {"command": f"cp /tmp/x.ets {A}"}),
        *suspect,
        *_read_call(at(30), "r", A, "b\n"),
    ])
    assert led.stories[A].versions[1].content is None
    assert not led.stories[A].versions[1].sealed
    assert led.stories[A].versions[-1].by == atoms.OUTBAND


def test_candidate_gap_propagates_to_diff_and_line_origins(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "w", "Write", {"file_path": A, "content": "same\na\n"}),
        *_call(at(10), "c", "Bash", {"command": f"test -f /tmp/flag && cp /tmp/x.ets {A}; true"}),
        *_call(at(20), "w2", "Write", {"file_path": A, "content": "same\nb\n"}),
    ])
    st = led.stories[A]
    assert st.versions[-1].diff_kind == "unknown" and st.versions[-1].state_gap
    origins = atoms.line_origins(st)[-1]
    assert origins[0][-1] == "bridged"         # 同文也不能假装中间没有不确定区间


@pytest.mark.parametrize("cmd", ["cp /tmp/new.py /tmp/fix.py", "rm /tmp/fix.py"])
def test_failed_script_mutation_invalidates_old_body(tmp_path, cmd):
    led = _ledger(tmp_path, [
        *_call(at(0), "w", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(5), "s", "Write", {"file_path": "/tmp/fix.py", "content": body()}),
        *_call(at(10), "bad", "Bash", {"command": cmd}, is_error=True),
        *_call(at(20), "run", "Bash", {"command": "python3 /tmp/fix.py"}),
    ])
    assert len(led.stories[A].versions) == 1


def test_script_multiedit_replays_once_in_order_and_honors_replace_all(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "w", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(5), "s", "Write", {"file_path": "/tmp/fix.py", "content": body("/proj/A.ets")}),
        *_call(at(10), "e", "MultiEdit", {"file_path": "/tmp/fix.py", "edits": [
            {"old_string": "/proj/", "new_string": "/proj/entry/", "replace_all": True},
            {"old_string": "'b'", "new_string": "'c'"},
        ]}),
        *_call(at(20), "run", "Bash", {"command": "python3 /tmp/fix.py"}),
    ])
    assert led.stories[A].versions[-1].content == "c\n"


def test_relative_script_name_does_not_borrow_from_different_cwd(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "w", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(5), "s", "Write", {"file_path": "/tmp/fix.py", "content": body()}),
        *_call(at(20), "run", "Bash", {"command": "python3 fix.py"}),
    ])
    assert len(led.stories[A].versions) == 1


def test_script_body_is_not_available_before_write_completes(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "w", "Write", {"file_path": A, "content": "a\n"}),
        _rec(at(5), "assistant", [_use("s", "Write", {"file_path": "/tmp/fix.py", "content": body()})]),
        *_call(at(10), "run", "Bash", {"command": "python3 /tmp/fix.py"}),
        _rec(at(20), "user", [_res("s")]),
    ])
    assert len(led.stories[A].versions) == 1


def test_script_time_lookup_normalizes_fractional_seconds():
    scripts = atoms_collect.ScriptTable()
    scripts.put("/tmp/fix.py", "2026-01-01T00:00:01.500Z", "late")
    assert scripts.body("/tmp/fix.py", "2026-01-01T00:00:01Z") is None


def test_mixed_record_citations_and_fallback_ids_are_distinct(tmp_path):
    led = _ledger(tmp_path, [
        _rec(at(0), "assistant", [
            {"type": "thinking", "thinking": "plan"},
            {"type": "text", "text": "do it"},
            _use("w", "Write", {"file_path": A, "content": "a\n"}),
        ]),
        _rec(at(1), "user", [_res("w")]),
    ])
    actions = led.agents[MAIN_ID].actions
    assert len({atoms.event_id(led, MAIN_ID, a.seq) for a in actions}) == len(actions)
    assert not led.loc_ambiguous
    for action in actions:
        ref = atoms_text._core(action.seq, led.locs[action.seq])
        nodes, bad = probe._link_nodes(led, ref)
        assert not bad and [n["action"] for n in nodes] == [action.seq]


@pytest.mark.parametrize("tool,inp", [
    ("Write", {"file_path": Z, "content": "pad " * 30 + A}),
    ("Edit", {"file_path": Z, "old_string": "z", "new_string": "pad " * 30 + A}),
    ("MultiEdit", {"file_path": Z, "edits": [{"old_string": "z", "new_string": "pad " * 30 + A}]}),
    ("Agent", {"prompt": "pad " * 30 + A}),
    ("SendMessage", {"to": "x", "message": "pad " * 30 + A}),
])
def test_all_input_scan_limits_are_visible_and_raw_input_is_recoverable(tmp_path, monkeypatch, tool, inp):
    monkeypatch.setattr(atoms_collect, "_SCAN_LIMIT", 64)
    led = _ledger(tmp_path, [*_call(at(0), "t", tool, inp)])
    action = next(a for a in led.agents[MAIN_ID].actions if a.tool == tool)
    assert action.detail["mentions_scan_truncated"] > 0 and led.scan_gaps
    assert "scan" in atoms_text.render_index(led)
    assert str(action.seq) in atoms_text.render_index(led, kind="scan")
    assert "scan" in atoms_text.render_file(led, A)       # 没有文件入口也必须提示未扫描区
    assert A in atoms_text.render_action(led, MAIN_ID, action.seq, part="input", find=A, max_chars=512)


@pytest.mark.parametrize("block", [
    {"type": "thinking", "thinking": "pad " * 30 + A},
    {"type": "text", "text": "pad " * 30 + A},
])
def test_text_scan_limits_reach_agent_and_search_responses(tmp_path, monkeypatch, block):
    monkeypatch.setattr(atoms_collect, "_SCAN_LIMIT", 64)
    led = _ledger(tmp_path, [_rec(at(0), "assistant", [block])])
    assert led.scan_gaps
    assert "scan" in atoms_text.render_agent(led, MAIN_ID)
    assert "scan" in atoms_text.render_search(led, A, agent=MAIN_ID)


def test_codex_shell_conditions_share_the_same_candidate_contract():
    import json
    cmd = f"false && cp /tmp/x.ets {A}; true"
    js = "const r = await tools.exec_command(" + json.dumps({"cmd": cmd, "workdir": "/proj"}) + ");"
    ops, detail, ok = atoms_collect._codex_exec_ops(js, "Script completed\nOutput:\n" + json.dumps({"exit_code": 0, "output": ""}), "/proj", {})
    assert ok and A in detail["conditional"]
    assert not any(o.path == A and o.op != "read" for o in ops)


def test_pool_shares_script_history_across_root_sessions(tmp_path):
    import json
    from migloop import service
    first = tmp_path / "11111111-0000-0000-0000-000000000000.jsonl"
    second = tmp_path / "22222222-0000-0000-0000-000000000000.jsonl"
    first.write_text("\n".join(json.dumps(r) for r in _call(at(5), "s", "Write", {
        "file_path": "/tmp/fix.py", "content": body()
    })), encoding="utf-8")
    second.write_text("\n".join(json.dumps(r) for r in [
        *_call(at(0), "w", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at(20), "run", "Bash", {"command": "python3 /tmp/fix.py"}),
    ]), encoding="utf-8")
    for roots in ([str(first), str(second)], [str(second), str(first)]):
        led = service._collect("claude", roots)
        assert led.stories[A].versions[-1].content == "b\n"


def test_overlapping_script_writes_leave_body_unknown_after_both_complete(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "w", "Write", {"file_path": A, "content": "a\n"}),
        _rec(at(5), "assistant", [_use("s1", "Write", {"file_path": "/tmp/fix.py", "content": body()})]),
        _rec(at(10), "assistant", [_use("s2", "Write", {"file_path": "/tmp/fix.py", "content": body(new="c")})]),
        _rec(at(20), "user", [_res("s2")]),
        _rec(at(30), "user", [_res("s1")]),
        *_call(at(40), "run", "Bash", {"command": "python3 /tmp/fix.py"}),
    ])
    assert len(led.stories[A].versions) == 1


def test_mention_count_limit_is_also_exposed(tmp_path, monkeypatch):
    monkeypatch.setattr(atoms_collect, "_MENTION_CAP", 2)
    led = _ledger(tmp_path, [_rec(at(0), "assistant", [{"type": "text", "text": "a.ets b.ets c.ets"}])])
    assert led.scan_gaps[0]["mentions"] == 1
    assert "scan" in atoms_text.render_agent(led, MAIN_ID)


def test_cite_checker_accepts_real_tool_use_definition(tmp_path):
    real = "toolu_REALCALL123456"
    led = _ledger(tmp_path, [*_call(at(0), real, "Write", {"file_path": A, "content": "a\n"})])
    mod = checker()
    report = mod.check_report(led, mod.Pool([str(tmp_path / f"{SID}.jsonl")]), real)
    assert report["valid"] == 1 and report["invalid"] == 0


def test_candidate_before_first_known_write_is_not_proof_of_creation(tmp_path):
    led = _ledger(tmp_path, [
        *_call(at(0), "c", "Bash", {"command": f"false && cp /tmp/x.ets {A}; true"}),
        *_call(at(10), "w", "Write", {"file_path": A, "content": "a\n"}),
    ])
    assert led.stories[A].versions[0].diff_kind == "unknown"
