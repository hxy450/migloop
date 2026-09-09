"""A report-only path has no file version; an existing agent can be an honest anchor."""
from __future__ import annotations

import json

import pytest

from migloop import atoms, probe, verdict
from tests.test_codex_message_evidence import TARGET, build, message
from tests.test_trajectory import _run_dir


@pytest.mark.parametrize("opened", [False, True])
def test_report_only_file_uses_real_agent_root_without_inventing_file_version(tmp_path, opened):
    led, owner = build(tmp_path, [message(3, "review", f"claim about {TARGET}", sender="/root/reviewer")])
    assert not led.stories[TARGET].versions
    agent_spec = f"agent:{owner.id}@v1"
    report = "```json\n" + json.dumps({"schema": "migloop-verdict/1", "ledger": atoms.ledger_identity(led),
                                       "root": agent_spec, "defects": []}) + "\n```"
    calls = [("agent", {"id": owner.id, "v": 1, "via": "sessions"}, f"# {owner.id} v1")] if opened else []
    payload = probe.probe_payload(led, _run_dir(tmp_path, calls, report))
    assert payload["structured"]["root"]["ok"]
    assert not verdict.resolve_node(led, f"file:{TARGET}@v0")["ok"]
    tree = payload["trajectory"]
    assert tree is not None and tree["root"] == f"agent:{owner.id}@1"
    root = next(n for n in tree["nodes"] if n["id"] == tree["root"])
    assert root["opened"] == ([1] if opened else [])
    if not opened:
        assert root["source"] == "结论" and not tree["visits"]
    assert not any(n["kind"] == "file" and n["key"] == TARGET for n in tree["nodes"])


def test_zero_version_chain_target_does_not_create_a_fake_file_root(tmp_path):
    led, owner = build(tmp_path, [message(3, "review", f"claim about {TARGET}", sender="/root/reviewer")])
    calls = [("sessions", {"file": TARGET}, "账本身份: " + atoms.ledger_identity(led) + "\n# chains")]
    payload = probe.probe_payload(led, _run_dir(tmp_path, calls, ""))
    assert payload["root"] == TARGET  # target path is allowed, a file-version node is not
    tree = payload["trajectory"]
    assert tree is None or not tree["nodes"]
