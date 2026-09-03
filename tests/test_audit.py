"""自动审计规则 —— 每条规则的触发与不触发都要钉死。

规则吃的是 lineage/agents/stages 的真实字段名(与 adapter 对齐),
字段名错了规则会静默不触发 —— 所以正向用例必须存在。
"""

from __future__ import annotations

from typing import Any

from migloop.audit import (
    DEFAULT_PIPELINE,
    _check_aborted_agents,
    _check_blind_write,
    _check_missing_inputs,
    _check_pipeline_gap,
    _check_rework,
    _check_snapshot_agents,
    _check_spec_orphan,
    build_audit,
)


def _direct(fn, t, *a):
    return {f["rule"] for f in fn(t, *a)}


def _agent_row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "agent_id": "a1", "desc": "converter-P1", "role": "execute",
        "n_ets": 2, "n_spec_read": 1, "shared_reads": [], "lines_android": 120,
        "writes_ets": ["entry/src/main/ets/pages/A.ets"],
    }
    base.update(over)
    return base


def _trace(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "stages": [{"stage": "a2h-run"}, {"stage": "a2h-spec"}],
        "agents": [],
        "lineage": {"agents": [], "specs": [], "files": []},
    }
    base.update(over)
    return base


def _rules_hit(trace: dict[str, Any]) -> set[str]:
    return {f["rule"] for f in build_audit(trace)["findings"]}


# ---------- 盲写 ----------


def test_blind_write_fires_on_no_input_executor() -> None:
    t = _trace(lineage={"agents": [_agent_row(n_spec_read=0, shared_reads=[],
                                              lines_android=0)],
                        "specs": [], "files": []})
    fs = _check_blind_write(t)
    assert {f["rule"] for f in fs} == {"blind-write"}
    f = fs[0]
    assert f["level"] == "error"
    assert f["agents"] == ["a1"]


def test_blind_write_quiet_when_agent_read_spec_or_android() -> None:
    read_spec = _trace(lineage={"agents": [_agent_row(n_spec_read=1, lines_android=0)],
                                "specs": [], "files": []})
    read_android = _trace(lineage={"agents": [_agent_row(n_spec_read=0, lines_android=88)],
                                   "specs": [], "files": []})
    assert not _direct(_check_blind_write, read_spec)
    assert not _direct(_check_blind_write, read_android)


def test_blind_write_spares_fixers_reading_project_files() -> None:
    """修复/组装类代理读的是现有工程代码与编译报错 —— 工程内读取也算依据。
    AntennaPod 真数据回测:没这条会把全部 closer 误打成盲写。"""
    t = _trace(lineage={"agents": [_agent_row(n_spec_read=0, lines_android=0,
                                              n_proj=6)],
                        "specs": [], "files": []})
    assert not _direct(_check_blind_write, t)


def test_blind_write_ignores_main_thread_slices() -> None:
    """主线按阶段拆的合成条目横跨全程,单片「没读」不代表无据。"""
    t = _trace(lineage={"agents": [_agent_row(agent_id="__main__:a2h-execute",
                                              n_spec_read=0, lines_android=0)],
                        "specs": [], "files": []})
    assert not _direct(_check_blind_write, t)


# ---------- 输入缺失聚合 ----------


def test_missing_inputs_aggregate_and_dedupe_with_blind_write() -> None:
    """未读 spec=warn,未读源码=info;全盲代理已按 blind-write 报,不重复计入。"""
    t = _trace(lineage={"agents": [
        _agent_row(agent_id="a1", desc="c1", n_spec_read=0, shared_reads=[],
                   lines_android=50),                       # 未读 spec
        _agent_row(agent_id="a2", desc="c2", n_spec_read=1, lines_android=0),  # 未读源码
        _agent_row(agent_id="a3", desc="c3", n_spec_read=0, shared_reads=[],
                   lines_android=0, n_proj=0),              # 全盲 -> blind-write
    ], "specs": [], "files": []})
    rules = {f["rule"]: f for f in _check_missing_inputs(t)}
    assert rules["no-spec-write"]["level"] == "warn"
    assert rules["no-spec-write"]["agents"] == ["c1"]
    assert rules["no-source-write"]["level"] == "info"
    assert rules["no-source-write"]["agents"] == ["c2"]
    assert {f["agents"][0] for f in _check_blind_write(t)} == {"a3"}


