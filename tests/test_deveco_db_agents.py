"""task 派发的 DevEco 子会话(SQLite 子会话 + 主线 task 工具),按 wugang 0905 的会话形态造最小库:
子会话结束时刻、类型/描述、task 对账与中断、主线 task 跨度不计活跃、合成通知不算人输入、按各自模型计费。"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest

from migloop.adapters import deveco

MIN = 60 * 1000
T0 = 1_788_600_000_000          # 主线首条
TOUCHED = T0 + 5 * 24 * 60 * MIN  # 整库被批量 touch 的时刻(5 天后)
PARENT = "ses_parent"
CHILD_OK = "ses_child_ok"
CHILD_ABORT = "ses_child_abort"
CHILD_OTHER = "ses_child_other"   # 跑在另一家 provider 的模型上
MAIN_MODEL = '{"id":"glm-5.3","providerID":"zhipuai","variant":"default"}'
OTHER_MODEL = '{"id":"GLM-5.3","providerID":"deveco","variant":"default"}'


def _msg(idx, role, parts, created, completed=None):
    return {"info": {"id": "msg_%d" % idx, "role": role, "sessionID": PARENT,
                     "time": {"created": created, "completed": completed or created + 100}},
            "parts": parts}


def _text(t, synthetic=False):
    p = {"type": "text", "text": t}
    if synthetic:
        p["synthetic"] = True
    return p


def _tool(name, start, end, inp, status="completed", metadata=None, call_id=None):
    st = {"status": status, "input": inp, "output": "ok", "time": {"start": start, "end": end}}
    if metadata:
        st["metadata"] = metadata
    return {"type": "tool", "tool": name, "callID": call_id or "c-%s-%d" % (name, start), "state": st}


def _task(start, end, desc, child, status="completed", interrupted=False):
    meta = {"parentSessionId": PARENT, "sessionId": child, "model": "x"}
    if interrupted:
        meta["interrupted"] = True
    return _tool("task", start, end, {"description": desc, "prompt": "do it", "subagent_type": "a2h-closer"},
                 status=status, metadata=meta, call_id="call-" + child)


def _export(messages):
    return {"info": {"id": PARENT, "directory": "D:/proj", "version": "0.1.0-TD.40",
                     "model": {"id": "glm-5.3", "providerID": "zhipuai"},
                     "time": {"created": T0, "updated": TOUCHED}},
            "messages": messages}


def _make_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE session (id TEXT PRIMARY KEY, parent_id TEXT, title TEXT, agent TEXT, model TEXT,
            tokens_input INT, tokens_output INT, tokens_reasoning INT, tokens_cache_read INT,
            tokens_cache_write INT, cost REAL, time_created INT, time_updated INT);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT, time_created INT, time_updated INT);
        CREATE TABLE part (id TEXT PRIMARY KEY, session_id TEXT, message_id TEXT, data TEXT,
            time_created INT, time_updated INT);
    """)

    def child(sid, title, agent, created, work_end, model=MAIN_MODEL):
        con.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sid, PARENT, title, agent, model, 1000, 500, 200, 0, 0, 0.0, created, TOUCHED))
        mid = sid + "-m1"
        con.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                    (mid, sid, json.dumps({"role": "assistant", "time": {"created": created + 1000, "completed": work_end},
                                           "tokens": {"input": 1000, "output": 500, "reasoning": 200}}),
                     created + 1000, work_end))
        con.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                    (sid + "-p1", sid, mid, json.dumps({"type": "reasoning", "text": "想",
                                                       "time": {"start": created + 2000, "end": created + 3000}}),
                     created + 2000, created + 3000))
        con.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                    (sid + "-p2", sid, mid, json.dumps({"type": "tool", "tool": "bash", "callID": sid + "-c",
                                                       "state": {"status": "completed", "input": {"command": "echo"},
                                                                 "output": "ok",
                                                                 "time": {"start": created + 4000, "end": work_end}}}),
                     created + 4000, work_end))

    child(CHILD_OK, "Batch 1 closer (@a2h-closer subagent)", "a2h-closer", T0 + 5 * MIN, T0 + 9 * MIN)
    child(CHILD_ABORT, "FV-1 closer iter1 (@a2h-closer subagent)", "a2h-closer", T0 + 20 * MIN, T0 + 24 * MIN)
    child(CHILD_OTHER, "Base-5 build gate (@hmos-builder subagent)", "hmos-builder", T0 + 30 * MIN, T0 + 34 * MIN,
          model=OTHER_MODEL)
    con.commit()
    con.close()


class DevEcoDbAgentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "deveco.db")
        _make_db(self.db)
        self.trace = deveco._parse(_export([
            _msg(0, "user", [_text("# a2h-execute — 执行\n\n## 1\n")], T0),
            _msg(1, "assistant", [
                {"type": "reasoning", "text": "想", "time": {"start": T0 + MIN, "end": T0 + MIN + 1000}},
                _task(T0 + 5 * MIN, T0 + 9 * MIN, "Batch 1 closer", CHILD_OK),
            ], T0 + MIN),
            _msg(2, "user", [_text('<task id="%s" state="completed">\n<summary>done</summary>' % CHILD_OK,
                                   synthetic=True)], T0 + 9 * MIN),
            _msg(3, "assistant", [
                _task(T0 + 20 * MIN, T0 + 24 * MIN, "FV-1 closer iter1", CHILD_ABORT,
                      status="error", interrupted=True),
            ], T0 + 20 * MIN),
            _msg(4, "user", [_text("retry")], T0 + 25 * MIN),
            _msg(5, "assistant", [_tool("bash", T0 + 26 * MIN, T0 + 26 * MIN + 1000, {"command": "ls"}),
                                  _task(T0 + 30 * MIN, T0 + 34 * MIN, "Base-5 build gate", CHILD_OTHER)],
                 T0 + 26 * MIN),
        ]), storage_root=self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _agent(self, sid):
        return next(a for a in self.trace["agents"] if a["agent_id"] == "subagent:" + sid)

    def test_child_end_is_its_own_last_record_not_session_touch(self):
        a = self._agent(CHILD_OK)
        self.assertEqual(deveco._iso_ms(a["end_ts"]), T0 + 9 * MIN)
        self.assertEqual(a["dur_ms"], 4 * MIN)
        # 阶段墙钟不再被子代理拖到 5 天后
        for s in self.trace["stages"]:
            self.assertLessEqual(deveco._iso_ms(s["end_ts"]), T0 + 40 * MIN)

    def test_type_and_desc_from_task_title(self):
        a = self._agent(CHILD_OK)
        self.assertEqual(a["type"], "a2h-closer")
        self.assertEqual(a["desc"], "Batch 1 closer")
        self.assertEqual(deveco._parse_title("[Implement (2 units)] B01实体模型"), ("implement", "B01实体模型"))
        self.assertEqual(deveco._parse_title("Convert page 0001 MainPage (@a2h-activity-converter subagent)"),
                         ("a2h-activity-converter", "Convert page 0001 MainPage"))

    def test_task_call_linked_and_interrupted_marked(self):
        ok, ab = self._agent(CHILD_OK), self._agent(CHILD_ABORT)
        self.assertEqual(ok["tuid"], "call-" + CHILD_OK)
        self.assertIsNone(ok["aborted"])
        self.assertEqual(ab["tuid"], "call-" + CHILD_ABORT)
        self.assertEqual(ab["aborted"], "interrupted")
        self.assertEqual(self.trace["totals"]["aborted_agents"], 1)
        self.assertEqual(self.trace["totals"]["waste_output_tokens"], 700)   # 500 out + 200 reasoning

    def test_task_wait_not_counted_as_main_activity(self):
        # 主线:reasoning 1s + bash 1s;三个子会话各 1s reasoning + (4min-4s) bash
        child_work = 3 * (1000 + (4 * MIN - 4000))
        self.assertEqual(self.trace["totals"]["active_ms"], 2000 + child_work)

    def test_synthetic_task_notice_is_not_a_user_prompt(self):
        self.assertEqual(self.trace["totals"]["user_prompts"], 2)
        self.assertEqual([p["idx"] for p in self.trace["prompts"]], [0, 4])
        self.assertEqual(self.trace["meta"]["record_count"], 6)   # 消息本身还在

    def test_subagent_billed_under_its_own_model(self):
        self.assertEqual(self._agent(CHILD_OTHER)["model"], "GLM-5.3")
        billing = self.trace["billing"]
        self.assertEqual(billing["GLM-5.3"]["req"], 1)
        self.assertEqual(billing["GLM-5.3"]["out"], 700)
        self.assertEqual(billing["glm-5.3"]["req"], 2)            # 2 个同模型子代理(夹具的主线消息没带 tokens,不计请求)
        self.assertEqual(billing["glm-5.3"]["out"], 1400)

    def test_without_db_task_spans_stand_in_for_child_activity(self):
        trace = deveco._parse(_export([
            _msg(0, "user", [_text("go")], T0),
            _msg(1, "assistant", [_task(T0 + 5 * MIN, T0 + 9 * MIN, "x", CHILD_OK)], T0 + MIN),
        ]), storage_root=self.tmp.name + "/nowhere")
        self.assertEqual(trace["agents"], [])
        self.assertEqual(trace["totals"]["active_ms"], 4 * MIN)


if __name__ == "__main__":
    unittest.main()
