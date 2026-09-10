"""Independent source-contract/consumer review; synthetic evidence only."""
from __future__ import annotations

import json
import os
from contextlib import nullcontext
from pathlib import Path

import pytest

from migloop import atoms, atoms_collect, cc_sources, investigation, raw_events, temporal, time_receipts, transcript_store as store
from tests.test_cc_source_discovery import SID, dump


AT = "2026-01-01T00:00:00Z"


def pool(base: Path) -> tuple[atoms.Ledger, str, Path]:
    root = dump(base / f"{SID}.jsonl", [{"type": "user", "timestamp": AT,
                "message": {"role": "user", "content": "synthetic root request"}}])
    journal = Path(dump(base / SID / "subagents/workflows/wf-one/journal.jsonl", [{
        "type": "result", "key": "task", "agentId": "__main__:11111111",
        "timestamp": "2099-01-01T00:00:00Z", "result": "synthetic attachment field",
    }]))
    discovered = cc_sources.discover([root])
    agents = atoms_collect.collect_cc_pool([root], [0], sources=discovered)
    ledger = atoms.build_ledger(agents, auxiliary_sources=discovered.auxiliary_sources,
                               source_metadata=discovered.source_metadata)
    return ledger, root, journal


def qualified(ledger: atoms.Ledger, path: Path) -> str:
    return store.read_record(str(path), 1, source=store.source_spec(ledger, str(path))).ref


def test_arbitrary_pool_directory_named_subagents_never_changes_explicit_identity(tmp_path: Path) -> None:
    first, _, journal = pool(tmp_path / "original")
    second, _, moved = pool(tmp_path / "unrelated-parent/subagents/frozen")
    assert qualified(first, journal) == qualified(second, moved)
    assert atoms.ledger_identity(first) == atoms.ledger_identity(second)
    # Standalone legacy access does not guess any namespace from directories.
    assert len(store.read_record(str(moved), 1).ref.split(":")[1]) == 20


def test_latest_does_not_borrow_auxiliary_jsonl_timestamp(tmp_path: Path) -> None:
    ledger, _, journal = pool(tmp_path)
    assert store.resolve(ledger, qualified(ledger, journal)).ts is None
    current = investigation.scope(ledger, at="latest")
    assert current["at"] == "2026-01-01T00:00:00.000000Z"


@pytest.mark.parametrize("legacy", [True, False])
def test_raw_record_scalar_and_batch_receipts_preserve_the_supplied_address(tmp_path: Path, legacy: bool) -> None:
    ledger, _, journal = pool(tmp_path)
    ref = store.read_record(str(journal), 1).ref if legacy else qualified(ledger, journal)
    args = {"ref": ref, "at": AT, "include_undated": True}
    data = investigation.query(ledger, "record", args)
    assert data["ref"] == ref and data["ts"] is None
    assert data["text"] == journal.read_text(encoding="utf-8").rstrip("\n")
    scalar = time_receipts.append(ledger, "record", args, temporal.render(data), data)
    receipt = time_receipts.parse(ledger, "record", args, scalar)
    assert receipt and receipt["records"] == [ref]
    requests = [{"tool": "record", "args": args}]
    batch = investigation.render_batch(ledger, requests, max_chars=16000)
    parsed = investigation.parse_receipt("batch", {"requests": requests, "max_chars": 16000}, batch)
    assert parsed is not None and parsed["data"]["items"][0]["data"]["ref"] == ref


@pytest.mark.parametrize("legacy", [True, False])
def test_field_expansion_preserves_address_unknown_time_and_original_field(tmp_path: Path, legacy: bool) -> None:
    ledger, _, journal = pool(tmp_path)
    ref = store.read_record(str(journal), 1).ref if legacy else qualified(ledger, journal)
    args = {"refs": [{"ref": ref, "pointer": "/result"}], "at": AT, "include_undated": True}
    result = investigation.query(ledger, "expand", args)
    item, = result["items"]
    assert item["status"] == "ok"
    record, = item["records"]
    assert record["ref"] == ref and record["text"] == "synthetic attachment field"
    assert record["ts"] is None
    assert ledger.stories == {} and len(ledger.agents) == 1


@pytest.mark.parametrize("legacy", [True, False])
def test_changed_content_rejected_by_real_record_consumer_for_both_ref_versions(tmp_path: Path, legacy: bool) -> None:
    ledger, _, journal = pool(tmp_path)
    ref = store.read_record(str(journal), 1).ref if legacy else qualified(ledger, journal)
    journal.write_text('{"type":"result","key":"task","result":"changed"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="content changed"):
        investigation.query(ledger, "record", {"ref": ref, "at": AT, "include_undated": True})


def test_metadata_is_copied_before_identity_freeze_and_policy_is_in_identity(tmp_path: Path) -> None:
    ledger, root, journal = pool(tmp_path)
    supplied = {path: dict(spec) for path, spec in ledger.source_metadata.items()}
    clone = atoms.build_ledger(ledger.agents, auxiliary_sources=ledger.auxiliary_sources, source_metadata=supplied)
    before = atoms.ledger_identity(clone)
    supplied[os.path.normcase(root)]["timestamp_policy"] = "unknown"
    assert clone.source_metadata[os.path.normcase(root)]["timestamp_policy"] == "record"
    assert atoms.ledger_identity(clone) == before
    changed = atoms.build_ledger(ledger.agents, auxiliary_sources=ledger.auxiliary_sources, source_metadata=supplied)
    assert atoms.ledger_identity(changed) != before


def lookalikes() -> list[dict]:
    return [
        {"timestamp": AT, "message": {"role": "assistant", "content": [{
            "type": "tool_use", "id": "quote-only", "name": "Write",
            "input": {"file_path": "/project/NotExecuted.ets", "content": "quoted example"},
        }]}},
        {"timestamp": "2026-01-01T00:00:01Z", "message": {"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": "quote-only", "is_error": False, "content": "successfully written",
        }]}},
        {"timestamp": "2026-01-01T00:00:02Z", "type": "event_msg", "payload": {
            "type": "patch_apply_end", "call_id": "quoted-patch", "success": True,
            "changes": {"/project/NotExecuted.ets": {"type": "update", "unified_diff": "-old\n+quoted"}},
        }},
    ]