def test_missing_inputs_quiet_for_healthy_executors() -> None:
    t = _trace(lineage={"agents": [_agent_row()], "specs": [], "files": []})
    assert not _direct(_check_missing_inputs, t)


# ---------- spec 覆盖缺口 ----------


def _spec(path: str, read_by: list[str], kind: str = "page") -> dict[str, Any]:
    return {"path": path, "kind": kind, "read_by": read_by, "authors": ["a0"]}


def test_spec_orphan_needs_code_output_gate() -> None:
    """还没开始产码时全部 spec 都暂时无人读 —— 不是缺口,不得报。"""
    t = _trace(lineage={"agents": [], "specs": [_spec("spec/p1.md", [])], "files": []})
    assert not _direct(_check_spec_orphan, t)


def test_spec_orphan_fires_once_code_started() -> None:
    t = _trace(lineage={
        "agents": [],
        "specs": [_spec("spec/p1.md", []), _spec("spec/p2.md", ["a1"])],
        "files": [{"path": "e/A.ets", "kind": "ets", "writers": ["a1"]}],
    })
    f = _check_spec_orphan(t)[0]
    assert f["paths"] == ["spec/p1.md"], "只报没人读的那页"
    # 共享类 spec(ledger/plan)不算实质分页,交给 shared kind 过滤
    t2 = _trace(lineage={
        "agents": [], "specs": [_spec("spec/plan.md", [], kind="plan")],
        "files": [{"path": "e/A.ets", "kind": "ets", "writers": ["a1"]}],
    })
    assert not _direct(_check_spec_orphan, t2)


# ---------- 异常收尾 ----------


def test_aborted_agents_grouped_per_stage() -> None:
    """已启用规则:按阶段聚合一条,汇总浪费 token、点名、锚定阶段。"""
    t = _trace(agents=[
        {"agent_id": "a1", "desc": "w1", "stage": "a2h-execute",
         "aborted": "api_error", "output_tokens": 4200, "start_ts": "2026-08-20T01:00:00Z"},
        {"agent_id": "a2", "desc": "w2", "stage": "a2h-execute",
         "aborted": "interrupted", "output_tokens": 800},
        {"agent_id": "a3", "desc": "ok", "stage": "a2h-execute",
         "aborted": None, "output_tokens": 10},
    ])
    fs = [f for f in build_audit(t)["findings"] if f["rule"] == "aborted-agent"]
    assert len(fs) == 1, "同阶段聚合一条"
    f = fs[0]
    assert "5000" in f["detail"], "浪费 token 汇总"
    assert f["agents"] == ["a1", "a2"]
    assert f["anchor"]["stage"] == "a2h-execute"
    assert "白烧" not in f["detail"], "取证词汇不出客户面"


def test_normal_agents_stay_quiet() -> None:
    t = _trace(agents=[{"agent_id": "aY", "aborted": None, "output_tokens": 10}])
    assert not _direct(_check_aborted_agents, t)


# ---------- 流程跳步 ----------


def test_pipeline_gap_fires_on_skipped_stage() -> None:
    t = _trace(stages=[{"stage": "a2h-run"}, {"stage": "a2h-execute"}])
    f = _check_pipeline_gap(t, DEFAULT_PIPELINE)[0]
    assert f["level"] == "error"
    assert f["paths"] == ["a2h-spec", "a2h-plan"]


def test_pipeline_gap_quiet_on_prefix_progress_and_unknown_stages() -> None:
    # 正常推进(前缀)不报;完全不认识的阶段名(别的管线)也不报
    assert not _direct(_check_pipeline_gap,
                       _trace(stages=[{"stage": "a2h-run"}, {"stage": "a2h-spec"}]),
                       DEFAULT_PIPELINE)
    assert not _direct(_check_pipeline_gap, _trace(stages=[{"stage": "wf:Fix"}]),
                       DEFAULT_PIPELINE)
    assert DEFAULT_PIPELINE[0] == "a2h-run"


