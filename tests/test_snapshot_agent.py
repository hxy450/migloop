"""子代理转录是主会话快照的识别 —— adapter 只标记不剔除,审计据此点名。

运行时把主会话的快照当子代理上传(migbot-runtime-src#46):这种"代理"的记录 uuid
全部落在主会话里。分析页忠实画出来(遮掉就没人修),但要一眼认出、审计要点名。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from migloop import audit
from migloop.adapters import claude as cc

if TYPE_CHECKING:
    from pathlib import Path

SID = "cafe0000-0000-4000-8000-000000000002"
_TS = "2026-08-20T01:00:{s:02d}.000Z"


def _main_records(root: Path) -> list[dict]:
    return [
        {"type": "user", "uuid": "u0", "timestamp": _TS.format(s=0), "cwd": str(root),
         "sessionId": SID, "message": {"content": "start"}},
        {"type": "assistant", "uuid": "u1", "timestamp": _TS.format(s=1), "message": {
            "model": "claude-opus-5", "id": "m1", "usage": {"output_tokens": 10},
            "content": [{"type": "tool_use", "id": "tu1", "name": "Task",
                          "input": {"prompt": "build it"}}]}},
        {"type": "assistant", "uuid": "u2", "timestamp": _TS.format(s=2), "message": {
            "model": "claude-opus-5", "id": "m2", "usage": {"output_tokens": 10},
            "content": [{"type": "tool_use", "id": "tu2", "name": "Task",
                          "input": {"prompt": "convert page"}}]}},
    ]


def _dump(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _mk_session(root: Path) -> Path:
    main = root / f"{SID}.jsonl"
    recs = _main_records(root)
    _dump(main, recs)
    sub = root / SID / "subagents"
    sub.mkdir(parents=True)
    # 假代理:转录 = 主会话前两条的快照,uuid 全部落在主会话里
    (sub / "agent-fake.meta.json").write_text(json.dumps(
        {"agentType": "hmos-builder", "description": "build", "toolUseId": "tu1"}),
        encoding="utf-8")
    _dump(sub / "agent-fake.jsonl", recs[:2])
    # 真代理:自己的记录,uuid 与主会话无交集
    (sub / "agent-real.meta.json").write_text(json.dumps(
        {"agentType": "a2h-activity-converter", "description": "conv", "toolUseId": "tu2"}),
        encoding="utf-8")
    _dump(sub / "agent-real.jsonl", [
        {"type": "user", "uuid": "s0", "timestamp": _TS.format(s=3),
         "message": {"content": "do the work"}},
        {"type": "assistant", "uuid": "s1", "timestamp": _TS.format(s=4), "message": {
            "model": "claude-opus-5", "id": "se", "stop_reason": "end_turn",
            "usage": {"output_tokens": 5}, "content": [{"type": "text", "text": "done"}]}},
    ])
    return main


def test_snapshot_agent_flagged_and_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    trace = cc.extract(str(_mk_session(tmp_path)))
    by = {a["agent_id"]: a for a in trace["agents"]}
    assert set(by) == {"fake", "real"}, "只标记不剔除"
    assert by["fake"]["snapshot_of_main"] is True
    assert by["real"]["snapshot_of_main"] is False
    hits = [f for f in audit.build_audit(trace)["findings"] if f["rule"] == "agent-snapshot"]
    assert hits and hits[0]["agents"] == ["fake"]


def test_snapshot_flag_survives_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_SUB_CACHE", {})
    main = _mk_session(tmp_path)
    cc.extract(str(main))
    warm = cc.extract(str(main))
    assert {a["agent_id"]: a["snapshot_of_main"] for a in warm["agents"]} == {
        "fake": True, "real": False}