def test_attachment_native_lookalikes_are_only_unowned_unknown_time_raw_material(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    attachment = Path(dump(tmp_path / SID / "tool-results/quoted-examples.txt", lookalikes()))
    discovered = cc_sources.discover([root])
    agents = atoms_collect.collect_cc_pool([root], [0], sources=discovered)
    ledger = atoms.build_ledger(agents, auxiliary_sources=discovered.auxiliary_sources,
                               source_metadata=discovered.source_metadata)
    inventory = raw_events.inventory(ledger)
    assert inventory["events"] == []
    rows = [row for row in inventory["unknown_records"] if row["source"] == attachment.name]
    assert len(rows) == 3 and all(row["agents"] == [] and row["ts"] is None for row in rows)
    assert ledger.stories == {} and all(not a.actions for a in ledger.agents.values())
    search = investigation.query(ledger, "search", {"q": "NotExecuted.ets", "at": AT, "include_undated": True})
    assert search["rows"] == []
    assert len(search["undated"]["rows"]) == 2
    assert all(not row["agents"] and not row["annotations"] for row in search["undated"]["rows"])


@pytest.mark.parametrize("request_scope", [False, True])
def test_native_cache_is_bound_to_explicit_time_policy_and_logical_name(tmp_path: Path, request_scope: bool) -> None:
    path = dump(tmp_path / "cache-source.jsonl", lookalikes())
    key = os.path.normcase(path)
    # Positive-control raw protocol source. Changing only its explicit contract
    # must invalidate cached interpretation even with identical owner/stat/bytes.
    agents = {"synthetic-owner": atoms.AgentRec("synthetic-owner", "session", sources=[path])}

    def ledger(policy: str, logical: str) -> atoms.Ledger:
        return atoms.build_ledger(agents, source_metadata={key: {"logical_name": logical, "timestamp_policy": policy}})

    recorded, unknown, renamed = ledger("record", "native-one.jsonl"), ledger("unknown", "native-one.jsonl"), ledger("record", "native-two.jsonl")
    with raw_events.scan_scope() if request_scope else nullcontext():
        first = raw_events.inventory(recorded)
        hidden = raw_events.inventory(unknown)
        new_name = raw_events.inventory(renamed)
    assert len(first["events"]) == len(new_name["events"]) == 2
    assert hidden["events"] == [] and all(row["ts"] is None for row in hidden["unknown_records"])
    assert {event["id"] for event in first["events"]}.isdisjoint(event["id"] for event in new_name["events"])


def test_latest_cache_is_bound_to_time_policy_not_only_file_stats(tmp_path: Path) -> None:
    path = dump(tmp_path / "dated.jsonl", [{"timestamp": AT, "type": "opaque"}])
    agents = {"synthetic-owner": atoms.AgentRec("synthetic-owner", "session", sources=[path])}
    known = atoms.build_ledger(agents, source_metadata={os.path.normcase(path): {
        "logical_name": "dated.jsonl", "timestamp_policy": "record"}})
    unknown = atoms.build_ledger(agents, source_metadata={os.path.normcase(path): {
        "logical_name": "dated.jsonl", "timestamp_policy": "unknown"}})
    assert investigation.scope(known, at="latest")["at"] == "2026-01-01T00:00:00.000000Z"
    assert investigation.scope(unknown, at="latest")["at"] == "latest"


def test_legacy_action_navigation_expands_qualified_request_and_return_refs(tmp_path: Path) -> None:
    root = dump(tmp_path / f"{SID}.jsonl")
    dump(tmp_path / SID / "subagents/workflows/wf-one/agent-child.jsonl", lookalikes()[:2])
    discovered = cc_sources.discover([root])
    agents = atoms_collect.collect_cc_pool([root], [0], sources=discovered)
    ledger = atoms.build_ledger(agents, auxiliary_sources=discovered.auxiliary_sources,
                               source_metadata=discovered.source_metadata)
    action, = ledger.agents["agent-child"].actions
    ref = f"#{action.seq}@L{action.src[1] + 1}·{atoms.transcript_tag(action.src[0])}"
    expanded = investigation.query(ledger, "expand", {"refs": [ref], "at": "2026-01-01T00:00:10Z"})
    item, = expanded["items"]
    assert item["status"] == "ok" and item["withheld"] == []
    assert [record["line"] for record in item["records"]] == [1, 2]
    assert all(len(record["ref"].split(":")[1]) == 40 for record in item["records"])
    assert all(store.resolve(ledger, record["ref"]).raw == record["text"] for record in item["records"])
