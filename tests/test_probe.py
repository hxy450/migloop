"""调查覆盖:调查员的调用序列与报告环 → 探索树节点。"""
from __future__ import annotations

import json
import os
from typing import Any

from migloop import probe

from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call, _rec


def _run_dir(tmp_path: Any, seq: list[dict[str, Any]], report: str) -> str:
    d = tmp_path / "runs" / "lab" / "chain10-A.ets" / "rep1"
    os.makedirs(d, exist_ok=True)
    with open(d / "metrics.json", "w", encoding="utf-8") as fh:
        json.dump({"cost_usd": 1.5, "num_turns": 9, "transcript": {"seq": seq}}, fh)
    with open(d / "result.json", "w", encoding="utf-8") as fh:
        json.dump({"result": report}, fh)
    return str(d)


def test_probe_maps_calls_and_links_to_nodes(tmp_path: Any) -> None:
    conv = [_rec("2026-01-01T00:00:00Z", "user", "转换 A"),
            *_read_call("2026-01-01T00:00:10Z", "c1", "/proj/spec/pages/A.md", "spec\n"),
            *_call("2026-01-01T00:00:20Z", "c2", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets")]
    fix = [_rec("2026-01-01T02:00:00Z", "user", "修 A"),
           *_read_call("2026-01-01T02:00:10Z", "f1", "/proj/entry/A.ets", "a\n"),
           *_call("2026-01-01T02:00:20Z", "f2", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-a", "prompt": "转换 A"}, "done",
                   toolUseResult={"agentId": "c"}),
            *_call("2026-01-01T02:00:00Z", "m2", "Agent", {"name": "fixer", "prompt": "修 A"}, "done",
                   toolUseResult={"agentId": "f"})]
    led = _ledger(tmp_path, main, {"agent-c": conv, "agent-f": fix})
    conv_seq = next(a.seq for a in led.agents["agent-c"].actions if a.tool == "Write")
    seq = [{"tool": "guide", "input": {}, "chars": 4000},
           {"tool": "sessions", "input": {"path": "A.ets"}, "chars": 800},
           {"tool": "file", "input": {"path": "A.ets", "v": 2}, "chars": 1200},
           {"tool": "agent", "input": {"id": "conv-a", "v": 1}, "chars": 3000},
           {"tool": "action", "input": {"id": "agent-c", "seq": conv_seq}, "chars": 500},
           {"tool": "search", "input": {"q": "x", "until_ts": "2026-01-01T01:00:00Z"}, "chars": 300}]
    report = ("文件: entry/A.ets\n"
              "环 1  fixer 写 A.ets@v2 (#9@L9)   判定: 传递\n"
              f"环 2  conv-a(agent-c)v1 写 A.ets@v1,凭 spec/pages/A.md@v1 (#{conv_seq}@L{led.lines[conv_seq]})   判定: 错\n"
              "环 3  spec/pages/A.md@v1 外部输入   判定: 缺\n"
              f"环 4  主会话·{MAIN_ID.split(':')[1]} v1 的派发词缺约束   判定: 错\n"      # 主会话不是 agent-… 形式的 id,也得认成坐标
              "故障进入点:\n"                                    # 真报告里常换行再分条,还会给几条缺陷各自的进入点
              "- 两条缺陷各自进入。按时间最早是环 2(派发词缺约束);\n"
              "- 另一条的进入点是环 3\n")
    p = probe.probe_payload(led, _run_dir(tmp_path, seq, report))
    kinds = [s["node"]["kind"] if s["node"] else None for s in p["steps"]]
    assert kinds == [None, "chain", "file", "agent", "agent", "pool"]
    assert p["steps"][2]["node"] == {"kind": "file", "path": "/proj/entry/A.ets", "v": 2}
    assert p["steps"][3]["node"]["aid"] == "agent-c" and p["steps"][4]["node"]["aid"] == "agent-c"
    assert p["root"] == "/proj/entry/A.ets" and p["entry"] == 2 and p["entries"] == [2, 3]
    assert [lk["verdict"] for lk in p["links"]] == ["传递", "错", "缺", "错"]
    assert [lk["entry"] for lk in p["links"]] == [False, True, True, False]
    assert p["links"][3]["nodes"][0] == {"kind": "agent", "aid": MAIN_ID, "v": 1}
    # 判定只落在每环的主语(正文第一个坐标),并且按「节点 + 版本」记,同一 id 的别的版本不连坐
    assert p["verdicts"]["/proj/entry/A.ets"] == [{"kind": "file", "v": 2, "verdict": "传递", "links": [1], "entry": False}]
    assert p["verdicts"]["agent-c"] == [{"kind": "agent", "v": 1, "verdict": "错", "links": [2], "entry": True}]
    assert p["verdicts"]["/proj/spec/pages/A.md"][0]["verdict"] == "缺" and p["verdicts"]["/proj/spec/pages/A.md"][0]["entry"]
    assert p["verdicts"][MAIN_ID] == [{"kind": "agent", "v": 1, "verdict": "错", "links": [4], "entry": False}]
    assert [n["kind"] for n in p["links"][1]["nodes"]] == ["agent", "file", "file", "agent"]   # 主语在前,其余是提到


def test_fixchain_template_has_probe_hooks() -> None:
    from migloop.service import load_asset
    html = load_asset("fixchain.html")
    assert 'id="probe"' in html and "U.probe" in html and "probeDecorate(d, node)" in html and "bootProbe()" in html
    # 调查树:根开好后自动展开到每个查过的节点;没查过的兄弟折成桩;被归因的链整条标红(节点 + 边)
    assert "probeExpand(" in html and "unstub(" in html and "isStub" in html
    assert ".node.p-chain" in html and ".wire.chain" in html and "未查" in html
    # 红只落在 键 + 版本 对上的节点;同 id 别的版本挂灰标说明环判的是哪一版
    assert "probeVerdictFor(" in html and "判的是 v" in html


def test_probe_rejects_forged_line_numbers(tmp_path: Any) -> None:
    """引用核验只证明「位置存在、原文匹配」:#n@L 的 L 与账本记的转录行号对不上,就不落节点,记进 bad_refs。"""
    conv = [_rec("2026-01-01T00:00:00Z", "user", "转换 A"),
            *_call("2026-01-01T00:00:20Z", "c2", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-a", "prompt": "转换 A"}, "done",
                   toolUseResult={"agentId": "c"})]
    led = _ledger(tmp_path, main, {"agent-c": conv})
    conv_seq = next(a.seq for a in led.agents["agent-c"].actions if a.tool == "Write")
    good = f"#{conv_seq}@L{led.lines[conv_seq]}"
    report = ("文件: entry/A.ets\n"
              f"环 1  conv-a(agent-c)v1 写 A.ets@v1 ({good})   判定: 错\n"
              f"环 2  conv-a(agent-c)v1 又写 (#{conv_seq}@L999999)   判定: 传递\n"
              "故障进入点: 环 1\n")
    p = probe.probe_payload(led, _run_dir(tmp_path, [], report))
    assert p["links"][0]["bad_refs"] == [] and any(n.get("action") == conv_seq for n in p["links"][0]["nodes"])
    assert p["links"][1]["bad_refs"] == [f"#{conv_seq}@L999999"]
    assert not any(n.get("action") == conv_seq for n in p["links"][1]["nodes"])
    assert p["bad_refs"] == 1
