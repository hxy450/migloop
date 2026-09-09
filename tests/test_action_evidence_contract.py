"""Raw evidence and navigation must retain the same uncertainty as atom views."""
from __future__ import annotations

from dataclasses import replace
import json
import re
import pytest

from migloop import atoms, atoms_text, verdict
from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call


def test_default_action_keeps_both_bodies_when_they_fit_total_budget(tmp_path):
    marker = "BRANCH_EXCEPTION_MUST_SURVIVE"
    command = "x" * 1900 + marker + "z" * 950
    led = _ledger(tmp_path, _call("2026-01-01T00:00:00Z", "shell", "Bash",
                                 {"command": command}, "y" * 1500))
    seq = led.agents[MAIN_ID].actions[0].seq
    text = atoms_text.render_action(led, MAIN_ID, seq, max_chars=5000, m_n=0)
    assert command in text and "y" * 1500 in text
    assert "截断" not in text


def test_default_action_exposes_each_partial_body_and_how_to_resume(tmp_path):
    led = _ledger(tmp_path, _call("2026-01-01T00:00:00Z", "shell", "Bash",
                                 {"command": "x" * 4000}, "y" * 4000))
    seq = led.agents[MAIN_ID].actions[0].seq
    text = atoms_text.render_action(led, MAIN_ID, seq, max_chars=1000, m_n=0)
    assert "part=input" in text and "part=output" in text
    assert text.count("offset=") >= 2
    bodies = re.findall(r"```\n(.*?)\n```", text, re.S)
    assert len(bodies) == 2 and sum(map(len, bodies)) <= 1000


def test_action_links_keep_read_scope_and_uncertain_dependency_flags(tmp_path):
    led = _ledger(tmp_path, [*_call("2026-01-01T00:00:00Z", "w", "Write", {
        "file_path": "/proj/A.ets", "content": "old"}),
        *_read_call("2026-01-01T00:00:02Z", "r", "/proj/A.ets", "old")])
    action = led.agents[MAIN_ID].actions[-1]
    ref = action.files[0]
    ref.certain = False
    ref.ev = replace(ref.ev, dep=True, full=False, start=7, n=1, seen=((7, "old"),))
    row = atoms.action_links(led, MAIN_ID, action.seq)["files"][0]
    assert row["certain"] is False and row["dep"] is True
    assert row["full"] is False and row["start"] == 7 and row["n"] == 1
    assert row["seen"] == [[7, "old"]]
    text = atoms_text.render_action(led, MAIN_ID, action.seq, m_n=0)
    assert "依赖读" in text and "不确定" in text and "7-7行" in text


def test_search_navigation_targets_only_include_displayed_hits(tmp_path):
    records = []
    for index in range(34):
        records += _call("2026-01-01T00:00:00Z", f"w{index}", "Write", {
            "file_path": f"/proj/F{index:02d}.ets", "content": "needle"})
    led = _ledger(tmp_path, records)
    hits = []
    text = atoms_text.render_search(led, "needle", until_ts="2026-01-01T01:00:00Z",
                                    navigation_hits=hits)
    files = [h for h in hits if h["kind"] == "file"]
    assert len(files) == 30
    assert all(h["v"] == 1 and h["key"] in text for h in files)
    assert all("seq" in h and "field" in h for h in hits)
    assert "还有 4 个文件" in text


def test_observation_uncertainty_cannot_be_promoted_by_a_stale_certain_flag(tmp_path):
    led = _ledger(tmp_path, [*_call("2026-01-01T00:00:00Z", "w", "Write", {
        "file_path": "/proj/A.ets", "content": "old"}),
        *_read_call("2026-01-01T00:00:02Z", "r", "/proj/A.ets", "old"),
        *_call("2026-01-01T00:00:04Z", "w2", "Write", {
            "file_path": "/proj/B.ets", "content": "next effect"})])
    action = led.agents[MAIN_ID].actions[1]
    action.files[0].observation_uncertain = True
    file_node = verdict.resolve_node(led, "file:/proj/A.ets@v1")
    agent_node = verdict.resolve_node(led, f"agent:{MAIN_ID}@v{action.at}")
    status, _, note = verdict.check_edge(led, file_node, agent_node, "读")
    assert status == "unknown" and "窗口重叠" in note


