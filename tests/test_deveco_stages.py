"""DevEco 的 /<skill> 命令把整篇 SKILL.md 展开成 user 消息,没有 skill 工具调用;
第一个一级标题就是技能名,命中管线技能就该开阶段(2026-09-09 wugang 的 a2h-spec 会话只切出 Setup → Plan)。"""
from __future__ import annotations

import tempfile
import unittest

from migloop.adapters import deveco

SPEC_BODY = (
    "> **DevEco Code 0.1.1 派发约定。** 具名子代理由主 Agent 调用 `task` 工具。\n\n"
    "# a2h-spec — 阶段 A 前段：理解与契约草案\n\n## 0. 定位与纪律\n正文……\n"
)
VERIFY_BODY = (
    "> **路径约定**：下文 `$SKILLS_ROOT` = 本套 skills 的安装根目录。\n\n"
    "# arkts-visual-verify — 按页面截图对比 + 产出 fix-markdown\n\n## 1. 前置\n"
)
REGISTRY_BODY = "## 编排定位\n\nA2H 测试工具是第三方。\n\n# §M 合账段 — 把功能维度注入 fact-tree\n\n# a2h-spec 只是被提到\n"


def _msg(idx, role, parts, created):
    return {"info": {"id": "msg_%d" % idx, "role": role, "sessionID": "ses_x",
                     "time": {"created": created, "completed": created + 500}},
            "parts": parts}


def _text(t):
    return {"type": "text", "text": t}


def _bash():
    return {"type": "tool", "tool": "bash", "callID": "c-bash",
            "state": {"status": "completed", "input": {"command": "echo hi"}, "output": "hi"}}


def _skill(name):
    return {"type": "tool", "tool": "skill", "callID": "c-" + name,
            "state": {"status": "completed", "input": {"name": name}, "output": "loaded"}}


def _export(messages):
    return {"info": {"id": "ses_x", "directory": "D:/proj", "version": "0.1.0",
                     "model": {"id": "glm-5.3-flash", "providerID": "zhipuai"},
                     "time": {"created": 1000, "updated": 99000}},
            "messages": messages}


def _parse(data):
    # storage_root 指向空目录:没有 deveco.db,子代理走无 DB 兜底,测试只看主线阶段。
    with tempfile.TemporaryDirectory() as empty:
        return deveco._parse(data, storage_root=empty)


class DevEcoPromptSkillStagesTest(unittest.TestCase):
    def test_prompt_skill_only_first_h1_and_only_pipeline_names(self):
        self.assertEqual(deveco._prompt_skill(SPEC_BODY), "a2h-spec")
        self.assertEqual(deveco._prompt_skill(VERIFY_BODY), "arkts-visual-verify")
        self.assertIsNone(deveco._prompt_skill(REGISTRY_BODY))   # 第一个一级标题是 §M,后面提到的不算
        self.assertIsNone(deveco._prompt_skill("开始执行"))
        self.assertIsNone(deveco._prompt_skill("# 说明\n# a2h-spec\n"))
        self.assertIsNone(deveco._prompt_skill(""))

    def test_skill_body_prompts_open_pipeline_stages(self):
        trace = _parse(_export([
            _msg(0, "user", [_text(SPEC_BODY)], 1000),
            _msg(1, "assistant", [_bash()], 2000),
            _msg(2, "user", [_text("开始执行")], 3000),                 # 普通消息不开阶段
            _msg(3, "assistant", [_skill("a2h-plan")], 4000),          # skill 工具照旧
            _msg(4, "user", [_text(REGISTRY_BODY)], 5000),             # 非管线技能正文不开阶段
            _msg(5, "assistant", [_bash()], 6000),
            _msg(6, "user", [_text(VERIFY_BODY)], 7000),
            _msg(7, "assistant", [_bash()], 8000),
        ]))
        stages = trace["stages"]
        self.assertEqual([s["stage"] for s in stages], ["a2h-spec", "a2h-plan", "arkts-visual-verify"])
        self.assertEqual([s["start_idx"] for s in stages], [0, 3, 6])
        self.assertEqual([s["label"] for s in stages], ["Spec", "Plan", "Visual Verify"])
        self.assertEqual([p["stage"] for p in trace["prompts"]],
                         ["a2h-spec", "a2h-spec", "a2h-plan", "arkts-visual-verify"])

    def test_same_skill_via_prompt_then_tool_is_one_stage(self):
        trace = _parse(_export([
            _msg(0, "user", [_text("先聊两句")], 1000),
            _msg(1, "assistant", [_bash()], 2000),
            _msg(2, "user", [_text(SPEC_BODY)], 3000),
            _msg(3, "assistant", [_skill("a2h-spec")], 4000),          # 同名连续不重复开
            _msg(4, "assistant", [_bash()], 5000),
        ]))
        self.assertEqual([(s["stage"], s["start_idx"]) for s in trace["stages"]],
                         [("setup", 0), ("a2h-spec", 2)])


if __name__ == "__main__":
    unittest.main()
