"""skill-not-invoked:主线 Read 管线 skill 的 SKILL.md 照着执行、全程没经 Skill 工具调用它。

移植自 hmigbot-plus tests/web/test_insight1_audit.py(53c5524d)。

实录(2026-09-18,会话 2ce43a97):Gate C 通过后模型说「进入 a2h-plan 阶段。读 skill
定义:」就 Read 了 .claude/skills/a2h-plan/SKILL.md,全程没调 Skill。migloop 只还原
实际发生的事 —— 阶段划分里没有 a2h-plan 是对的,但这次不遵从要作为风险点标出来。
"""

from __future__ import annotations

from typing import Any

from migloop.audit import build_audit

_PLAN_MD = "/private/tmp/proj/.claude/skills/a2h-plan/SKILL.md"


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


def test_skill_md_read_without_skill_call_is_flagged() -> None:
    t = _trace(
        stages=[{"stage": "a2h-spec"}, {"stage": "a2h-execute"}],
        tools=[{"name": "Skill", "brief": "a2h-spec", "skill": "a2h-spec", "ok": True,
                "stage": "a2h-spec"},
               {"name": "Read", "brief": _PLAN_MD, "ok": True, "stage": "a2h-spec",
                "ts": "2026-09-18T16:44:25.271Z"},
               {"name": "Read", "brief": _PLAN_MD, "ok": True, "stage": "a2h-spec",
                "ts": "2026-09-18T17:13:07.836Z"}])
    fs = [x for x in build_audit(t)["findings"] if x["rule"] == "skill-not-invoked"]
    assert len(fs) == 1, "同一个 skill 读多次只报一条"
    f = fs[0]
    assert f["level"] == "warn"
    assert "a2h-plan" in f["title"]
    assert "16:44" in f["detail"], "写明首次发生时刻"
    assert "2 次" in f["detail"]
    assert f["paths"] == ["a2h-plan"]
    assert f["anchor"] == {"stage": "a2h-spec", "ts": "2026-09-18T16:44:25.271Z"}
    assert "skill-not-invoked" in build_audit(t)["checked"]


def test_skill_md_read_is_fine_when_skill_was_invoked() -> None:
    """先读后调、调过再回头重读(实录里 a2h-spec 就重读过)都不算。"""
    via_tool = _trace(
        stages=[{"stage": "a2h-spec"}, {"stage": "a2h-plan"}],
        tools=[{"name": "Read", "brief": _PLAN_MD, "ok": True, "stage": "a2h-spec"},
               {"name": "Skill", "brief": "migbot:a2h-plan", "skill": "migbot:a2h-plan",
                "ok": True, "stage": "a2h-plan"}])
    assert "skill-not-invoked" not in _rules_hit(via_tool)
    # 斜杠命令 / resume 续跑进入:没有 Skill 工具调用,但归属戳切出了该阶段
    via_attribution = _trace(
        stages=[{"stage": "a2h-spec"}, {"stage": "a2h-plan"}],
        tools=[{"name": "Read", "brief": _PLAN_MD, "ok": True, "stage": "a2h-plan"}])
    assert "skill-not-invoked" not in _rules_hit(via_attribution)


def test_skill_md_read_ignores_non_pipeline_and_reference_files() -> None:
    t = _trace(
        stages=[{"stage": "a2h-spec"}],
        tools=[{"name": "Read", "ok": True, "stage": "a2h-spec",
                "brief": "/p/.claude/skills/arkts-i18n/SKILL.md"},
               {"name": "Read", "ok": True, "stage": "a2h-spec",
                "brief": "/p/.claude/skills/a2h-plan/templates/ui-plan-template.md"},
               ])
    assert "skill-not-invoked" not in _rules_hit(t)
    assert "skill-not-invoked" not in build_audit(t)["checked"], "没读过管线 SKILL.md 时不适用"
    # Skill 调了但失败、转头去读 SKILL.md:由 skill-fail 负责报,这里不重复
    failed = _trace(
        stages=[{"stage": "a2h-spec"}],
        tools=[{"name": "Skill", "brief": "a2h-plan", "skill": "a2h-plan", "ok": False,
                "stage": "a2h-spec"},
               {"name": "Read", "brief": _PLAN_MD, "ok": True, "stage": "a2h-spec"}])
    hit = _rules_hit(failed)
    assert "skill-fail" in hit
    assert "skill-not-invoked" not in hit


def test_retrospect_is_not_mistaken_for_a_spec_stage() -> None:
    """``"spec" in "a2h-retrospect"`` 为真:没有 spec 阶段、retrospect 之后又回到 verify 的
    会话(2026-08-31 codex rollout 实测)曾被报「spec 阶段未起分析代理」。"""
    t = _trace(stages=[{"stage": "a2h-execute"}, {"stage": "a2h-retrospect"},
                       {"stage": "a2h-verify"}], tools=[])
    hit = _rules_hit(t)
    assert "spec-no-analyzer" not in hit
    assert "spec-main-write" not in hit
