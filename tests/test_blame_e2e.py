"""CC 会话 → 行级归属端到端:Write/Edit 实录重放出 blame/takeovers 字段。"""

from __future__ import annotations

import json
from pathlib import Path

from migloop.adapters import claude as cc


def _mk_session(root: Path) -> Path:
    sid = "beef0000-0000-4000-8000-000000000001"
    main = root / f"{sid}.jsonl"
    ts = "2026-08-20T02:00:{s:02d}.000Z"
    recs = [
        {"type": "user", "timestamp": ts.format(s=0), "cwd": str(root),
         "sessionId": sid, "message": {"content": "start"}},
        {"type": "assistant", "timestamp": ts.format(s=1), "message": {
            "model": "claude-opus-5", "id": "m1", "usage": {"output_tokens": 10},
            "content": [{"type": "tool_use", "id": "tu1", "name": "Task",
                          "input": {"prompt": "convert page"}}]}},
        {"type": "assistant", "timestamp": ts.format(s=2), "message": {
            "model": "claude-opus-5", "id": "m2", "usage": {"output_tokens": 10},
            "content": [{"type": "tool_use", "id": "tu2", "name": "Task",
                          "input": {"prompt": "fix page"}}]}},
    ]
    main.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")

    ets = str(root / "entry" / "src" / "A.ets")
    sub = root / sid / "subagents"
    sub.mkdir(parents=True)

    def agent(name: str, atype: str, tuid: str, s: int, tool: dict) -> None:
        (sub / f"agent-{name}.meta.json").write_text(json.dumps({
            "agentType": atype, "description": name, "toolUseId": tuid}),
            encoding="utf-8")
        srecs = [
            {"type": "user", "timestamp": ts.format(s=s),
             "message": {"content": "work"}},
            {"type": "assistant", "timestamp": ts.format(s=s + 1), "message": {
                "model": "claude-opus-5", "id": f"{name}-1",
                "usage": {"output_tokens": 5},
                "content": [{"type": "tool_use", "id": f"{name}-tu", **tool}]}},
            {"type": "assistant", "timestamp": ts.format(s=s + 2), "message": {
                "model": "claude-opus-5", "id": f"{name}-e", "stop_reason": "end_turn",
                "usage": {"output_tokens": 5},
                "content": [{"type": "text", "text": "done"}]}},
        ]
        (sub / f"agent-{name}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in srecs) + "\n", encoding="utf-8")

    agent("g1", "a2h-migration-worker", "tu1", 5, {
        "name": "Write", "input": {"file_path": ets,
                                   "content": "l1\nl2\nl3\nl4"}})
    agent("f1", "visual-fixer", "tu2", 20, {
        "name": "Edit", "input": {"file_path": ets, "old_string": "l2\nl3",
                                  "new_string": "L2\nL3fix"}})
    return main


def test_blame_fields_land_on_ets_file_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    trace = cc.extract(str(_mk_session(tmp_path)))
    ets = [f for f in trace["lineage"]["files"] if f["kind"] == "ets"]
    assert len(ets) == 1
    f = ets[0]
    assert f["blame_broken"] is None
    assert f["blame"] == [[1, 1, "g1"], [2, 3, "f1"], [4, 4, "g1"]]
    assert f["takeovers"] == [{"by": "f1", "lines": 2, "from": {"g1": 2}}]


def test_out_of_band_edit_degrades_honestly(tmp_path, monkeypatch):
    """old_string 对不上(实录外改动)→ blame=None + 原因,不硬猜。"""
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    main = _mk_session(tmp_path)
    jl = tmp_path / "beef0000-0000-4000-8000-000000000001" / "subagents" / "f1.jsonl"
    jl = jl.parent / "agent-f1.jsonl"
    body = jl.read_text(encoding="utf-8").replace("l2\\nl3", "not-in-file")
    jl.write_text(body, encoding="utf-8")
    trace = cc.extract(str(main))
    f = [x for x in trace["lineage"]["files"] if x["kind"] == "ets"][0]
    assert f["blame"] is None
    assert f["blame_broken"] == "edit-miss"


def test_collect_blame_events_cc(tmp_path, monkeypatch):
    """CC 版跨会话事件采集:主线+子代理的 .ets 写事件,含明文 payload,
    输出形状与 codex.collect_blame_events 一致。"""
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    main = _mk_session(tmp_path)
    ev = cc.collect_blame_events(str(main))
    assert len(ev) == 2
    ts0, path0, who0, op0, payload0 = ev[0]
    assert who0 == "g1" and op0 == "write" and payload0.startswith("l1")
    assert path0.replace("\\", "/").endswith("entry/src/A.ets")
    ts1, path1, who1, op1, payload1 = ev[1]
    assert who1 == "f1" and op1 == "edits" and payload1[0][0] == "l2\nl3"
    assert ts0 < ts1
