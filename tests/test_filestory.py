"""文件编年史引擎 + 生成链闭包 —— 行为契约。

引擎:五种事件(全文写/edit/opaque 写/派生写/读取,读取可携带全文快照即观测)
→ 每文件的版本序列(带真 diff 与档位标)+ 读取记录(绑版本)+ 断点清单。
闭包:从被修文件的版本出发,按「累积读边」离线算全生成 DAG;披露归属在闭包
收敛后按「被拉入的出现」切区间。每条用例对应设计裁定或 0723 复盘验证过的场景。
"""

from __future__ import annotations

from migloop.filestory import (
    Ev,
    build_generation_dag,
    build_stories,
)

_SEQ = [0]


def ev(ts: str, kind: str, path: str, agent: str = "a1", **kw: object) -> Ev:
    _SEQ[0] += 1
    return Ev(ts=ts, seq=_SEQ[0], kind=kind, path=path, agent=agent, **kw)  # type: ignore[arg-type]


# ═══════════════ 引擎:版本与 diff ═══════════════

def test_wfull_creation_then_true_diff() -> None:
    st = build_stories([
        ev("T01", "wfull", "a.md", content="line1\nline2\n"),
        ev("T02", "wfull", "a.md", content="line1\nline2x\n"),
    ])["a.md"]
    v1, v2 = st.versions
    assert (v1.v, v1.source, v1.diff_kind) == (1, "full", "creation")
    assert (v2.v, v2.diff_kind) == (2, "true")
    assert "+line2x" in (v2.diff or "") and "-line2" in (v2.diff or "")


def test_edit_applies_native_diff() -> None:
    st = build_stories([
        ev("T01", "wfull", "a.md", content="alpha\nbeta\n"),
        ev("T02", "edit", "a.md", old="beta", new="gamma"),
    ])["a.md"]
    v2 = st.versions[1]
    assert (v2.source, v2.diff_kind) == ("delta", "native")
    assert v2.content == "alpha\ngamma\n"
    assert st.breaks == []


def test_edit_miss_breaks_but_keeps_native_diff_and_reanchors() -> None:
    st = build_stories([
        ev("T01", "wfull", "a.md", content="alpha\n"),
        ev("T02", "edit", "a.md", old="不存在的锚", new="x"),      # 实录外改过 → miss
        ev("T03", "read", "a.md", content="omega\n", full=True),   # 观测重锚
        ev("T04", "edit", "a.md", old="omega", new="omega2"),      # 重锚后继续应用
    ])["a.md"]
    assert [b.kind for b in st.breaks] == ["edit-miss"]
    miss_v = st.versions[1]
    assert miss_v.content is None and miss_v.diff_kind == "native"  # 盲,但 diff 仍可点开
    anchor_v = st.versions[2]
    assert anchor_v.by == "__outband__" and anchor_v.content == "omega\n"
    assert st.versions[3].content == "omega2\n"                     # 段间续命


def test_opaque_sealed_by_observation_interval_diff() -> None:
    st = build_stories([
        ev("T01", "wfull", "a.md", content="v1\n"),
        ev("T02", "wopaque", "a.md", agent="gen"),
        ev("T03", "read", "a.md", content="v2\n", full=True, agent="reader"),
    ])["a.md"]
    sealed = st.versions[1]
    assert (sealed.by, sealed.source) == ("gen", "opaque")
    assert sealed.sealed and sealed.content == "v2\n"
    assert sealed.diff_kind == "interval" and "+v2" in (sealed.diff or "")
    assert len(st.versions) == 2                     # 观测封口,不另立版本


def test_multiple_opaque_collapse() -> None:
    st = build_stories([
        ev("T01", "wfull", "a.md", content="v1\n"),
        ev("T02", "wopaque", "a.md", agent="g1"),
        ev("T03", "wopaque", "a.md", agent="g2"),
        ev("T04", "read", "a.md", content="v3\n", full=True),
    ])["a.md"]
    assert st.versions[2].diff_kind == "collapsed"   # 区间 diff 有,归属糊
    assert st.versions[1].content is None            # 中间那笔永远未知


def test_observation_matching_state_binds_read_no_new_version() -> None:
    st = build_stories([
        ev("T01", "wfull", "a.md", content="same\n"),
        ev("T02", "read", "a.md", content="same\n", full=True, agent="r"),
    ])["a.md"]
    assert len(st.versions) == 1
    assert st.reads[-1].version == 1 and st.reads[-1].certain


