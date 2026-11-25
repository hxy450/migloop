"""阶段切分统一口径(stage_signals.segment)的最小合成夹具:四条规则各自钉住。"""

from __future__ import annotations

import json

from migloop import stage_signals as ss


def _pts(n: int, step: float = 10.0) -> list[tuple[int, float]]:
    return [(i, i * step) for i in range(n)]


def _top(segs):
    return [(s["start_idx"], s["end_idx"], s["stage"]) for s in segs if s["parent"] is None]


# ---- 规则 1:有 mark 只按 mark 切;管线 mark 是结束时刻,init 是开始时刻 ----

def test_end_marks_close_their_stage() -> None:
    segs = ss.segment(_pts(10), marks=[(35.0, "a2h-spec"), (75.0, "a2h-plan")],
                      signals=[(0, "a2h-spec"), (2, "a2h-plan"), (6, "a2h-execute")])
    # spec 占 (开头, 35],plan 占 (35, 75] 并带上同一回合的收尾;skill 信号在有 mark 时不参与切分
    assert _top(segs) == [(0, 3, "a2h-spec"), (4, 9, "a2h-plan")]
    # plan 的 mark 之后的人工输入开后续轮
    segs = ss.segment(_pts(10), marks=[(35.0, "a2h-spec"), (75.0, "a2h-plan")], human=[1, 9])
    assert _top(segs)[-1] == (9, 9, "after-pipeline")


def test_unmarked_stage_after_last_mark_is_named_by_its_skill() -> None:
    segs = ss.segment(_pts(10), marks=[(35.0, "a2h-spec")], signals=[(1, "a2h-spec"), (6, "a2h-plan")],
                      human=[8])
    # plan 还没打收尾 mark = 没结束:不切后续轮
    assert _top(segs) == [(0, 3, "a2h-spec"), (4, 9, "a2h-plan")]


def test_start_mark_followed_by_end_mark_folds_into_it() -> None:
    segs = ss.segment(_pts(10), marks=[(20.0, "a2h-init"), (25.0, "a2h-build"), (75.0, "a2h-spec")])
    assert _top(segs) == [(0, 1, "setup"), (2, 2, "a2h-build"), (3, 9, "a2h-spec")]


def test_marks_parse_both_shapes(tmp_path) -> None:
    doc = {"marks": [{"stage": "a2h-spec", "ts": "2026-11-01T00:10:00Z"}, {"stage": "a2h-plan-zh", "ts": "2026-11-01T00:20:00Z"}]}
    assert [s for _, s in ss.marks_from_doc(doc)] == ["a2h-spec", "a2h-plan"]
    assert [s for _, s in ss.marks_from_doc([["2026-11-01T00:10:00Z", "a2h-execute"]])] == ["a2h-execute"]
    facts = tmp_path / "proj" / ".migbot" / "metrics" / "r1" / "facts"
    facts.mkdir(parents=True)
    (facts / "stage-marks.json").write_text(json.dumps(doc), encoding="utf-8")
    first = ss.iso_seconds("2026-11-01T00:05:00Z")
    assert [s for _, s in ss.find_stage_marks(str(tmp_path / "t.jsonl"), str(tmp_path / "proj"), first)] == [
        "a2h-spec", "a2h-plan"]
    assert ss.mark_calls(".migbot/bin/a2h mark-stage a2h-plan; a2h.exe mark-stage nope") == ["a2h-plan"]


# ---- 规则 1:没有 mark 才用 skill 信号,短于 90 秒不切 ----

def test_short_skill_segments_are_not_cut() -> None:
    pts = [(0, 0.0), (1, 30.0), (2, 60.0), (3, 200.0), (4, 400.0), (5, 600.0)]
    segs = ss.segment(pts, signals=[(0, "a2h-spec"), (1, "a2h-plan"), (2, "a2h-spec"), (3, "a2h-execute")])
    # plan 只有 30 秒(回头读 / 预读),不切;spec 两段并回一段
    assert _top(segs) == [(0, 2, "a2h-spec"), (3, 5, "a2h-execute")]


def test_no_marks_no_pipeline_is_one_session() -> None:
    assert _top(ss.segment(_pts(5), human=[0, 3])) == [(0, 4, "session")]


# ---- 规则 2:最后一个管线阶段结束后,从第一条人工输入起是后续轮 ----

def test_trailing_rounds_start_at_first_human_input_after_pipeline() -> None:
    pts = _pts(20, 60.0)
    segs = ss.segment(pts, signals=[(1, "a2h-spec"), (5, "a2h-execute")], human=[0, 3, 14, 17],
                      last_pipeline_idx=12)
    assert _top(segs) == [(0, 0, "setup"), (1, 4, "a2h-spec"), (5, 13, "a2h-execute"), (14, 19, "after-pipeline")]


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
    assert ss.missing_stages(["a2h-spec", "a2h-plan"]) == []
    assert ss.missing_stages(["session"]) == []
