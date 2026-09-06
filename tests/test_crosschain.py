"""跨会话返修链 —— 生成会话与修复会话的 blame 事件接力,正式链在此成立。

单会话里"生成方在上一轮"的文件 writers 只剩 fixer,不成链;接力后
生成会话的重放终态就是修复会话的 baseline,链与行级归因同时立起来。
"""

from __future__ import annotations

from typing import Any

from migloop.crosschain import build_cross_chains

CWD = "/Users/x/proj"
F = "/Users/x/proj/entry/src/main/ets/pages/A.ets"


def _prior() -> dict[str, Any]:
    return {
        "meta": {"session_id": "01a009fe-aaaa", "cwd": "/Users/x"},
        "agents": [{"agent_id": "g1", "prompt_excerpt": "转换 GuidePage", "result": ""}],
        "lineage": {
            "agents": [{"agent_id": "g1", "desc": "converter GuidePage",
                        "stage": "a2h-execute", "type": "a2h-activity-converter",
                        "spec_reads": ["spec/pages/guide.md"],
                        "android_reads": ["/a/GuideActivity.java"], "n_android": 1}],
            "specs": [{"path": "spec/pages/guide.md", "authors": ["s1"]}],
            "files": []},
    }


def _cur(fixer_type: str = "visual-fixer",
         stage: str = "arkts-visual-verify") -> dict[str, Any]:
    return {
        "meta": {"session_id": "01a021e5-bbbb", "cwd": CWD},
        "agents": [{"agent_id": "f1", "prompt_excerpt": "",
                    "result": "修正引导页布局:栅格断点错误"}],
        "lineage": {
            "agents": [{"agent_id": "f1", "desc": "visual fixer r0",
                        "stage": stage, "type": fixer_type}],
            "specs": [], "files": []},
    }


def _events() -> list[tuple[str, str, str, str, Any]]:
    return [
        ("2026-08-16T10:00:00Z", F, "g1", "write", "l1\nl2\nl3"),
        ("2026-08-21T10:00:00Z", F, "f1", "edits", [("l2", "L2fix", False)]),
    ]


def test_cross_session_chain_with_line_relay() -> None:
    chains = build_cross_chains(_cur(), [_prior()], _events())
    assert len(chains) == 1
    c = chains[0]
    assert c["file"].endswith("A.ets")
    assert c["generator"]["id"] == "g1"
    assert c["generator"]["desc"] == "converter GuidePage"
    assert c["generator"]["spec_reads"] == ["spec/pages/guide.md"]
    assert c["gen_session"] == "01a009fe", "标注生成方来自哪个会话"
    assert c["fixer"]["id"] == "f1"
    assert "栅格断点" in c["fixer"]["note"]
    assert c["lines"] == {"touched": 1, "from": [
        {"id": "g1", "desc": "converter GuidePage", "n": 1}]}, \
        "接力后 no-baseline 消失,被修行归因到生成会话作者"


def test_no_fixer_in_current_session_no_chain() -> None:
    """非修复方由**阶段**决定(execute 及更早),与 type 无关。"""
    chains = build_cross_chains(_cur(stage="a2h-execute"), [_prior()], _events())
    assert chains == []
    # 类型仍叫 fixer 但阶段在 execute 内 —— 照样不成链
    assert build_cross_chains(
        _cur(fixer_type="visual-fixer", stage="a2h-execute"),
        [_prior()], _events()) == []


def test_relay_break_degrades_to_file_level() -> None:
    ev = [("2026-08-16T10:00:00Z", F, "g1", "write", "l1"),
          ("2026-08-21T10:00:00Z", F, "f1", "edits", [("not-there", "x", False)])]
    chains = build_cross_chains(_cur(), [_prior()], ev)
    assert len(chains) == 1
    assert chains[0]["lines"] is None
    assert chains[0]["blame_broken"] == "edit-miss"
    assert chains[0]["generator"]["id"] == "g1", "断链仍按写手序退回文件级生成方"


