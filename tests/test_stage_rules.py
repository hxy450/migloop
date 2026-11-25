"""阶段切分统一口径(stage_signals.segment)的最小合成夹具:四条规则各自钉住。"""

from __future__ import annotations

import json

from migloop import stage_signals as ss


def _pts(n: int, step: float = 10.0) -> list[tuple[int, float]]:
    return [(i, i * step) for i in range(n)]


def _top(segs):
    return [(s["start_idx"], s["end_idx"], s["stage"]) for s in segs if s["parent"] is None]


# ---- 规则 1:有 mark 只按 mark 切;除 ecat-refine 外 mark 都是完成水位 ----

def test_end_marks_close_their_stage() -> None:
    segs = ss.segment(_pts(10), marks=[(35.0, "a2h-spec"), (75.0, "a2h-plan")],
                      signals=[(0, "a2h-spec"), (2, "a2h-plan")])
    # spec 占 (开头, 35],plan 占 (35, 75];plan 的回头读不切;plan 收尾后再没 mark、也没新信号 = 未标记
    assert _top(segs) == [(0, 3, "a2h-spec"), (4, 7, "a2h-plan"), (8, 9, "unmarked")]
    assert segs[2]["after"] == "a2h-plan" and segs[2]["signal"] == "unterminated"


def test_first_marked_stage_starts_at_its_own_signal() -> None:
    # init 的 mark 也是完成水位:init 从 /a2h-init 起,之前归 setup;build 从 init 的 mark 起
    segs = ss.segment(_pts(10), marks=[(45.0, "a2h-init"), (55.0, "a2h-build"), (85.0, "a2h-execute")],
                      signals=[(3, "a2h-init"), (5, "a2h-build")])
    assert _top(segs) == [(0, 2, "setup"), (3, 4, "a2h-init"), (5, 5, "a2h-build"), (6, 8, "a2h-execute"),
                          (9, 9, "after-pipeline")]


def test_unterminated_stage_after_last_mark_is_named_by_its_skill() -> None:
    segs = ss.segment(_pts(10), marks=[(35.0, "a2h-spec")],
                      signals=[(1, "a2h-spec"), (6, "a2h-plan"), (7, "a2h-execute")], human=[8])
    # plan 还没打收尾 mark = 没结束:段内不再按 skill 切,也不切后续轮
    assert _top(segs) == [(0, 0, "setup"), (1, 3, "a2h-spec"), (4, 9, "a2h-plan")]
    assert segs[-1]["signal"] == "unterminated" and segs[-1]["after"] == "a2h-spec"


def test_after_final_mark_gap_then_follow_up_at_first_human_input() -> None:
    segs = ss.segment(_pts(12), marks=[(35.0, "a2h-plan"), (65.0, "a2h-execute")], human=[0, 9])
    assert _top(segs) == [(0, 3, "a2h-plan"), (4, 6, "a2h-execute"), (7, 8, "after-pipeline"), (9, 11, "follow-up")]
    # 管线收尾后,哪怕是「继续」也开后续轮(有 mark 时阶段结束由 mark 定)
    segs = ss.segment(_pts(12), marks=[(65.0, "a2h-execute")], human=[7], resumes=[7])
    assert _top(segs)[-1] == (7, 11, "follow-up")


def test_start_mark_followed_by_end_mark_folds_into_it() -> None:
    segs = ss.segment(_pts(10), marks=[(20.0, "ecat-refine"), (25.0, "a2h-verify"), (75.0, "a2h-retrospect")])
    assert _top(segs) == [(0, 1, "setup"), (2, 2, "a2h-verify"), (3, 7, "a2h-retrospect"), (8, 9, "after-pipeline")]
    segs = ss.segment(_pts(10), marks=[(20.0, "ecat-refine")])
    assert _top(segs) == [(0, 1, "setup"), (2, 9, "ecat-refine")]


def test_marks_parse_merge_and_ran() -> None:
    doc = {"marks": [{"stage": "a2h-spec", "ts": "2026-11-01T00:10:00Z"}, {"stage": "a2h-plan-zh", "ts": "2026-11-01T00:20:00Z"}]}
    assert [s for _, s in ss.marks_from_doc(doc)] == ["a2h-spec", "a2h-plan"]
    assert [s for _, s in ss.marks_from_doc([["2026-11-01T00:10:00Z", "a2h-execute"]])] == ["a2h-execute"]
    assert ss.mark_calls(".migbot/bin/a2h mark-stage a2h-plan; a2h.exe mark-stage nope") == ["a2h-plan"]
    assert ss.mark_calls("a2h-codex mark-stage a2h-execute") == ["a2h-execute"]
    assert ss.merge_marks([(100.0, "a2h-spec")], [(130.0, "a2h-spec"), (400.0, "a2h-plan")]) == [
        (100.0, "a2h-spec"), (400.0, "a2h-plan")]
    assert ss.mark_ran(True, "")
    assert ss.mark_ran(False, "Exit code 1\ninit-run ok\nmark-stage ok\n--- validate ---")
    assert ss.mark_ran(False, "[a2h-codex] mark-stage: a2h-build")
    assert not ss.mark_ran(False, "The user doesn't want to proceed with this tool use.")
    assert not ss.mark_ran(None, "")