def test_observation_mismatch_records_outband() -> None:
    st = build_stories([
        ev("T01", "wfull", "a.md", content="known\n"),
        ev("T02", "read", "a.md", content="tampered\n", full=True),
    ])["a.md"]
    assert [b.kind for b in st.breaks] == ["outband-change"]
    v2 = st.versions[1]
    assert v2.by == "__outband__" and v2.diff_kind == "true"
    assert st.reads[-1].version == 2


def test_external_input_first_seen_by_read() -> None:
    st = build_stories([
        ev("T01", "read", "AIPPT_spec.md", content="ref doc\n", full=True,
           start=1, n=1),
    ])["AIPPT_spec.md"]
    v1 = st.versions[0]
    assert v1.by == "__external__" and v1.diff_kind == "external" and v1.diff is None
    assert st.reads[0].version == 1


def test_plain_read_of_unknown_state_uncertain() -> None:
    st = build_stories([
        ev("T01", "wopaque", "a.md"),
        ev("T02", "read", "a.md"),
    ])["a.md"]
    assert st.reads[0].certain is False
    assert st.reads[0].version == 1                  # 绑到最近版本,但 certain=False


def test_read_span_preserved() -> None:
    st = build_stories([
        ev("T01", "wfull", "a.md", content="1\n2\n3\n4\n5\n"),
        ev("T02", "read", "a.md", start=2, n=3),
    ])["a.md"]
    r = st.reads[0]
    assert (r.start, r.n, r.version) == (2, 3, 1)


def test_derived_copy_resolves_source_state() -> None:
    st = build_stories([
        ev("T01", "wfull", "tpl.md", content="template body\n", agent="g"),
        ev("T02", "wderived", "page.md", src="tpl.md", agent="g"),
    ])
    v1 = st["page.md"].versions[0]
    assert v1.source == "derived" and v1.content == "template body\n"
    assert v1.diff_kind == "creation"


def test_derived_unknown_source_stays_unknown() -> None:
    st = build_stories([
        ev("T01", "wopaque", "tpl.md"),
        ev("T02", "wderived", "page.md", src="tpl.md"),
    ])
    assert st["page.md"].versions[0].content is None


# ═══════════════ 闭包:找全 ═══════════════

def _dag_case_cumulative() -> tuple:
    """★用户点破的场景:A 早年读 early.md,先写了别的(未被拉入),很晚才写
    与被修文件相关的 y.ets。累积边必须把 early.md 拉进闭包。"""
    events = [
        ev("T01", "read", "early.md", agent="A", content="early ref\n", full=True),
        ev("T02", "wfull", "unrelated.md", agent="A", content="x\n"),      # 不入链
        ev("T03", "read", "late.md", agent="A", content="late ref\n", full=True),
        ev("T04", "wfull", "y.ets", agent="A", content="code\n"),          # 被拉入
    ]
    stories = build_stories(events)
    dag = build_generation_dag(stories, "y.ets")
    return stories, dag


def test_closure_is_cumulative_not_interval() -> None:
    _st, dag = _dag_case_cumulative()
    vids = set(dag.version_nodes)
    assert ("early.md", 1) in vids       # 早年读,靠累积边进树
    assert ("late.md", 1) in vids
    assert ("unrelated.md", 1) not in vids   # 没被读传导,不进


def test_single_occurrence_owns_all_reads() -> None:
    _st, dag = _dag_case_cumulative()
    occs = [o for o in dag.occurrences if o[0] == "A"]
    assert len(occs) == 1                # A 只被拉入一次
    owned = dag.owned_reads[occs[0]]
    assert {(p, v) for p, v, _ts in owned} == {("early.md", 1), ("late.md", 1)}
    assert dag.inherited[occs[0]] == (0, None)   # 退化:穷尽挂载


def test_partition_across_two_pulled_occurrences() -> None:
    """A 两笔写各经不同文件入树 → 出现两次;读取按被拉入出现的区间切归属。"""
    events = [
        ev("T01", "read", "r1.md", agent="A", content="one\n", full=True),
        ev("T02", "wfull", "mid.ets", agent="A", content="m\n"),
        ev("T03", "read", "r2.md", agent="A", content="two\n", full=True),
        ev("T04", "wfull", "top.ets", agent="A", content="t\n"),
        ev("T05", "read", "mid.ets", agent="C", content="m\n", full=True),
        ev("T06", "read", "top.ets", agent="C", content="t\n", full=True),
        ev("T07", "wfull", "root.ets", agent="C", content="r\n"),
    ]
    dag = build_generation_dag(build_stories(events), "root.ets")
    a_occs = sorted(o for o in dag.occurrences if o[0] == "A")
    assert len(a_occs) == 2
    w_mid, w_top = a_occs
    assert {(p, v) for p, v, _ in dag.owned_reads[w_mid]} == {("r1.md", 1)}
    assert {(p, v) for p, v, _ in dag.owned_reads[w_top]} == {("r2.md", 1)}
    assert dag.inherited[w_mid] == (0, None)
    assert dag.inherited[w_top] == (1, w_mid)        # 沿用 1 项,指回上一次出现