@pytest.mark.parametrize("marker", ["中文证据", 'quoted "evidence"'])
def test_search_matches_decoded_text_not_only_json_serialization(tmp_path, marker):
    led = _ledger(tmp_path, _call("2026-01-01T00:00:00Z", "shell", "Bash", {"command": "echo"}, marker))
    hits = atoms.search_agent(led, MAIN_ID, marker)["hits"]
    assert len(hits) == 1 and hits[0]["field"] == "output"


def test_timed_search_does_not_use_late_results_as_earlier_knowledge(tmp_path):
    records = _call("2026-01-01T00:00:02Z", "shell", "Bash", {"command": "slow-command"}, "RESULT_ONLY")
    records[1]["timestamp"] = "2026-01-01T00:00:10Z"
    led = _ledger(tmp_path, records)
    early = atoms.search_agent(led, MAIN_ID, "RESULT_ONLY", until_ts="2026-01-01T00:00:08Z")
    later = atoms.search_agent(led, MAIN_ID, "RESULT_ONLY", since_ts="2026-01-01T00:00:08Z",
                               until_ts="2026-01-01T00:00:11Z")
    assert early["hits"] == []
    assert len(later["hits"]) == 1 and later["hits"][0]["ts"] == "2026-01-01T00:00:10Z"


def test_codex_tool_records_are_searchable_as_input_and_output():
    action = atoms.Action("2026-01-01T00:00:00Z", 1, "exec", "other", tuid="call_1")
    use = {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "call_1",
                                                   "input": "INPUT_LITERAL"}}
    result = {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "call_1",
                                                      "output": "OUTPUT_LITERAL"}}
    assert atoms._record_texts(use, action) == {"input": "INPUT_LITERAL"}
    assert atoms._record_texts(result, action) == {"output": "OUTPUT_LITERAL"}


def test_search_excluded_after_counts_actual_matches_only(tmp_path):
    led = _ledger(tmp_path, [*_call("2026-01-01T00:00:00Z", "w1", "Write", {
        "file_path": "/proj/A.ets", "content": "first"}),
        *_call("2026-01-01T00:00:02Z", "w2", "Write", {
            "file_path": "/proj/B.ets", "content": "unrelated"})])
    result = atoms.search_agent(led, MAIN_ID, "NOT_PRESENT", v=1)
    assert result["hits"] == [] and result["excluded_after"] == 0


@pytest.mark.parametrize("needle", ["中文证据", 'quoted "evidence"', "/proj/目标.ets", "ASCII_INPUT_TOKEN"])
def test_native_function_json_strings_are_decoded_for_search_not_raw_action(tmp_path, needle):
    from tests.test_atoms import _write_jsonl
    path = tmp_path / "codex.jsonl"
    arguments = json.dumps({"prompt": "中文证据 quoted \"evidence\" ASCII_INPUT_TOKEN", "file_path": "/proj/目标.ets"})
    rows = [{"timestamp": "2026-01-01T00:00:00Z", "type": "response_item", "payload": {
        "type": "function_call", "call_id": "native", "name": "spawn_agent", "arguments": arguments}},
        {"timestamp": "2026-01-01T00:00:01Z", "type": "response_item", "payload": {
            "type": "function_call_output", "call_id": "native", "output": "done"}}]
    _write_jsonl(str(path), rows)
    action = atoms.Action(rows[0]["timestamp"], 1, "spawn_agent", "other", src=(str(path), 0, 1), tuid="native")
    led = atoms.Ledger({}, {"agent-native": atoms.AgentRec("agent-native", "session", actions=[action])})
    hits = atoms.search_agent(led, "agent-native", needle)["hits"]
    assert len(hits) == 1 and hits[0]["field"] == "input"
    assert atoms.action_raw(led, "agent-native", 1)["input"] == arguments


def test_custom_call_code_is_not_json_decoded_for_search():
    code = json.dumps({"literal": 'quoted "evidence"'})
    action = atoms.Action("t", 1, "exec", "other", tuid="custom")
    row = {"payload": {"type": "custom_tool_call", "call_id": "custom", "input": code}}
    assert atoms._record_texts(row, action) == {"input": code}
