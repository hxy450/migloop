"""service 层对齐 hmigbot routes 的返修链接线:名片按字段补账本、run 级阶段区间与 execute 结束时刻。"""
from __future__ import annotations

import json
from typing import Any

from migloop import atoms, service


def test_fixchain_meta_falls_back_to_ledger_cards_for_agents_lineage_lacks() -> None:
    """血缘层认识某子代理但名片是空的(desc None、派发词空)—— 整卡覆盖会把账本的名字盖回裸 id,按字段补空;
    主会话不补;血缘层有的字段以它为准。"""
    led = atoms.Ledger(stories={}, agents={
        "agent-a4874344c8fb6228d": atoms.AgentRec(
            id="agent-a4874344c8fb6228d", session="81e0a463", description="修 round-1 视觉差异",
            kind="visual-fixer", stage="arkts-visual-verify", prompt="P" * 300, result="R" * 300),
        "agent-a1111111111111111": atoms.AgentRec(
            id="agent-a1111111111111111", session="81e0a463", description="账本名片", stage="a2h-execute"),
        "__main__:81e0a463": atoms.AgentRec(id="__main__:81e0a463", session="81e0a463"),
    })
    lineage: dict[str, dict[str, Any]] = {
        "a1111111111111111": {"desc": "血缘层名片", "stage": "a2h-plan", "prompt": "", "note": ""},
        "a4874344c8fb6228d": {"desc": None, "stage": "arkts-visual-verify", "prompt": "", "note": ""},
        "only-lineage": {"desc": "账本没有的", "stage": None, "prompt": "", "note": ""}}
    meta = service._merge_ledger_meta(lineage, led)
    assert set(meta) == {"a4874344c8fb6228d", "a1111111111111111", "only-lineage"}
    card = meta["a4874344c8fb6228d"]
    assert card["desc"] == "修 round-1 视觉差异" and card["stage"] == "arkts-visual-verify"
    assert len(card["prompt"]) == 200 and len(card["note"]) == 280
    assert meta["a1111111111111111"] == {"desc": "血缘层名片", "stage": "a2h-plan", "prompt": "", "note": "",
                                        "parent": None, "parent_name": None}
    assert meta["only-lineage"]["desc"] == "账本没有的"
    assert lineage["a4874344c8fb6228d"]["desc"] is None


def test_run_stage_intervals_reads_marks_next_to_transcript(tmp_path: Any) -> None:
    """转录同目录的 stage-marks.json(导出包 / 离线分析摆放):管线技能的 mark 打在阶段结束,
    fix_boundary = 最后一段 a2h-execute 的结束时刻。"""
    p = tmp_path / "abcdef12-0000-0000-0000-000000000000.jsonl"
    p.write_text(json.dumps({"timestamp": "2026-09-03T14:26:14.856Z", "type": "user", "cwd": "/proj",
                             "message": {"role": "user", "content": "go"}}) + "\n", encoding="utf-8")
    (tmp_path / "stage-marks.json").write_text(json.dumps({"marks": [
        {"stage": "a2h-init", "ts": "2026-09-03T14:26:00Z"},
        {"stage": "a2h-spec", "ts": "2026-09-03T15:02:00Z"},
        {"stage": "a2h-plan", "ts": "2026-09-03T15:19:00Z"},
        {"stage": "a2h-execute", "ts": "2026-09-03T16:46:29Z"},
        {"stage": "a2h-verify", "ts": "2026-09-03T20:19:00Z"},
    ]}), encoding="utf-8")
    iv = service.run_stage_intervals(str(p), "")
    stages = [x["stage"] for x in iv]
    assert "a2h-execute" in stages and "a2h-verify" in stages
    from migloop import atoms_collect
    assert atoms_collect.fix_boundary(iv).startswith("2026-09-03T16:46:29")