# ---------- 返工热点 ----------


def test_rework_lists_multi_writer_files() -> None:
    t = _trace(lineage={"agents": [], "specs": [], "files": [
        {"path": "e/A.ets", "kind": "ets", "writers": ["a1", "a2", "a3"]},
        {"path": "e/B.ets", "kind": "ets", "writers": ["a1"]},
        {"path": "spec/x.md", "kind": "spec", "writers": ["a1", "a2"]},
    ]})
    f = _check_rework(t)[0]
    assert f["level"] == "info"
    assert f["paths"] == ["e/A.ets"], "单写手与非代码文件不算返工"


# ---------- 汇总形状 ----------


def test_findings_sorted_by_severity_and_counted() -> None:
    t = _trace(
        stages=[{"stage": "a2h-run"}, {"stage": "a2h-execute"}],   # error
        agents=[{"agent_id": "aX", "aborted": "interrupted", "output_tokens": 1}],  # warn
        lineage={"agents": [], "specs": [], "files": [
            {"path": "e/A.ets", "kind": "ets", "writers": ["a1", "a2"]},  # info
        ]},
    )
    audit = build_audit(t)
    # 此夹具触发 execute-no-build(error) + aborted-agent(warn,已启用)
    assert [f["level"] for f in audit["findings"]] == ["error", "warn"]
    assert audit["counts"] == {"error": 1, "warn": 1, "info": 0}
    assert len(audit["checked"]) == 11


def test_clean_trace_yields_empty_findings() -> None:
    audit = build_audit(_trace())
    assert audit["findings"] == []
    assert audit["counts"] == {"error": 0, "warn": 0, "info": 0}


# ---------- 经验规则:skill/脚本/构建/分析代理/模拟器 ----------


def test_skill_fail_names_the_skill() -> None:
    t = _trace(tools=[{"name": "Skill", "brief": "a2h-spec", "ok": False, "stage": "a2h-spec"}])
    f = next(x for x in build_audit(t)["findings"] if x["rule"] == "skill-fail")
    assert f["level"] == "error"
    assert "a2h-spec" in f["detail"]
    ok = _trace(tools=[{"name": "Skill", "brief": "a2h-spec", "ok": True, "stage": "a2h-spec"}])
    assert "skill-fail" not in _rules_hit(ok)


def test_script_failures_split_per_stage_and_graded() -> None:
    """按阶段各出一条(点击跳转语义对齐),级别按该阶段自身次数定。"""
    t = _trace(tools=[{"name": "Bash", "ok": False, "stage": "a2h-execute",
                       "ts": "2026-08-19T08:00:00Z"}] * 6
                     + [{"name": "Bash", "ok": False, "stage": "a2h-spec"}] * 2)
    fs = [x for x in build_audit(t)["findings"] if x["rule"] == "script-fail"]
    assert len(fs) == 2, "两个阶段各一条"
    by = {f["anchor"]["stage"]: f for f in fs}
    assert by["a2h-execute"]["level"] == "warn"
    assert "6 次脚本失败" in by["a2h-execute"]["detail"]
    assert "08:00" in by["a2h-execute"]["detail"], "首次失败时刻要写明"
    assert by["a2h-spec"]["level"] == "info"


def test_execute_no_build_only_when_execute_lacks_markers() -> None:
    base_stages = [{"stage": "a2h-run"}, {"stage": "a2h-spec"}, {"stage": "a2h-plan"},
                   {"stage": "a2h-execute"}]
    silent = _trace(stages=base_stages,
                    tools=[{"name": "Bash", "brief": "ls -la", "ok": True, "stage": "a2h-execute"}])
    f = next(x for x in build_audit(silent)["findings"] if x["rule"] == "execute-no-build")
    assert f["level"] == "error"
    built = _trace(stages=base_stages,
                   tools=[{"name": "Bash", "brief": "ohpm install --all", "ok": True,
                           "stage": "a2h-execute"}])
    assert "execute-no-build" not in _rules_hit(built)
    # 没进 execute 阶段就不评这条
    assert "execute-no-build" not in _rules_hit(_trace())


