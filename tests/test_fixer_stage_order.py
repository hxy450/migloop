"""修复方判定 = 规范阶段序 > execute。

正式口径(用户 2026-08-25 定):五阶段 spec→plan→execute→verify→retrospect,
**a2h-execute 结束就是修复开始的标志,之后所有的都是修复**。判据用规范阶段
序而非时间戳 —— 纯修复轮会话里根本没有 execute 阶段,时间戳无从比较。
"""

from __future__ import annotations

import pytest

from migloop.audit import agent_is_fixer


@pytest.mark.parametrize("stage", ["a2h-spec", "a2h-plan", "a2h-execute",
                                   "mig-arch", "a2h-arch-scaffold", "setup"])
def test_execute_and_earlier_are_generators(stage):
    assert agent_is_fixer({"stage": stage}) is False


@pytest.mark.parametrize("stage", ["a2h-verify", "arkts-visual-verify",
                                   "a2h-retrospect"])
def test_after_execute_is_fixer(stage):
    assert agent_is_fixer({"stage": stage}) is True


def test_group_closer_inside_execute_is_generator():
    """execute 内部的收尾(group closer 修 build error)属于生成侧 ——
    把一组产出收尾到可编译是"生成完成"的一部分,不是返修。
    它作为行级原作者的身份由 blame 保留,信息不丢。"""
    a = {"stage": "a2h-execute", "type": "group1-closer", "desc": "Group 1 closer 收尾"}
    assert agent_is_fixer(a) is False


def test_fixer_type_no_longer_overrides_stage():
    """类型含 fixer/visual 不再单独成立 —— 口径只认阶段。
    (真实数据:8 次命中全部同时满足阶段,该分支从未单独生效)"""
    assert agent_is_fixer({"stage": "a2h-execute", "type": "visual-fixer"}) is False
    assert agent_is_fixer({"stage": "arkts-visual-verify", "type": "worker"}) is True


def test_unknown_stage_is_generator_not_fixer():
    """阶段切不出来时保守归生成侧 —— 宁可少判一条链,不可凭空造修复关系。"""
    assert agent_is_fixer({"stage": None}) is False
    assert agent_is_fixer({"stage": "", "type": "worker"}) is False
    assert agent_is_fixer({"stage": "some-custom-skill"}) is False


def test_workflow_phase_names_map_to_verify():
    """dynamic workflow 的阶段名带 verify/fix 词根的,归修复侧。"""
    assert agent_is_fixer({"stage": "visual-verify-round-2"}) is True
    assert agent_is_fixer({"stage": "fix-build-errors"}) is True
