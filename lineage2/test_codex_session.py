# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest

import extract_codex_session
import migloop


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def rec(ts, outer, payload):
    return {"timestamp": ts, "type": outer, "payload": payload}


class CodexSessionAdapterTest(unittest.TestCase):
    def test_multi_agent_rollout_normalizes_to_migloop_trace(self):
        with tempfile.TemporaryDirectory() as root:
            project = os.path.join(root, "harmony")
            android = os.path.join(root, "android")
            source = os.path.join(android, "app", "src", "main", "java", "Demo.java")
            spec = os.path.join(project, "spec", "baseline", "features", "F001.md")
            os.makedirs(os.path.dirname(source), exist_ok=True)
            os.makedirs(os.path.dirname(spec), exist_ok=True)
            with open(os.path.join(android, "settings.gradle"), "w", encoding="utf-8") as stream:
                stream.write("rootProject.name='demo'\n")
            java_text = "public class Demo {\n  int value = 1;\n  void run() { value++; }\n}\n"
            with open(source, "w", encoding="utf-8") as stream:
                stream.write(java_text)
            with open(spec, "w", encoding="utf-8") as stream:
                stream.write("# Feature\n")

            root_id, child_id = "root-1", "child-1"
            main_path = os.path.join(root, "rollout-root-1.jsonl")
            child_path = os.path.join(root, "rollout-child-1.jsonl")
            command = "Get-Content -LiteralPath %s -Raw" % json.dumps(source)
            js = "const r = await tools.shell_command({command:%s,workdir:%s}); text(r);" % (
                json.dumps(command), json.dumps(project)
            )
            # A real Codex stage boundary is a read of the converted skill.
            js = js.replace("const r =", "// .agents/skills/a2h-spec/SKILL.md\nconst r =")
            root_records = [
                rec("2026-01-01T00:00:00Z", "session_meta", {
                    "id": root_id, "session_id": root_id, "cwd": project,
                    "cli_version": "0.test", "source": "cli",
                }),
                rec("2026-01-01T00:00:01Z", "event_msg", {
                    "type": "task_started", "turn_id": "turn-1",
                }),
                rec("2026-01-01T00:00:01Z", "turn_context", {
                    "model": "gpt-test", "turn_id": "turn-1",
                }),
                rec("2026-01-01T00:00:02Z", "event_msg", {
                    "type": "user_message", "message": "migrate demo",
                }),
                rec("2026-01-01T00:00:03Z", "response_item", {
                    "type": "custom_tool_call", "name": "exec", "call_id": "call-read",
                    "input": js,
                }),
                rec("2026-01-01T00:00:04Z", "response_item", {
                    "type": "custom_tool_call_output", "call_id": "call-read",
                    "output": [{"type": "input_text", "text": java_text}],
                }),
                rec("2026-01-01T00:00:05Z", "response_item", {
                    "type": "function_call", "name": "spawn_agent", "call_id": "call-agent",
                    "arguments": json.dumps({"task_name": "worker", "message": "implement F001"}),
                }),
                rec("2026-01-01T00:00:06Z", "response_item", {
                    "type": "function_call_output", "call_id": "call-agent",
                    "output": json.dumps({"task_name": "/root/worker"}),
                }),
                rec("2026-01-01T00:00:07Z", "event_msg", {
                    "type": "token_count", "info": {
                        "total_token_usage": {"input_tokens": 100, "cached_input_tokens": 40,
                                              "output_tokens": 20, "reasoning_output_tokens": 5},
                        "last_token_usage": {"input_tokens": 100, "cached_input_tokens": 40,
                                             "output_tokens": 20, "reasoning_output_tokens": 5},
                    },
                }),
                rec("2026-01-01T00:00:08Z", "event_msg", {
                    "type": "task_complete", "turn_id": "turn-1",
                }),
            ]
            patch = "*** Begin Patch\n*** Update File: %s\n@@\n-# Feature\n+# Feature complete\n*** End Patch" % spec
            patch_js = "const patch = %s; text(await tools.apply_patch(patch));" % json.dumps(patch)
            child_records = [
                rec("2026-01-01T00:00:05Z", "session_meta", {
                    "id": child_id, "session_id": root_id, "cwd": project,
                    "cli_version": "0.test", "thread_source": "subagent",
                    "source": {"subagent": {"thread_spawn": {
                        "parent_thread_id": root_id, "depth": 1,
                        "agent_path": "/root/worker", "agent_nickname": "Ada",
                    }}},
                }),
                # Codex forks replay the parent's session metadata and token
                # counters before the child activation marker.  Those tokens
                # are inherited context, not work produced by this child.
                rec("2026-01-01T00:00:05Z", "session_meta", {
                    "id": root_id, "session_id": root_id, "cwd": project,
                    "cli_version": "0.test", "source": "cli",
                }),
                rec("2026-01-01T00:00:05Z", "event_msg", {
                    "type": "token_count", "info": {
                        "total_token_usage": {"input_tokens": 100, "cached_input_tokens": 40,
                                              "output_tokens": 20, "reasoning_output_tokens": 5},
                        "last_token_usage": {"input_tokens": 100, "cached_input_tokens": 40,
                                             "output_tokens": 20, "reasoning_output_tokens": 5},
                    },
                }),
                rec("2026-01-01T00:00:05Z", "response_item", {
                    "type": "message", "role": "developer",
                    "content": [{"type": "input_text",
                                 "text": "You are an agent in a team of agents collaborating to complete a task."}],
                }),
                rec("2026-01-01T00:00:06Z", "turn_context", {"model": "gpt-test"}),
                rec("2026-01-01T00:00:06Z", "event_msg", {
                    "type": "user_message", "message": "implement F001",
                }),
                rec("2026-01-01T00:00:07Z", "response_item", {
                    "type": "custom_tool_call", "name": "exec", "call_id": "call-patch",
                    "input": patch_js,
                }),
                rec("2026-01-01T00:00:08Z", "response_item", {
                    "type": "custom_tool_call_output", "call_id": "call-patch",
                    "output": "Done!",
                }),
                rec("2026-01-01T00:00:09Z", "event_msg", {
                    "type": "token_count", "info": {
                        "total_token_usage": {"input_tokens": 180, "cached_input_tokens": 60,
                                              "output_tokens": 50, "reasoning_output_tokens": 15},
                        "last_token_usage": {"input_tokens": 80, "cached_input_tokens": 20,
                                             "output_tokens": 30, "reasoning_output_tokens": 10},
                    },
                }),
                rec("2026-01-01T00:00:10Z", "event_msg", {"type": "task_complete"}),
            ]
            write_jsonl(main_path, root_records)
            write_jsonl(child_path, child_records)

            trace = extract_codex_session.extract(main_path, sessions_root=root)
            self.assertEqual("codex", trace["meta"]["session_format"])
            self.assertEqual(root_id, trace["meta"]["session_id"])
            self.assertEqual("gpt-test", trace["meta"]["model"])
            self.assertEqual(1, trace["totals"]["subagent_transcripts"])
            self.assertEqual(20, trace["totals"]["main_output_tokens"])
            self.assertEqual(30, trace["totals"]["subagent_output_tokens"])
            self.assertIn("a2h-spec", [stage["stage"] for stage in trace["stages"]])
            self.assertEqual("a2h-spec", trace["agents"][0]["stage"])
            self.assertEqual("completed", trace["agents"][0]["status"])
            self.assertTrue(any(tool["name"] == "PowerShell" for tool in trace["tools"]))
            self.assertTrue(any(item["path"].endswith("Demo.java")
                                for item in trace["lineage"]["android"]))
            self.assertTrue(any(item["path"].endswith("F001.md")
                                for item in trace["lineage"]["specs"]))
            self.assertEqual("codex", migloop.session_format(main_path))


if __name__ == "__main__":
    unittest.main()