def test_fixer_only_files_do_not_chain() -> None:
    ev = [("2026-08-21T10:00:00Z", F, "f1", "write", "l1")]
    assert build_cross_chains(_cur(), [_prior()], ev) == []


def test_prior_root_discovery_same_tree_and_earlier_only(monkeypatch, tmp_path) -> None:
    """前序发现:同工程树(含父子 cwd) + 文件名时间早于当前;其他工程不掺。"""
    from types import SimpleNamespace

    from migloop import crosschain
    from migloop.adapters import codex

    def mk(name: str) -> str:
        f = tmp_path / name
        f.write_text("{}", encoding="utf-8")
        return str(f)

    cur = mk("rollout-2026-08-21T09-18-20-cur.jsonl")
    early_parent = mk("rollout-2026-08-16T17-54-23-gen.jsonl")
    early_other = mk("rollout-2026-08-15T10-00-00-other.jsonl")
    later_same = mk("rollout-2026-08-22T10-00-00-late.jsonl")
    cwds = {early_parent: "/Users/x", early_other: "/Users/elsewhere",
            later_same: "/Users/x/proj", cur: "/Users/x/proj"}
    monkeypatch.setattr(codex, "iter_sessions", lambda root: [
        SimpleNamespace(path=p) for p in (cur, early_parent, early_other, later_same)])
    monkeypatch.setattr(codex, "session_summary", lambda p: {"cwd": cwds.get(p, "")})
    got = crosschain.find_prior_codex_roots(cur, "/Users/x/proj")
    assert got == [early_parent], "父目录 cwd 算同树;更晚的、别的工程的都排除"


