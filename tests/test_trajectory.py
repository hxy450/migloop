"""调查轨迹树:树 = 模型走过的路,不是账本的上游树。

节点只有两种(agent@版本 / file@版本),只收模型真的查过的和结论块点名的;每个节点出现一次,
挂在「模型第一次在返回文本里看到它」的那一步的落点下面 —— 这条边有实录(transcript.jsonl 的返回文本),不猜。
从没在返回里出现过就被查的:任务给的挂根,其余标「无来源」也挂根。结论里点名但没直接查的挂在给出它的那一步下,标「命中未展开」。
"""
from __future__ import annotations

import json
import os
from typing import Any

from migloop import atoms, probe, verdict
from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call, _rec


def _pool(tmp_path: Any) -> atoms.Ledger:
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
    return _ledger(tmp_path, main, {"agent-c": conv, "agent-f": fix})


def _run_dir(tmp_path: Any, calls: list[tuple[str, dict[str, Any], str]], report: str, name: str = "traj") -> str:
    """calls = [(tool, input, 返回文本)]:同时落 metrics.json(seq)和 transcript.jsonl(tool_use / tool_result)。"""
    d = tmp_path / "runs" / name / "chain10-A.ets" / "rep1"
    os.makedirs(d, exist_ok=True)
    seq = [{"tool": t, "input": inp, "chars": len(out)} for t, inp, out in calls]
    with open(d / "metrics.json", "w", encoding="utf-8") as fh:
        json.dump({"cost_usd": 1.0, "num_turns": len(calls), "transcript": {"seq": seq}}, fh)
    with open(d / "result.json", "w", encoding="utf-8") as fh:
        json.dump({"result": report}, fh)
    with open(d / "transcript.jsonl", "w", encoding="utf-8") as fh:
        for i, (t, inp, out) in enumerate(calls, 1):
            tid = f"toolu_{i}"
            fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "想一下"}, {"type": "tool_use", "id": tid, "name": "mcp__migloop__" + t, "input": inp}]}}) + "\n")
            fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": out}]}]}}) + "\n")
    return str(d)


def _block(led: atoms.Ledger) -> str:
    return ("散文。\n\n```yaml\nschema: migloop-verdict/1\n"
            f"ledger: {atoms.ledger_identity(led)}\n"
            "root: file:entry/A.ets@v1\n"
            "defects:\n"
            "  - id: A\n    title: t\n"
            "    repair: {before: file:entry/A.ets@v1, after: file:entry/A.ets@v2}\n"
            "    entry: [agent:conv-a@v1]\n"
            "    nodes:\n"
            "      - {node: file:spec/pages/A.md@v1, role: 正常, reason: r}\n"
            "      - {node: agent:conv-a@v1, role: 进入·错, reason: r}\n"
            "      - {node: file:entry/A.ets@v1, role: 带病传递, reason: r}\n"
            f"      - {{node: agent:{MAIN_ID}@v1, role: 正常, reason: 派发词没问题}}\n"
            "```\n")