def test_spec_stage_dispatch_disciplines() -> None:
    """spec 阶段要起 analyzer;spec 要由子代理写 —— 两条独立报。"""
    t = _trace(
        stages=[{"stage": "a2h-run"}, {"stage": "a2h-spec"}, {"stage": "a2h-plan"}],
        lineage={"agents": [
            {"agent_id": "w1", "stage": "a2h-spec", "type": "a2h-migration-worker",
             "n_spec_w": 0},
        ], "specs": [], "files": []},
    )
    hit = _rules_hit(t)
    assert "spec-no-analyzer" in hit
    assert "spec-main-write" in hit
    # spec 仍是末阶段(进行中)不评 —— analyzer 可能还没起
    ongoing = _trace(stages=[{"stage": "a2h-run"}, {"stage": "a2h-spec"}],
                     lineage={"agents": [], "specs": [], "files": []})
    assert "spec-no-analyzer" not in _rules_hit(ongoing)
    good = _trace(
        stages=[{"stage": "a2h-run"}, {"stage": "a2h-spec"}, {"stage": "a2h-plan"}],
        lineage={"agents": [
            {"agent_id": "an1", "stage": "a2h-spec", "type": "a2h-android-analyzer",
             "n_spec_w": 0},
            {"agent_id": "w1", "stage": "a2h-spec", "type": "a2h-migration-worker",
             "n_spec_w": 4},
        ], "specs": [], "files": []},
    )
    hit2 = _rules_hit(good)
    assert "spec-no-analyzer" not in hit2
    assert "spec-main-write" not in hit2


def test_verify_emulator_rule() -> None:
    pipeline_done = [{"stage": "a2h-run"}, {"stage": "a2h-spec"}, {"stage": "a2h-plan"},
                     {"stage": "a2h-execute"}, {"stage": "a2h-verify"}]
    silent = _trace(stages=pipeline_done,
                    tools=[{"name": "Bash", "brief": "cat report.md", "ok": True,
                            "stage": "a2h-verify"}])
    f = next(x for x in build_audit(silent)["findings"] if x["rule"] == "verify-no-emulator")
    assert f["level"] == "warn"
    live = _trace(stages=pipeline_done,
                  tools=[{"name": "Bash", "brief": "hdc shell aa start ...", "ok": True,
                          "stage": "a2h-verify"}])
    assert "verify-no-emulator" not in _rules_hit(live)
    assert "verify-no-emulator" not in _rules_hit(_trace())


def test_verify_dependency_chain_layers() -> None:
    """verify 三层递进:没起设备只报最上层;起了设备再查装包与截图。"""
    stages = [{"stage": "a2h-run"}, {"stage": "a2h-spec"}, {"stage": "a2h-plan"},
              {"stage": "a2h-execute"}, {"stage": "a2h-verify"}]
    # 起了设备但没装包没截图 -> 报两条,不再报 no-emulator
    dev_only = _trace(stages=stages, tools=[
        {"name": "Bash", "brief": "hdc shell aa start com.x", "ok": True, "stage": "a2h-verify"}])
    hit = _rules_hit(dev_only)
    assert "verify-no-emulator" not in hit
    assert "verify-no-install" in hit
    assert "verify-no-screenshot" in hit
    # 全链齐 -> 三条全静默
    full = _trace(stages=stages, tools=[
        {"name": "Bash", "brief": "hdc install ./out.hap", "ok": True, "stage": "a2h-verify"},
        {"name": "Bash", "brief": "hdc shell snapshot_display", "ok": True, "stage": "a2h-verify"}])
    hit2 = _rules_hit(full)
    assert not {"verify-no-emulator", "verify-no-install", "verify-no-screenshot"} & hit2


