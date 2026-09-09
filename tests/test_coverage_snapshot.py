"""A changed candidate policy must not silently change an old run's denominator."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

import pytest

from migloop import atoms, coverage, coverage_snapshot
from tests.test_repair_coverage import PATH, candidate_action, declaration, splash_ledger


def snapshots() -> tuple[atoms.Ledger, dict[str, Any], dict[str, Any]]:
    ledger, chains = splash_ledger()
    action = candidate_action(ledger, 100, tool="think", kind="think")
    current = coverage.manifest(ledger, chains, PATH)
    current.update(policy="execution-candidates/2", candidates=[])
    recorded = deepcopy(current)
    recorded.pop("policy")
    eid = atoms.event_id(ledger, "agent-fix", action.seq)
    assert eid is not None
    recorded["candidates"] = [{"id": "candidate:" + hashlib.sha256((eid + "\0" + PATH).encode()).hexdigest()[:20],
                                "event_id": eid, "file": PATH, "agent": "agent-fix", "seq": action.seq,
                                "event": coverage._action_event(ledger, "agent-fix", action.seq),
                                "source": "mention", "reason": "旧规则登记的纯文本提及",
                                "writer_confirmed": False, "repair_confirmed": False}]
    return ledger, current, recorded


def test_removed_text_candidate_remains_in_recorded_denominator() -> None:
    ledger, current, recorded = snapshots()
    selected, origin = coverage_snapshot.select_manifest(ledger, current, recorded)
    assert selected == recorded and len(selected["candidates"]) == 1 and current["candidates"] == []
    assert origin["source"] == "recorded" and origin["bound"] is True
    assert origin["policy"] == "legacy" and origin["current_policy"] == "execution-candidates/2"
    assert origin["policy_changed"] is True and origin["semantic_checked"] is False
    rows = [declaration(v) for v in (52, 53, 54)]
    reconciled = coverage.reconcile(ledger, selected, rows, [{"id": "A"}], identity_bound=origin["bound"])
    assert reconciled["complete"] is False and reconciled["counts"]["expected_candidates"] == 1
    assert reconciled["missing_candidates"] == [recorded["candidates"][0]["id"]]
    assert selected["candidates"][0]["writer_confirmed"] is False
    assert selected["candidates"][0]["repair_confirmed"] is False


def test_matching_recorded_policy_is_reported_without_change() -> None:
    ledger, current, recorded = snapshots()
    recorded["policy"] = current["policy"]
    _, origin = coverage_snapshot.select_manifest(ledger, current, recorded)
    assert origin["source"] == "recorded" and origin["policy_changed"] is False


def test_unrecorded_uses_current_but_does_not_claim_historical_policy_provenance() -> None:
    ledger, current, _ = snapshots()
    selected, origin = coverage_snapshot.select_manifest(ledger, current, None)
    assert selected == current and selected is not current
    assert origin["source"] == "current" and origin["status"] == "runtime_manifest_unrecorded"
    assert origin["bound"] is True and origin["policy_changed"] is False


@pytest.mark.parametrize(("field", "value"), [
    ("schema", "migloop-repair-manifest/99"), ("ledger", "wrong-ledger"), ("file", "/other/SplashPage.ets"),
    ("items", {}), ("candidates", None), ("items", [None]), ("candidates", [None]),
    ("policy", {}), ("errors", [{"code": "old_error"}]),
])
def test_invalid_recorded_header_or_shape_blocks_fallback_completion(field: str, value: Any) -> None:
    ledger, current, recorded = snapshots()
    recorded[field] = value
    selected, origin = coverage_snapshot.select_manifest(ledger, current, recorded)
    assert origin["source"] == "invalid" and origin["bound"] is False
    assert selected["items"] == current["items"] and selected["candidates"] == current["candidates"]
    assert selected["errors"] and origin["manifest_errors"]
    # Even an accidentally optimistic caller cannot turn the invalid fallback into complete.
    report = coverage.reconcile(ledger, selected, [declaration(v) for v in (52, 53, 54)], [{"id": "A"}], identity_bound=True)
    assert report["complete"] is False and report["manifest_errors"]


@pytest.mark.parametrize("recorded", [False, [], "not a snapshot", 0])
def test_non_mapping_record_is_invalid_not_absent(recorded: Any) -> None:
    ledger, current, _ = snapshots()
    selected, origin = coverage_snapshot.select_manifest(ledger, current, recorded)
    assert origin["bound"] is False and selected["errors"]


@pytest.mark.parametrize("mutation", ["unknown_version", "boolean_version", "wrong_node", "wrong_before", "duplicate", "event"])
def test_version_coordinates_and_event_identity_are_checked(mutation: str) -> None:
    ledger, current, recorded = snapshots()
    if mutation == "unknown_version":
        recorded["items"][0].update(v=999, node=f"file:{PATH}@v999")
    elif mutation == "boolean_version":
        recorded["items"][0]["v"] = True
    elif mutation == "wrong_node":
        recorded["items"][0]["node"] = "file:/other/SplashPage.ets@v52"
    elif mutation == "wrong_before":
        recorded["items"][0]["before"] = f"file:{PATH}@v54"
    elif mutation == "duplicate":
        recorded["items"].append(deepcopy(recorded["items"][0]))
    else:
        recorded["items"][0]["event"]["id"] = "invented"
    selected, origin = coverage_snapshot.select_manifest(ledger, current, recorded)
    assert origin["bound"] is False and selected["errors"]


@pytest.mark.parametrize("mutation", ["forged_event", "hash", "agent", "seq", "duplicate", "file", "pointer", "shape", "author"])
def test_candidate_hash_must_bind_to_a_real_event_and_the_exact_file(mutation: str) -> None:
    ledger, current, recorded = snapshots()
    item = recorded["candidates"][0]
    if mutation == "forged_event":
        item["event_id"] = "invented:event:id"
        item["id"] = "candidate:" + hashlib.sha256((item["event_id"] + "\0" + PATH).encode()).hexdigest()[:20]
        item["event"]["id"] = item["event_id"]
    elif mutation == "hash":
        item["id"] = "candidate:" + "0" * 20
    elif mutation == "agent":
        item["agent"] = "agent-gen"
    elif mutation == "seq":
        item["seq"] = True
    elif mutation == "duplicate":
        recorded["candidates"].append(deepcopy(item))
    elif mutation == "file":
        item["file"] = "/other/SplashPage.ets"
    elif mutation == "pointer":
        item["event"]["id"] = "invented:pointer"
    elif mutation == "shape":
        item["id"] = ["not-a-string"]
    else:
        item["writer_confirmed"] = True
    _, origin = coverage_snapshot.select_manifest(ledger, current, recorded)
    assert origin["source"] == "invalid" and origin["bound"] is False


@pytest.mark.parametrize("mode", ["recorded", "invalid", "unrecorded"])
def test_selection_does_not_mutate_or_share_nested_input_collections(mode: str) -> None:
    ledger, current, recorded = snapshots()
    if mode == "invalid":
        recorded["ledger"] = "old"
    if mode == "unrecorded":
        recorded = None
    current_before, recorded_before = deepcopy(current), deepcopy(recorded)
    selected, _ = coverage_snapshot.select_manifest(ledger, current, recorded)
    selected["items"][0]["change"]["text"] = "consumer annotation"
    selected["errors"].append({"code": "consumer-error"})
    assert current == current_before and recorded == recorded_before


def test_unrecorded_invalid_current_manifest_does_not_bind() -> None:
    ledger, current, _ = snapshots()
    current["ledger"] = "old"
    _, origin = coverage_snapshot.select_manifest(ledger, current, None)
    assert origin["bound"] is False


def test_probe_uses_harness_snapshot_not_new_filter_or_model_supplied_metadata(tmp_path, monkeypatch):
    from migloop import probe, verdict
    from tests.test_verdict import _run_dir
    ledger, current, recorded = snapshots()
    data = {"schema": verdict.SCHEMA, "ledger": atoms.ledger_identity(ledger), "root": f"file:{PATH}@v54",
            "defects": [], "coverage": [declaration(v, defects=[]) for v in (52, 53, 54)]}
    saved = {"data": data, "raw": json.dumps(data), "kind": "json", "errors": [],
             "harness_identity": atoms.ledger_identity(ledger), "repair_manifest": recorded}
    run = _run_dir(tmp_path, [], "", saved)
    monkeypatch.setattr(coverage, "manifest", lambda *args: deepcopy(current))
    result = probe.probe_payload(ledger, run, chain_payload={})
    assert result["repair_manifest_origin"]["source"] == "recorded"
    assert result["repair_manifest_origin"]["policy_changed"] is True
    assert result["coverage"]["counts"]["expected"] == 4
    assert result["coverage"]["missing_candidates"] == [recorded["candidates"][0]["id"]]
    assert result["coverage"]["complete"] is False
    assert verdict.validate({**data, "recorded_repair_manifest": current})
