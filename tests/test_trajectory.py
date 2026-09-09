"""调查树:结构只用账本边,路线只是步号 —— 零推断。

节点只有两种(agent@版本 / file@版本),只收模型真的查过的和结论块点名的,每个一次;根 = 被修文件的最终版本;
边只有账本核得出来的 写 / 读 / 派发 / 前一版;「出现于 #j」是事实标注,不画边;和链没有账本边的单独一列。
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
            "root: file:entry/A.ets@v2\n"
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


def test_tree_is_ledger_edges_rooted_at_final_version(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    calls = [
        ("sessions", {"file": "A.ets"}, "# 返修链(1)\n- entry/A.ets | 生成方 conv-a id=agent-c | 修复方 fixer id=agent-f\n"),
        ("file", {"path": "A.ets"}, "# entry/A.ets 2 版\n- v1 agent-c v1 (#c:3@L5)\n- v2 agent-f v1\n"),
        ("agent", {"id": "conv-a", "v": 1}, "# agent-c v1\n读 spec/pages/A.md@v1\n派发者 主会话·abcdef12 v1\n写 entry/A.ets@v1\n"),
        ("file", {"path": "spec/pages/A.md", "v": 1}, "# spec/pages/A.md@v1 外部输入\n"),
        ("agent", {"id": "fixer"}, "# agent-f\n读 entry/A.ets@v1\n"),
        ("search", {"q": "x", "until_ts": "2026-01-01T01:00:00Z"}, "全池命中:agent-c v1 说了 x;spec/pages/A.md@v1 里也有\n"),
    ]
    p = probe.probe_payload(led, _run_dir(tmp_path, calls, _block(led)))
    T = p["trajectory"]
    assert T is not None
    by = {n["id"]: n for n in T["nodes"]}
    ids = [n["id"] for n in T["nodes"]]
    assert len(ids) == len(set(ids)) and all(n["kind"] in ("file", "agent") for n in T["nodes"])
    # 根 = 被修文件的最终版本(账本里最后一版),不是修复前的版本
    root = by[T["root"]]
    assert root["key"] == "/proj/entry/A.ets" and root["v"] == 2 and root["parent"] is None and root["fixed"]
    # fixer 全程查询 → 只有一版,就是 v1;它写了 v2 → 挂根下,边是账本的「写」
    f = by["agent:agent-f@1"]
    assert f["parent"] == T["root"] and f["edge"] == "写" and f["side"] == "up" and f["depth"] == 1 and f["opened"] == [5]
    # A.ets@v1:fixer 写 v2 前读了它 → 挂 fixer 下,边「读」;和 v2 之间另有「前一版」边(不复制节点)
    a1 = by["file:/proj/entry/A.ets@1"]
    assert a1["parent"] == "agent:agent-f@1" and a1["edge"] == "读" and a1["depth"] == 2
    assert {"from": "file:/proj/entry/A.ets@1", "to": "file:/proj/entry/A.ets@2", "relation": "前一版", "skipped": 0} in T["edges"]
    # conv-a v1 写了 v1 → 挂 A.ets@v1 下;它读的 spec 与派发它的主会话挂它下面:agent → file → agent 交替
    c = by["agent:agent-c@1"]
    assert c["parent"] == "file:/proj/entry/A.ets@1" and c["edge"] == "写" and c["depth"] == 3
    assert by["file:/proj/spec/pages/A.md@1"]["parent"] == "agent:agent-c@1" and by["file:/proj/spec/pages/A.md@1"]["edge"] == "读"
    assert by[f"agent:{MAIN_ID}@1"]["parent"] == "agent:agent-c@1" and by[f"agent:{MAIN_ID}@1"]["edge"] == "派发"
    assert by[f"agent:{MAIN_ID}@1"]["source"] == "结论" and by[f"agent:{MAIN_ID}@1"]["opened"] == []
    # repair.before 也是模型点名的坐标:A.ets@v1 在集合里(这里它同时被查过,来源仍标「查过」)
    assert a1["source"] == "查过"
    # 「出现于」只是事实标注:conv-a 出现在第 1、2、6 步的返回里(第 3 步是打开它自己,不算)
    assert c["appears"] == [1, 2, 6]
    # 索引查询并进版本节点:file(A.ets) 第 2 步算打开了 v1 与 v2
    assert 2 in a1["opened"] and 2 in root["opened"]
    # 父在子之前,没有无账本边的节点
    pos = {n["id"]: i for i, n in enumerate(T["nodes"])}
    assert all(n["parent"] is None or pos[n["parent"]] < pos[n["id"]] for n in T["nodes"])
    assert not [n for n in T["nodes"] if n["side"] == "unlinked"]


def test_unlinked_nodes_go_to_their_own_column(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    calls = [
        ("agent", {"id": "fixer", "v": 1}, "# agent-f v1\n读 entry/A.ets@v1\n"),
        ("file", {"path": "A.ets"}, "# entry/A.ets\n- v1 agent-c v1\n- v2 agent-f v1\n"),
        ("file", {"path": "spec/pages/A.md", "v": 1}, "# spec/pages/A.md@v1\n"),
    ]
    report = ("```yaml\nschema: migloop-verdict/1\nroot: file:entry/A.ets@v2\ndefects:\n  - id: A\n    title: t\n"
              "    nodes:\n      - {node: file:entry/A.ets@v1, role: 带病传递, reason: r}\n```\n")
    p = probe.probe_payload(led, _run_dir(tmp_path, calls, report, name="unlinked"))
    T = p["trajectory"]
    by = {n["id"]: n for n in T["nodes"]}
    assert by[T["root"]]["v"] == 2 and by[T["root"]]["source"] == "任务"
    assert by["agent:agent-f@1"]["parent"] == T["root"] and by["agent:agent-f@1"]["edge"] == "写"
    # spec/pages/A.md@v1 查过了,但读它的 conv-a 不在集合里 → 不在根的上下游锥里 → 单独一列,不挂到任何人下
    a = by["file:/proj/spec/pages/A.md@1"]
    assert a["side"] == "unlinked" and a["edge"] is None and a["parent"] == T["root"]
    assert "file:/proj/entry/A.ets@-" not in by
    # 没有 transcript.jsonl 的老 run:没有轨迹,页面退回账本树
    d = _run_dir(tmp_path, calls, report, name="old")
    os.remove(os.path.join(d, "transcript.jsonl"))
    assert probe.probe_payload(led, d)["trajectory"] is None


def test_fixchain_template_builds_ledger_edge_tree() -> None:
    from migloop.service import load_asset
    html = load_asset("fixchain.html")
    for needle in ("probeBuildTrajectory(", "PROBE.trajectory", "node.traj", "不在根的上下游", "前一版", "XT.extra", "出现于",
                   "XT.via", "wire via", "T.declared", "账本无此边", "XT.walk"):
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
    assert verdict.SCHEMA == "migloop-verdict/1"


def test_walk_tree_follows_via_and_labels_ledger_relations(tmp_path: Any) -> None:
    """有 via 的 run:树 = 打开的节点按 via 挂(打开索引 = 整个,打开某版 = 那一版);每跳按账本标关系;via 不合规的进侧列。"""
    led = _pool(tmp_path)
    calls = [
        ("sessions", {"file": "A.ets"}, "# 返修链(1)\n"),
        ("file", {"path": "A.ets", "via": "sessions"}, "# entry/A.ets 2 版\n- v1 agent-c v1\n- v2 agent-f v1\n"),
        ("agent", {"id": "conv-a", "v": 1, "via": "file:entry/A.ets 写者"}, "# agent-c v1\n读 spec/pages/A.md@v1\n"),
        ("file", {"path": "spec/pages/A.md", "v": 1, "via": "agent:conv-a@v1 读取"}, "# spec/pages/A.md@v1\n"),
        ("agent", {"id": "fixer", "via": "file:entry/A.ets@v2 写者"}, "# agent-f\n"),         # v2 没打开过:老 run 才会出现,进侧列
        ("agent", {"id": "fixer", "v": 1, "via": "file:entry/A.ets@v1"}, '{"result": "⛔ via 不是已打开的节点"}'),   # 服务端拒了(客户端包成 JSON 落盘):不算打开
        ("agent", {"id": MAIN_ID, "v": 1, "via": "agent:conv-a@v1 派发"}, "# 主会话 v1\n"),
        ("file", {"path": "A.ets", "v": 2, "via": "agent:fixer 写"}, "# entry/A.ets@v2\n"),
        ("blame", {"path": "A.ets", "v": 2}, "# blame\n"),                                       # 不移动
        ("file", {"path": "A.ets", "via": "agent:conv-a@v1"}, "# 再看索引\n"),                  # 再次打开同一节点:只加步号
    ]
    p = probe.probe_payload(led, _run_dir(tmp_path, calls, _block(led), name="walk"))
    T = p["trajectory"]
    assert T["mode"] == "via"
    by = {n["id"]: n for n in T["nodes"]}
    root = by[T["root"]]
    assert root["id"] == "file:/proj/entry/A.ets@-" and root["label"] == "A.ets(索引)" and root["side"] == "root"
    assert root["opened"] == [2, 10] and root["via"] == "sessions"
    c = by["agent:agent-c@1"]
    assert c["parent"] == root["id"] and c["side"] == "up" and c["edge"] == "写者 v1" and c["depth"] == 1
    a = by["file:/proj/spec/pages/A.md@1"]
    assert a["parent"] == c["id"] and a["edge"] == "读 v1" and a["depth"] == 2
    m = by[f"agent:{MAIN_ID}@1"]
    assert m["parent"] == c["id"] and m["edge"] == "派发自 v1"
    f = by["agent:agent-f@-"]
    assert f["side"] == "unlinked" and f["note"] == "via 指向没打开过的节点" and f["parent"] == root["id"]
    a2 = by["file:/proj/entry/A.ets@2"]
    assert a2["parent"] == f["id"] and a2["edge"] == "写 v2" and a2["fixed"]                     # 从整个 fixer 跳到它写的 v2
    # 被拒的那一步没打开 fixer v1;结论点名的 A.ets@v1 同键已在路线上(索引 / v2),不另列侧列,角色落在那些节点上
    assert "agent:agent-f@1" not in by and "file:/proj/entry/A.ets@1" not in by
    d = {x["step"]: x["match"] for x in T["declared"]}
    assert d == {2: "入口", 3: "账本有边", 4: "账本有边", 5: "via 指向没打开过的节点", 6: "被拒(via 不合规,没打开)",
                 7: "账本有边", 8: "账本有边"}
    assert p["steps"][2]["via"] == "file:entry/A.ets 写者"
    # 整个文件 = 最新版视图:上游邻居按全部版本算(写 v1 的 conv-a v1、写 v2 的 fixer v1);在场的整个 fixer 覆盖它所有版本 → 未查 0
    assert root["unseen"] == 0
    assert by["agent:agent-c@1"]["unseen"] == 0                    # conv-a v1 的上游:读的 A.md@v1 在场,派发它的主会话 v1 在场
    # 没有 via 的老 run 仍走账本树
    assert probe.probe_payload(led, _run_dir(tmp_path, [("file", {"path": "A.ets"}, "x")], _block(led), name="noVia"))["trajectory"]["mode"] == "ledger"
