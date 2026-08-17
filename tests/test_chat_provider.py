# -*- coding: utf-8 -*-
import json
import os
import tempfile
import threading
import unittest
import urllib.request

from migloop.chat import provider as chat_provider
from migloop.live.monitor import LiveHTTPServer


class _Monitor:
    def snapshot(self):
        return {"version": 3, "records": 17, "session_id": "abc12345"}


class _Chat:
    def info(self):
        return {"enabled": True, "provider": "fake", "model": "test-model"}

    def chat(self, messages):
        clean = chat_provider.normalize_messages(messages)
        return "answer: " + clean[-1]["content"]


class ChatProviderTest(unittest.TestCase):
    def test_lineage_context_is_bounded_and_keeps_denominators(self):
        trace = {
            "meta": {"session_id": "s1", "cwd": "project", "record_count": 9},
            "totals": {"agent_calls": 2},
            "workflows": [{"name": "analysis", "agent_count": 2}],
            "lineage": {
                "stats": {"android_files": 10, "spec_files": 2},
                "android_total": {"files": 20, "code_lines": 500},
                "agents": [{"agent_id": "a1", "stage": "wf:analysis", "n_android": 5}],
                "specs": [{"path": "spec/a.md", "kind": "analysis", "authors": ["a1"]}],
                "files": [{"path": "entry/src/A.ets", "kind": "ets", "final_lines": 40,
                           "writers": ["a1"]}],
                "android": [{"path": "A.java", "readers": []}],
            },
        }
        result = chat_provider.build_lineage_context(trace, max_chars=5000)
        self.assertLessEqual(len(result), 5000)
        self.assertIn('"android_files": 10', result)
        self.assertIn('"files": 20', result)
        self.assertIn("spec/a.md", result)

    def test_message_validation_requires_last_user_turn(self):
        with self.assertRaises(chat_provider.ChatConfigurationError):
            chat_provider.normalize_messages([{"role": "assistant", "content": "done"}])
        self.assertEqual("hello", chat_provider.normalize_messages([
            {"role": "user", "content": " hello "}
        ])[0]["content"])

    def test_session_corpus_covers_main_and_subagent_records(self):
        with tempfile.TemporaryDirectory() as root:
            main = os.path.join(root, "session.jsonl")
            session_dir = os.path.splitext(main)[0]
            sub_dir = os.path.join(session_dir, "subagents")
            os.makedirs(sub_dir)
            with open(main, "w", encoding="utf-8") as stream:
                stream.write(json.dumps({"type": "user", "message": {"content": "检查支付流程"}}, ensure_ascii=False) + "\n")
            with open(os.path.join(sub_dir, "agent-a.jsonl"), "w", encoding="utf-8") as stream:
                stream.write(json.dumps({"type": "assistant", "message": {"content": "支付回调缺少失败分支"}}, ensure_ascii=False) + "\n")
            corpus = chat_provider.SessionCorpus(main)
            manifest = corpus.manifest()
            self.assertEqual(2, manifest["record_file_count"])
            evidence = corpus.retrieve("支付失败分支", max_chars=8000)
            self.assertIn("agent-a.jsonl", evidence)
            self.assertIn("支付回调缺少失败分支", evidence)

    def test_live_server_exposes_chat_ui_and_api(self):
        server = LiveHTTPServer(
            ("127.0.0.1", 0), _Monitor(),
            lambda: b"<html><body>analysis</body></html>",
            dashboard_poll_ms=10000, chat_service=_Chat(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            with urllib.request.urlopen(base + "/", timeout=3) as response:
                page = response.read().decode("utf-8")
            self.assertIn("Agent 分析", page)
            self.assertIn("test-model", page)

            request = urllib.request.Request(
                base + "/api/chat",
                data=json.dumps({"messages": [{"role": "user", "content": "progress?"}]}).encode(),
                method="POST", headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual("answer: progress?", payload["reply"])
            self.assertEqual("fake", payload["provider"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
