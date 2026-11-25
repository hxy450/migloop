"""ECAT 会话/run 的审计规则(移植自 hmigbot-plus tests/web/test_insight1_ecat_audit.py,90b6726d)。

会话级规则跑在统一 trace 上(与迁移会话同一 build_audit 出口,报告页「02 风险点」
直接吃);run 级规则跑在 ecat.list_runs 的聚合结果上(/ecat-runs 的 audit 字段)。
证据全部来自 test20 run_20260910_144341 的真实形态:
  · 判官派发失败:tools 里 Agent ok=False,result "Agent type 'entropy-judge' not found",
    随后同名 general-purpose 重派(#161)
  · placeholder 三轮恒 1.0(#162);iter 2 ΔH=0 未被采纳;硬检查报问题但判官给 0 分
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from migloop import audit, ecat, service
from migloop.audit import (
    _check_agent_type_missing,
    _check_ecat_no_effect,
    _check_ecat_out_of_scope,
    build_audit,
)

if TYPE_CHECKING:
    from pathlib import Path


def _rules(findings: list[dict[str, Any]]) -> set[str]:
    return {f["rule"] for f in findings}


# ---------- 会话级:子代理类型未注册 ----------


def _agent_tool(brief: str, ok: bool, result: str, ts: str = "2026-09-10T21:44:15Z") -> dict:
    return {"name": "Agent", "brief": brief, "ok": ok, "result": result, "stage": "session",
            "ts": ts, "agent_type": None}


def test_agent_type_missing_fires_on_not_found_then_fallback() -> None:
    trace = {
        "meta": {"ecat": {"role": "discriminator", "iteration": 0}},
        "tools": [
            _agent_tool("Judge page_audit dimension", False,
                        "Agent type 'entropy-judge' not found. Available agents: a2h-…"),
            _agent_tool("Judge entry_nav dimension", False,
                        "Agent type 'entropy-judge' not found. Available agents: a2h-…"),
            _agent_tool("Judge page_audit dimension", True, "Async agent launched successfully."),
        ],
        "agents": [{"agent_id": "a1", "type": "general-purpose", "desc": "Judge page_audit dimension"}],
    }
    out = _check_agent_type_missing(trace)
    assert [f["rule"] for f in out] == ["agent-type-missing"]
    f = out[0]
    assert f["level"] == "error"
    assert "entropy-judge" in f["title"] and "2" in f["detail"]
    assert "general-purpose" in f["detail"]
    assert f["anchor"] == {"stage": "session", "ts": "2026-09-10T21:44:15Z"}


def test_agent_type_missing_silent_when_all_dispatches_ok() -> None:
    trace = {"tools": [_agent_tool("Judge x", True, "Async agent launched successfully.")],
             "agents": [{"agent_id": "a1", "type": "entropy-judge", "desc": "Judge x"}]}
    assert _check_agent_type_missing(trace) == []


def test_agent_type_missing_not_ecat_specific() -> None:
    """迁移会话里派错 agent 类型同样要报 —— 规则不看 meta.ecat。"""
    trace = {"tools": [_agent_tool("convert page", False,
                                   "Agent type 'a2h-migration-worker' not found. Available agents: x")]}
    assert _rules(_check_agent_type_missing(trace)) == {"agent-type-missing"}


# ---------- 会话级:生成端越界写 / 无效轮 ----------


def _gen_trace(written: list[str], work_list: list[str], delta_h: float | None) -> dict:
    return {
        "meta": {"ecat": {"role": "generator", "iteration": 1, "run_id": "run_x",
                          "work_list_files": work_list, "delta_H": delta_h, "total_H": 0.09}},
        "lineage": {"files": [
            {"path": p, "kind": "ets", "writes": 1, "writers": ["a1"]} for p in written
        ] + [{"path": ".ecat/agents/generator/memory/MEMORY.md", "kind": "other", "writes": 1}]},
    }


def test_out_of_scope_fires_when_generator_writes_source_outside_work_list() -> None:
    t = _gen_trace(["entry/src/main/ets/pages/MainPage.ets", "entry/src/main/ets/pages/Other.ets",
                    "entry/src/main/ets/entryability/EntryAbility.ets"],
                   ["entry/src/main/ets/pages/MainPage.ets"], -0.01)
    out = _check_ecat_out_of_scope(t)
    assert [f["rule"] for f in out] == ["ecat-out-of-scope"]
    assert set(out[0]["paths"]) == {"entry/src/main/ets/pages/Other.ets",
                                    "entry/src/main/ets/entryability/EntryAbility.ets"}
    assert out[0]["level"] == "warn"


def test_out_of_scope_silent_when_writes_are_in_work_list_or_not_source() -> None:
    t = _gen_trace(["entry/src/main/ets/pages/MainPage.ets", "build_out.log"],
                   ["entry/src/main/ets/pages/MainPage.ets"], -0.01)
    assert _check_ecat_out_of_scope(t) == []
    # 工作单为空(判官全绿)时,任何源码写都是越界
    t2 = _gen_trace(["entry/src/main/ets/pages/MainPage.ets"], [], None)
    assert _rules(_check_ecat_out_of_scope(t2)) == {"ecat-out-of-scope"}


def test_out_of_scope_ignores_discriminator_and_non_ecat() -> None:
    t = _gen_trace(["entry/src/main/ets/pages/Other.ets"], [], -0.01)
    t["meta"]["ecat"]["role"] = "discriminator"
    assert _check_ecat_out_of_scope(t) == []
    assert _check_ecat_out_of_scope({"lineage": {"files": [{"path": "a.ets", "writes": 1}]}}) == []


def test_no_effect_fires_when_iteration_did_not_lower_entropy() -> None:
    assert _rules(_check_ecat_no_effect(_gen_trace([], [], 0.0))) == {"ecat-no-effect"}
    assert _rules(_check_ecat_no_effect(_gen_trace([], [], 0.0373))) == {"ecat-no-effect"}
    assert _check_ecat_no_effect(_gen_trace([], [], -0.015)) == []
    assert _check_ecat_no_effect(_gen_trace([], [], None)) == []


def test_build_audit_wires_ecat_rules() -> None:
    t = _gen_trace(["entry/src/main/ets/pages/Other.ets"], [], 0.0)
    t["tools"] = [_agent_tool("x", False, "Agent type 'entropy-judge' not found. Available agents: a")]
    result = build_audit(t)
    assert {"ecat-out-of-scope", "ecat-no-effect", "agent-type-missing"} <= _rules(result["findings"])
    assert {"agent-type-missing", "ecat-out-of-scope", "ecat-no-effect"} <= set(result["checked"])
    assert result["counts"]["error"] >= 1


# ---------- run 级 ----------


def _run(iterations: list[dict[str, Any]]) -> dict[str, Any]:
    return {"run_id": "run_x", "iterations": iterations, "unmatched_sessions": []}


def _it(i: int, h: float, dh: float | None, breakdown: dict[str, float],
        sessions: list[dict] | None = None, hard_issues: dict[str, list[str]] | None = None,
        soft: dict[str, float] | None = None) -> dict[str, Any]:
    return {"iteration": i, "total_H": h, "delta_H": dh, "breakdown": breakdown,
            "hard_issues": hard_issues or {}, "soft_scores": soft or {},
            "sessions": sessions or []}


def test_run_audit_dimension_stuck() -> None:
    run = _run([_it(0, 0.1066, None, {"placeholder": 1.0, "crash_risk": 0.125}),
                _it(1, 0.0916, -0.015, {"placeholder": 1.0, "crash_risk": 0.0}),
                _it(2, 0.0916, 0.0, {"placeholder": 1.0, "crash_risk": 0.0})])
    out = ecat.audit_run(run)["findings"]
    stuck = [f for f in out if f["rule"] == "ecat-dimension-stuck"]
    assert len(stuck) == 1 and "placeholder" in stuck[0]["title"] and stuck[0]["level"] == "error"
    assert "crash_risk" not in stuck[0]["title"]


def test_run_audit_stuck_needs_two_iterations_and_nonzero() -> None:
    assert "ecat-dimension-stuck" not in _rules(
        ecat.audit_run(_run([_it(0, 0.1, None, {"placeholder": 1.0})]))["findings"])
    assert "ecat-dimension-stuck" not in _rules(
        ecat.audit_run(_run([_it(0, 0.0, None, {"x": 0.0}), _it(1, 0.0, 0.0, {"x": 0.0})]))["findings"])


def test_run_audit_rebound_and_rejected() -> None:
    run = _run([_it(0, 0.10, None, {}), _it(1, 0.14, 0.0373, {}), _it(2, 0.14, 0.0, {})])
    out = ecat.audit_run(run)["findings"]
    by = {f["rule"]: f for f in out}
    assert "iter 1" in by["ecat-entropy-rebound"]["title"] and "+0.0373" in by["ecat-entropy-rebound"]["detail"]
    assert "iter 2" in by["ecat-iteration-rejected"]["title"]


def test_run_audit_judge_degraded_counts_sessions() -> None:
    sess = [{"role": "discriminator", "sid8": "cfad7bf2", "session_id": "cfad7bf2-x",
             "judge_dispatch": {"entropy-judge": 5, "general-purpose": 5}}]
    run = _run([_it(0, 0.1, None, {}, sessions=sess), _it(1, 0.09, -0.01, {}, sessions=[
        {"role": "discriminator", "sid8": "59ffa0a0", "session_id": "59ffa0a0-x",
         "judge_dispatch": {"entropy-judge": 5}}])])
    out = ecat.audit_run(run)["findings"]
    f = next(x for x in out if x["rule"] == "ecat-judge-degraded")
    assert f["level"] == "error" and "1/2" in f["detail"] and f["agents"] == ["cfad7bf2-x"]


def test_run_audit_hard_soft_conflict_is_info() -> None:
    run = _run([_it(0, 0.1, None, {"page_audit": 0.0},
                    hard_issues={"page_audit": ["Pages missing @Entry: ['MainPage.ets']"]},
                    soft={"page_audit": 0.0})])
    f = next(x for x in ecat.audit_run(run)["findings"] if x["rule"] == "ecat-hard-soft-conflict")
    assert f["level"] == "info" and "page_audit" in f["title"]


def test_run_audit_clean_run_has_no_findings() -> None:
    run = _run([_it(0, 0.1, None, {"x": 0.5}), _it(1, 0.05, -0.05, {"x": 0.0})])
    r = ecat.audit_run(run)
    assert r["findings"] == [] and r["counts"] == {"error": 0, "warn": 0, "info": 0}


# ---------- 真数据形态:list_runs 带 hard_issues/soft_scores 与 audit;extract_trace 带上下文 ----------

GEN_SID = "e20b4ce1-b84b-457f-aaa5-1929046c9809"
DISC_SID = "cfad7bf2-1774-45cb-864a-61339fa8a6c0"
RUN_ID = "run_20260910_144341"


def _rec(t: str, ts: str, sid: str, cwd: str, content: Any, mid: str = "m") -> dict:
    if t == "user":
        return {"type": "user", "timestamp": ts, "cwd": cwd, "sessionId": sid,
                "message": {"content": content}}
    return {"type": "assistant", "timestamp": ts, "message": {
        "model": "claude-opus-5", "id": mid, "usage": {"output_tokens": 5}, "content": content}}


@pytest.fixture
def harmony(tmp_path_factory: pytest.TempPathFactory) -> Path:
    h = tmp_path_factory.mktemp("h")
    slug = "proj"  # 真实落盘是 slug(cwd);名字不参与角色认定,取短名免撞 Windows MAX_PATH
    cwd = str(h)
    disc = h / ".ecat" / "agents" / "discriminator" / "projects" / slug
    gen = h / ".ecat" / "agents" / "generator" / "projects" / slug
    disc.mkdir(parents=True)
    gen.mkdir(parents=True)
    ets = str(h / "entry" / "src" / "main" / "ets" / "pages" / "Other.ets")
    disc_recs = [
        _rec("user", "2026-09-10T21:43:46.000Z", DISC_SID, cwd,
             "You are the Discriminator in the ECAT adversarial loop (iteration 0)."),
        _rec("assistant", "2026-09-10T21:44:15.000Z", DISC_SID, cwd, [
            {"type": "tool_use", "id": "tu1", "name": "Agent",
             "input": {"subagent_type": "entropy-judge", "description": "Judge page_audit dimension",
                       "prompt": "x"}}], "a1"),
        {"type": "user", "timestamp": "2026-09-10T21:44:16.000Z", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu1", "is_error": True,
             "content": "Agent type 'entropy-judge' not found. Available agents: general-purpose"}]}},
        _rec("assistant", "2026-09-10T21:45:39.000Z", DISC_SID, cwd, [
            {"type": "tool_use", "id": "tu2", "name": "Agent",
             "input": {"subagent_type": "general-purpose", "description": "Judge page_audit dimension",
                       "prompt": "x"}}], "a2"),
        _rec("assistant", "2026-09-10T21:53:53.000Z", DISC_SID, cwd,
             [{"type": "text", "text": "{}"}], "a3"),
    ]
    (disc / f"{DISC_SID}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in disc_recs) + "\n", encoding="utf-8")
    gen_recs = [
        _rec("user", "2026-09-10T21:53:53.000Z", GEN_SID, cwd,
             "You are the Generator in the ECAT adversarial loop (iteration 0)."),
        _rec("assistant", "2026-09-10T21:54:00.000Z", GEN_SID, cwd, [
            {"type": "tool_use", "id": "w1", "name": "Write",
             "input": {"file_path": ets, "content": "a\nb\n"}}], "g1"),
        _rec("assistant", "2026-09-10T22:33:50.000Z", GEN_SID, cwd,
             [{"type": "text", "text": "done"}], "g2"),
    ]
    (gen / f"{GEN_SID}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in gen_recs) + "\n", encoding="utf-8")

    runs = h / ".migbot" / "ecat_runs" / RUN_ID
    (runs / "0").mkdir(parents=True)
    (runs / "0" / "gradient.json").write_text(json.dumps({
        "summary": "s", "work_list": [
            {"file": "entry/src/main/ets/pages/MainPage.ets", "issues": ["Unregistered placeholder"],
             "suggested_skills": [], "severity": "high"}],
        "skill_evolution": [], "insights": []}), encoding="utf-8")
    hist = [
        {"iteration": 0, "total_H": 0.1066, "timestamp": "2026-09-10T21:43:45+00:00",
         "breakdown": {"placeholder": 1.0, "page_audit": 0.0},
         "details": {"page_audit": {"issues": ["Pages missing @Entry: ['MainPage.ets']"],
                                    "agentic_verdict": {"score": 0.0, "rationale": "fine"}},
                     "placeholder": {"unregistered_count": 6}}},
        {"iteration": 1, "total_H": 0.0916, "timestamp": "2026-09-10T22:34:04+00:00",
         "breakdown": {"placeholder": 1.0, "page_audit": 0.0}, "details": {}},
    ]
    (runs / "entropy_history.jsonl").write_text(
        "\n".join(json.dumps(r) for r in hist) + "\n", encoding="utf-8")
    return h


def test_list_runs_carries_hard_soft_and_audit(harmony: Path) -> None:
    run = ecat.list_runs(str(harmony))[0]
    it0 = run["iterations"][0]
    assert it0["hard_issues"] == {"page_audit": ["Pages missing @Entry: ['MainPage.ets']"]}
    assert it0["soft_scores"] == {"page_audit": 0.0}
    rules = _rules(run["audit"]["findings"])
    assert {"ecat-dimension-stuck", "ecat-judge-degraded", "ecat-hard-soft-conflict"} <= rules
    assert run["audit"]["counts"]["error"] == 2


def test_extract_trace_enriches_ecat_context_and_audit_fires(harmony: Path) -> None:
    gen_path = next(harmony.glob(f".ecat/agents/generator/projects/*/{GEN_SID}.jsonl"))
    t = service.extract_trace(str(gen_path))
    e = t["meta"]["ecat"]
    assert e["run_id"] == RUN_ID and e["iteration"] == 0
    assert e["work_list_files"] == ["entry/src/main/ets/pages/MainPage.ets"]
    assert e["total_H"] == pytest.approx(0.1066) and e["delta_H"] is None
    # 生成端写了工作单之外的 Other.ets → 越界
    assert "ecat-out-of-scope" in _rules(audit.build_audit(t)["findings"])

    disc_path = next(harmony.glob(f".ecat/agents/discriminator/projects/*/{DISC_SID}.jsonl"))
    t2 = service.extract_trace(str(disc_path))
    assert t2["meta"]["ecat"]["judge_dispatch"] == {"entropy-judge": 1, "general-purpose": 1}
    assert "agent-type-missing" in _rules(audit.build_audit(t2)["findings"])
