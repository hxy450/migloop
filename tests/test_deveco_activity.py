"""DevEco 的 question 工具是停下来等用户点选,state.time 跨的是人回答的时间,不能算活跃
(wugang 09-10 的会话:夜里 00:10 问、早上 08:10 答,8 小时全算成了「活跃」)。"""
from __future__ import annotations

import tempfile
import unittest

from migloop.adapters import deveco

HOUR = 3600 * 1000


def _msg(idx, role, parts, created):
    return {"info": {"id": "msg_%d" % idx, "role": role, "sessionID": "ses_x",
                     "time": {"created": created, "completed": created + 100}},
            "parts": parts}


def _tool(name, start, end, inp):
    return {"type": "tool", "tool": name, "callID": "c-%s-%d" % (name, start),
            "state": {"status": "completed", "input": inp, "output": "ok",
                      "time": {"start": start, "end": end}}}


def _export(messages):
    return {"info": {"id": "ses_x", "directory": "D:/proj", "version": "0.1.0",
                     "model": {"id": "glm-5.3-flash", "providerID": "zhipuai"},
                     "time": {"created": 1000, "updated": 2 * HOUR}},
            "messages": messages}


def _parse(data):
    with tempfile.TemporaryDirectory() as empty:
        return deveco._parse(data, storage_root=empty)


class DevEcoActivityTest(unittest.TestCase):
    def test_question_wait_is_not_active_time(self):
        trace = _parse(_export([
            _msg(0, "user", [{"type": "text", "text": "开始"}], 1000),
            _msg(1, "assistant", [
                {"type": "reasoning", "text": "想", "time": {"start": 2000, "end": 3000}},
                _tool("bash", 4000, 5000, {"command": "echo hi"}),
                _tool("question", 6000, 6000 + HOUR, {"questions": [{"question": "选哪个?"}]}),
            ], 2000),
            _msg(2, "assistant", [_tool("bash", 6000 + HOUR, 7000 + HOUR, {"command": "echo bye"})],
                 6000 + HOUR),
        ]))
        # reasoning 1s + bash 1s + bash 1s = 3s;question 等的那 1 小时不算
        self.assertEqual(trace["totals"]["active_ms"], 3000)
        self.assertEqual(trace["stages"][0]["active_ms"], 3000)
        self.assertGreaterEqual(trace["totals"]["duration_ms"], HOUR)
        # 工具本身仍在列表里,只是不计活跃
        self.assertEqual([t["name"] for t in trace["tools"]], ["Bash", "question", "Bash"])
        self.assertEqual(trace["tools"][1]["dur_ms"], HOUR)


if __name__ == "__main__":
    unittest.main()
