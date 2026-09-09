"""Canonical Codex messages are located evidence, not inferred sender executions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from migloop import atoms, atoms_collect, atoms_text
from tests.test_atoms import CROOT, _cexec, _crec, _write_jsonl

TARGET = "/proj/viewmodels/PptGenerationViewModel.ets"


def at(second: int) -> str:
    return f"2026-01-01T00:00:{second:02d}Z"


def message(second: int, pid: str, text: str, *, role: str = "user", sender: str | None = None,
            shape: str = "list", record_type: str = "response_item") -> dict:
    content = {"type": "output_text" if role == "assistant" else "input_text", "text": text}
    content = [content] if shape == "list" else text if shape == "string" else content
    payload = {"type": "agent_message" if sender else "message", "id": pid, "content": content}
    payload.update({"author": sender, "recipient": "/root"} if sender else {"role": role})
    return _crec(at(second), record_type, payload)


def build(tmp_path: Path, rows: list[dict]) -> tuple[atoms.Ledger, atoms.AgentRec]:
    command = "cat > /proj/viewmodels/Existing.ets <<'EOF'\nknown\nEOF"
    js = "text(await tools.exec_command(" + json.dumps({"cmd": command, "workdir": "/proj"}) + "));"
    records = [_crec(at(0), "session_meta", {"id": CROOT, "cwd": "/proj", "source": "cli"}),
               *_cexec(at(0), "initial", js, ""), *rows]
    tail = _cexec(at(40), "tail", js, "")
    tail[1]["timestamp"] = at(41)
    records += tail
    root = tmp_path / f"rollout-{CROOT}.jsonl"
    _write_jsonl(str(root), records)
    ledger = atoms.build_ledger(atoms_collect.collect_codex(str(root), seq=[0], sessions_root=str(tmp_path)))
    assert len(ledger.agents) == 1  # sender 标签不能制造缺失的子转录
    return ledger, next(iter(ledger.agents.values()))


@pytest.mark.parametrize("shape", ["list", "dict", "string"])
def test_agent_message_has_original_id_search_action_and_mention_navigation(tmp_path: Path, shape: str) -> None:
    text = f"Message Type: FINAL_ANSWER\nwrong_edit in {TARGET}; reviewer claim, not proven execution"
    led, owner = build(tmp_path, [message(3, "amsg_review", text, sender="/root/absent_reviewer", shape=shape)])
    found = [a for a in owner.actions if a.detail.get("source_event_id") == "amsg_review"]
    assert len(found) == 1
    action = found[0]
    assert action.tool == action.kind == "inbox" and action.tuid is None
    assert action.src is not None and action.src[1] == action.src[2] == 3
    assert action.detail["from"] == "/root/absent_reviewer" and action.detail["recipient"] == "/root"
    assert action.detail["source_event_type"] == "agent_message" and "未独立核验" in action.detail["claim_note"]
    assert action.files == [] and action.ver is None
    assert atoms.event_id(led, owner.id, action.seq).endswith(":amsg_review")
    result = atoms.search_agent(led, owner.id, "wrong_edit")
    assert result and len(result["hits"]) == 1
    hit = result["hits"][0]
    assert hit["seq"] == action.seq and hit["kind"] == "inbox" and hit["field"] == "text"
    raw = atoms.action_raw(led, owner.id, action.seq)
    assert raw is not None and raw["input"] == text and raw["output"] == ""
    assert raw["source_event_id"] == "amsg_review" and raw["sender"] == "/root/absent_reviewer"
    rendered = atoms_text.render_action(led, owner.id, action.seq, part="input", m_n=0)
    assert "wrong_edit" in rendered and "发送者消息主张,未独立核验" in rendered and "/root/absent_reviewer" in rendered
    assert TARGET in led.stories and not led.stories[TARGET].versions
    assert any(m.seq == action.seq and m.where == "text" for m in led.mentions[TARGET])
    assert not led.stories[TARGET].reads and not led.stories[TARGET].touches


def test_canonical_user_and_assistant_messages_keep_source_and_old_prompt_result(tmp_path: Path) -> None:
    user = f"user evidence {TARGET}"
    assistant = f"assistant conclusion {TARGET}"
    led, owner = build(tmp_path, [message(2, "msg_user", user), message(5, "msg_assistant", assistant, role="assistant")])
    by_id = {a.detail.get("source_event_id"): a for a in owner.actions}
    assert by_id["msg_user"].kind == "inbox" and by_id["msg_assistant"].kind == "say"
    assert owner.result == assistant and owner.prompt is None
    for pid, text in (("msg_user", user), ("msg_assistant", assistant)):
        action = by_id[pid]
        assert action.src is not None and action.tuid is None and action.files == []
        assert atoms.action_raw(led, owner.id, action.seq)["input"] == text
        assert any(h["seq"] == action.seq for h in atoms.search_agent(led, owner.id, text.split()[0])["hits"])
    # 子转录的首条 user 仍是 prompt,最后 assistant 仍是 result。
    child = atoms_collect._walk_codex(owner.actions[0].src[0], "agent-child", "child", [0], {}, set())
    assert child.prompt == user and child.result == assistant


def test_event_msg_mirrors_and_replayed_message_ids_do_not_duplicate_evidence(tmp_path: Path) -> None:
    sender = "/root/reviewer"
    led, owner = build(tmp_path, [
        message(2, "amsg_same", "mirror should not become truth", sender=sender, record_type="event_msg"),
        message(3, "amsg_same", "canonical wrong_edit", sender=sender),
        message(4, "amsg_same", "replayed canonical must not replace first", sender=sender),
        message(5, "mirror_only", "event only never canonical", sender=sender, record_type="event_msg"),
        message(6, "user_mirror", "user mirror", record_type="event_msg"),
        message(7, "say_mirror", "assistant mirror", role="assistant", record_type="event_msg")])
    actions = [a for a in owner.actions if a.kind in ("inbox", "say")]
    assert len(actions) == 1 and actions[0].detail["text"] == "canonical wrong_edit"
    assert not atoms.search_agent(led, owner.id, "mirror")["hits"]
    assert owner.result is None


def test_forked_canonical_message_ids_are_not_assigned_to_child_again(tmp_path: Path) -> None:
    led, owner = build(tmp_path, [message(2, "amsg_parent", "wrong_edit parent record", sender="/root/reviewer")])
    source = owner.actions[0].src[0]
    seen: set[str] = set()
    atoms_collect._walk_codex(source, "__main__:root", CROOT, [0], {}, seen)
    child = atoms_collect._walk_codex(source, "agent-child", "child", [0], {}, seen)
    assert not [a for a in child.actions if a.detail.get("source_event_id") == "amsg_parent"]


@pytest.mark.parametrize("role", ["developer", "system"])
def test_explicit_system_inputs_are_located_and_searchable_without_becoming_effects(tmp_path: Path, role: str) -> None:
    text = f"explicit constraint_{role} for {TARGET}"
    led, owner = build(tmp_path, [message(3, "msg_" + role, text, role=role)])
    action = next(a for a in owner.actions if a.detail.get("source_event_id") == "msg_" + role)
    assert action.kind == action.tool == "system" and action.tuid is None and action.ver is None and not action.files
    assert action.detail["from"] == role and action.src is not None
    assert owner.prompt is None and owner.result is None
    assert atoms.action_raw(led, owner.id, action.seq)["input"] == text
    assert any(h["seq"] == action.seq for h in atoms.search_agent(led, owner.id, "constraint_" + role)["hits"])
    assert TARGET in led.mentions and not led.stories[TARGET].versions


def test_only_explicit_session_base_instruction_text_is_added(tmp_path: Path) -> None:
    text = "base_only_constraint " + TARGET
    meta = _crec(at(2), "session_meta", {"id": CROOT, "cwd": "/proj", "base_instructions": {"text": text}})
    led, owner = build(tmp_path, [meta, meta,
        _crec(at(4), "session_meta", {"id": "schema_only", "tools": [{"description": "not instruction"}],
                                    "base_instructions": {"tools": [{"text": "not instruction"}]}}),
        _crec(at(5), "event_msg", {"id": "mirror", "base_instructions": {"text": "not instruction"}})])
    systems = [a for a in owner.actions if a.kind == "system"]
    assert len(systems) == 1
    action = systems[0]
    assert action.src[1] == action.src[2] == 3 and action.tuid is None and not action.files
    assert action.detail["source_event_type"] == "base_instructions" and action.detail["source_event_id"] == CROOT
    assert atoms.action_raw(led, owner.id, action.seq)["input"] == text
    hits = atoms.search_agent(led, owner.id, "base_only_constraint")["hits"]
    assert len(hits) == 1 and hits[0]["kind"] == "system" and hits[0]["seq"] == action.seq
    assert not atoms.search_agent(led, owner.id, "not instruction")["hits"]