def test_occurrence_pulled_only_via_version_read() -> None:
    """出现入树的唯一途径:它产出的版本被闭包内的读边指到。"""
    events = [
        ev("T01", "wfull", "p.ets", agent="A", content="p1\n"),
        ev("T02", "wfull", "p.ets", agent="A", content="p2\n"),
        ev("T03", "read", "p.ets", agent="B", content="p2\n", full=True),   # 只读到 v2
        ev("T04", "wfull", "root.ets", agent="B", content="r\n"),
    ]
    dag = build_generation_dag(build_stories(events), "root.ets")
    a_occs = [o for o in dag.occurrences if o[0] == "A"]
    assert len(a_occs) == 1                          # 只有写 v2 的那次
    assert ("p.ets", 2) in dag.version_nodes
    assert ("p.ets", 1) not in dag.version_nodes     # v1 没被读,不入树


def test_shared_version_node() -> None:
    events = [
        ev("T01", "read", "spec.md", agent="A", content="s\n", full=True),
        ev("T02", "wfull", "a.ets", agent="A", content="a\n"),
        ev("T03", "read", "spec.md", agent="B", content="s\n", full=True),
        ev("T04", "wfull", "b.ets", agent="B", content="b\n"),
        ev("T05", "read", "a.ets", agent="C", content="a\n", full=True),
        ev("T06", "read", "b.ets", agent="C", content="b\n", full=True),
        ev("T07", "wfull", "root.ets", agent="C", content="r\n"),
    ]
    dag = build_generation_dag(build_stories(events), "root.ets")
    spec_edges = [e for e in dag.edges if e[0] == ("spec.md", 1)]
    assert len(spec_edges) == 2                      # 一个节点,两条边
    assert len([v for v in dag.version_nodes if v[0] == "spec.md"]) == 1


def test_external_versions_are_leaves() -> None:
    _st, dag = _dag_case_cumulative()
    early = dag.version_nodes[("early.md", 1)]
    assert early.by == "__external__"
    assert not any(p[1] == ("early.md", 1) for p in dag.produced)  # 没有产出它的出现


def test_dep_edge_labeled() -> None:
    events = [
        ev("T01", "wfull", "tpl.md", agent="G", content="t\n"),
        ev("T02", "wderived", "page.ets", src="tpl.md", agent="G", dep=True),
        ev("T03", "read", "page.ets", agent="B", content="t\n", full=True),
        ev("T04", "wfull", "root.ets", agent="B", content="r\n"),
    ]
    dag = build_generation_dag(build_stories(events), "root.ets")
    kinds = {e[2] for e in dag.edges if e[0] == ("tpl.md", 1)}
    assert "dep" in kinds                            # cp 源:依赖边,标注区分


def test_mutual_write_read_no_cycle_and_terminates() -> None:
    events = [
        ev("T01", "wfull", "f.md", agent="A", content="f1\n"),
        ev("T02", "read", "f.md", agent="B", content="f1\n", full=True),
        ev("T03", "wfull", "g.md", agent="B", content="g1\n"),
        ev("T04", "read", "g.md", agent="A", content="g1\n", full=True),
        ev("T05", "wfull", "f.md", agent="A", content="f2\n"),
        ev("T06", "read", "f.md", agent="C", content="f2\n", full=True),
        ev("T07", "wfull", "root.ets", agent="C", content="r\n"),
    ]
    dag = build_generation_dag(build_stories(events), "root.ets")
    # f@2 ← A@T05 ← g@1 ← B@T03 ← f@1 ← A@T01(累积:A@T05 也读过 f@1? A 写的,读自己
    # 不入边由收集侧裁;引擎层面:版本链沿时间只退不进,节点集必含 f@1 与 f@2 两个节点
    assert ("f.md", 1) in dag.version_nodes and ("f.md", 2) in dag.version_nodes
    # 无环由时间单调保证:任何边 版本ts < 出现ts,出现ts = 其产出版本 ts


