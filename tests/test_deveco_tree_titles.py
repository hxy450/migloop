"""DevEco 直读库:孙代理、子会话标题的结局标记、task 工具名、提示词全文。

对照 hmigbot-plus 3fd7850d 的 DevEco 适配(另起的一版,只看行为):
  · 子代理还能再派子代理,会话树要一路往下取(原来只取直接孩子,孙代理的 token / 读写全丢);
  · 工作流给子会话标题追加 ``[stalled]`` / ``[failed]``:卡死记中断、失败记状态,
    且不能让标题尾巴把 workflow 结果索引对不上;
  · ``task`` 是子代理派发,与 CC 的 Agent 同名;
  · 提示词与 claude / codex 同上限,不在 400 字处截断。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from migloop.adapters import deveco

T0 = 1_794_550_900_000
ROOT, CHILD, GRANDCHILD, FAILED = "ses_root", "ses_child", "ses_grandchild", "ses_failed"
LONG = "用户执行 /hmbot,迁移目标如下:" + "x" * 900


def _db(path: Path, cwd: str) -> str:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE session (id TEXT PRIMARY KEY, parent_id TEXT, slug TEXT, project_id TEXT,
            directory TEXT, path TEXT, title TEXT, agent TEXT, model TEXT, version TEXT,
            summary_additions INTEGER, summary_deletions INTEGER, summary_files INTEGER, cost REAL,
            tokens_input INTEGER, tokens_output INTEGER, tokens_reasoning INTEGER,
            tokens_cache_read INTEGER, tokens_cache_write INTEGER,
            time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER,
            data TEXT);
    """)
    model = json.dumps({"id": "deepseek-v4-flash", "providerID": "custom"})

    def session(sid, parent, title, at, out):
        conn.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (sid, parent, sid, "p", cwd, cwd, title, "build", model, "0.1.3", 0, 0, 0, 0.0,
                      100, out, 5, 1000, 0, T0 + at * 1000, T0 + (at + 60) * 1000))

    n = [0]

    def message(sid, at, data, parts):
        n[0] += 1
        mid = f"msg_{n[0]:03d}"
        conn.execute("INSERT INTO message VALUES (?,?,?,?)", (mid, sid, T0 + at * 1000, json.dumps(data)))
        for i, part in enumerate(parts):
            conn.execute("INSERT INTO part VALUES (?,?,?,?,?)",
                         (f"prt_{n[0]:03d}_{i}", mid, sid, T0 + at * 1000 + i, json.dumps(part)))

    def tool(name, call, inp, at):
        return {"type": "tool", "tool": name, "callID": call,
                "state": {"status": "completed", "input": inp, "output": "ok",
                          "time": {"start": T0 + at * 1000, "end": T0 + at * 1000 + 250}}}

    session(ROOT, None, "DiceRoller 鸿蒙迁移", 0, 50)
    message(ROOT, 0, {"role": "user", "time": {"created": T0}}, [{"type": "text", "text": LONG}])
    message(ROOT, 1, {"role": "assistant", "modelID": "deepseek-v4-flash", "time": {"created": T0 + 1000},
                      "tokens": {"input": 100, "output": 50, "reasoning": 5, "cache": {"read": 1000, "write": 0}}},
            [tool("task", "c1", {"description": "impl core-dice", "prompt": "do it",
                                 "subagent_type": "general"}, 2)])
    session(CHILD, ROOT, "[Implement] impl:core-dice", 20, 70)
    message(CHILD, 21, {"role": "assistant"}, [tool("edit", "c2", {"filePath": cwd + "/entry/A.ets"}, 22)])
    session(GRANDCHILD, CHILD, "[Verify] verify:core-dice [stalled]", 40, 30)
    message(GRANDCHILD, 41, {"role": "assistant"}, [tool("read", "c3", {"filePath": "/x"}, 42)])
    session(FAILED, ROOT, "[Verify] verify:page-main [failed]", 80, 10)
    conn.commit()
    conn.close()
    return str(path)


def test_db_tree_titles_tools_and_prompts(tmp_path: Path) -> None:
    db = _db(tmp_path / "deveco.db", str(tmp_path / "harmony"))
    trace = deveco.extract_from_db(ROOT, storage_root=db)

    agents = {a["agent_id"].split(":", 1)[-1]: a for a in trace["agents"]}
    assert set(agents) == {CHILD, GRANDCHILD, FAILED}, "孙代理也是这棵树的一部分"
    assert agents[GRANDCHILD]["tool_uses"] == 1
    assert trace["totals"]["subagent_output_tokens"] == (70 + 5) + (30 + 5) + (10 + 5)

    assert (agents[GRANDCHILD]["status"], agents[GRANDCHILD]["aborted"]) == ("stalled", "stalled")
    assert (agents[FAILED]["status"], agents[FAILED]["aborted"]) == ("failed", None), "失败是结论,不算中断"
    assert (agents[CHILD]["status"], agents[CHILD]["aborted"]) == ("completed", None)
    assert agents[FAILED]["type"] == "verify"

    assert [t["name"] for t in trace["tools"]] == ["Agent"]
    assert trace["prompts"][0]["text"] == " ".join(LONG.split()), "提示词不在 400 字处截断"


def test_title_outcome_is_not_part_of_the_unit_label() -> None:
    assert deveco._parse_title("[Verify] verify:page-main [failed]") == ("verify", "verify:page-main")
    assert deveco._parse_title("[Implement (2 units)] B01实体模型") == ("implement", "B01实体模型")
    assert deveco._title_outcome("[Verify] verify:x [stalled]") == "stalled"
    assert deveco._title_outcome("[Verify] verify:x") is None