def test_findings_carry_evidence_anchor() -> None:
    """报告页「查看现场」跳转吃 anchor:skill-fail 带阶段+时刻,缺失类带阶段。"""
    t = _trace(
        stages=[{"stage": "a2h-run"}, {"stage": "a2h-spec"}, {"stage": "a2h-plan"},
                {"stage": "a2h-execute"}],
        tools=[{"name": "Skill", "brief": "a2h-plan", "ok": False, "stage": "a2h-plan",
                "ts": "2026-08-19T08:20:00Z"},
               {"name": "Bash", "brief": "ls", "ok": True, "stage": "a2h-execute"}])
    by = {f["rule"]: f for f in build_audit(t)["findings"]}
    assert by["skill-fail"]["anchor"] == {"stage": "a2h-plan", "ts": "2026-08-19T08:20:00Z"}
    assert "08:20" in by["skill-fail"]["detail"], "detail 要写发生时刻"
    assert by["execute-no-build"]["anchor"] == {"stage": "a2h-execute"}


def test_fix_chains_card_wraps_ledger_chains() -> None:
    """返修追溯卡只包账本算好的链:文件、生成方点名、跨会话计数、锚到生成阶段;
    不传链(摘要端点 / 进行中的会话)不出卡,也不再从血缘层另算。"""
    chains = [{
        "file": "A.ets", "file_abs": "/p/e/A.ets",
        "generator": {"id": "g1", "desc": "conv A", "stage": "a2h-execute"},
        "fixer": {"id": "f1", "desc": "vf", "stage": "arkts-visual-verify"},
        "fixers_all": [{"id": "f1", "desc": "vf"}], "lines": {"touched": 3},
        "gen_session": "aaaaaaaa",
    }]
    fs = [f for f in build_audit(_trace(), fix_chains=chains)["findings"]
          if f["rule"] == "verify-fix-traceback"]
    assert len(fs) == 1
    f = fs[0]
    assert f["level"] == "info" and f["paths"] == ["/p/e/A.ets"]
    assert "conv A" in f["detail"] and "1 条跨会话" in f["detail"]
    assert f["anchor"] == {"stage": "a2h-execute"}
    assert f["chain"][0]["fixer"]["id"] == "f1" and f["chain"][0]["gen_session"] == "aaaaaaaa"
    assert not [x for x in build_audit(_trace())["findings"] if x["rule"] == "verify-fix-traceback"]
    assert not [x for x in build_audit(_trace(), fix_chains=[])["findings"]
                if x["rule"] == "verify-fix-traceback"]


# ---------- 主会话快照 ----------


def test_snapshot_agents_named_and_kept_out_of_aborted() -> None:
    """上传上来的子代理转录是主会话快照:单独点名(error),不再算异常收尾。"""
    t = _trace(agents=[
        {"agent_id": "a1", "type": "hmos-builder", "stage": "a2h-execute",
         "aborted": "interrupted", "output_tokens": 100, "snapshot_of_main": True},
        {"agent_id": "a2", "type": "hmos-builder", "stage": "arkts-visual-verify",
         "aborted": "interrupted", "output_tokens": 100, "snapshot_of_main": True},
        {"agent_id": "a3", "desc": "real", "stage": "a2h-execute",
         "aborted": "api_error", "output_tokens": 7},
    ])
    found = {f["rule"]: f for f in build_audit(t)["findings"]}
    snap = found["agent-snapshot"]
    assert snap["level"] == "error"
    assert snap["agents"] == ["a1", "a2"]
    assert snap["anchor"]["stage"] == "a2h-execute"
    assert "a2h-execute 1 个" in snap["detail"]
    assert "arkts-visual-verify 1 个" in snap["detail"]
    assert "#46" in snap["detail"], "指向运行时 issue,让人知道该去哪修"
    assert found["aborted-agent"]["agents"] == ["a3"], "快照的异常收尾是假象,不进异常收尾卡"


def test_snapshot_rule_quiet_without_flag() -> None:
    t = _trace(agents=[{"agent_id": "aY", "aborted": "interrupted", "output_tokens": 1}])
    assert not _direct(_check_snapshot_agents, t)