def test_dag_payload_slim_and_diff_on_demand() -> None:
    from migloop.filestory import dag_payload, diff_payload

    _SEQ[0] = 0
    events = [
        ev("T01", "read", "spec/s.md", agent="A", content="s\n", full=True),
        ev("T02", "wfull", "src/x.ets", agent="A", content="x1\n"),
        ev("T03", "edit", "src/x.ets", agent="A", old="x1", new="x2"),
    ]
    stories = build_stories(events)
    pl = dag_payload(stories, "x.ets")            # 后缀即可解析
    assert pl is not None and pl["root"] == "src/x.ets"
    vc, oc = pl["vcols"], pl["ocols"]
    vs = {(row[vc.index("path")], row[vc.index("v")]): row for row in pl["versions"]}
    row2 = vs[("src/x.ets", 2)]
    assert row2[vc.index("diff_kind")] == "native"
    assert row2[vc.index("has_diff")] == 1        # 瘦身:正文不进 DAG 载荷
    occs = {row[oc.index("agent")]: row for row in pl["occurrences"]}
    owned_vi = occs["A"][oc.index("owned_vi")]
    owned_paths = {pl["versions"][vi][vc.index("path")] for vi in owned_vi}
    assert owned_paths <= {"spec/s.md"}
    d = diff_payload(stories, "x.ets", 2)         # 正文按需取
    assert d is not None and "+x2" in (d["diff"] or "")
    assert diff_payload(stories, "x.ets", 99) is None


def test_determinism() -> None:
    def build() -> object:
        _SEQ[0] = 0
        events = [
            ev("T01", "read", "s.md", agent="A", content="s\n", full=True),
            ev("T02", "wfull", "x.ets", agent="A", content="x\n"),
            ev("T03", "read", "x.ets", agent="B", content="x\n", full=True),
            ev("T04", "wfull", "root.ets", agent="B", content="r\n"),
        ]
        d = build_generation_dag(build_stories(events), "root.ets")
        return (sorted(d.version_nodes), sorted(d.occurrences),
                sorted(map(str, d.edges)), sorted(map(str, d.produced)))
    assert build() == build()


# ═══════════════ 逐行签名与链构建(旧 blame/crosschain 的替代) ═══════════════

def _chain_stories():  # type: ignore[no-untyped-def]
    return build_stories([
        ev("T01", "wfull", "p/A.ets", agent="agent-gen1",
           content="l1\nl2\nl3\nl4\n"),
        ev("T02", "edit", "p/A.ets", agent="agent-gen2", old="l3", new="l3g"),
        ev("T03", "edit", "p/A.ets", agent="agent-fixer", old="l2", new="l2f"),
        ev("T04", "edit", "p/A.ets", agent="agent-fixer", old="l3g", new="l3f"),
        ev("T05", "wfull", "p/B.md", agent="agent-gen1", content="doc\n"),
    ])


def test_line_owners_track_authorship_across_versions() -> None:
    from migloop.filestory import line_owners
    st = _chain_stories()["p/A.ets"]
    owners_final = line_owners(st)[-1]
    assert owners_final == ["agent-gen1", "agent-fixer", "agent-fixer", "agent-gen1"]


def test_line_owners_sealed_interval_attributes_to_opaque_author() -> None:
    from migloop.filestory import line_owners
    st = build_stories([
        ev("T01", "wfull", "a.md", agent="w1", content="x\n"),
        ev("T02", "wopaque", "a.md", agent="w2"),                  # 内容失联
        ev("T03", "read", "a.md", content="x\ny\n", full=True),    # 观测封口→interval
    ])["a.md"]
    assert line_owners(st)[1] == ["w1", "w2"]  # 封口后内容已知:老行沿承,新行归 opaque 作者


def test_line_owners_unsealed_opaque_stays_unknown() -> None:
    from migloop.filestory import line_owners
    st = build_stories([
        ev("T01", "wfull", "a.md", agent="w1", content="x\n"),
        ev("T02", "wopaque", "a.md", agent="w2"),                  # 永不封口
    ])["a.md"]
    per = line_owners(st)
    assert per[1] == []                        # 未知版:不猜,不清零历史


