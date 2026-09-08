"""调查覆盖:调查员的调用序列与报告环 → 探索树节点。"""
from __future__ import annotations

import json
import os
from typing import Any

from migloop import probe

from tests.test_atoms import _call, _ledger, _read_call, _rec


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
              f"环 2  conv-a(agent-c)v1 写 A.ets@v1,凭 spec/pages/A.md@v1 (#{conv_seq}@L5)   判定: 错\n"
              "环 3  spec/pages/A.md@v1 外部输入   判定: 缺\n"
              "故障进入点:\n"                                    # 真报告里常换行再分条,还会给几条缺陷各自的进入点
              "- 两条缺陷各自进入。按时间最早是环 2(派发词缺约束);\n"
              "- 另一条的进入点是环 3\n")
    p = probe.probe_payload(led, _run_dir(tmp_path, seq, report))
    kinds = [s["node"]["kind"] if s["node"] else None for s in p["steps"]]
    assert kinds == [None, "chain", "file", "agent", "agent", "pool"]
    assert p["steps"][2]["node"] == {"kind": "file", "path": "/proj/entry/A.ets", "v": 2}
    assert p["steps"][3]["node"]["aid"] == "agent-c" and p["steps"][4]["node"]["aid"] == "agent-c"
    assert p["root"] == "/proj/entry/A.ets" and p["entry"] == 2 and p["entries"] == [2, 3]
    assert [lk["verdict"] for lk in p["links"]] == ["传递", "错", "缺"]
    assert [lk["entry"] for lk in p["links"]] == [False, True, True]
    # 判定只落在每环的主语(正文第一个坐标):环 1 主语是 A.ets@v2 → 传递;环 2 主语是 agent-c → 错;环 3 主语是 A.md → 缺
    assert p["verdicts"]["/proj/entry/A.ets"]["verdict"] == "传递"
    assert p["verdicts"]["agent-c"]["verdict"] == "错" and p["verdicts"]["agent-c"]["entry"]
    assert p["verdicts"]["/proj/spec/pages/A.md"]["verdict"] == "缺" and p["verdicts"]["/proj/spec/pages/A.md"]["entry"]
    assert [n["kind"] for n in p["links"][1]["nodes"]] == ["agent", "file", "file", "agent"]   # 主语在前,其余是提到


def test_fixchain_template_has_probe_hooks() -> None:
    from migloop.service import load_asset
    html = load_asset("fixchain.html")
    assert 'id="probe"' in html and "U.probe" in html and "probeDecorate(d, node)" in html and "bootProbe()" in html