def test_later_root_discovery_mirror(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from migloop import crosschain
    from migloop.adapters import codex

    def mk(name: str) -> str:
        f = tmp_path / name
        f.write_text("{}", encoding="utf-8")
        return str(f)

    cur = mk("rollout-2026-08-16T17-54-23-gen.jsonl")
    later_same = mk("rollout-2026-08-21T09-18-20-fix.jsonl")
    earlier = mk("rollout-2026-08-15T10-00-00-old.jsonl")
    cwds = {later_same: "/Users/x/proj", earlier: "/Users/x/proj", cur: "/Users/x"}
    monkeypatch.setattr(codex, "iter_sessions", lambda root: [
        SimpleNamespace(path=p) for p in (cur, later_same, earlier)])
    monkeypatch.setattr(codex, "session_summary", lambda p: {"cwd": cwds.get(p, "")})
    assert crosschain.find_later_codex_roots(cur, "/Users/x") == [later_same]


def test_journey_rounds_shape() -> None:
    """迁移全程:多轮 trace(时间序)归约成轮卡数据 —— 阶段/规模/修复方都在。"""
    from migloop.crosschain import journey_rounds

    gen = {
        "meta": {"session_id": "01a009fe-x", "cwd": "/u/x",
                 "started_at": "2026-08-16T09:55:00Z", "ended_at": "2026-08-17T03:12:00Z"},
        "stages": [{"stage": "setup", "label": "Setup", "duration_ms": 60000},
                   {"stage": "a2h-spec", "label": "Spec", "duration_ms": 3600000}],
        "totals": {"subagent_transcripts": 54},
        "agents": [{"agent_id": "g", "type": "a2h-activity-converter"}],
        "lineage": {"agents": [], "specs": [],
                    "files": [{"path": "a.ets", "kind": "ets", "writers": ["g"]}]},
    }
    ver = {
        "meta": {"session_id": "01a021e5-y", "cwd": "/u/x/proj",
                 "started_at": "2026-08-21T01:19:00Z", "ended_at": "2026-08-22T15:24:00Z"},
        "stages": [{"stage": "arkts-visual-verify", "label": "Visual Verify",
                    "duration_ms": 7200000}],
        "totals": {"subagent_transcripts": 60},
        "agents": [{"agent_id": "f", "type": "visual-fixer"}],
        "lineage": {"agents": [], "specs": [], "files": []},
    }
    rounds = journey_rounds([gen, ver])
    assert [r["sid8"] for r in rounds] == ["01a009fe", "01a021e5"]
    assert rounds[0]["stages"] == [{"label": "Setup", "duration_ms": 60000},
                                   {"label": "Spec", "duration_ms": 3600000}]
    assert rounds[0]["agents"] == 54 and rounds[0]["ets_files"] == 1
    assert rounds[0]["fixers"] == 0 and rounds[1]["fixers"] == 1
    assert rounds[0]["started_at"] == "2026-08-16T09:55:00Z"
    assert rounds[1]["project"] == "proj"


def test_chain_carries_fixer_diff() -> None:
    """抽屉「改了什么」:链带修复方的 diff 摘要,生成方的写入不混入。"""
    chains = build_cross_chains(_cur(), [_prior()], _events())
    d = chains[0]["diff"]
    assert len(d) == 1 and d[0]["by"] == "f1"
    assert "- l2" in d[0]["text"] and "+ L2fix" in d[0]["text"]


def test_trace_graph_full_dag() -> None:
    """全量调用图:节点 = agents+files(绝对路径归一),边 = 台账读写实录,
    跨会话合并,fixer 按当前会话判定 —— 页面吃这张图,不吃摘要投影。"""
    from migloop.crosschain import build_trace_graph

    gen = {
        "meta": {"session_id": "01a009fe-x", "cwd": "/u/HUAWEI"},
        "agents": [{"agent_id": "g1", "prompt_excerpt": "转换", "result": "done"}],
        "lineage": {
            "agents": [{"agent_id": "g1", "desc": "converter", "stage": "a2h-execute",
                        "type": "worker"}],
            "specs": [{"path": "AIPPT_830_test/spec/f.md", "kind": "page",
                       "authors": ["s1"], "read_by": ["g1"]}],
            "android": [{"path": "AIPPT/app/A.kt", "readers": ["s1"]}],
            "files": [{"path": "AIPPT_830_test/entry/X.ets", "kind": "ets",
                       "writers": ["g1"], "readers": []}]},
    }
    ver = {
        "meta": {"session_id": "01a021e5-y", "cwd": "/u/HUAWEI/AIPPT_830_test"},
        "agents": [{"agent_id": "f1", "result": "fixed"}],
        "lineage": {
            "agents": [{"agent_id": "f1", "desc": "vf", "stage": "arkts-visual-verify",
                        "type": "visual-fixer"}],
            "specs": [], "android": [],
            "files": [{"path": "entry/X.ets", "kind": "ets",
                       "writers": ["f1"], "readers": ["f1"]}]},
    }
    g = build_trace_graph(ver, [gen])
    nodes, edges = g["nodes"], {tuple(e) for e in g["edges"]}
    # 文件绝对路径归一:两个会话的 X.ets 是同一节点
    fx = "/u/HUAWEI/AIPPT_830_test/entry/X.ets"
    assert fx in nodes and nodes[fx]["kind"] == "ets"
    assert nodes["/u/HUAWEI/AIPPT_830_test/spec/f.md"]["kind"] == "spec"
    assert nodes["/u/HUAWEI/AIPPT/app/A.kt"]["kind"] == "src"
    assert nodes["f1"]["kind"] == "fixer", "当前会话 verify 阶段 → fixer"
    assert nodes["g1"]["kind"] == "agent"
    # 边:数据流方向(输入文件→agent,agent→输出文件)
    assert ("/u/HUAWEI/AIPPT/app/A.kt", "s1") in edges
    assert ("s1", "/u/HUAWEI/AIPPT_830_test/spec/f.md") in edges
    assert ("/u/HUAWEI/AIPPT_830_test/spec/f.md", "g1") in edges
    assert ("g1", fx) in edges
    assert ("f1", fx) in edges and (fx, "f1") in edges


def test_chain_lists_all_generators_and_fixers_individually() -> None:
    """多方不共享文案:每个生成方有自己的派发指令,每轮修复方有自己的修因。"""
    prior = _prior()
    prior["agents"].append({"agent_id": "g2", "prompt_excerpt": "补投影页", "result": ""})
    prior["lineage"]["agents"].append(
        {"agent_id": "g2", "desc": "converter G2", "stage": "a2h-execute",
         "type": "a2h-activity-converter"})
    cur = _cur()
    cur["agents"].append({"agent_id": "f2", "prompt_excerpt": "",
                          "result": "round1:再修布局余量"})
    cur["lineage"]["agents"].append(
        {"agent_id": "f2", "desc": "visual fixer r1", "stage": "arkts-visual-verify",
         "type": "visual-fixer"})
    ev = [
        ("2026-08-16T10:00:00Z", F, "g1", "write", "l1\nl2\nl3"),
        ("2026-08-16T11:00:00Z", F, "g2", "edits", [("l3", "L3", False)]),
        ("2026-08-21T10:00:00Z", F, "f1", "edits", [("l2", "L2fix", False)]),
        ("2026-08-21T12:00:00Z", F, "f2", "edits", [("L2fix", "L2fix2", False)]),
    ]
    c = build_cross_chains(cur, [prior], ev)[0]
    # 行级 trim:g2 写的 l3 没被修 —— 它不在这条返修链里(写过文件≠写过被改的行)
    assert [g["id"] for g in c["generators"]] == ["g1"]
    assert c["generators"][0]["prompt"] == "转换 GuidePage"
    assert [f["id"] for f in c["fixers_all"]] == ["f1", "f2"]
    assert "栅格断点" in c["fixers_all"][0]["note"]
    assert "布局余量" in c["fixers_all"][1]["note"]
    # diff 按轮标注归属
    assert {d["by"] for d in c["diff"]} == {"f1", "f2"}
    assert all(d.get("by_desc") for d in c["diff"])


def test_generators_fall_back_to_all_writers_when_blame_broken() -> None:
    """无行级(断链)时退回文件级全写手 —— 诚实降级,不瞎 trim。"""
    ev = [("2026-08-16T10:00:00Z", F, "g1", "write", "l1"),
          ("2026-08-21T10:00:00Z", F, "f1", "edits", [("nope", "x", False)])]
    c = build_cross_chains(_cur(), [_prior()], ev)[0]
    assert c["blame_broken"] == "edit-miss"
    assert [g["id"] for g in c["generators"]] == ["g1"]


def _mk_cc(dirp, sid, ts):
    f = dirp / f"{sid}.jsonl"
    f.write_text('{"type":"user","timestamp":"' + ts + '","cwd":"C:/p","sessionId":"'
                 + sid + '","message":{"content":"x"}}\n', encoding="utf-8")
    return str(f)


def test_claude_prior_and_later_roots_by_first_ts(tmp_path) -> None:
    """CC 同工程 = 同 transcript 目录;时间序用首条记录 timestamp
    (文件 mtime 在拷贝/归档后不可靠)。"""
    from migloop import crosschain

    a = _mk_cc(tmp_path, "aaaa1111-0000-4000-8000-000000000001", "2026-08-16T09:00:00Z")
    b = _mk_cc(tmp_path, "bbbb2222-0000-4000-8000-000000000002", "2026-08-20T09:00:00Z")
    c = _mk_cc(tmp_path, "cccc3333-0000-4000-8000-000000000003", "2026-08-22T09:00:00Z")
    (tmp_path / "bbbb2222-0000-4000-8000-000000000002").mkdir()  # 子代理目录不算会话
    assert crosschain.find_prior_claude_roots(b) == [a]
    assert crosschain.find_later_claude_roots(b) == [c]
    assert crosschain.collect_claude_project_roots(b) == [a, b, c]