def test_fixed_line_origins_attributes_replaced_lines() -> None:
    from migloop.filestory import fixed_line_origins
    st = _chain_stories()["p/A.ets"]
    touched, origins, other, broken = fixed_line_origins(st, [3, 4])
    assert broken is None
    assert touched == 2                       # l2、l3g 各一行
    assert origins == {"agent-gen1": 1, "agent-gen2": 1}
    assert other == {}


def test_fixed_line_origins_classifies_unattributable_lines() -> None:
    from migloop.filestory import build_fix_chains, fixed_line_origins
    st = build_stories([
        ev("T01", "wfull", "p/D.ets", agent="agent-g", content="a\nb\n"),
        ev("T02", "edit", "p/D.ets", agent="agent-f", old="b", new="b1"),   # 改别人
        ev("T03", "edit", "p/D.ets", agent="agent-f", old="b1", new="b2"),  # 改自己
    ])
    _t, origins, other, _b = fixed_line_origins(st["p/D.ets"], [2, 3])
    assert origins == {"agent-g": 1} and other == {"self": 1}
    # 全是"纯新增+改自己":origins 空,broken 里报出分类而不是空白
    st2 = build_stories([
        ev("T01", "wfull", "p/E.ets", agent="agent-g", content="a\n"),
        ev("T02", "edit", "p/E.ets", agent="agent-f", old="a", new="a\nx"),   # 纯新增
        ev("T03", "edit", "p/E.ets", agent="agent-f", old="x", new="x2"),     # 改自己
    ])
    chains = build_fix_chains(st2, {}, {"g": False, "f": True})
    c = chains[0]
    assert c["lines"] is None
    assert "纯新增" in c["blame_broken"] and "修复方改自己的行" in c["blame_broken"]
    assert [g["id"] for g in c["generators"]] == ["agent-g"]   # 树退回文件级写手


def test_build_fix_chains_engine_only() -> None:
    from migloop.filestory import build_fix_chains
    meta = {"gen1": {"desc": "布局转换", "stage": "conv"},
            "gen2": {"desc": "风险切片", "stage": "slice"},
            "fixer": {"desc": "视觉修复", "stage": "verify", "note": "圆角错"}}
    chains = build_fix_chains(_chain_stories(), meta,
                              {"gen1": False, "gen2": False, "fixer": True})
    assert len(chains) == 1                   # B.md 非 .ets、且无修复方写入
    c = chains[0]
    assert c["file"] == "A.ets" and c["fix_versions"] == [3, 4]
    assert c["fixer"]["desc"] == "视觉修复"
    ids = [g["id"] for g in c["generators"]]
    assert set(ids) == {"agent-gen1", "agent-gen2"}   # 被修行原作者,非全部写手
    assert c["lines"] is not None and c["lines"]["touched"] == 2


def test_dag_payload_flags_pre_edit_reads() -> None:
    from migloop.filestory import dag_payload
    st = build_stories([
        ev("T00", "wfull", "root.ets", agent="agent-g0", content="r\n"),
        ev("T01", "wfull", "p/S.md", agent="agent-w", content="s\n"),
        ev("T02", "wfull", "p/T.ets", agent="agent-g", content="t\n"),
        ev("T03", "read", "p/S.md", agent="agent-g"),      # 信息读:g 没写过 S
        ev("T04", "read", "p/T.ets", agent="agent-g"),     # 写前必读:g 写过 T
        ev("T05", "edit", "root.ets", agent="agent-g", old="r", new="r2"),
    ])
    j = dag_payload(st, "root.ets")
    assert j is not None
    oc = {c: i for i, c in enumerate(j["ocols"])}
    vc = {c: i for i, c in enumerate(j["vcols"])}
    row = next(r for r in j["occurrences"]
               if r[oc["agent"]] == "agent-g" and r[oc["owned_vi"]])
    flagged = {j["versions"][vi][vc["path"]]: f
               for vi, f in zip(row[oc["owned_vi"]], row[oc["owned_self01"]],
                                strict=True)}
    assert flagged["p/S.md"] == 0 and flagged["p/T.ets"] == 1


def test_agent_story_payload_flags_pre_edit_reads() -> None:
    from migloop.filestory import agent_story_payload
    st = build_stories([
        ev("T01", "wfull", "p/S.md", agent="agent-w", content="s\n"),
        ev("T02", "wfull", "p/T.ets", agent="agent-g", content="t\n"),
        ev("T03", "read", "p/S.md", agent="agent-g"),
        ev("T04", "read", "p/T.ets", agent="agent-g"),
        ev("T05", "wfull", "p/U.ets", agent="agent-g", content="u\n"),
    ])
    j = agent_story_payload(st, "g")
    assert j is not None
    news = {r[0]: r[3] for o in j["occurrences"] for r in o["news"]}
    assert news["p/S.md"] == 0 and news["p/T.ets"] == 1


