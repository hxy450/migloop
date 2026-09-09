"""调查树:结构只用账本边,路线只是步号 —— 零推断。

节点只有两种(agent@版本 / file@版本),只收模型真的查过的和结论块点名的,每个一次;根 = 被修文件的最终版本;
边只有账本核得出来的 写 / 读 / 派发 / 前一版;「出现于 #j」是事实标注,不画边;和链没有账本边的单独一列。
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest

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


def _run_dir(tmp_path: Any, calls: list[tuple[str, dict[str, Any], Any]], report: str, name: str = "traj") -> str:
    """calls = [(tool, input, 返回文本)]:同时落 metrics.json(seq)和 transcript.jsonl(tool_use / tool_result)。"""
    d = tmp_path / "runs" / name / "chain10-A.ets" / "rep1"
    os.makedirs(d, exist_ok=True)
    seq = [{"tool": t, "input": inp, "chars": len(str(out or ""))} for t, inp, out in calls]
    with open(d / "metrics.json", "w", encoding="utf-8") as fh:
        json.dump({"cost_usd": 1.0, "num_turns": len(calls), "transcript": {"seq": seq}}, fh)
    with open(d / "result.json", "w", encoding="utf-8") as fh:
        json.dump({"result": report}, fh)
    with open(d / "transcript.jsonl", "w", encoding="utf-8") as fh:
        for i, (t, inp, out) in enumerate(calls, 1):
            tid = f"toolu_{i}"
            fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "想一下"}, {"type": "tool_use", "id": tid, "name": "mcp__migloop__" + t, "input": inp}]}}) + "\n")
            if out is not None:
                text = out.get("text", "") if isinstance(out, dict) else out
                fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": tid, "is_error": bool(isinstance(out, dict) and out.get("is_error")),
                     "content": [{"type": "text", "text": text}]}]}}) + "\n")
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
    # 「出现于」核精确版本:第1步仅提agent未给版本,第3步是打开它自己,都不算。
    assert c["appears"] == [2, 6]
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
    report = (f"```yaml\nschema: migloop-verdict/1\nledger: {atoms.ledger_identity(led)}\nroot: file:entry/A.ets@v2\ndefects:\n  - id: A\n    title: t\n"
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
    assert probe._sight("entry/A.ets @v1", "file", "/proj/entry/A.ets", 1, None) == (True, True)
    assert probe._sight("entry/A.ets@v10", "file", "/proj/entry/A.ets", 1, None) == (True, False)
    assert probe._sight("OtherA.ets@v1", "file", "/proj/entry/A.ets", 1, None) == (True, False)
    assert probe._sight("agent-c v1 写了", "agent", "agent-c", 1, None) == (True, True)
    assert probe._sight("id=agent-c 的 v2", "agent", "agent-c", 1, None) == (True, False)
    assert probe._sight("agent-c v2 提到 agent-f v1", "agent", "agent-c", 1, None) == (True, False)
    assert probe._sight("主会话·abcdef12 v83 派发", "agent", "__main__:abcdef12", 83, None) == (True, True)
    assert verdict.SCHEMA == "migloop-verdict/1"


def test_walk_tree_follows_via_and_labels_ledger_relations(tmp_path: Any) -> None:
    """有 via 的 run:树 = 打开的节点(都带版本)按 via 挂;每跳按账本标关系;via 不合规的进侧列;被拒的不算打开。"""
    led = _pool(tmp_path)
    calls = [
        ("sessions", {"file": "A.ets"}, "# 返修链(1)\n"),
        ("file", {"path": "A.ets", "v": 2, "via": "sessions"}, "# entry/A.ets@v2\n- v1 agent-c v1\n- v2 agent-f v1\n"),
        ("agent", {"id": "fixer", "v": 1, "via": "file:entry/A.ets@v2 写者"}, "# agent-f v1\n读 entry/A.ets@v1\n"),
        ("file", {"path": "A.ets", "v": 1, "via": "agent:fixer@v1 读取"}, "# entry/A.ets@v1\n- v1 agent-c v1\n"),
        ("agent", {"id": "conv-a", "v": 1, "via": "file:entry/A.ets@v1 写者"}, "# agent-c v1\n读 spec/pages/A.md@v1\n"),
        ("file", {"path": "spec/pages/A.md", "v": 1, "via": "agent:conv-a@v1 读取"}, "# spec/pages/A.md@v1\n"),
        ("agent", {"id": MAIN_ID, "v": 1, "via": "agent:conv-a@v1 派发"}, f"# agent 主会话 id={MAIN_ID} v1\n"),
        ("agent", {"id": MAIN_ID, "v": 2, "via": "file:entry/A.ets@v9"}, '{"result": "⛔ via 不是已打开的节点"}'),   # 服务端拒了:不算打开
        ("blame", {"path": "A.ets", "v": 2}, "# blame\n"),                                       # 不移动
        ("file", {"path": "A.ets", "v": 2, "via": "agent:conv-a@v1"}, "# entry/A.ets@v2\n"),   # 再次打开同一节点也保留转移
    ]
    p = probe.probe_payload(led, _run_dir(tmp_path, calls, _block(led), name="walk"))
    T = p["trajectory"]
    assert T["mode"] == "via"
    by = {n["id"]: n for n in T["nodes"]}
    root = by[T["root"]]
    assert root["id"] == "file:/proj/entry/A.ets@2" and root["label"] == "A.ets@v2" and root["side"] == "root"
    assert root["opened"] == [2, 10] and root["via"] == "sessions" and root["fixed"]
    f = by["agent:agent-f@1"]
    assert f["parent"] == root["id"] and f["edge"] == "写者 v2" and f["depth"] == 1
    a1 = by["file:/proj/entry/A.ets@1"]
    assert a1["parent"] == f["id"] and a1["edge"] == "读 v1" and a1["depth"] == 2
    c = by["agent:agent-c@1"]
    assert c["parent"] == a1["id"] and c["edge"] == "写者 v1" and c["depth"] == 3
    a = by["file:/proj/spec/pages/A.md@1"]
    assert a["parent"] == c["id"] and a["edge"] == "读 v1"
    m = by[f"agent:{MAIN_ID}@1"]
    assert m["parent"] == c["id"] and m["edge"] == "派发自 v1"
    assert f"agent:{MAIN_ID}@2" not in by                                     # 被拒的那一步没打开
    assert all(n["v"] is not None for n in T["nodes"])                        # 树上没有不带版本的节点
    d = {x["step"]: x["match"] for x in T["declared"]}
    assert d == {2: "入口", 3: "账本有边", 4: "账本有边", 5: "账本有边", 6: "账本有边", 7: "账本有边",
                 8: "被拒(未打开)", 10: "账本无此边"}
    assert T["transitions"][-1]["step"] == 10 and T["transitions"][-1]["to"] == root["id"]
    assert p["steps"][2]["via"] == "file:entry/A.ets@v2 写者"
    # 没有 via 的老 run 仍走账本树
    assert probe.probe_payload(led, _run_dir(tmp_path, [("file", {"path": "A.ets"}, "x")], _block(led), name="noVia"))["trajectory"]["mode"] == "ledger"


def test_walk_preserves_revisits_self_loops_multiple_parents_and_windows(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    calls = [
        ("file", {"path": "A.ets", "v": 2, "via": "sessions"}, "# entry/A.ets@v2"),
        ("agent", {"id": "fixer", "v": 1, "via": "file:A.ets@v2"}, "# agent-f v1"),
        ("file", {"path": "A.ets", "v": 2, "content": True, "start": 3, "n": 5, "via": "agent:fixer@v1"}, "# entry/A.ets@v2"),
        ("file", {"path": "A.ets", "v": 2, "via": "file:A.ets@v2"}, "# entry/A.ets@v2"),
        ("agent", {"id": "conv-a", "v": 1, "via": "file:A.ets@v2"}, "# agent-c v1"),
        ("agent", {"id": "fixer", "v": 1, "since": 0, "until": 9, "via": "agent:conv-a@v1"}, "# agent-f v1"),
    ]
    p = probe.probe_payload(led, _run_dir(tmp_path, calls, "", "revisits"))
    tree = p["trajectory"]
    by = {n["id"]: n for n in tree["nodes"]}
    root = by[tree["root"]]
    assert root["opened"] == [1, 3, 4] and root["parent"] is None
    assert by["agent:agent-f@1"]["opened"] == [2, 6]
    assert by["agent:agent-f@1"]["parent"] == root["id"]      # 第六步不重挂父节点,不会造环
    assert len(tree["nodes"]) == 3 and len(tree["visits"]) == 6
    assert [t["step"] for t in tree["transitions"]] == [2, 3, 4, 5, 6]
    assert tree["transitions"][2]["from"] == tree["transitions"][2]["to"] == root["id"]
    assert tree["transitions"][-1]["from"] == "agent:agent-c@1"
    assert tree["transitions"][-1]["to"] == "agent:agent-f@1"
    assert tree["transitions"][-1]["relation"] is None       # 真实声明转移与账本边分开
    assert tree["visits"][2]["scope"] == "正文 v2 3-7行"
    assert tree["visits"][-1]["args"]["since"] == 0 and tree["visits"][-1]["args"]["until"] == 9
    assert tree["visits"][-1]["result_ref"] == "toolu_6"
    assert all(v["verified"] and v["status"] == "opened" for v in tree["visits"])


@pytest.mark.parametrize("case,status", [("certain", "true"), ("uncertain", "unknown"),
                                        ("dependency", "unknown"), ("conditional", "unknown"),
                                        ("overlap", "unknown"), ("mention", "unknown"), ("absent", "false")])
def test_route_keeps_read_uncertainty_and_candidate_evidence(tmp_path: Any, case: str, status: str) -> None:
    from dataclasses import replace
    led = _pool(tmp_path)
    path = "/proj/spec/pages/A.md"
    act = next(a for a in led.agents["agent-c"].actions if any(r.path == path for r in a.files))
    ref = next(r for r in act.files if r.path == path)
    if case == "uncertain":
        ref.certain = False
    elif case == "overlap":
        ref.certain = False
        ref.observation_uncertain = True
    elif case == "dependency":
        ref.ev = replace(ref.ev, dep=True)
    elif case in ("conditional", "mention", "absent"):
        act.files = []
        led.mentions[path] = []
        if case == "conditional":
            act.detail["conditional_reads"] = [path]
        elif case == "mention":
            led.mentions[path] = [atoms.Mention(act.ts, act.seq, "agent-c", 1, path, "only mentioned", cls="out")]
    calls = [("agent", {"id": "conv-a", "v": 1, "via": "sessions"}, "# agent-c v1"),
             ("file", {"path": path, "v": 1, "via": "agent:conv-a@v1"}, f"# {path}@v1")]
    tree = probe.probe_payload(led, _run_dir(tmp_path, calls, "", case))["trajectory"]
    tr = tree["transitions"][0]
    assert tr["relation_status"] == status
    assert tr["relation_note"]
    assert tr["relation"] == ("读 v1" if status == "true" else None)
    assert tree["nodes"][1]["edge"] == tr["relation"]  # 候选不升级成真正的读边
    if status != "false":
        assert tr["relation_evidence"][0]["seq"] == act.seq
        assert tr["relation_evidence"][0]["event_id"] == atoms.event_id(led, "agent-c", act.seq)
    if case in ("certain", "uncertain", "dependency", "conditional"):
        assert tr["causal_from"] == "file:" + path + "@1" and tr["causal_to"] == "agent:agent-c@1"
    if status == "unknown":
        assert tr["match"] == "账本关系待核" and "候选" in tr["relation_label"]
    if case == "overlap":
        assert "读取窗口重叠" in tr["relation_label"]
        assert tr["relation_evidence"][0]["observation"]["observation_uncertain"] is True


@pytest.mark.parametrize("case", ["valid", "first", "old", "wrong_target", "failed", "identity", "replayed"])
def test_search_navigation_is_a_verified_event_not_a_third_atom_or_read_edge(tmp_path: Any, case: str) -> None:
    from migloop import via
    led = _pool(tmp_path)
    args = {"q": "spec", "until_ts": "2026-01-01T01:00:00Z"}
    state = via.ViaState()
    output = via.search_return(led, state, args, "# search\nspec hit", [
        {"kind": "file", "key": "/proj/spec/pages/A.md", "v": 1, "seq": 2, "field": "content"}])
    receipt = via.search_receipt(output, args)
    assert receipt
    handle = receipt["hits"][0]["via"]
    if case == "identity":
        receipt["ledger"] = "another-ledger"
        output = output.rpartition("\n" + via.SEARCH_RECEIPT)[0] + "\n" + via.SEARCH_RECEIPT + json.dumps(receipt)
    if case == "old":
        output = "# historical search without receipt"
    calls = [] if case == "first" else [("agent", {"id": "fixer", "v": 1, "via": "sessions"}, "# agent-f v1")]
    calls.append(("search", args, {"text": output, "is_error": True} if case == "failed" else output))
    if case == "replayed":
        calls.append(("search", args, output))
    path = "/proj/entry/A.ets" if case == "wrong_target" else "/proj/spec/pages/A.md"
    calls.append(("file", {"path": path, "v": 1, "via": handle}, f"# {path}@v1"))
    tree = probe.probe_payload(led, _run_dir(tmp_path, calls, "", "search-" + case))["trajectory"]
    assert all(n["kind"] in ("file", "agent") for n in tree["nodes"])
    assert all(n["edge"] is None for n in tree["nodes"])
    if case in ("valid", "first"):
        assert len(tree["transitions"]) == 1
        tr = tree["transitions"][0]
        assert tr["from"] is None and tr["source"] == "search" and tr["relation"] is None
        assert tr["relation_status"] == "not_checked" and tr["causal_from"] is None and tr["causal_to"] is None
        source = tr["search_source"]
        assert source["call_id"] == f"toolu_{source['step']}" and source["result_line"] == source["step"] * 2
        assert "不证明外层" in source["note"] and source["target"]["via"] == handle
        assert tree["visits"][-1]["search_source"] == source
        if case == "valid":
            assert tree["nodes"][-1]["side"] == "unlinked"  # 不挂到从未读过它的 fixer 上
    else:
        assert tree["transitions"] == []
    if case == "identity":
        assert tree["nodes"] == [] and tree["searches"][0]["status"] == "unverified"


def test_search_must_finish_before_the_referencing_call(tmp_path: Any) -> None:
    from migloop import via
    from tests.test_atoms import _write_jsonl
    led = _pool(tmp_path)
    args = {"q": "spec", "until_ts": "2026-01-01T01:00:00Z"}
    output = via.search_return(led, via.ViaState(), args, "search hit", [
        {"kind": "file", "key": "/proj/spec/pages/A.md", "v": 1, "field": "content"}])
    handle = via.search_receipt(output, args)["hits"][0]["via"]
    calls = [("search", args, output), ("file", {"path": "A.md", "v": 1, "via": handle}, "# spec/pages/A.md@v1")]
    run = _run_dir(tmp_path, calls, "", "parallel-search")
    with open(os.path.join(run, "transcript.jsonl"), encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    _write_jsonl(os.path.join(run, "transcript.jsonl"), [rows[0], rows[2], rows[1], rows[3]])
    tree = probe.probe_payload(led, run)["trajectory"]
    assert tree["transitions"] == [] and "搜索来处未核验" in tree["visits"][0]["note"]


def test_failed_missing_and_mismatched_returns_never_open_nodes(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    calls = [
        ("file", {"path": "A.ets", "v": 2, "via": "sessions"}, "⛔ via 不合规"),
        ("agent", {"id": "fixer", "v": 1, "via": "sessions"}, {"text": "transport failed", "is_error": True}),
        ("file", {"path": "A.ets", "v": 2, "via": "sessions"}, None),
        ("file", {"path": "A.ets", "v": 999, "via": "sessions"}, "# entry/A.ets@v2"),
        ("file", {"path": "A.ets", "v": 2, "via": "sessions"}, "old response without a coordinate"),
    ]
    p = probe.probe_payload(led, _run_dir(tmp_path, calls, "", "failures"))
    tree = p["trajectory"]
    assert tree["root"] is None and tree["nodes"] == [] and tree["transitions"] == []
    assert [v["status"] for v in tree["visits"]] == ["rejected", "error", "pending", "unverified", "unverified"]
    assert len(tree["declared"]) == 5
    assert all(not v["verified"] for v in tree["visits"])
    assert tree["visits"][3]["actual_node"] == "file:/proj/entry/A.ets@2"
    assert tree["visits"][3]["requested_node"] == "file:/proj/entry/A.ets@999"
    assert p["steps"][2]["ok"] is False and p["steps"][2]["result_present"] is False
    missing_via = [("file", {"path": "A.ets", "v": 2}, "⛔ via 缺失")]
    only_rejection = probe.probe_payload(led, _run_dir(tmp_path, missing_via, "", "missing-via"))["trajectory"]
    assert only_rejection["mode"] == "via" and only_rejection["nodes"] == []
    assert only_rejection["visits"][0]["status"] == "rejected"


def test_unopened_conclusion_version_remains_a_separate_side_node(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    calls = [("file", {"path": "A.ets", "v": 2, "via": "sessions"}, "# entry/A.ets@v2")]
    tree = probe.probe_payload(led, _run_dir(tmp_path, calls, _block(led), "precise-verdict"))["trajectory"]
    by = {n["id"]: n for n in tree["nodes"]}
    assert by["file:/proj/entry/A.ets@1"]["opened"] == []
    assert by["file:/proj/entry/A.ets@1"]["source"] == "结论"
    assert by["file:/proj/entry/A.ets@1"]["side"] == "unlinked"
    assert by["file:/proj/entry/A.ets@2"]["opened"] == [1]
    # 未查询邻居以精确坐标给 UI,不能用另一版本抵消这个写者。
    assert by["file:/proj/entry/A.ets@2"]["unseen_neighbors"] == [{"kind": "agent", "key": "agent-f", "v": 1}]


def test_unbound_conclusions_do_not_add_nodes_to_the_call_route(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    calls = [("file", {"path": "A.ets", "v": 2, "via": "sessions"}, "# entry/A.ets@v2")]
    report = _block(led).replace(atoms.ledger_identity(led), "another-ledger")
    tree = probe.probe_payload(led, _run_dir(tmp_path, calls, report, "unbound"))["trajectory"]
    assert [n["id"] for n in tree["nodes"]] == ["file:/proj/entry/A.ets@2"]
    assert tree["verification"] == "unverified" and "身份未记录" in tree["verification_note"]
    assert tree["nodes"][0]["fixed"] is False


def test_appears_badges_require_the_exact_returned_version(tmp_path: Any) -> None:
    led = _pool(tmp_path)
    calls = [
        ("file", {"path": "A.ets", "v": 1, "via": "sessions"}, "# entry/A.ets@v1"),
        ("search", {"q": "A.ets", "until_ts": "2026-01-01"}, "entry/A.ets@v2"),
        ("search", {"q": "A.ets", "until_ts": "2026-01-01"}, "entry/A.ets@v10"),
        ("search", {"q": "A.ets", "until_ts": "2026-01-01"}, "entry/A.ets @v1"),
    ]
    tree = probe.probe_payload(led, _run_dir(tmp_path, calls, "", "appears"))["trajectory"]
    assert tree["nodes"][0]["appears"] == [4]


def test_parallel_call_cannot_claim_a_result_that_had_not_returned(tmp_path: Any) -> None:
    from tests.test_atoms import _write_jsonl
    led = _pool(tmp_path)
    run_dir = _run_dir(tmp_path, [], "", "parallel")
    # 两个调用都成功,但第二个调用发出时第一个结果还未返回给模型。
    first = {"type": "tool_use", "id": "first", "name": "mcp__migloop__file",
             "input": {"path": "A.ets", "v": 2, "via": "sessions"}}
    second = {"type": "tool_use", "id": "second", "name": "mcp__migloop__agent",
              "input": {"id": "fixer", "v": 1, "via": "file:A.ets@v2"}}
    _write_jsonl(os.path.join(run_dir, "transcript.jsonl"), [
        {"type": "assistant", "message": {"content": [first, second]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "second", "content": "# agent-f v1"},
            {"type": "tool_result", "tool_use_id": "first", "content": "# entry/A.ets@v2"}]}}
    ])
    p = probe.probe_payload(led, run_dir)
    tree = p["trajectory"]
    assert len(p["steps"]) == 2                            # 原始转录是事实,空 metrics 不能抹掉调用
    assert len(tree["visits"]) == 2 and tree["transitions"] == []
    assert tree["visits"][1]["note"] == "via 指向调用前尚未成功返回的节点"
    assert tree["nodes"][1]["side"] == "unlinked"


def test_transcript_pairs_by_id_and_keeps_missing_result_and_deduplicates_replay(tmp_path: Any) -> None:
    from tests.test_atoms import _write_jsonl
    run_dir = _run_dir(tmp_path, [], "", "ids")
    first = {"type": "tool_use", "id": "a", "name": "mcp__migloop__file", "input": {"path": "A", "v": 1}}
    second = {"type": "tool_use", "id": "b", "name": "mcp__migloop__agent", "input": {"id": "B", "v": 1}}
    _write_jsonl(os.path.join(run_dir, "transcript.jsonl"), [
        {"type": "assistant", "message": {"content": [first, second]}},
        {"type": "assistant", "message": {"content": [first]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "b", "content": [{"type": "text", "text": '{"result": "B result"}'}]}]}}
    ])
    calls = probe._transcript_calls(run_dir)
    assert calls is not None and len(calls) == 2
    assert calls[0]["id"] == "a" and calls[0]["has_result"] is False
    assert calls[1]["id"] == "b" and calls[1]["text"] == "B result" and calls[1]["has_result"] is True
