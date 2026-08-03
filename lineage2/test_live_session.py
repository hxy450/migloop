# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest

from live_session import IncrementalSessionMonitor, IntervalIndex, _attach_live_controls


def append_jsonl(path, record, newline=True):
    payload = json.dumps(record, ensure_ascii=False).encode("utf-8")
    with open(path, "ab") as stream:
        stream.write(payload)
        if newline:
            stream.write(b"\n")
    return len(payload) + (1 if newline else 0)


class IncrementalLiveSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.android = os.path.join(root, "android")
        self.project = os.path.join(root, "migration")
        self.cache = os.path.join(root, "cache")
        os.makedirs(os.path.join(self.android, "app", "src", "main", "java"), exist_ok=True)
        os.makedirs(self.project, exist_ok=True)
        open(os.path.join(self.android, "settings.gradle"), "w").close()
        self.java = os.path.join(self.android, "app", "src", "main", "java", "Foo.java")
        with open(self.java, "w", encoding="utf-8") as stream:
            stream.write("class Foo {\n  int value;\n}\n")
        self.session = os.path.join(self.project, "session-1.jsonl")
        open(self.session, "wb").close()

    def tearDown(self):
        self.tmp.cleanup()

    def _monitor(self, reset=False):
        return IncrementalSessionMonitor(
            self.session, cache_dir=self.cache, poll_interval=0.05,
            checkpoint_interval=0.01, reset_cache=reset,
        )

    def test_interval_union_reports_only_new_lines(self):
        index = IntervalIndex()
        self.assertEqual(2, index.add("Foo.java", [(1, 2)]))
        self.assertEqual(1, index.add("Foo.java", [(2, 2)]))
        self.assertEqual(0, index.add("Foo.java", [(1, 3)]))
        self.assertEqual([[1, 3]], index.to_json()["Foo.java"])

    def test_real_analysis_page_gets_live_controller(self):
        page = _attach_live_controls(
            b"<html><body><main>real analysis</main></body></html>",
            baseline_version=7, baseline_records=120, poll_ms=10000,
        ).decode("utf-8")
        self.assertIn("real analysis", page)
        self.assertIn("BASELINE_VERSION=7", page)
        self.assertIn("BASELINE_RECORDS=120", page)
        self.assertIn("setInterval(tick,10000)", page)
        self.assertIn('href="/refresh"', page)

    def test_reads_only_appended_bytes_and_restores_checkpoint(self):
        first = {
            "type": "user", "timestamp": "2026-08-02T12:00:00Z",
            "sessionId": "session-1", "cwd": self.project,
            "promptSource": "typed", "message": {"content": "start"},
        }
        tool = {
            "type": "assistant", "timestamp": "2026-08-02T12:00:01Z",
            "sessionId": "session-1", "cwd": self.project,
            "message": {
                "id": "m1", "model": "claude-test", "stop_reason": "tool_use",
                "usage": {"input_tokens": 10, "output_tokens": 5,
                          "cache_read_input_tokens": 2},
                "content": [{"type": "tool_use", "id": "t1", "name": "Read",
                             "input": {"file_path": self.java}}],
            },
        }
        result = {
            "type": "user", "timestamp": "2026-08-02T12:00:02Z",
            "sessionId": "session-1", "cwd": self.project,
            "toolUseResult": {"file": {"numLines": 3, "startLine": 1, "totalLines": 3}},
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                        "content": "1\tclass Foo {\n2\t  int value;\n3\t}"}]},
        }
        total = sum(append_jsonl(self.session, r) for r in (first, tool, result))
        monitor = self._monitor(reset=True)
        self.assertTrue(monitor.poll_once())
        snap = monitor.snapshot()
        self.assertEqual(total, snap["bytes_read_last"])
        self.assertEqual(3, snap["coverage"]["code_lines"])
        self.assertEqual(1, snap["tool_calls"])
        self.assertEqual(5, snap["output_tokens"])
        monitor.save_checkpoint(force=True)

        resumed = self._monitor()
        self.assertTrue(resumed.loaded_checkpoint)
        self.assertFalse(resumed.poll_once())
        self.assertEqual(0, resumed.snapshot()["bytes_read_last"])

        record = {
            "type": "assistant", "timestamp": "2026-08-02T12:00:03Z",
            "sessionId": "session-1", "cwd": self.project,
            "message": {"id": "m2", "model": "claude-test", "stop_reason": "end_turn",
                        "usage": {"input_tokens": 4, "output_tokens": 7},
                        "content": [{"type": "text", "text": "done"}]},
        }
        added = append_jsonl(self.session, record)
        self.assertTrue(resumed.poll_once())
        snap = resumed.snapshot()
        self.assertEqual(added, snap["bytes_read_last"])
        self.assertEqual(12, snap["output_tokens"])
        self.assertEqual("waiting", snap["status"])

    def test_incomplete_tail_and_subagent_running_state(self):
        record = {
            "type": "user", "timestamp": "2026-08-02T12:00:00Z",
            "sessionId": "session-1", "cwd": self.project,
            "promptSource": "typed", "message": {"content": "go"},
        }
        raw = json.dumps(record).encode("utf-8")
        cut = len(raw) // 2
        with open(self.session, "ab") as stream:
            stream.write(raw[:cut])
        monitor = self._monitor(reset=True)
        self.assertTrue(monitor.poll_once())
        self.assertEqual(0, monitor.snapshot()["records"])
        with open(self.session, "ab") as stream:
            stream.write(raw[cut:] + b"\n")
        self.assertTrue(monitor.poll_once())
        self.assertEqual(1, monitor.snapshot()["records"])

        sub = os.path.splitext(self.session)[0] + os.sep + "subagents"
        os.makedirs(sub, exist_ok=True)
        agent = os.path.join(sub, "agent-a1.jsonl")
        with open(os.path.join(sub, "agent-a1.meta.json"), "w", encoding="utf-8") as stream:
            json.dump({"agentType": "general", "description": "inspect source"}, stream)
        append_jsonl(agent, {
            "type": "assistant", "timestamp": "2026-08-02T12:00:02Z",
            "message": {"id": "a-m1", "model": "claude-test", "stop_reason": "tool_use",
                        "usage": {"output_tokens": 3},
                        "content": [{"type": "tool_use", "id": "a-t1", "name": "Grep",
                                     "input": {"pattern": "Foo", "path": self.java}}]},
        })
        self.assertTrue(monitor.poll_once())
        snap = monitor.snapshot()
        self.assertEqual(1, snap["agent_counts"].get("running"))
        append_jsonl(agent, {
            "type": "assistant", "timestamp": "2026-08-02T12:00:03Z",
            "message": {"id": "a-m2", "model": "claude-test", "stop_reason": "end_turn",
                        "usage": {"output_tokens": 2},
                        "content": [{"type": "text", "text": "complete"}]},
        })
        self.assertTrue(monitor.poll_once())
        snap = monitor.snapshot()
        self.assertEqual(1, snap["agent_counts"].get("completed"))
        self.assertEqual(5, snap["agents"][0]["output_tokens"])

    def test_legacy_text_only_subagent_without_stop_reason_is_completed(self):
        sub = os.path.splitext(self.session)[0] + os.sep + "subagents"
        os.makedirs(sub, exist_ok=True)
        agent = os.path.join(sub, "agent-legacy.jsonl")
        append_jsonl(agent, {
            "type": "assistant", "timestamp": "2026-08-02T12:00:02Z",
            "message": {
                "id": "legacy-final", "model": "claude-test",
                "usage": {"output_tokens": 9},
                "content": [{"type": "text", "text": "migration complete"}],
            },
        })
        monitor = self._monitor(reset=True)
        self.assertTrue(monitor.poll_once())
        snap = monitor.snapshot()
        self.assertEqual(1, snap["agent_counts"].get("completed"))
        self.assertNotIn("running", snap["agent_counts"])

    def test_truncated_stream_replays_instead_of_retaining_old_totals(self):
        append_jsonl(self.session, {
            "type": "user", "timestamp": "2026-08-02T12:00:00Z",
            "sessionId": "session-1", "cwd": self.project,
            "promptSource": "typed", "message": {"content": "old"},
        })
        monitor = self._monitor(reset=True)
        monitor.poll_once()
        self.assertEqual(1, monitor.snapshot()["user_prompts"])
        with open(self.session, "wb") as stream:
            stream.write((json.dumps({
                "type": "assistant", "timestamp": "2026-08-02T12:10:00Z",
                "sessionId": "session-1", "cwd": self.project,
                "message": {"id": "new", "model": "claude-test",
                            "stop_reason": "end_turn", "usage": {"output_tokens": 9},
                            "content": [{"type": "text", "text": "new"}]},
            }) + "\n").encode("utf-8"))
        monitor.poll_once()
        snap = monitor.snapshot()
        self.assertEqual(0, snap["user_prompts"])
        self.assertEqual(9, snap["output_tokens"])
        self.assertEqual(1, snap["records"])


if __name__ == "__main__":
    unittest.main()