def test_trajectory_places_each_node_once_under_first_sighting(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    calls = [
        ("sessions", {"file": "A.ets"}, "# 返修链(1)\n- entry/A.ets | 生成方 conv-a id=agent-c | 修复方 fixer id=agent-f\n"),
        ("file", {"path": "A.ets"}, "# entry/A.ets 2 版\n- v1 agent-c v1 (#c:3@L5)\n- v2 agent-f v1\n"),
        ("agent", {"id": "conv-a", "v": 1}, "# agent-c v1\n读 spec/pages/A.md@v1\n派发者 主会话·abcdef12 v1\n写 entry/A.ets@v1\n"),
        ("file", {"path": "spec/pages/A.md", "v": 1}, "# spec/pages/A.md@v1 外部输入\n"),
        ("agent", {"id": "fixer"}, "# agent-f\n读 entry/A.ets@v1\n"),                # 之前没有任何返回提到过 agent-f 的 v?…
        ("search", {"q": "x", "until_ts": "2026-01-01T01:00:00Z"}, "全池命中:agent-c v1 说了 x;spec/pages/A.md@v1 里也有\n"),
    ]
    p = probe.probe_payload(led, _run_dir(tmp_path, calls, _block(led)))
    T = p["trajectory"]
    assert T is not None
    by = {n["id"]: n for n in T["nodes"]}
    ids = [n["id"] for n in T["nodes"]]
    # 每个节点一次,只有 agent / file 两种,精确到版本;根是被修文件的修复前版本
    assert len(ids) == len(set(ids)) and all(n["kind"] in ("file", "agent") for n in T["nodes"])
    root = by[T["root"]]
    assert root["kind"] == "file" and root["key"] == "/proj/entry/A.ets" and root["v"] == 1 and root["parent"] is None
    assert root["edge_kind"] == "task"
    # conv-a v1:第 1 步 sessions 的返回里就有它的 id(sessions 不落节点)→ 挂根,边是「命中」,版本没标出来
    c = by["agent:agent-c@1"]
    assert c["parent"] == T["root"] and c["edge_kind"] == "search" and c["seen_step"] == 1 and c["seen_tool"] == "sessions"
    assert c["seen_exact"] is False and c["opened"] == [3] and c["source"] == "查过"
    # spec/pages/A.md@v1:第 3 步 agent(conv-a) 的返回里第一次出现 → 挂在 conv-a v1 下;第 6 步又出现一次 → 计数,不重复挂
    a = by["file:/proj/spec/pages/A.md@1"]
    assert a["parent"] == "agent:agent-c@1" and a["seen_step"] == 3 and a["seen_exact"] and a["seen_count"] == 2
    assert a["opened"] == [4]
    # 主会话 v1:结论点名、没查过;第 3 步返回里出现 → 挂在 conv-a v1 下,标「命中未展开」
    m = by[f"agent:{MAIN_ID}@1"]
    assert m["parent"] == "agent:agent-c@1" and m["source"] == "结论" and m["opened"] == [] and m["seen_step"] == 3
    # fixer 整段(v 未指定):第 1 步 sessions 的返回里出现过(sessions 不落节点)→ 挂根,边是「命中」
    f = by["agent:agent-f@-"]
    assert f["parent"] == T["root"] and f["edge_kind"] == "search" and f["seen_step"] == 1 and f["opened"] == [5]
    # 修复后版本 A.ets@v2:结论里只在 repair.after;打开这个键的步(#2 索引)不算看到,第 1 步 sessions 提到过文件 → 挂根,版本未标
    a2 = by["file:/proj/entry/A.ets@2"]
    assert a2["fixed"] and a2["source"] == "查过" and a2["parent"] == T["root"] and a2["seen_step"] == 1 and a2["seen_exact"] is False
    assert a2["opened"] == [2]                       # 不带版本的 file(A.ets) 索引查询算打开了它的每个版本节点
    # 父在子之前(页面按顺序装树)
    pos = {n["id"]: i for i, n in enumerate(T["nodes"])}
    assert all(n["parent"] is None or pos[n["parent"]] < pos[n["id"]] for n in T["nodes"])
    # 账本关系只在两端版本都精确时核:根(A.ets@v1)← conv-a v1 是写边;A.md@v1 → conv-a v1 是读边
    assert c["ledger"] == {"relation": "写", "status": "true"}
    assert a["ledger"] == {"relation": "读", "status": "true"}
    assert f["ledger"] is None
    # 没查过的账本邻居数:conv-a v1 上游 = 读 A.md@v1 + 派发者主会话 v1,两者都在树上 → 0;根 A.ets@v1 上游 = 写者 conv-a v1 在树上 → 0
    assert c["unseen"] == 0 and root["unseen"] == 0


def test_trajectory_marks_unsourced_and_merges_index_steps(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    calls = [
        ("agent", {"id": "fixer", "v": 1}, "# agent-f v1\n读 entry/A.ets@v1\n"),      # 第一步就查了 fixer:没人提过它 → 无来源
        ("file", {"path": "A.ets"}, "# entry/A.ets\n- v1 agent-c v1\n- v2 agent-f v1\n"),   # 索引查询,不带版本
    ]
    report = ("```yaml\nschema: migloop-verdict/1\nroot: file:entry/A.ets@v1\ndefects:\n  - id: A\n    title: t\n"
              "    nodes:\n      - {node: file:entry/A.ets@v1, role: 带病传递, reason: r}\n```\n")
    p = probe.probe_payload(led, _run_dir(tmp_path, calls, report, name="unsourced"))
    T = p["trajectory"]
    by = {n["id"]: n for n in T["nodes"]}
    f = by["agent:agent-f@1"]
    assert f["parent"] == T["root"] and f["edge_kind"] == "none" and f["seen_step"] is None
    # file(A.ets) 不带版本的索引查询并进同键的版本节点(根 A.ets@v1),不另立一个「整个文件」节点
    assert "file:/proj/entry/A.ets@-" not in by and by[T["root"]]["opened"] == [2]
    # 没有 transcript.jsonl 的老 run:没有轨迹,页面退回账本树
    d = _run_dir(tmp_path, calls, report, name="old")
    os.remove(os.path.join(d, "transcript.jsonl"))
    assert probe.probe_payload(led, d)["trajectory"] is None


def test_fixchain_template_builds_trajectory_tree() -> None:
    from migloop.service import load_asset
    html = load_asset("fixchain.html")
    for needle in ("probeBuildTrajectory(", "PROBE.trajectory", "node.traj", "无来源", "命中未展开", "看到"):
        assert needle in html, needle


def test_sighting_rules() -> None:
    seen, exact = probe._sight("读 entry/pages/A.ets@v3 与 B.ets", "file", "/proj/entry/pages/A.ets", 3, None)
    assert seen and exact
    seen, exact = probe._sight("读 pages/A.ets@v2", "file", "/proj/entry/pages/A.ets", 3, None)
    assert seen and not exact
    assert probe._sight("没有它", "file", "/proj/entry/pages/A.ets", 3, None) == (False, False)
    assert probe._sight("agent-c v1 写了", "agent", "agent-c", 1, None) == (True, True)
    assert probe._sight("id=agent-c 的 v2", "agent", "agent-c", 1, None) == (True, False)
    assert probe._sight("主会话·abcdef12 v83 派发", "agent", "__main__:abcdef12", 83, None) == (True, True)
    assert probe._sight("主会话·abcdef12 v83 派发", "agent", "__main__:abcdef12", None, None) == (True, True)
    assert verdict.SCHEMA == "migloop-verdict/1"
