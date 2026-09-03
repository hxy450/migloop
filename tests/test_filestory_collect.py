"""CC 收集器契约:合成一份最小 CC transcript,断言五种事件的翻译。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from migloop.filestory import build_stories
from migloop.filestory_collect import collect_events_cc

SID = "cafe0000-0000-4000-8000-000000000001"
CWD = "C:\\proj"


def _rec(ts: str, blocks: list[dict], cwd: str = CWD) -> dict:
    return {"timestamp": ts, "cwd": cwd,
            "message": {"content": blocks}}


def _tool_use(name: str, tid: str, inp: dict) -> dict:
    return {"type": "tool_use", "name": name, "id": tid, "input": inp}


def _tool_result(tid: str, text: str) -> dict:
    return {"type": "tool_result", "tool_use_id": tid,
            "content": [{"type": "text", "text": text}]}


def _mk(tmp_path: Path) -> str:
    main = tmp_path / f"{SID}.jsonl"
    recs = [
        # Read 全文快照(观测)
        {"timestamp": "T01", "cwd": CWD,
         "toolUseResult": {"file": {"filePath": "spec/ref.md", "content": "ref\n",
                                    "startLine": 1, "numLines": 1, "totalLines": 1}},
         "message": {"content": [_tool_result("t0", "ok")]}},
        # Write
        _rec("T02", [_tool_use("Write", "t1",
                               {"file_path": "spec/a.md", "content": "v1\n"})]),
        # Edit
        _rec("T03", [_tool_use("Edit", "t2",
                               {"file_path": "spec/a.md", "old_string": "v1",
                                "new_string": "v2"})]),
        # heredoc 全文写
        _rec("T04", [_tool_use("Bash", "t3",
                               {"command": "cat > spec/b.md <<'EOF'\nbody\nEOF"})]),
        # sed 区间读 + 程序落盘(opaque)
        _rec("T05", [_tool_use("Bash", "t4",
                               {"command": "sed -n '3,5p' spec/a.md && python3 g.py > spec/c.md"})]),
        # 干净 cat:输出=快照
        _rec("T06", [_tool_use("Bash", "t5", {"command": "cat spec/b.md"})]),
        _rec("T07", [_tool_result("t5", "body\n")]),
        # cp:依赖读 + 派生写(收集层给 wopaque;派生解析属引擎后续)
        _rec("T08", [_tool_use("Bash", "t6",
                               {"command": "cp spec/b.md spec/d.md"})]),
    ]
    main.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    sub = tmp_path / SID / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-conv1.jsonl").write_text(json.dumps(
        {"timestamp": "T09", "cwd": CWD,
         "toolUseResult": {"file": {"filePath": "spec/a.md", "content": "v2\n",
                                    "startLine": 1, "numLines": 1,
                                    "totalLines": 1}},
         "message": {"content": [_tool_result("t7", "ok")]}}) + "\n",
        encoding="utf-8")
    return str(main)


def test_collect_translates_all_channels(tmp_path: Path) -> None:
    evs = collect_events_cc(_mk(tmp_path))
    kinds = [(e.kind, e.path.rsplit("/", 1)[-1]) for e in evs]
    assert ("read", "ref.md") in kinds          # Read 快照
    assert ("wfull", "a.md") in kinds           # Write
    assert ("edit", "a.md") in kinds            # Edit
    assert ("wfull", "b.md") in kinds           # heredoc 全文
    assert ("wopaque", "c.md") in kinds         # 程序落盘
    r_sed = next(e for e in evs if e.kind == "read" and e.start == 3)
    assert r_sed.n == 3                          # sed 区间保留
    cat_obs = [e for e in evs if e.kind == "read" and e.path.endswith("b.md")
               and e.content == "body\n"]
    assert cat_obs and cat_obs[0].full           # 干净 cat = 全文快照
    dep = [e for e in evs if e.dep]
    assert dep and dep[0].path.endswith("b.md")  # cp 源 = 依赖读


def test_agent_identity_main_vs_subagent(tmp_path: Path) -> None:
    evs = collect_events_cc(_mk(tmp_path))
    mains = {e.agent for e in evs if e.ts <= "T08"}
    assert mains == {"__main__:cafe0000"}
    assert any(e.agent == "agent-conv1" for e in evs)


def test_codex_collector_translates_patch_and_shell(tmp_path: Path) -> None:
    from migloop.filestory_collect import collect_events_codex

    patch = ("*** Begin Patch\n"
             "*** Add File: entry/src/main/ets/A.ets\n"
             "+line1\n+line2\n"
             "*** Update File: entry/src/main/ets/A.ets\n"
             "@@\n line1\n-line2\n+line2x\n"
             "*** End Patch")
    js = ('const p = await tools.shell_command({ command: "cat spec/x.md", '
          'workdir: "C:/proj" });\n'
          'await tools.apply_patch(' + json.dumps(patch) + ');')
    recs = [
        {"timestamp": "T00", "type": "session_meta",
         "payload": {"cwd": "C:/proj", "id": "feedbeef-0000"}},
        {"timestamp": "T01", "payload": {"type": "custom_tool_call", "name": "exec",
                                         "call_id": "c1", "input": js}},
        {"timestamp": "T02", "payload": {"type": "custom_tool_call_output",
                                         "call_id": "c1",
                                         "output": [{"type": "input_text",
                                                     "text": "Script completed\nWall time 0.1 seconds\nOutput:\nx-doc\n"}]}},
    ]
    p = tmp_path / "rollout-2026-01-01T00-00-00-feedbeef-0000.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    evs = collect_events_codex(str(p), str(tmp_path))
    kinds = [(e.kind, e.path.rsplit("/", 1)[-1]) for e in evs]
    assert ("wfull", "A.ets") in kinds           # Add File → 全文写
    assert ("edit", "A.ets") in kinds            # Update hunk → 原生差量
    e_edit = next(e for e in evs if e.kind == "edit")
    assert e_edit.old == "line1\nline2" and e_edit.new == "line1\nline2x"
    obs = [e for e in evs if e.kind == "read" and e.content]
    assert obs and obs[0].content == "x-doc\n" and obs[0].full   # 输出剥壳后的干净 cat 快照
    st = build_stories(evs)
    a = st["C:/proj/entry/src/main/ets/A.ets"]
    assert [v.diff_kind for v in a.versions] == ["creation", "native"]
    assert a.versions[-1].content == "line1\nline2x\n"


def test_collected_events_feed_engine(tmp_path: Path) -> None:
    stories = build_stories(collect_events_cc(_mk(tmp_path)))
    a = stories[f"{CWD.replace(chr(92), '/')}/spec/a.md"]
    assert [v.diff_kind for v in a.versions] == ["creation", "native"]
    b = stories[f"{CWD.replace(chr(92), '/')}/spec/b.md"]
    assert b.versions[0].content == "body\n"     # heredoc 体
    ref = stories[f"{CWD.replace(chr(92), '/')}/spec/ref.md"]
    assert ref.versions[0].by == "__external__"  # 外部输入,首见即读