def test_build_fix_chains_falls_back_when_lines_unattributable() -> None:
    from migloop.filestory import build_fix_chains
    st = build_stories([
        ev("T01", "wfull", "p/C.ets", agent="agent-g", content="a\nb\n"),
        ev("T02", "wopaque", "p/C.ets", agent="agent-f"),          # 修复=脚本落盘,内容未知
    ])
    chains = build_fix_chains(st, {}, {"g": False, "f": True})
    c = chains[0]
    assert c["lines"] is None and c["blame_broken"] == "content-unknown"
    assert [g["id"] for g in c["generators"]] == ["agent-g"]       # 退回文件级写手


def test_build_fix_chains_lists_fix_phase_created_code_as_missing_generation() -> None:
    """用户口径(2026-09-04):修复期新建的、不在测试目录下的代码文件也是返修 —— 生成期少了一个文件,
    修复方补建了(漏生成)。生成方标「生成期未产出」;verify 自建的测试文件(ohosTest / .test.ets)不进链。"""
    from migloop.filestory import build_fix_chains
    st = build_stories([
        ev("T01", "wfull", "p/entry/src/main/ets/A.ets", agent="agent-g", content="a\n"),
        ev("T03", "wfull", "p/entry/src/main/ets/util/New.ets", agent="agent-f", content="n\n", aver=1),
        ev("T04", "wfull", "p/entry/src/main/ets/util/New.ets", agent="agent-f", content="m\n", aver=2),
        ev("T03", "wfull", "p/entry/src/ohosTest/ets/test/X.test.ets", agent="agent-f", content="t\n"),
        ev("T03", "wfull", "p/entry/src/main/ets/test/Helper.ets", agent="agent-f", content="h\n"),
    ])
    chains = build_fix_chains(st, {}, {"g": False, "f": True}, fix_after="T02")
    assert [(c["file"], c["kind"]) for c in chains] == [("New.ets", "created")]
    c = chains[0]
    assert c["generator"]["id"] is None and "未产出" in c["generator"]["desc"]
    assert c["generators"] == [] and c["lines"] is None and c["gen_at"] is None
    assert c["fix_versions"] == [1, 2] and c["fixer"]["id"] == "agent-f"
    assert c["fixers_all"][0]["vers"] == [1, 2]
    # 生成过又被改的照旧是 rework
    st2 = build_stories([
        ev("T01", "wfull", "p/entry/src/main/ets/A.ets", agent="agent-g", content="a\n"),
        ev("T03", "wfull", "p/entry/src/main/ets/A.ets", agent="agent-f", content="b\n"),
    ])
    assert [(c["file"], c["kind"]) for c in build_fix_chains(st2, {}, {"g": False, "f": True}, fix_after="T02")] \
        == [("A.ets", "rework")]


def test_build_fix_chains_fixer_is_the_first_fix_writer_in_time() -> None:
    """DiceRoller EntryAbility.ets:UI-T Step3(T+4:50)先改、ECAT fix-uitest(T+6:53)后改,链却报修复方是
    ECAT、修复于 T+6:53 —— 修复方曾按 id 字母序取第一个。修复方 = 修复侧第一笔写者,fixers_all 按首次
    修复先后排;rework 与 created 两种链同一规则。"""
    from migloop.filestory import build_fix_chains
    st = build_stories([
        ev("T01", "wfull", "p/entry/src/main/ets/A.ets", agent="agent-g", content="a\n"),
        ev("T03", "wfull", "p/entry/src/main/ets/A.ets", agent="agent-z-early", content="a\nb\n", aver=1),
        ev("T04", "wfull", "p/entry/src/main/ets/A.ets", agent="agent-a-late", content="a\nb\nc\n", aver=1),
        ev("T03", "wfull", "p/entry/src/main/ets/util/New.ets", agent="agent-z-early", content="n\n", aver=2),
        ev("T04", "wfull", "p/entry/src/main/ets/util/New.ets", agent="agent-a-late", content="m\n", aver=2),
    ])
    chains = {c["file"]: c for c in build_fix_chains(st, {}, {}, fix_after="T02")}
    assert {c["kind"] for c in chains.values()} == {"rework", "created"}
    for c in chains.values():
        assert c["fixer"]["id"] == "agent-z-early" and c["fix_at"] == "T03"
        assert [f["id"] for f in c["fixers_all"]] == ["agent-z-early", "agent-a-late"]
    # 每个修复方各自改了文件的哪几版、第一笔在什么时候:Index.ets 四拨修复方 21 版,只报第一个看不出分段
    assert [(f["fvers"], f["at"]) for f in chains["A.ets"]["fixers_all"]] == [([2], "T03"), ([3], "T04")]
    assert [(f["fvers"], f["at"]) for f in chains["New.ets"]["fixers_all"]] == [([1], "T03"), ([2], "T04")]