def test_find_stage_marks(tmp_path) -> None:
    doc = {"marks": [{"stage": "a2h-spec", "ts": "2026-11-01T00:10:00Z"}]}
    facts = tmp_path / "proj" / ".migbot" / "metrics" / "r1" / "facts"
    facts.mkdir(parents=True)
    (facts / "stage-marks.json").write_text(json.dumps(doc), encoding="utf-8")
    first = ss.iso_seconds("2026-11-01T00:05:00Z")
    assert [s for _, s in ss.find_stage_marks(str(tmp_path / "t.jsonl"), str(tmp_path / "proj"), first)] == ["a2h-spec"]


# ---- 规则 1:没有 mark 才用 skill 信号,短于 90 秒不切 ----

def test_short_skill_segments_are_not_cut() -> None:
    pts = [(0, 0.0), (1, 30.0), (2, 60.0), (3, 200.0), (4, 400.0), (5, 600.0)]
    segs = ss.segment(pts, signals=[(0, "a2h-spec"), (1, "a2h-plan"), (2, "a2h-spec"), (3, "a2h-execute")])
    # plan 只有 30 秒(回头读 / 预读),不切;spec 两段并回一段
    assert _top(segs) == [(0, 2, "a2h-spec"), (3, 5, "a2h-execute")]


def test_no_marks_no_pipeline_is_one_session() -> None:
    assert _top(ss.segment(_pts(5), human=[0, 3])) == [(0, 4, "session")]


def test_zero_length_setup_is_not_listed() -> None:
    pts = [(0, None), (1, None), (2, 0.0), (3, 200.0), (4, 400.0)]
    assert _top(ss.segment(pts, signals=[(2, "a2h-spec")])) == [(0, 4, "a2h-spec")]


# ---- 规则 2:最后一个管线阶段结束后,从第一条人工输入起是后续轮 ----

def test_trailing_rounds_start_at_first_human_input_after_pipeline() -> None:
    pts = _pts(20, 60.0)
    segs = ss.segment(pts, signals=[(1, "a2h-spec"), (5, "a2h-execute")], human=[0, 3, 14, 17],
                      last_pipeline_idx=12)
    assert _top(segs) == [(0, 0, "setup"), (1, 4, "a2h-spec"), (5, 13, "a2h-execute"), (14, 19, "follow-up")]


def test_resume_requests_keep_the_last_stage_without_marks() -> None:
    segs = ss.segment(_pts(20, 60.0), signals=[(1, "a2h-execute")], human=[0, 8, 15], resumes=[8],
                      last_pipeline_idx=5)
    assert _top(segs) == [(0, 0, "setup"), (1, 14, "a2h-execute"), (15, 19, "follow-up")]
    assert ss.is_resume_request("继续执行 a2h-execute，直到结束。上一次是 API 429 中断的")
    assert ss.is_resume_request("继续，resume agent") and ss.is_resume_request("  Continue please")
    assert not ss.is_resume_request("不算中断时间 各个阶段和总耗时多久")


def test_program_prompts_do_not_open_trailing_rounds() -> None:
    segs = ss.segment(_pts(20, 60.0), signals=[(1, "a2h-spec")], human=[], last_pipeline_idx=5)
    assert _top(segs)[-1] == (1, 19, "a2h-spec")


# ---- 规则 3:管线阶段里的 Workflow 是子段;管线外的才是顶层段 ----

def test_workflow_inside_pipeline_stage_is_a_child_ending_at_its_real_end() -> None:
    segs = ss.segment(_pts(20, 60.0), signals=[(1, "a2h-execute")],
                      workflows=[{"idx": 4, "end": 7 * 60.0 + 5, "key": "impl"}])
    assert _top(segs) == [(0, 0, "setup"), (1, 19, "a2h-execute")]
    (child,) = [s for s in segs if s["parent"] is not None]
    assert (child["start_idx"], child["end_idx"], child["stage"], child["parent"]) == (4, 7, "wf:impl", 1)


def test_workflow_outside_pipeline_is_top_level_and_outer_stage_resumes() -> None:
    segs = ss.segment(_pts(10, 60.0), workflows=[{"idx": 3, "end": 5 * 60.0, "key": "probe"}])
    assert _top(segs) == [(0, 2, "session"), (3, 5, "wf:probe"), (6, 9, "session")]


def test_missing_stages_only_between_first_and_last() -> None:
    assert ss.missing_stages(["setup", "a2h-spec", "a2h-execute"]) == ["a2h-plan"]
    assert ss.missing_stages(["a2h-init", "a2h-build", "a2h-spec", "a2h-plan", "a2h-execute"]) == ["a2h-run"]
    assert ss.missing_stages(["a2h-spec", "a2h-plan"]) == []
    assert ss.missing_stages(["session"]) == []
