"""Offline contract tests, never call a model or modify existing runs."""
import importlib.util
from pathlib import Path

import pytest


def module():
    path = Path(__file__).resolve().parents[1] / 'docs/experiments/longchain-20260911/hybrid.py'
    spec = importlib.util.spec_from_file_location('optional_mcp_trial', path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_hybrid_changes_only_mcp_not_raw_access_or_reasoning():
    raw = {'features.shell_tool': True, 'model_reasoning_effort': 'medium', 'mcp_servers': {}}
    tools = {**raw, 'features.shell_tool': False, 'mcp_servers': {'migloop': {'required': True}}}
    hybrid = module().hybrid_settings(raw, tools)
    assert hybrid == {**raw, 'mcp_servers': tools['mcp_servers']}
    hybrid['mcp_servers']['migloop']['required'] = False
    assert tools['mcp_servers']['migloop']['required'] is True


def test_hybrid_rejects_hidden_condition_changes():
    raw = {'features.shell_tool': True, 'model_reasoning_effort': 'medium', 'mcp_servers': {}}
    with pytest.raises(ValueError):
        module().hybrid_settings(raw, {**raw, 'features.shell_tool': False, 'model_reasoning_effort': 'high'})


def test_task_prefix_and_free_report_are_preserved():
    raw = 'An existing task\r\nWith original output form\r\n'
    prompt = module().hybrid_prompt(raw, 'frozen-root.jsonl')
    assert prompt.startswith(raw)
    assert '不需要 YAML、check 或 via' in prompt
    assert '不是必须走 MCP' in prompt
    assert 'Slice8' not in prompt and '价格' not in prompt