def test_build_fix_chains_scope_is_project_code_under_root() -> None:
    """用户口径(2026-09-04):链根 = 工程根目录下的代码与配置,不再只认 .ets。三条同时满足:在 root 之下;
    扩展名 .ets/.ts/.js/.json5/.cpp/.h 或 resources/** 下的 .json;不在 spec/docs/.claude/.agents/.ecat/.migbot/
    build/oh_modules/.hvigor 下。DiceRoller 只放开扩展名会多 98 条噪音,真修复只有 app.json5 与 oh-package.json5;
    0723 漏的是 module.json5(WX Ability 的注册)与 color.json(视觉修改的颜色令牌)。"""
    from migloop.filestory import build_fix_chains, is_project_code

    def gen_fix(path: str) -> list[Ev]:
        return [ev("T01", "wfull", path, agent="agent-g", content="a\n"),
                ev("T03", "wfull", path, agent="agent-f", content="b\n", aver=1)]

    st = build_stories([
        *gen_fix("/p/entry/src/main/ets/A.ets"),
        *gen_fix("/p/AppScope/app.json5"),
        *gen_fix("/p/entry/src/main/cpp/napi.cpp"),
        *gen_fix("/p/entry/src/main/resources/base/element/string.json"),
        *gen_fix("/p/spec/plan.json5"),                                   # 噪音目录
        *gen_fix("/p/docs/x.ets"),
        *gen_fix("/p/.claude/skills/x.ts"),
        *gen_fix("/p/build/outputs/x.json5"),
        *gen_fix("/p/oh_modules/lib/x.js"),
        *gen_fix("/p/build_out.log"),                                     # 扩展名
        *gen_fix("/p/spec_oracle.json"),                                  # 不在 resources 下的 json
        *gen_fix("/p/entry/src/main/resources/base/media/icon.png"),
        *gen_fix("/tmp/x.json5"),                                         # 根目录之外
        *gen_fix("/q/entry/src/main/ets/B.ets"),
    ])
    files = sorted(c["file_abs"] for c in build_fix_chains(st, {}, {}, fix_after="T02", root="/p"))
    assert files == ["/p/AppScope/app.json5", "/p/entry/src/main/cpp/napi.cpp",
                     "/p/entry/src/main/ets/A.ets", "/p/entry/src/main/resources/base/element/string.json"]
    # 不给 root(老调用方)只按扩展名与目录过滤
    files = sorted(c["file_abs"] for c in build_fix_chains(st, {}, {}, fix_after="T02"))
    assert "/tmp/x.json5" in files and "/q/entry/src/main/ets/B.ets" in files and "/p/spec/plan.json5" not in files
    assert is_project_code("C:\\w\\entry\\src\\main\\ets\\A.ets", "C:/w") is True     # Windows 分隔符两边都认
    assert is_project_code("C:/w/build/x.ets", "C:\\w\\") is False


def test_fix_period_touches_lists_project_files_touched_after_execute() -> None:
    """修复期被脚本碰过、方向不明的工程文件:只列指针不立版本;范围与链同一口径(root 之下的代码/配置);
    有 fix_after 按时刻,没有按阶段名。"""
    from migloop.filestory import FileStory, Touch, fix_period_touches
    st = {
        "/p/entry/src/main/ets/A.ets": FileStory("/p/entry/src/main/ets/A.ets", touches=[
            Touch("T01", 5, "agent-g", 1, "脚本黑盒", "a2h-execute"),
            Touch("T03", 9, "agent-f", 2, "脚本黑盒", "arkts-visual-verify")]),
        "/p/spec/x.md": FileStory("/p/spec/x.md", touches=[Touch("T03", 11, "agent-f", 2, "脚本黑盒", None)]),
        "/tmp/y.ets": FileStory("/tmp/y.ets", touches=[Touch("T03", 12, "agent-f", 2, "脚本黑盒", None)]),
    }
    got = fix_period_touches(st, root="/p", fix_after="T02")
    assert [(t["file"], t["seq"], t["by"], t["by_ver"], t["has_versions"]) for t in got] \
        == [("A.ets", 9, "agent-f", 2, False)]
    assert [t["seq"] for t in fix_period_touches(st, root="/p")] == [9]          # 没 marks:按阶段名


