"""Offline guards for paired same-history experiments, no model calls."""

import importlib.util
from pathlib import Path

import pytest

DRIVER = Path(__file__).parents[1] / "docs/experiments/inquiry-20260911/run_paired_review.py"
spec = importlib.util.spec_from_file_location("paired_review_test", DRIVER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_fork_keeps_options_and_never_selects_last_session():
    command = ["codex", "-a", "never", "exec", "--json", "--sandbox", "read-only", "-C", "cwd", "-"]
    identity = "11111111-1111-4111-8111-111111111111"
    assert runner.fork_command(command, identity) == command[:-1] + ["fork", identity, "-"]
    assert command[-1] == "-"
    for bad in ("--last", "thread-name", ""):
        with pytest.raises(ValueError):
            runner.fork_command(command, bad)
    with pytest.raises(ValueError):
        runner.fork_command(command[:-1] + ["resume", identity, "-"], identity)


def count(total, last=None):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": total, "last_token_usage": last}}}


@pytest.mark.parametrize("inherited", [True, False])
def test_usage_proves_reset_or_inheritance_without_double_count(inherited):
    base = {"input_tokens": 1000, "cached_input_tokens": 900, "output_tokens": 20}
    delta = {"input_tokens": 250, "cached_input_tokens": 200, "output_tokens": 5}
    total = {k: v + (base[k] if inherited else 0) for k, v in delta.items()}
    parent = [count(base)]
    prompt = {"type": "response_item", "payload": {"role": "user", "content": [{"text": "review"}]}}
    result = runner.review_usage(parent, parent + [prompt, count(total, delta)], "review")
    assert result["counter_mode"] == ("inherited" if inherited else "reset")
    assert result["incremental_total"] == 255
    assert result["incremental_uncached_input"] == 50


def test_usage_unknown_counter_semantics_cannot_publish_cost():
    base = {"input_tokens": 1000, "cached_input_tokens": 900, "output_tokens": 20}
    prompt = {"type": "response_item", "payload": {"role": "user", "content": [{"text": "review"}]}}
    with pytest.raises(ValueError, match="semantics"):
        runner.review_usage([count(base)], [prompt, count({"input_tokens": 1400}, {"input_tokens": 2})], "review")


def test_common_skill_has_no_case_names_or_expected_answers():
    root = DRIVER.parent / "review-skill"
    for path in root.iterdir():
        text = path.read_text(encoding="utf-8")
        for forbidden in ("GuidePage", "CustomDialog", "windowBottomPadding", "F10-06", "F10-09"):
            assert forbidden not in text
    text = (root / "SKILL.md").read_text(encoding="utf-8")
    assert "Get-Content -Encoding utf8" in text
    assert "不重写整份原稿" in text and "不调用 submit" in text
