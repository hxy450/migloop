"""A prompt or self-report must not displace the first matching native output."""
from copy import deepcopy

from migloop import atoms, atoms_text
from tests.test_atoms import MAIN_ID, _call, _ledger, _rec


def test_pool_search_partitions_record_sources_without_dropping_hits(tmp_path):
    records = [_rec("2026-01-01T00:00:00Z", "user", "Please run build with hvigor"),
               _rec("2026-01-01T00:00:01Z", "assistant", "I think hvigor already succeeded"),
               *_call("2026-01-01T00:00:02Z", "native", "Bash", {"command": "hvigor assembleHap"},
                      out="hvigor FAILED: exit 1"),
               *_call("2026-01-01T00:00:03Z", "native2", "Bash", {"command": "hvigor assembleHap"},
                      out="hvigor BUILD SUCCESSFUL")]
    ledger = _ledger(tmp_path, records)
    before = deepcopy(ledger)
    result = atoms.search_pool(ledger, "hvigor", until_ts="2026-01-01T01:00:00Z")
    row = next(a for a in result["agents"] if a["agent"] == MAIN_ID)
    assert row["first"]["kind"] == "instruction"
    groups = {s["source"]: s for s in row["sources"]}
    assert set(groups) == {"instruction", "statement", "tool_input", "tool_output"}
    assert sum(s["n"] for s in groups.values()) == row["n"] == 6
    assert groups["tool_output"]["n"] == 2
    # No cherry-picking a successful result: first result is the actual failure.
    assert "FAILED" in str(groups["tool_output"]["first"]["snips"])
    assert groups["tool_output"]["first"]["field"] == "output"
    text = atoms_text.render_search(ledger, "hvigor", until_ts="2026-01-01T01:00:00Z")
    assert "[工具返回 2 条]" in text and "[消息/自述 1 条]" in text
    assert "[指令/注入 1 条]" in text and "FAILED" in text
    assert "不判断内容真假" in text and "action(id=" in text
    assert ledger == before


def test_source_grouping_obeys_time_window_and_does_not_invent_empty_groups(tmp_path):
    ledger = _ledger(tmp_path, [*_call("2026-01-01T00:00:02Z", "run", "Bash",
        {"command": "echo marker"}, out="marker")])
    action = ledger.agents[MAIN_ID].actions[0]
    result = atoms.search_pool(ledger, "marker", until_ts=action.ts)
    row = result["agents"][0]
    assert [s["source"] for s in row["sources"]] == ["tool_input"]
    assert row["n"] == 1
    assert atoms.search_pool(ledger, "absent", until_ts=action.ts)["agents"] == []


def test_earliest_output_uses_return_time_not_launch_order(tmp_path):
    slow = list(_call("2026-01-01T00:00:02Z", "slow", "Bash", {"command": "echo marker"}, out="marker slow"))
    fast = list(_call("2026-01-01T00:00:03Z", "fast", "Bash", {"command": "echo marker"}, out="marker fast"))
    slow[-1]["timestamp"] = "2026-01-01T00:00:10Z"
    fast[-1]["timestamp"] = "2026-01-01T00:00:04Z"
    ledger = _ledger(tmp_path, [slow[0], fast[0], fast[-1], slow[-1]])
    result = atoms.search_pool(ledger, "marker", until_ts="2026-01-01T00:00:11Z")
    outputs = next(g for g in result["agents"][0]["sources"] if g["source"] == "tool_output")
    assert outputs["n"] == 2 and "marker fast" in str(outputs["first"]["snips"])


def test_navigation_receipt_records_actual_matched_field_not_action_kind(tmp_path):
    from migloop import via
    from tests.test_verdict import _pool

    ledger = _pool(tmp_path)
    for args in ({"q": "spec", "until_ts": "2026-01-01T01:00:00Z"},
                 {"q": "spec", "agent": "agent-c", "v": 1}):
        hits = []
        text = atoms_text.render_search(ledger, navigation_hits=hits, **args)
        readers = [h for h in hits if h["kind"] == "agent" and h["key"] == "agent-c"]
        assert {h["field"] for h in readers} == {"input", "output"}
        result = via.search_return(ledger, via.ViaState(), args, text, hits)
        receipt = via.search_receipt(result, args)
        assert any(h["field"] == "output" and h["key"] == "agent-c" for h in receipt["hits"])