def test_build_fix_chains_marks_template_file_first_modified_in_fix_phase() -> None:
    """生成期从没写过、修复期才改的模板/外部文件(0723 的 module.json5、color.json;DiceRoller 的 oh-package.json5)
    不是「修复期新建」—— 文件一直在,是生成期没改它。单独一种 kind=template,问题从"为什么没有它"变成
    "为什么生成期没改它";测试目录下的照旧不进链。"""
    from migloop.filestory import build_fix_chains
    st = build_stories([
        ev("T00", "read", "/p/entry/src/main/module.json5", agent="agent-g", content="{}\n", full=True),
        ev("T03", "wfull", "/p/entry/src/main/module.json5", agent="agent-f", content="{abilities}\n", aver=1),
        ev("T03", "wfull", "/p/entry/src/main/ets/New.ets", agent="agent-f", content="n\n", aver=2),
        ev("T00", "read", "/p/entry/src/ohosTest/module.json5", agent="agent-g", content="{}\n", full=True),
        ev("T03", "wfull", "/p/entry/src/ohosTest/module.json5", agent="agent-f", content="t\n", aver=3),
    ])
    chains = {c["file"]: c for c in build_fix_chains(st, {}, {}, fix_after="T02", root="/p")}
    assert set(chains) == {"module.json5", "New.ets"}
    t = chains["module.json5"]
    assert t["kind"] == "template" and t["generator"]["id"] is None and "未改" in t["generator"]["desc"]
    assert t["fixer"]["id"] == "agent-f" and t["fix_versions"] == [2] and "未改" in t["blame_broken"]
    assert chains["New.ets"]["kind"] == "created"


# ═══════════════ 第 1 步:假前身与依赖读 ═══════════════

def test_write_created_invalidates_unseen_external_prefix() -> None:
    """此前只被「读」过却从没见过内容的外部版本,遇到结果为 created 的 Write 就是假前身:作废,
    这次写才是 v1 creation;那些读改记成「碰过」,指针不丢。"""
    st = build_stories([
        ev("T01", "read", "a.ets", agent="M"),                       # 内容没进上下文
        ev("T02", "wfull", "a.ets", agent="C", content="x\n", created=True),
    ])["a.ets"]
    assert [(v.v, v.source, v.diff_kind, v.by) for v in st.versions] == [(1, "full", "creation", "C")]
    assert not st.reads and len(st.touches) == 1 and "尚不存在" in st.touches[0].reason


def test_dep_read_of_unseen_file_is_touch_not_version() -> None:
    """依赖读(< 输入、cp 源)碰到从没见过的文件:内容没进上下文,存在都不确定 —— 只记碰过,不立外部版本。"""
    st = build_stories([ev("T01", "read", "b.ets", agent="M", dep=True)])["b.ets"]
    assert not st.versions and not st.reads and len(st.touches) == 1


def test_read_record_keeps_via() -> None:
    st = build_stories([ev("T01", "read", "c.md", agent="M", content="c\n", full=True, via="script")])["c.md"]
    assert st.reads[0].via == "script"


# ═══════════════ 跨断点同文推定 ═══════════════

def test_line_origins_bridge_across_break_by_identical_text() -> None:
    """v2 内容未知(断点),v3 重锚:和 v1 逐行同文的 a、c 归属沿用 v1 的作者并标推定;改了的 b 才是未知。"""
    from migloop.filestory import line_origins, line_owners
    st = build_stories([
        ev("T01", "wfull", "a.ets", agent="A", content="a\nb\nc\n"),
        ev("T02", "edit", "a.ets", agent="X", old="zzz", new="q"),                 # edit-miss:断点,之后状态未知
        ev("T03", "read", "a.ets", agent="R", content="a\nB\nc\n", full=True),   # 实录外修改后的重锚
    ])["a.ets"]
    o = line_origins(st)[2]
    assert o[0] == ("A", 1, "bridged") and o[1] is None and o[2] == ("A", 1, "bridged")
    assert line_owners(st)[2] == ["A", None, "A"]
